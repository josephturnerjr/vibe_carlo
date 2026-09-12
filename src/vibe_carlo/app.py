import asyncio
import json
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt
from fastapi import FastAPI, Form, Query, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError

from vibe_carlo.auth import (
    clear_session_cookie,
    create_session,
    delete_session,
    get_user_by_email,
    set_session_cookie,
    validate_session,
    verify_password,
)
from vibe_carlo.db import cleanup_expired_sessions, get_connection, init_db
from vibe_carlo.plans import (
    create_parameter_set,
    create_plan,
    delete_parameter_set,
    delete_plan,
    get_plan,
    list_parameter_sets,
    list_plans,
    move_parameter_set,
    update_parameter_set,
    update_plan_name,
)
from vibe_carlo.schemas import (
    AccountType,
    FlatDistribution,
    ParamSetSpec,
    PlanParameterSet,
    SimulationInput,
    SnapshotRow,
    SpendingDistribution,
    StatementAccountRow,
    TruncatedNormalDistribution,
    UniformDistribution,
)
from vibe_carlo.simulation.engine import run_simulation
from vibe_carlo.simulation.models import load_historical_data
from vibe_carlo.simulation.plan_engine import run_plan_simulation
from vibe_carlo.simulation.solver import solve_plan_safe_spending, solve_safe_spending
from vibe_carlo.snapshots import (
    create_snapshot,
    delete_snapshot,
    get_snapshot,
    list_snapshots,
    update_snapshot,
)
from vibe_carlo.statements import (
    create_account,
    create_statement,
    delete_account,
    delete_statement,
    get_latest_statement,
    get_statement,
    list_accounts,
    list_statements,
    update_account,
    update_statement_date,
)
from vibe_carlo.timeline import compute_timeline

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


def _format_accounting(value: float) -> str:
    """Format a dollar value in accounting style: $1,234.56 or ($1,234.56)."""
    if value < 0:
        return f"(${abs(value):,.2f})"
    return f"${value:,.2f}"


templates.env.filters["accounting"] = _format_accounting

historical_data: npt.NDArray[np.float64]
historical_data_json: str = ""
_db_path: Path | None = None
_secure_cookies = os.environ.get("VIBE_CARLO_SECURE_COOKIES", "") == "1"


@asynccontextmanager
async def lifespan(app: FastAPI) -> Any:
    global historical_data, historical_data_json  # noqa: PLW0603
    historical_data = load_historical_data()
    historical_data_json = json.dumps(historical_data.tolist())
    init_db(_db_path)
    cleanup_expired_sessions(_db_path)
    yield


app = FastAPI(lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


# ---------------------------------------------------------------------------
# Health check (unauthenticated)
# ---------------------------------------------------------------------------


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------


def _get_current_user(request: Request) -> tuple[int, str] | None:
    """Read session cookie and return (user_id, email) or None."""
    session_id = request.cookies.get("session_id")
    if not session_id:
        return None
    conn = get_connection(_db_path)
    try:
        return validate_session(conn, session_id)
    finally:
        conn.close()


def _auth_redirect(request: Request) -> Response:
    """Return a redirect to /login, HTMX-aware."""
    if request.headers.get("HX-Request"):
        return Response(status_code=200, headers={"HX-Redirect": "/login"})
    return RedirectResponse(url="/login", status_code=303)


# ---------------------------------------------------------------------------
# Form parsing helpers
# ---------------------------------------------------------------------------


def _parse_distribution(
    dist_type: str,
    value: float,
    low: float,
    high: float,
    mean: float,
    stddev: float,
) -> SpendingDistribution:
    """Convert form fields into the appropriate SpendingDistribution model."""
    if dist_type == "uniform":
        return UniformDistribution(low=low, high=high)
    if dist_type == "truncated_normal":
        return TruncatedNormalDistribution(low=low, high=high, mean=mean, stddev=stddev)
    # Default to flat
    return FlatDistribution(value=value)


def _parse_form_params(
    cash_value: float,
    market_value: float,
    bond_value: float,
    earnings: float,
    spending_dist_type: str,
    spending_dist_value: float,
    spending_dist_low: float,
    spending_dist_high: float,
    spending_dist_mean: float,
    spending_dist_stddev: float,
    years_to_simulate: int,
    sample_years: int | None,
    withdrawal_tax_rate_pct: float,
) -> SimulationInput:
    """Parse and validate form fields into a SimulationInput.

    The form field is a percentage (e.g. 20 for 20%); internally we store a
    fraction on [0, 1).
    """
    spending_dist = _parse_distribution(
        spending_dist_type,
        spending_dist_value,
        spending_dist_low,
        spending_dist_high,
        spending_dist_mean,
        spending_dist_stddev,
    )
    return SimulationInput(
        cash_value=cash_value,
        market_value=market_value,
        bond_value=bond_value,
        earnings=earnings,
        spending_distribution=spending_dist,
        years_to_simulate=years_to_simulate,
        sample_years=sample_years,
        withdrawal_tax_rate=withdrawal_tax_rate_pct / 100.0,
    )


# ---------------------------------------------------------------------------
# Auth routes
# ---------------------------------------------------------------------------


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request) -> Response:
    user = _get_current_user(request)
    if user is not None:
        return RedirectResponse(url="/", status_code=303)
    return templates.TemplateResponse(request, "login.html", {"error": None})


@app.post("/login", response_class=HTMLResponse)
async def login_submit(
    request: Request,
    email: str = Form(default=""),
    password: str = Form(default=""),
) -> Response:
    conn = get_connection(_db_path)
    try:
        user = get_user_by_email(conn, email)
        if user is None or not verify_password(password, str(user["password_hash"])):
            return templates.TemplateResponse(
                request,
                "login.html",
                {"error": "Invalid email or password."},
                status_code=401,
            )
        session_id = create_session(conn, int(str(user["id"])))
    finally:
        conn.close()
    response = RedirectResponse(url="/", status_code=303)
    set_session_cookie(response, session_id, secure=_secure_cookies)
    return response


@app.post("/logout")
async def logout(request: Request) -> Response:
    session_id = request.cookies.get("session_id")
    if session_id:
        conn = get_connection(_db_path)
        try:
            delete_session(conn, session_id)
        finally:
            conn.close()
    response = RedirectResponse(url="/login", status_code=303)
    clear_session_cookie(response)
    return response


# ---------------------------------------------------------------------------
# Main routes (all require auth)
# ---------------------------------------------------------------------------


@app.get("/", response_class=HTMLResponse)
async def index(
    request: Request,
    snapshot_id: int | None = Query(default=None),
) -> Response:
    user = _get_current_user(request)
    if user is None:
        return templates.TemplateResponse(
            request,
            "public_index.html",
            {"historical_data_json": historical_data_json},
        )
    user_id, user_email = user

    snapshot: SnapshotRow | None = None
    if snapshot_id is not None:
        conn = get_connection(_db_path)
        try:
            snapshot = get_snapshot(conn, snapshot_id, user_id)
        finally:
            conn.close()
        if snapshot is None:
            return HTMLResponse(status_code=404, content="Snapshot not found")
    return templates.TemplateResponse(
        request, "index.html", {"snapshot": snapshot, "user_email": user_email}
    )


@app.post("/simulate", response_model=None)
async def simulate(
    request: Request,
    cash_value: float = Form(default=0.0),
    market_value: float = Form(default=0.0),
    bond_value: float = Form(default=0.0),
    earnings: float = Form(default=0.0),
    spending_dist_type: str = Form(default="flat"),
    spending_dist_value: float = Form(default=0.0),
    spending_dist_low: float = Form(default=0.0),
    spending_dist_high: float = Form(default=0.0),
    spending_dist_mean: float = Form(default=0.0),
    spending_dist_stddev: float = Form(default=5000.0),
    years_to_simulate: int = Form(default=30),
    sample_years: int | None = Form(default=None),
    withdrawal_tax_rate_pct: float = Form(default=0.0),
) -> Response:
    user = _get_current_user(request)
    if user is None:
        return _auth_redirect(request)

    try:
        params = _parse_form_params(
            cash_value,
            market_value,
            bond_value,
            earnings,
            spending_dist_type,
            spending_dist_value,
            spending_dist_low,
            spending_dist_high,
            spending_dist_mean,
            spending_dist_stddev,
            years_to_simulate,
            sample_years,
            withdrawal_tax_rate_pct,
        )
    except (ValidationError, ValueError) as e:
        if isinstance(e, ValidationError):
            messages = [err.get("msg", "Validation error") for err in e.errors()]
        else:
            messages = [str(e)]
        return JSONResponse(status_code=422, content={"detail": messages})

    result = await asyncio.to_thread(run_simulation, params, historical_data)

    return templates.TemplateResponse(
        request,
        "partials/results.html",
        {
            "result": result,
            "params": params,
        },
    )


@app.post("/safe-spending", response_model=None)
async def safe_spending(
    request: Request,
    cash_value: float = Form(default=0.0),
    market_value: float = Form(default=0.0),
    bond_value: float = Form(default=0.0),
    earnings: float = Form(default=0.0),
    spending_dist_type: str = Form(default="flat"),
    spending_dist_value: float = Form(default=0.0),
    spending_dist_low: float = Form(default=0.0),
    spending_dist_high: float = Form(default=0.0),
    spending_dist_mean: float = Form(default=0.0),
    spending_dist_stddev: float = Form(default=5000.0),
    years_to_simulate: int = Form(default=30),
    sample_years: int | None = Form(default=None),
    withdrawal_tax_rate_pct: float = Form(default=0.0),
    target_net_worth: float = Form(default=0.0),
) -> Response:
    user = _get_current_user(request)
    if user is None:
        return _auth_redirect(request)

    try:
        params = _parse_form_params(
            cash_value,
            market_value,
            bond_value,
            earnings,
            spending_dist_type,
            spending_dist_value,
            spending_dist_low,
            spending_dist_high,
            spending_dist_mean,
            spending_dist_stddev,
            years_to_simulate,
            sample_years,
            withdrawal_tax_rate_pct,
        )
        table = await asyncio.to_thread(
            solve_safe_spending, params, historical_data, target_net_worth
        )
    except (ValidationError, ValueError) as e:
        if isinstance(e, ValidationError):
            messages = [err.get("msg", "Validation error") for err in e.errors()]
        else:
            messages = [str(e)]
        return JSONResponse(status_code=422, content={"detail": messages})

    return templates.TemplateResponse(request, "partials/safe_spending.html", {"table": table})


# ---------------------------------------------------------------------------
# Snapshot routes
# ---------------------------------------------------------------------------


@app.get("/snapshots", response_class=HTMLResponse)
async def snapshots_page(request: Request) -> Response:
    user = _get_current_user(request)
    if user is None:
        return _auth_redirect(request)
    user_id, user_email = user

    conn = get_connection(_db_path)
    try:
        snapshots = list_snapshots(conn, user_id)
    finally:
        conn.close()
    return templates.TemplateResponse(
        request, "snapshots.html", {"snapshots": snapshots, "user_email": user_email}
    )


@app.post("/snapshots/save", response_class=HTMLResponse)
async def save_snapshot(
    request: Request,
    snapshot_name: str = Form(default=""),
    snapshot_date: str = Form(default=""),
    cash_value: float = Form(default=0.0),
    market_value: float = Form(default=0.0),
    bond_value: float = Form(default=0.0),
    earnings: float = Form(default=0.0),
    spending_dist_type: str = Form(default="flat"),
    spending_dist_value: float = Form(default=0.0),
    spending_dist_low: float = Form(default=0.0),
    spending_dist_high: float = Form(default=0.0),
    spending_dist_mean: float = Form(default=0.0),
    spending_dist_stddev: float = Form(default=5000.0),
    years_to_simulate: int = Form(default=30),
    sample_years: int | None = Form(default=None),
    withdrawal_tax_rate_pct: float = Form(default=0.0),
) -> Response:
    user = _get_current_user(request)
    if user is None:
        return _auth_redirect(request)
    user_id, _user_email = user

    if not snapshot_date:
        return HTMLResponse(
            '<p class="text-red-600 text-sm">Date is required.</p>',
            status_code=422,
        )
    try:
        params = _parse_form_params(
            cash_value,
            market_value,
            bond_value,
            earnings,
            spending_dist_type,
            spending_dist_value,
            spending_dist_low,
            spending_dist_high,
            spending_dist_mean,
            spending_dist_stddev,
            years_to_simulate,
            sample_years,
            withdrawal_tax_rate_pct,
        )
    except (ValidationError, ValueError) as e:
        if isinstance(e, ValidationError):
            messages = [err.get("msg", "Validation error") for err in e.errors()]
        else:
            messages = [str(e)]
        msg = "; ".join(messages)
        return HTMLResponse(
            f'<p class="text-red-600 text-sm">{msg}</p>',
            status_code=422,
        )

    name = snapshot_name.strip() or None
    conn = get_connection(_db_path)
    try:
        create_snapshot(conn, user_id, name, snapshot_date, params)
    finally:
        conn.close()
    return HTMLResponse('<p class="text-green-600 text-sm">Snapshot saved.</p>')


@app.post("/snapshots/{snapshot_id}/update", response_class=HTMLResponse)
async def update_snapshot_route(
    request: Request,
    snapshot_id: int,
    snapshot_name: str = Form(default=""),
    snapshot_date: str = Form(default=""),
    cash_value: float = Form(default=0.0),
    market_value: float = Form(default=0.0),
    bond_value: float = Form(default=0.0),
    earnings: float = Form(default=0.0),
    spending_dist_type: str = Form(default="flat"),
    spending_dist_value: float = Form(default=0.0),
    spending_dist_low: float = Form(default=0.0),
    spending_dist_high: float = Form(default=0.0),
    spending_dist_mean: float = Form(default=0.0),
    spending_dist_stddev: float = Form(default=5000.0),
    years_to_simulate: int = Form(default=30),
    sample_years: int | None = Form(default=None),
    withdrawal_tax_rate_pct: float = Form(default=0.0),
) -> Response:
    user = _get_current_user(request)
    if user is None:
        return _auth_redirect(request)
    user_id, _user_email = user

    if not snapshot_date:
        return HTMLResponse(
            '<p class="text-red-600 text-sm">Date is required.</p>',
            status_code=422,
        )
    try:
        params = _parse_form_params(
            cash_value,
            market_value,
            bond_value,
            earnings,
            spending_dist_type,
            spending_dist_value,
            spending_dist_low,
            spending_dist_high,
            spending_dist_mean,
            spending_dist_stddev,
            years_to_simulate,
            sample_years,
            withdrawal_tax_rate_pct,
        )
    except (ValidationError, ValueError) as e:
        if isinstance(e, ValidationError):
            messages = [err.get("msg", "Validation error") for err in e.errors()]
        else:
            messages = [str(e)]
        msg = "; ".join(messages)
        return HTMLResponse(
            f'<p class="text-red-600 text-sm">{msg}</p>',
            status_code=422,
        )

    name = snapshot_name.strip() or None
    conn = get_connection(_db_path)
    try:
        found = update_snapshot(conn, snapshot_id, user_id, name, snapshot_date, params)
    finally:
        conn.close()
    if not found:
        return HTMLResponse(
            '<p class="text-red-600 text-sm">Snapshot not found.</p>',
            status_code=404,
        )
    return HTMLResponse('<p class="text-green-600 text-sm">Snapshot updated.</p>')


@app.delete("/snapshots/{snapshot_id}", response_class=HTMLResponse)
async def delete_snapshot_route(request: Request, snapshot_id: int) -> Response:
    user = _get_current_user(request)
    if user is None:
        return _auth_redirect(request)
    user_id, _user_email = user

    conn = get_connection(_db_path)
    try:
        found = delete_snapshot(conn, snapshot_id, user_id)
    finally:
        conn.close()
    if not found:
        return HTMLResponse(
            '<p class="text-red-600 text-sm">Snapshot not found.</p>',
            status_code=404,
        )
    # Return empty string so HTMX removes the row
    return HTMLResponse("")


# ---------------------------------------------------------------------------
# Timeline route
# ---------------------------------------------------------------------------


@app.get("/timeline", response_class=HTMLResponse)
async def timeline_page(request: Request) -> Response:
    user = _get_current_user(request)
    if user is None:
        return _auth_redirect(request)
    user_id, user_email = user

    conn = get_connection(_db_path)
    try:
        rows = list_snapshots(conn, user_id)
    finally:
        conn.close()
    # list_snapshots returns DESC order; reverse for ASC
    snapshots_asc = list(reversed(rows))

    timeline = (
        await asyncio.to_thread(compute_timeline, snapshots_asc, historical_data)
        if snapshots_asc
        else None
    )
    return templates.TemplateResponse(
        request, "timeline.html", {"timeline": timeline, "user_email": user_email}
    )


# ---------------------------------------------------------------------------
# Statement routes
# ---------------------------------------------------------------------------


@app.get("/statements", response_class=HTMLResponse)
async def statements_page(request: Request) -> Response:
    user = _get_current_user(request)
    if user is None:
        return _auth_redirect(request)
    user_id, user_email = user

    conn = get_connection(_db_path)
    try:
        stmts = list_statements(conn, user_id)
    finally:
        conn.close()

    from datetime import date

    return templates.TemplateResponse(
        request,
        "statements.html",
        {"statements": stmts, "today": date.today().isoformat(), "user_email": user_email},
    )


@app.post("/statements")
async def create_statement_route(
    request: Request,
    statement_date: str = Form(default=""),
    copy_from_latest: str = Form(default="false"),
) -> Response:
    user = _get_current_user(request)
    if user is None:
        return _auth_redirect(request)
    user_id, _user_email = user

    if not statement_date:
        return HTMLResponse(
            '<p class="text-red-600 text-sm">Date is required.</p>',
            status_code=422,
        )

    conn = get_connection(_db_path)
    try:
        # Find latest before creating the new one
        latest_accounts: list[StatementAccountRow] = []
        if copy_from_latest == "true":
            latest = get_latest_statement(conn, user_id)
            if latest is not None:
                latest_accounts = list_accounts(conn, latest.id, user_id)

        stmt_id = create_statement(conn, user_id, statement_date)

        for acct in latest_accounts:
            create_account(
                conn,
                stmt_id,
                user_id,
                name=acct.name,
                account_type=acct.account_type,
                value=abs(acct.value),
            )
    finally:
        conn.close()

    return RedirectResponse(url=f"/statements/{stmt_id}", status_code=303)


@app.get("/statements/{statement_id}", response_class=HTMLResponse)
async def statement_edit_page(request: Request, statement_id: int) -> Response:
    user = _get_current_user(request)
    if user is None:
        return _auth_redirect(request)
    user_id, user_email = user

    conn = get_connection(_db_path)
    try:
        stmt = get_statement(conn, statement_id, user_id)
        if stmt is None:
            return HTMLResponse(status_code=404, content="Statement not found")
        accounts = list_accounts(conn, statement_id, user_id)
    finally:
        conn.close()

    assets = [a for a in accounts if a.account_type == AccountType.asset]
    liabilities = [a for a in accounts if a.account_type == AccountType.liability]

    return templates.TemplateResponse(
        request,
        "statement_edit.html",
        {
            "statement": stmt,
            "assets": assets,
            "liabilities": liabilities,
            "user_email": user_email,
        },
    )


@app.post("/statements/{statement_id}", response_class=HTMLResponse)
async def save_statement_route(request: Request, statement_id: int) -> Response:
    user = _get_current_user(request)
    if user is None:
        return _auth_redirect(request)
    user_id, _user_email = user

    form = await request.form()
    new_date = str(form.get("statement_date", ""))
    if not new_date:
        return HTMLResponse(
            '<p class="text-red-600 text-sm">Date is required.</p>',
            status_code=422,
        )

    account_ids = form.getlist("account_ids")
    account_names = form.getlist("account_names")
    account_types = form.getlist("account_types")
    account_values = form.getlist("account_values")

    conn = get_connection(_db_path)
    try:
        stmt = get_statement(conn, statement_id, user_id)
        if stmt is None:
            return HTMLResponse(status_code=404, content="Statement not found")

        update_statement_date(conn, statement_id, user_id, new_date)

        # Get existing account IDs to detect deletions
        existing_accounts = list_accounts(conn, statement_id, user_id)
        existing_ids = {a.id for a in existing_accounts}
        form_ids: set[int] = set()

        for i in range(len(account_names)):
            acct_id_str = str(account_ids[i]) if i < len(account_ids) else ""
            acct_name = str(account_names[i])
            acct_type_str = str(account_types[i]) if i < len(account_types) else "asset"
            acct_type = AccountType(acct_type_str)
            acct_value = float(str(account_values[i])) if i < len(account_values) else 0.0

            if acct_id_str:
                acct_id = int(acct_id_str)
                form_ids.add(acct_id)
                update_account(
                    conn,
                    acct_id,
                    user_id,
                    name=acct_name,
                    account_type=acct_type,
                    value=acct_value,
                )
            else:
                create_account(
                    conn,
                    statement_id,
                    user_id,
                    name=acct_name,
                    account_type=acct_type,
                    value=acct_value,
                )

        # Delete accounts that were removed from the form
        for removed_id in existing_ids - form_ids:
            delete_account(conn, removed_id, user_id)
    finally:
        conn.close()

    return HTMLResponse('<p class="text-green-600 text-sm">Saved.</p>')


@app.delete("/statements/{statement_id}", response_class=HTMLResponse)
async def delete_statement_route(request: Request, statement_id: int) -> Response:
    user = _get_current_user(request)
    if user is None:
        return _auth_redirect(request)
    user_id, _user_email = user

    conn = get_connection(_db_path)
    try:
        found = delete_statement(conn, statement_id, user_id)
    finally:
        conn.close()
    if not found:
        return HTMLResponse(status_code=404, content="Statement not found")
    return HTMLResponse("")


# ---------------------------------------------------------------------------
# Plan routes
# ---------------------------------------------------------------------------


def _parse_param_set_form(
    param_name: str,
    duration: int | None,
    cash_value: float,
    market_value: float,
    bond_value: float,
    earnings: float,
    spending_dist_type: str,
    spending_dist_value: float,
    spending_dist_low: float,
    spending_dist_high: float,
    spending_dist_mean: float,
    spending_dist_stddev: float,
    withdrawal_tax_rate_pct: float,
) -> ParamSetSpec:
    """Parse form fields into a ParamSetSpec for create/update_parameter_set."""
    spending_dist = _parse_distribution(
        spending_dist_type,
        spending_dist_value,
        spending_dist_low,
        spending_dist_high,
        spending_dist_mean,
        spending_dist_stddev,
    )
    return ParamSetSpec(
        name=param_name,
        duration=duration,
        cash_value=cash_value,
        market_value=market_value,
        bond_value=bond_value,
        earnings=earnings,
        spending_distribution=spending_dist,
        withdrawal_tax_rate=withdrawal_tax_rate_pct / 100.0,
    )


@app.get("/plans", response_class=HTMLResponse)
async def plans_page(request: Request) -> Response:
    user = _get_current_user(request)
    if user is None:
        return _auth_redirect(request)
    user_id, user_email = user

    conn = get_connection(_db_path)
    try:
        plans = list_plans(conn, user_id)
    finally:
        conn.close()
    return templates.TemplateResponse(
        request, "plans.html", {"plans": plans, "user_email": user_email}
    )


@app.post("/plans")
async def create_plan_route(
    request: Request,
    name: str = Form(default=""),
) -> Response:
    user = _get_current_user(request)
    if user is None:
        return _auth_redirect(request)
    user_id, _user_email = user

    plan_name = name.strip()
    if not plan_name:
        return HTMLResponse(
            '<p class="text-red-600 text-sm">Plan name is required.</p>',
            status_code=422,
        )
    conn = get_connection(_db_path)
    try:
        plan_id = create_plan(conn, user_id, plan_name)
    finally:
        conn.close()
    return RedirectResponse(url=f"/plans/{plan_id}", status_code=303)


@app.get("/plans/{plan_id}", response_class=HTMLResponse)
async def plan_author_page(
    request: Request,
    plan_id: int,
    edit_param_id: int | None = Query(default=None),
) -> Response:
    user = _get_current_user(request)
    if user is None:
        return _auth_redirect(request)
    user_id, user_email = user

    conn = get_connection(_db_path)
    try:
        plan = get_plan(conn, plan_id, user_id)
        if plan is None:
            return HTMLResponse(status_code=404, content="Plan not found")
        param_sets = list_parameter_sets(conn, plan_id, user_id)
        edit_param: PlanParameterSet | None = None
        if edit_param_id is not None:
            edit_param = next((ps for ps in param_sets if ps.id == edit_param_id), None)
    finally:
        conn.close()

    return templates.TemplateResponse(
        request,
        "plan_author.html",
        {
            "plan": plan,
            "param_sets": param_sets,
            "edit_param": edit_param,
            "user_email": user_email,
        },
    )


@app.post("/plans/{plan_id}/name", response_class=HTMLResponse)
async def update_plan_name_route(
    request: Request,
    plan_id: int,
    name: str = Form(default=""),
) -> Response:
    user = _get_current_user(request)
    if user is None:
        return _auth_redirect(request)
    user_id, _user_email = user

    plan_name = name.strip()
    if not plan_name:
        return HTMLResponse('<span class="text-red-600 text-sm">Name required</span>')
    conn = get_connection(_db_path)
    try:
        found = update_plan_name(conn, plan_id, user_id, plan_name)
    finally:
        conn.close()
    if not found:
        return HTMLResponse(status_code=404, content="Plan not found")
    return HTMLResponse('<span class="text-green-600 text-sm">Saved</span>')


@app.delete("/plans/{plan_id}", response_class=HTMLResponse)
async def delete_plan_route(request: Request, plan_id: int) -> Response:
    user = _get_current_user(request)
    if user is None:
        return _auth_redirect(request)
    user_id, _user_email = user

    conn = get_connection(_db_path)
    try:
        found = delete_plan(conn, plan_id, user_id)
    finally:
        conn.close()
    if not found:
        return HTMLResponse(status_code=404, content="Plan not found")
    return HTMLResponse("")


@app.post("/plans/{plan_id}/params", response_class=HTMLResponse)
async def add_parameter_set_route(
    request: Request,
    plan_id: int,
    param_name: str = Form(default=""),
    duration: int | None = Form(default=None),
    cash_value: float = Form(default=0.0),
    market_value: float = Form(default=0.0),
    bond_value: float = Form(default=0.0),
    earnings: float = Form(default=0.0),
    spending_dist_type: str = Form(default="flat"),
    spending_dist_value: float = Form(default=0.0),
    spending_dist_low: float = Form(default=0.0),
    spending_dist_high: float = Form(default=0.0),
    spending_dist_mean: float = Form(default=0.0),
    spending_dist_stddev: float = Form(default=5000.0),
    withdrawal_tax_rate_pct: float = Form(default=0.0),
) -> Response:
    user = _get_current_user(request)
    if user is None:
        return _auth_redirect(request)
    user_id, _user_email = user

    try:
        spec = _parse_param_set_form(
            param_name,
            duration,
            cash_value,
            market_value,
            bond_value,
            earnings,
            spending_dist_type,
            spending_dist_value,
            spending_dist_low,
            spending_dist_high,
            spending_dist_mean,
            spending_dist_stddev,
            withdrawal_tax_rate_pct,
        )
    except (ValidationError, ValueError):
        return HTMLResponse(
            '<p class="text-red-600 text-sm">Invalid parameters.</p>',
            status_code=422,
        )

    conn = get_connection(_db_path)
    try:
        ps_id = create_parameter_set(conn, plan_id, user_id, spec)
        if ps_id is None:
            return HTMLResponse(status_code=404, content="Plan not found")
        plan = get_plan(conn, plan_id, user_id)
        param_sets = list_parameter_sets(conn, plan_id, user_id)
    finally:
        conn.close()

    return templates.TemplateResponse(
        request,
        "partials/plan_params_table.html",
        {"plan": plan, "param_sets": param_sets},
    )


@app.post("/plans/{plan_id}/params/{param_id}", response_class=HTMLResponse)
async def update_parameter_set_route(
    request: Request,
    plan_id: int,
    param_id: int,
    param_name: str = Form(default=""),
    duration: int | None = Form(default=None),
    cash_value: float = Form(default=0.0),
    market_value: float = Form(default=0.0),
    bond_value: float = Form(default=0.0),
    earnings: float = Form(default=0.0),
    spending_dist_type: str = Form(default="flat"),
    spending_dist_value: float = Form(default=0.0),
    spending_dist_low: float = Form(default=0.0),
    spending_dist_high: float = Form(default=0.0),
    spending_dist_mean: float = Form(default=0.0),
    spending_dist_stddev: float = Form(default=5000.0),
    withdrawal_tax_rate_pct: float = Form(default=0.0),
) -> Response:
    user = _get_current_user(request)
    if user is None:
        return _auth_redirect(request)
    user_id, _user_email = user

    try:
        spec = _parse_param_set_form(
            param_name,
            duration,
            cash_value,
            market_value,
            bond_value,
            earnings,
            spending_dist_type,
            spending_dist_value,
            spending_dist_low,
            spending_dist_high,
            spending_dist_mean,
            spending_dist_stddev,
            withdrawal_tax_rate_pct,
        )
    except (ValidationError, ValueError):
        return HTMLResponse(
            '<p class="text-red-600 text-sm">Invalid parameters.</p>',
            status_code=422,
        )

    conn = get_connection(_db_path)
    try:
        found = update_parameter_set(conn, param_id, user_id, spec)
        if not found:
            return HTMLResponse(status_code=404, content="Parameter set not found")
        plan = get_plan(conn, plan_id, user_id)
        param_sets = list_parameter_sets(conn, plan_id, user_id)
    finally:
        conn.close()

    return templates.TemplateResponse(
        request,
        "partials/plan_params_table.html",
        {"plan": plan, "param_sets": param_sets},
    )


@app.delete("/plans/{plan_id}/params/{param_id}", response_class=HTMLResponse)
async def delete_parameter_set_route(request: Request, plan_id: int, param_id: int) -> Response:
    user = _get_current_user(request)
    if user is None:
        return _auth_redirect(request)
    user_id, _user_email = user

    conn = get_connection(_db_path)
    try:
        found = delete_parameter_set(conn, param_id, user_id)
        if not found:
            return HTMLResponse(status_code=404, content="Parameter set not found")
        plan = get_plan(conn, plan_id, user_id)
        param_sets = list_parameter_sets(conn, plan_id, user_id)
    finally:
        conn.close()

    return templates.TemplateResponse(
        request,
        "partials/plan_params_table.html",
        {"plan": plan, "param_sets": param_sets},
    )


@app.post("/plans/{plan_id}/params/{param_id}/move", response_class=HTMLResponse)
async def move_parameter_set_route(
    request: Request,
    plan_id: int,
    param_id: int,
    direction: str = Form(default=""),
) -> Response:
    user = _get_current_user(request)
    if user is None:
        return _auth_redirect(request)
    user_id, _user_email = user

    conn = get_connection(_db_path)
    try:
        move_parameter_set(conn, param_id, user_id, direction)
        plan = get_plan(conn, plan_id, user_id)
        param_sets = list_parameter_sets(conn, plan_id, user_id)
    finally:
        conn.close()

    return templates.TemplateResponse(
        request,
        "partials/plan_params_table.html",
        {"plan": plan, "param_sets": param_sets},
    )


@app.get("/plans/{plan_id}/simulate", response_class=HTMLResponse)
async def plan_simulate_page(request: Request, plan_id: int) -> Response:
    user = _get_current_user(request)
    if user is None:
        return _auth_redirect(request)
    user_id, user_email = user

    conn = get_connection(_db_path)
    try:
        plan = get_plan(conn, plan_id, user_id)
        if plan is None:
            return HTMLResponse(status_code=404, content="Plan not found")
        param_sets = list_parameter_sets(conn, plan_id, user_id)
    finally:
        conn.close()

    if not param_sets:
        return RedirectResponse(url=f"/plans/{plan_id}", status_code=303)

    return templates.TemplateResponse(
        request,
        "plan_simulate.html",
        {"plan": plan, "param_sets": param_sets, "user_email": user_email},
    )


@app.post("/plans/{plan_id}/simulate", response_model=None)
async def run_plan_simulation_route(
    request: Request,
    plan_id: int,
    years_to_simulate: int = Form(default=30),
    sample_years: int | None = Form(default=None),
) -> Response:
    user = _get_current_user(request)
    if user is None:
        return _auth_redirect(request)
    user_id, _user_email = user

    conn = get_connection(_db_path)
    try:
        plan = get_plan(conn, plan_id, user_id)
        if plan is None:
            return HTMLResponse(status_code=404, content="Plan not found")
        param_sets = list_parameter_sets(conn, plan_id, user_id)
    finally:
        conn.close()

    if not param_sets:
        return JSONResponse(
            status_code=422,
            content={"detail": ["Plan has no parameter sets"]},
        )

    effective_sample = sample_years if sample_years else years_to_simulate

    result = await asyncio.to_thread(
        run_plan_simulation,
        param_sets,
        years_to_simulate,
        effective_sample,
        historical_data,
    )

    return templates.TemplateResponse(
        request,
        "partials/results.html",
        {"result": result, "params": None},
    )


@app.post("/plans/{plan_id}/safe-spending", response_model=None)
async def plan_safe_spending_route(
    request: Request,
    plan_id: int,
    years_to_simulate: int = Form(default=30),
    sample_years: int | None = Form(default=None),
    target_net_worth: float = Form(default=0.0),
) -> Response:
    """Solve the plan's final phase for the spending it can sustain.

    Earlier phases describe commitments already made, so only the concluding
    phase is varied.
    """
    user = _get_current_user(request)
    if user is None:
        return _auth_redirect(request)
    user_id, _user_email = user

    conn = get_connection(_db_path)
    try:
        plan = get_plan(conn, plan_id, user_id)
        if plan is None:
            return HTMLResponse(status_code=404, content="Plan not found")
        param_sets = list_parameter_sets(conn, plan_id, user_id)
    finally:
        conn.close()

    if not param_sets:
        return JSONResponse(
            status_code=422,
            content={"detail": ["Plan has no parameter sets"]},
        )

    effective_sample = sample_years if sample_years else years_to_simulate

    try:
        table = await asyncio.to_thread(
            solve_plan_safe_spending,
            param_sets,
            years_to_simulate,
            effective_sample,
            historical_data,
            target_net_worth,
        )
    except ValueError as e:
        return JSONResponse(status_code=422, content={"detail": [str(e)]})

    return templates.TemplateResponse(request, "partials/safe_spending.html", {"table": table})
