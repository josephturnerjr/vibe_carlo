# Asset Statements - Implementation Plan

## Implementation Sequence

### Step 1: Database Schema (`src/vibe_carlo/db.py`)

Add two table DDL constants and register them in `init_db()`.

```sql
CREATE TABLE IF NOT EXISTS statements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    statement_date TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS statement_accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    statement_id INTEGER NOT NULL REFERENCES statements(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    account_type TEXT NOT NULL,
    value REAL NOT NULL,
    order_position INTEGER NOT NULL,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);
```

Add `conn.execute(...)` calls in `init_db()` after the existing table
creation lines.

### Step 2: Pydantic Models (`src/vibe_carlo/schemas.py`)

Add:

```python
class AccountType(StrEnum):
    asset = "asset"
    liability = "liability"

class StatementRow(BaseModel):
    id: int
    user_id: int
    statement_date: str
    net_worth: float = 0.0

class StatementAccountRow(BaseModel):
    id: int
    statement_id: int
    name: str
    account_type: AccountType
    value: float
    order_position: int
```

### Step 3: CRUD Layer (`src/vibe_carlo/statements.py` — new file)

Follow `plans.py` parent-child pattern exactly.

**Statement functions:**

| Function | Signature | Returns |
|----------|-----------|---------|
| `create_statement` | `(conn, user_id, statement_date)` | `int` (ID) |
| `get_statement` | `(conn, statement_id, user_id)` | `dict \| None` |
| `list_statements` | `(conn, user_id)` | `list[dict]` with `net_worth` via LEFT JOIN + SUM |
| `update_statement_date` | `(conn, statement_id, user_id, statement_date)` | `bool` |
| `delete_statement` | `(conn, statement_id, user_id)` | `bool` (manual cascade: delete accounts first) |
| `get_latest_statement` | `(conn, user_id)` | `dict \| None` (most recent by date) |

**Account functions:**

| Function | Signature | Returns |
|----------|-----------|---------|
| `create_account` | `(conn, statement_id, user_id, *, name, account_type, value)` | `int \| None` |
| `get_account` | `(conn, account_id, user_id)` | `dict \| None` |
| `list_accounts` | `(conn, statement_id, user_id)` | `list[dict]` ordered by type then position |
| `update_account` | `(conn, account_id, user_id, *, name, account_type, value)` | `bool` |
| `delete_account` | `(conn, account_id, user_id)` | `bool` |

**Value sign enforcement** in `create_account` and `update_account`:
```python
stored_value = abs(value) if account_type == "asset" else -abs(value)
```

**Ownership checks:**
- Statement ops: `WHERE id = ? AND user_id = ?`
- Account ops: `WHERE id = ? AND statement_id IN (SELECT id FROM statements WHERE user_id = ?)`

### Step 4: Unit Tests (`tests/test_statements.py` — new file)

Write and verify all CRUD tests pass before proceeding to UI.
See TEST.md for full test list.

### Step 5: Navigation (`src/vibe_carlo/templates/base.html`)

Add "Statements" link to both desktop and mobile nav sections, between
"Plans" and "Timeline".

### Step 6: List Page (`src/vibe_carlo/templates/statements.html` — new file)

Follows `plans.html` pattern:
- Header: "Asset Statements"
- Create buttons:
  - If statements exist: "Copy from Latest" + "Start Blank" (two forms)
  - If no statements: single "New Statement" button
  - Both POST to `/statements` with `statement_date=today` and
    `copy_from_latest=true/false`
- Table columns: Date | Net Worth | Actions (Edit link, Delete button)
- Net worth formatted with `{{ stmt.net_worth | accounting }}`
- Delete: `hx-delete`, `hx-target="closest tr"`, `hx-swap="outerHTML"`
- Empty state: "No statements yet."

### Step 7: Edit Page (`src/vibe_carlo/templates/statement_edit.html` — new file)

Layout:
- Back link to `/statements`
- Form (`id="statement-form"`):
  - Date input
  - **Assets section**: header + "Add Asset" button + account rows table + subtotal
  - **Liabilities section**: header + "Add Liability" button + account rows table + subtotal
  - **Net Worth** display
  - Save button with unsaved-changes indicator
- Each account row contains:
  - Hidden `<input name="account_ids" value="{id or empty}">`
  - `<input name="account_names" value="{name}">`
  - Hidden `<input name="account_types" value="asset|liability">`
  - `<input name="account_values" value="{abs(value)}">`
  - Remove button (JS removes the row)

**Client-side JavaScript:**
- `addAccount(type)`: Appends a new row to the correct section
- `removeAccount(btn)`: Removes the closest `<tr>`, recalculates
- `recalculate()`: Sums values per section, updates subtotals and net worth
- `formatAccounting(val)`: Returns `$1,234.56` or `($1,234.56)`
- Input event listeners on value fields trigger `recalculate()`
- Track dirty state for save button visual indicator

### Step 8: Route Handlers (`src/vibe_carlo/app.py`)

Add imports, register accounting Jinja2 filter, and add 5 routes:

```python
def _format_accounting(value: float) -> str:
    if value < 0:
        return f"(${abs(value):,.2f})"
    return f"${value:,.2f}"

templates.env.filters["accounting"] = _format_accounting
```

**Routes:**

1. **GET /statements** — List page. Calls `list_statements()`, renders
   `statements.html`.

2. **POST /statements** — Create. Validates date (422 if empty). If
   `copy_from_latest`, finds latest statement and copies its accounts.
   Redirects 303 to `/statements/{id}`.

3. **GET /statements/{id}** — Edit page. Calls `get_statement()` and
   `list_accounts()`. 404 if not found. Renders `statement_edit.html`
   with accounts split into assets and liabilities lists.

4. **POST /statements/{id}** — Bulk save. Receives parallel form arrays.
   Updates date. Reconciles accounts:
   - Accounts with existing IDs: update
   - Accounts with empty IDs: create
   - Existing DB accounts not in form: delete
   Returns success/error HTML fragment.

5. **DELETE /statements/{id}** — Delete. Calls `delete_statement()`.
   404 if not found. Returns empty string.

### Step 9: API Tests (`tests/test_statement_api.py` — new file)

Write and verify all API tests pass. See TEST.md for full test list.

### Step 10: Pre-commit Checks

```bash
uv run ruff format . && uv run ruff check . && uv run ty check && uv run pytest
```
