# -*- coding: utf-8 -*-
"""Build a compact, evidence-first RCA payload from triage + causal graph."""
from __future__ import annotations

import json
from typing import Any, Dict, List


class RCAContextBuilder:
    """Create the exact context the RCA model needs, without raw log bloat."""

    def build(self, incidents: List[Dict[str, Any]], causal_graph: Dict[str, Any], triage: Any = None) -> str:
        incident_by_id = {str(i.get("incident_id")): i for i in incidents if i.get("incident_id")}
        root_ids = [str(x) for x in (causal_graph.get("root_cause_candidates") or []) if x]
        all_edges = [e for e in (causal_graph.get("edges") or []) if e.get("source") and e.get("target")]
        all_edges = sorted(
            all_edges,
            key=lambda e: (-float(e.get("score", 0.0) or 0.0), str(e.get("source", "")), str(e.get("target", "")))
        )
        top_edges = all_edges[:5]

        # Root-first selection: only the root and the strongest causal neighborhood
        # enter the expert context. Unconnected high-risk incidents are secondary support.
        anchors = []
        for nid in root_ids:
            if nid in incident_by_id and nid not in anchors:
                anchors.append(nid)
        for edge in top_edges:
            for nid in (edge.get("source"), edge.get("target")):
                nid = str(nid)
                if nid in incident_by_id and nid not in anchors:
                    anchors.append(nid)
        for nid in self._selected_ids(triage):
            if nid in incident_by_id and nid not in anchors:
                anchors.append(nid)

        if not anchors:
            ranked = sorted(
                incidents,
                key=lambda i: (-int(i.get("max_risk_score", 0) or 0), str(i.get("incident_id", "")))
            )
            anchors = [str(i.get("incident_id")) for i in ranked[:3] if i.get("incident_id")]

        selected_ids = anchors[:8]
        selected = [incident_by_id[nid] for nid in selected_ids if nid in incident_by_id]

        selected_set = set(selected_ids)
        selected_edges = [e for e in top_edges if e.get("source") in selected_set or e.get("target") in selected_set][:5]

        triage_compact = None
        if isinstance(triage, dict):
            items = []
            for item in (triage.get("selected_incidents") or [])[:4]:
                iid = str(item.get("incident_id", ""))
                if iid and iid in selected_set:
                    items.append({
                        "incident_id": iid,
                        "risk_score": item.get("max_risk_score", item.get("risk_score", 0)),
                        "reason": str(item.get("reason", item.get("why", "")))[:180],
                    })
            triage_compact = {
                "selected_incidents": items,
                "overall_priority": str(triage.get("overall_priority", triage.get("summary", "")))[:220],
            }

        graph_confidence = float(causal_graph.get("graph_confidence", 0.0) or 0.0)
        root_scores = causal_graph.get("root_cause_scores", {}) or {}
        root_score_view = {
            str(k): round(float(v or 0.0), 3)
            for k, v in root_scores.items()
            if str(k) in selected_set
        }

        # Do not duplicate graph nodes and incident candidates. The incident compact
        # record is the authoritative detail payload; graph only carries relationship edges.
        graph_edges = []
        for e in selected_edges:
            reasons = list(e.get("evidence") or e.get("reasons") or [])[:6]
            dimensions = self._evidence_dimensions(reasons)
            graph_edges.append({
                "source": e.get("source"),
                "target": e.get("target"),
                "score": round(float(e.get("score", 0.0) or 0.0), 3),
                "validation_source": e.get("validation_source", "unknown"),
                "judge_confidence": e.get("judge_confidence"),
                "evidence": reasons,
                "evidence_dimensions": sorted(dimensions),
                "independent_evidence_count": len(dimensions & {"temporal", "dependency", "propagation"}),
            })

        payload = {
            "task": "root_cause_analysis",
            "instructions": {
                "distinguish_root_cause_from_symptoms": True,
                "use_event_ids_as_evidence": True,
                "do_not_treat_risk_as_ground_truth": True,
                "do_not_claim_causality_without_temporal_and_dependency_evidence": True,
                "no_edges_means_no_confirmed_root_cause": True,
                "prefer_upstream_nodes_with_downstream_effects": True,
                "numeric_confidence_source": "causal_graph.authoritative_confidence",
                "do_not_override_numeric_graph_confidence": True,
                "report_evidence_diversity": True,
            },
            "triage": triage_compact,
            "causal_graph": {
                "root_cause_candidates": root_ids[:3],
                "root_cause_scores": root_score_view,
                "graph_confidence": round(graph_confidence, 3),
                "authoritative_confidence": round(graph_confidence, 3),
                "edge_count": causal_graph.get("edge_count", 0),
                "root_cause_status": causal_graph.get("root_cause_status", "unconfirmed"),
                "edges": graph_edges,
            },
            "incident_candidates": [self._compact_incident(i) for i in selected],
            "context_selection": {
                "anchor_incidents": selected_ids,
                "root_candidates": root_ids[:3],
                "selection_policy": "root_first_plus_top_causal_edges_then_triage_support",
            },
            "context_budget": {
                "max_incidents": len(selected),
                "max_graph_edges": len(graph_edges),
                "max_triage_items": 4,
                "target_estimated_input_tokens": 5000,
                "max_events_per_incident": 1,
                "message_max_chars": 220,
                "raw_log_blocks_included": False,
                "duplicate_graph_node_payload": False,
            },
        }
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))

    @staticmethod
    def _evidence_dimensions(reasons: List[str]) -> set[str]:
        reasons = set(reasons or [])
        dimensions = set()
        if reasons & {"tight_temporal_precedence", "temporal_precedence", "overlapping_incident_windows"}:
            dimensions.add("temporal")
        if reasons & {
            "explicit_dependency_direction", "known_dependency_direction",
            "inferred_dependency_direction", "cross_domain_dependency", "inferred_topology",
        }:
            dimensions.add("dependency")
        if reasons & {
            "strong_error_propagation", "timeout_to_retry", "http_failure_to_retry",
            "application_error_to_retry",
        }:
            dimensions.add("propagation")
        return dimensions

    @staticmethod
    def _selected_ids(triage: Any) -> set[str]:
        if not isinstance(triage, dict):
            return set()
        return {
            str(item.get("incident_id"))
            for item in (triage.get("selected_incidents") or [])
            if item.get("incident_id")
        }

    @staticmethod
    def _compact_incident(incident: Dict[str, Any]) -> Dict[str, Any]:
        events = sorted(
            list(incident.get("events") or []),
            key=lambda e: (-int(e.get("risk_score", 0) or 0), str(e.get("event_id", "")))
        )[:1]
        return {
            "incident_id": incident.get("incident_id"),
            "time_range": incident.get("time_range", {}),
            "services": list(incident.get("services") or [])[:4],
            "service_families": list(incident.get("service_families") or [])[:4],
            "event_count": incident.get("event_count", 0),
            "max_risk_score": incident.get("max_risk_score", 0),
            "error_family_counts": dict(incident.get("error_family_counts") or {}),
            "severity_counts": dict(incident.get("severity_counts") or {}),
            "topology_dependencies": list(incident.get("topology_dependencies") or [])[:4],
            "topology_upstreams": list(incident.get("topology_upstreams") or [])[:4],
            "topology_downstreams": list(incident.get("topology_downstreams") or [])[:4],
            "evidence_ids": list(incident.get("evidence_ids") or [])[:3],
            "evidence_count": incident.get("evidence_count", len(incident.get("evidence_ids") or [])),
            "events": [RCAContextBuilder._compact_event(e) for e in events],
        }

    @staticmethod
    def _compact_event(event: Dict[str, Any]) -> Dict[str, Any]:
        keep = (
            "event_id", "event_time", "severity", "service", "service_family",
            "component", "exception_type", "error_family", "message", "risk_score",
            "occurrences_1m",
        )
        result = {k: event[k] for k in keep if k in event and event[k] not in (None, "", {}, [])}
        if "message" in result:
            message = str(result["message"]).replace("\n", " | ").strip()
            result["message"] = message[:220] + ("..." if len(message) > 220 else "")
        return result

