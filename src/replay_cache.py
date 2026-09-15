# -*- coding: utf-8 -*-
"""Bounded replay cache for deterministic pipeline analyses.

Caches the bounded pipeline result for the same input-file fingerprint and
pipeline configuration so Streamlit reruns do not repeat expensive AI stages.
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import time
import zlib
from typing import Any, Dict, Optional

REPLAY_CACHE_ENABLED = os.getenv("AIOPS_REPLAY_CACHE_ENABLED", "1").lower() in {"1", "true", "yes", "on"}
REPLAY_CACHE_PATH = os.getenv("AIOPS_REPLAY_CACHE_PATH", "data/.aiops_replay_cache.sqlite3")
REPLAY_CACHE_TTL = max(0, int(os.getenv("AIOPS_REPLAY_CACHE_TTL_SECONDS", str(7 * 24 * 3600))))
REPLAY_CACHE_MAX_ENTRIES = max(10, int(os.getenv("AIOPS_REPLAY_CACHE_MAX_ENTRIES", "128")))
REPLAY_SCHEMA = "v1"


def file_fingerprint(path: str) -> str:
    """Cheap stable fingerprint: path-independent file identity + head/tail bytes."""
    p = os.path.abspath(path)
    st = os.stat(p)
    h = hashlib.sha256()
    h.update(str(st.st_size).encode())
    h.update(str(st.st_mtime_ns).encode())
    h.update(str(st.st_ino).encode())
    h.update(str(os.path.basename(p)).encode("utf-8", "ignore"))
    sample = 1024 * 1024
    with open(p, "rb") as f:
        head = f.read(sample)
        h.update(head)
        if st.st_size > sample:
            f.seek(max(0, st.st_size - sample))
            h.update(f.read(sample))
    return h.hexdigest()


def make_key(file_id: str, config: Dict[str, Any]) -> str:
    payload = {"schema": REPLAY_SCHEMA, "file": file_id, "config": config}
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class ReplayCache:
    def __init__(self, path: str = REPLAY_CACHE_PATH):
        self.path = os.path.abspath(path)

    def _ensure(self, conn: sqlite3.Connection) -> None:
        conn.execute("CREATE TABLE IF NOT EXISTS replay_results (cache_key TEXT PRIMARY KEY, created_at REAL NOT NULL, accessed_at REAL NOT NULL, payload BLOB NOT NULL, payload_bytes INTEGER NOT NULL)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_replay_accessed ON replay_results(accessed_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_replay_created ON replay_results(created_at)")

    def get(self, key: str) -> Optional[Dict[str, Any]]:
        if not REPLAY_CACHE_ENABLED:
            return None
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            now = time.time()
            with sqlite3.connect(self.path, timeout=5) as conn:
                self._ensure(conn)
                row = conn.execute("SELECT created_at, payload FROM replay_results WHERE cache_key=?", (key,)).fetchone()
                if not row:
                    return None
                if REPLAY_CACHE_TTL and row[0] < now - REPLAY_CACHE_TTL:
                    conn.execute("DELETE FROM replay_results WHERE cache_key=?", (key,))
                    return None
                conn.execute("UPDATE replay_results SET accessed_at=? WHERE cache_key=?", (now, key))
            return json.loads(zlib.decompress(row[1]).decode("utf-8"))
        except Exception as exc:
            print(f"[REPLAY CACHE] READ WARNING | {exc}")
            return None

    def put(self, key: str, payload: Dict[str, Any]) -> None:
        if not REPLAY_CACHE_ENABLED:
            return
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str).encode("utf-8")
            blob = zlib.compress(raw, level=6)
            now = time.time()
            with sqlite3.connect(self.path, timeout=5) as conn:
                self._ensure(conn)
                conn.execute("INSERT OR REPLACE INTO replay_results(cache_key, created_at, accessed_at, payload, payload_bytes) VALUES(?,?,?,?,?)", (key, now, now, blob, len(blob)))
                self._evict(conn, now)
        except Exception as exc:
            print(f"[REPLAY CACHE] WRITE WARNING | {exc}")

    def _evict(self, conn: sqlite3.Connection, now: float) -> None:
        if REPLAY_CACHE_TTL:
            conn.execute("DELETE FROM replay_results WHERE created_at < ?", (now - REPLAY_CACHE_TTL,))
        count = conn.execute("SELECT COUNT(*) FROM replay_results").fetchone()[0]
        if count > REPLAY_CACHE_MAX_ENTRIES:
            conn.execute("DELETE FROM replay_results WHERE cache_key IN (SELECT cache_key FROM replay_results ORDER BY accessed_at ASC, created_at ASC LIMIT ?)", (count - REPLAY_CACHE_MAX_ENTRIES,))
