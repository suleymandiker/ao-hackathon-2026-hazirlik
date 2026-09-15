# -*- coding: utf-8 -*-
import logging
import re
import time
from parser_layer.format_detector.format_detector import FormatDetector
from parser_layer.parsers.json_parser import JsonParser
from parser_layer.parsers.syslog_parser import SyslogParser
from parser_layer.parsers.kv_parser import KVParser
from parser_layer.parsers.structured_text_parser import StructuredTextParser
from parser_layer.parsers.plain_text_parser import PlainTextParser
from parser_layer.canonical_event_builder import CanonicalEventBuilder

logger = logging.getLogger(__name__)


class ParserPipeline:
    def __init__(self):
        self.detector = FormatDetector()
        self.parsers = {
            "json": JsonParser(),
            "syslog": SyslogParser(),
            "kv": KVParser(),
            "structured_text": StructuredTextParser(),
            "plain_text": PlainTextParser(),
        }
        self.builder = CanonicalEventBuilder()

        self._detect_func = self.detector.detect
        self._build_func = self.builder.build
        self._plain_parser_func = self.parsers["plain_text"].parse

    def process(self, event):
        try:
            t0 = time.perf_counter()

            if not event or not event.strip():
                return None

            if event.startswith('{'):
                format_type = "json"
            else:
                format_type = self._detect_func(event)

            t1 = time.perf_counter()
            parser = self.parsers.get(format_type)
            if not parser:
                return None

            fields = parser.parse(event)
            parser_fallback = False

            # FormatDetector intentionally remains conservative, but a malformed
            # or mixed-format block should not become an unparseable event simply
            # because it contains a character such as '|'. PlainTextParser is the
            # safe last resort and keeps the raw event available for later AI layers.
            if not fields and format_type != "plain_text":
                fields = self._plain_parser_func(event)
                parser_fallback = bool(fields)

            t2 = time.perf_counter()
            if not fields:
                return None

            result = self._build_func(fields, event, format_type)
            metadata = result.setdefault("metadata", {})
            metadata["parser_format_detected"] = format_type
            metadata["parser_fallback"] = parser_fallback

            t3 = time.perf_counter()
            total_ms = (t3 - t0) * 1000
            if total_ms > 20:
                d_ms = (t1 - t0) * 1000
                p_ms = (t2 - t1) * 1000
                b_ms = (t3 - t2) * 1000
                logger.warning(
                    f"[STRESS] Toplam: {total_ms:.1f}ms | Detect: {d_ms:.1f}ms | "
                    f"Parse: {p_ms:.1f}ms | Build: {b_ms:.1f}ms | Format: {format_type} | "
                    f"Fallback: {parser_fallback}"
                )

            return result

        except Exception:
            return None
