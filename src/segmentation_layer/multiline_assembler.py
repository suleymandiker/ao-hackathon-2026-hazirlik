# -*- coding: utf-8 -*-
"""Deterministic streaming multiline event assembler."""

from __future__ import annotations

import re
from typing import Iterator, Tuple, Dict, Any


class MultilineAssembler:
    def __init__(self, separator: str = " | "):
        self.separator = separator

    def iter_events(self, file_path: str, regex_pattern: str) -> Iterator[str]:
        for record in self.iter_event_records(file_path, regex_pattern):
            yield record["event"]

    def iter_event_records(self, file_path: str, regex_pattern: str) -> Iterator[Dict[str, Any]]:
        compiled = re.compile(regex_pattern)
        current = []
        first_line_is_header = False
        line_count = 0

        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            for raw_line in f:
                line = raw_line.rstrip("\r\n")
                if not line.strip():
                    # Empty lines are a deterministic secondary boundary.
                    # They do not create empty events.
                    if current:
                        yield {
                            "event": self._join(current),
                            "line_count": line_count,
                            "first_line_is_header": first_line_is_header,
                            "source": "regex" if first_line_is_header else "orphan",
                        }
                        current = []
                        line_count = 0
                        first_line_is_header = False
                    continue

                if compiled.match(line):
                    if current:
                        yield {
                            "event": self._join(current),
                            "line_count": line_count,
                            "first_line_is_header": first_line_is_header,
                            "source": "regex",
                        }
                    current = [line.strip()]
                    line_count = 1
                    first_line_is_header = True
                else:
                    if not current:
                        current = [line.strip()]
                        line_count = 1
                        first_line_is_header = False
                    else:
                        current.append(line.strip())
                        line_count += 1

        if current:
            yield {
                "event": self._join(current),
                "line_count": line_count,
                "first_line_is_header": first_line_is_header,
                "source": "regex" if first_line_is_header else "orphan",
            }

    def _join(self, lines):
        return self.separator.join(part for part in lines if part)
