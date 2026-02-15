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
            "earnings": "12000",
            "spending_dist_type": "flat",
            "spending_dist_value": "0",
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
            "earnings": "0",
            "spending_dist_type": "flat",
            "spending_dist_value": "5000",
            "years_to_simulate": "20",
            "sample_years": "5",
        },
    )
    assert response.status_code == 200
    assert "Portfolio Survival Rate" in response.text


def test_simulate_with_tax_settings(client: TestClient) -> None:
    response = client.post(
        "/simulate",
        data={
            "cash_value": "0",
            "market_value": "500000",
            "bond_value": "0",
            "earnings": "0",
            "spending_dist_type": "flat",
            "spending_dist_value": "50000",
            "years_to_simulate": "10",
            "filing_status": "single",
        },
    )
    assert response.status_code == 200
    assert "Portfolio Survival Rate" in response.text
    assert "Federal Tax Adjustment" in response.text
    assert "Gross" in response.text


def test_simulate_without_filing_status_no_tax_card(client: TestClient) -> None:
    response = client.post(
        "/simulate",
        data={
            "cash_value": "10000",
            "market_value": "70000",
            "bond_value": "20000",
            "earnings": "12000",
            "spending_dist_type": "flat",
            "spending_dist_value": "0",
            "years_to_simulate": "10",
        },
    )
    assert response.status_code == 200
    assert "Federal Tax Adjustment" not in response.text


def test_simulate_invalid_filing_status(client: TestClient) -> None:
    response = client.post(
        "/simulate",
        data={
            "cash_value": "10000",
            "market_value": "70000",
            "bond_value": "20000",
            "earnings": "0",
            "spending_dist_type": "flat",
            "spending_dist_value": "5000",
            "years_to_simulate": "10",
            "filing_status": "invalid_status",
        },
    )
    assert response.status_code == 422


def test_simulate_validation_error_zero_portfolio(client: TestClient) -> None:
    response = client.post(
        "/simulate",
        data={
            "cash_value": "0",
            "market_value": "0",
            "bond_value": "0",
            "earnings": "0",
            "spending_dist_type": "flat",
            "spending_dist_value": "0",
            "years_to_simulate": "30",
        },
    )
    assert response.status_code == 422


def test_simulate_uniform_distribution(client: TestClient) -> None:
    response = client.post(
        "/simulate",
        data={
            "cash_value": "0",
            "market_value": "500000",
            "bond_value": "0",
            "earnings": "0",
            "spending_dist_type": "uniform",
            "spending_dist_low": "40000",
            "spending_dist_high": "60000",
            "years_to_simulate": "10",
        },
    )
    assert response.status_code == 200
    assert "Portfolio Survival Rate" in response.text


def test_simulate_truncated_normal_distribution(client: TestClient) -> None:
    response = client.post(
        "/simulate",
        data={
            "cash_value": "0",
            "market_value": "500000",
            "bond_value": "0",
            "earnings": "0",
            "spending_dist_type": "truncated_normal",
            "spending_dist_low": "35000",
            "spending_dist_high": "65000",
            "spending_dist_mean": "50000",
            "spending_dist_stddev": "5000",
            "years_to_simulate": "10",
        },
    )
    assert response.status_code == 200
    assert "Portfolio Survival Rate" in response.text


def test_simulate_uniform_with_tax(client: TestClient) -> None:
    response = client.post(
        "/simulate",
        data={
            "cash_value": "0",
            "market_value": "500000",
            "bond_value": "0",
            "earnings": "0",
            "spending_dist_type": "uniform",
            "spending_dist_low": "40000",
            "spending_dist_high": "60000",
            "years_to_simulate": "10",
            "filing_status": "single",
        },
    )
    assert response.status_code == 200
    assert "Federal Tax Adjustment" in response.text
    assert "Avg gross" in response.text
