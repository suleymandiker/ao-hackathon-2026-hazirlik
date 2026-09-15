# -*- coding: utf-8 -*-
"""Compact, diverse, token-bounded incident selection for Agent 1."""
from __future__ import annotations

import json
from typing import Any, Dict, List


def estimate_json_tokens(value: Any) -> int:
    """Cheap tokenizer-free estimate; approximately 4 JSON chars per token."""
    try:
        raw = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    except (TypeError, ValueError):
        raw = str(value)
    return max(1, (len(raw) + 3) // 4)


def compact_triage_incident(incident: Dict[str, Any]) -> Dict[str, Any]:
    """Keep only fields useful to Agent 1; exclude the full representative event array."""
    events = sorted(
        list(incident.get("events") or []),
        key=lambda e: (-int(e.get("risk_score", 0) or 0), str(e.get("event_id", ""))),
    )[:1]
    compact = {
        "incident_id": incident.get("incident_id"),
        "time_range": incident.get("time_range", {}),
        "services": list(incident.get("services") or [])[:6],
        "inferred_services": list(incident.get("inferred_services") or [])[:6],
        "service_families": list(incident.get("service_families") or [])[:6],
        "event_count": int(incident.get("event_count", 0) or 0),
        "max_risk_score": int(incident.get("max_risk_score", 0) or 0),
        "error_family_counts": dict(list((incident.get("error_family_counts") or {}).items())[:6]),
        "severity_counts": dict(list((incident.get("severity_counts") or {}).items())[:6]),
        "topology_dependencies": list(incident.get("topology_dependencies") or [])[:6],
        "topology_upstreams": list(incident.get("topology_upstreams") or [])[:6],
        "topology_downstreams": list(incident.get("topology_downstreams") or [])[:6],
        "evidence_ids": list(incident.get("evidence_ids") or [])[:5],
        "evidence_count": int(incident.get("evidence_count", 0) or 0),
        "correlation": {
            "evidence": list(((incident.get("correlation") or {}).get("evidence") or []))[:6],
            "explicit_trace": float(((incident.get("correlation") or {}).get("explicit_trace", 0.0) or 0.0)),
            "pairwise_max": float(((incident.get("correlation") or {}).get("pairwise_max", 0.0) or 0.0)),
        },
    }
    if events:
        event = events[0]
        message = str(event.get("message", "")).replace("\n", " | ").strip()
        compact["representative_event"] = {
            k: event[k]
            for k in (
                "event_id", "event_time", "severity", "service", "inferred_service",
                "service_family", "error_family", "domain", "exception_type", "risk_score",
            )
            if k in event and event[k] not in (None, "", {}, [])
        }
        if message:
            compact["representative_event"]["message"] = message[:220]
    return compact


def select_triage_incidents(
    incidents: List[Dict[str, Any]], top_k: int = 18, max_tokens: int = 12000
) -> List[Dict[str, Any]]:
    """Select risk-first but diverse incidents under a hard estimated token budget."""
    if not incidents:
        return []

    def risk(inc: Dict[str, Any]) -> int:
        return int(inc.get("max_risk_score", 0) or 0)

    def start_value(inc: Dict[str, Any]) -> str:
        return str((inc.get("time_range") or {}).get("start", ""))

    ranked = sorted(
        incidents,
        key=lambda inc: (
            -risk(inc),
            -int(inc.get("event_count", 0) or 0),
            -int(inc.get("evidence_count", 0) or 0),
            start_value(inc),
            str(inc.get("incident_id", "")),
        ),
    )

    selected: List[Dict[str, Any]] = []
    seen_services, seen_errors, seen_domains, seen_time_buckets = set(), set(), set(), set()
    remaining = list(ranked)

    while remaining and len(selected) < top_k:
        best = None
        best_key = None
        for inc in remaining:
            compact = compact_triage_incident(inc)
            services = {str(x).lower() for x in compact.get("service_families", []) if x}
            if not services:
                services = {str(x).lower() for x in compact.get("services", []) if x}
            errors = {str(x).lower() for x in (compact.get("error_family_counts") or {}).keys() if x}
            domain_value = str((compact.get("representative_event") or {}).get("domain", "")).lower()
            bucket = start_value(inc)[:15]
            novelty = (
                2.2 * len(services - seen_services)
                + 1.8 * len(errors - seen_errors)
                + 1.2 * (1 if domain_value and domain_value not in seen_domains else 0)
                + 0.8 * (1 if bucket and bucket not in seen_time_buckets else 0)
            )
            score = (risk(inc) / 100.0) * 5.0 + novelty + min(2.0, int(inc.get("event_count", 0) or 0) / 100.0)
            key = (score, risk(inc), int(inc.get("event_count", 0) or 0), str(inc.get("incident_id", "")))
            if best_key is None or key > best_key:
                best, best_key = inc, key

        if best is None:
            break
        compact = compact_triage_incident(best)
        if estimate_json_tokens(selected + [compact]) > max_tokens:
            break
        selected.append(compact)

        services = {str(x).lower() for x in compact.get("service_families", []) if x}
        if not services:
            services = {str(x).lower() for x in compact.get("services", []) if x}
        seen_services.update(services)
        seen_errors.update(str(x).lower() for x in (compact.get("error_family_counts") or {}).keys() if x)
        domain_value = str((compact.get("representative_event") or {}).get("domain", "")).lower()
        if domain_value:
            seen_domains.add(domain_value)
        bucket = str((compact.get("time_range") or {}).get("start", ""))[:15]
        if bucket:
            seen_time_buckets.add(bucket)
        iid = str(best.get("incident_id", ""))
        remaining = [inc for inc in remaining if str(inc.get("incident_id", "")) != iid]

    return sorted(selected, key=lambda i: str((i.get("time_range") or {}).get("start", "")))
