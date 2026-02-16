"""Authentication helpers: password hashing, user CRUD, session management."""

import secrets
import sqlite3
from datetime import UTC, datetime, timedelta

import bcrypt
from fastapi import Response


def hash_password(password: str) -> str:
    """Hash a password with bcrypt."""
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    """Check a password against a bcrypt hash."""
    return bcrypt.checkpw(password.encode(), password_hash.encode())


def create_user(conn: sqlite3.Connection, email: str, password: str) -> int:
    """Insert a new user and return their ID."""
    cur = conn.execute(
        "INSERT INTO users (email, password_hash) VALUES (?, ?)",
        (email.lower(), hash_password(password)),
    )
    conn.commit()
    return cur.lastrowid  # type: ignore[return-value]


def get_user_by_email(conn: sqlite3.Connection, email: str) -> dict[str, object] | None:
    """Fetch a user by email (case-insensitive), or None if not found."""
    cur = conn.execute("SELECT * FROM users WHERE email = ?", (email.lower(),))
    row = cur.fetchone()
    return dict(row) if row else None


def delete_user(conn: sqlite3.Connection, email: str) -> bool:
    """Delete a user by email. Returns True if the user existed."""
    cur = conn.execute("DELETE FROM users WHERE email = ?", (email.lower(),))
    conn.commit()
    return cur.rowcount > 0


def update_password(conn: sqlite3.Connection, email: str, new_password: str) -> bool:
    """Change a user's password. Returns True if the user existed."""
    cur = conn.execute(
        "UPDATE users SET password_hash = ? WHERE email = ?",
        (hash_password(new_password), email.lower()),
    )
    conn.commit()
    return cur.rowcount > 0


def list_users(conn: sqlite3.Connection) -> list[dict[str, object]]:
    """Return all users."""
    cur = conn.execute("SELECT id, email, created_at FROM users ORDER BY id")
    return [dict(r) for r in cur.fetchall()]


def create_session(conn: sqlite3.Connection, user_id: int) -> str:
    """Create a new session for a user and return the session token."""
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(UTC) + timedelta(days=30)
    conn.execute(
        "INSERT INTO sessions (id, user_id, expires_at) VALUES (?, ?, ?)",
        (token, user_id, expires_at.strftime("%Y-%m-%d %H:%M:%S")),
    )
    conn.commit()
    return token


def validate_session(conn: sqlite3.Connection, session_id: str) -> tuple[int, str] | None:
    """Validate a session token. Returns (user_id, email) if valid, None otherwise."""
    cur = conn.execute(
        """\
        SELECT u.id, u.email FROM sessions s
        JOIN users u ON u.id = s.user_id
        WHERE s.id = ? AND s.expires_at > datetime('now')
        """,
        (session_id,),
    )
    row = cur.fetchone()
    if row is None:
        return None
    return (int(row[0]), str(row[1]))


def delete_session(conn: sqlite3.Connection, session_id: str) -> None:
    """Delete a session by token."""
    conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
    conn.commit()


def set_session_cookie(response: Response, session_id: str, *, secure: bool = False) -> None:
    """Set the session cookie on a response."""
    response.set_cookie(
        key="session_id",
        value=session_id,
        httponly=True,
        samesite="lax",
        secure=secure,
        max_age=30 * 24 * 60 * 60,  # 30 days
    )


def clear_session_cookie(response: Response) -> None:
    """Clear the session cookie on a response."""
    response.delete_cookie(key="session_id")
