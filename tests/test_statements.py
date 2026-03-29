"""CRUD unit tests for asset statement operations."""

from pathlib import Path

import pytest

from vibe_carlo.auth import create_user
from vibe_carlo.db import get_connection, init_db
from vibe_carlo.statements import (
    create_account,
    create_statement,
    delete_account,
    delete_statement,
    get_account,
    get_latest_statement,
    get_statement,
    list_accounts,
    list_statements,
    update_account,
    update_statement_date,
)


@pytest.fixture()
def db(tmp_path: Path) -> tuple[Path, int]:
    """Create a temporary SQLite database with a test user, return (path, user_id)."""
    db_path = tmp_path / "test.db"
    init_db(db_path)
    conn = get_connection(db_path)
    user_id = create_user(conn, "test@example.com", "password123")
    conn.close()
    return db_path, user_id


def _make_account_kwargs(
    name: str = "Checking",
    account_type: str = "asset",
    value: float = 10000.0,
) -> dict[str, object]:
    return {"name": name, "account_type": account_type, "value": value}


# --- Statement happy path ---


def test_create_and_get_statement(db: tuple[Path, int]) -> None:
    db_path, user_id = db
    conn = get_connection(db_path)
    stmt_id = create_statement(conn, user_id, "2025-06-15")
    stmt = get_statement(conn, stmt_id, user_id)
    conn.close()

    assert stmt is not None
    assert stmt["statement_date"] == "2025-06-15"
    assert stmt["user_id"] == user_id


def test_list_statements_ordered_by_date(db: tuple[Path, int]) -> None:
    db_path, user_id = db
    conn = get_connection(db_path)
    create_statement(conn, user_id, "2025-01-01")
    create_statement(conn, user_id, "2025-06-15")
    create_statement(conn, user_id, "2025-03-10")
    stmts = list_statements(conn, user_id)
    conn.close()

    assert len(stmts) == 3
    assert stmts[0]["statement_date"] == "2025-06-15"
    assert stmts[1]["statement_date"] == "2025-03-10"
    assert stmts[2]["statement_date"] == "2025-01-01"


def test_list_statements_with_net_worth(db: tuple[Path, int]) -> None:
    db_path, user_id = db
    conn = get_connection(db_path)
    stmt_id = create_statement(conn, user_id, "2025-06-15")
    create_account(conn, stmt_id, user_id, name="House", account_type="asset", value=500000)
    create_account(conn, stmt_id, user_id, name="401k", account_type="asset", value=200000)
    create_account(conn, stmt_id, user_id, name="Mortgage", account_type="liability", value=300000)
    stmts = list_statements(conn, user_id)
    conn.close()

    assert len(stmts) == 1
    # net_worth = 500000 + 200000 + (-300000) = 400000
    assert stmts[0]["net_worth"] == pytest.approx(400000.0)


def test_update_statement_date(db: tuple[Path, int]) -> None:
    db_path, user_id = db
    conn = get_connection(db_path)
    stmt_id = create_statement(conn, user_id, "2025-06-15")
    result = update_statement_date(conn, stmt_id, user_id, "2025-07-01")
    stmt = get_statement(conn, stmt_id, user_id)
    conn.close()

    assert result is True
    assert stmt is not None
    assert stmt["statement_date"] == "2025-07-01"


def test_delete_statement(db: tuple[Path, int]) -> None:
    db_path, user_id = db
    conn = get_connection(db_path)
    stmt_id = create_statement(conn, user_id, "2025-06-15")
    result = delete_statement(conn, stmt_id, user_id)
    stmt = get_statement(conn, stmt_id, user_id)
    conn.close()

    assert result is True
    assert stmt is None


# --- Account happy path ---


def test_create_account(db: tuple[Path, int]) -> None:
    db_path, user_id = db
    conn = get_connection(db_path)
    stmt_id = create_statement(conn, user_id, "2025-06-15")
    acct_id = create_account(conn, stmt_id, user_id, **_make_account_kwargs())  # type: ignore[arg-type]
    acct = get_account(conn, acct_id, user_id)  # type: ignore[arg-type]
    conn.close()

    assert acct is not None
    assert acct["name"] == "Checking"
    assert acct["account_type"] == "asset"
    assert acct["value"] == 10000.0
    assert acct["order_position"] == 0


def test_list_accounts_ordered(db: tuple[Path, int]) -> None:
    db_path, user_id = db
    conn = get_connection(db_path)
    stmt_id = create_statement(conn, user_id, "2025-06-15")
    # Create liability first, then asset
    create_account(conn, stmt_id, user_id, name="Visa", account_type="liability", value=5000)
    create_account(conn, stmt_id, user_id, name="Checking", account_type="asset", value=10000)
    create_account(conn, stmt_id, user_id, name="Savings", account_type="asset", value=20000)
    accounts = list_accounts(conn, stmt_id, user_id)
    conn.close()

    assert len(accounts) == 3
    # Assets come first
    assert accounts[0]["account_type"] == "asset"
    assert accounts[1]["account_type"] == "asset"
    assert accounts[2]["account_type"] == "liability"


def test_update_account(db: tuple[Path, int]) -> None:
    db_path, user_id = db
    conn = get_connection(db_path)
    stmt_id = create_statement(conn, user_id, "2025-06-15")
    acct_id = create_account(conn, stmt_id, user_id, **_make_account_kwargs())  # type: ignore[arg-type]
    result = update_account(
        conn,
        acct_id,  # type: ignore[arg-type]
        user_id,
        name="Savings",
        account_type="asset",
        value=25000,
    )
    acct = get_account(conn, acct_id, user_id)  # type: ignore[arg-type]
    conn.close()

    assert result is True
    assert acct is not None
    assert acct["name"] == "Savings"
    assert acct["value"] == 25000.0


def test_delete_account(db: tuple[Path, int]) -> None:
    db_path, user_id = db
    conn = get_connection(db_path)
    stmt_id = create_statement(conn, user_id, "2025-06-15")
    acct_id = create_account(conn, stmt_id, user_id, **_make_account_kwargs())  # type: ignore[arg-type]
    result = delete_account(conn, acct_id, user_id)  # type: ignore[arg-type]
    acct = get_account(conn, acct_id, user_id)  # type: ignore[arg-type]
    conn.close()

    assert result is True
    assert acct is None


def test_get_latest_statement(db: tuple[Path, int]) -> None:
    db_path, user_id = db
    conn = get_connection(db_path)
    create_statement(conn, user_id, "2025-01-01")
    create_statement(conn, user_id, "2025-06-15")
    create_statement(conn, user_id, "2025-03-10")
    latest = get_latest_statement(conn, user_id)
    conn.close()

    assert latest is not None
    assert latest["statement_date"] == "2025-06-15"


# --- Value sign enforcement ---


def test_create_account_asset_positive(db: tuple[Path, int]) -> None:
    db_path, user_id = db
    conn = get_connection(db_path)
    stmt_id = create_statement(conn, user_id, "2025-06-15")
    acct_id = create_account(conn, stmt_id, user_id, name="401k", account_type="asset", value=5000)
    acct = get_account(conn, acct_id, user_id)  # type: ignore[arg-type]
    conn.close()

    assert acct is not None
    assert acct["value"] == 5000.0


def test_create_account_liability_negative(db: tuple[Path, int]) -> None:
    db_path, user_id = db
    conn = get_connection(db_path)
    stmt_id = create_statement(conn, user_id, "2025-06-15")
    acct_id = create_account(
        conn, stmt_id, user_id, name="Mortgage", account_type="liability", value=5000
    )
    acct = get_account(conn, acct_id, user_id)  # type: ignore[arg-type]
    conn.close()

    assert acct is not None
    assert acct["value"] == -5000.0


def test_update_account_type_change_flips_sign(db: tuple[Path, int]) -> None:
    db_path, user_id = db
    conn = get_connection(db_path)
    stmt_id = create_statement(conn, user_id, "2025-06-15")
    acct_id = create_account(conn, stmt_id, user_id, name="Car", account_type="asset", value=20000)
    # Change to liability
    update_account(conn, acct_id, user_id, name="Car Loan", account_type="liability", value=20000)  # type: ignore[arg-type]
    acct = get_account(conn, acct_id, user_id)  # type: ignore[arg-type]
    conn.close()

    assert acct is not None
    assert acct["value"] == -20000.0


def test_update_account_liability_to_asset(db: tuple[Path, int]) -> None:
    db_path, user_id = db
    conn = get_connection(db_path)
    stmt_id = create_statement(conn, user_id, "2025-06-15")
    acct_id = create_account(
        conn, stmt_id, user_id, name="Loan", account_type="liability", value=10000
    )
    update_account(conn, acct_id, user_id, name="Investment", account_type="asset", value=10000)  # type: ignore[arg-type]
    acct = get_account(conn, acct_id, user_id)  # type: ignore[arg-type]
    conn.close()

    assert acct is not None
    assert acct["value"] == 10000.0


# --- Edge cases ---


def test_get_nonexistent_statement(db: tuple[Path, int]) -> None:
    db_path, user_id = db
    conn = get_connection(db_path)
    stmt = get_statement(conn, 999, user_id)
    conn.close()
    assert stmt is None


def test_delete_nonexistent_statement(db: tuple[Path, int]) -> None:
    db_path, user_id = db
    conn = get_connection(db_path)
    result = delete_statement(conn, 999, user_id)
    conn.close()
    assert result is False


def test_create_account_wrong_user(db: tuple[Path, int]) -> None:
    db_path, user_id = db
    conn = get_connection(db_path)
    stmt_id = create_statement(conn, user_id, "2025-06-15")
    user_b_id = create_user(conn, "other@example.com", "password456")
    acct_id = create_account(
        conn, stmt_id, user_b_id, name="Sneaky", account_type="asset", value=9999
    )
    conn.close()
    assert acct_id is None


def test_get_latest_statement_none(db: tuple[Path, int]) -> None:
    db_path, user_id = db
    conn = get_connection(db_path)
    latest = get_latest_statement(conn, user_id)
    conn.close()
    assert latest is None


def test_list_statements_empty(db: tuple[Path, int]) -> None:
    db_path, user_id = db
    conn = get_connection(db_path)
    stmts = list_statements(conn, user_id)
    conn.close()
    assert stmts == []


def test_list_accounts_empty(db: tuple[Path, int]) -> None:
    db_path, user_id = db
    conn = get_connection(db_path)
    stmt_id = create_statement(conn, user_id, "2025-06-15")
    accounts = list_accounts(conn, stmt_id, user_id)
    conn.close()
    assert accounts == []


def test_net_worth_zero_no_accounts(db: tuple[Path, int]) -> None:
    db_path, user_id = db
    conn = get_connection(db_path)
    create_statement(conn, user_id, "2025-06-15")
    stmts = list_statements(conn, user_id)
    conn.close()
    assert stmts[0]["net_worth"] == pytest.approx(0.0)


# --- Cascade & Isolation ---


def test_delete_statement_cascades(db: tuple[Path, int]) -> None:
    db_path, user_id = db
    conn = get_connection(db_path)
    stmt_id = create_statement(conn, user_id, "2025-06-15")
    create_account(conn, stmt_id, user_id, name="House", account_type="asset", value=500000)
    create_account(conn, stmt_id, user_id, name="Mortgage", account_type="liability", value=300000)
    delete_statement(conn, stmt_id, user_id)
    accounts = list_accounts(conn, stmt_id, user_id)
    conn.close()
    assert accounts == []


def test_cross_user_isolation(db: tuple[Path, int]) -> None:
    db_path, user_id = db
    conn = get_connection(db_path)
    user_b_id = create_user(conn, "userb@example.com", "password456")
    stmt_id = create_statement(conn, user_id, "2025-06-15")
    create_account(conn, stmt_id, user_id, name="House", account_type="asset", value=500000)

    # User B cannot access User A's data
    assert get_statement(conn, stmt_id, user_b_id) is None
    assert list_statements(conn, user_b_id) == []
    assert update_statement_date(conn, stmt_id, user_b_id, "2025-07-01") is False
    assert delete_statement(conn, stmt_id, user_b_id) is False
    assert list_accounts(conn, stmt_id, user_b_id) == []
    assert (
        create_account(conn, stmt_id, user_b_id, name="Sneaky", account_type="asset", value=1)
        is None
    )

    conn.close()
