"""CRUD operations for plans and plan parameter sets."""

import sqlite3
from typing import Any

from vibe_carlo.schemas import ParamSetSpec, PlanParameterSet, PlanRow
from vibe_carlo.snapshots import deserialize_distribution, serialize_distribution


def create_plan(conn: sqlite3.Connection, user_id: int, name: str) -> int:
    """Insert a new plan and return its ID."""
    cur = conn.execute(
        "INSERT INTO plans (user_id, name) VALUES (?, ?)",
        (user_id, name),
    )
    conn.commit()
    return cur.lastrowid  # type: ignore[return-value]


def get_plan(conn: sqlite3.Connection, plan_id: int, user_id: int) -> PlanRow | None:
    """Fetch a single plan by ID scoped to user, or None if not found."""
    cur = conn.execute(
        "SELECT * FROM plans WHERE id = ? AND user_id = ?",
        (plan_id, user_id),
    )
    row = cur.fetchone()
    if row is None:
        return None
    return PlanRow.model_validate(dict(row))


def list_plans(conn: sqlite3.Connection, user_id: int) -> list[PlanRow]:
    """Return all plans for a user with parameter set counts."""
    cur = conn.execute(
        """\
        SELECT p.*, COUNT(ps.id) as parameter_set_count
        FROM plans p
        LEFT JOIN plan_parameter_sets ps ON ps.plan_id = p.id
        WHERE p.user_id = ?
        GROUP BY p.id
        ORDER BY p.created_at DESC
        """,
        (user_id,),
    )
    return [PlanRow.model_validate(dict(r)) for r in cur.fetchall()]


def update_plan_name(conn: sqlite3.Connection, plan_id: int, user_id: int, name: str) -> bool:
    """Update a plan's name. Returns True if the row existed."""
    cur = conn.execute(
        """\
        UPDATE plans SET name = ?, updated_at = datetime('now')
        WHERE id = ? AND user_id = ?
        """,
        (name, plan_id, user_id),
    )
    conn.commit()
    return cur.rowcount > 0


def delete_plan(conn: sqlite3.Connection, plan_id: int, user_id: int) -> bool:
    """Delete a plan and its parameter sets. Returns True if the row existed."""
    # Verify ownership first
    cur = conn.execute(
        "SELECT id FROM plans WHERE id = ? AND user_id = ?",
        (plan_id, user_id),
    )
    if cur.fetchone() is None:
        return False
    # Delete parameter sets first (PRAGMA foreign_keys not enabled)
    conn.execute(
        "DELETE FROM plan_parameter_sets WHERE plan_id = ?",
        (plan_id,),
    )
    conn.execute("DELETE FROM plans WHERE id = ?", (plan_id,))
    conn.commit()
    return True


# ---------------------------------------------------------------------------
# Parameter set operations
# ---------------------------------------------------------------------------


def _param_set_from_row(row: dict[str, Any]) -> PlanParameterSet:
    """Build a PlanParameterSet from a DB row dict (deserializes spending_distribution)."""
    data = dict(row)
    data["spending_distribution"] = deserialize_distribution(str(data["spending_distribution"]))
    return PlanParameterSet.model_validate(data)


def create_parameter_set(
    conn: sqlite3.Connection,
    plan_id: int,
    user_id: int,
    params: ParamSetSpec,
) -> int | None:
    """Add a parameter set to a plan. Returns ID or None if plan not owned."""
    # Verify plan ownership
    cur = conn.execute(
        "SELECT id FROM plans WHERE id = ? AND user_id = ?",
        (plan_id, user_id),
    )
    if cur.fetchone() is None:
        return None

    # Auto-assign order_position
    cur = conn.execute(
        "SELECT COALESCE(MAX(order_position), -1) + 1 FROM plan_parameter_sets WHERE plan_id = ?",
        (plan_id,),
    )
    next_pos: int = cur.fetchone()[0]

    cur = conn.execute(
        """\
        INSERT INTO plan_parameter_sets
            (plan_id, name, order_position, duration,
             cash_value, market_value, bond_value, earnings,
             spending_distribution, withdrawal_tax_rate)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            plan_id,
            params.name,
            next_pos,
            params.duration,
            params.cash_value,
            params.market_value,
            params.bond_value,
            params.earnings,
            serialize_distribution(params.spending_distribution),
            params.withdrawal_tax_rate,
        ),
    )
    conn.commit()
    return cur.lastrowid


def get_parameter_set(
    conn: sqlite3.Connection, param_set_id: int, user_id: int
) -> PlanParameterSet | None:
    """Fetch a parameter set with ownership check via plan join."""
    cur = conn.execute(
        """\
        SELECT ps.* FROM plan_parameter_sets ps
        JOIN plans p ON ps.plan_id = p.id
        WHERE ps.id = ? AND p.user_id = ?
        """,
        (param_set_id, user_id),
    )
    row = cur.fetchone()
    if row is None:
        return None
    return _param_set_from_row(dict(row))


def list_parameter_sets(
    conn: sqlite3.Connection, plan_id: int, user_id: int
) -> list[PlanParameterSet]:
    """Return all parameter sets for a plan, ordered by position."""
    cur = conn.execute(
        """\
        SELECT ps.* FROM plan_parameter_sets ps
        JOIN plans p ON ps.plan_id = p.id
        WHERE ps.plan_id = ? AND p.user_id = ?
        ORDER BY ps.order_position ASC
        """,
        (plan_id, user_id),
    )
    return [_param_set_from_row(dict(r)) for r in cur.fetchall()]


def update_parameter_set(
    conn: sqlite3.Connection,
    param_set_id: int,
    user_id: int,
    params: ParamSetSpec,
) -> bool:
    """Update a parameter set. Returns True if the row existed and was owned."""
    cur = conn.execute(
        """\
        UPDATE plan_parameter_sets SET
            name = ?, duration = ?,
            cash_value = ?, market_value = ?, bond_value = ?,
            earnings = ?, spending_distribution = ?, withdrawal_tax_rate = ?,
            updated_at = datetime('now')
        WHERE id = ? AND plan_id IN (
            SELECT id FROM plans WHERE user_id = ?
        )
        """,
        (
            params.name,
            params.duration,
            params.cash_value,
            params.market_value,
            params.bond_value,
            params.earnings,
            serialize_distribution(params.spending_distribution),
            params.withdrawal_tax_rate,
            param_set_id,
            user_id,
        ),
    )
    conn.commit()
    return cur.rowcount > 0


def delete_parameter_set(conn: sqlite3.Connection, param_set_id: int, user_id: int) -> bool:
    """Delete a parameter set. Returns True if the row existed and was owned."""
    cur = conn.execute(
        """\
        DELETE FROM plan_parameter_sets
        WHERE id = ? AND plan_id IN (
            SELECT id FROM plans WHERE user_id = ?
        )
        """,
        (param_set_id, user_id),
    )
    conn.commit()
    return cur.rowcount > 0


def move_parameter_set(
    conn: sqlite3.Connection,
    param_set_id: int,
    user_id: int,
    direction: str,
) -> bool:
    """Move a parameter set up or down. Returns True if swap occurred."""
    # Get the current set with ownership check
    cur_set = get_parameter_set(conn, param_set_id, user_id)
    if cur_set is None:
        return False

    plan_id = cur_set.plan_id
    cur_pos = cur_set.order_position

    # Find the adjacent set
    if direction == "up":
        cur = conn.execute(
            """\
            SELECT id, order_position FROM plan_parameter_sets
            WHERE plan_id = ? AND order_position < ?
            ORDER BY order_position DESC LIMIT 1
            """,
            (plan_id, cur_pos),
        )
    elif direction == "down":
        cur = conn.execute(
            """\
            SELECT id, order_position FROM plan_parameter_sets
            WHERE plan_id = ? AND order_position > ?
            ORDER BY order_position ASC LIMIT 1
            """,
            (plan_id, cur_pos),
        )
    else:
        return False

    adjacent = cur.fetchone()
    if adjacent is None:
        return False

    # Swap positions
    adj_id = adjacent["id"]
    adj_pos = adjacent["order_position"]
    conn.execute(
        "UPDATE plan_parameter_sets SET order_position = ? WHERE id = ?",
        (adj_pos, param_set_id),
    )
    conn.execute(
        "UPDATE plan_parameter_sets SET order_position = ? WHERE id = ?",
        (cur_pos, adj_id),
    )
    conn.commit()
    return True
