"""SQLite database setup for vibe_carlo snapshots."""

import os
import sqlite3
from pathlib import Path

_CREATE_SNAPSHOTS_TABLE = """\
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

_CREATE_USERS_TABLE = """\
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now'))
);
"""

_CREATE_SESSIONS_TABLE = """\
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TEXT DEFAULT (datetime('now')),
    expires_at TEXT NOT NULL
);
"""


def _migrate_add_user_id(conn: sqlite3.Connection) -> None:
    """Add user_id column to snapshots table if it doesn't exist."""
    columns = [row[1] for row in conn.execute("PRAGMA table_info(snapshots)").fetchall()]
    if "user_id" not in columns:
        conn.execute("ALTER TABLE snapshots ADD COLUMN user_id INTEGER REFERENCES users(id)")
        conn.commit()


def get_db_path() -> Path:
    """Return the path to the SQLite database file.

    Uses VIBE_CARLO_DB env var if set, otherwise ~/.vibe_carlo/snapshots.db.
    """
    env = os.environ.get("VIBE_CARLO_DB")
    if env:
        return Path(env)
    return Path.home() / ".vibe_carlo" / "snapshots.db"


def init_db(db_path: Path | None = None) -> None:
    """Create the database directory and tables if they don't exist."""
    path = db_path or get_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    try:
        conn.execute(_CREATE_SNAPSHOTS_TABLE)
        conn.execute(_CREATE_USERS_TABLE)
        conn.execute(_CREATE_SESSIONS_TABLE)
        _migrate_add_user_id(conn)
        conn.commit()
    finally:
        conn.close()


def get_connection(db_path: Path | None = None) -> sqlite3.Connection:
    """Return a connection with Row factory enabled."""
    path = db_path or get_db_path()
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    return conn
