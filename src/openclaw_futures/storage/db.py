"""SQLite database helpers."""
from __future__ import annotations

import sqlite3
from pathlib import Path


SCHEMA = """
CREATE TABLE IF NOT EXISTS trade_ideas (
    idea_id INTEGER PRIMARY KEY,
    created_at TEXT NOT NULL,
    source_room TEXT NOT NULL,
    symbol TEXT NOT NULL,
    setup_type TEXT NOT NULL,
    bias TEXT NOT NULL,
    entry_min REAL NOT NULL,
    entry_max REAL NOT NULL,
    stop REAL NOT NULL,
    target REAL NOT NULL,
    risk_per_contract REAL NOT NULL,
    reward_per_contract REAL NOT NULL,
    rr REAL NOT NULL,
    confidence REAL NOT NULL,
    notes_json TEXT NOT NULL,
    status TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS trade_actions (
    action_id INTEGER PRIMARY KEY,
    idea_id INTEGER NOT NULL,
    acted_at TEXT NOT NULL,
    action_type TEXT NOT NULL,
    contracts INTEGER,
    entry_fill REAL,
    exit_fill REAL,
    pnl_dollars REAL,
    notes TEXT,
    FOREIGN KEY (idea_id) REFERENCES trade_ideas (idea_id)
);

CREATE TABLE IF NOT EXISTS market_bars (
    symbol TEXT NOT NULL,
    interval TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    open REAL NOT NULL,
    high REAL NOT NULL,
    low REAL NOT NULL,
    close REAL NOT NULL,
    volume REAL,
    source TEXT NOT NULL,
    PRIMARY KEY (symbol, interval, timestamp)
);

CREATE TABLE IF NOT EXISTS runtime_state (
    state_key TEXT PRIMARY KEY,
    value_json TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    initialize(connection)
    return connection


def initialize(connection: sqlite3.Connection) -> None:
    connection.executescript(SCHEMA)
    connection.commit()
