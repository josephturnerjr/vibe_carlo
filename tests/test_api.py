from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

from vibe_carlo.app import app


@pytest.fixture(scope="module")
def client() -> Generator[TestClient]:
    with TestClient(app) as c:
        yield c


def test_index_page_renders(client: TestClient) -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "vibe_carlo" in response.text
    assert "Run Simulation" in response.text


def test_simulate_returns_results(client: TestClient) -> None:
    response = client.post(
        "/simulate",
        data={
            "cash_value": "10000",
            "market_value": "70000",
            "bond_value": "20000",
            "annual_contribution": "12000",
            "annual_spending": "0",
            "years_to_simulate": "10",
        },
    )
    assert response.status_code == 200
    assert "Portfolio Survival Rate" in response.text
    assert "fan-chart" in response.text
    assert "histogram" in response.text


def test_simulate_with_sample_years(client: TestClient) -> None:
    response = client.post(
        "/simulate",
        data={
            "cash_value": "0",
            "market_value": "100000",
            "bond_value": "0",
            "annual_contribution": "0",
            "annual_spending": "5000",
            "years_to_simulate": "20",
            "sample_years": "5",
        },
    )
    assert response.status_code == 200
    assert "Portfolio Survival Rate" in response.text


def test_simulate_validation_error_zero_portfolio(client: TestClient) -> None:
    response = client.post(
        "/simulate",
        data={
            "cash_value": "0",
            "market_value": "0",
            "bond_value": "0",
            "annual_contribution": "0",
            "annual_spending": "0",
            "years_to_simulate": "30",
        },
    )
    assert response.status_code == 422
