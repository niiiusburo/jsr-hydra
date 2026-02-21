"""
PURPOSE: RL model retraining service for JSR Hydra Brain.

Periodically checks for existing RL state files (Thompson Sampling
distributions, brain memory) and performs retraining when sufficient
data has accumulated. Exits gracefully when no models exist yet.

NOT YET IMPLEMENTED — this is a proper skeleton that:
  - Scans for RL state / model artifacts before doing any work
  - Runs on a configurable schedule (default: every 6 hours)
  - Exits cleanly if no models are found (instead of spinning forever)
  - Supports graceful shutdown via SIGINT/SIGTERM

Model / state file locations (set via env vars or defaults):
  - RL_STATE_PATH  : /app/data/brain/rl_state.json   (Thompson Sampling dists)
  - MEMORY_PATH    : /app/data/brain/memory.json      (brain learning state)
  - MODELS_DIR     : /app/models                      (future ML model artifacts)

CALLED BY: docker-compose (profile: retrainer) — `python -m app.engine.retrainer`
"""

import asyncio
import json
import os
import signal
from pathlib import Path

from app.utils.logger import get_logger

logger = get_logger("engine.retrainer")

# ---------------------------------------------------------------------------
# Configuration (overridable via environment variables)
# ---------------------------------------------------------------------------

# Where the learner saves RL state (Thompson Sampling distributions)
RL_STATE_PATH = os.getenv("RL_STATE_PATH", "/app/data/brain/rl_state.json")

# Where brain memory (trade history, insights) is persisted
MEMORY_PATH = os.getenv("MEMORY_PATH", "/app/data/brain/memory.json")

# Directory for future ML model artifacts (e.g., .pt, .onnx, .pkl files)
MODELS_DIR = os.getenv("MODELS_DIR", "/app/models")

# How often to check for retraining (seconds).  Default: 6 hours
RETRAIN_INTERVAL_SECONDS = int(os.getenv("RETRAIN_INTERVAL_SECONDS", str(6 * 3600)))

# Minimum number of trades in brain memory before retraining is worthwhile
MIN_TRADES_FOR_RETRAIN = int(os.getenv("MIN_TRADES_FOR_RETRAIN", "50"))


# ---------------------------------------------------------------------------
# Graceful shutdown
# ---------------------------------------------------------------------------

_shutdown_event = asyncio.Event()


def _handle_signal(sig: signal.Signals) -> None:
    logger.info("retrainer_signal_received", signal=sig.name)
    _shutdown_event.set()


# ---------------------------------------------------------------------------
# Model / state discovery
# ---------------------------------------------------------------------------


def _discover_rl_state() -> dict | None:
    """Load and return the RL state JSON if it exists, else None."""
    if not os.path.isfile(RL_STATE_PATH):
        return None
    try:
        with open(RL_STATE_PATH, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("retrainer_rl_state_unreadable", path=RL_STATE_PATH, error=str(exc))
        return None


def _discover_brain_memory() -> dict | None:
    """Load and return the brain memory JSON if it exists, else None."""
    if not os.path.isfile(MEMORY_PATH):
        return None
    try:
        with open(MEMORY_PATH, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("retrainer_memory_unreadable", path=MEMORY_PATH, error=str(exc))
        return None


def _discover_model_files() -> list[Path]:
    """Return a list of ML model files (*.pt, *.onnx, *.pkl, *.joblib) in MODELS_DIR."""
    model_dir = Path(MODELS_DIR)
    if not model_dir.is_dir():
        return []
    extensions = {".pt", ".onnx", ".pkl", ".joblib", ".h5", ".safetensors"}
    return sorted(
        p for p in model_dir.rglob("*") if p.suffix in extensions
    )


# ---------------------------------------------------------------------------
# Retraining logic (placeholder — fill in when Phase 3 is implemented)
# ---------------------------------------------------------------------------


async def _retrain_cycle() -> None:
    """
    Execute a single retraining cycle.

    Currently a no-op skeleton.  When Phase 3 is implemented, this will:
      1. Load latest trade history from brain memory
      2. Rebuild / fine-tune Thompson Sampling priors with offline data
      3. Optionally train a neural model on accumulated experience
      4. Save updated model artifacts to MODELS_DIR
    """
    # --- Step 1: Check for RL state ---
    rl_state = _discover_rl_state()
    if rl_state is None:
        logger.info("retrain_skip", reason="No RL state found", path=RL_STATE_PATH)
        return

    total_trades = rl_state.get("rl_total_trades", 0)
    logger.info("retrain_rl_state_found", total_trades=total_trades)

    # --- Step 2: Check brain memory for sufficient data ---
    memory = _discover_brain_memory()
    if memory is None:
        logger.info("retrain_skip", reason="No brain memory found", path=MEMORY_PATH)
        return

    trade_count = len(memory.get("trade_history", []))
    if trade_count < MIN_TRADES_FOR_RETRAIN:
        logger.info(
            "retrain_skip",
            reason="Insufficient trade history",
            trade_count=trade_count,
            min_required=MIN_TRADES_FOR_RETRAIN,
        )
        return

    # --- Step 3: Check for existing model files ---
    model_files = _discover_model_files()
    logger.info(
        "retrain_discovery_complete",
        trade_count=trade_count,
        rl_total_trades=total_trades,
        model_files_found=len(model_files),
        model_files=[str(p) for p in model_files[:10]],  # log first 10
    )

    # --- Step 4: Actual retraining (TODO — Phase 3) ---
    # When implemented, this section will:
    #   - Re-fit Thompson Sampling priors from offline trade batch
    #   - Train / fine-tune any neural RL models
    #   - Evaluate new model vs. baseline
    #   - Atomic-swap model files if new model is better
    logger.info(
        "retrain_placeholder",
        message="Retraining logic not yet implemented (Phase 3). "
                "Data is sufficient; will retrain once logic is added.",
        trade_count=trade_count,
    )


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------


async def main() -> None:
    """
    Entry point for the retrainer service.

    Behaviour:
      - On startup, checks whether any RL state or model files exist.
      - If nothing exists at all, logs clearly and exits (no point spinning).
      - If state exists, enters a scheduled loop, running _retrain_cycle()
        every RETRAIN_INTERVAL_SECONDS.
      - Shuts down cleanly on SIGINT / SIGTERM.
    """
    logger.info(
        "retrainer_starting",
        rl_state_path=RL_STATE_PATH,
        memory_path=MEMORY_PATH,
        models_dir=MODELS_DIR,
        retrain_interval_seconds=RETRAIN_INTERVAL_SECONDS,
        min_trades=MIN_TRADES_FOR_RETRAIN,
    )

    # Register signal handlers for graceful shutdown
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _handle_signal, sig)

    # Initial check: is there *anything* to work with?
    has_rl_state = os.path.isfile(RL_STATE_PATH)
    has_memory = os.path.isfile(MEMORY_PATH)
    has_models = bool(_discover_model_files())

    if not has_rl_state and not has_memory and not has_models:
        logger.info(
            "retrainer_exit_no_data",
            message="No RL state, brain memory, or model files found. "
                    "Nothing to retrain. Exiting gracefully. "
                    "The retrainer will be useful once the engine has "
                    "accumulated trading data.",
        )
        return

    logger.info(
        "retrainer_data_found",
        has_rl_state=has_rl_state,
        has_memory=has_memory,
        has_models=has_models,
        message="Entering retraining schedule loop",
    )

    # Schedule loop
    while not _shutdown_event.is_set():
        try:
            await _retrain_cycle()
        except Exception:
            logger.exception("retrain_cycle_error")

        # Wait for the next cycle or a shutdown signal
        try:
            await asyncio.wait_for(
                _shutdown_event.wait(),
                timeout=RETRAIN_INTERVAL_SECONDS,
            )
        except asyncio.TimeoutError:
            # Timeout means it is time for the next cycle
            pass

    logger.info("retrainer_shutdown", message="Retrainer stopped gracefully")


if __name__ == "__main__":
    asyncio.run(main())
