from enum import StrEnum

from pydantic import BaseModel, field_validator, model_validator


class FilingStatus(StrEnum):
    single = "single"
    married_jointly = "married_jointly"
    married_separately = "married_separately"
    head_of_household = "head_of_household"


class SimulationInput(BaseModel):
    cash_value: float
    market_value: float
    bond_value: float
    annual_contribution: float
    annual_spending: float
    years_to_simulate: int
    sample_years: int | None = None
    filing_status: FilingStatus | None = None
    other_income: float = 0.0

    @field_validator("cash_value", "market_value", "bond_value")
    @classmethod
    def values_non_negative(cls, v: float) -> float:
        if v < 0:
            raise ValueError("Dollar values must be non-negative")
        return v

    @field_validator("annual_contribution", "annual_spending")
    @classmethod
    def flows_non_negative(cls, v: float) -> float:
        if v < 0:
            raise ValueError("Annual flows must be non-negative")
        return v

    @field_validator("other_income")
    @classmethod
    def other_income_non_negative(cls, v: float) -> float:
        if v < 0:
            raise ValueError("Other income must be non-negative")
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
