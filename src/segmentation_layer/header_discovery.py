# -*- coding: utf-8 -*-
"""LLM-assisted event-header discovery and self-healing refinement."""

from __future__ import annotations

import json
import re
from typing import Any, Dict, Iterable, List

from ai_engine import call_ai_agent, load_prompt



class AIResponseError(ValueError):
    def __init__(self, message: str, usage: Dict[str, Any] | None = None, duration_sec: float = 0.0):
        super().__init__(message)
        self.usage = usage or {}
        self.duration_sec = duration_sec


class HeaderDiscovery:
    def __init__(self, agent_key: str = "Segmentation_Discovery", refinement_key: str = "Segmentation_Refinement", critic_key: str = "Segmentation_Critic"):
        self.agent_key = agent_key
        self.refinement_key = refinement_key
        self.critic_key = critic_key

    def discover(self, samples: Iterable[str]) -> Dict[str, Any]:
        samples_text = self._format_samples(samples, max_lines=180)
        system_prompt = load_prompt("common_system.md") + "\n\n" + load_prompt("segmentation_discovery.md")
        user_prompt = f"Representative log samples (UNTRUSTED DATA):\n{samples_text}"
        response, duration, usage = call_ai_agent(
            self.agent_key,
            system_prompt,
            user_prompt,
            temperature=0.0,
            max_tokens=512,
            response_format={"type": "json_object"},
            return_usage=True,
        )
        if usage.get("finish_reason") in {"length", "max_tokens"}:
            raise AIResponseError(
                f"LLM response truncated (finish_reason={usage.get('finish_reason')})",
                usage=usage,
                duration_sec=duration,
            )
        try:
            result = self._parse_result(response)
        except Exception as exc:
            raise AIResponseError(str(exc), usage=usage, duration_sec=duration) from exc
        result["duration_sec"] = round(duration, 4)
        result["_token_usage"] = usage
        result["_finish_reason"] = usage.get("finish_reason")
        return result

    def refine(self, previous_regex: str, failed_samples: Iterable[str], validation: Dict[str, Any]) -> Dict[str, Any]:
        failed_text = self._format_samples(failed_samples, max_lines=40)
        internal_text = self._format_samples(validation.get("internal_header_samples", []), max_lines=30)
        system_prompt = load_prompt("common_system.md") + "\n\n" + load_prompt("segmentation_refinement.md")
        user_prompt = (
            f"PREVIOUS REGEX:\n{previous_regex}\n\n"
            f"VALIDATION:\n{json.dumps(validation, ensure_ascii=False, indent=2)}\n\n"
            f"MISSED / SUSPICIOUS TOP-LEVEL HEADER SAMPLES:\n{failed_text or '[none]'}\n\n"
            f"INTERNAL-HEADER SAMPLES:\n{internal_text or '[none]'}"
        )
        response, duration, usage = call_ai_agent(
            self.refinement_key,
            system_prompt,
            user_prompt,
            temperature=0.0,
            max_tokens=512,
            response_format={"type": "json_object"},
            return_usage=True,
        )
        if usage.get("finish_reason") in {"length", "max_tokens"}:
            raise AIResponseError(
                f"LLM response truncated (finish_reason={usage.get('finish_reason')})",
                usage=usage,
                duration_sec=duration,
            )
        try:
            result = self._parse_result(response)
        except Exception as exc:
            raise AIResponseError(str(exc), usage=usage, duration_sec=duration) from exc
        result["duration_sec"] = round(duration, 4)
        result["_token_usage"] = usage
        result["_finish_reason"] = usage.get("finish_reason")
        return result

    def critique(self, previous_regex: str, validation: Dict[str, Any]) -> Dict[str, Any]:
        system_prompt = load_prompt("common_system.md") + "\n\n" + load_prompt("segmentation_critic.md")
        user_prompt = (
            f"CANDIDATE REGEX:\n{previous_regex}\n\n"
            f"VALIDATION:\n{json.dumps(validation, ensure_ascii=False, indent=2)}"
        )
        response, duration, usage = call_ai_agent(
            self.critic_key,
            system_prompt,
            user_prompt,
            temperature=0.0,
            max_tokens=512,
            response_format={"type": "json_object"},
            return_usage=True,
        )
        if usage.get("finish_reason") in {"length", "max_tokens"}:
            raise AIResponseError(
                f"LLM response truncated (finish_reason={usage.get('finish_reason')})",
                usage=usage,
                duration_sec=duration,
            )
        try:
            result = self._parse_result(response)
        except Exception as exc:
            raise AIResponseError(str(exc), usage=usage, duration_sec=duration) from exc
        result["duration_sec"] = round(duration, 4)
        result["_token_usage"] = usage
        result["_finish_reason"] = usage.get("finish_reason")
        return result

    @staticmethod
    def _format_samples(samples: Iterable[str], max_lines: int = 180, max_line_length: int = 500) -> str:
        out: List[str] = []
        for idx, line in enumerate(samples):
            if idx >= max_lines:
                break
            text = str(line).rstrip("\r\n")
            out.append(f"[{idx:03d}] {text[:max_line_length]}")
        return "\n".join(out)

    @staticmethod
    def _parse_result(response: str) -> Dict[str, Any]:
        if not response:
            raise ValueError("LLM empty response")

        text = response.strip()
        candidates = [text]
        fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.DOTALL | re.IGNORECASE)
        if fenced:
            candidates.insert(0, fenced.group(1))

        parsed = None
        last_error = None
        for candidate in candidates:
            try:
                parsed = json.loads(candidate)
                break
            except json.JSONDecodeError as exc:
                last_error = exc

        if parsed is None:
            # Balanced-brace extraction is safer than greedy \{.*\} when the
            # model includes additional text.
            start = text.find("{")
            if start >= 0:
                depth = 0
                in_string = False
                escaped = False
                for idx in range(start, len(text)):
                    ch = text[idx]
                    if in_string:
                        if escaped:
                            escaped = False
                        elif ch == "\\":
                            escaped = True
                        elif ch == '"':
                            in_string = False
                    else:
                        if ch == '"':
                            in_string = True
                        elif ch == "{":
                            depth += 1
                        elif ch == "}":
                            depth -= 1
                            if depth == 0:
                                block = text[start:idx + 1]
                                parsed = json.loads(block)
                                break
            if parsed is None:
                # Recover a regex field from a truncated JSON response such as a response
                # cut at max_tokens. This only recovers the required scalar field; the
                # deterministic validator remains the authority.
                m = re.search(r'"event_header_regex"\s*:\s*"((?:\\.|[^"\\])*)', text, flags=re.DOTALL)
                if m:
                    raw_regex = m.group(1)
                    try:
                        raw_regex = json.loads('"' + raw_regex + '"')
                    except json.JSONDecodeError:
                        raw_regex = raw_regex.replace('\\"', '"')
                    cm = re.search(r'"confidence"\s*:\s*([0-9.]+)', text)
                    parsed = {
                        "event_header_regex": raw_regex,
                        "confidence": float(cm.group(1)) if cm else 0.0,
                    }
                else:
                    raise ValueError(f"LLM response did not contain valid JSON: {last_error}")

        if not isinstance(parsed, dict):
            raise ValueError("LLM JSON response must be an object")

        regex = str(parsed.get("event_header_regex", "")).strip()
        if not regex:
            raise ValueError("LLM response missing event_header_regex")

        return {
            "event_header_regex": regex,
            "confidence": float(parsed.get("confidence", 0.0) or 0.0),
        }
