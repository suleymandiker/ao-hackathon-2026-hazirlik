# -*- coding: utf-8 -*-
"""Bounded streaming state for pre-correlating high-volume log events.

The goal is not to replace the existing incident correlation logic.  It keeps a
bounded set of compact state buckets and retains only representative events.
The finalized representatives are then handed to IncidentContextBuilder,
while the original event cardinality is preserved via ``aggregation_count``.
"""
from __future__ import annotations

from collections import Counter, OrderedDict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Tuple


@dataclass
class IncidentState:
    key: Tuple[str, str, str, str, str]
    first_seen: int
    last_seen: int
    event_count: int = 0
    max_risk_score: int = 0
    representatives: List[Dict[str, Any]] = field(default_factory=list)
    error_family_counts: Counter = field(default_factory=Counter)
    severity_counts: Counter = field(default_factory=Counter)

    def update(self, event: Dict[str, Any], representative_limit: int) -> None:
        ts = _to_ms(event.get("event_time"))
        self.first_seen = min(self.first_seen, ts)
        self.last_seen = max(self.last_seen, ts)
        weight = max(1, int(event.get("aggregation_count", 1) or 1))
        self.event_count += weight
        self.max_risk_score = max(self.max_risk_score, int(event.get("risk_score", 0) or 0))
        family = str(event.get("error_family") or "unknown")
        severity = str(event.get("severity") or "unknown").upper()
        self.error_family_counts[family] += weight
        self.severity_counts[severity] += weight
        self._consider_representative(event, representative_limit)

    def _consider_representative(self, event: Dict[str, Any], limit: int) -> None:
        if not self.representatives:
            self.representatives.append(dict(event))
            return
        candidates = self.representatives + [event]
        candidates.sort(
            key=lambda e: (
                -int(e.get("risk_score", 0) or 0),
                _to_ms(e.get("event_time")),
            )
        )
        # Keep max-risk evidence and temporal diversity.
        selected: List[Dict[str, Any]] = []
        seen_ids = set()
        for item in candidates:
            eid = str(item.get("event_id") or "")
            if eid and eid in seen_ids:
                continue
            if eid:
                seen_ids.add(eid)
            selected.append(dict(item))
            if len(selected) >= limit:
                break
        self.representatives = selected

    def to_representatives(self) -> List[Dict[str, Any]]:
        out = []
        for index, event in enumerate(self.representatives):
            item = dict(event)
            # Cardinality belongs to the state, not to every representative.
            # Only the first representative carries the weight so downstream
            # incident metrics remain faithful (1416 events stay 1416).
            item["aggregation_count"] = self.event_count if index == 0 else 0
            item["aggregation_first_seen"] = self.first_seen
            item["aggregation_last_seen"] = self.last_seen
            item["aggregation_error_family_counts"] = dict(self.error_family_counts) if index == 0 else {}
            item["aggregation_severity_counts"] = dict(self.severity_counts) if index == 0 else {}
            item["aggregation_max_risk_score"] = self.max_risk_score
            out.append(item)
        return out


def _to_ms(value: Any) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


class StreamingIncidentStateStore:
    """Bounded in-memory state with deterministic coarse spillover buckets."""

    def __init__(self, max_states: int = 2000, representative_limit: int = 3) -> None:
        self.max_states = max(100, int(max_states))
        self.representative_limit = max(1, int(representative_limit))
        self.states: "OrderedDict[Tuple[str, str, str, str, str], IncidentState]" = OrderedDict()
        self.spill_count = 0
        self.coarsened_count = 0
        self.max_observed_states = 0

    @staticmethod
    def _key(event: Dict[str, Any]) -> Tuple[str, str, str, str, str]:
        return (
            str(event.get("service_family") or event.get("service") or "unknown").lower(),
            str(event.get("component") or "unknown").lower(),
            str(event.get("error_family") or "unknown").lower(),
            str(event.get("exception_type") or "unknown").lower(),
            str(event.get("template_id") or event.get("template") or "unknown").lower()[:140],
        )

    @staticmethod
    def _coarse_key(event: Dict[str, Any]) -> Tuple[str, str, str, str, str]:
        return (
            str(event.get("service_family") or event.get("service") or "unknown").lower(),
            str(event.get("component") or "unknown").lower(),
            str(event.get("error_family") or "unknown").lower(),
            "*",
            "*",
        )

    def add(self, event: Dict[str, Any]) -> None:
        key = self._key(event)
        state = self.states.get(key)
        if state is None and len(self.states) >= self.max_states:
            coarse_key = self._coarse_key(event)
            state = self.states.get(coarse_key)
            key = coarse_key
            self.spill_count += 1
            self.coarsened_count += 1
            if state is None:
                # No new coarse bucket is allowed once the state budget is full.
                key = ("__overflow__", "__overflow__", "__overflow__", "*", "*")
                state = self.states.get(key)
        elif state is None and len(self.states) == self.max_states - 1:
            # Reserve the final slot for a global overflow bucket. This keeps
            # the configured max_states a hard upper bound even when the
            # first coarsened key has never been seen before.
            overflow_key = ("__overflow__", "__overflow__", "__overflow__", "*", "*")
            if overflow_key not in self.states:
                key = overflow_key
                state = None
                self.spill_count += 1
                self.coarsened_count += 1
        if state is None:
            ts = _to_ms(event.get("event_time"))
            state = IncidentState(key=key, first_seen=ts, last_seen=ts)
            self.states[key] = state
        state.update(event, self.representative_limit)
        self.states.move_to_end(key)
        self.max_observed_states = max(self.max_observed_states, len(self.states))

    def to_events(self) -> List[Dict[str, Any]]:
        events: List[Dict[str, Any]] = []
        for state in sorted(self.states.values(), key=lambda s: (s.first_seen, s.last_seen)):
            events.extend(state.to_representatives())
        return events

    def stats(self) -> Dict[str, Any]:
        total_count = sum(state.event_count for state in self.states.values())
        return {
            "active_states": len(self.states),
            "max_states": self.max_states,
            "representative_limit": self.representative_limit,
            "max_observed_states": self.max_observed_states,
            "represented_events": len(self.to_events()),
            "aggregated_event_count": total_count,
            "spill_events": self.spill_count,
            "coarsened_events": self.coarsened_count,
        }
