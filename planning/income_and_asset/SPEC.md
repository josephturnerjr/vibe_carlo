# Asset Statements - Feature Specification

## Overview
Asset Statements allow users to create point-in-time net worth snapshots.
Each statement captures a complete picture of assets and liabilities on a
given date. By creating statements periodically (e.g. quarterly), users
can track their detailed financial history.

## Data Model

### Statement
- **Date**: A single date representing when the snapshot was taken.
- **Accounts**: A list of accounts, each classified as either an asset or
  a liability.

### Account
- **Name**: A free-text label (e.g. "House", "401k", "Visa Card").
- **Type**: Either "asset" or "liability".
- **Value**: A positive dollar amount entered by the user. The system
  stores the value as positive for assets and negative for liabilities.
  The user always enters a positive number.

## Display

### Statement Editor
- The statement date is displayed and editable at the top.
- Accounts are displayed in two sections: **Assets** first, then
  **Liabilities**.
- Each section displays its accounts in a table or list with name and
  value columns.
- Each section shows a **subtotal** (sum of values in that section).
- A **net worth** total is displayed (assets subtotal + liabilities
  subtotal, where liabilities are negative).
- All dollar values are displayed in **accounting format** (USD):
  - Positive values: `$1,234.56`
  - Negative values: `($1,234.56)`
  - Zero: `$0.00`

### Statement List
- Displays all statements ordered by date (most recent first).
- Each row shows the date and net worth.
- Users can click a statement to open it for editing.
- Users can delete a statement from the list.

## User Flows

### Create New Statement
1. User clicks "New Statement" from the statement list page.
2. User is presented with a choice:
   - **Copy from latest**: Pre-populates accounts from the most recent
     statement (by date). The user can then update values, add, or remove
     accounts. The date defaults to today.
   - **Start blank**: Opens an empty statement with no accounts. The date
     defaults to today.
3. If no prior statements exist, the choice is skipped and a blank
   statement is opened.

### Edit Statement
1. User clicks a statement from the list to open it.
2. The editor displays the statement date and all accounts (assets then
   liabilities).
3. User can:
   - Change the date.
   - Edit any account's name or value.
   - Change an account's type (asset/liability), which flips the sign of
     its stored value.
   - Remove an account.
   - Add a new account (specifying name, type, and value).
4. User clicks **Save** to persist changes. A save button is always
   visible; it is visually distinguished when there are unsaved changes.

### Delete Statement
1. User clicks a delete button on a statement in the list.
2. The statement and all its accounts are deleted.
3. No confirmation dialog is required (consistent with existing app
   patterns).

## Constraints
- All values are in USD.
- Statements are scoped to the authenticated user (consistent with
  existing app patterns).
- This feature is independent of the existing Snapshots feature.
- No auto-save; all saves are manual via an explicit save button.
