"""Bounded AI-assisted Drain3 policy tuner.

The model sees only a small representative sample and template statistics.
Python/Drain3 remains authoritative for mining; the LLM only recommends a
small parameter change. Tuned policies are cached by sample fingerprint.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import time
from typing import Any, Dict, Iterable, List

from ai_engine import call_ai_agent, load_prompt
from drain3 import TemplateMiner
from drain3.template_miner_config import TemplateMinerConfig
from drain3.masking import MaskingInstruction


DEFAULT_SIM_TH = float(os.getenv("AIOPS_DRAIN_SIM_TH", "0.50"))
DEFAULT_DEPTH = int(os.getenv("AIOPS_DRAIN_DEPTH", "4"))


class DrainPolicyTuner:
    def __init__(
        self,
        cache_path: str | None = None,
        enabled: bool | None = None,
        max_calls: int | None = None,
        sample_events: int | None = None,
        top_templates: int | None = None,
    ):
        self.enabled = (os.getenv("AIOPS_DRAIN_AUTOTUNE_ENABLED", "1").lower() in {"1", "true", "yes", "on"}) if enabled is None else enabled
        self.max_calls = max(1, int(os.getenv("AIOPS_DRAIN_AUTOTUNE_MAX_CALLS", "2"))) if max_calls is None else max(1, int(max_calls))
        self.sample_events = max(50, int(os.getenv("AIOPS_DRAIN_AUTOTUNE_SAMPLE_EVENTS", "250"))) if sample_events is None else max(50, int(sample_events))
        self.top_templates = max(5, int(os.getenv("AIOPS_DRAIN_AUTOTUNE_TOP_TEMPLATES", "12"))) if top_templates is None else max(5, int(top_templates))
        self.cache_path = cache_path or os.getenv("AIOPS_DRAIN_POLICY_CACHE_PATH", "data/.aiops_drain_policy.sqlite3")
        self.last_result: Dict[str, Any] = {"enabled": self.enabled, "cache_hit": False, "calls": 0}

    @staticmethod
    def _mask_config() -> List[MaskingInstruction]:
        return [
            MaskingInstruction(pattern=r"\b\d{1,3}(?:\.\d{1,3}){3}\b", mask_with="IP"),
            MaskingInstruction(pattern=r"\b[0-9a-fA-F]{8}-([0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}\b", mask_with="UUID"),
            MaskingInstruction(pattern=r"(?<![a-zA-Z0-9])\b\d+\b(?![a-zA-Z0-9])", mask_with="NUM"),
            MaskingInstruction(pattern=r"\b0x[0-9a-fA-F]+\b", mask_with="HEX"),
            MaskingInstruction(pattern=r"(/[a-zA-Z0-9\._\-]+)+", mask_with="PATH"),
        ]

    @classmethod
    def _miner_preview(cls, sim_th: float, depth: int) -> TemplateMiner:
        cfg = TemplateMinerConfig()
        cfg.profiling_enabled = False
        cfg.drain_sim_th = float(max(0.1, min(0.99, sim_th)))
        cfg.drain_depth = int(max(2, min(10, depth)))
        cfg.masking_instructions = cls._mask_config()
        return TemplateMiner(config=cfg)

    @classmethod
    def _preview(cls, messages: List[str], sim_th: float, depth: int, top_n: int) -> Dict[str, Any]:
        miner = cls._miner_preview(sim_th, depth)
        clusters = {}
        wildcard_counts = 0
        token_counts = 0
        samples = []
        for message in messages[:500]:
            clean = re.sub(r"\s+", " ", str(message).strip())
            if not clean:
                continue
            result = miner.add_log_message(clean)
            tpl = str(result.get("template_mined", "UNKNOWN_PATTERN"))
            clusters[tpl] = int(result.get("cluster_size", 1) or 1)
            wildcard_counts += tpl.count("<*>")
            token_counts += max(1, len(tpl.split()))
            if len(samples) < 5:
                samples.append({"message": clean[:260], "template": tpl[:260]})
        ranked = sorted(clusters.items(), key=lambda x: x[1], reverse=True)[:top_n]
        unique = len(clusters)
        processed = sum(clusters.values())
        coverage = processed / max(1, len(messages))
        wildcard_ratio = wildcard_counts / max(1, token_counts)
        return {
            "unique_templates": unique,
            "messages": len(messages),
            "top_templates": [{"template": t[:300], "count": c} for t, c in ranked],
            "wildcard_ratio": round(wildcard_ratio, 4),
            "samples": samples,
            "coverage": round(coverage, 4),
        }

    def _fingerprint(self, messages: List[str]) -> str:
        normalized = "\n".join(re.sub(r"\s+", " ", str(x).strip())[:500] for x in messages[: self.sample_events])
        raw = json.dumps({"schema": 1, "messages": normalized, "base_sim_th": DEFAULT_SIM_TH, "base_depth": DEFAULT_DEPTH}, ensure_ascii=False, sort_keys=True).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()

    def _cache_get(self, key: str) -> Dict[str, Any] | None:
        path = os.path.abspath(self.cache_path)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        try:
            with sqlite3.connect(path, timeout=5) as conn:
                conn.execute("CREATE TABLE IF NOT EXISTS drain_policies (cache_key TEXT PRIMARY KEY, payload TEXT NOT NULL, created_at REAL NOT NULL, accessed_at REAL NOT NULL)")
                row = conn.execute("SELECT payload FROM drain_policies WHERE cache_key=?", (key,)).fetchone()
                if not row:
                    return None
                conn.execute("UPDATE drain_policies SET accessed_at=? WHERE cache_key=?", (time.time(), key))
                return json.loads(row[0])
        except Exception:
            return None

    def _cache_put(self, key: str, payload: Dict[str, Any]) -> None:
        path = os.path.abspath(self.cache_path)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        try:
            with sqlite3.connect(path, timeout=5) as conn:
                conn.execute("CREATE TABLE IF NOT EXISTS drain_policies (cache_key TEXT PRIMARY KEY, payload TEXT NOT NULL, created_at REAL NOT NULL, accessed_at REAL NOT NULL)")
                now = time.time()
                conn.execute("INSERT OR REPLACE INTO drain_policies(cache_key,payload,created_at,accessed_at) VALUES(?,?,?,?)", (key, json.dumps(payload, ensure_ascii=False), now, now))
                conn.execute("DELETE FROM drain_policies WHERE cache_key IN (SELECT cache_key FROM drain_policies ORDER BY accessed_at DESC LIMIT -1 OFFSET 64)")
        except Exception:
            pass

    @staticmethod
    def _build_prompt(sim_th: float, depth: int, preview: Dict[str, Any]) -> str:
        return json.dumps({
            "task": "Tune Drain3 for high-fidelity SRE log templates.",
            "goal": "Preserve meaningful exception/error/status detail while avoiding over-fragmentation.",
            "current": {"sim_th": round(sim_th, 3), "depth": depth},
            "evidence": preview,
            "allowed_recommendations": ["optimal_fidelity", "increase_sim_th", "decrease_sim_th", "increase_depth", "decrease_depth", "keep"],
            "output_contract": {"fidelity_score": "0..10", "recommendation": "one allowed value", "new_sim_th": "number 0.10..0.95", "new_depth": "integer 2..10", "reason": "<=240 chars"},
        }, ensure_ascii=False, indent=2)

    @staticmethod
    def _parse(raw: str) -> Dict[str, Any]:
        text = str(raw or "").strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.I | re.S).strip()
        try:
            obj = json.loads(text)
        except json.JSONDecodeError:
            start, end = text.find("{"), text.rfind("}")
            if start < 0 or end <= start:
                raise
            obj = json.loads(text[start:end + 1])
        return obj if isinstance(obj, dict) else {}

    def tune(self, messages: Iterable[str], dataset_id: str = "default") -> Dict[str, Any]:
        msgs = [str(x) for x in messages if str(x).strip()][: self.sample_events]
        result = {"enabled": self.enabled, "cache_hit": False, "calls": 0, "sim_th": DEFAULT_SIM_TH, "depth": DEFAULT_DEPTH, "dataset_id": dataset_id}
        if not self.enabled or len(msgs) < 50:
            result["reason"] = "disabled_or_small_sample"
            self.last_result = result
            return result

        key = self._fingerprint(msgs)
        cached = self._cache_get(f"{dataset_id}:{key}")
        if cached:
            result.update(cached)
            result["cache_hit"] = True
            self.last_result = result
            print(f"[DRAIN TUNER] CACHE HIT | sim_th={result['sim_th']:.2f} | depth={result['depth']}")
            return result

        sim_th, depth = DEFAULT_SIM_TH, DEFAULT_DEPTH
        history = []
        system = load_prompt("drain3_autotuner.md")
        for iteration in range(1, self.max_calls + 1):
            preview = self._preview(msgs, sim_th, depth, self.top_templates)
            prompt = self._build_prompt(sim_th, depth, preview)
            raw, duration, usage = call_ai_agent(
                "Drain3_AutoTuner", system, prompt, temperature=0.0, max_tokens=320,
                response_format={"type": "json_object"}, return_usage=True,
            )
            result["calls"] += 1
            try:
                decision = self._parse(raw)
            except Exception as exc:
                history.append({"iteration": iteration, "error": str(exc)[:200]})
                break
            score = max(0.0, min(10.0, float(decision.get("fidelity_score", 0.0) or 0.0)))
            recommendation = str(decision.get("recommendation", "keep")).strip().lower()
            new_sim = max(0.10, min(0.95, float(decision.get("new_sim_th", sim_th) or sim_th)))
            new_depth = max(2, min(10, int(decision.get("new_depth", depth) or depth)))
            if recommendation == "increase_sim_th" and new_sim <= sim_th:
                new_sim = min(0.95, round(sim_th + 0.10, 2))
            if recommendation == "decrease_sim_th" and new_sim >= sim_th:
                new_sim = max(0.10, round(sim_th - 0.10, 2))
            if recommendation == "increase_depth" and new_depth <= depth:
                new_depth = min(10, depth + 1)
            if recommendation == "decrease_depth" and new_depth >= depth:
                new_depth = max(2, depth - 1)
            history.append({"iteration": iteration, "sim_th": sim_th, "depth": depth, "score": score, "recommendation": recommendation, "new_sim_th": new_sim, "new_depth": new_depth, "reason": str(decision.get("reason", ""))[:240], "duration": round(duration, 3), "usage": usage or {}})
            sim_th, depth = new_sim, new_depth
            if recommendation in {"optimal_fidelity", "keep"} or score >= 8.0:
                break

        result.update({"sim_th": round(sim_th, 3), "depth": int(depth), "fingerprint": key, "history": history, "reason": "ai_tuned"})
        self._cache_put(f"{dataset_id}:{key}", {k: v for k, v in result.items() if k not in {"cache_hit", "calls"}})
        self.last_result = result
        print(f"[DRAIN TUNER] DONE | calls={result['calls']} | sim_th={result['sim_th']:.2f} | depth={result['depth']}")
        return result
