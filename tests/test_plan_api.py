"""API integration tests for plan routes."""

import tempfile
from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import vibe_carlo.app as app_module
from vibe_carlo.app import app
from vibe_carlo.auth import create_session, create_user
from vibe_carlo.db import get_connection, init_db


@pytest.fixture(scope="module")
def _db_path() -> Generator[tuple[Path, int]]:
    """Set up a temp DB with a test user and patch app._db_path."""
    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / "test.db"
        init_db(db_path)
        conn = get_connection(db_path)
        user_id = create_user(conn, "plantest@example.com", "password123")
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


def _param_set_form_data(
    name: str = "Working Phase",
    duration: str = "10",
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
    filing_status: str = "",
) -> dict[str, str]:
    data: dict[str, str] = {
        "param_name": name,
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
    }
    if duration:
        data["duration"] = duration
    if filing_status:
        data["filing_status"] = filing_status
    return data


def test_plans_page_renders(client: TestClient) -> None:
    response = client.get("/plans")
    assert response.status_code == 200
    assert "Plans" in response.text


def test_create_plan(client: TestClient) -> None:
    response = client.post("/plans", data={"name": "Test Plan"}, follow_redirects=False)
    assert response.status_code == 303
    assert "/plans/" in response.headers["location"]


def test_plan_author_page_renders(client: TestClient) -> None:
    # Create a plan first
    response = client.post("/plans", data={"name": "Author Test"}, follow_redirects=False)
    plan_url = response.headers["location"]

    response = client.get(plan_url)
    assert response.status_code == 200
    assert "Author Test" in response.text
    assert "Add Parameter Set" in response.text


def test_add_parameter_set(client: TestClient) -> None:
    # Create a plan
    response = client.post("/plans", data={"name": "Param Test"}, follow_redirects=False)
    plan_url = response.headers["location"]
    plan_id = plan_url.split("/")[-1]

    # Add a parameter set
    data = _param_set_form_data(name="Working Phase")
    response = client.post(f"/plans/{plan_id}/params", data=data)
    assert response.status_code == 200
    assert "Working Phase" in response.text


def test_update_parameter_set(client: TestClient) -> None:
    # Create a plan with a parameter set
    response = client.post("/plans", data={"name": "Update PS Test"}, follow_redirects=False)
    plan_id = response.headers["location"].split("/")[-1]

    data = _param_set_form_data(name="Original")
    client.post(f"/plans/{plan_id}/params", data=data)

    # Get the param set ID from author page
    response = client.get(f"/plans/{plan_id}")
    # The page should have the parameter set listed
    assert "Original" in response.text

    # Find param ID - get it from the edit link
    import re

    match = re.search(r"edit_param_id=(\d+)", response.text)
    assert match is not None
    param_id = match.group(1)

    # Update
    data = _param_set_form_data(name="Updated")
    response = client.post(f"/plans/{plan_id}/params/{param_id}", data=data)
    assert response.status_code == 200
    assert "Updated" in response.text


def test_delete_parameter_set(client: TestClient) -> None:
    # Create a plan with a parameter set
    response = client.post("/plans", data={"name": "Delete PS Test"}, follow_redirects=False)
    plan_id = response.headers["location"].split("/")[-1]

    data = _param_set_form_data(name="ToDelete")
    client.post(f"/plans/{plan_id}/params", data=data)

    # Get param ID
    import re

    response = client.get(f"/plans/{plan_id}")
    match = re.search(r"edit_param_id=(\d+)", response.text)
    assert match is not None
    param_id = match.group(1)

    response = client.delete(f"/plans/{plan_id}/params/{param_id}")
    assert response.status_code == 200
    assert "ToDelete" not in response.text


def test_move_parameter_set(client: TestClient) -> None:
    # Create a plan with two parameter sets
    response = client.post("/plans", data={"name": "Move PS Test"}, follow_redirects=False)
    plan_id = response.headers["location"].split("/")[-1]

    client.post(f"/plans/{plan_id}/params", data=_param_set_form_data(name="First"))
    client.post(f"/plans/{plan_id}/params", data=_param_set_form_data(name="Second"))

    # Get second param ID
    import re

    response = client.get(f"/plans/{plan_id}")
    matches = re.findall(r"edit_param_id=(\d+)", response.text)
    assert len(matches) >= 2
    second_id = matches[1]  # Second parameter set

    # Move second up
    response = client.post(
        f"/plans/{plan_id}/params/{second_id}/move",
        data={"direction": "up"},
    )
    assert response.status_code == 200


def test_delete_plan(client: TestClient) -> None:
    response = client.post("/plans", data={"name": "To Delete Plan"}, follow_redirects=False)
    plan_id = response.headers["location"].split("/")[-1]

    response = client.delete(f"/plans/{plan_id}")
    assert response.status_code == 200


def test_plan_simulate_page_renders(client: TestClient) -> None:
    # Create plan with a parameter set
    response = client.post("/plans", data={"name": "Sim Page Test"}, follow_redirects=False)
    plan_id = response.headers["location"].split("/")[-1]

    client.post(f"/plans/{plan_id}/params", data=_param_set_form_data())

    response = client.get(f"/plans/{plan_id}/simulate")
    assert response.status_code == 200
    assert "Simulate" in response.text
    assert "Plan Phases" in response.text


def test_run_plan_simulation(client: TestClient) -> None:
    # Create plan with a parameter set
    response = client.post("/plans", data={"name": "Run Sim Test"}, follow_redirects=False)
    plan_id = response.headers["location"].split("/")[-1]

    client.post(f"/plans/{plan_id}/params", data=_param_set_form_data())

    response = client.post(
        f"/plans/{plan_id}/simulate",
        data={"years_to_simulate": "10"},
    )
    assert response.status_code == 200
    assert "Survival Rate" in response.text


def test_simulate_empty_plan_error(client: TestClient) -> None:
    # Create plan without parameter sets
    response = client.post("/plans", data={"name": "Empty Plan"}, follow_redirects=False)
    plan_id = response.headers["location"].split("/")[-1]

    response = client.post(
        f"/plans/{plan_id}/simulate",
        data={"years_to_simulate": "10"},
    )
    assert response.status_code == 422


def test_nonexistent_plan_404(client: TestClient) -> None:
    response = client.get("/plans/99999")
    assert response.status_code == 404
