"""
PURPOSE: System-level API routes for JSR Hydra trading system.

Provides endpoints for health checks, version information, dashboard summary,
kill switch controls, and system status monitoring.
"""

import asyncio
import time
from datetime import datetime
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.config.constants import EventType
from app.config.settings import settings
from app.db.engine import get_db
from app.models.account import MasterAccount, EquitySnapshot
from app.models.strategy import Strategy
from app.models.trade import Trade
from app.models.system import SystemHealth
from app.schemas import HealthCheck, VersionInfo, DashboardSummary
from app.schemas.account import AccountResponse
from app.schemas.strategy import StrategyMetrics
from app.services.regime_service import RegimeService
from app.core.rate_limit import limiter, READ_LIMIT, WRITE_LIMIT
from app.utils.logger import get_logger
from app.version import get_version


logger = get_logger(__name__)
router = APIRouter(prefix="/system", tags=["system"])

_startup_time = time.time()

MT5_REST_URL = getattr(settings, "MT5_REST_URL", "http://jsr-mt5:18812")


def _build_open_position_sync(
    mt5_positions: list[dict],
    db_positions: list[dict],
) -> tuple[list[dict], str]:
    """
    Pick the position source used by dashboard cards/tables.

    Priority:
    1) Merge MT5 + DB OPEN trades when both exist (dedupe by ticket).
    2) Fallback to whichever source is available.
    """
    if mt5_positions and db_positions:
        # Build DB lookup by ticket for strategy enrichment
        db_by_ticket: dict[str, dict] = {}
        for db_pos in db_positions:
            db_ticket = db_pos.get("ticket")
            if db_ticket is not None:
                db_by_ticket[str(db_ticket)] = db_pos

        # Enrich MT5 positions with strategy metadata from DB
        merged = []
        for pos in mt5_positions:
            enriched = dict(pos)
            mt5_ticket = str(pos.get("ticket", ""))
            db_match = db_by_ticket.get(mt5_ticket)
            if db_match:
                enriched.setdefault("strategy_code", db_match.get("strategy_code"))
                enriched.setdefault("strategy_name", db_match.get("strategy_name"))
            merged.append(enriched)

        # Add DB-only positions (no MT5 match)
        mt5_tickets = {
            str(pos.get("ticket"))
            for pos in mt5_positions
            if pos.get("ticket") is not None
        }
        appended = 0
        for db_pos in db_positions:
            db_ticket = db_pos.get("ticket")
            if db_ticket is not None and str(db_ticket) in mt5_tickets:
                continue
            merged.append(db_pos)
            appended += 1

        if appended > 0:
            return merged, "hybrid"
        return merged, "mt5"

    if mt5_positions:
        return mt5_positions, "mt5"
    if db_positions:
        return db_positions, "db"
    return [], "none"


def _resolve_open_position_count(mt5_count: int, db_count: int) -> tuple[int, str]:
    """
    Build a unified count for UI while keeping source diagnostics.

    We use the maximum so pages do not show fewer opens just because one
    provider lags (e.g., bridge temporarily unavailable).
    """
    unified = max(mt5_count, db_count)
    if mt5_count == db_count:
        return unified, "mt5+db"
    if mt5_count > db_count:
        return unified, "mt5"
    return unified, "db"


async def _get_db_open_trade_rows(db: AsyncSession) -> list[Trade]:
    """Return all OPEN trades from DB ordered by newest first."""
    result = await db.execute(
        select(Trade)
        .where(Trade.status == "OPEN")
        .order_by(Trade.opened_at.desc())
    )
    return result.scalars().all()


async def _load_strategy_lookup(
    db: AsyncSession,
    strategy_ids: set[str],
) -> dict[str, dict]:
    """Load strategy code/name metadata for a set of strategy IDs."""
    clean_ids = {sid for sid in strategy_ids if sid}
    if not clean_ids:
        return {}

    result = await db.execute(
        select(Strategy.id, Strategy.code, Strategy.name)
        .where(Strategy.id.in_(clean_ids))
    )
    rows = result.all()
    return {
        str(strategy_id): {"code": code, "name": name}
        for strategy_id, code, name in rows
    }


async def _load_symbol_ticks(symbols: set[str]) -> dict[str, dict]:
    """Fetch live ticks for a symbol set from the MT5 bridge."""
    clean_symbols = sorted({s for s in symbols if s})
    if not clean_symbols:
        return {}

    responses = await asyncio.gather(
        *[_mt5_request(f"/tick/{symbol}") for symbol in clean_symbols],
        return_exceptions=True,
    )

    ticks: dict[str, dict] = {}
    for symbol, response in zip(clean_symbols, responses):
        if isinstance(response, dict) and (
            response.get("bid") is not None or response.get("ask") is not None
        ):
            ticks[symbol] = response
    return ticks


def _select_mark_price(direction: str, tick: Optional[dict]) -> Optional[float]:
    """Select a realistic mark/close price from tick for BUY/SELL."""
    if not tick:
        return None

    is_buy = (direction or "").upper() == "BUY"
    preferred = tick.get("bid") if is_buy else tick.get("ask")
    fallback = tick.get("ask") if is_buy else tick.get("bid")
    raw_price = preferred if preferred is not None else fallback

    if raw_price is None:
        return None

    try:
        return float(raw_price)
    except (TypeError, ValueError):
        return None


def _estimate_open_profit(
    *,
    symbol: str,
    direction: str,
    lots: float,
    entry_price: float,
    current_price: float,
) -> float:
    """Estimate unrealized profit from entry/current price using engine conventions."""
    point_diff = current_price - entry_price
    if (direction or "").upper() == "SELL":
        point_diff = -point_diff

    # Contract size depends on symbol — must match engine.py conventions.
    # 1 lot = contract_size units; profit = point_diff * lots * contract_size
    if any(c in symbol for c in ("BTC", "ETH", "LTC", "XRP")):
        contract_size = 1.0       # 1 lot = 1 coin
    elif "XAU" in symbol:
        contract_size = 100.0     # 1 lot = 100 oz
    else:
        contract_size = 100000.0  # 1 lot = 100k units (standard forex incl. JPY)

    return round(point_diff * lots * contract_size, 2)


def _map_open_trades_to_positions(
    trades: list[Trade],
    ticks_by_symbol: dict[str, dict],
    strategy_lookup: dict[str, dict],
) -> list[dict]:
    """Normalize DB OPEN trades into dashboard position rows with estimated live PnL."""
    positions: list[dict] = []
    for trade in trades:
        ticket = trade.mt5_ticket
        if ticket is None:
            ticket = f"DB-{str(trade.id)[:8]}"

        direction = (trade.direction or "").upper()
        symbol = trade.symbol or ""
        entry_price = float(trade.entry_price or 0.0)
        lots = float(trade.lots or 0.0)

        tick = ticks_by_symbol.get(symbol)
        current_price = _select_mark_price(direction, tick)
        estimated_profit = None
        if current_price is not None and lots > 0:
            estimated_profit = _estimate_open_profit(
                symbol=symbol,
                direction=direction,
                lots=lots,
                entry_price=entry_price,
                current_price=current_price,
            )

        strategy_key = str(trade.strategy_id) if trade.strategy_id else ""
        strategy_meta = strategy_lookup.get(strategy_key, {})
        strategy_code = strategy_meta.get("code")
        strategy_name = strategy_meta.get("name")

        positions.append({
            "ticket": ticket,
            "symbol": symbol,
            "type": direction,
            "lots": lots,
            "price_open": entry_price,
            "price_current": current_price,
            "profit": estimated_profit,
            "strategy_code": strategy_code,
            "strategy_name": strategy_name,
            "opened_at": trade.opened_at.isoformat() if trade.opened_at else None,
            "source": "DB_ESTIMATE" if current_price is not None else "DB",
        })

    return positions


def _sum_position_profit(positions: list[dict]) -> float:
    """Sum available position profits safely."""
    total = 0.0
    for pos in positions:
        raw = pos.get("profit")
        if raw is None:
            continue
        try:
            total += float(raw)
        except (TypeError, ValueError):
            continue
    return round(total, 2)


async def _mt5_request(path: str, method: str = "GET", json_data: dict = None, timeout: float = 5.0):
    """Make a request to the MT5 REST bridge."""
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            if method == "GET":
                resp = await client.get(f"{MT5_REST_URL}{path}")
            else:
                resp = await client.post(f"{MT5_REST_URL}{path}", json=json_data)
            if resp.status_code == 200:
                return resp.json()
            return None
    except Exception:
        return None


# ════════════════════════════════════════════════════════════════
# Health Check (Public — no auth required)
# ════════════════════════════════════════════════════════════════


@router.get("/health", response_model=None, tags=["health"])
@limiter.limit(READ_LIMIT)
async def health_check(request: Request, db: AsyncSession = Depends(get_db)):
    """Comprehensive health check with all service statuses."""
    services = {}
    overall_status = "ok"

    # Check database
    try:
        await db.execute(select(1))
        services["postgres"] = {"status": "connected"}
    except Exception as e:
        services["postgres"] = {"status": "disconnected", "error": str(e)}
        overall_status = "degraded"

    # Check Redis
    try:
        from app.events.bus import get_event_bus
        bus = get_event_bus()
        if bus._redis:
            await bus._redis.ping()
            services["redis"] = {"status": "connected"}
        else:
            services["redis"] = {"status": "disconnected"}
            overall_status = "degraded"
    except Exception:
        services["redis"] = {"status": "disconnected"}
        overall_status = "degraded"

    # Check MT5
    mt5_data = await _mt5_request("/account")
    if mt5_data and "balance" in mt5_data:
        services["mt5"] = {
            "status": "connected",
            "account": mt5_data.get("login"),
            "broker": mt5_data.get("server"),
            "balance": mt5_data.get("balance"),
        }
    else:
        services["mt5"] = {"status": "disconnected"}
        overall_status = "degraded"

    # Version
    version_data = get_version()

    uptime = time.time() - _startup_time

    # Trading info
    trading = {
        "dry_run": settings.DRY_RUN,
        "system_status": "RUNNING",
    }

    # Open positions count
    mt5_positions = await _mt5_request("/positions")
    mt5_open_positions = len(mt5_positions) if isinstance(mt5_positions, list) else 0

    db_open_trades = 0
    try:
        db_open_trades = len(await _get_db_open_trade_rows(db))
    except Exception as e:
        logger.warning("health_db_open_trades_error", error=str(e))
        try:
            await db.rollback()
        except Exception:
            pass

    unified_open_positions, open_source = _resolve_open_position_count(
        mt5_open_positions,
        db_open_trades,
    )
    trading["open_positions"] = unified_open_positions
    trading["open_positions_mt5"] = mt5_open_positions
    trading["open_trades_db"] = db_open_trades
    trading["open_positions_source"] = open_source

    return {
        "status": overall_status,
        "version": version_data.get("version", "1.0.0"),
        "codename": version_data.get("codename", "Hydra"),
        "uptime_seconds": round(uptime, 1),
        "services": services,
        "trading": trading,
    }


# ════════════════════════════════════════════════════════════════
# Version Info
# ════════════════════════════════════════════════════════════════


@router.get("/version", response_model=VersionInfo, tags=["version"])
@limiter.limit(READ_LIMIT)
async def get_system_version(
    request: Request,
    _current_user: str = Depends(get_current_user),
) -> VersionInfo:
    """Retrieve system version information."""
    version_data = get_version()
    return VersionInfo(
        version=version_data.get("version", "unknown"),
        codename=version_data.get("codename", "Hydra"),
        updated_at=version_data.get("updated_at", datetime.utcnow().isoformat()),
    )


# ════════════════════════════════════════════════════════════════
# Dashboard Summary — REAL DATA from MT5 + DB
# ════════════════════════════════════════════════════════════════


@router.get("/dashboard", response_model=None)
@limiter.limit(READ_LIMIT)
async def get_dashboard_summary(
    request: Request,
    _current_user: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Dashboard summary with real MT5 account data, positions, and strategy metrics."""
    try:
        return await _build_dashboard(db)
    except Exception as e:
        logger.error("dashboard_fatal_error", error=str(e))
        # Return a degraded but valid response instead of 500
        return {
            "account": None,
            "positions": [],
            "strategies": [],
            "recent_trades": [],
            "regime": None,
            "symbols": [],
            "system_status": "ERROR",
            "version": "unknown",
            "dry_run": settings.DRY_RUN,
            "uptime_seconds": round(time.time() - _startup_time, 1),
            "error": str(e),
        }


async def _build_dashboard(db: AsyncSession) -> dict:
    """Build dashboard data with graceful fallbacks for each section."""
    version_data = get_version()
    version = version_data.get("version", "1.0.0")

    # ── MT5 requests in parallel ──
    mt5_account, positions_raw, symbols_raw = await asyncio.gather(
        _mt5_request("/account"),
        _mt5_request("/positions"),
        _mt5_request("/symbols"),
    )

    account_data = None
    try:
        if mt5_account and "balance" in mt5_account:
            # Calculate drawdown
            peak_equity = mt5_account.get("equity", 0)
            try:
                stmt = select(MasterAccount).limit(1)
                result = await db.execute(stmt)
                db_account = result.scalar_one_or_none()
                if db_account and db_account.peak_equity:
                    peak_equity = max(db_account.peak_equity, mt5_account.get("equity", 0))
            except Exception:
                await db.rollback()  # master_accounts table may not exist yet

            drawdown_pct = 0.0
            if peak_equity > 0:
                drawdown_pct = max(0, (peak_equity - mt5_account.get("equity", 0)) / peak_equity * 100)

            account_data = {
                "login": mt5_account.get("login"),
                "server": mt5_account.get("server"),
                "balance": mt5_account.get("balance", 0),
                "equity": mt5_account.get("equity", 0),
                "margin": mt5_account.get("margin", 0),
                "free_margin": mt5_account.get("free_margin", 0),
                "margin_level": mt5_account.get("margin_level", 0),
                "profit": mt5_account.get("profit", 0),
                "currency": mt5_account.get("currency", "USD"),
                "leverage": mt5_account.get("leverage", 0),
                "peak_equity": peak_equity,
                "drawdown_pct": round(drawdown_pct, 2),
            }
    except Exception as e:
        logger.warning("dashboard_account_error", error=str(e))
        try:
            await db.rollback()
        except Exception:
            pass

    # ── Positions: MT5 primary + DB OPEN trades fallback ──
    mt5_positions = positions_raw if isinstance(positions_raw, list) else []
    db_open_trade_rows: list[Trade] = []
    db_open_positions: list[dict] = []
    try:
        db_open_trade_rows = await _get_db_open_trade_rows(db)
        strategy_lookup = await _load_strategy_lookup(
            db,
            {str(trade.strategy_id) for trade in db_open_trade_rows if trade.strategy_id},
        )
        ticks_by_symbol = await _load_symbol_ticks(
            {trade.symbol for trade in db_open_trade_rows if trade.symbol}
        )
        db_open_positions = _map_open_trades_to_positions(
            db_open_trade_rows,
            ticks_by_symbol,
            strategy_lookup,
        )
    except Exception as e:
        logger.warning("dashboard_db_open_trades_error", error=str(e))
        try:
            await db.rollback()
        except Exception:
            pass

    positions, open_positions_source = _build_open_position_sync(
        mt5_positions,
        db_open_positions,
    )
    open_positions_unified = len(positions)
    _, open_count_source = _resolve_open_position_count(
        len(mt5_positions),
        len(db_open_positions),
    )
    floating_profit = _sum_position_profit(positions)
    if account_data is not None and open_positions_source in {"db", "hybrid"}:
        account_data["profit"] = floating_profit

    # ── Strategies from DB ──
    strategies_data = []
    try:
        stmt = select(Strategy)
        result = await db.execute(stmt)
        strategies = result.scalars().all()
        for s in strategies:
            strategies_data.append({
                "code": s.code,
                "name": s.name,
                "status": s.status,
                "allocation_pct": s.allocation_pct,
                "win_rate": s.win_rate,
                "profit_factor": s.profit_factor,
                "total_trades": s.total_trades,
                "total_profit": s.total_profit,
            })
    except Exception as e:
        logger.warning("dashboard_strategies_error", error=str(e))
        try:
            await db.rollback()
        except Exception:
            pass

    # ── Recent trades from DB ──
    recent_trades = []
    try:
        stmt = select(Trade).order_by(Trade.created_at.desc()).limit(20)
        result = await db.execute(stmt)
        trades = result.scalars().all()
        for t in trades:
            recent_trades.append({
                "id": str(t.id),
                "symbol": t.symbol,
                "direction": t.direction,
                "lots": t.lots,
                "entry_price": t.entry_price,
                "exit_price": t.exit_price,
                "profit": t.profit,
                "net_profit": t.net_profit,
                "status": t.status,
                "opened_at": t.opened_at.isoformat() if t.opened_at else None,
                "closed_at": t.closed_at.isoformat() if t.closed_at else None,
            })
    except Exception as e:
        logger.warning("dashboard_trades_error", error=str(e))
        try:
            await db.rollback()
        except Exception:
            pass

    # ── Current regime from DB ──
    regime_data = None
    try:
        regime = await RegimeService.get_current_regime(db)
        if regime:
            regime_data = {
                "state": regime.regime.upper() if regime.regime else "UNKNOWN",
                "confidence": regime.confidence or 0,
                "conviction": regime.conviction_score or 0,
                "lastDetected": regime.detected_at.isoformat() if regime.detected_at else None,
            }
    except Exception as e:
        logger.warning("dashboard_regime_error", error=str(e))
        try:
            await db.rollback()
        except Exception:
            pass

    # ── Available symbols (already fetched in parallel above) ──
    symbol_names = symbols_raw if isinstance(symbols_raw, list) else []

    # ── Equity curve from snapshots ──
    equity_curve = []
    try:
        from datetime import timedelta
        cutoff = datetime.utcnow() - timedelta(days=30)

        # Find master account id for the snapshot query
        master_id_val = None
        try:
            stmt = select(MasterAccount).limit(1)
            result = await db.execute(stmt)
            db_acct = result.scalar_one_or_none()
            if db_acct:
                master_id_val = db_acct.id
        except Exception:
            await db.rollback()

        if master_id_val:
            try:
                snap_stmt = (
                    select(EquitySnapshot)
                    .where(
                        EquitySnapshot.master_id == master_id_val,
                        EquitySnapshot.timestamp >= cutoff,
                    )
                    .order_by(EquitySnapshot.timestamp.asc())
                )
                snap_result = await db.execute(snap_stmt)
                snapshots = snap_result.scalars().all()
                peak = 0.0
                for snap in snapshots:
                    if snap.equity > peak:
                        peak = snap.equity
                    dd = ((peak - snap.equity) / peak * 100) if peak > 0 else 0.0
                    equity_curve.append({
                        "timestamp": snap.timestamp.isoformat(),
                        "equity": snap.equity,
                        "balance": snap.balance,
                        "margin_used": snap.margin_used,
                        "drawdown": round(dd, 2),
                    })
            except Exception:
                await db.rollback()
    except Exception as e:
        logger.warning("dashboard_equity_curve_error", error=str(e))

    # ── System status ──
    uptime = time.time() - _startup_time

    return {
        "account": account_data,
        "positions": positions,
        "floating_profit": floating_profit,
        "open_positions": open_positions_unified,
        "open_positions_mt5": len(mt5_positions),
        "open_trades_db": len(db_open_positions),
        "open_positions_source": open_positions_source,
        "open_count_source": open_count_source,
        "strategies": strategies_data,
        "recent_trades": recent_trades,
        "regime": regime_data,
        "equity_curve": equity_curve,
        "symbols": symbol_names[:20],  # First 20 symbols
        "system_status": "RUNNING",
        "version": version,
        "dry_run": settings.DRY_RUN,
        "uptime_seconds": round(uptime, 1),
    }


# ════════════════════════════════════════════════════════════════
# Live Tick Price
# ════════════════════════════════════════════════════════════════


@router.get("/tick/{symbol}")
@limiter.limit(READ_LIMIT)
async def get_tick(
    request: Request,
    symbol: str,
    _current_user: str = Depends(get_current_user),
):
    """Get live tick price for a symbol (public, no auth)."""
    data = await _mt5_request(f"/tick/{symbol}")
    if data and "bid" in data:
        return data
    raise HTTPException(status_code=404, detail=f"No tick data for {symbol}")


# ════════════════════════════════════════════════════════════════
# Positions (from MT5)
# ════════════════════════════════════════════════════════════════


@router.get("/positions")
@limiter.limit(READ_LIMIT)
async def get_positions(
    request: Request,
    _current_user: str = Depends(get_current_user),
):
    """Get open positions from MT5."""
    data = await _mt5_request("/positions")
    if isinstance(data, list):
        return data
    return []


# ════════════════════════════════════════════════════════════════
# Kill Switch Controls
# ════════════════════════════════════════════════════════════════


@router.post("/kill-switch", status_code=status.HTTP_200_OK)
@limiter.limit(WRITE_LIMIT)
async def trigger_kill_switch(
    request: Request,
    reason: str = "Manual kill switch triggered",
    current_user: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Trigger kill switch — close all positions and halt trading."""
    logger.critical("kill_switch_triggered", reason=reason, triggered_by=current_user)

    # Close all open positions
    positions_closed = 0
    positions = await _mt5_request("/positions")
    if isinstance(positions, list):
        for pos in positions:
            ticket = pos.get("ticket")
            if ticket:
                result = await _mt5_request(f"/close/{ticket}", method="POST")
                if result and result.get("retcode") == 10009:
                    positions_closed += 1
                    logger.info("kill_switch_position_closed", ticket=ticket)

    # Publish event
    try:
        from app.events.bus import get_event_bus
        bus = get_event_bus()
        await bus.publish(EventType.KILL_SWITCH_TRIGGERED.value, {
            "reason": reason,
            "positions_closed": positions_closed,
            "triggered_by": current_user,
        })
    except Exception:
        pass

    return {
        "status": "halted",
        "reason": reason,
        "positions_closed": positions_closed,
        "timestamp": datetime.utcnow().isoformat(),
        "triggered_by": current_user,
    }


@router.post("/kill-switch/reset", status_code=status.HTTP_200_OK)
@limiter.limit(WRITE_LIMIT)
async def reset_kill_switch(
    request: Request,
    current_user: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Reset kill switch and resume trading."""
    logger.info("kill_switch_reset", reset_by=current_user)

    # Publish KILL_SWITCH_RESET event via the shared Redis event bus.
    # The engine process subscribes to this channel and will call
    # kill_switch.reset(admin_override=True) upon receiving this event.
    try:
        from app.events.bus import get_event_bus
        bus = get_event_bus()
        await bus.publish(EventType.KILL_SWITCH_RESET.value, {
            "reset_by": current_user,
            "timestamp": datetime.utcnow().isoformat(),
        })
    except Exception as e:
        logger.warning("kill_switch_reset_event_failed", error=str(e))

    return {
        "status": "running",
        "timestamp": datetime.utcnow().isoformat(),
        "reset_by": current_user,
    }
