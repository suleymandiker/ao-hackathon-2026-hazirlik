# -*- coding: utf-8 -*-
"""Build compact, evidence-oriented payloads for LLM triage/RCA."""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List


class LLMContextBuilder:
    """Project rich canonical events into a compact LLM-facing schema."""

    _CONTAINER_PREFIX = re.compile(r"^\s*(?:stdout|stderr)\s+F\s+", re.I)
    _LEADING_SEVERITY = re.compile(
        r"^\s*(?:TRACE|DEBUG|INFO|NOTICE|WARN|WARNING|ERROR|CRITICAL|ALERT|FATAL|EMERGENCY)\s*[:\-]?\s*",
        re.I,
    )
    _SECRETISH = re.compile(r"(?i)(password|passwd|token|secret|api[_-]?key)=([^\s,;&]+)")

    def __init__(self, max_message_chars: int = 1600, include_attributes: bool = True):
        self.max_message_chars = max_message_chars
        self.include_attributes = include_attributes

    def build_event(self, event: Dict[str, Any]) -> Dict[str, Any]:
        attributes = dict(event.get("attributes") or {})
        service = self._first_nonempty(
            event.get("service"),
            attributes.get("service"),
            attributes.get("service_name"),
            attributes.get("app"),
            attributes.get("application"),
            attributes.get("syslog_app_name"),
        )
        source = self._source_alias(event.get("source"), attributes)

        payload: Dict[str, Any] = {
            "event_id": event.get("event_id"),
            "event_time": self._event_time(event.get("event_time")),
            "severity": str(event.get("severity", "INFO")).upper(),
            "service": service or "unknown",
            "source": source,
            "message": self._clean_message(str(event.get("message") or "")),
        }

        for key in ("service_family", "inferred_service", "inferred_service_family", "component", "framework", "runtime", "library", "exception_type", "error_family", "domain"):
            value = event.get(key)
            if value:
                payload[key] = value

        # Risk is useful as an upstream deterministic signal, not as ground truth.
        if event.get("risk_score") is not None:
            payload["risk_score"] = int(event["risk_score"])

        occurrences = event.get("window_count_1m")
        if occurrences is not None:
            payload["occurrences_1m"] = int(occurrences)

        # Keep only correlation/evidence attributes that can help the LLM.
        if self.include_attributes:
            selected = self._select_attributes(attributes)
            if selected:
                payload["attributes"] = selected

        return payload

    def build_events(self, events: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return [self.build_event(e) for e in events]

    def _select_attributes(self, attributes: Dict[str, Any]) -> Dict[str, Any]:
        keep_keys = {
            "service", "service_name", "app", "application", "host", "hostname",
            "trace_id", "span_id", "request_id", "correlation_id",
            "http_status_code", "response_size_bytes", "syslog_app_name",
        }
        result: Dict[str, Any] = {}
        for key, value in attributes.items():
            if key not in keep_keys:
                continue
            if value is None or value == "":
                continue
            # Never push obvious secrets to the LLM.
            if "password" in key.lower() or "secret" in key.lower() or "token" == key.lower() or "api_key" in key.lower():
                continue
            result[key] = value
        return result

    def _clean_message(self, message: str) -> str:
        message = message.replace("\x00", " ").replace("\r", " ").replace("\n", " | ")
        message = self._CONTAINER_PREFIX.sub("", message)
        message = self._LEADING_SEVERITY.sub("", message)
        message = self._SECRETISH.sub(r"\1=[REDACTED]", message)
        message = re.sub(r"\s+", " ", message).strip()
        return message[: self.max_message_chars]

    @staticmethod
    def _first_nonempty(*values: Any) -> str:
        for value in values:
            if value is not None and str(value).strip():
                return str(value).strip()
        return ""

    @staticmethod
    def _source_alias(source: Any, attributes: Dict[str, Any]) -> str:
        value = str(source or "unknown").lower()
        if "structured" in value:
            if "http_status_code" in attributes:
                return "http"
            return "container_or_application"
        return value

    @staticmethod
    def _event_time(value: Any) -> str | None:
        if value is None:
            return None
        if isinstance(value, str):
            return value
        try:
            numeric = float(value)
            # Existing parser data sometimes carries epoch seconds and sometimes
            # epoch milliseconds. Normalize to an integer millisecond string.
            if numeric < 10_000_000_000:
                numeric *= 1000
            return str(int(numeric))
        except (TypeError, ValueError):
            return str(value)

    @staticmethod
    def _useful_template(template: Any, message: str) -> bool:
        template_text = str(template).strip()
        if not template_text:
            return False
        normalized_template = re.sub(r"[<*][^>*]+[>*]", "", template_text)
        return normalized_template.strip().lower() != message.strip().lower()
