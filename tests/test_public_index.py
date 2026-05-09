"""Server-side tests for the public (unauthenticated) landing page at GET /."""

import json
import re

from fastapi.testclient import TestClient

import vibe_carlo.app as app_module
from vibe_carlo.app import app
from vibe_carlo.simulation.models import load_historical_data


def _public_client() -> TestClient:
    """TestClient with NO session cookie. Lifespan-managed."""
    return TestClient(app)


def _extract_inlined_data(html: str) -> list[list[float]]:
    """Pull the contents of <script id="historical-data">…</script> and parse JSON."""
    m = re.search(
        r'<script[^>]*id="historical-data"[^>]*>(.*?)</script>',
        html,
        re.DOTALL,
    )
    assert m is not None, "expected <script id='historical-data'> in page"
    return json.loads(m.group(1))


# ---------------------------------------------------------------------------
# Server bifurcation — happy path
# ---------------------------------------------------------------------------


def test_get_root_unauthenticated_returns_200() -> None:
    with _public_client() as c:
        r = c.get("/")
    assert r.status_code == 200
    # Marker unique to public_index.html: the inlined historical-data script.
    assert 'id="historical-data"' in r.text


def test_get_root_unauthenticated_does_not_redirect() -> None:
    with _public_client() as c:
        r = c.get("/", follow_redirects=False)
    assert r.status_code == 200
    assert "location" not in {k.lower() for k in r.headers.keys()}


def test_get_root_authenticated_unchanged(auth_client: TestClient) -> None:
    r = auth_client.get("/")
    assert r.status_code == 200
    # Markers unique to the authenticated index.html.
    assert 'id="snapshot-modal"' in r.text
    assert 'hx-post="/simulate"' in r.text
    # And the public page's inlined data is NOT present.
    assert 'id="historical-data"' not in r.text


# ---------------------------------------------------------------------------
# Inlined historical data — correctness
# ---------------------------------------------------------------------------


def test_inlined_historical_data_matches_csv() -> None:
    with _public_client() as c:
        r = c.get("/")
    inlined = _extract_inlined_data(r.text)
    expected = load_historical_data().tolist()
    assert inlined == expected


def test_inlined_historical_data_shape() -> None:
    with _public_client() as c:
        r = c.get("/")
    inlined = _extract_inlined_data(r.text)
    expected = load_historical_data()
    assert len(inlined) == len(expected)
    for row in inlined:
        assert len(row) == 3
        assert all(isinstance(v, (int, float)) for v in row)


def test_inlined_historical_data_year_count_matches() -> None:
    with _public_client() as c:
        r = c.get("/")
    inlined = _extract_inlined_data(r.text)
    # CSV covers 1928-2024 inclusive = 97 rows
    assert len(inlined) == 97


# ---------------------------------------------------------------------------
# UI element presence/absence
# ---------------------------------------------------------------------------


def test_public_page_has_login_link() -> None:
    with _public_client() as c:
        r = c.get("/")
    assert 'href="/login"' in r.text
    assert re.search(r"login", r.text, re.IGNORECASE) is not None


def test_public_page_has_no_snapshot_ui() -> None:
    with _public_client() as c:
        r = c.get("/")
    assert 'id="snapshot-modal"' not in r.text
    assert 'id="save-snapshot-btn"' not in r.text
    assert 'hx-post="/snapshots/save"' not in r.text


def test_public_page_has_no_advanced_sample_years() -> None:
    with _public_client() as c:
        r = c.get("/")
    assert 'name="sample_years"' not in r.text


def test_public_page_has_no_authenticated_nav() -> None:
    with _public_client() as c:
        r = c.get("/")
    # The public page's nav must not link to authenticated-only sections.
    assert 'href="/snapshots"' not in r.text
    assert 'href="/plans"' not in r.text
    assert 'href="/timeline"' not in r.text
    assert 'href="/statements"' not in r.text


def test_public_page_distribution_picker_present() -> None:
    with _public_client() as c:
        r = c.get("/")
    # Three distribution options must be wired in via the macro.
    assert 'value="flat"' in r.text
    assert 'value="uniform"' in r.text
    assert 'value="truncated_normal"' in r.text


def test_public_page_filing_status_options_present() -> None:
    with _public_client() as c:
        r = c.get("/")
    for option in (
        'value=""',
        'value="single"',
        'value="married_jointly"',
        'value="married_separately"',
        'value="head_of_household"',
    ):
        assert option in r.text


# ---------------------------------------------------------------------------
# Caching: inlined data is computed once at startup, not per request
# ---------------------------------------------------------------------------


def test_inlined_data_is_cached_at_startup() -> None:
    with _public_client() as c:
        c.get("/")
        json_after_first = app_module.historical_data_json
        c.get("/")
        json_after_second = app_module.historical_data_json
    # Same string object identity → not re-serialized per request.
    assert json_after_first is json_after_second
    assert json_after_first != ""
