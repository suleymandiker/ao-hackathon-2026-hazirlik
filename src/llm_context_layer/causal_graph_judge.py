# -*- coding: utf-8 -*-
"""LLM judge for ambiguous causal relationships with optional expert escalation."""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List

from ai_engine import call_ai_agent, MODELS_CONFIG, load_prompt


class CausalGraphJudge:
    """Use a fast model first; escalate only unresolved critical candidates."""

    def __init__(
        self,
        low: float = 0.45,
        high: float = 0.80,
        max_pairs: int = 24,
        batch_size: int = 4,
        max_batch_tokens: int = 2600,
        escalation_score: float = 0.65,
        max_escalations: int = 2,
    ):
        self.low = low
        self.high = high
        self.max_pairs = max_pairs
        self.batch_size = max(1, int(batch_size))
        self.max_batch_tokens = max(800, int(max_batch_tokens))
        self.escalation_score = escalation_score
        self.max_escalations = max_escalations
        self.stats = {
            "calls": 0,
            "success": 0,
            "rejected": 0,
            "ambiguous_pairs": 0,
            "edge_decisions": 0,
            "accepted_edges": 0,
            "rejected_edges": 0,
            "token_usage": {"prompt_tokens": 0, "cached_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            "expert_escalations": 0,
            "expert_success": 0,
            "expert_decisions": 0,
            "expert_token_usage": {"prompt_tokens": 0, "cached_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            "candidate_pairs_seen": 0,
            "candidate_pairs_selected": 0,
            "fast_batches": 0,
            "max_batch_tokens": self.max_batch_tokens,
            "largest_estimated_batch_tokens": 0,
        }

    def decide(self, pair_rows: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        if not pair_rows:
            return {}
        # Bound model load: rank ambiguous candidates and evaluate in small batches.
        ranked = sorted(
            pair_rows,
            key=lambda r: (
                -float(r.get("deterministic_score", 0.0) or 0.0),
                -len(r.get("reasons") or []),
                -int(r.get("time_delta_ms", 0) or 0),
                str(r.get("pair_id", "")),
            ),
        )
        rows = ranked[: self.max_pairs]
        self.stats["ambiguous_pairs"] += len(rows)
        self.stats["candidate_pairs_seen"] = len(pair_rows)
        self.stats["candidate_pairs_selected"] = len(rows)
        decisions: Dict[str, Dict[str, Any]] = {}
        batch: List[Dict[str, Any]] = []
        estimated_tokens = 0
        for row in rows:
            row_tokens = self._estimate_tokens(row)
            if batch and (
                len(batch) >= self.batch_size
                or estimated_tokens + row_tokens > self.max_batch_tokens
            ):
                self.stats["largest_estimated_batch_tokens"] = max(
                    self.stats["largest_estimated_batch_tokens"], estimated_tokens
                )
                decisions.update(self._decide_with_agent(
                    batch,
                    agent_key="Causal_Graph_Judge",
                    stats_bucket="fast",
                ))
                batch = []
                estimated_tokens = 0
            batch.append(row)
            estimated_tokens += row_tokens
        if batch:
            self.stats["largest_estimated_batch_tokens"] = max(
                self.stats["largest_estimated_batch_tokens"], estimated_tokens
            )
            decisions.update(self._decide_with_agent(
                batch,
                agent_key="Causal_Graph_Judge",
                stats_bucket="fast",
            ))

        unresolved = [
            row for row in rows
            if row["pair_id"] not in decisions
            and float(row.get("deterministic_score", 0.0) or 0.0) >= self.escalation_score
        ]
        if unresolved:
            for row in unresolved[: self.max_escalations]:
                result = self._decide_with_agent(
                    [row],
                    agent_key="Ajan_2_Causal_Expert",
                    stats_bucket="expert",
                )
                decision = result.get(row["pair_id"])
                if decision:
                    decision["validation_model"] = MODELS_CONFIG["Ajan_2_Causal_Expert"]["model_id"]
                    decisions[row["pair_id"]] = decision
        return decisions

    def _decide_with_agent(
        self,
        rows: List[Dict[str, Any]],
        agent_key: str,
        stats_bucket: str,
    ) -> Dict[str, Dict[str, Any]]:
        pairs_json = json.dumps(rows, ensure_ascii=False, indent=2)
        if stats_bucket == "expert":
            system = load_prompt("common_system.md") + "\n\n" + load_prompt("causal_graph_expert.md")
        else:
            system = load_prompt("common_system.md") + "\n\n" + load_prompt("causal_graph_judge.md")
        prompt = pairs_json
        raw, _, usage = call_ai_agent(
            agent_key, system, prompt,
            temperature=0.0, max_tokens=512,
            response_format={"type": "json_object"}, return_usage=True,
        )
        if stats_bucket == "fast":
            self.stats["calls"] += 1
            self.stats["fast_batches"] += 1
            self._usage(usage, "token_usage")
        else:
            self.stats["expert_escalations"] += 1
            self._usage(usage, "expert_token_usage")

        try:
            obj = self._parse(raw)
        except Exception:
            if stats_bucket == "fast":
                self.stats["rejected"] += 1
            return {}

        decisions = obj.get("decisions") or []
        if isinstance(decisions, dict):
            decisions = [{"pair_id": k, **v} for k, v in decisions.items()]
        out: Dict[str, Dict[str, Any]] = {}
        allowed = {r["pair_id"] for r in rows}
        for d in decisions:
            pid = str(d.get("pair_id", ""))
            decision = str(d.get("decision", "separate")).lower()
            conf = max(0.0, min(1.0, float(d.get("confidence", 0.0) or 0.0)))
            if pid not in allowed or decision not in {"edge", "separate"}:
                continue
            out[pid] = {
                "pair_id": pid,
                "decision": decision,
                "confidence": conf,
                "short_reason": str(d.get("short_reason", ""))[:400],
                "validation_model": MODELS_CONFIG["Causal_Graph_Judge"]["model_id"] if stats_bucket == "fast" else MODELS_CONFIG["Ajan_2_Causal_Expert"]["model_id"],
            }
            if stats_bucket == "fast":
                self.stats["edge_decisions"] += 1
                if decision == "edge" and conf >= self.high:
                    self.stats["accepted_edges"] += 1
                elif decision == "edge":
                    self.stats["rejected_edges"] += 1
            else:
                self.stats["expert_success"] += 1
                self.stats["expert_decisions"] += 1
        if stats_bucket == "fast" and out:
            self.stats["success"] += 1
        elif stats_bucket == "expert" and out:
            self.stats["expert_success"] += 0  # counted per decision above
        return out

    @staticmethod
    def _estimate_tokens(value: Any) -> int:
        try:
            raw = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        except (TypeError, ValueError):
            raw = str(value)
        return max(1, (len(raw) + 3) // 4)

    @staticmethod
    def _parse(raw: str) -> Dict[str, Any]:
        text = str(raw or "").strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.I | re.S).strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            start, end = text.find("{"), text.rfind("}")
            if start < 0 or end <= start:
                raise
            return json.loads(text[start:end + 1])

    def _usage(self, usage: Dict[str, Any], bucket: str) -> None:
        target = self.stats[bucket]
        if not usage:
            return
        for key in target:
            if key in usage:
                target[key] += int(usage.get(key, 0) or 0)
