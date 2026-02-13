from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError

from vibe_carlo.schemas import (
    FilingStatus,
    FlatDistribution,
    SimulationInput,
    SpendingDistribution,
    TruncatedNormalDistribution,
    UniformDistribution,
)
from vibe_carlo.simulation.engine import run_simulation
from vibe_carlo.simulation.models import load_historical_data

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

historical_data: npt.NDArray[np.float64]


@asynccontextmanager
async def lifespan(app: FastAPI) -> Any:
    global historical_data  # noqa: PLW0603
    historical_data = load_historical_data()
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


@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "index.html")


@app.post("/simulate", response_model=None)
async def simulate(
    request: Request,
    cash_value: float = Form(default=0.0),
    market_value: float = Form(default=0.0),
    bond_value: float = Form(default=0.0),
    annual_contribution: float = Form(default=0.0),
    spending_dist_type: str = Form(default="flat"),
    spending_dist_value: float = Form(default=0.0),
    spending_dist_low: float = Form(default=0.0),
    spending_dist_high: float = Form(default=0.0),
    spending_dist_mean: float = Form(default=0.0),
    spending_dist_stddev: float = Form(default=5000.0),
    years_to_simulate: int = Form(default=30),
    sample_years: int | None = Form(default=None),
    filing_status: str | None = Form(default=None),
    other_income: float = Form(default=0.0),
) -> HTMLResponse | JSONResponse:
    try:
        spending_dist = _parse_distribution(
            spending_dist_type,
            spending_dist_value,
            spending_dist_low,
            spending_dist_high,
            spending_dist_mean,
            spending_dist_stddev,
        )
        params = SimulationInput(
            cash_value=cash_value,
            market_value=market_value,
            bond_value=bond_value,
            annual_contribution=annual_contribution,
            spending_distribution=spending_dist,
            years_to_simulate=years_to_simulate,
            sample_years=sample_years,
            filing_status=FilingStatus(filing_status) if filing_status else None,
            other_income=other_income,
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
