"""API integration tests for the timeline route."""

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
from vibe_carlo.snapshots import create_snapshot


@pytest.fixture(scope="module")
def _db_path() -> Generator[tuple[Path, int]]:
    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / "test.db"
        init_db(db_path)
        conn = get_connection(db_path)
        user_id = create_user(conn, "test@example.com", "password123")
        conn.close()
        original = app_module._db_path
        app_module._db_path = db_path
        yield db_path, user_id
        app_module._db_path = original


@pytest.fixture(scope="module")
def client(_db_path: tuple[Path, int]) -> Generator[TestClient]:
    db_path, user_id = _db_path
    conn = get_connection(db_path)
    session_id = create_session(conn, user_id)
    conn.close()
    with TestClient(app, cookies={"session_id": session_id}) as c:
        yield c


def _make_params(
    cash: float = 100_000,
    market: float = 500_000,
    bonds: float = 50_000,
) -> SimulationInput:
    return SimulationInput(
        cash_value=cash,
        market_value=market,
        bond_value=bonds,
        earnings=0.0,
        spending_distribution=FlatDistribution(value=0.0),
        years_to_simulate=30,
    )


def test_timeline_page_200(client: TestClient) -> None:
    response = client.get("/timeline")
    assert response.status_code == 200


def test_timeline_empty_state(client: TestClient) -> None:
    # With a fresh empty DB, should show empty-state message
    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / "empty.db"
        init_db(db_path)
        conn = get_connection(db_path)
        user_id = create_user(conn, "empty@test.com", "pass")
        session_id = create_session(conn, user_id)
        conn.close()
        original = app_module._db_path
        app_module._db_path = db_path
        try:
            with TestClient(app, cookies={"session_id": session_id}) as c:
                response = c.get("/timeline")
                assert response.status_code == 200
                assert "No snapshots saved yet" in response.text
        finally:
            app_module._db_path = original


def test_timeline_with_snapshots(client: TestClient, _db_path: tuple[Path, int]) -> None:
    db_path, user_id = _db_path
    conn = get_connection(db_path)
    params = _make_params()
    create_snapshot(conn, user_id, "T1", "2024-01-01", params)
    create_snapshot(conn, user_id, "T2", "2025-01-01", params)
    conn.close()

    response = client.get("/timeline")
    assert response.status_code == 200
    assert "timeline-data" in response.text
    assert "timeline-chart" in response.text


def test_timeline_nav_link_present(client: TestClient) -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "/timeline" in response.text
    assert "Timeline" in response.text
