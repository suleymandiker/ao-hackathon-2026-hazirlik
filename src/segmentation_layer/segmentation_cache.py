# -*- coding: utf-8 -*-
"""Validated multiline-header regex cache.

The cache is intentionally small and JSON based. It stores only learned metadata;
raw logs are never written here.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
import time
from typing import Any, Dict, Optional


CACHE_FORMAT_VERSION = "1"


class SegmentationCache:
    def __init__(self, cache_path: Optional[str] = None):
        base_dir = os.path.dirname(os.path.abspath(__file__))
        self.cache_path = cache_path or os.path.join(base_dir, "segmentation_cache.json")
        self._lock = threading.Lock()
        os.makedirs(os.path.dirname(self.cache_path), exist_ok=True)

    def _load(self) -> Dict[str, Any]:
        try:
            with open(self.cache_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                return {}
            if data.get("__format_version__") not in (None, CACHE_FORMAT_VERSION):
                return {}
            return data
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return {}

    def get(self, fingerprint: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            return self._load().get(fingerprint)

    def put(self, fingerprint: str, value: Dict[str, Any]) -> None:
        with self._lock:
            data = self._load()
            data.setdefault("__format_version__", CACHE_FORMAT_VERSION)
            data[fingerprint] = value
            self._atomic_write(data)

    def remove(self, fingerprint: str) -> None:
        with self._lock:
            data = self._load()
            if fingerprint in data:
                del data[fingerprint]
                self._atomic_write(data)

    def clear(self) -> None:
        with self._lock:
            self._atomic_write({"__format_version__": CACHE_FORMAT_VERSION})

    def _atomic_write(self, data: Dict[str, Any]) -> None:
        directory = os.path.dirname(self.cache_path)
        fd, tmp_path = tempfile.mkstemp(prefix="seg-cache-", suffix=".json", dir=directory, text=True)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            # Windows may briefly lock the destination file (Streamlit reruns,
            # antivirus/indexer, editor, or another process). Cache persistence
            # must never make the pipeline fail, so retry briefly and then skip
            # the write if the file remains locked.
            last_error: Optional[OSError] = None
            for attempt in range(5):
                try:
                    os.replace(tmp_path, self.cache_path)
                    last_error = None
                    break
                except PermissionError as exc:
                    last_error = exc
                    time.sleep(0.10 * (attempt + 1))
                except OSError as exc:
                    last_error = exc
                    break
            if last_error is not None:
                # Cache is an optimization only; a locked cache must not break
                # segmentation or the Streamlit test screen.
                print(
                    f"[CACHE] WARNING | segmentation cache write skipped: "
                    f"{self.cache_path} | {last_error}"
                )
        finally:
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass
