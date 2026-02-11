# Development Standards

## Type Hints
- Type hints are required on all function signatures (parameters and return types).
- Use modern Python typing syntax (e.g., `str | None` instead of `Optional[str]`).

## Type Checking
- All code must pass `ty` with zero errors before each commit.
- Run: `ty check`

## Code Formatting
- All code must be formatted with `ruff format` before each commit.
- Run: `ruff format .`

## Linting
- All code must pass `ruff check` with zero errors before each commit.
- Run: `ruff check .`
- Fix auto-fixable issues: `ruff check --fix .`

## Pre-Commit Workflow
Before every commit, run:
```bash
ruff format . && ruff check . && ty check
```
All three must pass cleanly.
