# Phase 2: Saved Snapshots — Implementation Steps & Test Plan

## Implementation Steps

### Step 1: Database layer (`src/vibe_carlo/db.py`)
- `get_db_path()` — resolves DB path from `VIBE_CARLO_DB` env var or `~/.vibe_carlo/snapshots.db`
- `init_db(db_path)` — creates parent directory + `snapshots` table if not exists
- `get_connection(db_path)` — returns `sqlite3.Connection` with `row_factory = sqlite3.Row`

### Step 2: Snapshot CRUD (`src/vibe_carlo/snapshots.py`)
- `create_snapshot(conn, name, date, params: SimulationInput) → int`
- `get_snapshot(conn, id) → dict | None`
- `list_snapshots(conn) → list[dict]` — ordered by `snapshot_date DESC, id DESC`
- `update_snapshot(conn, id, name, date, params: SimulationInput) → bool`
- `delete_snapshot(conn, id) → bool`
- Distribution serialized via `json.dumps(dist.model_dump())`, deserialized via `TypeAdapter`

### Step 3: Schema additions (`src/vibe_carlo/schemas.py`)
- `SnapshotRow` Pydantic model with all DB columns as typed fields

### Step 4: Routes (`src/vibe_carlo/app.py`)
- `_parse_form_params()` — extracted helper for form → `SimulationInput` conversion
- `_snapshot_to_row()` — converts raw DB dict → typed `SnapshotRow`
- `init_db()` called in `lifespan`
- `GET /` — accepts optional `snapshot_id` query param, passes `SnapshotRow` to template
- `GET /snapshots` — renders snapshot table
- `POST /snapshots/save` — validates + creates snapshot, returns HTMX feedback
- `POST /snapshots/{id}/update` — validates + updates, returns HTMX feedback
- `DELETE /snapshots/{id}` — deletes, returns empty HTML for HTMX row removal

### Step 5: Templates
- `base.html` — added nav bar with "Simulation" and "Snapshots" links
- `index.html` — form values pre-filled from `snapshot` context; save/update section below form; JS `htmx:configRequest` handler collects form + snapshot fields
- `snapshots.html` — table with inline Plotly mini-charts for distribution columns

## Test Plan

### `tests/test_snapshots.py` — CRUD unit tests (14 tests)

**Happy path:**
1. `test_create_and_get_snapshot` — create with flat distribution, retrieve by ID, verify all fields
2. `test_create_snapshot_uniform_distribution` — verify JSON round-trip for uniform dist
3. `test_create_snapshot_truncated_normal` — verify JSON round-trip for truncated normal dist
4. `test_create_snapshot_with_name` — optional name stored and returned
5. `test_create_snapshot_without_name` — name is None when omitted
6. `test_list_snapshots_ordered_by_date` — 3 snapshots with different dates, verify sort order
7. `test_update_snapshot` — create, update values + date, verify changes persisted
8. `test_delete_snapshot` — create, delete, verify get returns None

**Edge cases:**
9. `test_get_nonexistent_snapshot` — returns None
10. `test_delete_nonexistent_snapshot` — returns False
11. `test_update_nonexistent_snapshot` — returns False
12. `test_multiple_snapshots_same_date` — both stored and returned
13. `test_snapshot_with_all_optional_fields_none` — name=None, filing_status=None
14. `test_snapshot_preserves_filing_status` — all 4 filing statuses round-trip correctly

### `tests/test_snapshot_api.py` — API integration tests (13 tests)

**Happy path:**
15. `test_snapshots_page_renders` — GET /snapshots returns 200
16. `test_save_snapshot_from_form` — POST /snapshots/save with valid form data
17. `test_load_snapshot_into_form` — GET /?snapshot_id=N pre-fills form
18. `test_update_snapshot_via_api` — POST /snapshots/{id}/update modifies record
19. `test_delete_snapshot_via_api` — DELETE /snapshots/{id} removes row
20. `test_snapshot_round_trip` — save → list → load → update → verify

**Edge cases / validation:**
21. `test_save_snapshot_missing_date` — returns 422
22. `test_save_snapshot_zero_portfolio` — returns 422
23. `test_load_nonexistent_snapshot` — returns 404
24. `test_delete_nonexistent_snapshot` — returns 404
25. `test_update_nonexistent_snapshot` — returns 404
26. `test_save_snapshot_each_distribution_type` — flat, uniform, truncated_normal all save
27. `test_snapshots_page_empty` — shows empty state message
