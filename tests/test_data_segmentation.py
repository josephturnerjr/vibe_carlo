"""User data isolation tests."""

import tempfile
from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import vibe_carlo.app as app_module
from vibe_carlo.app import app
from vibe_carlo.auth import create_session, create_user
from vibe_carlo.db import get_connection, init_db
from vibe_carlo.schemas import FlatDistribution, SimulationInput
from vibe_carlo.snapshots import create_snapshot, get_snapshot


def _make_params() -> SimulationInput:
    return SimulationInput(
        cash_value=100_000,
        market_value=500_000,
        bond_value=50_000,
        earnings=0.0,
        spending_distribution=FlatDistribution(value=0.0),
        years_to_simulate=30,
    )


@pytest.fixture()
def two_users() -> Generator[tuple[Path, TestClient, int, TestClient, int]]:
    """Create two users with separate authenticated clients.

    Yields (db_path, client_a, user_id_a, client_b, user_id_b).
    """
    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / "test.db"
        init_db(db_path)
        conn = get_connection(db_path)
        uid_a = create_user(conn, "alice@test.com", "pass-a")
        uid_b = create_user(conn, "bob@test.com", "pass-b")
        sid_a = create_session(conn, uid_a)
        sid_b = create_session(conn, uid_b)
        conn.close()

        original = app_module._db_path
        app_module._db_path = db_path
        client_a = TestClient(app, cookies={"session_id": sid_a})
        client_b = TestClient(app, cookies={"session_id": sid_b})
        yield db_path, client_a, uid_a, client_b, uid_b
        app_module._db_path = original


def test_user_a_snapshots_invisible_to_b(
    two_users: tuple[Path, TestClient, int, TestClient, int],
) -> None:
    db_path, client_a, uid_a, client_b, uid_b = two_users
    # Create a snapshot as user A
    conn = get_connection(db_path)
    create_snapshot(conn, uid_a, "Alice Only", "2025-01-01", _make_params())
    conn.close()

    # User B sees empty snapshots list
    response = client_b.get("/snapshots")
    assert response.status_code == 200
    assert "Alice Only" not in response.text


def test_user_b_cannot_load_user_a_snapshot(
    two_users: tuple[Path, TestClient, int, TestClient, int],
) -> None:
    db_path, client_a, uid_a, client_b, uid_b = two_users
    conn = get_connection(db_path)
    sid = create_snapshot(conn, uid_a, "Secret", "2025-01-01", _make_params())
    conn.close()

    response = client_b.get(f"/?snapshot_id={sid}")
    assert response.status_code == 404


def test_user_b_cannot_update_user_a_snapshot(
    two_users: tuple[Path, TestClient, int, TestClient, int],
) -> None:
    db_path, client_a, uid_a, client_b, uid_b = two_users
    conn = get_connection(db_path)
    sid = create_snapshot(conn, uid_a, "Original", "2025-01-01", _make_params())
    conn.close()

    response = client_b.post(
        f"/snapshots/{sid}/update",
        data={
            "snapshot_name": "Hacked",
            "snapshot_date": "2025-06-01",
            "cash_value": "999999",
            "market_value": "500000",
            "bond_value": "50000",
            "earnings": "0",
            "spending_dist_type": "flat",
            "spending_dist_value": "0",
            "years_to_simulate": "30",
        },
    )
    assert response.status_code == 404

    # Verify data unchanged
    conn = get_connection(db_path)
    row = get_snapshot(conn, sid, uid_a)
    conn.close()
    assert row is not None
    assert row["name"] == "Original"


def test_user_b_cannot_delete_user_a_snapshot(
    two_users: tuple[Path, TestClient, int, TestClient, int],
) -> None:
    db_path, client_a, uid_a, client_b, uid_b = two_users
    conn = get_connection(db_path)
    sid = create_snapshot(conn, uid_a, "Protected", "2025-01-01", _make_params())
    conn.close()

    response = client_b.delete(f"/snapshots/{sid}")
    assert response.status_code == 404

    # Verify data still exists
    conn = get_connection(db_path)
    row = get_snapshot(conn, sid, uid_a)
    conn.close()
    assert row is not None


def test_timeline_scoped_to_user(
    two_users: tuple[Path, TestClient, int, TestClient, int],
) -> None:
    db_path, client_a, uid_a, client_b, uid_b = two_users
    conn = get_connection(db_path)
    create_snapshot(conn, uid_a, "A-Point1", "2024-01-01", _make_params())
    create_snapshot(conn, uid_a, "A-Point2", "2025-01-01", _make_params())
    conn.close()

    # User B's timeline should not contain user A's data
    response = client_b.get("/timeline")
    assert response.status_code == 200
    assert "A-Point1" not in response.text


def test_both_users_same_named_snapshots(
    two_users: tuple[Path, TestClient, int, TestClient, int],
) -> None:
    db_path, client_a, uid_a, client_b, uid_b = two_users
    conn = get_connection(db_path)
    sid_a = create_snapshot(conn, uid_a, "Same Name", "2025-01-01", _make_params())
    sid_b = create_snapshot(conn, uid_b, "Same Name", "2025-01-01", _make_params())
    conn.close()

    # Both should succeed (no uniqueness conflict)
    assert sid_a != sid_b

    # Each user sees only their own
    conn = get_connection(db_path)
    row_a = get_snapshot(conn, sid_a, uid_a)
    row_b = get_snapshot(conn, sid_b, uid_b)
    cross = get_snapshot(conn, sid_a, uid_b)
    conn.close()
    assert row_a is not None
    assert row_b is not None
    assert cross is None
