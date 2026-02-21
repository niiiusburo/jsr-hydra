"""
Path helpers for Brain persistence files.

Resolves writable locations for brain state files across environments:
- container runtime (default: /app/data/brain)
- local development / CI fallback (/tmp/jsr-hydra/brain)
"""

from pathlib import Path
from functools import lru_cache

from app.config.settings import settings
from app.utils.logger import get_logger

logger = get_logger("brain.paths")

DEFAULT_BRAIN_DATA_DIR = "/app/data/brain"
FALLBACK_BRAIN_DATA_DIR = "/tmp/jsr-hydra/brain"


@lru_cache(maxsize=1)
def get_brain_data_dir() -> Path:
    """Return a writable directory for brain persistence artifacts."""
    configured = (getattr(settings, "BRAIN_DATA_DIR", "") or DEFAULT_BRAIN_DATA_DIR).strip()
    candidates = [configured, FALLBACK_BRAIN_DATA_DIR]

    for candidate in candidates:
        path = Path(candidate)
        try:
            path.mkdir(parents=True, exist_ok=True)
            return path
        except Exception as e:
            logger.warning(
                "brain_data_dir_unwritable",
                path=str(path),
                error=str(e),
            )

    # Final fail-safe: best-effort temp path.
    tmp_path = Path("/tmp")
    logger.warning("brain_data_dir_fallback_tmp", path=str(tmp_path))
    return tmp_path


def resolve_brain_state_path(filename: str) -> str:
    """Resolve full persistence file path under a writable brain data directory."""
    safe_name = filename.strip().lstrip("/")
    return str(get_brain_data_dir() / safe_name)
