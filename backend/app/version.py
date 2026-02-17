"""
PURPOSE: Manage version information for JSR Hydra trading system.

This module reads version data from version.json and exposes it through
a get_version() function. Version data is cached after the first read
to minimize file I/O operations.
"""

import json
from pathlib import Path
from typing import Any, Dict, Optional

_version_cache: Optional[Dict[str, Any]] = None


def get_version() -> Dict[str, Any]:
    """
    PURPOSE: Retrieve version information for JSR Hydra.

    Reads version.json from the project root and caches the result
    in a module-level variable. Subsequent calls return the cached
    version data without re-reading the file.

    Returns:
        Dict[str, Any]: Version information including version string,
            codename, updated_at timestamp, and changelog entries.

    Raises:
        FileNotFoundError: If version.json cannot be found in the project root.
        json.JSONDecodeError: If version.json is invalid JSON.
    """
    global _version_cache

    if _version_cache is not None:
        return _version_cache

    version_file: Path = Path(__file__).parent.parent.parent / "version.json"

    with open(version_file, "r") as f:
        _version_cache = json.load(f)

    return _version_cache
