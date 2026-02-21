"""
PURPOSE: Fetch free news, sentiment, and economic calendar data for LLM-enhanced trading decisions.

Aggregates data from multiple free APIs (no API keys required unless noted):
1. Bitcoin Fear & Greed Index (Alternative.me) - crypto sentiment
2. CoinGecko Global Market Data - crypto market overview / dominance
3. Finnhub Economic Calendar - upcoming high-impact forex events (free key required)
4. CryptoPanic / RSS headlines - crypto news headlines

All fetchers are async (httpx) with graceful fallbacks. Each returns a dict
that can be injected into LLM prompts alongside technical indicators.

CALLED BY:
    - brain/llm_brain.py (analyze_market) — every 15 minutes
    - brain/brain.py (process_cycle) — for enriching market_data before LLM call
"""

import asyncio
import time
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

import httpx

from app.utils.logger import get_logger

logger = get_logger("brain.sentiment")

# ════════════════════════════════════════════════════════════════
# Cache Configuration
# ════════════════════════════════════════════════════════════════

# Simple in-memory cache to avoid hammering free APIs
_cache: Dict[str, Dict[str, Any]] = {}
CACHE_TTL = {
    "fear_greed": 600,        # 10 minutes (updates daily, but we check often)
    "crypto_global": 300,     # 5 minutes
    "economic_calendar": 900, # 15 minutes
    "crypto_news": 600,       # 10 minutes
}

HTTP_TIMEOUT = 10.0


def _get_cached(key: str) -> Optional[Any]:
    """Return cached value if still valid, else None."""
    entry = _cache.get(key)
    if entry and time.time() - entry["ts"] < CACHE_TTL.get(key, 300):
        return entry["data"]
    return None


def _set_cached(key: str, data: Any) -> None:
    """Store data in cache with current timestamp."""
    _cache[key] = {"data": data, "ts": time.time()}


# ════════════════════════════════════════════════════════════════
# 1. Bitcoin Fear & Greed Index (Alternative.me)
# ════════════════════════════════════════════════════════════════
# Endpoint: https://api.alternative.me/fng/
# No API key required. Rate limit: 60 req/min over 10-min window.
# Updates once daily. Returns 0-100 scale:
#   0-25: Extreme Fear, 26-46: Fear, 47-54: Neutral,
#   55-75: Greed, 76-100: Extreme Greed

FEAR_GREED_URL = "https://api.alternative.me/fng/"


async def fetch_fear_greed_index() -> Dict[str, Any]:
    """
    PURPOSE: Fetch the current Bitcoin Fear & Greed Index.

    Returns:
        Dict with keys: value (int 0-100), classification (str),
        timestamp (str ISO), source (str).
        On error: {"value": None, "classification": "unavailable", "error": str}

    CALLED BY: get_sentiment_data()
    """
    cached = _get_cached("fear_greed")
    if cached is not None:
        return cached

    result = {
        "value": None,
        "classification": "unavailable",
        "timestamp": None,
        "source": "alternative.me",
    }

    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
            resp = await client.get(FEAR_GREED_URL, params={"limit": 1})
            resp.raise_for_status()
            data = resp.json()

        entries = data.get("data", [])
        if entries:
            entry = entries[0]
            result["value"] = int(entry.get("value", 0))
            result["classification"] = entry.get("value_classification", "unknown")
            ts = entry.get("timestamp")
            if ts:
                result["timestamp"] = datetime.fromtimestamp(
                    int(ts), tz=timezone.utc
                ).isoformat()

        _set_cached("fear_greed", result)
        logger.info("fear_greed_fetched", value=result["value"], classification=result["classification"])

    except Exception as e:
        result["error"] = str(e)
        logger.warning("fear_greed_fetch_failed", error=str(e))

    return result


# ════════════════════════════════════════════════════════════════
# 2. CoinGecko Global Crypto Market Data
# ════════════════════════════════════════════════════════════════
# Endpoint: https://api.coingecko.com/api/v3/global
# No API key required for basic endpoints. Rate limit: ~10-30 req/min.
# Provides BTC dominance, total market cap change, volume change.

COINGECKO_GLOBAL_URL = "https://api.coingecko.com/api/v3/global"


async def fetch_crypto_global() -> Dict[str, Any]:
    """
    PURPOSE: Fetch global crypto market overview from CoinGecko.

    Returns:
        Dict with keys: btc_dominance (float %), market_cap_change_24h (float %),
        volume_change_24h (float %), total_market_cap_usd (float),
        active_cryptos (int), source (str).
        On error: returns partial dict with "error" key.

    CALLED BY: get_sentiment_data()
    """
    cached = _get_cached("crypto_global")
    if cached is not None:
        return cached

    result = {
        "btc_dominance": None,
        "market_cap_change_24h": None,
        "volume_change_24h": None,
        "total_market_cap_usd": None,
        "active_cryptos": None,
        "source": "coingecko",
    }

    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
            resp = await client.get(COINGECKO_GLOBAL_URL)
            resp.raise_for_status()
            data = resp.json().get("data", {})

        result["btc_dominance"] = round(
            data.get("market_cap_percentage", {}).get("btc", 0), 2
        )
        result["market_cap_change_24h"] = round(
            data.get("market_cap_change_percentage_24h_usd", 0), 2
        )
        # CoinGecko doesn't always include volume change; handle gracefully
        result["volume_change_24h"] = round(
            data.get("volume_change_percentage_24h_usd", 0), 2
        ) if data.get("volume_change_percentage_24h_usd") is not None else None
        result["total_market_cap_usd"] = data.get("total_market_cap", {}).get("usd")
        result["active_cryptos"] = data.get("active_cryptocurrencies")

        _set_cached("crypto_global", result)
        logger.info(
            "crypto_global_fetched",
            btc_dom=result["btc_dominance"],
            cap_change=result["market_cap_change_24h"],
        )

    except Exception as e:
        result["error"] = str(e)
        logger.warning("crypto_global_fetch_failed", error=str(e))

    return result


# ════════════════════════════════════════════════════════════════
# 3. Finnhub Economic Calendar (Free Tier — requires free API key)
# ════════════════════════════════════════════════════════════════
# Endpoint: https://finnhub.io/api/v1/calendar/economic
# Free tier: 60 calls/min. Key is free at finnhub.io/register.
# Returns upcoming economic events with impact levels.
# If no API key is configured, this fetcher returns an empty list gracefully.

FINNHUB_CALENDAR_URL = "https://finnhub.io/api/v1/calendar/economic"

# High-impact events that move forex/gold markets
HIGH_IMPACT_EVENTS = {
    "nonfarm payrolls", "non-farm payrolls", "nfp",
    "interest rate decision", "fed interest rate",
    "fomc", "federal funds rate",
    "cpi", "consumer price index", "inflation rate",
    "gdp", "gross domestic product",
    "unemployment rate", "jobless claims",
    "ecb interest rate", "boe interest rate",
    "pmi", "purchasing managers", "ism manufacturing",
    "retail sales", "trade balance",
    "pce price index", "core pce",
}

# Currencies we trade or that impact our symbols
RELEVANT_CURRENCIES = {"USD", "EUR", "GBP", "XAU", "BTC", "JPY", "CHF", "AUD", "CAD", "NZD"}


async def fetch_economic_calendar(
    finnhub_api_key: Optional[str] = None,
    days_ahead: int = 3,
) -> Dict[str, Any]:
    """
    PURPOSE: Fetch upcoming high-impact economic events from Finnhub.

    Args:
        finnhub_api_key: Finnhub API key. If None, returns empty result.
        days_ahead: How many days ahead to look for events.

    Returns:
        Dict with keys: events (list of event dicts), count (int),
        next_high_impact (str or None — next important event summary),
        source (str).
        Each event dict: {name, country, time, impact, estimate, previous, actual}

    CALLED BY: get_sentiment_data()
    """
    cached = _get_cached("economic_calendar")
    if cached is not None:
        return cached

    result: Dict[str, Any] = {
        "events": [],
        "count": 0,
        "next_high_impact": None,
        "source": "finnhub",
    }

    if not finnhub_api_key:
        result["note"] = "No Finnhub API key configured. Set FINNHUB_API_KEY in .env for economic calendar data."
        return result

    try:
        now = datetime.now(timezone.utc)
        from_date = now.strftime("%Y-%m-%d")
        to_date = (now + timedelta(days=days_ahead)).strftime("%Y-%m-%d")

        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
            resp = await client.get(
                FINNHUB_CALENDAR_URL,
                params={"from": from_date, "to": to_date, "token": finnhub_api_key},
            )
            resp.raise_for_status()
            data = resp.json()

        raw_events = data.get("economicCalendar", [])

        # Filter for relevant events
        filtered = []
        for evt in raw_events:
            event_name = (evt.get("event") or "").lower()
            country = (evt.get("country") or "").upper()
            impact = (evt.get("impact") or "").lower()

            # Keep high-impact events or events matching our known list
            is_high_impact = impact in ("high", "3")
            is_known_event = any(kw in event_name for kw in HIGH_IMPACT_EVENTS)
            is_relevant_country = country in RELEVANT_CURRENCIES or country in ("US", "EU", "GB", "JP", "CH", "AU", "CA", "NZ")

            if (is_high_impact or is_known_event) and is_relevant_country:
                filtered.append({
                    "name": evt.get("event", "Unknown"),
                    "country": country,
                    "time": evt.get("time", ""),
                    "impact": impact,
                    "estimate": evt.get("estimate"),
                    "previous": evt.get("prev"),
                    "actual": evt.get("actual"),
                    "unit": evt.get("unit", ""),
                })

        # Sort by time
        filtered.sort(key=lambda x: x.get("time", ""))

        result["events"] = filtered[:20]  # Cap at 20 events
        result["count"] = len(filtered)

        # Find next upcoming high-impact event
        now_iso = now.isoformat()
        for evt in filtered:
            evt_time = evt.get("time", "")
            if evt_time and evt_time > now_iso:
                result["next_high_impact"] = (
                    f"{evt['name']} ({evt['country']}) at {evt_time}"
                )
                break

        _set_cached("economic_calendar", result)
        logger.info("economic_calendar_fetched", event_count=len(filtered))

    except Exception as e:
        result["error"] = str(e)
        logger.warning("economic_calendar_fetch_failed", error=str(e))

    return result


# ════════════════════════════════════════════════════════════════
# 4. Crypto News Headlines (CryptoPanic RSS — no key, or CoinTelegraph RSS)
# ════════════════════════════════════════════════════════════════
# We parse lightweight RSS/Atom feeds as a fallback for free crypto news.
# CoinTelegraph RSS: https://cointelegraph.com/rss
# No API key. No rate limit documented (be reasonable: 1 req/10 min).

CRYPTO_NEWS_RSS_FEEDS = [
    "https://cointelegraph.com/rss",
]


async def fetch_crypto_news_headlines(max_headlines: int = 5) -> Dict[str, Any]:
    """
    PURPOSE: Fetch recent crypto news headlines from RSS feeds.

    Parses RSS XML to extract titles. Lightweight — no heavy dependencies.
    Falls back gracefully if feeds are unreachable.

    Args:
        max_headlines: Maximum number of headlines to return.

    Returns:
        Dict with keys: headlines (list of str), count (int), source (str).

    CALLED BY: get_sentiment_data()
    """
    cached = _get_cached("crypto_news")
    if cached is not None:
        return cached

    result: Dict[str, Any] = {
        "headlines": [],
        "count": 0,
        "source": "cointelegraph_rss",
    }

    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT, follow_redirects=True) as client:
            for feed_url in CRYPTO_NEWS_RSS_FEEDS:
                try:
                    resp = await client.get(feed_url)
                    resp.raise_for_status()
                    # Simple XML title extraction (avoids heavy XML parsing dependency)
                    content = resp.text
                    headlines = _extract_rss_titles(content, max_headlines)
                    if headlines:
                        result["headlines"] = headlines
                        result["count"] = len(headlines)
                        break
                except Exception as feed_err:
                    logger.debug("rss_feed_failed", url=feed_url, error=str(feed_err))
                    continue

        _set_cached("crypto_news", result)
        if result["headlines"]:
            logger.info("crypto_news_fetched", count=result["count"])

    except Exception as e:
        result["error"] = str(e)
        logger.warning("crypto_news_fetch_failed", error=str(e))

    return result


def _extract_rss_titles(xml_content: str, max_items: int = 5) -> List[str]:
    """
    Extract <title> values from RSS XML content without importing xml.etree.

    Skips the first <title> (usually the feed title itself) and returns
    up to max_items item titles.
    """
    titles: List[str] = []
    import re

    # Match all <title>...</title> or <title><![CDATA[...]]></title>
    pattern = re.compile(r"<title[^>]*>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>", re.DOTALL)
    matches = pattern.findall(xml_content)

    # Skip the first match (feed-level title) and collect item titles
    for match in matches[1:]:
        title = match.strip()
        if title and len(title) > 10:  # Skip very short/empty titles
            titles.append(title)
            if len(titles) >= max_items:
                break

    return titles


# ════════════════════════════════════════════════════════════════
# 5. Main Aggregator
# ════════════════════════════════════════════════════════════════


async def get_sentiment_data(
    finnhub_api_key: Optional[str] = None,
    include_news: bool = True,
) -> Dict[str, Any]:
    """
    PURPOSE: Aggregate all sentiment/news data into a single dict for LLM prompt injection.

    Fetches all sources concurrently. Each source fails independently.
    Returns a structured dict ready to be serialized into an LLM prompt.

    Args:
        finnhub_api_key: Optional Finnhub key for economic calendar.
        include_news: Whether to fetch RSS news (can be slow).

    Returns:
        Dict with keys: fear_greed, crypto_global, economic_calendar,
        news_headlines, summary (human-readable 1-liner), fetched_at.

    CALLED BY: brain/brain.py or brain/llm_brain.py before LLM calls
    """
    # Run all fetchers concurrently
    tasks = [
        fetch_fear_greed_index(),
        fetch_crypto_global(),
        fetch_economic_calendar(finnhub_api_key=finnhub_api_key),
    ]
    if include_news:
        tasks.append(fetch_crypto_news_headlines())

    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Unpack results with safe fallbacks
    fear_greed = results[0] if not isinstance(results[0], Exception) else {"value": None, "error": str(results[0])}
    crypto_global = results[1] if not isinstance(results[1], Exception) else {"error": str(results[1])}
    econ_calendar = results[2] if not isinstance(results[2], Exception) else {"events": [], "error": str(results[2])}
    news = (
        results[3] if len(results) > 3 and not isinstance(results[3], Exception)
        else {"headlines": []}
    )

    # Build human-readable summary line
    summary = _build_sentiment_summary(fear_greed, crypto_global, econ_calendar)

    return {
        "fear_greed": fear_greed,
        "crypto_global": crypto_global,
        "economic_calendar": econ_calendar,
        "news_headlines": news,
        "summary": summary,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }


def _build_sentiment_summary(
    fear_greed: Dict, crypto_global: Dict, econ_calendar: Dict
) -> str:
    """Build a one-line human-readable sentiment summary for the LLM."""
    parts: List[str] = []

    # Fear & Greed
    fg_val = fear_greed.get("value")
    fg_class = fear_greed.get("classification", "unknown")
    if fg_val is not None:
        parts.append(f"Crypto sentiment: {fg_class} ({fg_val}/100)")

    # Market cap change
    cap_change = crypto_global.get("market_cap_change_24h")
    if cap_change is not None:
        direction = "up" if cap_change >= 0 else "down"
        parts.append(f"Total crypto market cap {direction} {abs(cap_change):.1f}% in 24h")

    # BTC dominance
    btc_dom = crypto_global.get("btc_dominance")
    if btc_dom is not None:
        parts.append(f"BTC dominance {btc_dom:.1f}%")

    # Next high-impact event
    next_event = econ_calendar.get("next_high_impact")
    if next_event:
        parts.append(f"Next high-impact event: {next_event}")

    return ". ".join(parts) if parts else "Sentiment data unavailable."


# ════════════════════════════════════════════════════════════════
# 6. LLM Prompt Formatter
# ════════════════════════════════════════════════════════════════


def format_sentiment_for_prompt(sentiment_data: Dict[str, Any]) -> str:
    """
    PURPOSE: Format aggregated sentiment data into a text block for LLM prompt injection.

    Produces a structured, readable text block that can be appended to
    the market analysis prompt in llm_brain.py.

    Args:
        sentiment_data: Output from get_sentiment_data().

    Returns:
        str: Formatted text block for LLM prompt.

    CALLED BY: brain/llm_brain.py analyze_market (to enrich the user prompt)
    """
    lines: List[str] = []

    # Section: Market Sentiment
    lines.append("=== MARKET SENTIMENT & NEWS ===")

    # Fear & Greed
    fg = sentiment_data.get("fear_greed", {})
    fg_val = fg.get("value")
    if fg_val is not None:
        fg_class = fg.get("classification", "unknown")
        lines.append(f"Bitcoin Fear & Greed Index: {fg_val}/100 ({fg_class})")

        # Interpretation hints for the LLM
        if fg_val <= 25:
            lines.append("  -> Extreme fear often signals buying opportunities (contrarian indicator)")
        elif fg_val <= 40:
            lines.append("  -> Fear in market — potential accumulation zone, but watch for further downside")
        elif fg_val >= 75:
            lines.append("  -> Extreme greed — elevated risk of correction, consider tightening stops")
        elif fg_val >= 55:
            lines.append("  -> Greed — bullish momentum, but watch for overextension")
    else:
        lines.append("Bitcoin Fear & Greed Index: unavailable")

    # Crypto Global Market
    cg = sentiment_data.get("crypto_global", {})
    btc_dom = cg.get("btc_dominance")
    cap_change = cg.get("market_cap_change_24h")
    vol_change = cg.get("volume_change_24h")

    if any(v is not None for v in [btc_dom, cap_change, vol_change]):
        lines.append("")
        lines.append("Crypto Market Overview:")
        if btc_dom is not None:
            lines.append(f"  BTC Dominance: {btc_dom:.1f}%")
        if cap_change is not None:
            lines.append(f"  Total Market Cap 24h Change: {cap_change:+.2f}%")
        if vol_change is not None:
            lines.append(f"  Total Volume 24h Change: {vol_change:+.2f}%")

    # Economic Calendar
    econ = sentiment_data.get("economic_calendar", {})
    events = econ.get("events", [])
    if events:
        lines.append("")
        lines.append(f"Upcoming High-Impact Economic Events ({econ.get('count', 0)} total):")
        for evt in events[:7]:  # Show top 7
            est_str = f", Est: {evt['estimate']}" if evt.get("estimate") is not None else ""
            prev_str = f", Prev: {evt['previous']}" if evt.get("previous") is not None else ""
            actual_str = f", Actual: {evt['actual']}" if evt.get("actual") is not None else ""
            lines.append(
                f"  - {evt['name']} ({evt['country']}) @ {evt.get('time', 'TBD')}"
                f"{est_str}{prev_str}{actual_str}"
            )
        lines.append("  NOTE: Avoid opening new positions 30 min before/after high-impact events.")
    elif econ.get("note"):
        lines.append("")
        lines.append(f"Economic Calendar: {econ['note']}")

    # News Headlines
    news = sentiment_data.get("news_headlines", {})
    headlines = news.get("headlines", [])
    if headlines:
        lines.append("")
        lines.append("Recent Crypto News Headlines:")
        for h in headlines[:5]:
            lines.append(f"  - {h}")

    # Summary
    summary = sentiment_data.get("summary", "")
    if summary:
        lines.append("")
        lines.append(f"Sentiment Summary: {summary}")

    return "\n".join(lines)
