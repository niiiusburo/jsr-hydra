"""
Capital allocation Pydantic schemas for the JSR Hydra API.

Handles validation and serialization of strategy allocation weights,
updates, and summary reports.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, field_validator


class AllocationResponse(BaseModel):
    """
    Single strategy allocation response.

    Attributes:
        strategy_code: Strategy identifier code
        strategy_name: Strategy name
        weight: Allocation weight (0-1)
        source: Allocation source (e.g., 'algorithm', 'manual')
        regime: Optional associated market regime
        allocated_at: Timestamp of allocation
    """

    model_config = ConfigDict(from_attributes=True)

    strategy_code: str
    strategy_name: str
    weight: float
    source: str
    regime: Optional[str] = None
    allocated_at: datetime

    @field_validator('weight')
    @classmethod
    def validate_weight(cls, v: float) -> float:
        """Validate weight is between 0 and 1."""
        if not 0 <= v <= 1:
            raise ValueError('weight must be between 0 and 1')
        return v


class AllocationUpdate(BaseModel):
    """
    Schema for updating strategy allocations.

    Attributes:
        allocations: Dictionary mapping strategy codes to weights (0-1)
    """

    model_config = ConfigDict(from_attributes=True)

    allocations: dict[str, float]

    @field_validator('allocations')
    @classmethod
    def validate_allocations(cls, v: dict[str, float]) -> dict[str, float]:
        """Validate all weights are 0-1 and sum is <= 1.0."""
        total = 0.0
        for strategy_code, weight in v.items():
            if not 0 <= weight <= 1:
                raise ValueError(
                    f'weight for {strategy_code} must be between 0 and 1'
                )
            total += weight

        if total > 1.0:
            raise ValueError(
                f'sum of all allocations must be <= 1.0, got {total}'
            )

        return v


class AllocationSummary(BaseModel):
    """
    Summary of current allocations.

    Attributes:
        allocations: List of individual allocations
        total_weight: Sum of all allocation weights
    """

    model_config = ConfigDict(from_attributes=True)

    allocations: list[AllocationResponse]
    total_weight: float

    @field_validator('total_weight')
    @classmethod
    def validate_total_weight(cls, v: float) -> float:
        """Validate total weight is between 0 and 1."""
        if not 0 <= v <= 1:
            raise ValueError('total_weight must be between 0 and 1')
        return v
