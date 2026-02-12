# Development Standards

## Package Management
- All tools, scripts, and commands must be run through `uv` (e.g., `uv run pytest`, `uv run ruff`).
- Never install tools globally or use `pip` directly.
- Add new dependencies to `pyproject.toml` and run `uv sync --all-extras`.

## Type Hints
- Type hints are required on all function signatures (parameters and return types).
- Use modern Python typing syntax (e.g., `str | None` instead of `Optional[str]`).

## Type Checking
- All code must pass `ty` with zero errors before each commit.
- Run: `uv run ty check`

## Code Formatting
- All code must be formatted with `ruff format` before each commit.
- Run: `uv run ruff format .`

## Linting
- All code must pass `ruff check` with zero errors before each commit.
- Run: `uv run ruff check .`
- Fix auto-fixable issues: `uv run ruff check --fix .`

## Pre-Commit Workflow
Before every commit, run:
```bash
uv run ruff format . && uv run ruff check . && uv run ty check
```
All three must pass cleanly.
