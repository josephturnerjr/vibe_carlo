"""CRUD operations for asset statements and statement accounts."""

import sqlite3

# ---------------------------------------------------------------------------
# Statement operations
# ---------------------------------------------------------------------------


def create_statement(conn: sqlite3.Connection, user_id: int, statement_date: str) -> int:
    """Insert a new statement and return its ID."""
    cur = conn.execute(
        "INSERT INTO statements (user_id, statement_date) VALUES (?, ?)",
        (user_id, statement_date),
    )
    conn.commit()
    return cur.lastrowid  # type: ignore[return-value]


def get_statement(
    conn: sqlite3.Connection, statement_id: int, user_id: int
) -> dict[str, object] | None:
    """Fetch a single statement by ID scoped to user, or None if not found."""
    cur = conn.execute(
        "SELECT * FROM statements WHERE id = ? AND user_id = ?",
        (statement_id, user_id),
    )
    row = cur.fetchone()
    if row is None:
        return None
    return dict(row)


def list_statements(conn: sqlite3.Connection, user_id: int) -> list[dict[str, object]]:
    """Return all statements for a user with net_worth via LEFT JOIN + SUM."""
    cur = conn.execute(
        """\
        SELECT s.*, COALESCE(SUM(sa.value), 0) as net_worth
        FROM statements s
        LEFT JOIN statement_accounts sa ON sa.statement_id = s.id
        WHERE s.user_id = ?
        GROUP BY s.id
        ORDER BY s.statement_date DESC
        """,
        (user_id,),
    )
    return [dict(r) for r in cur.fetchall()]


def update_statement_date(
    conn: sqlite3.Connection, statement_id: int, user_id: int, statement_date: str
) -> bool:
    """Update a statement's date. Returns True if the row existed."""
    cur = conn.execute(
        """\
        UPDATE statements SET statement_date = ?, updated_at = datetime('now')
        WHERE id = ? AND user_id = ?
        """,
        (statement_date, statement_id, user_id),
    )
    conn.commit()
    return cur.rowcount > 0


def delete_statement(conn: sqlite3.Connection, statement_id: int, user_id: int) -> bool:
    """Delete a statement and its accounts. Returns True if the row existed."""
    cur = conn.execute(
        "SELECT id FROM statements WHERE id = ? AND user_id = ?",
        (statement_id, user_id),
    )
    if cur.fetchone() is None:
        return False
    conn.execute(
        "DELETE FROM statement_accounts WHERE statement_id = ?",
        (statement_id,),
    )
    conn.execute("DELETE FROM statements WHERE id = ?", (statement_id,))
    conn.commit()
    return True


def get_latest_statement(conn: sqlite3.Connection, user_id: int) -> dict[str, object] | None:
    """Return the most recent statement by date, or None."""
    cur = conn.execute(
        """\
        SELECT * FROM statements
        WHERE user_id = ?
        ORDER BY statement_date DESC
        LIMIT 1
        """,
        (user_id,),
    )
    row = cur.fetchone()
    if row is None:
        return None
    return dict(row)


# ---------------------------------------------------------------------------
# Account operations
# ---------------------------------------------------------------------------


def _enforce_sign(account_type: str, value: float) -> float:
    """Enforce value sign: positive for assets, negative for liabilities."""
    if account_type == "asset":
        return abs(value)
    return -abs(value)


def create_account(
    conn: sqlite3.Connection,
    statement_id: int,
    user_id: int,
    *,
    name: str,
    account_type: str,
    value: float,
) -> int | None:
    """Add an account to a statement. Returns ID or None if statement not owned."""
    cur = conn.execute(
        "SELECT id FROM statements WHERE id = ? AND user_id = ?",
        (statement_id, user_id),
    )
    if cur.fetchone() is None:
        return None

    cur = conn.execute(
        "SELECT COALESCE(MAX(order_position), -1) + 1"
        " FROM statement_accounts WHERE statement_id = ?",
        (statement_id,),
    )
    next_pos: int = cur.fetchone()[0]

    stored_value = _enforce_sign(account_type, value)
    cur = conn.execute(
        """\
        INSERT INTO statement_accounts
            (statement_id, name, account_type, value, order_position)
        VALUES (?, ?, ?, ?, ?)
        """,
        (statement_id, name, account_type, stored_value, next_pos),
    )
    conn.commit()
    return cur.lastrowid


def get_account(
    conn: sqlite3.Connection, account_id: int, user_id: int
) -> dict[str, object] | None:
    """Fetch an account with ownership check via statement join."""
    cur = conn.execute(
        """\
        SELECT sa.* FROM statement_accounts sa
        JOIN statements s ON sa.statement_id = s.id
        WHERE sa.id = ? AND s.user_id = ?
        """,
        (account_id, user_id),
    )
    row = cur.fetchone()
    if row is None:
        return None
    return dict(row)


def list_accounts(
    conn: sqlite3.Connection, statement_id: int, user_id: int
) -> list[dict[str, object]]:
    """Return all accounts for a statement, ordered by type (asset first) then position."""
    cur = conn.execute(
        """\
        SELECT sa.* FROM statement_accounts sa
        JOIN statements s ON sa.statement_id = s.id
        WHERE sa.statement_id = ? AND s.user_id = ?
        ORDER BY
            CASE sa.account_type WHEN 'asset' THEN 0 ELSE 1 END,
            sa.order_position ASC
        """,
        (statement_id, user_id),
    )
    return [dict(r) for r in cur.fetchall()]


def update_account(
    conn: sqlite3.Connection,
    account_id: int,
    user_id: int,
    *,
    name: str,
    account_type: str,
    value: float,
) -> bool:
    """Update an account. Returns True if the row existed and was owned."""
    stored_value = _enforce_sign(account_type, value)
    cur = conn.execute(
        """\
        UPDATE statement_accounts SET
            name = ?, account_type = ?, value = ?,
            updated_at = datetime('now')
        WHERE id = ? AND statement_id IN (
            SELECT id FROM statements WHERE user_id = ?
        )
        """,
        (name, account_type, stored_value, account_id, user_id),
    )
    conn.commit()
    return cur.rowcount > 0


def delete_account(conn: sqlite3.Connection, account_id: int, user_id: int) -> bool:
    """Delete an account. Returns True if the row existed and was owned."""
    cur = conn.execute(
        """\
        DELETE FROM statement_accounts
        WHERE id = ? AND statement_id IN (
            SELECT id FROM statements WHERE user_id = ?
        )
        """,
        (account_id, user_id),
    )
    conn.commit()
    return cur.rowcount > 0
