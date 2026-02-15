"""CRUD unit tests for snapshot operations."""

from pathlib import Path

import pytest

from vibe_carlo.db import get_connection, init_db
from vibe_carlo.schemas import (
    FilingStatus,
    FlatDistribution,
    SimulationInput,
    TruncatedNormalDistribution,
    UniformDistribution,
)
from vibe_carlo.snapshots import (
    create_snapshot,
    delete_snapshot,
    get_snapshot,
    list_snapshots,
    update_snapshot,
)


@pytest.fixture()
def db(tmp_path: Path) -> Path:
    """Create a temporary SQLite database and return its path."""
    db_path = tmp_path / "test.db"
    init_db(db_path)
    return db_path


def _make_params(
    cash: float = 100000,
    market: float = 500000,
    bonds: float = 50000,
    earnings: float = 60000,
    spending: FlatDistribution | UniformDistribution | TruncatedNormalDistribution | None = None,
    years: int = 30,
    sample_years: int | None = None,
    filing_status: FilingStatus | None = None,
) -> SimulationInput:
    dist = spending or FlatDistribution(value=40000)
    return SimulationInput(
        cash_value=cash,
        market_value=market,
        bond_value=bonds,
        earnings=earnings,
        spending_distribution=dist,
        years_to_simulate=years,
        sample_years=sample_years,
        filing_status=filing_status,
    )


# --- Happy path ---


def test_create_and_get_snapshot(db: Path) -> None:
    conn = get_connection(db)
    params = _make_params()
    sid = create_snapshot(conn, "Test", "2025-01-15", params)
    row = get_snapshot(conn, sid)
    conn.close()

    assert row is not None
    assert row["name"] == "Test"
    assert row["snapshot_date"] == "2025-01-15"
    assert row["cash_value"] == 100000
    assert row["market_value"] == 500000
    assert row["bond_value"] == 50000
    assert row["earnings"] == 60000
    assert row["years_to_simulate"] == 30
    assert '"dist_type": "flat"' in str(row["spending_distribution"])


def test_create_snapshot_uniform_distribution(db: Path) -> None:
    conn = get_connection(db)
    dist = UniformDistribution(low=30000, high=60000)
    params = _make_params(spending=dist)
    sid = create_snapshot(conn, None, "2025-02-01", params)
    row = get_snapshot(conn, sid)
    conn.close()

    assert row is not None
    assert '"dist_type": "uniform"' in str(row["spending_distribution"])
    assert '"low": 30000' in str(row["spending_distribution"])
    assert '"high": 60000' in str(row["spending_distribution"])


def test_create_snapshot_truncated_normal(db: Path) -> None:
    conn = get_connection(db)
    dist = TruncatedNormalDistribution(low=20000, high=80000, mean=50000, stddev=10000)
    params = _make_params(spending=dist)
    sid = create_snapshot(conn, None, "2025-03-01", params)
    row = get_snapshot(conn, sid)
    conn.close()

    assert row is not None
    assert '"dist_type": "truncated_normal"' in str(row["spending_distribution"])
    assert '"mean": 50000' in str(row["spending_distribution"])


def test_create_snapshot_with_name(db: Path) -> None:
    conn = get_connection(db)
    params = _make_params()
    sid = create_snapshot(conn, "My Retirement Plan", "2025-06-01", params)
    row = get_snapshot(conn, sid)
    conn.close()

    assert row is not None
    assert row["name"] == "My Retirement Plan"


def test_create_snapshot_without_name(db: Path) -> None:
    conn = get_connection(db)
    params = _make_params()
    sid = create_snapshot(conn, None, "2025-06-01", params)
    row = get_snapshot(conn, sid)
    conn.close()

    assert row is not None
    assert row["name"] is None


def test_list_snapshots_ordered_by_date(db: Path) -> None:
    conn = get_connection(db)
    params = _make_params()
    create_snapshot(conn, "Jan", "2025-01-01", params)
    create_snapshot(conn, "Mar", "2025-03-01", params)
    create_snapshot(conn, "Feb", "2025-02-01", params)
    rows = list_snapshots(conn)
    conn.close()

    assert len(rows) == 3
    assert rows[0]["name"] == "Mar"
    assert rows[1]["name"] == "Feb"
    assert rows[2]["name"] == "Jan"


def test_update_snapshot(db: Path) -> None:
    conn = get_connection(db)
    params = _make_params(cash=100000)
    sid = create_snapshot(conn, "Original", "2025-01-01", params)

    updated_params = _make_params(cash=200000)
    result = update_snapshot(conn, sid, "Updated", "2025-06-01", updated_params)
    row = get_snapshot(conn, sid)
    conn.close()

    assert result is True
    assert row is not None
    assert row["name"] == "Updated"
    assert row["snapshot_date"] == "2025-06-01"
    assert row["cash_value"] == 200000


def test_delete_snapshot(db: Path) -> None:
    conn = get_connection(db)
    params = _make_params()
    sid = create_snapshot(conn, "ToDelete", "2025-01-01", params)
    result = delete_snapshot(conn, sid)
    row = get_snapshot(conn, sid)
    conn.close()

    assert result is True
    assert row is None


# --- Edge cases ---


def test_get_nonexistent_snapshot(db: Path) -> None:
    conn = get_connection(db)
    row = get_snapshot(conn, 999)
    conn.close()
    assert row is None


def test_delete_nonexistent_snapshot(db: Path) -> None:
    conn = get_connection(db)
    result = delete_snapshot(conn, 999)
    conn.close()
    assert result is False


def test_update_nonexistent_snapshot(db: Path) -> None:
    conn = get_connection(db)
    params = _make_params()
    result = update_snapshot(conn, 999, "Ghost", "2025-01-01", params)
    conn.close()
    assert result is False


def test_multiple_snapshots_same_date(db: Path) -> None:
    conn = get_connection(db)
    params = _make_params()
    create_snapshot(conn, "A", "2025-01-01", params)
    create_snapshot(conn, "B", "2025-01-01", params)
    rows = list_snapshots(conn)
    conn.close()

    assert len(rows) == 2
    names = {r["name"] for r in rows}
    assert names == {"A", "B"}


def test_snapshot_with_all_optional_fields_none(db: Path) -> None:
    conn = get_connection(db)
    # sample_years=None gets defaulted to years_to_simulate by SimulationInput validator
    params = _make_params(sample_years=None, filing_status=None)
    sid = create_snapshot(conn, None, "2025-01-01", params)
    row = get_snapshot(conn, sid)
    conn.close()

    assert row is not None
    assert row["name"] is None
    assert row["sample_years"] == 30  # defaults to years_to_simulate
    assert row["filing_status"] is None


def test_snapshot_preserves_filing_status(db: Path) -> None:
    conn = get_connection(db)
    for status in FilingStatus:
        params = _make_params(filing_status=status)
        sid = create_snapshot(conn, None, "2025-01-01", params)
        row = get_snapshot(conn, sid)
        assert row is not None
        assert row["filing_status"] == status.value
    conn.close()
