"""API integration tests for snapshot routes."""

import tempfile
from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import vibe_carlo.app as app_module
from vibe_carlo.app import app
from vibe_carlo.db import get_connection, init_db


@pytest.fixture(scope="module")
def _db_path() -> Generator[Path]:
    """Set up a temp DB for the module and patch app._db_path."""
    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / "test.db"
        init_db(db_path)
        original = app_module._db_path
        app_module._db_path = db_path
        yield db_path
        app_module._db_path = original


@pytest.fixture(scope="module")
def client(_db_path: Path) -> Generator[TestClient]:
    with TestClient(app) as c:
        yield c


def _snapshot_form_data(
    name: str = "",
    date: str = "2025-06-15",
    cash: str = "100000",
    market: str = "500000",
    bonds: str = "50000",
    earnings: str = "60000",
    dist_type: str = "flat",
    dist_value: str = "40000",
    dist_low: str = "0",
    dist_high: str = "0",
    dist_mean: str = "0",
    dist_stddev: str = "5000",
    years: str = "30",
    sample_years: str = "",
    filing_status: str = "",
) -> dict[str, str]:
    data: dict[str, str] = {
        "snapshot_name": name,
        "snapshot_date": date,
        "cash_value": cash,
        "market_value": market,
        "bond_value": bonds,
        "earnings": earnings,
        "spending_dist_type": dist_type,
        "spending_dist_value": dist_value,
        "spending_dist_low": dist_low,
        "spending_dist_high": dist_high,
        "spending_dist_mean": dist_mean,
        "spending_dist_stddev": dist_stddev,
        "years_to_simulate": years,
    }
    if sample_years:
        data["sample_years"] = sample_years
    if filing_status:
        data["filing_status"] = filing_status
    return data


# --- Happy path ---


def test_snapshots_page_renders(client: TestClient) -> None:
    response = client.get("/snapshots")
    assert response.status_code == 200
    assert "Saved Snapshots" in response.text


def test_save_snapshot_from_form(client: TestClient, _db_path: Path) -> None:
    data = _snapshot_form_data(name="API Test", date="2025-07-01")
    response = client.post("/snapshots/save", data=data)
    assert response.status_code == 200
    assert "Snapshot saved" in response.text

    # Verify it's in the DB
    conn = get_connection(_db_path)
    from vibe_carlo.snapshots import list_snapshots

    rows = list_snapshots(conn)
    conn.close()
    assert any(r["name"] == "API Test" for r in rows)


def test_load_snapshot_into_form(client: TestClient, _db_path: Path) -> None:
    # Create a snapshot first
    conn = get_connection(_db_path)
    from vibe_carlo.schemas import FlatDistribution, SimulationInput
    from vibe_carlo.snapshots import create_snapshot

    params = SimulationInput(
        cash_value=250000,
        market_value=750000,
        bond_value=100000,
        earnings=80000,
        spending_distribution=FlatDistribution(value=55000),
        years_to_simulate=25,
    )
    sid = create_snapshot(conn, "LoadTest", "2025-08-01", params)
    conn.close()

    response = client.get(f"/?snapshot_id={sid}")
    assert response.status_code == 200
    assert "250000" in response.text
    assert "750000" in response.text
    assert "100000" in response.text
    assert "LoadTest" in response.text


def test_update_snapshot_via_api(client: TestClient, _db_path: Path) -> None:
    # Create a snapshot
    conn = get_connection(_db_path)
    from vibe_carlo.schemas import FlatDistribution, SimulationInput
    from vibe_carlo.snapshots import create_snapshot, get_snapshot

    params = SimulationInput(
        cash_value=100000,
        market_value=400000,
        bond_value=0,
        earnings=50000,
        spending_distribution=FlatDistribution(value=30000),
        years_to_simulate=20,
    )
    sid = create_snapshot(conn, "BeforeUpdate", "2025-01-01", params)
    conn.close()

    data = _snapshot_form_data(name="AfterUpdate", date="2025-12-01", cash="200000")
    response = client.post(f"/snapshots/{sid}/update", data=data)
    assert response.status_code == 200
    assert "Snapshot updated" in response.text

    conn = get_connection(_db_path)
    row = get_snapshot(conn, sid)
    conn.close()
    assert row is not None
    assert row["name"] == "AfterUpdate"
    assert row["cash_value"] == 200000.0


def test_delete_snapshot_via_api(client: TestClient, _db_path: Path) -> None:
    # Create a snapshot to delete
    conn = get_connection(_db_path)
    from vibe_carlo.schemas import FlatDistribution, SimulationInput
    from vibe_carlo.snapshots import create_snapshot, get_snapshot

    params = SimulationInput(
        cash_value=100000,
        market_value=400000,
        bond_value=0,
        earnings=0,
        spending_distribution=FlatDistribution(value=30000),
        years_to_simulate=20,
    )
    sid = create_snapshot(conn, "ToDelete", "2025-01-01", params)
    conn.close()

    response = client.delete(f"/snapshots/{sid}")
    assert response.status_code == 200

    conn = get_connection(_db_path)
    row = get_snapshot(conn, sid)
    conn.close()
    assert row is None


def test_snapshot_round_trip(client: TestClient, _db_path: Path) -> None:
    # Save
    data = _snapshot_form_data(
        name="RoundTrip",
        date="2025-09-01",
        cash="333000",
        market="666000",
        bonds="111000",
        earnings="75000",
        dist_type="uniform",
        dist_low="40000",
        dist_high="70000",
        years="35",
        filing_status="married_jointly",
    )
    response = client.post("/snapshots/save", data=data)
    assert response.status_code == 200

    # List
    response = client.get("/snapshots")
    assert response.status_code == 200
    assert "RoundTrip" in response.text

    # Find the snapshot ID
    conn = get_connection(_db_path)
    from vibe_carlo.snapshots import list_snapshots

    rows = list_snapshots(conn)
    conn.close()
    row = next(r for r in rows if r["name"] == "RoundTrip")
    sid = row["id"]

    # Load
    response = client.get(f"/?snapshot_id={sid}")
    assert response.status_code == 200
    assert "333000" in response.text
    assert "666000" in response.text

    # Update
    data = _snapshot_form_data(name="RoundTripUpdated", date="2025-10-01", cash="444000")
    response = client.post(f"/snapshots/{sid}/update", data=data)
    assert response.status_code == 200

    # Verify update
    conn = get_connection(_db_path)
    from vibe_carlo.snapshots import get_snapshot

    updated = get_snapshot(conn, sid)
    conn.close()
    assert updated is not None
    assert updated["name"] == "RoundTripUpdated"
    assert updated["cash_value"] == 444000.0


# --- Edge cases / validation ---


def test_save_snapshot_missing_date(client: TestClient) -> None:
    data = _snapshot_form_data(date="")
    response = client.post("/snapshots/save", data=data)
    assert response.status_code == 422
    assert "Date is required" in response.text


def test_save_snapshot_zero_portfolio(client: TestClient) -> None:
    data = _snapshot_form_data(cash="0", market="0", bonds="0")
    response = client.post("/snapshots/save", data=data)
    assert response.status_code == 422


def test_load_nonexistent_snapshot(client: TestClient) -> None:
    response = client.get("/?snapshot_id=99999")
    assert response.status_code == 404


def test_delete_nonexistent_snapshot(client: TestClient) -> None:
    response = client.delete("/snapshots/99999")
    assert response.status_code == 404


def test_update_nonexistent_snapshot(client: TestClient) -> None:
    data = _snapshot_form_data()
    response = client.post("/snapshots/99999/update", data=data)
    assert response.status_code == 404


def test_save_snapshot_each_distribution_type(client: TestClient, _db_path: Path) -> None:
    # Flat
    data = _snapshot_form_data(
        name="FlatDist", date="2025-01-01", dist_type="flat", dist_value="50000"
    )
    response = client.post("/snapshots/save", data=data)
    assert response.status_code == 200

    # Uniform
    data = _snapshot_form_data(
        name="UniformDist",
        date="2025-01-02",
        dist_type="uniform",
        dist_low="30000",
        dist_high="60000",
    )
    response = client.post("/snapshots/save", data=data)
    assert response.status_code == 200

    # Truncated normal
    data = _snapshot_form_data(
        name="NormalDist",
        date="2025-01-03",
        dist_type="truncated_normal",
        dist_low="20000",
        dist_high="80000",
        dist_mean="50000",
        dist_stddev="10000",
    )
    response = client.post("/snapshots/save", data=data)
    assert response.status_code == 200

    # Verify all three in DB
    conn = get_connection(_db_path)
    from vibe_carlo.snapshots import list_snapshots

    rows = list_snapshots(conn)
    conn.close()
    names = {r["name"] for r in rows}
    assert {"FlatDist", "UniformDist", "NormalDist"} <= names


def test_snapshots_page_empty(_db_path: Path) -> None:
    # Use a fresh DB
    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / "empty.db"
        init_db(db_path)
        original = app_module._db_path
        app_module._db_path = db_path
        try:
            with TestClient(app) as c:
                response = c.get("/snapshots")
                assert response.status_code == 200
                assert "No snapshots saved yet" in response.text
        finally:
            app_module._db_path = original
