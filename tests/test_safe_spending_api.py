"""API integration tests for the safe-spending routes."""

import re
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
    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / "test.db"
        init_db(db_path)
        conn = get_connection(db_path)
        user_id = create_user(conn, "solvetest@example.com", "password123")
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


BASE_FORM = {
    "cash_value": "50000",
    "market_value": "800000",
    "bond_value": "150000",
    "earnings": "0",
    "spending_dist_type": "flat",
    "spending_dist_value": "40000",
    "years_to_simulate": "30",
    "sample_years": "5",
    "withdrawal_tax_rate_pct": "0",
}


def _dollar_rows(html: str) -> list[int]:
    return [int(v.replace(",", "")) for v in re.findall(r"\$([\d,]+)\s*</td>", html)]


def test_safe_spending_returns_table(client: TestClient) -> None:
    resp = client.post("/safe-spending", data=BASE_FORM)
    assert resp.status_code == 200
    body = resp.text
    for level in (95, 90, 85, 80, 75, 70, 65, 60, 55, 50):
        assert f">\n                        {level}%" in body
    # 99% is deliberately not offered as a row (it appears only in the caveat text).
    assert ">\n                        99%" not in body


def test_safe_spending_rows_increase_as_success_falls(client: TestClient) -> None:
    resp = client.post("/safe-spending", data=BASE_FORM)
    values = _dollar_rows(resp.text)
    assert len(values) == 10
    assert values == sorted(values)


def test_safe_spending_target_lowers_the_numbers(client: TestClient) -> None:
    without = _dollar_rows(client.post("/safe-spending", data=BASE_FORM).text)
    with_target = _dollar_rows(
        client.post("/safe-spending", data={**BASE_FORM, "target_net_worth": "500000"}).text
    )
    assert all(a < b for a, b in zip(with_target, without))


def test_safe_spending_rejects_zero_spending(client: TestClient) -> None:
    resp = client.post("/safe-spending", data={**BASE_FORM, "spending_dist_value": "0"})
    assert resp.status_code == 422
    assert "spending being solved for is zero" in resp.json()["detail"][0]


def test_safe_spending_rejects_negative_target(client: TestClient) -> None:
    resp = client.post("/safe-spending", data={**BASE_FORM, "target_net_worth": "-1"})
    assert resp.status_code == 422


def test_safe_spending_requires_auth() -> None:
    with TestClient(app) as anon:
        resp = anon.post("/safe-spending", data=BASE_FORM, follow_redirects=False)
        assert resp.status_code in (303, 401)


# ---------------------------------------------------------------------------
# Plan route
# ---------------------------------------------------------------------------


def _make_plan(client: TestClient) -> int:
    resp = client.post("/plans", data={"name": "Solver plan"})
    assert resp.status_code == 200
    plan_id = max(int(v) for v in re.findall(r"/plans/(\d+)", resp.text))

    for name, duration, earnings, spend in (
        ("Working", "10", "150000", "90000"),
        ("Retirement", "", "25000", "60000"),
    ):
        resp = client.post(
            f"/plans/{plan_id}/params",
            data={
                "param_name": name,
                "duration": duration,
                "cash_value": "50000",
                "market_value": "800000",
                "bond_value": "150000",
                "earnings": earnings,
                "spending_dist_type": "flat",
                "spending_dist_value": spend,
                "withdrawal_tax_rate_pct": "15",
            },
        )
        assert resp.status_code == 200
    return plan_id


def test_plan_safe_spending_solves_final_phase(client: TestClient) -> None:
    plan_id = _make_plan(client)
    resp = client.post(
        f"/plans/{plan_id}/safe-spending",
        data={"years_to_simulate": "35", "sample_years": "5"},
    )
    assert resp.status_code == 200
    body = resp.text
    # The heading names the phase being solved, not the committed one.
    assert "Retirement" in body
    # 35-year horizon less the 10 committed working years.
    assert "25-year phase" in body
    values = _dollar_rows(body)
    assert len(values) == 10
    assert values == sorted(values)


def test_plan_safe_spending_unknown_plan_is_404(client: TestClient) -> None:
    resp = client.post("/plans/999999/safe-spending", data={"years_to_simulate": "30"})
    assert resp.status_code == 404
