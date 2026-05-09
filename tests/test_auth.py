"""Authentication flow tests."""

import tempfile
from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import vibe_carlo.app as app_module
from vibe_carlo.app import app
from vibe_carlo.auth import create_session, create_user
from vibe_carlo.db import get_connection, init_db


@pytest.fixture()
def _fresh_db() -> Generator[tuple[Path, int]]:
    """Create a fresh temp DB with a test user for each test."""
    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / "test.db"
        init_db(db_path)
        conn = get_connection(db_path)
        user_id = create_user(conn, "alice@test.com", "correct-password")
        conn.close()
        original = app_module._db_path
        app_module._db_path = db_path
        yield db_path, user_id
        app_module._db_path = original


def _make_authed_client(db_path: Path, user_id: int) -> TestClient:
    conn = get_connection(db_path)
    session_id = create_session(conn, user_id)
    conn.close()
    return TestClient(app, cookies={"session_id": session_id})


# --- Tests ---


def test_login_page_renders(_fresh_db: tuple[Path, int]) -> None:
    with TestClient(app) as c:
        response = c.get("/login")
        assert response.status_code == 200
        assert "Sign in" in response.text
        assert "email" in response.text
        assert "password" in response.text


def test_successful_login(_fresh_db: tuple[Path, int]) -> None:
    with TestClient(app) as c:
        response = c.post(
            "/login",
            data={"email": "alice@test.com", "password": "correct-password"},
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert response.headers["location"] == "/"
        assert "session_id" in response.cookies


def test_wrong_password(_fresh_db: tuple[Path, int]) -> None:
    with TestClient(app) as c:
        response = c.post(
            "/login",
            data={"email": "alice@test.com", "password": "wrong-password"},
        )
        assert response.status_code == 401
        assert "Invalid email or password" in response.text


def test_unknown_email(_fresh_db: tuple[Path, int]) -> None:
    with TestClient(app) as c:
        response = c.post(
            "/login",
            data={"email": "nobody@test.com", "password": "anything"},
        )
        assert response.status_code == 401
        assert "Invalid email or password" in response.text


def test_unauthenticated_redirect(_fresh_db: tuple[Path, int]) -> None:
    with TestClient(app) as c:
        response = c.get("/snapshots", follow_redirects=False)
        assert response.status_code == 303
        assert response.headers["location"] == "/login"


def test_unauthenticated_root_serves_public_page(_fresh_db: tuple[Path, int]) -> None:
    """GET / for an unauthenticated visitor renders the public landing page,
    not a redirect to /login."""
    with TestClient(app) as c:
        response = c.get("/", follow_redirects=False)
        assert response.status_code == 200
        assert 'id="historical-data"' in response.text


def test_all_protected_routes_redirect(_fresh_db: tuple[Path, int]) -> None:
    with TestClient(app) as c:
        for method, path in [
            ("GET", "/snapshots"),
            ("GET", "/timeline"),
            ("POST", "/simulate"),
            ("POST", "/snapshots/save"),
            ("DELETE", "/snapshots/1"),
        ]:
            response = getattr(c, method.lower())(path, follow_redirects=False)
            # Should redirect to login or return HX-Redirect
            assert response.status_code == 303, f"{method} {path} didn't redirect"
            assert response.headers["location"] == "/login"


def test_logout_clears_session(_fresh_db: tuple[Path, int]) -> None:
    db_path, user_id = _fresh_db
    client = _make_authed_client(db_path, user_id)

    # Verify we're authenticated
    response = client.get("/", follow_redirects=False)
    assert response.status_code == 200

    # Logout
    response = client.post("/logout", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/login"

    # After logout, protected routes should redirect to login
    # Need fresh client without cookies
    with TestClient(app) as c:
        response = c.get("/snapshots", follow_redirects=False)
        assert response.status_code == 303


def test_expired_session_rejected(_fresh_db: tuple[Path, int]) -> None:
    db_path, user_id = _fresh_db
    conn = get_connection(db_path)
    # Create a session that's already expired
    import secrets

    token = secrets.token_urlsafe(32)
    conn.execute(
        "INSERT INTO sessions (id, user_id, expires_at) VALUES (?, ?, ?)",
        (token, user_id, "2020-01-01 00:00:00"),
    )
    conn.commit()
    conn.close()

    with TestClient(app, cookies={"session_id": token}) as c:
        response = c.get("/snapshots", follow_redirects=False)
        assert response.status_code == 303
        assert response.headers["location"] == "/login"


def test_invalid_cookie_rejected(_fresh_db: tuple[Path, int]) -> None:
    with TestClient(app, cookies={"session_id": "garbage-token-xyz"}) as c:
        response = c.get("/snapshots", follow_redirects=False)
        assert response.status_code == 303
        assert response.headers["location"] == "/login"


def test_already_logged_in_login_redirects_home(_fresh_db: tuple[Path, int]) -> None:
    db_path, user_id = _fresh_db
    client = _make_authed_client(db_path, user_id)
    response = client.get("/login", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/"


def test_case_insensitive_email_login(_fresh_db: tuple[Path, int]) -> None:
    with TestClient(app) as c:
        response = c.post(
            "/login",
            data={"email": "Alice@Test.Com", "password": "correct-password"},
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert "session_id" in response.cookies
