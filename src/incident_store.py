# -*- coding: utf-8 -*-
"""Small persistent incident store for hackathon-scale streaming runs.

SQLite is intentionally used here because it is part of the Python standard
library, requires no service, and gives us durable storage without adding a
Docker/DB dependency to the demo.
"""
from __future__ import annotations

import json
import os
import sqlite3
from typing import Any, Dict, List, Optional


class SQLiteIncidentStore:
    def __init__(self, path: str = "data/.aiops_incidents.sqlite3") -> None:
        self.path = os.path.abspath(path)
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA synchronous=NORMAL")
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS incidents (
                incident_id TEXT PRIMARY KEY,
                start_ms INTEGER,
                end_ms INTEGER,
                max_risk_score INTEGER,
                event_count INTEGER,
                payload_json TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_incidents_time ON incidents(start_ms, end_ms)")
        self.conn.commit()

    def upsert_many(self, incidents: List[Dict[str, Any]]) -> None:
        if not incidents:
            return
        rows = []
        for incident in incidents:
            tr = incident.get("time_range") or {}
            rows.append(
                (
                    str(incident.get("incident_id")),
                    self._to_int(tr.get("start")),
                    self._to_int(tr.get("end")),
                    int(incident.get("max_risk_score", 0) or 0),
                    int(incident.get("event_count", 0) or 0),
                    json.dumps(incident, ensure_ascii=False, separators=(",", ":")),
                )
            )
        self.conn.executemany(
            """
            INSERT INTO incidents (incident_id, start_ms, end_ms, max_risk_score, event_count, payload_json)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(incident_id) DO UPDATE SET
                start_ms=excluded.start_ms,
                end_ms=excluded.end_ms,
                max_risk_score=excluded.max_risk_score,
                event_count=excluded.event_count,
                payload_json=excluded.payload_json
            """,
            rows,
        )
        self.conn.commit()

    def count(self) -> int:
        return int(self.conn.execute("SELECT COUNT(*) FROM incidents").fetchone()[0])

    def load_all(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        sql = "SELECT payload_json FROM incidents ORDER BY start_ms, end_ms, incident_id"
        params: tuple = ()
        if limit is not None:
            sql += " LIMIT ?"
            params = (int(limit),)
        rows = self.conn.execute(sql, params).fetchall()
        return [json.loads(row[0]) for row in rows]

    def load_recent(self, limit: int = 5000) -> List[Dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT payload_json FROM incidents ORDER BY start_ms DESC, end_ms DESC, incident_id DESC LIMIT ?",
            (int(limit),),
        ).fetchall()
        incidents = [json.loads(row[0]) for row in rows]
        incidents.reverse()
        return incidents

    def clear(self) -> None:
        self.conn.execute("DELETE FROM incidents")
        self.conn.commit()

    def close(self) -> None:
        try:
            self.conn.close()
        except Exception:
            pass

    @staticmethod
    def _to_int(value: Any) -> int:
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return 0

    def __enter__(self) -> "SQLiteIncidentStore":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()
