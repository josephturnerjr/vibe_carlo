from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class FilingStatus(StrEnum):
    single = "single"
    married_jointly = "married_jointly"
    married_separately = "married_separately"
    head_of_household = "head_of_household"


# ---------------------------------------------------------------------------
# Spending distribution models (discriminated union on dist_type)
# ---------------------------------------------------------------------------


class FlatDistribution(BaseModel):
    dist_type: Literal["flat"] = "flat"
    value: float = Field(ge=0)


class UniformDistribution(BaseModel):
    dist_type: Literal["uniform"] = "uniform"
    low: float = Field(ge=0)
    high: float = Field(ge=0)

    @model_validator(mode="after")
    def low_le_high(self) -> "UniformDistribution":
        if self.low > self.high:
            raise ValueError("low must be ≤ high")
        return self


class TruncatedNormalDistribution(BaseModel):
    dist_type: Literal["truncated_normal"] = "truncated_normal"
    low: float = Field(ge=0)
    high: float = Field(ge=0)
    mean: float
    stddev: float = Field(gt=0)

    @model_validator(mode="after")
    def validate_bounds(self) -> "TruncatedNormalDistribution":
        if self.low > self.high:
            raise ValueError("low must be ≤ high")
        if not (self.low <= self.mean <= self.high):
            raise ValueError("mean must be within [low, high]")
        return self


SpendingDistribution = Annotated[
    FlatDistribution | UniformDistribution | TruncatedNormalDistribution,
    Field(discriminator="dist_type"),
]


class SimulationInput(BaseModel):
    cash_value: float
    market_value: float
    bond_value: float
    earnings: float = 0.0
    spending_distribution: SpendingDistribution = Field(
        default_factory=lambda: FlatDistribution(value=0.0)
    )
    years_to_simulate: int
    sample_years: int | None = None
    filing_status: FilingStatus | None = None

    @field_validator("cash_value", "market_value", "bond_value")
    @classmethod
    def values_non_negative(cls, v: float) -> float:
        if v < 0:
            raise ValueError("Dollar values must be non-negative")
        return v

    @field_validator("earnings")
    @classmethod
    def earnings_non_negative(cls, v: float) -> float:
        if v < 0:
            raise ValueError("Earnings must be non-negative")
        return v

    @field_validator("years_to_simulate")
    @classmethod
    def years_positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("Years to simulate must be positive")
        return v

    @model_validator(mode="after")
    def validate_portfolio_and_sample_years(self) -> "SimulationInput":
        if self.cash_value + self.market_value + self.bond_value <= 0:
            raise ValueError("Total portfolio value must be greater than zero")
        if self.sample_years is None:
            self.sample_years = self.years_to_simulate
        if self.sample_years <= 0:
            raise ValueError("Sample years must be positive")
        return self


class SimulationResult(BaseModel):
    year_labels: list[int]
    percentiles: dict[str, list[float]]
    success_rate: float
    final_year_distribution: list[float]
    gross_withdrawal: float | None = None
    effective_tax_rate: float | None = None
