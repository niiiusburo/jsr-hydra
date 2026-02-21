"""
PURPOSE: Chart Vision Analysis API routes for JSR Hydra.

Accepts TradingView chart screenshot uploads and returns AI-powered analysis
of indicators, patterns, trend direction, key levels, and strategy suggestions.

CALLED BY: Frontend chart-vision dashboard page.
"""

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile

from app.api.auth import get_current_user
from app.chart_vision.analyzer import get_chart_analyzer
from app.core.rate_limit import limiter, WRITE_LIMIT, READ_LIMIT
from app.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/chart-vision", tags=["chart-vision"])

# Accepted MIME types for uploaded chart images
_ALLOWED_CONTENT_TYPES = {"image/png", "image/jpeg", "image/jpg", "image/webp"}
_MAX_FILE_BYTES = 10 * 1024 * 1024  # 10 MB


# ════════════════════════════════════════════════════════════════
# POST /api/chart-vision/analyze
# ════════════════════════════════════════════════════════════════


@router.post("/analyze")
@limiter.limit(WRITE_LIMIT)
async def analyze_chart(
    request: Request,
    image: UploadFile = File(..., description="Chart screenshot (PNG, JPG, or WEBP, max 10 MB)"),
    context: str = Form("", description="Optional context, e.g. 'BTCUSD 1H chart with custom indicators'"),
    _current_user: str = Depends(get_current_user),
) -> dict:
    """
    PURPOSE: Upload a chart screenshot and receive AI-powered technical analysis.

    Accepts multipart/form-data with:
      - image: PNG / JPG / WEBP file (max 10 MB)
      - context: optional free-text description of the chart

    Returns a JSON object containing detected indicators, chart patterns,
    trend direction, key price levels, a strategy suggestion, and a
    natural-language summary.

    CALLED BY: Frontend chart-vision page "Analyze" button.
    """
    # Validate content type
    content_type = (image.content_type or "").lower()
    if content_type not in _ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{content_type}'. Only PNG, JPG, and WEBP images are accepted.",
        )

    # Read and validate file size
    image_data = await image.read()
    if len(image_data) > _MAX_FILE_BYTES:
        raise HTTPException(
            status_code=400,
            detail=f"Image is too large ({len(image_data) // 1024} KB). Maximum allowed size is 10 MB.",
        )
    if len(image_data) == 0:
        raise HTTPException(status_code=400, detail="Uploaded image file is empty.")

    logger.info(
        "chart_vision_analyze_request",
        filename=image.filename,
        content_type=content_type,
        size_bytes=len(image_data),
        has_context=bool(context),
    )

    analyzer = get_chart_analyzer()
    result = await analyzer.analyze_chart(image_data, user_context=context)

    # Surface friendly error if no vision model is configured
    if result.get("error") == "no_vision_model":
        raise HTTPException(
            status_code=503,
            detail=result.get(
                "detail",
                "Chart vision analysis requires OPENAI_API_KEY to be configured (GPT-4o).",
            ),
        )

    logger.info(
        "chart_vision_analyze_complete",
        symbol=result.get("symbol", "UNKNOWN"),
        trend=result.get("trend", "UNKNOWN"),
        confidence=result.get("confidence"),
    )

    return result


# ════════════════════════════════════════════════════════════════
# GET /api/chart-vision/history
# ════════════════════════════════════════════════════════════════


@router.get("/history")
@limiter.limit(READ_LIMIT)
async def get_chart_vision_history(
    request: Request,
    _current_user: str = Depends(get_current_user),
) -> dict:
    """
    PURPOSE: Return recent chart analysis results (last 10, newest first).

    CALLED BY: Frontend chart-vision history sidebar.
    """
    analyzer = get_chart_analyzer()
    history = analyzer.get_history(limit=10)
    # Return newest first
    return {
        "history": list(reversed(history)),
        "count": len(history),
    }
