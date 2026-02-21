"""
PURPOSE: Strategy Builder API routes for JSR Hydra.

Provides endpoints to parse natural language trading descriptions into
structured strategy definitions with Pine Script and Python code.

Authentication required for all endpoints.

CALLED BY:
    - Frontend strategy-builder dashboard page
    - External integrations via API
"""

import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.api.auth import get_current_user
from app.brain import get_brain
from app.core.rate_limit import limiter, READ_LIMIT, WRITE_LIMIT
from app.strategy_builder.nl_parser import NLStrategyParser
from app.strategy_builder.code_generator import StrategyCodeGenerator
from app.utils.logger import get_logger

logger = get_logger("api.strategy_builder")

router = APIRouter(prefix="/strategy-builder", tags=["strategy-builder"])

# In-process history store (last 20 parsed strategies per process)
# In production this could move to Redis for cross-process persistence.
_strategy_history: List[Dict] = []
_MAX_HISTORY = 20


def _store_strategy(strategy: Dict) -> None:
    """Append a strategy to the rolling in-process history."""
    global _strategy_history
    _strategy_history.append(strategy)
    if len(_strategy_history) > _MAX_HISTORY:
        _strategy_history = _strategy_history[-_MAX_HISTORY:]


def _get_parser_and_generator() -> tuple:
    """Resolve NLStrategyParser and StrategyCodeGenerator using the Brain's LLM."""
    brain = get_brain()
    if not brain._llm:
        raise HTTPException(
            status_code=503,
            detail=(
                "LLM is not configured. Set OPENAI_API_KEY or ZAI_API_KEY in settings "
                "and select a provider in the Brain dashboard."
            ),
        )
    parser = NLStrategyParser(brain._llm)
    generator = StrategyCodeGenerator()
    return parser, generator


def _raise_route_error(action: str, error: Exception) -> None:
    """Raise a consistent 500 response for strategy builder route failures."""
    logger.error(
        "strategy_builder_route_failed",
        action=action,
        error=str(error),
        exception_type=type(error).__name__,
    )
    raise HTTPException(status_code=500, detail=f"Failed to {action}")


# ════════════════════════════════════════════════════════════════
# Request / Response Models
# ════════════════════════════════════════════════════════════════


class ParseRequest(BaseModel):
    input: str = Field(..., min_length=5, max_length=2000, description="Natural language strategy description")
    symbol: Optional[str] = Field(default="BTCUSD", description="Trading symbol context")


class RefineRequest(BaseModel):
    strategy_id: str = Field(..., description="ID of a previously parsed strategy")
    feedback: str = Field(..., min_length=3, max_length=2000, description="Natural language refinement instructions")


class DeployRequest(BaseModel):
    strategy_id: str = Field(..., description="ID of a previously parsed strategy")
    deploy_as: Optional[str] = Field(default=None, description="Strategy slot code (F, G, H, ...)")


# ════════════════════════════════════════════════════════════════
# POST /api/strategy-builder/parse
# ════════════════════════════════════════════════════════════════


@router.post("/parse")
@limiter.limit(WRITE_LIMIT)
async def parse_strategy(
    request: Request,
    body: ParseRequest,
    _current_user: str = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    PURPOSE: Parse a natural language strategy description into structured rules.

    Calls the LLM to extract trading conditions, generates Pine Script and Python
    code, and returns a full strategy definition.

    Args:
        body.input: e.g. "Buy when price crosses above SMA44 and RSI is below 30"
        body.symbol: Trading symbol for context (default: BTCUSD)

    Returns:
        dict: Full strategy definition with conditions, Pine Script, Python code,
              risk parameters, confidence, warnings, and a unique strategy_id.
    """
    try:
        parser, generator = _get_parser_and_generator()
    except HTTPException:
        raise
    except Exception as e:
        _raise_route_error("initialize strategy builder", e)

    try:
        logger.info(
            "strategy_parse_request",
            input_length=len(body.input),
            symbol=body.symbol,
        )

        # Parse natural language -> structured definition
        context = {"symbol": body.symbol or "BTCUSD"}
        strategy_def = await parser.parse(body.input, context=context)

        if strategy_def.get("error"):
            raise HTTPException(
                status_code=422,
                detail=f"Strategy parsing failed: {strategy_def['warnings'][0] if strategy_def['warnings'] else 'Unknown error'}",
            )

        # Generate code if LLM did not already produce it
        if not strategy_def.get("pine_script"):
            strategy_def["pine_script"] = generator.generate_pine_script(strategy_def)
        if not strategy_def.get("python_code"):
            strategy_def["python_code"] = generator.generate_python_rule(strategy_def)

        # Always regenerate webhook payload template
        strategy_def["webhook_payload"] = generator.generate_webhook_payload_template(strategy_def)

        # Assign a unique ID for refinement and deploy tracking
        strategy_def["strategy_id"] = str(uuid.uuid4())
        strategy_def["symbol"] = body.symbol or "BTCUSD"

        _store_strategy(strategy_def)

        logger.info(
            "strategy_parse_success",
            strategy_id=strategy_def["strategy_id"],
            name=strategy_def.get("name"),
            conditions=len(strategy_def.get("conditions", [])),
        )

        return strategy_def

    except HTTPException:
        raise
    except Exception as e:
        _raise_route_error("parse strategy", e)


# ════════════════════════════════════════════════════════════════
# POST /api/strategy-builder/refine
# ════════════════════════════════════════════════════════════════


@router.post("/refine")
@limiter.limit(WRITE_LIMIT)
async def refine_strategy(
    request: Request,
    body: RefineRequest,
    _current_user: str = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    PURPOSE: Refine an existing parsed strategy with additional natural language input.

    Looks up the strategy from history by ID and sends it to the LLM along
    with the refinement feedback to produce an updated strategy definition.

    Args:
        body.strategy_id: ID of a previously parsed strategy
        body.feedback: e.g. "also add an EMA20 filter and tighten the SL"

    Returns:
        dict: Updated strategy definition with a new strategy_id.
    """
    try:
        parser, generator = _get_parser_and_generator()
    except HTTPException:
        raise
    except Exception as e:
        _raise_route_error("initialize strategy builder", e)

    # Look up existing strategy from history
    existing = next(
        (s for s in _strategy_history if s.get("strategy_id") == body.strategy_id),
        None,
    )
    if not existing:
        raise HTTPException(
            status_code=404,
            detail=f"Strategy {body.strategy_id} not found in recent history. Parse a new strategy first.",
        )

    try:
        logger.info(
            "strategy_refine_request",
            strategy_id=body.strategy_id,
            feedback_length=len(body.feedback),
        )

        refined = await parser.refine(existing, body.feedback)

        if refined.get("error"):
            raise HTTPException(
                status_code=422,
                detail=f"Strategy refinement failed: {refined['warnings'][0] if refined['warnings'] else 'Unknown error'}",
            )

        # Regenerate code from refined definition
        refined["pine_script"] = generator.generate_pine_script(refined)
        refined["python_code"] = generator.generate_python_rule(refined)
        refined["webhook_payload"] = generator.generate_webhook_payload_template(refined)

        # New ID for the refined version
        refined["strategy_id"] = str(uuid.uuid4())
        refined["refined_from"] = body.strategy_id
        refined["symbol"] = existing.get("symbol", "BTCUSD")

        _store_strategy(refined)

        logger.info(
            "strategy_refine_success",
            strategy_id=refined["strategy_id"],
            name=refined.get("name"),
        )

        return refined

    except HTTPException:
        raise
    except Exception as e:
        _raise_route_error("refine strategy", e)


# ════════════════════════════════════════════════════════════════
# GET /api/strategy-builder/history
# ════════════════════════════════════════════════════════════════


@router.get("/history")
@limiter.limit(READ_LIMIT)
async def get_strategy_history(
    request: Request,
    _current_user: str = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    PURPOSE: Return the last 20 strategy definitions created in this session.

    Returns:
        dict: {strategies: [...], count: int}
    """
    try:
        # Return newest first, with slim fields for list view
        history = []
        for s in reversed(_strategy_history):
            history.append({
                "strategy_id": s.get("strategy_id"),
                "name": s.get("name"),
                "description": s.get("description"),
                "action": s.get("action"),
                "conditions_count": len(s.get("conditions", [])),
                "confidence": s.get("confidence"),
                "suggested_timeframe": s.get("suggested_timeframe"),
                "created_at": s.get("created_at"),
                "symbol": s.get("symbol"),
                "warnings": s.get("warnings", []),
            })

        return {"strategies": history, "count": len(history)}

    except Exception as e:
        _raise_route_error("retrieve strategy history", e)


# ════════════════════════════════════════════════════════════════
# POST /api/strategy-builder/deploy
# ════════════════════════════════════════════════════════════════


@router.post("/deploy")
@limiter.limit(WRITE_LIMIT)
async def deploy_strategy(
    request: Request,
    body: DeployRequest,
    _current_user: str = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    PURPOSE: Save a parsed strategy definition for deployment as a live rule.

    Currently saves the strategy definition to the in-process store and marks
    it as "pending deploy". Full engine integration is a future milestone.

    Args:
        body.strategy_id: ID of a previously parsed strategy
        body.deploy_as: Strategy slot code (F, G, H, ...) — optional

    Returns:
        dict: Deployment status
    """
    existing = next(
        (s for s in _strategy_history if s.get("strategy_id") == body.strategy_id),
        None,
    )
    if not existing:
        raise HTTPException(
            status_code=404,
            detail=f"Strategy {body.strategy_id} not found in recent history.",
        )

    try:
        # Mark the strategy as queued for deployment
        existing["deploy_status"] = "pending"
        existing["deploy_as"] = body.deploy_as or "F"

        logger.info(
            "strategy_deploy_queued",
            strategy_id=body.strategy_id,
            deploy_as=existing["deploy_as"],
            name=existing.get("name"),
        )

        return {
            "status": "queued",
            "message": (
                f"Strategy '{existing.get('name')}' queued for deployment as slot "
                f"'{existing['deploy_as']}'. Full engine deployment coming in a future update."
            ),
            "strategy_id": body.strategy_id,
            "deploy_as": existing["deploy_as"],
        }

    except Exception as e:
        _raise_route_error("deploy strategy", e)
