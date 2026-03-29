# Epic: Asset Statements

## Overview
This feature offers users a tool to create asset statements.
These statements are tracked over time, and capture a complete picture
of net worth. By creating these statements periodically
(e.g. once a quarter) a user can track their detailed financial history
and better plan the future.

## Concept
An asset statement consists of a start and end date, a list of assets,
and a list of liabilities.

### Assets and Liabilities
On the statement, a user can list all of their assets
and liabilities (debts).

These assets and debts represent anything the user considers material financial
value, and they loosely correspond to "accounts" in finance terms. Some examples may include:

* Their home
* Their car
* Their 401k
* Their checking account
* Their credit card
* etc

Each account must include at a minimum a name and a current value in
dollars; the value is positive for assets and negative for debts. When creating an
account, the user should be able to specify if it is an asset or a
liability; if it is an asset, the value should be pinned positive, and
if it is a liability it should be pinned negative.

Assets and liabilities should be displayed separately: all assets first,
then liabilities.

## Other requirements

A user should be able to see a list of all statements, ordered by end date.

A user should be able to create a new statement.

A user should be able to open and edit any saved statement. The editor can use
the same format as the input tool.

A user should be able to delete any saved statement.

Statements should be saved automatically as data is entered, so no data
is lost. This should be accomplished by a periodic (timer) save. There
should also be a save button that is enabled when there are unsaved
changes. 

