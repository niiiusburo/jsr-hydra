"""
Regime detection Pydantic schemas for the JSR Hydra API.

Handles validation and serialization of market regime states,
confidence scores, and historical regime data.
"""

from datetime import datetime
from uuid import UUID
from typing import Optional

from pydantic import BaseModel, ConfigDict, field_validator


class RegimeResponse(BaseModel):
    """
    Current market regime state schema.

    Attributes:
        id: Unique regime record identifier (UUID)
        regime: Regime type (e.g., 'trending', 'ranging', 'volatile')
        confidence: Confidence score (0-1)
        conviction_score: Optional conviction score
        hmm_state: Optional Hidden Markov Model state
        is_drifting: Whether regime is drifting
        layer_scores: Dictionary of layer-specific scores
        detected_at: Timestamp of regime detection
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    regime: str
    confidence: Optional[float] = None
    conviction_score: Optional[int] = None
    hmm_state: Optional[int] = None
    is_drifting: bool
    layer_scores: dict
    detected_at: datetime

    @field_validator('confidence')
    @classmethod
    def validate_confidence(cls, v: Optional[float]) -> Optional[float]:
        """Validate confidence is between 0 and 1, or None."""
        if v is None:
            return v
        if not 0 <= v <= 1:
            raise ValueError('confidence must be between 0 and 1')
        return v


class RegimeHistory(BaseModel):
    """
    Historical regime data.

    Attributes:
        regimes: List of regime states
    """

    model_config = ConfigDict(from_attributes=True)

    regimes: list[RegimeResponse]
