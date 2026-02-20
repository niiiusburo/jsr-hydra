"""
PURPOSE: Rate limiting configuration for JSR Hydra API using slowapi.

Provides a shared Limiter instance keyed by client IP address and
pre-defined rate limit strings for different endpoint categories:
    - AUTH_LIMIT:    strict  (5/minute)  — login, token endpoints
    - WRITE_LIMIT:   moderate (30/minute) — kill switch, trade creation, strategy updates
    - READ_LIMIT:    relaxed  (60/minute) — list/get endpoints, dashboard, stats
"""

from slowapi import Limiter
from slowapi.util import get_remote_address

# Shared limiter instance — keyed by client IP
limiter = Limiter(key_func=get_remote_address)

# ── Rate limit tiers ──────────────────────────────────────────
AUTH_LIMIT = "5/minute"
WRITE_LIMIT = "30/minute"
READ_LIMIT = "60/minute"
