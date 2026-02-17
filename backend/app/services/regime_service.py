"""
Regime detection service for JSR Hydra trading system.

PURPOSE: Manage market regime state including detection, persistence,
and historical analysis for regime-based strategy allocation.

CALLED BY: app.api.routes.regime, regime detection engine, dashboard
"""

from uuid import UUID
from datetime import datetime
from typing import Optional

from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.regime import RegimeState
from app.schemas.regime import RegimeResponse
from app.events.bus import get_event_bus
from app.utils.logger import get_logger


logger = get_logger("services.regime")


class RegimeService:
    """
    Service for managing market regime detection and state.

    PURPOSE: Provide business logic for regime operations including
    detection persistence, retrieval, and historical analysis.

    CALLED BY: API routes for regime endpoints, regime detection modules
    """

    @staticmethod
    async def get_current_regime(
        db: AsyncSession
    ) -> Optional[RegimeResponse]:
        """
        Retrieve the most recent market regime state.

        PURPOSE: Fetch the latest detected market regime for use in
        decision making, allocation adjustments, and reporting.

        CALLED BY: Dashboard endpoint, allocation engine, API endpoints

        Args:
            db: Async database session

        Returns:
            RegimeResponse: Current regime state, None if no regime detected
        """
        logger.info("get_current_regime_started")

        try:
            stmt = select(RegimeState).order_by(desc(RegimeState.detected_at)).limit(1)
            result = await db.execute(stmt)
            regime = result.scalar_one_or_none()

            if not regime:
                logger.info("no_current_regime_found")
                return None

            logger.info(
                "current_regime_retrieved",
                regime=regime.regime,
                confidence=regime.confidence
            )

            return RegimeResponse.model_validate(regime)

        except Exception as e:
            logger.error("get_current_regime_error", error=str(e))
            raise

    @staticmethod
    async def save_regime(
        db: AsyncSession,
        regime: str,
        confidence: Optional[float] = None,
        conviction_score: Optional[int] = None,
        hmm_state: Optional[int] = None,
        is_drifting: bool = False,
        layer_scores: Optional[dict] = None
    ) -> RegimeResponse:
        """
        Save a detected market regime state to the database.

        PURPOSE: Persist regime detection results from the detection engine
        and publish regime_detected event for downstream consumption.

        CALLED BY: Regime detection engine, analysis modules

        Args:
            db: Async database session
            regime: Regime type (e.g., 'trending', 'ranging', 'volatile', 'choppy')
            confidence: Confidence score (0-1), optional
            conviction_score: HMM/ML conviction score, optional
            hmm_state: Hidden Markov Model state identifier, optional
            is_drifting: Whether regime appears to be drifting, default False
            layer_scores: Dictionary of layer-specific scores, default {}

        Returns:
            RegimeResponse: Persisted regime state

        Raises:
            Exception: On database errors
        """
        logger.info(
            "save_regime_started",
            regime=regime,
            confidence=confidence,
            is_drifting=is_drifting
        )

        try:
            layer_scores = layer_scores or {}

            # Create regime record
            regime_state = RegimeState(
                regime=regime,
                confidence=confidence,
                conviction_score=conviction_score,
                hmm_state=hmm_state,
                is_drifting=is_drifting,
                layer_scores=layer_scores,
                detected_at=datetime.utcnow()
            )

            db.add(regime_state)
            await db.flush()
            await db.commit()

            logger.info(
                "regime_saved",
                regime_id=str(regime_state.id),
                regime=regime,
                confidence=confidence
            )

            # Publish event
            event_bus = get_event_bus()
            await event_bus.publish(
                event_type="regime_detected",
                data={
                    "regime_id": str(regime_state.id),
                    "regime": regime,
                    "confidence": confidence,
                    "conviction_score": conviction_score,
                    "is_drifting": is_drifting,
                    "layer_scores": layer_scores,
                    "detected_at": regime_state.detected_at.isoformat()
                },
                source="regime_service",
                severity="INFO"
            )

            return RegimeResponse.model_validate(regime_state)

        except Exception as e:
            logger.error("save_regime_error", error=str(e), regime=regime)
            await db.rollback()
            raise

    @staticmethod
    async def get_regime_history(
        db: AsyncSession,
        limit: int = 50
    ) -> list[RegimeResponse]:
        """
        Retrieve historical regime states in reverse chronological order.

        PURPOSE: Fetch recent regime detections for analysis, plotting,
        and understanding regime transitions.

        CALLED BY: Dashboard endpoint, analysis endpoints, historical reports

        Args:
            db: Async database session
            limit: Maximum number of regimes to retrieve (default: 50)

        Returns:
            list[RegimeResponse]: List of regime states, newest first
        """
        logger.info("get_regime_history_started", limit=limit)

        try:
            stmt = (
                select(RegimeState)
                .order_by(desc(RegimeState.detected_at))
                .limit(limit)
            )
            result = await db.execute(stmt)
            regimes = result.scalars().all()

            logger.info("regime_history_retrieved", count=len(regimes))

            return [RegimeResponse.model_validate(r) for r in regimes]

        except Exception as e:
            logger.error("get_regime_history_error", error=str(e))
            raise

    @staticmethod
    async def get_regime_by_id(
        db: AsyncSession,
        regime_id: UUID
    ) -> Optional[RegimeResponse]:
        """
        Retrieve a specific regime state by ID.

        PURPOSE: Fetch detailed information about a particular regime
        detection event for analysis or debugging.

        CALLED BY: Historical analysis endpoints

        Args:
            db: Async database session
            regime_id: UUID of the regime to retrieve

        Returns:
            RegimeResponse if found, None otherwise
        """
        logger.info("get_regime_by_id_started", regime_id=str(regime_id))

        try:
            stmt = select(RegimeState).where(RegimeState.id == regime_id)
            result = await db.execute(stmt)
            regime = result.scalar_one_or_none()

            if not regime:
                logger.info("regime_not_found", regime_id=str(regime_id))
                return None

            logger.info("regime_retrieved", regime_id=str(regime_id))
            return RegimeResponse.model_validate(regime)

        except Exception as e:
            logger.error(
                "get_regime_by_id_error",
                error=str(e),
                regime_id=str(regime_id)
            )
            raise
