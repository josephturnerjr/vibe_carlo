# Phase 2: Saved Snapshots — Architecture

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│  Browser                                                            │
│                                                                     │
│  ┌──────────────────────┐     ┌──────────────────────────────────┐  │
│  │  / (index.html)      │     │  /snapshots (snapshots.html)     │  │
│  │                      │     │                                  │  │
│  │  Simulation form     │ ←── │  Table of all snapshots          │  │
│  │  + Save Snapshot UI  │     │  [Load] [Delete] per row         │  │
│  │  + Update Snapshot   │     │  Distribution mini-charts        │  │
│  │    (when loaded)     │     │                                  │  │
│  └──────┬───────────────┘     └──────┬────────────┬──────────────┘  │
│         │ HTMX                       │ nav link   │ HTMX            │
└─────────┼────────────────────────────┼────────────┼─────────────────┘
          │                            │            │
          ▼                            ▼            ▼
┌─────────────────────────────────────────────────────────────────────┐
│  FastAPI (app.py)                                                   │
│                                                                     │
│  Existing:                          NEW:                            │
│  GET  /           ──────────┐       GET  /snapshots                 │
│  POST /simulate             │       POST /snapshots/save            │
│                             │       POST /snapshots/{id}/update     │
│                     modified│       DELETE /snapshots/{id}          │
│                     to load │       GET / ?snapshot_id=N             │
│                     snapshot│                                       │
│                     from DB │                                       │
└─────────────────────────────┼───────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│  db.py                                                              │
│  - get_db_path() → ~/.vibe_carlo/snapshots.db (or VIBE_CARLO_DB)   │
│  - init_db() — CREATE TABLE IF NOT EXISTS                           │
│  - get_connection() — returns sqlite3 connection                    │
│                                                                     │
│  snapshots.py                                                       │
│  - create_snapshot(params) → id                                     │
│  - get_snapshot(id) → dict | None                                   │
│  - list_snapshots() → list[dict]                                    │
│  - update_snapshot(id, params)                                      │
│  - delete_snapshot(id) → bool                                       │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│  SQLite: ~/.vibe_carlo/snapshots.db                                 │
│                                                                     │
│  snapshots table:                                                   │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │ id INTEGER PRIMARY KEY AUTOINCREMENT                          │ │
│  │ name TEXT                          -- optional user label      │ │
│  │ snapshot_date TEXT NOT NULL         -- YYYY-MM-DD              │ │
│  │ cash_value REAL NOT NULL                                      │ │
│  │ market_value REAL NOT NULL                                    │ │
│  │ bond_value REAL NOT NULL                                      │ │
│  │ earnings REAL NOT NULL DEFAULT 0                              │ │
│  │ spending_distribution TEXT NOT NULL -- JSON blob               │ │
│  │ years_to_simulate INTEGER NOT NULL                            │ │
│  │ sample_years INTEGER                                          │ │
│  │ filing_status TEXT                                            │ │
│  │ created_at TEXT DEFAULT (datetime('now'))                      │ │
│  │ updated_at TEXT DEFAULT (datetime('now'))                      │ │
│  └────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────┘
```

## New Infrastructure

- **SQLite database** — Python built-in `sqlite3`, zero new dependencies
- **2 new Python modules**: `db.py` (connection/init), `snapshots.py` (CRUD)
- **1 new Pydantic model**: `SnapshotRow` in `schemas.py`
- **1 new template**: `templates/snapshots.html` (table page)
- **No new JS dependencies** — reuses existing `distribution_picker.js` patterns for mini-chart rendering

## Modified Files

- `app.py` — new snapshot routes + modified `GET /` to accept `?snapshot_id=N`
- `schemas.py` — added `SnapshotRow` model
- `base.html` — added nav links (Simulation / Snapshots) in header
- `index.html` — added save/update snapshot UI section with HTMX integration

## DB File Location

- **Default**: `~/.vibe_carlo/snapshots.db` (persists across app restarts)
- **Override**: `VIBE_CARLO_DB` environment variable
- **Tests**: use `tmp_path` fixture for isolated test DBs

## UI Flows

### Saving a new snapshot (on `/`)
1. User fills out simulation parameters
2. Below the form, enters optional name and required date in the "Save Snapshot" section
3. Clicks "Save Snapshot" — HTMX collects form values + snapshot fields, POSTs to `/snapshots/save`
4. Server validates (reuses `SimulationInput` validation), saves to DB
5. Inline feedback: success or error message

### Viewing snapshots (on `/snapshots`)
- Table with columns: Name, Date, Cash, Market, Bonds, Earnings, Spending, Years, Filing Status, Actions
- Spending column: small inline Plotly charts for distributions, or `Fixed($X)` text for flat
- Actions: "Load" link + "Delete" button per row
- Sorted by snapshot_date descending

### Loading a snapshot
1. Click "Load" → navigates to `/?snapshot_id=N`
2. Server fetches snapshot, passes typed `SnapshotRow` to template
3. All form fields pre-filled from snapshot data
4. "Update Snapshot" button appears alongside "Save Snapshot"

### Updating a snapshot
1. User modifies parameters after loading
2. Clicks "Update Snapshot" → POSTs to `/snapshots/{id}/update`
3. Server validates and updates DB row

### Deleting a snapshot
1. Click "Delete" on table row → `hx-delete="/snapshots/{id}"`
2. Browser confirms with native dialog
3. Server deletes row, returns empty HTML
4. HTMX removes the `<tr>` element
