# Asset Statements - Test Plan

## Unit Tests (`tests/test_statements.py`)

Tests the CRUD layer directly against the database. Uses a
function-scoped `db` fixture for isolation.

### Helper

```python
def _make_account_kwargs(
    name: str = "Checking",
    account_type: str = "asset",
    value: float = 10000.0,
) -> dict[str, object]:
```

### Happy Path

| Test | Description |
|------|-------------|
| `test_create_and_get_statement` | Create a statement, get it back, verify fields |
| `test_list_statements_ordered_by_date` | Create 3 statements with different dates, verify order is most-recent-first |
| `test_list_statements_with_net_worth` | Create statement with assets and liabilities, verify net_worth = sum of all values |
| `test_update_statement_date` | Update date, verify it changed |
| `test_delete_statement` | Delete, verify get returns None |
| `test_create_account` | Create account, verify fields and auto-assigned order_position |
| `test_list_accounts_ordered` | Create mixed assets/liabilities, verify assets come first, then by order_position |
| `test_update_account` | Update name and value, verify changes |
| `test_delete_account` | Delete account, verify it's gone |
| `test_get_latest_statement` | Create multiple statements, verify returns most recent by date |

### Value Sign Enforcement

| Test | Description |
|------|-------------|
| `test_create_account_asset_positive` | Create asset with value 5000, verify stored as +5000 |
| `test_create_account_liability_negative` | Create liability with value 5000, verify stored as -5000 |
| `test_update_account_type_change_flips_sign` | Change asset to liability, verify sign flips from + to - |
| `test_update_account_liability_to_asset` | Change liability to asset, verify sign flips from - to + |

### Edge Cases

| Test | Description |
|------|-------------|
| `test_get_nonexistent_statement` | get_statement with bad ID returns None |
| `test_delete_nonexistent_statement` | delete_statement with bad ID returns False |
| `test_create_account_wrong_user` | create_account on another user's statement returns None |
| `test_get_latest_statement_none` | get_latest_statement with no statements returns None |
| `test_list_statements_empty` | list_statements with no data returns [] |
| `test_list_accounts_empty` | list_accounts on empty statement returns [] |
| `test_net_worth_zero_no_accounts` | Statement with no accounts has net_worth = 0 |

### Cascade & Isolation

| Test | Description |
|------|-------------|
| `test_delete_statement_cascades` | Delete statement, verify all its accounts are gone |
| `test_cross_user_isolation` | User B cannot get/list/update/delete User A's statements or accounts |

## API Integration Tests (`tests/test_statement_api.py`)

Tests HTTP endpoints end-to-end. Uses module-scoped `client` fixture
with authenticated session.

### Helper

```python
def _statement_form_data(
    date: str = "2025-06-15",
    account_ids: list[str] | None = None,
    account_names: list[str] | None = None,
    account_types: list[str] | None = None,
    account_values: list[str] | None = None,
) -> dict[str, str | list[str]]:
```

### Page Rendering

| Test | Description |
|------|-------------|
| `test_statements_page_renders` | GET /statements returns 200, contains "Asset Statements" |
| `test_statements_page_empty` | List page with no data shows empty state |
| `test_statement_edit_page_renders` | GET /statements/{id} returns 200 |

### Create Flow

| Test | Description |
|------|-------------|
| `test_create_statement_blank` | POST /statements with copy_from_latest=false, verify 303 redirect, statement exists in DB |
| `test_create_statement_copy_from_latest` | POST with copy_from_latest=true, verify new statement has same accounts as latest |
| `test_create_statement_copy_no_prior` | POST with copy_from_latest=true but no prior statements, verify still creates blank statement |
| `test_create_statement_date_required` | POST with empty date returns 422 |

### Save Flow

| Test | Description |
|------|-------------|
| `test_save_statement_update_date` | POST /statements/{id} with new date, verify date changed in DB |
| `test_save_statement_add_accounts` | POST with new accounts (empty IDs), verify accounts created |
| `test_save_statement_update_accounts` | POST with existing account IDs and new values, verify updated |
| `test_save_statement_remove_accounts` | POST without a previously existing account ID, verify it's deleted |
| `test_save_statement_full_reconciliation` | Add some, update some, remove some in one save, verify all changes applied |

### Delete Flow

| Test | Description |
|------|-------------|
| `test_delete_statement` | DELETE /statements/{id} returns 200, verify gone from DB |
| `test_delete_nonexistent_statement` | DELETE /statements/99999 returns 404 |

### Display

| Test | Description |
|------|-------------|
| `test_net_worth_accounting_format` | List page shows net worth in accounting format (check for $ and comma in HTML) |
| `test_edit_page_shows_accounts` | Edit page contains account names and values |
| `test_edit_page_sections` | Edit page has "Assets" and "Liabilities" section headers |

### Not Found

| Test | Description |
|------|-------------|
| `test_edit_nonexistent_statement` | GET /statements/99999 returns 404 |
| `test_save_nonexistent_statement` | POST /statements/99999 returns 404 |
