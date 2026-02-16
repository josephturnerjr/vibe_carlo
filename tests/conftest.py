"""Shared test fixtures for authenticated test clients."""

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
def auth_db() -> Generator[tuple[Path, int]]:
    """Create a temp DB with a test user. Yields (db_path, user_id)."""
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
def auth_client(auth_db: tuple[Path, int]) -> Generator[TestClient]:
    """TestClient with a valid session cookie."""
    db_path, user_id = auth_db
    conn = get_connection(db_path)
    session_id = create_session(conn, user_id)
    conn.close()
    with TestClient(app, cookies={"session_id": session_id}) as c:
        yield c
