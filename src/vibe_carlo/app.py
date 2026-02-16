from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt
from fastapi import FastAPI, Form, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError

from vibe_carlo.db import get_connection, init_db
from vibe_carlo.schemas import (
    FilingStatus,
    FlatDistribution,
    SimulationInput,
    SnapshotRow,
    SpendingDistribution,
    TruncatedNormalDistribution,
    UniformDistribution,
)
from vibe_carlo.simulation.engine import run_simulation
from vibe_carlo.simulation.models import load_historical_data
from vibe_carlo.snapshots import (
    create_snapshot,
    delete_snapshot,
    get_snapshot,
    list_snapshots,
    update_snapshot,
)
from vibe_carlo.timeline import compute_timeline

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

historical_data: npt.NDArray[np.float64]
_db_path: Path | None = None


@asynccontextmanager
async def lifespan(app: FastAPI) -> Any:
    global historical_data  # noqa: PLW0603
    historical_data = load_historical_data()
    init_db(_db_path)
    yield


app = FastAPI(lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


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
    filing_status: str | None,
) -> SimulationInput:
    """Parse and validate form fields into a SimulationInput."""
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
        filing_status=FilingStatus(filing_status) if filing_status else None,
    )


def _snapshot_to_row(raw: dict[str, object]) -> SnapshotRow:
    """Convert a raw DB dict into a typed SnapshotRow."""
    from vibe_carlo.snapshots import _deserialize_distribution

    dist = _deserialize_distribution(str(raw["spending_distribution"]))
    filing = FilingStatus(str(raw["filing_status"])) if raw.get("filing_status") else None
    return SnapshotRow(
        id=int(str(raw["id"])),
        name=str(raw["name"]) if raw.get("name") else None,
        snapshot_date=str(raw["snapshot_date"]),
        cash_value=float(str(raw["cash_value"])),
        market_value=float(str(raw["market_value"])),
        bond_value=float(str(raw["bond_value"])),
        earnings=float(str(raw["earnings"])),
        spending_distribution=dist,
        years_to_simulate=int(str(raw["years_to_simulate"])),
        sample_years=int(str(raw["sample_years"])) if raw.get("sample_years") else None,
        filing_status=filing,
        created_at=str(raw["created_at"]) if raw.get("created_at") else None,
        updated_at=str(raw["updated_at"]) if raw.get("updated_at") else None,
    )


@app.get("/", response_class=HTMLResponse)
async def index(
    request: Request,
    snapshot_id: int | None = Query(default=None),
) -> HTMLResponse:
    snapshot: SnapshotRow | None = None
    if snapshot_id is not None:
        conn = get_connection(_db_path)
        try:
            raw = get_snapshot(conn, snapshot_id)
        finally:
            conn.close()
        if raw is None:
            return HTMLResponse(status_code=404, content="Snapshot not found")
        snapshot = _snapshot_to_row(raw)
    return templates.TemplateResponse(request, "index.html", {"snapshot": snapshot})


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
    filing_status: str | None = Form(default=None),
) -> HTMLResponse | JSONResponse:
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
            filing_status,
        )
    except (ValidationError, ValueError) as e:
        if isinstance(e, ValidationError):
            messages = [err.get("msg", "Validation error") for err in e.errors()]
        else:
            messages = [str(e)]
        return JSONResponse(status_code=422, content={"detail": messages})

    result = run_simulation(params, historical_data)

    return templates.TemplateResponse(
        request,
        "partials/results.html",
        {
            "result": result,
            "params": params,
        },
    )


# ---------------------------------------------------------------------------
# Snapshot routes
# ---------------------------------------------------------------------------


@app.get("/snapshots", response_class=HTMLResponse)
async def snapshots_page(request: Request) -> HTMLResponse:
    conn = get_connection(_db_path)
    try:
        rows = list_snapshots(conn)
    finally:
        conn.close()
    typed_rows = [_snapshot_to_row(r) for r in rows]
    return templates.TemplateResponse(request, "snapshots.html", {"snapshots": typed_rows})


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
    filing_status: str | None = Form(default=None),
) -> HTMLResponse:
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
            filing_status,
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
        create_snapshot(conn, name, snapshot_date, params)
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
    filing_status: str | None = Form(default=None),
) -> HTMLResponse:
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
            filing_status,
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
        found = update_snapshot(conn, snapshot_id, name, snapshot_date, params)
    finally:
        conn.close()
    if not found:
        return HTMLResponse(
            '<p class="text-red-600 text-sm">Snapshot not found.</p>',
            status_code=404,
        )
    return HTMLResponse('<p class="text-green-600 text-sm">Snapshot updated.</p>')


@app.delete("/snapshots/{snapshot_id}", response_class=HTMLResponse)
async def delete_snapshot_route(snapshot_id: int) -> HTMLResponse:
    conn = get_connection(_db_path)
    try:
        found = delete_snapshot(conn, snapshot_id)
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
async def timeline_page(request: Request) -> HTMLResponse:
    conn = get_connection(_db_path)
    try:
        rows = list_snapshots(conn)
    finally:
        conn.close()
    # list_snapshots returns DESC order; reverse for ASC
    typed_rows = [_snapshot_to_row(r) for r in reversed(rows)]

    timeline = compute_timeline(typed_rows, historical_data) if typed_rows else None
    return templates.TemplateResponse(request, "timeline.html", {"timeline": timeline})
