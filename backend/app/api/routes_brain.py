"""
PURPOSE: Brain API routes for JSR Hydra trading system.

Provides read-only endpoints to access the Brain's real-time cognitive state:
thoughts, market analysis, planned next moves, and per-strategy confidence scores.

Authentication required for all endpoints — brain state and controls contain
sensitive trading telemetry.

CALLED BY:
    - Frontend dashboard (polling or SSE)
    - External monitoring tools
"""

from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from app.api.auth import get_current_user
from app.brain import get_brain
from app.core.rate_limit import limiter, READ_LIMIT, WRITE_LIMIT
from app.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/brain", tags=["brain"])


def _raise_brain_route_error(action: str, error: Exception) -> None:
    """Raise a consistent 500 response for brain route failures."""
    logger.error(
        "brain_route_failed",
        action=action,
        error=str(error),
        exception_type=type(error).__name__,
    )
    raise HTTPException(
        status_code=500,
        detail=f"Failed to {action}",
    )


# ════════════════════════════════════════════════════════════════
# Full Brain State
# ════════════════════════════════════════════════════════════════


@router.get("/state")
@limiter.limit(READ_LIMIT)
async def get_brain_state(
    request: Request,
    _current_user: str = Depends(get_current_user),
):
    """
    PURPOSE: Return full brain state including thoughts, analysis, next moves, and strategy scores.

    Returns:
        dict: Complete brain state snapshot

    CALLED BY: Frontend dashboard
    """
    try:
        brain = get_brain()
        return brain.get_state()
    except Exception as e:
        _raise_brain_route_error("retrieve brain state", e)


# ════════════════════════════════════════════════════════════════
# Recent Thoughts
# ════════════════════════════════════════════════════════════════


@router.get("/thoughts")
@limiter.limit(READ_LIMIT)
async def get_brain_thoughts(
    request: Request,
    limit: int = Query(default=50, ge=1, le=100, description="Number of recent thoughts to return"),
    _current_user: str = Depends(get_current_user),
):
    """
    PURPOSE: Return recent Brain thoughts, newest first.

    Args:
        limit: Maximum number of thoughts (1-100, default 50)

    Returns:
        dict: List of thought objects with timestamp, type, content, confidence, metadata

    CALLED BY: Frontend thought feed
    """
    try:
        brain = get_brain()
        thoughts = brain.get_thoughts(limit=limit)
        return {
            "thoughts": thoughts,
            "count": len(thoughts),
            "total": brain._cycle_count,
        }
    except Exception as e:
        _raise_brain_route_error("retrieve brain thoughts", e)


# ════════════════════════════════════════════════════════════════
# Market Analysis
# ════════════════════════════════════════════════════════════════


@router.get("/analysis")
@limiter.limit(READ_LIMIT)
async def get_market_analysis(
    request: Request,
    _current_user: str = Depends(get_current_user),
):
    """
    PURPOSE: Return current market analysis (trend, momentum, volatility, regime).

    Returns:
        dict: Human-readable market read with raw indicator data

    CALLED BY: Frontend analysis panel
    """
    try:
        brain = get_brain()
        return brain.get_market_analysis()
    except Exception as e:
        _raise_brain_route_error("retrieve market analysis", e)


# ════════════════════════════════════════════════════════════════
# Next Moves
# ════════════════════════════════════════════════════════════════


@router.get("/next-moves")
@limiter.limit(READ_LIMIT)
async def get_next_moves(
    request: Request,
    _current_user: str = Depends(get_current_user),
):
    """
    PURPOSE: Return what the Brain is watching for — planned next actions and triggers.

    Returns:
        dict: List of human-readable next move descriptions

    CALLED BY: Frontend next-moves panel
    """
    try:
        brain = get_brain()
        moves = brain.get_next_moves()
        return {
            "next_moves": moves,
            "count": len(moves),
        }
    except Exception as e:
        _raise_brain_route_error("retrieve next moves", e)


# ════════════════════════════════════════════════════════════════
# Strategy Scores
# ════════════════════════════════════════════════════════════════


@router.get("/strategy-scores")
@limiter.limit(READ_LIMIT)
async def get_strategy_scores(
    request: Request,
    _current_user: str = Depends(get_current_user),
):
    """
    PURPOSE: Return per-strategy confidence scores with reasoning.

    Returns:
        dict: Strategy code -> {name, confidence, reason, status, rl_preset, rl_expected}

    CALLED BY: Frontend strategy confidence panel
    """
    try:
        brain = get_brain()
        scores = brain.get_strategy_scores()
        return {
            "strategy_scores": scores,
            "count": len(scores),
        }
    except Exception as e:
        _raise_brain_route_error("retrieve strategy scores", e)


# ════════════════════════════════════════════════════════════════
# RL Stats
# ════════════════════════════════════════════════════════════════


@router.get("/strategy-xp")
@limiter.limit(READ_LIMIT)
async def get_strategy_xp(
    request: Request,
    _current_user: str = Depends(get_current_user),
):
    """
    PURPOSE: Return Pokemon-style XP/level data for all strategies.

    Returns:
        dict: Strategy code -> XP state with level, progress, badges, skills

    CALLED BY: Frontend strategy pages, XP bar components
    """
    try:
        brain = get_brain()
        return brain.get_strategy_xp()
    except Exception as e:
        _raise_brain_route_error("retrieve strategy XP", e)


@router.get("/rl-stats")
@limiter.limit(READ_LIMIT)
async def get_rl_stats(
    request: Request,
    _current_user: str = Depends(get_current_user),
):
    """
    PURPOSE: Return reinforcement learning statistics for the brain dashboard.

    Includes Thompson Sampling distributions, trade history stats,
    per-strategy confidence adjustments, exploration rate, regime performance,
    and current streaks.

    Returns:
        dict: Comprehensive RL statistics including:
            - distributions: Thompson Sampling Beta distributions per (strategy, regime)
            - total_trades_analyzed: Total trades processed by RL
            - total_reward: Cumulative RL reward
            - avg_reward: Average RL reward per trade
            - exploration_rate: Current exploration rate (0-1)
            - confidence_adjustments: Per-strategy RL confidence adjustments
            - trade_history_summary: Win rate and profit summary
            - regime_performance: Per-strategy per-regime performance matrix
            - streaks: Current win/loss streaks per strategy

    CALLED BY: Frontend RL dashboard panel
    """
    try:
        brain = get_brain()
        return brain.get_rl_stats()
    except Exception as e:
        _raise_brain_route_error("retrieve RL stats", e)


# ════════════════════════════════════════════════════════════════
# LLM Insights
# ════════════════════════════════════════════════════════════════


class LLMConfigUpdate(BaseModel):
    provider: Literal["openai", "zai"]
    model: Optional[str] = None


@router.get("/llm-config")
@limiter.limit(READ_LIMIT)
async def get_llm_config(
    request: Request,
    _current_user: str = Depends(get_current_user),
):
    """
    PURPOSE: Return active LLM provider/model and available options.

    Returns:
        dict: {
            enabled: bool,
            provider: str,
            model: str,
            last_error: str | null,
            providers: [{provider, configured, default_model, base_url}],
            models: {provider: [model_ids]}
        }
    """
    try:
        brain = get_brain()
        return brain.get_llm_config()
    except Exception as e:
        _raise_brain_route_error("retrieve LLM config", e)


@router.patch("/llm-config")
@limiter.limit(WRITE_LIMIT)
async def set_llm_config(
    request: Request,
    body: LLMConfigUpdate,
    _current_user: str = Depends(get_current_user),
):
    """
    PURPOSE: Update active LLM provider/model for the Brain.

    This writes runtime config to Redis so both API + engine processes
    switch to the same provider/model.
    """
    try:
        brain = get_brain()
        return brain.set_llm_config(provider=body.provider, model=body.model)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        _raise_brain_route_error("update LLM config", e)


@router.get("/llm-insights")
@limiter.limit(READ_LIMIT)
async def get_llm_insights(
    request: Request,
    _current_user: str = Depends(get_current_user),
):
    """
    PURPOSE: Return LLM-generated trading insights and usage statistics.

    Returns GPT-powered market analyses, trade reviews, strategy suggestions,
    and regime change analyses along with token usage and cost tracking.

    Returns:
        dict: {
            insights: List of LLM insight dicts (newest first),
            stats: {total_calls, total_tokens_used, estimated_cost_usd, model, insights_count}
        }

    CALLED BY: Frontend LLM insights panel
    """
    try:
        brain = get_brain()
        # Engine process owns live LLM history; API process should read Redis copy.
        if brain._cycle_count > 0 and brain._llm:
            return {
                "insights": brain._llm.get_insights(),
                "stats": brain._llm.get_stats(),
            }
        redis_state = brain.load_from_redis()
        if redis_state:
            redis_insights = redis_state.get("llm_insights")
            redis_stats = redis_state.get("llm_stats")
            if redis_insights is not None and redis_stats is not None:
                return {
                    "insights": redis_insights,
                    "stats": redis_stats,
                }
        if brain._llm:
            return {
                "insights": brain._llm.get_insights(),
                "stats": brain._llm.get_stats(),
            }
        llm_config = brain.get_llm_config()
        return {
            "insights": [],
            "stats": {
                "total_calls": 0,
                "total_tokens_used": 0,
                "estimated_cost_usd": 0,
                "model": "none",
                "provider": "none",
                "insights_count": 0,
                "last_error": llm_config.get("last_error"),
                "message": llm_config.get("last_error")
                or "LLM not configured -- set provider API key to enable",
            },
        }
    except Exception as e:
        _raise_brain_route_error("retrieve LLM insights", e)


# ════════════════════════════════════════════════════════════════
# Auto-Allocation Status
# ════════════════════════════════════════════════════════════════


@router.get("/auto-allocation-status")
@limiter.limit(READ_LIMIT)
async def get_auto_allocation_status(
    request: Request,
    _current_user: str = Depends(get_current_user),
):
    """
    PURPOSE: Return auto-allocation engine status including fitness scores,
    rebalance history, and configuration.

    Returns:
        dict: {
            enabled: bool,
            trades_since_rebalance: int,
            trades_until_next: int,
            total_rebalances: int,
            last_fitness_scores: dict,
            last_allocations: dict,
            rebalance_history: list,
            config: dict,
        }

    CALLED BY: Frontend AllocationManager component
    """
    try:
        brain = get_brain()
        return brain.get_auto_allocation_status()
    except Exception as e:
        _raise_brain_route_error("retrieve auto-allocation status", e)


class AutoAllocationToggle(BaseModel):
    enabled: bool


@router.patch("/auto-allocation-status")
@limiter.limit(WRITE_LIMIT)
async def toggle_auto_allocation(
    request: Request,
    body: AutoAllocationToggle,
    _current_user: str = Depends(get_current_user),
):
    """
    PURPOSE: Enable or disable auto-allocation.

    Args:
        body: {"enabled": bool}

    Returns:
        dict: Updated auto-allocation status

    CALLED BY: Frontend AllocationManager toggle
    """
    try:
        brain = get_brain()
        brain.set_auto_allocation_enabled(body.enabled)
        return brain.get_auto_allocation_status()
    except Exception as e:
        _raise_brain_route_error("update auto-allocation status", e)
