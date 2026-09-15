# -*- coding: utf-8 -*-
"""LLM judge for ambiguous incident-correlation decisions.

The deterministic correlator remains authoritative for strong/weak matches.
Only grey-zone pairs are presented to the model. The model can recommend merge
or keep-separate, but the result is always recorded as evidence and never used
without a deterministic safety gate.
"""
from __future__ import annotations

import json
import re
import os
from typing import Any, Dict, List, Tuple

from ai_engine import call_ai_agent, load_prompt


class IncidentCorrelationJudge:
    """Use DeepSeek only for ambiguous pair decisions."""

    def __init__(self, low: float = 0.35, high: float = 0.80, max_pairs: int = 8, batch_size: int = 4, max_batch_tokens: int = 2200):
        self.low = low
        self.high = high
        self.max_pairs = int(os.environ.get("AIOPS_CORRELATION_MAX_PAIRS", max_pairs))
        self.batch_size = max(1, int(os.environ.get("AIOPS_CORRELATION_BATCH_SIZE", batch_size)))
        self.max_batch_tokens = max(800, int(os.environ.get("AIOPS_CORRELATION_MAX_BATCH_TOKENS", max_batch_tokens)))
        self.stats: Dict[str, Any] = {
            "calls": 0,
            "success": 0,
            "rejected": 0,
            "ambiguous_pairs": 0,
            "merge_decisions": 0,
            "separate_decisions": 0,
            "accepted_merges": 0,
            "rejected_merges": 0,
            "ai_status": "not_run",
            "token_usage": {"prompt_tokens": 0, "cached_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            "batches": 0,
            "max_batch_tokens": self.max_batch_tokens,
            "largest_estimated_batch_tokens": 0,
        }
        self.last_decisions: List[Dict[str, Any]] = []

    def decide(self, pair_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
        if not pair_rows:
            self.stats["ai_status"] = "not_needed"
            return {}
        rows = pair_rows[: self.max_pairs]
        self.stats["ambiguous_pairs"] += len(rows)
        system = load_prompt("common_system.md") + "\n\n" + load_prompt("incident_correlation_judge.md")
        all_clean: Dict[str, Dict[str, Any]] = {}
        batch: List[Dict[str, Any]] = []
        estimated_tokens = 0
        for row in rows:
            row_tokens = self._estimate_tokens(self._compact_pair(row))
            if batch and (len(batch) >= self.batch_size or estimated_tokens + row_tokens > self.max_batch_tokens):
                out = self._decide_batch(batch, system)
                all_clean.update(out)
                batch = []
                estimated_tokens = 0
            batch.append(row)
            estimated_tokens += row_tokens
        if batch:
            out = self._decide_batch(batch, system)
            all_clean.update(out)
        self.last_decisions = [{"pair_id": k, **v} for k, v in all_clean.items()]
        self.stats["merge_decisions"] += sum(1 for v in all_clean.values() if v["decision"] == "merge")
        self.stats["separate_decisions"] += sum(1 for v in all_clean.values() if v["decision"] == "separate")
        self.stats["ai_status"] = "success" if all_clean else "empty_or_invalid"
        return all_clean

    def _decide_batch(self, rows: List[Dict[str, Any]], system: str) -> Dict[str, Dict[str, Any]]:
        prompt = self._build_prompt(rows)
        self.stats["batches"] += 1
        self.stats["largest_estimated_batch_tokens"] = max(self.stats["largest_estimated_batch_tokens"], self._estimate_tokens(prompt))
        raw, _duration, usage = call_ai_agent(
            "Incident_Correlation_Judge", system, prompt, temperature=0.0, max_tokens=320,
            response_format={"type": "json_object"}, return_usage=True,
        )
        self.stats["calls"] += 1
        self._accumulate_usage(usage)
        try:
            result = self._parse_json(raw)
        except Exception as exc:
            self.stats["rejected"] += 1
            return {}
        decisions = result.get("decisions") if isinstance(result, dict) else None
        if not isinstance(decisions, list):
            self.stats["rejected"] += 1
            return {}
        allowed = {r["pair_id"] for r in rows}
        clean: Dict[str, Dict[str, Any]] = {}
        for item in decisions:
            if not isinstance(item, dict):
                continue
            pair_id = str(item.get("pair_id", "")).strip()
            decision = str(item.get("decision", "")).lower().strip()
            try:
                confidence = float(item.get("confidence", 0.0))
            except (TypeError, ValueError):
                confidence = 0.0
            if pair_id not in allowed or decision not in {"merge", "separate"}:
                continue
            clean[pair_id] = {"decision": decision, "confidence": max(0.0, min(1.0, confidence)), "short_reason": str(item.get("short_reason", ""))[:180]}
        if clean:
            self.stats["success"] += 1
        else:
            self.stats["rejected"] += 1
        return clean

    @classmethod
    def _compact_pair(cls, row: Dict[str, Any]) -> Dict[str, Any]:
        def compact_side(value: Any) -> Dict[str, Any]:
            data = value if isinstance(value, dict) else {}
            out: Dict[str, Any] = {}
            for key in ("incident_id", "event_count", "max_risk_score", "services", "service_families", "domains", "error_families", "exception_types"):
                if key in data:
                    val = data[key]
                    if isinstance(val, list):
                        out[key] = [str(x)[:80] for x in val[:6]]
                    elif isinstance(val, dict):
                        out[key] = {str(k)[:60]: v for k, v in list(val.items())[:6]}
                    else:
                        out[key] = val
            return out
        return {
            "pair_id": row.get("pair_id", ""),
            "deterministic_score": round(float(row.get("score", 0.0) or 0.0), 3),
            "reasons": list(row.get("reasons", []))[:8],
            "time_delta_ms": row.get("time_delta_ms", 0),
            "left": compact_side(row.get("left", {})),
            "right": compact_side(row.get("right", {})),
        }

    @staticmethod
    def _estimate_tokens(value: Any) -> int:
        try:
            raw = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        except (TypeError, ValueError):
            raw = str(value)
        return max(1, (len(raw) + 3) // 4)

    @staticmethod
    def _build_prompt(rows: List[Dict[str, Any]]) -> str:
        compact = []
        for row in rows:
            compact.append({
                "pair_id": row["pair_id"],
                "deterministic_score": round(float(row["score"]), 3),
                "reasons": row.get("reasons", []),
                "time_delta_ms": row.get("time_delta_ms", 0),
                "left": row.get("left", {}),
                "right": row.get("right", {}),
            })
        return json.dumps({
            "task": "For each ambiguous pair, decide whether both events belong to the same incident.",
            "pairs": compact,
        }, ensure_ascii=False, indent=2)

    @staticmethod
    def _parse_json(raw: str) -> Dict[str, Any]:
        text = str(raw or "").strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.I | re.S).strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            start = text.find("{")
            end = text.rfind("}")
            if start >= 0 and end > start:
                return json.loads(text[start:end + 1])
            raise

    def _accumulate_usage(self, usage: Dict[str, Any]) -> None:
        if not usage:
            return
        target = self.stats["token_usage"]
        for key in target:
            target[key] += int(usage.get(key, 0) or 0)
