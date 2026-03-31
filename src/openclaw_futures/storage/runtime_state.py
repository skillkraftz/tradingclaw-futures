"""Small JSON-backed runtime state store."""
from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime


def get_state(connection: sqlite3.Connection, key: str) -> dict[str, object] | None:
    row = connection.execute(
        "SELECT value_json FROM runtime_state WHERE state_key = ?",
        (key,),
    ).fetchone()
    if row is None:
        return None
    return json.loads(row["value_json"])


def set_state(connection: sqlite3.Connection, key: str, value: dict[str, object]) -> None:
    connection.execute(
        """
        INSERT INTO runtime_state (state_key, value_json, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT(state_key) DO UPDATE SET
            value_json = excluded.value_json,
            updated_at = excluded.updated_at
        """,
        (key, json.dumps(value), _now()),
    )
    connection.commit()


def _now() -> str:
    return datetime.now(UTC).isoformat()
