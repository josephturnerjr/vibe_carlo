"""CRUD operations for simulation snapshots."""

import json
import sqlite3

from vibe_carlo.schemas import SimulationInput, SpendingDistribution


def _serialize_distribution(dist: SpendingDistribution) -> str:
    """Serialize a SpendingDistribution to a JSON string."""
    return json.dumps(dist.model_dump())


def _deserialize_distribution(raw: str) -> SpendingDistribution:
    """Deserialize a JSON string to a SpendingDistribution."""
    from pydantic import TypeAdapter

    adapter: TypeAdapter[SpendingDistribution] = TypeAdapter(SpendingDistribution)
    return adapter.validate_python(json.loads(raw))


def create_snapshot(
    conn: sqlite3.Connection,
    name: str | None,
    snapshot_date: str,
    params: SimulationInput,
) -> int:
    """Insert a new snapshot and return its ID."""
    cur = conn.execute(
        """\
        INSERT INTO snapshots
            (name, snapshot_date, cash_value, market_value, bond_value,
             earnings, spending_distribution, years_to_simulate,
             sample_years, filing_status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            name,
            snapshot_date,
            params.cash_value,
            params.market_value,
            params.bond_value,
            params.earnings,
            _serialize_distribution(params.spending_distribution),
            params.years_to_simulate,
            params.sample_years,
            params.filing_status.value if params.filing_status else None,
        ),
    )
    conn.commit()
    return cur.lastrowid  # type: ignore[return-value]


def get_snapshot(conn: sqlite3.Connection, snapshot_id: int) -> dict[str, object] | None:
    """Fetch a single snapshot by ID, or None if not found."""
    cur = conn.execute("SELECT * FROM snapshots WHERE id = ?", (snapshot_id,))
    row = cur.fetchone()
    if row is None:
        return None
    return dict(row)


def list_snapshots(conn: sqlite3.Connection) -> list[dict[str, object]]:
    """Return all snapshots ordered by snapshot_date descending."""
    cur = conn.execute("SELECT * FROM snapshots ORDER BY snapshot_date DESC, id DESC")
    return [dict(r) for r in cur.fetchall()]


def update_snapshot(
    conn: sqlite3.Connection,
    snapshot_id: int,
    name: str | None,
    snapshot_date: str,
    params: SimulationInput,
) -> bool:
    """Update an existing snapshot. Returns True if the row existed."""
    cur = conn.execute(
        """\
        UPDATE snapshots SET
            name = ?,
            snapshot_date = ?,
            cash_value = ?,
            market_value = ?,
            bond_value = ?,
            earnings = ?,
            spending_distribution = ?,
            years_to_simulate = ?,
            sample_years = ?,
            filing_status = ?,
            updated_at = datetime('now')
        WHERE id = ?
        """,
        (
            name,
            snapshot_date,
            params.cash_value,
            params.market_value,
            params.bond_value,
            params.earnings,
            _serialize_distribution(params.spending_distribution),
            params.years_to_simulate,
            params.sample_years,
            params.filing_status.value if params.filing_status else None,
            snapshot_id,
        ),
    )
    conn.commit()
    return cur.rowcount > 0


def delete_snapshot(conn: sqlite3.Connection, snapshot_id: int) -> bool:
    """Delete a snapshot by ID. Returns True if the row existed."""
    cur = conn.execute("DELETE FROM snapshots WHERE id = ?", (snapshot_id,))
    conn.commit()
    return cur.rowcount > 0
