# -*- coding: utf-8 -*-
"""Deterministic enrichment of canonical events for correlation/LLM context."""
from __future__ import annotations

import re
from typing import Any, Dict

_SERVICE_FIELD_KEYS = ("service", "service_name", "app", "application", "syslog_app_name")
_SERVICE_WORD_RE = re.compile(r"(?i)\b([a-z][a-z0-9_-]{1,40})(?:-api|-service|_api|_service)?\b")
_CLASS_RE = re.compile(r"\b([A-Z][A-Za-z0-9]+(?:Service|Controller|Client|Worker))\b")
_PACKAGE_RE = re.compile(r"\b(?:com|org|io)\.([a-z][a-z0-9_-]{1,30})(?:\.[A-Za-z0-9_]+)+\b")
_PATH_RE = re.compile(r"/api/([a-z][a-z0-9_-]{1,40})\b", re.I)
_EXCEPTION_RE = re.compile(r"\b([A-Za-z][A-Za-z0-9_]*(?:Exception|Error))\b")
_TOKEN_RE = re.compile(r"[a-z][a-z0-9_/-]{2,}", re.I)

class EventContextInferer:
    def enrich(self, event: Dict[str, Any]) -> Dict[str, Any]:
        attrs = dict(event.get("attributes") or {})
        raw = str(event.get("raw") or event.get("message") or "")
        message = str(event.get("message") or "")
        service = self._first(*[event.get(k) for k in _SERVICE_FIELD_KEYS], *[attrs.get(k) for k in _SERVICE_FIELD_KEYS])
        component = None
        component = self._component_from_text(raw)
        if service:
            normalized = self._normalize_service(service)
            event["service"] = normalized
            event["service_family"] = self._service_family(normalized)
        else:
            inferred = self._infer_service(raw, message)
            event["service"] = "unknown"
            event["service_family"] = "unknown"
            if inferred:
                event["inferred_service"] = self._normalize_service(inferred)
                event["inferred_service_family"] = self._service_family(inferred)
        if component:
            event["component"] = component
        framework = self._framework_from_text(raw)
        if framework:
            event["framework"] = framework
        runtime = self._runtime_from_text(raw)
        if runtime:
            event["runtime"] = runtime
        library = self._library_from_text(raw)
        if library:
            event["library"] = library
        exception = self._first_match(_EXCEPTION_RE, raw)
        if exception:
            event["exception_type"] = exception
        event["error_family"] = self._error_family(message or raw)
        event["domain"] = self._domain(message or raw, event.get("service_family"))
        event["correlation_tokens"] = self._correlation_tokens(message or raw)
        return event

    @staticmethod
    def _framework_from_text(text: str) -> str | None:
        low = text.lower()
        if "org.springframework" in low or "springframework" in low:
            return "spring"
        if "django" in low:
            return "django"
        if "flask" in low:
            return "flask"
        if "fastapi" in low or "uvicorn" in low:
            return "fastapi"
        return None

    @staticmethod
    def _runtime_from_text(text: str) -> str | None:
        low = text.lower()
        if "node:internal" in low or "axios" in low:
            return "nodejs"
        if "traceback" in low and (".py" in low or "python" in low):
            return "python"
        if "java.lang." in low or "java:" in low or "org.springframework" in low:
            return "jvm"
        return None

    @staticmethod
    def _library_from_text(text: str) -> str | None:
        low = text.lower()
        if "axios" in low:
            return "axios"
        if "resttemplate" in low or "org.springframework.web.client" in low:
            return "spring-resttemplate"
        return None

    @staticmethod
    def _first(*values: Any) -> str | None:
        for value in values:
            if value is not None and str(value).strip():
                return str(value).strip()
        return None

    @staticmethod
    def _first_match(pattern: re.Pattern[str], text: str) -> str | None:
        m = pattern.search(text)
        return m.group(1) if m else None

    def _infer_service(self, raw: str, message: str) -> str | None:
        # Explicit API route gives the strongest deterministic service signal.
        m = _PATH_RE.search(raw)
        if m:
            return f"{m.group(1).lower()}-api"

        # A Java/Kotlin application class is a component, not automatically a service.
        # Use the domain prefix only when it is meaningful (PaymentService -> payment).
        m = _CLASS_RE.search(raw)
        if m:
            name = m.group(1)
            base = re.sub(r"(?:Service|Controller|Client|Worker)$", "", name, flags=re.I)
            suffix = re.search(r"(Service|Controller|Client|Worker)$", name, re.I)
            if base and base.lower() in {"payment", "order", "identity", "gateway", "checkout", "user", "auth"}:
                return f"{base.lower()}-service" if suffix and suffix.group(1).lower() == "service" else base.lower()

        low = (raw + " " + message).lower()
        # Application/service nouns only. Framework/library names are deliberately excluded.
        for candidate in (
            "payment", "order", "identity", "gateway", "checkout",
            "redis", "scheduler", "worker", "database", "postgres",
        ):
            if re.search(rf"\b{re.escape(candidate)}(?:-api|-service)?\b", low):
                return f"{candidate}-api" if re.search(rf"\b{re.escape(candidate)}-api\b", low) else candidate

        # File paths can provide a component hint, but not a service name.
        return None

    @staticmethod
    def _component_from_text(text: str) -> str | None:
        m = _CLASS_RE.search(text)
        return m.group(1) if m else None

    @staticmethod
    def _normalize_service(value: str) -> str:
        return str(value).strip().lower().replace("_", "-")

    @staticmethod
    def _service_family(value: str) -> str:
        v = str(value).strip().lower().replace("_", "-")
        for suffix in ("-service", "-api", "-worker", "-client"):
            if v.endswith(suffix):
                v = v[:-len(suffix)]
                break
        return v


    @staticmethod
    def _domain(text: str, service_family: Any = None) -> str:
        if service_family and str(service_family).lower() != "unknown":
            return str(service_family).lower()
        low = text.lower()
        domains = (
            "payment", "order", "identity", "gateway", "checkout",
            "database", "redis", "scheduler", "worker", "user",
        )
        for candidate in domains:
            if re.search(rf"\b{re.escape(candidate)}(?:-api|-service)?\b", low):
                return candidate
        return "unknown"

    @staticmethod
    def _error_family(text: str) -> str:
        low = text.lower()
        # More specific families must be checked before the generic
        # application_error bucket.
        if "retry" in low or "retry attempt" in low:
            return "retry"
        if "timeout" in low or "timed out" in low:
            return "timeout"
        if "connection" in low or "econnreset" in low:
            return "connection"
        if "http 5" in low or "http 500" in low:
            return "http_5xx"
        if "not found" in low:
            return "not_found"
        if "nullpointer" in low or "exception" in low or "traceback" in low or "error" in low:
            return "application_error"
        return "other"

    @staticmethod
    def _correlation_tokens(text: str) -> set[str]:
        stop = {"the", "and", "with", "from", "because", "failed", "error", "warn", "info", "request", "process", "attempt"}
        return {t.lower() for t in _TOKEN_RE.findall(text) if t.lower() not in stop}
