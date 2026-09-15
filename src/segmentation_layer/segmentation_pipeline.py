# -*- coding: utf-8 -*-
"""AI-assisted, self-healing multiline segmentation pipeline."""

from __future__ import annotations

import hashlib
import os
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, Iterator, List, Optional, Tuple

from parser_layer.parser_pipeline import ParserPipeline
from segmentation_layer.header_discovery import HeaderDiscovery, AIResponseError
from segmentation_layer.multiline_assembler import MultilineAssembler
from segmentation_layer.regex_validator import RegexValidator
from segmentation_layer.segmentation_cache import SegmentationCache


SEGMENTATION_SCHEMA_VERSION = "v38-policy-cache"

DEFAULT_FALLBACK_REGEX = (
    r'^(?:\{'
    r'|<\d{1,3}>'
    r'|\S+\s+\d{4}-\d{2}-\d{2}[T\s]\d{2}:\d{2}:\d{2}(?:[.,]\d{3,6})?'
    r'|\d{4}-\d{2}-\d{2}[T\s]\d{2}:\d{2}:\d{2}'
    r'|\d{2}/\d{2}/\d{4}\s+\d{2}:\d{2}:\d{2}'
    r'|\d{1,3}(?:\.\d{1,3}){3}\s+\S+\s+\S+\s+\['
    r'|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2}\s+\d{2}:\d{2}:\d{2}'
    r'|[IWEF]\d{4}\s+\d{2}:\d{2}:\d{2}'
    r'|(?:INFO|ERROR|WARN|WARNING|DEBUG|TRACE|FATAL|CRITICAL)\s+\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}'
    r'|(?:INFO|ERROR|WARN|WARNING|DEBUG|TRACE|FATAL|CRITICAL)\s*[:|\-]'
    r'|Traceback \(most recent call last\):'
    r')'
)


class StratifiedSampler:
    def __init__(self, num_chunks: int = 10, chunk_size: int = 15):
        self.num_chunks = num_chunks
        self.chunk_size = chunk_size

    def sample(self, file_path: str) -> Tuple[List[str], int]:
        file_size = os.path.getsize(file_path)
        if file_size <= 0:
            return [], 0
        chunks: List[List[str]] = []
        step = max(file_size // self.num_chunks, 1)
        with open(file_path, "rb") as f:
            for i in range(self.num_chunks):
                byte_pos = min(i * step, max(file_size - 1, 0))
                f.seek(byte_pos)
                if byte_pos > 0:
                    f.readline()
                lines: List[str] = []
                for _ in range(self.chunk_size):
                    raw = f.readline()
                    if not raw:
                        break
                    lines.append(raw.decode("utf-8", errors="ignore").rstrip("\r\n"))
                if lines:
                    chunks.append(lines)
        return [line for chunk in chunks for line in chunk], file_size


class SegmentationPipeline:
    def __init__(
        self,
        max_iterations: int = 3,
        discovery_sample_lines: int = 150,
        cache_path: Optional[str] = None,
        enable_ai: bool = True,
        max_refine_calls: int = 2,
        enable_critic: bool = True,
    ):
        self.max_iterations = max(1, max_iterations)
        self.max_refine_calls = max(0, max_refine_calls)
        self.enable_ai = enable_ai
        self.enable_critic = enable_critic
        self.discovery_sample_lines = max(10, discovery_sample_lines)
        self.sampler = StratifiedSampler(
            num_chunks=10,
            chunk_size=max(1, self.discovery_sample_lines // 10),
        )
        self.discovery = HeaderDiscovery()
        self.validator = RegexValidator()
        self.assembler = MultilineAssembler()
        self.cache = SegmentationCache(cache_path)
        self.parser = ParserPipeline()
        self.last_result: Dict[str, Any] = {}

    def prepare(self, file_path: str, force_rediscovery: bool = False) -> Dict[str, Any]:
        samples, file_size = self.sampler.sample(file_path)
        fingerprint = self._fingerprint(
            file_path,
            samples,
            file_size,
            discovery_sample_lines=self.discovery_sample_lines,
            enable_ai=self.enable_ai,
            enable_critic=self.enable_critic,
            max_iterations=self.max_iterations,
            max_refine_calls=self.max_refine_calls,
        )

        if not force_rediscovery:
            cached = self.cache.get(fingerprint)
            if cached and cached.get("verified") and cached.get("regex"):
                result = dict(cached)
                result.update({"cache_hit": True, "fingerprint": fingerprint})
                result["source"] = "cache-verified"
                self.last_result = result
                print(f"[SEGMENTATION] CACHE HIT | model={result.get('model')} | regex verified")
                return result

        token_usage = {"prompt_tokens": 0, "cached_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        usage_by_agent: Dict[str, Dict[str, Any]] = {}
        history: List[Dict[str, Any]] = []
        regex: Optional[str] = None
        confidence = 0.0
        source = "fallback"
        reason = ""
        ai_discovery_calls = 0
        ai_refinement_calls = 0
        ai_critic_calls = 0
        parser_validation_calls = 0
        parser_validation_success = 0

        if self.enable_ai:
            print(f"[SEGMENTATION] AI discovery enabled | model=deepseek-v4-flash-0731 | samples={len(samples)}")
            try:
                ai_discovery_calls += 1
                initial = self.discovery.discover(samples)
                regex = initial["event_header_regex"]
                confidence = initial.get("confidence", 0.0)
                source = "llm-discovery"
                reason = "initial discovery"
                initial_usage = initial.get("_token_usage", {})
                self._merge_usage(token_usage, initial_usage)
                self._merge_agent_usage(usage_by_agent, self.discovery.agent_key, initial_usage)
            except AIResponseError as exc:
                self._merge_usage(token_usage, exc.usage)
                self._merge_agent_usage(usage_by_agent, self.discovery.agent_key, exc.usage)
                reason = f"initial discovery failed: {exc}"
                print(f"[SEGMENTATION] AI discovery FAILED -> deterministic fallback | reason={reason}")
                regex = DEFAULT_FALLBACK_REGEX
        else:
            regex = DEFAULT_FALLBACK_REGEX
            reason = "AI discovery disabled; deterministic fallback used"

        # Candidate loop: validate after every model proposal. The parser is
        # explicitly part of the feedback signal, but never the only signal.
        for iteration in range(1, self.max_iterations + 1):
            validation = self.validator.validate(
                file_path,
                regex,
                parser_fn=self.parser.process,
            )
            parser_validation_calls += validation["parser_validation"]["attempts"]
            parser_validation_success += validation["parser_validation"]["success"]

            entry = {
                "iteration": iteration,
                "regex": regex,
                "coverage_score": validation["coverage_score"],
                "candidate_unmatched_headers": validation["candidate_unmatched_headers"],
                "internal_header_candidates": validation["internal_header_candidates"],
                "parser_success_ratio": validation["parser_validation"]["success_ratio"],
                "event_count": validation["event_count"],
                "accounting_zero_loss": validation["accounting_zero_loss"],
                "accepted": validation["accepted"],
                "phase": "candidate_validation",
                "ai_status": "accepted" if source.startswith("llm-") and validation["accepted"] else ("truncated" if "truncated" in reason.lower() else ("rejected" if source.startswith("llm-") else "n/a")),
            }
            history.append(entry)

            print(
                f"[SEGMENTATION] VALIDATE | iteration={iteration} | "
                f"headers={validation['header_matches']} | events={validation['event_count']} | "
                f"coverage={validation['coverage_score']:.2f}% | "
                f"internal_headers={validation['internal_header_candidates']} | "
                f"parser={validation['parser_validation']['success_ratio']:.2f}% | "
                f"accepted={validation['accepted']}"
            )

            if validation["accepted"]:
                result = self._build_result(
                    fingerprint=fingerprint,
                    file_size=file_size,
                    regex=regex,
                    confidence=confidence,
                    source=source,
                    validation=validation,
                    history=history,
                    token_usage=token_usage,
                    usage_by_agent=usage_by_agent,
                    reason=reason,
                    verified=True,
                    cache_hit=False,
                    ai_discovery_calls=ai_discovery_calls,
                    ai_refinement_calls=ai_refinement_calls,
                    ai_critic_calls=ai_critic_calls,
                )
                self.cache.put(fingerprint, result)
                self.last_result = result
                return result

            if not self.enable_ai or ai_refinement_calls >= self.max_refine_calls:
                break

            if not validation.get("failed_samples") and not validation.get("internal_header_samples"):
                reason = "validation failed but no actionable refinement evidence was produced"
                break

            try:
                ai_refinement_calls += 1
                refined = self.discovery.refine(
                    previous_regex=regex,
                    failed_samples=validation.get("failed_samples", []),
                    validation={
                        "coverage_score": validation["coverage_score"],
                        "all_line_match_ratio": validation["all_line_match_ratio"],
                        "event_count": validation["event_count"],
                        "header_matches": validation["header_matches"],
                        "candidate_unmatched_headers": validation["candidate_unmatched_headers"],
                        "internal_header_candidates": validation["internal_header_candidates"],
                        "internal_header_samples": validation.get("internal_header_samples", []),
                        "parser_validation": validation["parser_validation"],
                        "positive_samples": validation.get("positive_samples", []),
                    },
                )
                refined_usage = refined.get("_token_usage", {})
                self._merge_usage(token_usage, refined_usage)
                self._merge_agent_usage(usage_by_agent, self.discovery.refinement_key, refined_usage)
                new_regex = refined["event_header_regex"]
                if new_regex == regex:
                    reason = "LLM refinement returned the same regex"
                    break
                regex = new_regex
                confidence = refined.get("confidence", confidence)
                source = "llm-self-healing"
                reason = "refined by deterministic validation feedback"
                print(f"[SEGMENTATION] self-healing iteration={iteration} | model=deepseek-v4-flash-0731")
            except AIResponseError as exc:
                self._merge_usage(token_usage, exc.usage)
                self._merge_agent_usage(usage_by_agent, self.discovery.refinement_key, exc.usage)
                reason = f"refinement failed: {exc}"
                print(f"[SEGMENTATION] REFINEMENT FAILED | reason={exc}")
                break

        # DeepSeek failed to produce a verified candidate. Let the larger Qwen
        # model act as an expensive critic/reviewer before falling back.
        final_validation = self.validator.validate(file_path, regex or DEFAULT_FALLBACK_REGEX, parser_fn=self.parser.process)
        if self.enable_ai and self.enable_critic and not final_validation["accepted"]:
            try:
                ai_critic_calls += 1
                critique = self.discovery.critique(regex or DEFAULT_FALLBACK_REGEX, final_validation)
                critique_usage = critique.get("_token_usage", {})
                self._merge_usage(token_usage, critique_usage)
                self._merge_agent_usage(usage_by_agent, self.discovery.critic_key, critique_usage)
                critic_regex = critique["event_header_regex"]
                critic_validation = self.validator.validate(file_path, critic_regex, parser_fn=self.parser.process)
                if critic_validation["accepted"]:
                    result = self._build_result(
                        fingerprint=fingerprint,
                        file_size=file_size,
                        regex=critic_regex,
                        confidence=critique.get("confidence", confidence),
                        source="llm-critic",
                        validation=critic_validation,
                        history=history,
                        token_usage=token_usage,
                        reason="accepted by Qwen critic after DeepSeek self-healing failed",
                        verified=True,
                        cache_hit=False,
                        ai_discovery_calls=ai_discovery_calls,
                        ai_refinement_calls=ai_refinement_calls,
                        ai_critic_calls=ai_critic_calls,
                    )
                    self.cache.put(fingerprint, result)
                    self.last_result = result
                    return result
                print(
                    f"[SEGMENTATION] CRITIC CANDIDATE REJECTED | "
                    f"coverage={critic_validation['coverage_score']:.2f}% | "
                    f"internal_headers={critic_validation['internal_header_candidates']}"
                )
            except AIResponseError as exc:
                self._merge_usage(token_usage, exc.usage)
                self._merge_agent_usage(usage_by_agent, self.discovery.critic_key, exc.usage)
                reason = f"critic failed: {exc}"
                print(f"[SEGMENTATION] CRITIC FAILED | reason={exc}")

        # Safety rule: never use an unverified AI regex. Validate the deterministic
        # fallback and use it only as the safe non-LLM path.
        fallback_validation = self.validator.validate(file_path, DEFAULT_FALLBACK_REGEX, parser_fn=self.parser.process)
        if fallback_validation["accepted"]:
            final_validation = fallback_validation
            regex = DEFAULT_FALLBACK_REGEX
            verified = True
            source = "fallback-validated"
            reason = (reason + " | " if reason else "") + "AI candidate not verified; deterministic fallback selected"
        else:
            # We may still have a useful fallback segmentation for continuity,
            # but we explicitly label it unverified so it cannot be cached.
            final_validation = fallback_validation
            regex = DEFAULT_FALLBACK_REGEX
            verified = False
            source = "fallback-unverified"
            reason = (reason + " | " if reason else "") + "fallback also failed strict validation"

        result = self._build_result(
            fingerprint=fingerprint,
            file_size=file_size,
            regex=regex,
            confidence=0.0,
            source=source,
            validation=final_validation,
            history=history,
            token_usage=token_usage,
            usage_by_agent=usage_by_agent,
            reason=reason,
            verified=verified,
            cache_hit=False,
            ai_discovery_calls=ai_discovery_calls,
            ai_refinement_calls=ai_refinement_calls,
            ai_critic_calls=ai_critic_calls,
        )
        self.last_result = result
        if verified:
            self.cache.put(fingerprint, result)
        return result

    def iter_events(self, file_path: str, force_rediscovery: bool = False) -> Iterator[str]:
        result = self.prepare(file_path, force_rediscovery=force_rediscovery)
        if not result.get("verified"):
            raise RuntimeError(
                "Segmentation verification failed; refusing to use an unverified regex. "
                + str(result.get("reason", "unknown reason"))
            )
        yield from self.assembler.iter_events(file_path, result["regex"])

    def process_file(self, file_path: str, force_rediscovery: bool = False) -> Iterator[str]:
        yield from self.iter_events(file_path, force_rediscovery=force_rediscovery)

    def _build_result(self, **kwargs) -> Dict[str, Any]:
        validation = kwargs.pop("validation")
        history = kwargs.pop("history")
        source = kwargs.get("source", "")
        ai_discovery_calls = kwargs.get("ai_discovery_calls", 0)
        ai_refinement_calls = kwargs.get("ai_refinement_calls", 0)
        ai_critic_calls = kwargs.get("ai_critic_calls", 0)
        return {
            "verified": kwargs.pop("verified"),
            "model": "deepseek-v4-flash-0731" if source.startswith("llm-") and source != "llm-critic" else ("qwen35-122b-a10b-awq" if source == "llm-critic" else "fallback-regex"),
            "cache_hit": kwargs.pop("cache_hit"),
            "fingerprint": kwargs.pop("fingerprint"),
            "file_size_bytes": kwargs.pop("file_size"),
            "regex": kwargs.pop("regex"),
            "confidence": round(float(kwargs.pop("confidence") or 0.0), 4),
            "source": kwargs.pop("source"),
            "reason": kwargs.pop("reason"),
            "coverage_score": validation.get("coverage_score", 0.0),
            "candidate_unmatched_headers": validation.get("candidate_unmatched_headers", 0),
            "internal_header_candidates": validation.get("internal_header_candidates", 0),
            "accounting_zero_loss": validation.get("accounting_zero_loss", False),
            "segmentation_counts": {
                "regex_discovered_boundaries": validation.get("header_matches", 0),
                "orphan_block_boundaries": validation.get("first_line_sources", {}).get("orphan", 0),
                "orphan_reasons": validation.get("orphan_reasons", {}),
                "logical_events": validation.get("event_count", 0),
            },
            "validation": validation,
            "history": history,
            "token_usage": kwargs.pop("token_usage"),
            "token_usage_by_agent": kwargs.pop("usage_by_agent", {}),
            "ai_calls": {
                "discovery": kwargs.pop("ai_discovery_calls", 0),
                "refinement": kwargs.pop("ai_refinement_calls", 0),
                "critic": kwargs.pop("ai_critic_calls", 0),
            },
            "ai_call_total": ai_discovery_calls + ai_refinement_calls + ai_critic_calls,
            "ai_success_calls": sum(1 for h in history if h.get("ai_status") in {"accepted", "success"}),
            "ai_truncated_calls": sum(1 for h in history if h.get("ai_status") == "truncated"),
            "ai_rejected_candidates": sum(1 for h in history if h.get("ai_status") == "rejected"),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

    @staticmethod
    def _merge_agent_usage(target: Dict[str, Dict[str, Any]], agent_key: str, usage: Dict[str, Any]) -> None:
        if not usage:
            return
        current = target.setdefault(agent_key, {
            "calls": 0,
            "prompt_tokens": 0,
            "cached_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "finish_reasons": [],
        })
        current["calls"] += 1
        for key in ("prompt_tokens", "cached_tokens", "completion_tokens", "total_tokens"):
            try:
                current[key] += int(usage.get(key, 0) or 0)
            except (TypeError, ValueError):
                pass
        reason = usage.get("finish_reason")
        if reason:
            current["finish_reasons"].append(reason)

    @staticmethod
    def _fingerprint(
        file_path: str,
        samples: Iterable[str],
        file_size: int,
        *,
        discovery_sample_lines: int,
        enable_ai: bool,
        enable_critic: bool,
        max_iterations: int,
        max_refine_calls: int,
    ) -> str:
        h = hashlib.sha256()
        h.update(SEGMENTATION_SCHEMA_VERSION.encode("utf-8"))
        h.update(b"\npolicy:")
        policy = {
            "discovery_sample_lines": int(discovery_sample_lines),
            "enable_ai": bool(enable_ai),
            "enable_critic": bool(enable_critic),
            "max_iterations": int(max_iterations),
            "max_refine_calls": int(max_refine_calls),
            "fallback_regex": DEFAULT_FALLBACK_REGEX,
            "discovery_model": "deepseek-v4-flash-0731",
            "critic_model": "ai-genai__qwen35-122b-a10b-awq-ai-genai",
        }
        h.update(repr(sorted(policy.items())).encode("utf-8"))
        h.update(b"\nfile:")
        h.update(str(file_size).encode())
        h.update(b"\nname:")
        h.update(os.path.basename(file_path).encode("utf-8", errors="ignore"))
        for line in samples:
            h.update(line[:500].encode("utf-8", errors="ignore"))
            h.update(b"\n")
        return h.hexdigest()[:32]

    @staticmethod
    def _merge_usage(target: Dict[str, int], usage: Dict[str, Any]) -> None:
        for key in target:
            try:
                target[key] += int(usage.get(key, 0) or 0)
            except (TypeError, ValueError):
                pass
