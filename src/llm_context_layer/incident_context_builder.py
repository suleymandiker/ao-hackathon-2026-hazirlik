# -*- coding: utf-8 -*-
"""Deterministic correlation with optional LLM judgment for grey-zone pairs."""
from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any, Dict, List, Tuple

from .llm_context_builder import LLMContextBuilder
from .context_inference import EventContextInferer
from .incident_correlation_judge import IncidentCorrelationJudge


class IncidentContextBuilder:
    """Generate incident candidates using evidence-first deterministic grouping.

    Strong matches are merged automatically. Weak matches are kept separate.
    Grey-zone pairs are sent in one compact batch to DeepSeek for a correlation
    judgment, then gated by deterministic safeguards.
    """

    def __init__(self, window_seconds: int = 300, merge_threshold: float = 0.52, judge_low: float = 0.35, judge_high: float = 0.80, judge: Any | None = None, max_representative_events: int = 6, max_evidence_ids: int = 20):
        self.window_ms = window_seconds * 1000
        self.merge_threshold = merge_threshold
        self.judge_low = judge_low
        self.judge_high = judge_high
        self.event_builder = LLMContextBuilder()
        self.inferer = EventContextInferer()
        self.judge = judge if judge is not None else IncidentCorrelationJudge(low=judge_low, high=judge_high)
        self.max_representative_events = max(2, int(max_representative_events))
        self.max_evidence_ids = max(5, int(max_evidence_ids))
        self.last_stats: Dict[str, Any] = {}

    def build(self, events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not events:
            self.last_stats = {"judge": self.judge.stats}
            return []

        enriched_events: List[Tuple[int, Dict[str, Any], Dict[str, Any]]] = []
        for original in events:
            enriched_original = self.inferer.enrich(dict(original))
            compact = self.event_builder.build_event(enriched_original)
            # Preserve streaming aggregation metadata through the compact event
            # representation; the LLM context builder intentionally strips
            # non-LLM fields, but incident cardinality/counters are authoritative.
            for key in (
                "aggregation_count", "aggregation_first_seen", "aggregation_last_seen",
                "aggregation_error_family_counts", "aggregation_severity_counts",
                "aggregation_max_risk_score",
            ):
                if key in original:
                    compact[key] = original[key]
            enriched_events.append((self._event_time_ms(enriched_original.get("event_time")), enriched_original, compact))

        enriched_events.sort(key=lambda x: x[0])
        n = len(enriched_events)
        parent = list(range(n))

        def find(x: int) -> int:
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(a: int, b: int) -> None:
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[rb] = ra

        ambiguous: List[Dict[str, Any]] = []
        pair_scores: Dict[Tuple[int, int], Tuple[float, List[str]]] = {}

        for i in range(n):
            for j in range(i + 1, n):
                if enriched_events[j][0] - enriched_events[i][0] > self.window_ms:
                    break
                score, reasons = self._pair_score(enriched_events[i], enriched_events[j])
                pair_scores[(i, j)] = (score, reasons)
                if score >= self.merge_threshold:
                    # Strong deterministic evidence: merge without LLM.
                    if score >= self.judge_high or self._hard_merge_evidence(reasons):
                        union(i, j)
                    else:
                        ambiguous.append(self._judge_row(i, j, score, reasons, enriched_events))
                elif self.judge_low <= score < self.merge_threshold:
                    ambiguous.append(self._judge_row(i, j, score, reasons, enriched_events))

        decisions = self.judge.decide(ambiguous)
        accepted_merges = 0
        rejected_merges = 0
        for row in ambiguous:
            decision = decisions.get(row["pair_id"])
            if not decision:
                # Preserve the previous deterministic behavior when the judge is unavailable.
                if row["score"] >= self.merge_threshold and self._hard_merge_evidence(row.get("reasons", [])):
                    union(row["i"], row["j"])
                continue
            # LLM never overrides a clearly unsafe merge. Confidence must be high enough.
            if decision["decision"] == "merge" and decision["confidence"] >= 0.70:
                union(row["i"], row["j"])
                accepted_merges += 1
            elif decision["decision"] == "merge":
                rejected_merges += 1

        groups_by_root: Dict[int, List[int]] = {}
        for idx in range(n):
            groups_by_root.setdefault(find(idx), []).append(idx)

        incidents: List[Dict[str, Any]] = []
        for ordinal, indices in enumerate(sorted(groups_by_root.values(), key=lambda g: enriched_events[g[0]][0]), 1):
            rows = [enriched_events[i] for i in indices]
            all_items = [row[2] for row in rows]
            originals = [row[1] for row in rows]
            all_items = self._apply_group_service_attribution(all_items)
            evidence_ids = [str(item.get("event_id")) for item in all_items if item.get("event_id")]
            event_weights = [max(1, int(item.get("aggregation_count", 1) or 1)) for item in all_items]
            scores: List[float] = []
            reasons: List[str] = []
            for left in range(len(rows)):
                for right in range(left + 1, len(rows)):
                    score, rs = self._pair_score(rows[left], rows[right])
                    if score > 0:
                        scores.append(score)
                        reasons.extend(rs)

            representative_items = self._representative_items(rows, self.max_representative_events)
            actual_services = sorted({item.get("service", "unknown") for item in all_items if item.get("service") not in (None, "unknown")})
            inferred_services = sorted({item.get("inferred_service") for item in all_items if item.get("inferred_service")})
            families = sorted({self._effective_family(item) for item in all_items})
            observed_families = sorted({
                str(item.get("service_family")).lower() for item in all_items
                if str(item.get("service_family") or "unknown").lower() != "unknown"
            })
            inferred_families = sorted({
                str(item.get("inferred_service_family")).lower() for item in all_items
                if item.get("inferred_service_family")
            })
            error_family_counts: Dict[str, int] = {}
            severity_counts: Dict[str, int] = {}
            topology_dependencies = set()
            topology_upstreams = set()
            topology_downstreams = set()
            for item in all_items:
                weight = max(1, int(item.get("aggregation_count", 1) or 1))
                ef_counts = item.get("aggregation_error_family_counts") or {}
                sv_counts = item.get("aggregation_severity_counts") or {}
                if ef_counts:
                    for ef, count in ef_counts.items():
                        error_family_counts[str(ef)] = error_family_counts.get(str(ef), 0) + int(count or 0)
                else:
                    ef = str(item.get("error_family") or "unknown")
                    error_family_counts[ef] = error_family_counts.get(ef, 0) + weight
                if sv_counts:
                    for sv, count in sv_counts.items():
                        severity_counts[str(sv).upper()] = severity_counts.get(str(sv).upper(), 0) + int(count or 0)
                else:
                    sv = str(item.get("severity") or "unknown").upper()
                    severity_counts[sv] = severity_counts.get(sv, 0) + weight
                for key in ("depends_on", "dependencies", "dependency", "upstream_service", "upstream_services"):
                    value = item.get(key)
                    values = value if isinstance(value, list) else [value]
                    for dep in values:
                        if dep:
                            topology_dependencies.add(str(dep))
                for key in ("downstream_service", "downstream_services"):
                    value = item.get(key)
                    values = value if isinstance(value, list) else [value]
                    for dep in values:
                        if dep:
                            topology_downstreams.add(str(dep))
                for key in ("upstream_service", "upstream_services"):
                    value = item.get(key)
                    values = value if isinstance(value, list) else [value]
                    for dep in values:
                        if dep:
                            topology_upstreams.add(str(dep))
            incident = {
                "incident_id": self._incident_id(evidence_ids, ordinal),
                "time_range": {"start": all_items[0].get("event_time"), "end": all_items[-1].get("event_time")},
                "services": actual_services or ["unknown"],
                "inferred_services": inferred_services,
                "service_evidence": {
                    "observed": actual_services,
                    "inferred": inferred_services,
                    "observed_families": observed_families,
                    "inferred_families": inferred_families,
                },
                "service_families": families or ["unknown"],
                "event_count": sum(event_weights),
                "max_risk_score": max(int(item.get("aggregation_max_risk_score", item.get("risk_score", 0)) or 0) for item in all_items),
                "error_family_counts": dict(sorted(error_family_counts.items(), key=lambda kv: (-kv[1], kv[0]))),
                "severity_counts": dict(sorted(severity_counts.items(), key=lambda kv: (-kv[1], kv[0]))),
                "topology_dependencies": sorted(topology_dependencies),
                "topology_upstreams": sorted(topology_upstreams),
                "topology_downstreams": sorted(topology_downstreams),
                "events": representative_items,
                "evidence_ids": evidence_ids[: self.max_evidence_ids],
                "evidence_count": len(evidence_ids),
                "aggregated_event_count": sum(event_weights),
                "representative_event_count": len(all_items),
                "correlation": {
                    "temporal": self._temporal_score(rows[0][0], rows[-1][0]) if len(rows) > 1 else 0.0,
                    "explicit_trace": self._explicit_trace_score(originals),
                    "service": round(self._group_service_score(all_items), 3),
                    "semantic": round(self._semantic_score(all_items), 3),
                    "pairwise_max": round(max(scores, default=0.0), 3),
                    "pairwise_mean": round(sum(scores) / len(scores), 3) if scores else 0.0,
                    "evidence": sorted(set(reasons)),
                    "llm_judged_pairs": [d for d in self.judge.last_decisions if self._decision_pair_in_group(d, evidence_ids)],
                    "candidate_only": 1.0,
                },
            }
            incidents.append(incident)

        self.judge.stats["accepted_merges"] = accepted_merges
        self.judge.stats["rejected_merges"] = rejected_merges
        self.last_stats = {
            "ambiguous_pairs": len(ambiguous),
            "judge": self.judge.stats,
            "accepted_merges": accepted_merges,
            "rejected_merges": rejected_merges,
            "judge_decisions": list(self.judge.last_decisions),
            "incident_count": len(incidents),
            "multi_event_incidents": sum(1 for i in incidents if i["event_count"] > 1),
        }
        return incidents

    @staticmethod
    def _hard_merge_evidence(reasons: List[str]) -> bool:
        hard = {"shared_trace_id", "shared_request_id", "shared_correlation_id", "same_component"}
        return any(r in hard for r in reasons)


    def _representative_items(self, rows: List[Tuple[int, Dict[str, Any], Dict[str, Any]]], limit: int) -> List[Dict[str, Any]]:
        """Retain a bounded evidence sample while preserving event_count separately."""
        items = [row[2] for row in rows]
        if len(items) <= limit:
            return items
        ranked: List[Tuple[tuple, Dict[str, Any]]] = []
        selected_ids = set()
        candidates: List[Dict[str, Any]] = []
        # Always retain earliest/latest/highest-risk events.
        ordered_by_time = sorted(items, key=lambda x: self._event_time_ms(x.get("event_time")))
        candidates.extend([ordered_by_time[0], ordered_by_time[-1]])
        candidates.append(max(items, key=lambda x: int(x.get("risk_score", 0) or 0)))
        # First occurrence per error family gives structural diversity.
        seen_families = set()
        for item in ordered_by_time:
            family = str(item.get("error_family") or "unknown")
            if family not in seen_families:
                candidates.append(item)
                seen_families.add(family)
            if len(seen_families) >= limit:
                break
        # Then fill by highest risk / newest evidence.
        candidates.extend(sorted(items, key=lambda x: (-int(x.get("risk_score", 0) or 0), str(x.get("event_id", "")))))
        out: List[Dict[str, Any]] = []
        for item in candidates:
            eid = str(item.get("event_id", ""))
            if eid in selected_ids:
                continue
            selected_ids.add(eid)
            out.append(item)
            if len(out) >= limit:
                break
        return out

    @staticmethod
    def _effective_family(item: Dict[str, Any]) -> str:
        family = str(item.get("service_family") or "unknown").lower()
        if family != "unknown":
            return family
        inferred = str(item.get("inferred_service_family") or "unknown").lower()
        return inferred if inferred != "unknown" else "unknown"

    @staticmethod
    def _apply_group_service_attribution(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        known = [i for i in items if i.get("service") not in (None, "unknown")]
        families = {IncidentContextBuilder._effective_family(i) for i in known if IncidentContextBuilder._effective_family(i) != "unknown"}
        if len(families) != 1:
            return items
        family = next(iter(families))
        service = next((str(i.get("service")) for i in known if i.get("service") not in (None, "unknown")), f"{family}-service")
        for item in items:
            if item.get("service") in (None, "unknown"):
                item_family = IncidentContextBuilder._effective_family(item)
                if item_family == family or item.get("error_family") in {"retry", "timeout", "connection"} or item.get("domain") == family:
                    item["inferred_service"] = service
                    item["inferred_service_family"] = family
                    item["service_attribution"] = "correlation_inferred"
        return items

    @staticmethod
    def _judge_row(i, j, score, reasons, enriched_events):
        l = enriched_events[i][2]
        r = enriched_events[j][2]
        return {
            "pair_id": f"{l.get('event_id')}::{r.get('event_id')}",
            "i": i,
            "j": j,
            "score": score,
            "reasons": reasons,
            "time_delta_ms": abs(enriched_events[j][0] - enriched_events[i][0]),
            "left": {k: l.get(k) for k in ("event_id", "event_time", "severity", "service", "service_family", "inferred_service", "error_family", "domain", "message")},
            "right": {k: r.get(k) for k in ("event_id", "event_time", "severity", "service", "service_family", "inferred_service", "error_family", "domain", "message")},
        }

    @staticmethod
    def _decision_pair_in_group(decision: Dict[str, Any], evidence_ids: List[str]) -> bool:
        pid = str(decision.get("pair_id", ""))
        return any(ev in pid for ev in evidence_ids)

    def _pair_score(self, left, right) -> Tuple[float, List[str]]:
        left_ms, left_original, left_item = left
        right_ms, right_original, right_item = right
        delta = abs(right_ms - left_ms)
        la = left_item.get("attributes") or {}
        ra = right_item.get("attributes") or {}
        has_explicit_id = any(la.get(k) and la.get(k) == ra.get(k) for k in ("trace_id", "request_id", "correlation_id"))
        effective_window = self.window_ms if has_explicit_id else min(self.window_ms, 120_000)
        if delta > effective_window:
            return 0.0, []

        score = 0.20 * self._temporal_score(left_ms, right_ms)
        reasons: List[str] = []
        if self._temporal_score(left_ms, right_ms) > 0.5:
            reasons.append("temporal_proximity")

        for key in ("trace_id", "request_id", "correlation_id"):
            if la.get(key) and la.get(key) == ra.get(key):
                score += 0.60
                reasons.append(f"shared_{key}")
                return min(score, 1.0), reasons

        lf = self._effective_family(left_item)
        rf = self._effective_family(right_item)
        if lf != "unknown" and rf != "unknown" and lf == rf:
            score += 0.30
            reasons.append("same_service_family")

        lc = left_item.get("component")
        rc = right_item.get("component")
        if lc and rc and lc.lower() == rc.lower():
            score += 0.22
            reasons.append("same_component")

        lef = left_item.get("error_family")
        ref = right_item.get("error_family")
        if lef and ref and lef == ref:
            score += 0.15
            reasons.append("same_error_family")

        if {lef, ref} & {"retry"} and ({lef, ref} & {"application_error", "http_5xx", "timeout", "connection"}) and delta <= 120_000:
            score += 0.35
            reasons.append("retry_after_failure")

        lt = set(left_original.get("correlation_tokens") or [])
        rt = set(right_original.get("correlation_tokens") or [])
        overlap = len(lt & rt) / max(1, len(lt | rt))
        if overlap >= 0.18:
            score += 0.18
            reasons.append("semantic_token_overlap")

        if self._domain_overlap(left_item, right_item):
            score += 0.15
            reasons.append("same_domain")

        if lf == "unknown" and rf == "unknown" and not (lt & rt):
            score *= 0.45
        return min(score, 1.0), reasons

    @staticmethod
    def _domain_overlap(left_item: Dict[str, Any], right_item: Dict[str, Any]) -> bool:
        left = str(left_item.get("message", "")).lower()
        right = str(right_item.get("message", "")).lower()
        left_domain = str(left_item.get("domain") or "unknown").lower()
        right_domain = str(right_item.get("domain") or "unknown").lower()
        if left_domain != "unknown" and left_domain == right_domain:
            return True
        domains = ("payment", "order", "identity", "database", "redis", "gateway", "checkout")
        return any(d in left and d in right for d in domains)

    @staticmethod
    def _group_service_score(items: List[Dict[str, Any]]) -> float:
        known = [IncidentContextBuilder._effective_family(i) for i in items if IncidentContextBuilder._effective_family(i) != "unknown"]
        return 1.0 if len(set(known)) == 1 and known else 0.0

    @staticmethod
    def _semantic_score(items: List[Dict[str, Any]]) -> float:
        token_sets = [set(x.get("correlation_tokens") or []) for x in items]
        if len(token_sets) < 2:
            return 0.0
        intersections = []
        for i in range(len(token_sets)):
            for j in range(i + 1, len(token_sets)):
                intersections.append(len(token_sets[i] & token_sets[j]) / max(1, len(token_sets[i] | token_sets[j])))
        return max(intersections, default=0.0)

    def _temporal_score(self, a_ms: int, b_ms: int) -> float:
        delta = abs(b_ms - a_ms)
        return max(0.0, 1.0 - (delta / max(1, self.window_ms)))

    @staticmethod
    def _explicit_trace_score(events: List[Dict[str, Any]]) -> float:
        values = []
        for event in events:
            attrs = event.get("attributes") or {}
            for key in ("trace_id", "request_id", "correlation_id"):
                if attrs.get(key):
                    values.append((key, str(attrs[key])))
        if len(values) < 2:
            return 0.0
        return 1.0 if len(set(values)) < len(values) else 0.0

    @staticmethod
    def _event_time_ms(value: Any) -> int:
        if isinstance(value, str):
            try:
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
                return int(parsed.timestamp() * 1000)
            except ValueError:
                try:
                    value = float(value)
                except ValueError:
                    return 0
        try:
            numeric = float(value or 0)
            return int(numeric * 1000 if numeric < 10_000_000_000 else numeric)
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _incident_id(evidence_ids: List[str], ordinal: int) -> str:
        material = "|".join(evidence_ids) or str(ordinal)
        return "INC-" + hashlib.sha1(material.encode("utf-8")).hexdigest()[:10]
