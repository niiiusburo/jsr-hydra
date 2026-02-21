"""
PURPOSE: Redis-backed runtime settings store for JSR Hydra trading system.

Provides a singleton RuntimeSettings class that persists all tunable runtime
parameters to Redis so both the API and engine processes share the same
configuration. Changes take effect on the next read — no restart required.

All settings are validated for type and range before being saved.

CALLED BY:
    - api/routes_settings.py — read/write via REST endpoints
    - brain/learner.py — reads learning params at runtime
    - brain/auto_allocator.py — reads allocator params at runtime
"""

import json
from datetime import datetime, timezone
from typing import Any, Optional

import redis

from app.config.settings import settings
from app.utils.logger import get_logger

logger = get_logger("config.runtime_settings")

RUNTIME_SETTINGS_REDIS_KEY = "jsr:settings:runtime"

# ════════════════════════════════════════════════════════════════
# Schema Definition
# ════════════════════════════════════════════════════════════════

# Each setting definition: key -> {label, type, default, *range or choices}
_SCHEMA: dict[str, dict] = {
    # ── Learning params ─────────────────────────────────────────
    "exploration_rate": {
        "label": "Exploration Rate",
        "category": "learning",
        "type": "float",
        "default": 0.10,
        "min": 0.01,
        "max": 0.30,
        "description": "Fraction of signals allowed through despite RL concerns (exploration vs exploitation).",
    },
    "min_trades_for_adjustment": {
        "label": "Min Trades for Adjustment",
        "category": "learning",
        "type": "int",
        "default": 5,
        "min": 3,
        "max": 20,
        "description": "Minimum trades in context before confidence adjustments are applied.",
    },
    "max_trade_history": {
        "label": "Max Trade History",
        "category": "learning",
        "type": "int",
        "default": 200,
        "min": 50,
        "max": 2000,
        "description": "Rolling window size for trade history kept in memory.",
    },
    "streak_warning_threshold": {
        "label": "Streak Warning Threshold",
        "category": "learning",
        "type": "int",
        "default": 3,
        "min": 2,
        "max": 8,
        "description": "Consecutive win/loss streak length that triggers a warning or confidence change.",
    },
    "confidence_lookback": {
        "label": "Confidence Lookback",
        "category": "learning",
        "type": "int",
        "default": 20,
        "min": 10,
        "max": 50,
        "description": "Number of recent trades per strategy used when recalculating confidence adjustments.",
    },
    "learning_speed": {
        "label": "Learning Speed",
        "category": "learning",
        "type": "str",
        "default": "normal",
        "choices": ["conservative", "normal", "aggressive"],
        "description": "Overall pace of adaptation. Aggressive reacts faster but is noisier.",
    },
    "automation_level": {
        "label": "Automation Level",
        "category": "learning",
        "type": "str",
        "default": "suggest",
        "choices": ["monitor", "suggest", "semi_auto", "full_auto"],
        "description": "How much the brain is allowed to act autonomously on its recommendations.",
    },
    # ── Allocator params ─────────────────────────────────────────
    "rebalance_interval": {
        "label": "Rebalance Interval (trades)",
        "category": "allocator",
        "type": "int",
        "default": 10,
        "min": 5,
        "max": 50,
        "description": "Number of completed trades between automatic allocation rebalances.",
    },
    "max_change_per_rebalance": {
        "label": "Max Change per Rebalance (%)",
        "category": "allocator",
        "type": "float",
        "default": 5.0,
        "min": 1.0,
        "max": 20.0,
        "description": "Maximum percentage-point shift any strategy's allocation can move in one rebalance.",
    },
    "min_allocation_pct": {
        "label": "Min Allocation (%)",
        "category": "allocator",
        "type": "float",
        "default": 5.0,
        "min": 1.0,
        "max": 15.0,
        "description": "Floor allocation percentage so no strategy is completely starved.",
    },
    "max_allocation_pct": {
        "label": "Max Allocation (%)",
        "category": "allocator",
        "type": "float",
        "default": 50.0,
        "min": 20.0,
        "max": 80.0,
        "description": "Ceiling allocation percentage to prevent over-concentration in one strategy.",
    },
    # ── Risk params ───────────────────────────────────────────────
    "max_drawdown_pct": {
        "label": "Max Drawdown (%)",
        "category": "risk",
        "type": "float",
        "default": 15.0,
        "min": 5.0,
        "max": 30.0,
        "description": "Maximum allowable equity drawdown before trading is halted.",
    },
    "daily_loss_limit_pct": {
        "label": "Daily Loss Limit (%)",
        "category": "risk",
        "type": "float",
        "default": 5.0,
        "min": 1.0,
        "max": 10.0,
        "description": "Maximum daily loss as a percentage of account equity before trading stops for the day.",
    },
    "per_trade_risk_pct": {
        "label": "Per-Trade Risk (%)",
        "category": "risk",
        "type": "float",
        "default": 1.0,
        "min": 0.25,
        "max": 3.0,
        "description": "Fraction of account equity risked per trade when calculating lot size.",
    },
    "max_lots": {
        "label": "Max Lots",
        "category": "risk",
        "type": "float",
        "default": 0.01,
        "min": 0.01,
        "max": 10.0,
        "description": "Hard cap on position size in lots regardless of risk calculation.",
    },
    # ── Pattern settings ──────────────────────────────────────────
    "hour_filter_enabled": {
        "label": "Hour Filter Enabled",
        "category": "patterns",
        "type": "bool",
        "default": False,
        "description": "When enabled, the brain avoids trading during historically poor hours.",
    },
    "dow_filter_enabled": {
        "label": "Day-of-Week Filter Enabled",
        "category": "patterns",
        "type": "bool",
        "default": False,
        "description": "When enabled, the brain avoids trading on historically poor weekdays.",
    },
    "min_trades_for_pattern": {
        "label": "Min Trades for Pattern",
        "category": "patterns",
        "type": "int",
        "default": 8,
        "min": 3,
        "max": 30,
        "description": "Minimum trades required in a time bucket before that pattern is acted upon.",
    },
    # ── Exploration decay ─────────────────────────────────────────
    "exploration_decay_enabled": {
        "label": "Exploration Decay Enabled",
        "category": "exploration_decay",
        "type": "bool",
        "default": False,
        "description": "When enabled, exploration rate is gradually reduced as total trade count grows.",
    },
    "exploration_decay_after_trades": {
        "label": "Exploration Decay After Trades",
        "category": "exploration_decay",
        "type": "int",
        "default": 500,
        "min": 100,
        "max": 5000,
        "description": "Total trades after which exploration decay begins.",
    },
    "exploration_decay_target": {
        "label": "Exploration Decay Target",
        "category": "exploration_decay",
        "type": "float",
        "default": 0.02,
        "min": 0.01,
        "max": 0.10,
        "description": "Minimum exploration rate the decay will reduce to.",
    },
}

# Ordered category list for frontend grouping
_CATEGORY_ORDER = ["learning", "allocator", "risk", "patterns", "exploration_decay"]


# ════════════════════════════════════════════════════════════════
# RuntimeSettings Class
# ════════════════════════════════════════════════════════════════


class RuntimeSettings:
    """
    PURPOSE: Redis-backed singleton for tunable runtime parameters.

    Loads settings from Redis on first access and caches them in memory.
    Writes are validated and immediately persisted to Redis so all processes
    pick up changes on their next read.

    CALLED BY:
        - api/routes_settings.py — GET/PATCH/POST/schema endpoints
        - brain/learner.py — learning params at runtime
        - brain/auto_allocator.py — allocator params at runtime
    """

    def __init__(self) -> None:
        self._cache: dict[str, Any] = {}
        self._loaded: bool = False

    # ------------------------------------------------------------------ #
    #  Redis connection
    # ------------------------------------------------------------------ #

    def _get_redis(self) -> redis.Redis:
        """Return a synchronous Redis connection using the configured URL."""
        return redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)

    # ------------------------------------------------------------------ #
    #  Load / Save
    # ------------------------------------------------------------------ #

    def _load_from_redis(self) -> None:
        """
        PURPOSE: Populate the in-memory cache from Redis.

        Falls back to schema defaults for any key missing from Redis.
        Safe to call on every request if needed — errors are logged and
        the cache is populated from defaults so the system stays functional.

        CALLED BY: _ensure_loaded()
        """
        defaults = {key: defn["default"] for key, defn in _SCHEMA.items()}
        try:
            r = self._get_redis()
            raw = r.get(RUNTIME_SETTINGS_REDIS_KEY)
            if raw:
                stored = json.loads(raw)
                # Merge: stored values override defaults; unknown keys are ignored
                merged = {**defaults, **{k: v for k, v in stored.items() if k in _SCHEMA}}
                self._cache = merged
                logger.info(
                    "runtime_settings_loaded",
                    key_count=len(self._cache),
                    source="redis",
                )
            else:
                self._cache = defaults
                logger.info(
                    "runtime_settings_loaded",
                    key_count=len(self._cache),
                    source="defaults",
                )
        except Exception as e:
            logger.warning("runtime_settings_load_failed", error=str(e))
            self._cache = defaults
        finally:
            self._loaded = True

    def _save_to_redis(self) -> None:
        """
        PURPOSE: Persist the in-memory cache to Redis as JSON.

        CALLED BY: set(), update(), reset_to_defaults()

        Raises:
            RuntimeError: If the Redis write fails (callers may re-raise as HTTPException).
        """
        try:
            r = self._get_redis()
            payload = {
                **self._cache,
                "_updated_at": datetime.now(timezone.utc).isoformat(),
            }
            r.set(RUNTIME_SETTINGS_REDIS_KEY, json.dumps(payload))
            logger.info("runtime_settings_saved", key_count=len(self._cache))
        except Exception as e:
            logger.error("runtime_settings_save_failed", error=str(e))
            raise RuntimeError(f"Failed to persist runtime settings: {e}") from e

    def _ensure_loaded(self) -> None:
        """Load from Redis if not yet loaded in this process."""
        if not self._loaded:
            self._load_from_redis()

    # ------------------------------------------------------------------ #
    #  Public API
    # ------------------------------------------------------------------ #

    def get(self, key: str) -> Any:
        """
        PURPOSE: Return the current value of a single setting.

        Falls back to the schema default if the key is not in the cache.

        Args:
            key: Setting name as defined in _SCHEMA.

        Returns:
            The current value, or the schema default, or None if key is unknown.

        CALLED BY: brain/learner.py, brain/auto_allocator.py, routes_settings.py
        """
        self._ensure_loaded()
        if key not in _SCHEMA:
            logger.warning("runtime_settings_unknown_key", key=key)
            return None
        return self._cache.get(key, _SCHEMA[key]["default"])

    def set(self, key: str, value: Any) -> None:
        """
        PURPOSE: Validate and save a single setting.

        Args:
            key: Setting name as defined in _SCHEMA.
            value: New value. Must pass type and range validation.

        Raises:
            ValueError: If key is unknown, type is wrong, or value is out of range.
            RuntimeError: If Redis write fails.

        CALLED BY: update(), routes_settings.py PATCH endpoint
        """
        self._ensure_loaded()
        if key not in _SCHEMA:
            raise ValueError(f"Unknown setting key: '{key}'")

        validated = self._validate(key, value)
        self._cache[key] = validated
        self._save_to_redis()
        logger.info("runtime_setting_updated", key=key, value=validated)

    def update(self, partial_dict: dict) -> None:
        """
        PURPOSE: Bulk-update multiple settings atomically.

        Validates all values first; if any fail, no changes are saved.

        Args:
            partial_dict: {key: value} pairs to update.

        Raises:
            ValueError: If any key is unknown or value is invalid.
            RuntimeError: If Redis write fails.

        CALLED BY: routes_settings.py PATCH endpoint
        """
        self._ensure_loaded()
        validated_updates: dict[str, Any] = {}
        for key, value in partial_dict.items():
            if key.startswith("_"):
                continue  # Skip internal metadata keys
            if key not in _SCHEMA:
                raise ValueError(f"Unknown setting key: '{key}'")
            validated_updates[key] = self._validate(key, value)

        self._cache.update(validated_updates)
        self._save_to_redis()
        logger.info(
            "runtime_settings_bulk_updated",
            updated_keys=list(validated_updates.keys()),
        )

    def get_all(self) -> dict:
        """
        PURPOSE: Return all current settings grouped by category.

        Returns:
            dict: {
                "learning": {key: value, ...},
                "allocator": {key: value, ...},
                "risk": {key: value, ...},
                "patterns": {key: value, ...},
                "exploration_decay": {key: value, ...},
            }

        CALLED BY: routes_settings.py GET endpoint
        """
        self._ensure_loaded()
        grouped: dict[str, dict] = {cat: {} for cat in _CATEGORY_ORDER}
        for key, defn in _SCHEMA.items():
            cat = defn["category"]
            grouped.setdefault(cat, {})[key] = self._cache.get(key, defn["default"])
        return grouped

    def get_schema(self) -> dict:
        """
        PURPOSE: Return full setting definitions for frontend form generation.

        Returns the schema grouped by category, including label, type,
        default, range/choices, and description for each setting.

        Returns:
            dict: {category: [{key, label, type, default, ...}, ...], ...}

        CALLED BY: routes_settings.py GET /schema endpoint
        """
        grouped: dict[str, list] = {cat: [] for cat in _CATEGORY_ORDER}
        for key, defn in _SCHEMA.items():
            cat = defn["category"]
            entry: dict[str, Any] = {
                "key": key,
                "label": defn["label"],
                "type": defn["type"],
                "default": defn["default"],
                "description": defn.get("description", ""),
                "current_value": self._cache.get(key, defn["default"]) if self._loaded else defn["default"],
            }
            if "min" in defn:
                entry["min"] = defn["min"]
            if "max" in defn:
                entry["max"] = defn["max"]
            if "choices" in defn:
                entry["choices"] = defn["choices"]
            grouped.setdefault(cat, []).append(entry)
        return {"categories": _CATEGORY_ORDER, "settings": grouped}

    def reset_to_defaults(self) -> dict:
        """
        PURPOSE: Reset all settings to their schema defaults and persist to Redis.

        Returns:
            dict: The new (default) grouped settings via get_all().

        CALLED BY: routes_settings.py POST /reset endpoint
        """
        self._cache = {key: defn["default"] for key, defn in _SCHEMA.items()}
        self._loaded = True
        self._save_to_redis()
        logger.info("runtime_settings_reset_to_defaults")
        return self.get_all()

    def reload(self) -> None:
        """
        PURPOSE: Force a reload from Redis, discarding the in-memory cache.

        Useful after external changes to Redis or at startup.

        CALLED BY: optional startup hooks, tests
        """
        self._loaded = False
        self._load_from_redis()

    # ------------------------------------------------------------------ #
    #  Validation
    # ------------------------------------------------------------------ #

    def _validate(self, key: str, value: Any) -> Any:
        """
        PURPOSE: Validate and coerce a value against the schema definition.

        Args:
            key: Setting name.
            value: Raw value to validate.

        Returns:
            The coerced/validated value.

        Raises:
            ValueError: If type coercion fails or value is out of allowed range/choices.
        """
        defn = _SCHEMA[key]
        expected_type = defn["type"]

        # Type coercion
        try:
            if expected_type == "float":
                coerced = float(value)
            elif expected_type == "int":
                coerced = int(value)
            elif expected_type == "bool":
                if isinstance(value, bool):
                    coerced = value
                elif isinstance(value, str):
                    coerced = value.lower() in ("true", "1", "yes")
                else:
                    coerced = bool(value)
            elif expected_type == "str":
                coerced = str(value)
            else:
                coerced = value
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"Setting '{key}' expects type {expected_type}, got {type(value).__name__}: {exc}"
            ) from exc

        # Range check for numeric types
        if expected_type in ("float", "int"):
            if "min" in defn and coerced < defn["min"]:
                raise ValueError(
                    f"Setting '{key}' value {coerced} is below minimum {defn['min']}"
                )
            if "max" in defn and coerced > defn["max"]:
                raise ValueError(
                    f"Setting '{key}' value {coerced} exceeds maximum {defn['max']}"
                )

        # Choices check for string types
        if expected_type == "str" and "choices" in defn:
            if coerced not in defn["choices"]:
                raise ValueError(
                    f"Setting '{key}' value '{coerced}' is not one of: {defn['choices']}"
                )

        return coerced


# ════════════════════════════════════════════════════════════════
# Module-level singleton
# ════════════════════════════════════════════════════════════════

runtime_settings: RuntimeSettings = RuntimeSettings()
