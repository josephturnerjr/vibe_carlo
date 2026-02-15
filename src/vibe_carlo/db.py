"""SQLite database setup for vibe_carlo snapshots."""

import os
import sqlite3
from pathlib import Path

_CREATE_TABLE = """\
CREATE TABLE IF NOT EXISTS snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    snapshot_date TEXT NOT NULL,
    cash_value REAL NOT NULL,
    market_value REAL NOT NULL,
    bond_value REAL NOT NULL,
    earnings REAL NOT NULL DEFAULT 0,
    spending_distribution TEXT NOT NULL,
    years_to_simulate INTEGER NOT NULL,
    sample_years INTEGER,
    filing_status TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);
"""


def get_db_path() -> Path:
    """Return the path to the SQLite database file.

    Uses VIBE_CARLO_DB env var if set, otherwise ~/.vibe_carlo/snapshots.db.
    """
    env = os.environ.get("VIBE_CARLO_DB")
    if env:
        return Path(env)
    return Path.home() / ".vibe_carlo" / "snapshots.db"


def init_db(db_path: Path | None = None) -> None:
    """Create the database directory and table if they don't exist."""
    path = db_path or get_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    try:
        conn.execute(_CREATE_TABLE)
        conn.commit()
    finally:
        conn.close()


def get_connection(db_path: Path | None = None) -> sqlite3.Connection:
    """Return a connection with Row factory enabled."""
    path = db_path or get_db_path()
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    return conn
