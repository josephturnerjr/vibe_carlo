# Asset Statements - Architecture

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────┐
│                        Browser                          │
│                                                         │
│  statements.html ◄──── base.html (+ nav link)          │
│  (list page)           ┌─────────────────────────┐      │
│                        │ statement_edit.html      │      │
│                        │  ┌───────────────────┐   │      │
│                        │  │ Client-side JS    │   │      │
│                        │  │ - add/remove rows │   │      │
│                        │  │ - recalculate     │   │      │
│                        │  │ - format values   │   │      │
│                        │  └───────────────────┘   │      │
│                        └─────────────────────────┘      │
└────────────────┬────────────────────────────────────────┘
                 │  HTTP (HTMX + standard forms)
                 ▼
┌─────────────────────────────────────────────────────────┐
│                     app.py (routes)                      │
│                                                         │
│  GET  /statements          → list page                  │
│  POST /statements          → create (303 redirect)      │
│  GET  /statements/{id}     → edit page                  │
│  POST /statements/{id}     → bulk save (date+accounts)  │
│  DELETE /statements/{id}   → delete (HTMX row removal)  │
│                                                         │
│  + Jinja2 filter: {{ value | accounting }}               │
└────────────────┬────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────┐
│               statements.py (CRUD layer)                │
│                                                         │
│  Statements: create, get, list, update_date, delete     │
│  Accounts:   create, get, list, update, delete          │
│  Utility:    get_latest_statement                       │
│                                                         │
│  • User ownership enforced on all operations            │
│  • Value sign enforced: +abs for assets, -abs for liab  │
│  • order_position auto-assigned                         │
│  • Manual cascade delete (accounts then statement)      │
└────────────────┬────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────┐
│                    SQLite (db.py)                        │
│                                                         │
│  ┌─────────────────┐      ┌──────────────────────┐      │
│  │  statements     │      │  statement_accounts  │      │
│  │─────────────────│      │──────────────────────│      │
│  │ id (PK)         │◄────┐│ id (PK)              │      │
│  │ user_id (FK)    │     ││ statement_id (FK)    │      │
│  │ statement_date  │     │└──────────────────────│      │
│  │ created_at      │     │ name                  │      │
│  │ updated_at      │     │ account_type          │      │
│  └─────────────────┘     │ value                 │      │
│                          │ order_position        │      │
│                          │ created_at            │      │
│                          │ updated_at            │      │
│                          └──────────────────────┘      │
│                                                         │
│  ★ NEW TABLES (no changes to existing tables)           │
└─────────────────────────────────────────────────────────┘
```

## How It Integrates with Existing Code

### Modified Files
| File | Change |
|------|--------|
| `src/vibe_carlo/db.py` | Add 2 `CREATE TABLE` statements to `init_db()` |
| `src/vibe_carlo/schemas.py` | Add `AccountType` enum, `StatementRow`, `StatementAccountRow` models |
| `src/vibe_carlo/app.py` | Add 5 route handlers, import `statements.py`, register accounting filter |
| `src/vibe_carlo/templates/base.html` | Add "Statements" nav link (desktop + mobile) |

### New Files
| File | Purpose |
|------|---------|
| `src/vibe_carlo/statements.py` | CRUD functions (follows `plans.py` pattern) |
| `src/vibe_carlo/templates/statements.html` | List page (follows `plans.html` pattern) |
| `src/vibe_carlo/templates/statement_edit.html` | Edit page with client-side JS for add/remove/recalculate |
| `tests/test_statements.py` | CRUD unit tests |
| `tests/test_statement_api.py` | API integration tests |

## New Infrastructure

**None.** This feature uses only existing infrastructure:
- SQLite (existing DB)
- FastAPI routes (existing pattern)
- Jinja2 templates (existing pattern)
- HTMX for delete from list (existing pattern)
- Vanilla JavaScript for client-side DOM manipulation (existing pattern)

The only new element is a small amount of client-side JavaScript in the
edit page for adding/removing account rows and recalculating subtotals.
This is simpler than the existing `distribution_picker.js`.

## Key Design Decisions

1. **Client-side add/remove, server-side save.** Account rows are
   added/removed in the DOM via JavaScript. The Save button POSTs the
   complete form state. This keeps the "manual save" semantic clean and
   avoids per-field server round-trips.

2. **Bulk save via form arrays.** The save endpoint receives parallel
   arrays (`account_ids[]`, `account_names[]`, `account_types[]`,
   `account_values[]`) and reconciles against the DB (create new, update
   existing, delete removed).

3. **No partial templates needed.** Since account add/remove is
   client-side, no HTMX partials are needed for the edit page. The only
   HTMX interaction is delete-from-list on the list page.

4. **Accounting format as Jinja2 filter.** `{{ value | accounting }}`
   for server-rendered values. JavaScript handles formatting on the
   edit page.
