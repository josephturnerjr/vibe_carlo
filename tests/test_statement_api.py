"""API integration tests for statement routes."""

import tempfile
from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import vibe_carlo.app as app_module
from vibe_carlo.app import app
from vibe_carlo.auth import create_session, create_user
from vibe_carlo.db import get_connection, init_db
from vibe_carlo.statements import create_account, create_statement, get_statement, list_accounts


@pytest.fixture(scope="module")
def _db_path() -> Generator[tuple[Path, int]]:
    """Set up a temp DB with a test user and patch app._db_path."""
    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / "test.db"
        init_db(db_path)
        conn = get_connection(db_path)
        user_id = create_user(conn, "stmttest@example.com", "password123")
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


def _statement_form_data(
    date: str = "2025-06-15",
    account_ids: list[str] | None = None,
    account_names: list[str] | None = None,
    account_types: list[str] | None = None,
    account_values: list[str] | None = None,
) -> dict[str, str | list[str]]:
    data: dict[str, str | list[str]] = {"statement_date": date}
    if account_ids is not None:
        data["account_ids"] = account_ids
    if account_names is not None:
        data["account_names"] = account_names
    if account_types is not None:
        data["account_types"] = account_types
    if account_values is not None:
        data["account_values"] = account_values
    return data


# --- Page Rendering ---


def test_statements_page_renders(client: TestClient) -> None:
    response = client.get("/statements")
    assert response.status_code == 200
    assert "Asset Statements" in response.text


def test_statements_page_empty(client: TestClient) -> None:
    response = client.get("/statements")
    assert response.status_code == 200
    # Should show either "No statements yet." or "New Statement" button
    assert "No statements yet." in response.text or "New Statement" in response.text


# --- Create Flow ---


def test_create_statement_blank(client: TestClient, _db_path: tuple[Path, int]) -> None:
    response = client.post(
        "/statements",
        data={"statement_date": "2025-06-15", "copy_from_latest": "false"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert "/statements/" in response.headers["location"]


def test_create_statement_copy_from_latest(client: TestClient, _db_path: tuple[Path, int]) -> None:
    db_path, user_id = _db_path

    # Create a statement with accounts that will be the latest by date
    conn = get_connection(db_path)
    src_id = create_statement(conn, user_id, "2099-12-31")
    create_account(conn, src_id, user_id, name="CopyHouse", account_type="asset", value=500000)
    create_account(
        conn, src_id, user_id, name="CopyMortgage", account_type="liability", value=300000
    )
    conn.close()

    response = client.post(
        "/statements",
        data={"statement_date": "2099-12-31", "copy_from_latest": "true"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    new_url = response.headers["location"]
    new_id = int(new_url.split("/")[-1])

    # Verify accounts were copied
    conn = get_connection(db_path)
    accounts = list_accounts(conn, new_id, user_id)
    conn.close()

    assert len(accounts) == 2
    names = {str(a["name"]) for a in accounts}
    assert "CopyHouse" in names
    assert "CopyMortgage" in names


def test_create_statement_copy_no_prior(client: TestClient) -> None:
    # This tests copy_from_latest=true when the new statement IS the latest
    # (edge case: no prior statements by other date)
    response = client.post(
        "/statements",
        data={"statement_date": "2020-01-01", "copy_from_latest": "true"},
        follow_redirects=False,
    )
    assert response.status_code == 303


def test_create_statement_date_required(client: TestClient) -> None:
    response = client.post(
        "/statements",
        data={"statement_date": "", "copy_from_latest": "false"},
    )
    assert response.status_code == 422


# --- Save Flow ---


def test_save_statement_update_date(client: TestClient, _db_path: tuple[Path, int]) -> None:
    db_path, user_id = _db_path

    # Create a statement
    conn = get_connection(db_path)
    stmt_id = create_statement(conn, user_id, "2025-06-15")
    conn.close()

    response = client.post(
        f"/statements/{stmt_id}",
        data=_statement_form_data(date="2025-08-01"),
    )
    assert response.status_code == 200

    conn = get_connection(db_path)
    stmt = get_statement(conn, stmt_id, user_id)
    conn.close()
    assert stmt is not None
    assert stmt["statement_date"] == "2025-08-01"


def test_save_statement_add_accounts(client: TestClient, _db_path: tuple[Path, int]) -> None:
    db_path, user_id = _db_path

    conn = get_connection(db_path)
    stmt_id = create_statement(conn, user_id, "2025-06-15")
    conn.close()

    response = client.post(
        f"/statements/{stmt_id}",
        data=_statement_form_data(
            account_ids=["", ""],
            account_names=["Checking", "Savings"],
            account_types=["asset", "asset"],
            account_values=["5000", "10000"],
        ),
    )
    assert response.status_code == 200

    conn = get_connection(db_path)
    accounts = list_accounts(conn, stmt_id, user_id)
    conn.close()
    assert len(accounts) == 2


def test_save_statement_update_accounts(client: TestClient, _db_path: tuple[Path, int]) -> None:
    db_path, user_id = _db_path

    conn = get_connection(db_path)
    stmt_id = create_statement(conn, user_id, "2025-06-15")
    acct_id = create_account(
        conn, stmt_id, user_id, name="Checking", account_type="asset", value=5000
    )
    conn.close()

    response = client.post(
        f"/statements/{stmt_id}",
        data=_statement_form_data(
            account_ids=[str(acct_id)],
            account_names=["Updated Checking"],
            account_types=["asset"],
            account_values=["15000"],
        ),
    )
    assert response.status_code == 200

    conn = get_connection(db_path)
    accounts = list_accounts(conn, stmt_id, user_id)
    conn.close()
    assert len(accounts) == 1
    assert accounts[0]["name"] == "Updated Checking"
    assert accounts[0]["value"] == 15000.0


def test_save_statement_remove_accounts(client: TestClient, _db_path: tuple[Path, int]) -> None:
    db_path, user_id = _db_path

    conn = get_connection(db_path)
    stmt_id = create_statement(conn, user_id, "2025-06-15")
    create_account(conn, stmt_id, user_id, name="ToKeep", account_type="asset", value=5000)
    create_account(conn, stmt_id, user_id, name="ToRemove", account_type="asset", value=3000)
    accounts_before = list_accounts(conn, stmt_id, user_id)
    keep_id = str(accounts_before[0]["id"])
    conn.close()

    # Only send the first account
    response = client.post(
        f"/statements/{stmt_id}",
        data=_statement_form_data(
            account_ids=[keep_id],
            account_names=["ToKeep"],
            account_types=["asset"],
            account_values=["5000"],
        ),
    )
    assert response.status_code == 200

    conn = get_connection(db_path)
    accounts = list_accounts(conn, stmt_id, user_id)
    conn.close()
    assert len(accounts) == 1
    assert accounts[0]["name"] == "ToKeep"


def test_save_statement_full_reconciliation(
    client: TestClient, _db_path: tuple[Path, int]
) -> None:
    db_path, user_id = _db_path

    conn = get_connection(db_path)
    stmt_id = create_statement(conn, user_id, "2025-06-15")
    acct1 = create_account(
        conn, stmt_id, user_id, name="Update Me", account_type="asset", value=1000
    )
    create_account(conn, stmt_id, user_id, name="Delete Me", account_type="asset", value=2000)
    conn.close()

    # Update acct1, delete acct2, add new acct3
    response = client.post(
        f"/statements/{stmt_id}",
        data=_statement_form_data(
            account_ids=[str(acct1), ""],
            account_names=["Updated", "Brand New"],
            account_types=["asset", "liability"],
            account_values=["5000", "3000"],
        ),
    )
    assert response.status_code == 200

    conn = get_connection(db_path)
    accounts = list_accounts(conn, stmt_id, user_id)
    conn.close()

    assert len(accounts) == 2
    names = {str(a["name"]) for a in accounts}
    assert "Updated" in names
    assert "Brand New" in names
    assert "Delete Me" not in names


# --- Delete Flow ---


def test_delete_statement(client: TestClient, _db_path: tuple[Path, int]) -> None:
    db_path, user_id = _db_path

    conn = get_connection(db_path)
    stmt_id = create_statement(conn, user_id, "2025-06-15")
    conn.close()

    response = client.delete(f"/statements/{stmt_id}")
    assert response.status_code == 200

    conn = get_connection(db_path)
    stmt = get_statement(conn, stmt_id, user_id)
    conn.close()
    assert stmt is None


def test_delete_nonexistent_statement(client: TestClient) -> None:
    response = client.delete("/statements/99999")
    assert response.status_code == 404


# --- Display ---


def test_net_worth_accounting_format(client: TestClient, _db_path: tuple[Path, int]) -> None:
    db_path, user_id = _db_path

    conn = get_connection(db_path)
    stmt_id = create_statement(conn, user_id, "2025-12-31")
    create_account(conn, stmt_id, user_id, name="Savings", account_type="asset", value=1234567)
    conn.close()

    response = client.get("/statements")
    assert response.status_code == 200
    assert "$" in response.text
    assert "1,234,567" in response.text


def test_edit_page_shows_accounts(client: TestClient, _db_path: tuple[Path, int]) -> None:
    db_path, user_id = _db_path

    conn = get_connection(db_path)
    stmt_id = create_statement(conn, user_id, "2025-06-15")
    create_account(conn, stmt_id, user_id, name="My401k", account_type="asset", value=250000)
    conn.close()

    response = client.get(f"/statements/{stmt_id}")
    assert response.status_code == 200
    assert "My401k" in response.text
    assert "250000" in response.text


def test_edit_page_sections(client: TestClient, _db_path: tuple[Path, int]) -> None:
    db_path, user_id = _db_path

    conn = get_connection(db_path)
    stmt_id = create_statement(conn, user_id, "2025-06-15")
    conn.close()

    response = client.get(f"/statements/{stmt_id}")
    assert response.status_code == 200
    assert "Assets" in response.text
    assert "Liabilities" in response.text


def test_statement_edit_page_renders(client: TestClient, _db_path: tuple[Path, int]) -> None:
    db_path, user_id = _db_path

    conn = get_connection(db_path)
    stmt_id = create_statement(conn, user_id, "2025-06-15")
    conn.close()

    response = client.get(f"/statements/{stmt_id}")
    assert response.status_code == 200


# --- Not Found ---


def test_edit_nonexistent_statement(client: TestClient) -> None:
    response = client.get("/statements/99999")
    assert response.status_code == 404


def test_save_nonexistent_statement(client: TestClient) -> None:
    response = client.post(
        "/statements/99999",
        data=_statement_form_data(),
    )
    assert response.status_code == 404
