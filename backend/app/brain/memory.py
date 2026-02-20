"""
PURPOSE: Persistent Brain Memory for JSR Hydra trading system.

Simple file-based persistence for the brain's learned state.
Saves to /tmp/jsr_brain_memory.json every 5 minutes and loads on startup.
This survives engine restarts but not container rebuilds.

CALLED BY: brain/learner.py — for state persistence and recovery
"""

import json
import os
from datetime import datetime, timezone
from typing import Optional

from app.brain.paths import resolve_brain_state_path
from app.utils.logger import get_logger

logger = get_logger("brain.memory")

MEMORY_FILE_PATH = resolve_brain_state_path("memory.json")


def get_memory_path() -> str:
    """
    PURPOSE: Return the file path used for brain memory persistence.

    Returns:
        str: Absolute path to the brain memory JSON file.

    CALLED BY: brain/learner.py, diagnostic endpoints
    """
    return MEMORY_FILE_PATH


def save_state(state: dict) -> bool:
    """
    PURPOSE: Serialize and save the brain learning state to disk.

    Writes the full brain state dictionary as JSON. Includes a
    _saved_at timestamp for staleness detection on reload.

    Args:
        state: The brain learning state dictionary to persist.

    Returns:
        bool: True if save succeeded, False otherwise.

    CALLED BY: brain/learner.py — periodic save (every 5 minutes)
    """
    try:
        state_copy = dict(state)
        state_copy["_saved_at"] = datetime.now(timezone.utc).isoformat()

        tmp_path = MEMORY_FILE_PATH + ".tmp"
        with open(tmp_path, "w") as f:
            json.dump(state_copy, f, indent=2, default=str)

        # Atomic rename to avoid partial writes
        os.replace(tmp_path, MEMORY_FILE_PATH)

        logger.info(
            "brain_memory_saved",
            path=MEMORY_FILE_PATH,
            trade_count=len(state.get("trade_history", [])),
            insight_count=len(state.get("insights", [])),
        )
        return True

    except Exception as e:
        logger.error(
            "brain_memory_save_failed",
            path=MEMORY_FILE_PATH,
            error=str(e),
        )
        return False


def load_state() -> Optional[dict]:
    """
    PURPOSE: Load and deserialize the brain learning state from disk.

    Reads the JSON file at MEMORY_FILE_PATH and returns the parsed
    dictionary. Returns None if file does not exist or is corrupt.

    Returns:
        dict or None: The loaded brain state, or None if unavailable.

    CALLED BY: brain/learner.py — on startup
    """
    if not os.path.exists(MEMORY_FILE_PATH):
        logger.info(
            "brain_memory_not_found",
            path=MEMORY_FILE_PATH,
            message="Starting with fresh brain state",
        )
        return None

    try:
        with open(MEMORY_FILE_PATH, "r") as f:
            state = json.load(f)

        saved_at = state.pop("_saved_at", "unknown")
        trade_count = len(state.get("trade_history", []))
        insight_count = len(state.get("insights", []))

        logger.info(
            "brain_memory_loaded",
            path=MEMORY_FILE_PATH,
            saved_at=saved_at,
            trade_count=trade_count,
            insight_count=insight_count,
        )
        return state

    except json.JSONDecodeError as e:
        logger.error(
            "brain_memory_corrupt",
            path=MEMORY_FILE_PATH,
            error=str(e),
            message="Starting with fresh brain state due to corrupt file",
        )
        return None

    except Exception as e:
        logger.error(
            "brain_memory_load_failed",
            path=MEMORY_FILE_PATH,
            error=str(e),
        )
        return None
