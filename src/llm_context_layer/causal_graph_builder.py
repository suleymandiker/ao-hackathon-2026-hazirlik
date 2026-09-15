# -*- coding: utf-8 -*-
"""Evidence-first dependency-aware causal graph with optional LLM judge."""
from __future__ import annotations

import hashlib
from typing import Any, Dict, List, Tuple, Optional

from .causal_graph_judge import CausalGraphJudge


class CausalGraphBuilder:
    """Build directed incident-to-incident causal hypotheses.

    Candidate generation is intentionally broader than edge acceptance:
    dependency/temporal/downstream evidence creates candidates, deterministic
    strong evidence can auto-accept them, and only grey-zone candidates go to
    the LLM judge. An absence of edges is represented honestly as an
    unconfirmed root-cause state.
    """

    # (upstream family, downstream family)
    _DEPENDENCY_PAIRS = {
        ("database", "payment"),
        ("database", "order"),
        ("database", "gateway"),
        ("database", "checkout"),
        ("postgres", "payment"),
        ("postgres", "order"),
        ("redis", "payment"),
        ("redis", "order"),
        ("redis", "gateway"),
        ("identity", "payment"),
        ("identity", "order"),
        ("identity", "gateway"),
        ("payment", "gateway"),
        ("payment", "checkout"),
        ("order", "gateway"),
        ("order", "checkout"),
        ("checkout", "gateway"),
    }

    _SERVICE_ALIASES = {
        "payment-api": "payment",
        "payment-service": "payment",
        "payment-worker": "payment",
        "order-api": "order",
        "order-service": "order",
        "order-worker": "order",
        "identity-api": "identity",
        "identity-service": "identity",
        "auth": "identity",
        "auth-service": "identity",
        "postgresql": "database",
        "postgres-db": "database",
        "postgres": "database",
        "db": "database",
        "database-service": "database",
        "redis-cache": "redis",
        "redis-service": "redis",
        "gateway-api": "gateway",
        "gateway-service": "gateway",
        "checkout-api": "checkout",
        "checkout-service": "checkout",
    }

    _DOWNSTREAM_ERROR_MAP = {
        "connection": {"http_5xx", "timeout", "application_error", "other"},
        "timeout": {"retry", "http_5xx", "application_error"},
        "http_5xx": {"retry", "timeout", "application_error"},
        "application_error": {"retry", "http_5xx", "timeout"},
    }

    def __init__(
        self,
        max_edge_seconds: int = 300,
        min_edge_score: float = 0.35,
        judge: Optional[CausalGraphJudge] = None,
        judge_low: float = 0.40,
        judge_high: float = 0.80,
    ):
        self.max_edge_ms = max_edge_seconds * 1000
        self.min_edge_score = min_edge_score
        self.judge = judge if judge is not None else CausalGraphJudge(low=judge_low, high=judge_high)
        self.judge_low = judge_low
        self.judge_high = judge_high
        self.stats: Dict[str, Any] = {}
        self.max_llm_candidates = max(8, int(__import__("os").environ.get("AIOPS_CAUSAL_MAX_LLM_CANDIDATES", "20")))

    def build(self, incidents: List[Dict[str, Any]]) -> Dict[str, Any]:
        nodes = [self._node(i) for i in incidents]
        edges: List[Dict[str, Any]] = []
        ambiguous: List[Dict[str, Any]] = []
        candidate_count = 0
        rejected_weak = 0

        for i, left in enumerate(nodes):
            for j, right in enumerate(nodes):
                if i == j or left["start_ms"] >= right["start_ms"]:
                    continue
                score, reasons = self._edge_score(left, right)
                if not self._candidate_pair(left, right, score, reasons):
                    if reasons or score > 0:
                        rejected_weak += 1
                    continue

                candidate_count += 1
                row = {
                    "pair_id": f"{left['incident_id']}::{right['incident_id']}",
                    "source": left["incident_id"],
                    "target": right["incident_id"],
                    "deterministic_score": round(score, 3),
                    "reasons": reasons,
                    "source_summary": self._judge_summary(left),
                    "target_summary": self._judge_summary(right),
                }

                # Strong evidence remains deterministic; grey-zone evidence is
                # handed to the LLM. Dependency direction is strong only when
                # it is paired with valid temporal precedence.
                if score >= 0.80 or (
                    ("explicit_dependency_direction" in reasons or "known_dependency_direction" in reasons)
                    and "temporal_precedence" in reasons
                    and score >= self.min_edge_score
                ) or "strong_error_propagation" in reasons and score >= 0.80:
                    edges.append(self._make_edge(row, validated=True, validation_source="deterministic"))
                elif score >= self.judge_low:
                    ambiguous.append(row)
                else:
                    rejected_weak += 1

        # LLM stage only sees a prefiltered top-K set. Time alone is not enough:
        # require at least two independent evidence dimensions (e.g. temporal +
        # dependency, or temporal + propagation) before a pair can reach the judge.
        prefiltered = [row for row in ambiguous if self._llm_candidate_supported(row)]
        prefiltered = sorted(
            prefiltered,
            key=lambda r: (
                -float(r.get("deterministic_score", 0.0) or 0.0),
                -self._evidence_dimension_count(r.get("reasons") or []),
                -int(r.get("time_delta_ms", 0) or 0),
                str(r.get("pair_id", "")),
            ),
        )[: self.max_llm_candidates]
        decisions = self.judge.decide(prefiltered)
        decision_records: List[Dict[str, Any]] = []
        for row in ambiguous:
            d = decisions.get(row["pair_id"])
            if not d:
                decision_records.append({
                    "pair_id": row["pair_id"],
                    "decision": "no_decision",
                    "confidence": 0.0,
                    "short_reason": "LLM returned no usable decision",
                })
                continue
            confidence = float(d.get("confidence", 0.0) or 0.0)
            decision_records.append({
                "pair_id": row["pair_id"],
                "decision": d.get("decision", "separate"),
                "confidence": round(confidence, 3),
                "short_reason": d.get("short_reason", ""),
                "validation_model": d.get("validation_model", "deepseek-v4-flash-0731"),
            })
            if d.get("decision") == "edge":
                fusion = self._fuse_confidence(row, confidence)
                decision_records[-1]["deterministic_score"] = round(float(row.get("deterministic_score", 0.0) or 0.0), 3)
                decision_records[-1]["fused_confidence"] = round(fusion["final_confidence"], 3)
                decision_records[-1]["fusion_policy"] = fusion["policy"]
                if fusion["accepted"]:
                    edge = self._make_edge(row, validated=True, validation_source="llm_judge")
                    edge["judge_confidence"] = round(confidence, 3)
                    edge["final_confidence"] = round(fusion["final_confidence"], 3)
                    edge["judge_reason"] = d.get("short_reason", "")
                    edge["decision_evidence"] = ["llm_judge_validation", "evidence_fusion"]
                    edge["fusion_components"] = fusion["components"]
                    edges.append(edge)

        # Remove duplicate parallel edges.
        unique: Dict[Tuple[str, str], Dict[str, Any]] = {}
        for e in edges:
            key = (e["source"], e["target"])
            if key not in unique or e["score"] > unique[key]["score"]:
                unique[key] = e
        edges = list(unique.values())

        incoming = {n["incident_id"]: 0 for n in nodes}
        outgoing = {n["incident_id"]: 0 for n in nodes}
        upstream_ids: Dict[str, List[str]] = {n["incident_id"]: [] for n in nodes}
        downstream_ids: Dict[str, List[str]] = {n["incident_id"]: [] for n in nodes}
        for edge in edges:
            src, dst = edge["source"], edge["target"]
            incoming[dst] += 1
            outgoing[src] += 1
            downstream_ids[src].append(dst)
            upstream_ids[dst].append(src)

        root_scores: Dict[str, float] = {}
        roles: Dict[str, str] = {}
        for n in nodes:
            nid = n["incident_id"]
            has_in = incoming[nid] > 0
            has_out = outgoing[nid] > 0
            if not has_in and has_out:
                roles[nid] = "upstream_root_candidate"
            elif has_in and has_out:
                roles[nid] = "intermediate"
            elif has_in and not has_out:
                roles[nid] = "downstream_symptom"
            else:
                roles[nid] = "isolated"

            if edges:
                topology = 0.0
                if not has_in:
                    topology += 0.55
                if has_out:
                    topology += 0.25
                topology += 0.10 * min(1.0, outgoing[nid] / max(1, len(nodes) - 1))
                topology += 0.10 * min(1.0, n["max_risk_score"] / 100.0)
                root_scores[nid] = min(1.0, topology)
            else:
                root_scores[nid] = 0.0

        if edges:
            root_candidates = [
                nid for nid, role in roles.items()
                if role == "upstream_root_candidate"
            ]
            if not root_candidates:
                # Cyclic/all-intermediate graph: rank by topology, but never use
                # this fallback when the graph itself has no edges.
                root_candidates = [
                    nid for nid, _ in sorted(root_scores.items(), key=lambda kv: (-kv[1], kv[0]))[:3]
                ]
        else:
            root_candidates = []

        for node in nodes:
            nid = node["incident_id"]
            node["graph_role"] = roles[nid]
            node["upstream_incidents"] = sorted(upstream_ids[nid])
            node["downstream_incidents"] = sorted(downstream_ids[nid])
            node["root_cause_score"] = round(root_scores[nid], 3)
            node.pop("start_ms", None)
            node.pop("end_ms", None)

        # Confidence remains evidence-derived, but now records evidence diversity.
        # A single evidence dimension is discounted; 2+ independent dimensions
        # keep the original edge score, while 3 dimensions are capped at 1.0.
        for edge in edges:
            evidence = list(edge.get("evidence") or [])
            dimensions = self._evidence_dimensions(evidence)
            independent = len(dimensions & {"temporal", "dependency", "propagation"})
            edge["evidence_dimensions"] = sorted(dimensions)
            edge["independent_evidence_count"] = independent
            diversity_factor = 0.875 if independent <= 1 else 1.0
            edge["evidence_diversity_score"] = round(min(1.0, float(edge.get("score", 0.0) or 0.0) * diversity_factor), 3)
        confidence = sum(float(e.get("evidence_diversity_score", e["score"])) for e in edges) / len(edges) if edges else 0.0
        self.stats = {
            "judge": self.judge.stats,
            "deterministic_edges": sum(1 for e in edges if e.get("validation_source") == "deterministic"),
            "llm_validated_edges": sum(1 for e in edges if e.get("validation_source") == "llm_judge"),
            "ambiguous_candidates": len(ambiguous),
            "llm_prefiltered_candidates": len(prefiltered),
            "llm_prefilter_rejected": max(0, len(ambiguous) - len(prefiltered)),
            "candidate_pairs": candidate_count,
            "weak_candidates_rejected": rejected_weak,
            "judge_decisions": decision_records,
        }
        return {
            "nodes": nodes,
            "edges": edges,
            "root_cause_candidates": root_candidates[:3],
            "root_cause_scores": {n["incident_id"]: round(root_scores[n["incident_id"]], 3) for n in sorted(nodes, key=lambda x: (-root_scores[x["incident_id"]], x["incident_id"]))[:5]},
            "graph_confidence": round(confidence, 3),
            "edge_count": len(edges),
            "node_count": len(nodes),
            "evidence_first": True,
            "root_cause_status": "confirmed_by_graph" if root_candidates else ("unconfirmed" if nodes else "no_incidents"),
            "stats": self.stats,
        }

    def _node(self, incident: Dict[str, Any]) -> Dict[str, Any]:
        events = incident.get("events") or []
        service_values = set()
        inferred_values = set()
        families = set()
        domains = set()
        errors = set()
        exceptions = set()
        topology_dependencies = set()
        topology_upstreams = set()
        topology_downstreams = set()
        for e in events:
            service = e.get("service")
            inferred_service = e.get("inferred_service")
            if service not in (None, "", "unknown"):
                service_values.add(str(service))
            if inferred_service:
                inferred_values.add(str(inferred_service))
            family = e.get("service_family") or e.get("inferred_service_family")
            normalized_family = self._normalize_family(family)
            if normalized_family != "unknown":
                families.add(normalized_family)
            domain = str(e.get("domain") or e.get("inferred_domain") or "unknown").lower()
            if domain != "unknown":
                domains.add(self._normalize_family(domain))
            error = str(e.get("error_family") or "unknown").lower()
            if error != "unknown":
                errors.add(error)
            if e.get("exception_type"):
                exceptions.add(str(e["exception_type"]))
            for key in ("depends_on", "dependencies", "dependency", "upstream_service", "upstream_services"):
                value = e.get(key)
                values = value if isinstance(value, list) else [value]
                for item in values:
                    if item:
                        topology_dependencies.add(self._normalize_family(item))
            for key, target in (("downstream_service", topology_downstreams), ("downstream_services", topology_downstreams)):
                value = e.get(key)
                values = value if isinstance(value, list) else [value]
                for item in values:
                    if item:
                        target.add(self._normalize_family(item))
            for key, target in (("upstream_service", topology_upstreams), ("upstream_services", topology_upstreams)):
                value = e.get(key)
                values = value if isinstance(value, list) else [value]
                for item in values:
                    if item:
                        target.add(self._normalize_family(item))

        # Incident-level metadata can be stronger than event-level metadata.
        for value in incident.get("service_families") or []:
            normalized = self._normalize_family(value)
            if normalized != "unknown":
                families.add(normalized)
        for value in incident.get("inferred_services") or []:
            if value:
                inferred_values.add(str(value))
        for value in incident.get("services") or []:
            if value not in (None, "", "unknown"):
                service_values.add(str(value))
        for key, target in (("topology_dependencies", topology_dependencies), ("topology_upstreams", topology_upstreams), ("topology_downstreams", topology_downstreams)):
            for value in incident.get(key) or []:
                if value:
                    target.add(self._normalize_family(value))

        return {
            "incident_id": incident.get("incident_id"),
            "start_ms": self._time_ms(incident.get("time_range", {}).get("start")),
            "end_ms": self._time_ms(incident.get("time_range", {}).get("end")),
            "event_count": int(incident.get("event_count", len(events))),
            "max_risk_score": int(incident.get("max_risk_score", 0)),
            "services": sorted(service_values),
            "inferred_services": sorted(inferred_values),
            "service_families": sorted(families),
            "domains": sorted(domains),
            "error_families": sorted(errors),
            "exception_types": sorted(exceptions),
            "topology_dependencies": sorted(topology_dependencies),
            "topology_upstreams": sorted(topology_upstreams),
            "topology_downstreams": sorted(topology_downstreams),
            "evidence_ids": list(incident.get("evidence_ids") or []),
        }

    @staticmethod
    def _judge_summary(node: Dict[str, Any]) -> Dict[str, Any]:
        return {
            k: node[k]
            for k in (
                "incident_id", "event_count", "max_risk_score", "services",
                "inferred_services", "service_families", "domains",
                "error_families", "exception_types", "topology_dependencies",
                "topology_upstreams", "topology_downstreams",
            )
        }

    @staticmethod
    def _evidence_dimensions(reasons: List[str]) -> set[str]:
        reasons = set(reasons or [])
        dimensions = set()
        if reasons & {"tight_temporal_precedence", "temporal_precedence"}:
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
        if reasons & {"same_domain", "same_service_family"}:
            dimensions.add("structure")
        return dimensions

    @classmethod
    def _evidence_dimension_count(cls, reasons: List[str]) -> int:
        return len(cls._evidence_dimensions(reasons))

    @classmethod
    def _llm_candidate_supported(cls, row: Dict[str, Any]) -> bool:
        """Keep grey-zone causal pairs only when >=2 independent evidence dimensions exist."""
        dimensions = cls._evidence_dimensions(row.get("reasons") or [])
        return len(dimensions & {"temporal", "dependency", "propagation"}) >= 2

    def _candidate_pair(self, left: Dict[str, Any], right: Dict[str, Any], score: float, reasons: List[str]) -> bool:
        if not reasons and score <= 0:
            return False
        # Do not require same domain/service: real RCA commonly crosses layers
        # (e.g. database -> application).
        candidate_reasons = {
            "explicit_dependency_direction",
            "known_dependency_direction",
            "strong_error_propagation",
            "temporal_precedence",
            "tight_temporal_precedence",
            "timeout_to_retry",
            "http_failure_to_retry",
            "cross_domain_dependency",
            "inferred_topology",
        }
        if candidate_reasons.intersection(reasons):
            return True
        return score >= self.min_edge_score

    def _edge_score(self, left: Dict[str, Any], right: Dict[str, Any]) -> Tuple[float, List[str]]:
        # Incident windows can overlap. A causal dependency only requires the
        # downstream incident to START after the upstream incident starts.
        # Requiring ``right.start >= left.end`` incorrectly rejects common
        # failure propagation patterns where the upstream outage is still open
        # while downstream failures begin.
        start_delta = right["start_ms"] - left["start_ms"]
        if start_delta < 0 or start_delta > self.max_edge_ms:
            return 0.0, []

        overlap_ms = max(0, left["end_ms"] - right["start_ms"])
        temporal = max(0.0, 1.0 - start_delta / max(1, self.max_edge_ms))
        score = 0.20 * temporal
        reasons: List[str] = []
        if start_delta <= 30_000:
            score += 0.10
            reasons.append("tight_temporal_precedence")
        elif start_delta <= 120_000:
            reasons.append("temporal_precedence")
        if overlap_ms > 0:
            reasons.append("overlapping_incident_windows")

        lf = set(left["service_families"]) - {"unknown"}
        rf = set(right["service_families"]) - {"unknown"}
        ld = set(left["domains"]) - {"unknown"}
        rd = set(right["domains"]) - {"unknown"}
        le = set(left["error_families"]) - {"unknown"}
        re = set(right["error_families"]) - {"unknown"}

        dependency_kind = self._dependency_relation(lf, rf, left, right)
        if dependency_kind == "explicit":
            score += 0.55
            reasons.append("explicit_dependency_direction")
        elif dependency_kind == "known":
            score += 0.45
            reasons.append("known_dependency_direction")
            if not (ld & rd):
                score += 0.10
                reasons.append("cross_domain_dependency")
            else:
                reasons.append("inferred_topology")
        elif dependency_kind == "inferred":
            score += 0.32
            reasons.append("inferred_dependency_direction")
            if not (ld & rd):
                score += 0.08
                reasons.append("cross_domain_dependency")

        if "connection" in le and (re & {"http_5xx", "timeout", "application_error", "other"}):
            score += 0.25
            reasons.append("strong_error_propagation")
        if "timeout" in le and "retry" in re:
            score += 0.18
            reasons.append("timeout_to_retry")
        if "http_5xx" in le and "retry" in re:
            score += 0.18
            reasons.append("http_failure_to_retry")
        if "application_error" in le and "retry" in re:
            score += 0.15
            reasons.append("application_error_to_retry")

        if ld & rd and ld:
            score += 0.10
            reasons.append("same_domain")
        if lf & rf:
            score += 0.08
            reasons.append("same_service_family")
        if left["max_risk_score"] >= 65:
            score += 0.03
            reasons.append("high_severity_upstream")

        return min(score, 1.0), sorted(set(reasons))

    def _dependency_relation(
        self, left_families: set[str], right_families: set[str],
        left: Dict[str, Any], right: Dict[str, Any]
    ) -> str:
        """Return known/inferred/none without turning the registry into a rule dump.

        Known pairs remain the high-confidence topology source. Inferred relations
        use generic service-family semantics and error propagation patterns so new
        services can participate without adding one registry entry per service.
        """
        left_down = set(left.get("topology_downstreams", []))
        right_up = set(right.get("topology_upstreams", []))
        if left_down & right_families or right_up & left_families:
            return "explicit"
        left_dep = set(left.get("topology_dependencies", []))
        if left_dep & right_families:
            return "explicit"
        if any((a, b) in self._DEPENDENCY_PAIRS for a in left_families for b in right_families):
            return "known"

        # Generic infrastructure -> application inference. This intentionally
        # stays conservative and requires the upstream to look infrastructural
        # and the downstream to look application-facing.
        infra = {"database", "redis", "cache", "kafka", "queue", "identity", "storage", "dns"}
        app = {"payment", "order", "checkout", "gateway", "notification", "search", "user", "recommendation", "api", "application"}
        if (left_families & infra) and (right_families & app):
            return "inferred"

        # Generic error-propagation inference can identify an application fan-out
        # even when the exact service family is unknown. Do not use time alone.
        le = set(left.get("error_families", [])) - {"unknown"}
        re = set(right.get("error_families", [])) - {"unknown"}
        if (le & {"connection", "timeout", "http_5xx", "application_error"}) and (re & {"timeout", "http_5xx", "application_error", "retry"}):
            if left_families and right_families and left_families.isdisjoint(right_families):
                return "inferred"
        return "none"


    def _fuse_confidence(self, row: Dict[str, Any], llm_confidence: float) -> Dict[str, Any]:
        """Fuse deterministic evidence with the LLM opinion without letting LLM override weak evidence.

        Strong deterministic topology/propagation evidence gets a higher weight. For ordinary
        grey-zone candidates the fusion can lift a borderline LLM decision, but acceptance still
        requires either strong structural evidence or a high-confidence LLM decision.
        """
        deterministic = max(0.0, min(1.0, float(row.get("deterministic_score", 0.0) or 0.0)))
        llm = max(0.0, min(1.0, float(llm_confidence or 0.0)))
        reasons = set(row.get("reasons") or [])
        strong_evidence = {
            "explicit_dependency_direction", "known_dependency_direction",
            "strong_error_propagation", "tight_temporal_precedence",
            "cross_domain_dependency", "overlapping_incident_windows",
        }
        strong_hits = len(strong_evidence.intersection(reasons))
        structure_bonus = min(0.10, strong_hits * 0.02)
        final_conf = min(1.0, (deterministic * 0.55) + (llm * 0.35) + structure_bonus)

        policy = "reject"
        accepted = False
        dimensions = self._evidence_dimensions(row.get("reasons") or [])
        independent = len(dimensions & {"temporal", "dependency", "propagation"})
        # Accept only corroborated LLM edges. The LLM never creates causality
        # alone: it validates a deterministic candidate with at least two
        # independent evidence dimensions. This fixes the previous failure mode
        # where sensible ~0.60 judge decisions were zeroed out by over-strict fusion.
        if deterministic >= 0.50 and llm >= 0.60 and independent >= 2:
            accepted = final_conf >= 0.50
            policy = "corroborated_evidence_fusion" if accepted else "below_final_confidence"
        elif deterministic >= 0.72 and llm >= 0.55 and strong_hits >= 2:
            accepted = final_conf >= 0.55
            policy = "strong_evidence_fusion" if accepted else "below_final_confidence"
        else:
            policy = "insufficient_combined_evidence"

        return {
            "accepted": accepted,
            "final_confidence": final_conf,
            "policy": policy,
            "components": {
                "deterministic_score": deterministic,
                "llm_confidence": llm,
                "strong_evidence_count": strong_hits,
                "structure_bonus": structure_bonus,
            },
        }

    @classmethod
    def _normalize_family(cls, value: Any) -> str:
        v = str(value or "unknown").strip().lower().replace("_", "-")
        if not v:
            return "unknown"
        if v in cls._SERVICE_ALIASES:
            return cls._SERVICE_ALIASES[v]
        for suffix in ("-service", "-api", "-worker", "-client"):
            if v.endswith(suffix):
                v = v[:-len(suffix)]
                break
        if v in {"db", "postgres", "postgresql"}:
            return "database"
        return v

    @staticmethod
    def _time_ms(value: Any) -> int:
        if isinstance(value, str):
            text = value.strip()
            try:
                from datetime import datetime
                parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
                return int(parsed.timestamp() * 1000)
            except (TypeError, ValueError):
                value = text
        try:
            numeric = float(value or 0)
            return int(numeric * 1000 if numeric < 10_000_000_000 else numeric)
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _edge_id(source: str, target: str) -> str:
        return "EDGE-" + hashlib.sha1(f"{source}->{target}".encode()).hexdigest()[:10]

    def _make_edge(self, row: Dict[str, Any], validated: bool, validation_source: str) -> Dict[str, Any]:
        reasons = sorted(set(row.get("reasons", [])))
        evidence = list(reasons)
        if validation_source == "deterministic":
            evidence.append("deterministic_evidence")
        return {
            "edge_id": self._edge_id(row["source"], row["target"]),
            "source": row["source"],
            "target": row["target"],
            "score": round(float(row["deterministic_score"]), 3),
            "reasons": reasons,
            "evidence": sorted(set(evidence)),
            "type": "causal_hypothesis",
            "validated": validated,
            "validation_source": validation_source,
        }
