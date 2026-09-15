# -*- coding: utf-8 -*-
"""End-to-end AIOps pipeline with AI-assisted segmentation and compact LLM context."""

import json
import time
from typing import Any, Dict, List, Optional
from incident_store import SQLiteIncidentStore
from triage_context import estimate_json_tokens, select_triage_incidents

from parser_layer.parser_pipeline import ParserPipeline
from segmentation_layer.segmentation_pipeline import SegmentationPipeline
from signal_processing_layer.drain_manager import DrainManager
from signal_processing_layer.drain_policy_tuner import DrainPolicyTuner
from signal_processing_layer.time_window import TimeWindowManager
from smart_filter_layer.scoring_engine import ScoringEngine
from llm_context_layer.llm_context_builder import LLMContextBuilder
from llm_context_layer.incident_context_builder import IncidentContextBuilder
from llm_context_layer.context_inference import EventContextInferer
from llm_context_layer.causal_graph_builder import CausalGraphBuilder
from llm_context_layer.rca_context_builder import RCAContextBuilder
from llm_context_layer.streaming_incident_state import StreamingIncidentStateStore
from replay_cache import ReplayCache, file_fingerprint, make_key


class AIOpsPipeline:
    def __init__(self, threshold: int = 50):
        print("[SİSTEM] AIOps Boru Hattı (Pipeline) Başlatılıyor...")

        self.segmenter = SegmentationPipeline()
        self.parser = ParserPipeline()
        self.drain_tuner = DrainPolicyTuner()
        self.drain = DrainManager()
        self.time_window = TimeWindowManager(window_seconds=60)
        self.scoring_engine = ScoringEngine(threshold=threshold)
        self.llm_context_builder = LLMContextBuilder()
        self.context_inferer = EventContextInferer()
        self.incident_context_builder = IncidentContextBuilder(window_seconds=300, merge_threshold=0.52)
        self.causal_graph_builder = CausalGraphBuilder(max_edge_seconds=300, min_edge_score=0.35)
        self.rca_context_builder = RCAContextBuilder()
        self.triage_top_k = max(6, int(__import__("os").environ.get("AIOPS_TRIAGE_TOP_K", "18")))
        self.triage_max_tokens = max(2000, int(__import__("os").environ.get("AIOPS_TRIAGE_MAX_INPUT_TOKENS", "12000")))
        self.debug_event_retain_limit = max(100, int(__import__("os").environ.get("AIOPS_DEBUG_EVENT_RETAIN_LIMIT", "5000")))
        self.stream_window_seconds = max(30, int(__import__("os").environ.get("AIOPS_STREAM_WINDOW_SECONDS", "300")))
        self.max_graph_incidents = max(100, int(__import__("os").environ.get("AIOPS_MAX_GRAPH_INCIDENTS", "5000")))
        self.max_active_window_events = max(100, int(__import__("os").environ.get("AIOPS_MAX_ACTIVE_WINDOW_EVENTS", "20000")))
        self.max_stream_incident_states = max(100, int(__import__("os").environ.get("AIOPS_MAX_STREAM_INCIDENT_STATES", "2000")))
        self.stream_representative_events = max(1, int(__import__("os").environ.get("AIOPS_STREAM_REPRESENTATIVE_EVENTS", "3")))
        self.incident_store_path = __import__("os").environ.get("AIOPS_INCIDENT_STORE_PATH", "data/.aiops_incidents.sqlite3")

        self.last_segmentation_result: Dict[str, Any] = {}
        self.last_stats: Dict[str, Any] = {}
        self.last_actionable_events: List[Dict[str, Any]] = []
        self.last_llm_events: List[Dict[str, Any]] = []
        self.last_incident_contexts: List[Dict[str, Any]] = []
        self.last_causal_graph: Dict[str, Any] = {}
        self.last_rca_context: str = "{}"
        self.last_debug_trace: Dict[str, Any] = {}
        self.last_drain_policy: Dict[str, Any] = {}
        self.replay_cache = ReplayCache()

    def iter_raw_events(self, file_path: str):
        """Yield logical events after self-healing multiline segmentation."""
        yield from self.segmenter.iter_events(file_path)

    def build_rca_context(self, triage: Any = None) -> str:
        """Build compact RCA context from stored incidents + causal graph.

        ``triage`` may be the parsed JSON object returned by Agent 1. If it is
        unavailable, all incident candidates are retained.
        """
        return self.rca_context_builder.build(
            self.last_incident_contexts or [],
            self.last_causal_graph or {},
            triage=triage,
        )

    def process_file(self, file_path: str, debug_limit: int = 20):
        """Run the pipeline with windowed incident finalization.

        Raw/log events are processed as a stream. Only the current incident
        window is held in memory; finalized incidents are persisted to SQLite.
        The causal graph then operates on compact incident summaries loaded from
        the store, with a configurable upper bound.
        """
        import os

        debug_limit = max(1, int(debug_limit))
        debug_trace: Dict[str, Any] = {}

        # Full bounded replay cache: identical input + identical pipeline policy
        # restores the prior bounded analysis result and skips expensive AI stages.
        try:
            file_id = file_fingerprint(file_path)
            replay_config = {
                "schema": "pipeline-replay-v1",
                "threshold": int(getattr(self.scoring_engine, "threshold", 50)),
                "stream_window_seconds": self.stream_window_seconds,
                "max_active_window_events": self.max_active_window_events,
                "max_stream_incident_states": self.max_stream_incident_states,
                "stream_representative_events": self.stream_representative_events,
                "triage_top_k": self.triage_top_k,
                "triage_max_tokens": self.triage_max_tokens,
                "drain_tuner_sample_events": getattr(self.drain_tuner, "sample_events", 0),
            }
            replay_key = make_key(file_id, replay_config)
            snapshot = self.replay_cache.get(replay_key)
            if snapshot:
                self.last_segmentation_result = snapshot.get("last_segmentation_result", {})
                self.last_stats = snapshot.get("last_stats", {})
                self.last_actionable_events = snapshot.get("last_actionable_events", [])
                self.last_llm_events = snapshot.get("last_llm_events", [])
                self.last_incident_contexts = snapshot.get("last_incident_contexts", [])
                self.last_causal_graph = snapshot.get("last_causal_graph", {})
                self.last_rca_context = snapshot.get("last_rca_context", "{}")
                self.last_debug_trace = snapshot.get("last_debug_trace", {})
                self.last_drain_policy = snapshot.get("last_drain_policy", {})
                self.last_stats["replay_cache_hit"] = True
                print(f"[REPLAY CACHE] HIT | key={replay_key[:12]} | incidents={len(self.last_incident_contexts)} | causal_edges={self.last_causal_graph.get('edge_count', 0)}")
                return json.dumps(self._select_triage_incidents(self.last_incident_contexts, self.triage_top_k, self.triage_max_tokens), indent=2, ensure_ascii=False)
        except Exception as exc:
            print(f"[REPLAY CACHE] PRECHECK WARNING | {exc}")
            file_id = None
            replay_key = None


        def capture(stage: str, payload: Any) -> None:
            if stage in debug_trace:
                return
            debug_trace[stage] = payload

        stats = {
            "raw_blocks": 0,
            "parsed": 0,
            "signaled": 0,
            "filtered_out": 0,
            "actionable": 0,
            "windows_finalized": 0,
            "max_active_window_events": 0,
            "persisted_incidents": 0,
            "max_active_incident_states": 0,
            "stream_aggregated_events": 0,
            "stream_represented_events": 0,
            "stream_coarsened_events": 0,
            "drain_tuning_calls": 0,
            "drain_tuning_cache_hit": False,
        }

        active_state_store = StreamingIncidentStateStore(
            max_states=self.max_stream_incident_states,
            representative_limit=self.stream_representative_events,
        )
        active_window_start: Optional[int] = None
        active_window_end: Optional[int] = None
        store = SQLiteIncidentStore(self.incident_store_path)
        # Each CLI run starts from a clean incident store by default. Set
        # AIOPS_PRESERVE_INCIDENT_STORE=1 to keep history for inspection.
        if os.environ.get("AIOPS_PRESERVE_INCIDENT_STORE", "0") != "1":
            store.clear()

        # Bounded pre-sample only: AI can tune Drain3 once for a new dataset
        # fingerprint, while the full file continues through the streaming path.
        try:
            drain_sample = []
            for raw_sample in self.iter_raw_events(file_path):
                sample_event = self.parser.process(raw_sample)
                if sample_event and sample_event.get("message"):
                    drain_sample.append(str(sample_event.get("message")))
                if len(drain_sample) >= self.drain_tuner.sample_events:
                    break
            tune_result = self.drain_tuner.tune(drain_sample, dataset_id=os.path.abspath(file_path))
            self.last_drain_policy = tune_result
            tuned_state = "drain3_state_{:02d}_{:03d}.bin".format(
                int(tune_result.get("depth", 4)),
                int(round(float(tune_result.get("sim_th", 0.50)) * 1000)),
            )
            self.drain = DrainManager(
                state_file=tuned_state,
                sim_th=tune_result.get("sim_th", 0.50),
                depth=tune_result.get("depth", 4),
            )
        except Exception as exc:
            self.last_drain_policy = {"enabled": False, "reason": f"tuner_failed: {exc}"}
            self.drain = DrainManager()

        stats["drain_tuning_calls"] = int(self.last_drain_policy.get("calls", 0) or 0)
        stats["drain_tuning_cache_hit"] = bool(self.last_drain_policy.get("cache_hit", False))
        capture("drain_tuning", self.last_drain_policy)

        last_window_events: List[Dict[str, Any]] = []

        def finalize_window() -> None:
            nonlocal active_state_store, active_window_start, active_window_end, last_window_events
            stream_events = active_state_store.to_events()
            if not stream_events:
                return
            incidents = self.incident_context_builder.build(stream_events)
            if "bounded_incident_state" not in debug_trace:
                stream_stats_preview = active_state_store.stats()
                capture("bounded_incident_state", {
                    "stats": stream_stats_preview,
                    "representative_events": stream_events[:debug_limit],
                })
            if "incident_aggregation" not in debug_trace:
                capture("incident_aggregation", {
                    "count": len(incidents),
                    "incidents": incidents[:debug_limit],
                })
            stream_stats = active_state_store.stats()
            stats["stream_aggregated_events"] += stream_stats["aggregated_event_count"]
            stats["stream_represented_events"] += stream_stats["represented_events"]
            stats["stream_coarsened_events"] += stream_stats["coarsened_events"]
            stats["max_active_incident_states"] = max(stats["max_active_incident_states"], stream_stats["max_observed_states"])
            store.upsert_many(incidents)
            stats["windows_finalized"] += 1
            stats["persisted_incidents"] += len(incidents)
            last_window_events = stream_events[-self.debug_event_retain_limit:]
            active_state_store = StreamingIncidentStateStore(
                max_states=self.max_stream_incident_states,
                representative_limit=self.stream_representative_events,
            )
            active_window_start = None
            active_window_end = None

        try:
            for raw_log in self.iter_raw_events(file_path):
                stats["raw_blocks"] += 1
                if "segmentation" not in debug_trace:
                    capture("segmentation", {
                        "sample_count": debug_limit,
                        "events": [],
                    })
                if len(debug_trace["segmentation"]["events"]) < debug_limit:
                    debug_trace["segmentation"]["events"].append(raw_log)
                event = self.parser.process(raw_log)
                if not event:
                    continue
                stats["parsed"] += 1
                if "parser" not in debug_trace:
                    capture("parser", {"events": []})
                if len(debug_trace["parser"]["events"]) < debug_limit:
                    debug_trace["parser"]["events"].append(dict(event))
                event = self.context_inferer.enrich(event)
                if "context" not in debug_trace:
                    capture("context", {"events": []})
                if len(debug_trace["context"]["events"]) < debug_limit:
                    debug_trace["context"]["events"].append(dict(event))

                message = event.get("message", "")
                attributes = event.get("attributes", {})
                pattern_data = self.drain.extract_pattern(message, attributes=attributes)
                t_id = pattern_data["template_id"]
                window_count = self.time_window.add_and_count(t_id, event.get("ingest_time"))

                metadata = event.get("metadata", {})
                now_ms = time.time() * 1000
                metadata.update({
                    "signal_at": now_ms,
                    "latency_signal_ms": round(now_ms - metadata.get("parser_at", now_ms), 4),
                    "entropy": pattern_data["entropy"],
                    "confidence": pattern_data["confidence"],
                })
                event.update({
                    "template_id": t_id,
                    "template": pattern_data["template"],
                    "historical_count": pattern_data["cluster_size"],
                    "window_count_1m": window_count,
                    "metadata": metadata,
                })
                stats["signaled"] += 1
                if "drain_signal" not in debug_trace:
                    capture("drain_signal", {"events": []})
                if len(debug_trace["drain_signal"]["events"]) < debug_limit:
                    debug_trace["drain_signal"]["events"].append({
                        "event_id": event.get("event_id"),
                        "template_id": t_id,
                        "template": pattern_data.get("template"),
                        "cluster_size": pattern_data.get("cluster_size"),
                        "entropy": pattern_data.get("entropy"),
                        "confidence": pattern_data.get("confidence"),
                        "message": str(message)[:300],
                    })

                score_result = self.scoring_engine.calculate_score(event)
                event.update({
                    "risk_score": score_result["total_risk_score"],
                    "score_details": score_result["details"],
                })
                if "smart_filter" not in debug_trace:
                    capture("smart_filter", {"events": []})
                if len(debug_trace["smart_filter"]["events"]) < debug_limit:
                    debug_trace["smart_filter"]["events"].append({
                        "event_id": event.get("event_id"),
                        "severity": event.get("severity"),
                        "risk_score": event.get("risk_score"),
                        "actionable": bool(score_result.get("is_actionable")),
                        "score_details": score_result.get("details", {}),
                        "message": str(event.get("message", ""))[:300],
                    })
                if not score_result["is_actionable"]:
                    stats["filtered_out"] += 1
                    continue
                stats["actionable"] += 1

                ts = self._event_time_ms(event.get("event_time"))
                if active_window_start is None:
                    active_window_start = ts
                    active_window_end = active_window_start + self.stream_window_seconds * 1000
                elif ts > active_window_end or active_state_store.stats()["aggregated_event_count"] >= self.max_active_window_events:
                    finalize_window()
                    active_window_start = ts
                    active_window_end = active_window_start + self.stream_window_seconds * 1000

                active_state_store.add(event)
                state_stats = active_state_store.stats()
                stats["max_active_window_events"] = max(stats["max_active_window_events"], state_stats["represented_events"])
                stats["max_active_incident_states"] = max(stats["max_active_incident_states"], state_stats["active_states"])

            finalize_window()

            all_incidents = store.load_recent(self.max_graph_incidents)
            causal_graph = self.causal_graph_builder.build(all_incidents)
            capture("causal_graph", causal_graph)
            triage_incidents = self._select_triage_incidents(
                all_incidents, self.triage_top_k, self.triage_max_tokens
            )
            capture("triage_selection", {
                "all_incidents": len(all_incidents),
                "selected_incidents": triage_incidents[:debug_limit],
                "estimated_input_tokens": self._estimate_json_tokens(triage_incidents),
            })
            rca_context = self.rca_context_builder.build(all_incidents, causal_graph)
            capture("rca_context", json.loads(rca_context) if rca_context else {})

            self.last_actionable_events = last_window_events
            self.last_llm_events = []
            self.last_incident_contexts = all_incidents
            self.last_causal_graph = causal_graph
            self.last_rca_context = rca_context
            self.last_segmentation_result = self.segmenter.last_result
            self.last_debug_trace = debug_trace
            correlation_stats = getattr(self.incident_context_builder, "last_stats", {}) or {}
            self.last_stats = stats

            self.last_segmentation_result = dict(self.last_segmentation_result or {})
            collapsed = max(0, stats["actionable"] - len(all_incidents))
            grouped_events = sum(1 for inc in all_incidents if int(inc.get("event_count", 0)) > 1)
            max_group_size = max((int(inc.get("event_count", 0)) for inc in all_incidents), default=0)
            self.last_segmentation_result["llm_context"] = {
                "actionable_events": stats["actionable"],
                "incident_candidates": len(all_incidents),
                "events_collapsed_into_incidents": collapsed,
                "groups_with_multiple_events": grouped_events,
                "max_incident_event_count": max_group_size,
                "correlation": correlation_stats,
                "streaming": {
                    "window_seconds": self.stream_window_seconds,
                    "windows_finalized": stats["windows_finalized"],
                    "max_active_window_events": stats["max_active_window_events"],
                    "persisted_incidents": stats["persisted_incidents"],
                    "incident_store": self.incident_store_path,
                    "graph_incident_limit": self.max_graph_incidents,
                    "max_active_window_events": self.max_active_window_events,
                    "bounded_incident_state": {
                        "max_active_states": self.max_stream_incident_states,
                        "representative_events_per_state": self.stream_representative_events,
                        "max_active_states_observed": stats["max_active_incident_states"],
                        "aggregated_events": stats["stream_aggregated_events"],
                        "represented_events": stats["stream_represented_events"],
                        "coarsened_events": stats["stream_coarsened_events"],
                    },
                },
                "causal_graph": {
                    "nodes": causal_graph.get("node_count", 0),
                    "edges": causal_graph.get("edge_count", 0),
                    "edge_records": causal_graph.get("edges", []),
                    "root_cause_candidates": causal_graph.get("root_cause_candidates", []),
                    "root_cause_scores": causal_graph.get("root_cause_scores", {}),
                    "graph_confidence": causal_graph.get("graph_confidence", 0.0),
                    "stats": causal_graph.get("stats", {}),
                },
                "drain3_tuning": self.last_drain_policy,
                "triage_selection": {
                    "all_incidents": len(all_incidents),
                    "sent_to_triage": len(triage_incidents),
                    "top_k": self.triage_top_k,
                    "max_input_tokens": self.triage_max_tokens,
                    "estimated_input_tokens": self._estimate_json_tokens(triage_incidents),
                    "selection_policy": "risk_temporal_service_error_diversity_with_token_budget",
                },
            }

            print("\n📊 BORU HATTI (PIPELINE) ÖZETİ:")
            print(f"  > Logical Event: {stats['raw_blocks']}")
            print(f"  > Parse Edilen: {stats['parsed']}")
            print(f"  > Sinyale Dönüşen (Drain3): {stats['signaled']}")
            print(f"  > Çöpe Atılan (Gürültü): {stats['filtered_out']}")
            print(f"  > Actionable Signal: {stats['actionable']}")
            print(f"  > Incident Candidate: {len(all_incidents)}")
            print(f"  > Events Collapsed into Incidents: {collapsed}")
            print(f"  > Multi-event Incidents: {grouped_events} | Max events/incident: {max_group_size}")
            print(f"  > Streaming Windows Finalized: {stats['windows_finalized']} | Max Active Window Representatives: {stats['max_active_window_events']} | Configured Limit: {self.max_active_window_events}")
            print(f"  > Bounded Incident States: max_active={stats['max_active_incident_states']} | limit={self.max_stream_incident_states} | aggregated={stats['stream_aggregated_events']} | represented={stats['stream_represented_events']} | coarsened={stats['stream_coarsened_events']}")
            print(f"  > Incident Store: {self.incident_store_path} | Persisted Incidents: {stats['persisted_incidents']}")
            causal_stats = causal_graph.get("stats", {}) or {}
            judge_stats = (causal_stats.get("judge") or {})
            print(f"  > Causal Graph Nodes: {causal_graph.get('node_count', 0)}")
            print(f"  > Causal Graph Edges: {causal_graph.get('edge_count', 0)}")
            print(f"  > Causal Deterministic Edges: {causal_stats.get('deterministic_edges', 0)}")
            print(f"  > Causal LLM Validated Edges: {causal_stats.get('llm_validated_edges', 0)}")
            print(f"  > Causal Ambiguous Candidates: {causal_stats.get('ambiguous_candidates', 0)}")
            print(f"  > Causal Judge Calls: {judge_stats.get('calls', 0)} | Success: {judge_stats.get('success', 0)}")
            judge_decisions = causal_stats.get("judge_decisions", []) or []
            print(f"  > Causal Judge Decisions: showing {min(10, len(judge_decisions))}/{len(judge_decisions)} | {judge_decisions[:10]}")
            for edge in (causal_graph.get("edges") or []):
                print(f"  > Causal Edge: {edge.get('source')} -> {edge.get('target')} | score={edge.get('score')} | source={edge.get('validation_source')} | evidence={edge.get('evidence', [])}")
            print(f"  > Root Cause Candidates: {causal_graph.get('root_cause_candidates', [])}")
            print(f"  > Root Cause Status: {causal_graph.get('root_cause_status', 'unconfirmed')}")
            print(f"  > Causal Graph Confidence: {causal_graph.get('graph_confidence', 0.0)}")
            print(f"  > Drain3 Policy: sim_th={self.last_drain_policy.get('sim_th', 0.50)} | depth={self.last_drain_policy.get('depth', 4)} | AI calls={self.last_drain_policy.get('calls', 0)} | cache_hit={self.last_drain_policy.get('cache_hit', False)}")
            print(f"  > Triage Incident Context: {len(triage_incidents)}/{len(all_incidents)}")

            if replay_key:
                self.replay_cache.put(replay_key, {
                    "last_segmentation_result": self.last_segmentation_result,
                    "last_stats": self.last_stats,
                    "last_actionable_events": self.last_actionable_events,
                    "last_llm_events": self.last_llm_events,
                    "last_incident_contexts": self.last_incident_contexts,
                    "last_causal_graph": self.last_causal_graph,
                    "last_rca_context": self.last_rca_context,
                    "last_debug_trace": self.last_debug_trace,
                    "last_drain_policy": self.last_drain_policy,
                })
                print(f"[REPLAY CACHE] STORED | key={replay_key[:12]}")

            return json.dumps(triage_incidents, indent=2, ensure_ascii=False)
        finally:
            store.close()

    @staticmethod
    def _event_time_ms(value: Any) -> int:
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return int(time.time() * 1000)

    @staticmethod
    def _estimate_json_tokens(value: Any) -> int:
        return estimate_json_tokens(value)

    @staticmethod
    def _select_triage_incidents(incidents: List[Dict[str, Any]], top_k: int, max_tokens: int = 12000) -> List[Dict[str, Any]]:
        return select_triage_incidents(incidents, top_k=top_k, max_tokens=max_tokens)
