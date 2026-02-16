"""CLI user management tests."""

import argparse
from pathlib import Path

import pytest

from vibe_carlo.auth import get_user_by_email, verify_password
from vibe_carlo.cli import (
    cmd_assign_snapshots,
    cmd_change_password,
    cmd_create,
    cmd_delete,
    cmd_list,
)
from vibe_carlo.db import get_connection, init_db


@pytest.fixture(autouse=True)
def _set_db_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Set VIBE_CARLO_DB to a temp path for all tests."""
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("VIBE_CARLO_DB", str(db_path))
    init_db(db_path)
    return db_path


def _ns(**kwargs: object) -> argparse.Namespace:
    """Build an argparse.Namespace from kwargs."""
    return argparse.Namespace(**kwargs)


def test_create_user(_set_db_env: Path) -> None:
    cmd_create(_ns(email="new@test.com", password="secret123"))
    conn = get_connection(_set_db_env)
    user = get_user_by_email(conn, "new@test.com")
    conn.close()
    assert user is not None
    assert verify_password("secret123", str(user["password_hash"]))


def test_create_duplicate_user(_set_db_env: Path) -> None:
    cmd_create(_ns(email="dup@test.com", password="pass1"))
    with pytest.raises(SystemExit):
        cmd_create(_ns(email="dup@test.com", password="pass2"))


def test_delete_user(_set_db_env: Path) -> None:
    cmd_create(_ns(email="todelete@test.com", password="pass"))
    cmd_delete(_ns(email="todelete@test.com"))
    conn = get_connection(_set_db_env)
    user = get_user_by_email(conn, "todelete@test.com")
    conn.close()
    assert user is None


def test_delete_nonexistent_user(_set_db_env: Path) -> None:
    with pytest.raises(SystemExit):
        cmd_delete(_ns(email="ghost@test.com"))


def test_change_password(_set_db_env: Path) -> None:
    cmd_create(_ns(email="pwchange@test.com", password="oldpass"))
    cmd_change_password(_ns(email="pwchange@test.com", password="newpass"))
    conn = get_connection(_set_db_env)
    user = get_user_by_email(conn, "pwchange@test.com")
    conn.close()
    assert user is not None
    assert verify_password("newpass", str(user["password_hash"]))
    assert not verify_password("oldpass", str(user["password_hash"]))


def test_change_password_nonexistent(_set_db_env: Path) -> None:
    with pytest.raises(SystemExit):
        cmd_change_password(_ns(email="nobody@test.com", password="x"))


def test_list_users(_set_db_env: Path, capsys: pytest.CaptureFixture[str]) -> None:
    cmd_create(_ns(email="a@test.com", password="p"))
    cmd_create(_ns(email="b@test.com", password="p"))
    cmd_list(_ns())
    output = capsys.readouterr().out
    assert "a@test.com" in output
    assert "b@test.com" in output


def test_assign_snapshots(_set_db_env: Path) -> None:
    db_path = _set_db_env
    # Create a user
    cmd_create(_ns(email="owner@test.com", password="p"))

    # Insert unowned snapshots directly
    conn = get_connection(db_path)
    conn.execute(
        "INSERT INTO snapshots (snapshot_date, cash_value, market_value, bond_value, "
        "spending_distribution, years_to_simulate) VALUES (?, ?, ?, ?, ?, ?)",
        ("2025-01-01", 100000, 500000, 50000, '{"dist_type":"flat","value":0}', 30),
    )
    conn.execute(
        "INSERT INTO snapshots (snapshot_date, cash_value, market_value, bond_value, "
        "spending_distribution, years_to_simulate) VALUES (?, ?, ?, ?, ?, ?)",
        ("2025-02-01", 200000, 600000, 60000, '{"dist_type":"flat","value":0}', 25),
    )
    conn.commit()

    # Verify they have no user_id
    rows = conn.execute("SELECT user_id FROM snapshots WHERE user_id IS NULL").fetchall()
    assert len(rows) == 2
    conn.close()

    # Assign
    cmd_assign_snapshots(_ns(email="owner@test.com"))

    # Verify assignment
    conn = get_connection(db_path)
    user = get_user_by_email(conn, "owner@test.com")
    assert user is not None
    rows = conn.execute(
        "SELECT user_id FROM snapshots WHERE user_id = ?", (user["id"],)
    ).fetchall()
    assert len(rows) == 2
    unowned = conn.execute("SELECT user_id FROM snapshots WHERE user_id IS NULL").fetchall()
    assert len(unowned) == 0
    conn.close()
