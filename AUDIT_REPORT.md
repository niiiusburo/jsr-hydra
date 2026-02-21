# JSR Hydra — Full Codebase Audit Report

**Date:** 2026-02-19
**Audited by:** 5 parallel AI agents (Claude Sonnet 4.6)
**Scope:** Backend, Frontend, Engine, Events, Services, Models, Schemas, Infrastructure

---

## Summary

| Severity | Count |
|----------|-------|
| CRITICAL | 2     |
| HIGH     | 11    |
| MEDIUM   | 18    |
| LOW      | 14    |
| **Total**| **45** |

---

## CRITICAL Issues (Must Fix — System Broken or Dangerous)

### C-19: Retrainer Is a Complete Stub
**File:** `backend/app/engine/retrainer.py`
**Issue:** The retrainer service runs in an infinite loop logging "No models to retrain yet" every 60 seconds. It does nothing. It's also never launched from docker-compose.
**Fix:** Either implement or remove. If keeping as placeholder, don't run it as a service.

### C-22-OLD: Insecure Default Credentials in Production
**File:** `backend/app/config/settings.py`
**Issue:** `JWT_SECRET="change-me-in-production"` and `ADMIN_PASSWORD="admin"` are hardcoded defaults with no enforcement. If `.env` is missing these, the system runs with known credentials.
**Fix:** Raise an error on startup if `JWT_SECRET` or `ADMIN_PASSWORD` are still at their defaults (when not in dev mode).

---

## HIGH Issues (Should Fix — Incorrect Behavior or Security Risk)

### H-01: No Auth on Most API Read Endpoints
**Files:** `routes_system.py`, `routes_trades.py` (GET), `routes_strategies.py` (GET), `routes_brain.py` (GET)
**Issue:** Dashboard, trades list, strategies list, brain status — all public. Anyone can view account balance, open positions, trading history.
**Fix:** Add `Depends(get_current_user)` to all endpoints that expose sensitive data.

### H-02: No Auth on Brain Auto-Allocation Toggle
**File:** `backend/app/api/routes_brain.py` (PATCH `/auto-allocation-status`)
**Issue:** Mutating endpoint with no authentication. Anyone can toggle auto-allocation on/off.
**Fix:** Add `Depends(get_current_user)`.

### H-06: Dashboard Page Bypasses Zustand Store
**File:** `frontend/app/dashboard/page.tsx`
**Issue:** Makes direct `fetch()` calls instead of using the Zustand store (`useDashboardStore`). Data is not shared with other components, causing redundant API calls.
**Fix:** Use the Zustand store for dashboard data.

### H-12: Two-Phase Trade Write Race Condition
**File:** `backend/app/engine/engine.py`
**Issue:** Trades are written as PENDING first, then updated to OPEN after MT5 confirmation. If the engine crashes between these two writes, trades remain stuck in PENDING forever.
**Fix:** Use a single transaction, or add a cleanup job for stale PENDING trades.

### H-16: equity_curve Not Populated
**File:** `backend/app/api/routes_system.py` → `backend/app/models/account.py`
**Issue:** The equity_curve field exists in the model but is never written to. Frontend equity chart always shows empty.
**Fix:** Record equity snapshots periodically (e.g., after each trade or on a schedule).

### H-18: EventType Enum Defined But Never Used
**File:** `backend/app/config/constants.py` → all event publishers
**Issue:** `EventType` enum is defined with proper event names, but all code uses raw strings (`"trade_closed"`, `"TRADE_CLOSED"`). No compile-time checking of event names.
**Fix:** Use `EventType.TRADE_CLOSED.value` everywhere for consistency.

### H-20: Frontend Dead/Orphaned Components
**Files:** `frontend/components/trades/TradeStats.tsx`, `TradeTable.tsx`, `TradeFilters.tsx`, `StrategyDetail.tsx`
**Issue:** These components exist but are never imported or used by any page. Dead code bloat.
**Fix:** Either integrate them into the pages that need them, or delete them.

### H-21: No Error Handling on Brain API Routes
**File:** `backend/app/api/routes_brain.py`
**Issue:** All brain endpoints have no try/except. Any Brain service error returns raw 500 with stack trace.
**Fix:** Add proper error handling with user-friendly error messages.

### H-25: No CSRF Protection
**File:** `backend/app/main.py`
**Issue:** No CSRF tokens for state-changing requests. Combined with credentials mode, this enables cross-site request forgery.
**Fix:** Add CSRF middleware or use SameSite cookies.

### H-27: No Rate Limiting on API
**File:** `backend/app/main.py`
**Issue:** No rate limiting middleware. Kill switch, trade creation, and auth endpoints can be hammered without restriction.
**Fix:** Add rate limiting (e.g., slowapi) at least for auth and critical endpoints.

### H-28: Caddy WebSocket Proxy May Timeout
**File:** `infra/caddy/Caddyfile`
**Issue:** No explicit WebSocket timeout configuration. Caddy's default timeouts may close long-lived WS connections prematurely.
**Fix:** Add `flush_interval -1` and appropriate timeouts for the `/ws/*` route.

---

## MEDIUM Issues (Should Address — Reduced Functionality)

### M-03: No Pagination on Strategies Endpoint
**File:** `backend/app/api/routes_strategies.py`
**Issue:** Returns all strategies without pagination. Not a problem with 4 strategies, but doesn't scale.

### M-05: No Request Timeout on Frontend Fetches
**File:** `frontend/app/dashboard/page.tsx` and other pages
**Issue:** `fetch()` calls have no timeout. If backend hangs, frontend hangs indefinitely.

### M-06: Engine Loop Has No Backoff on Repeated Failures
**File:** `backend/app/engine/engine.py`
**Issue:** If MT5 is disconnected, the engine loop retries every cycle with no exponential backoff, flooding logs.

### M-07: Trade Symbols Filter Fetches 100 Trades Just for Dropdown
**File:** `frontend/app/dashboard/trades/page.tsx` (line 53)
**Issue:** Fetches 100 trades just to extract unique symbols for the filter dropdown. Should have a dedicated `/symbols` endpoint.

### M-09: Frontend Trade Debounce on Every Keystroke
**File:** `frontend/app/dashboard/trades/page.tsx` (line 108-111)
**Issue:** 300ms debounce on filter changes is fine, but the timer resets on every dropdown change, causing unnecessary delays for select inputs.

### M-12: Session Breakout Strategy Hardcoded Times
**File:** `backend/app/strategies/session_breakout.py`
**Issue:** London/NY session times are hardcoded without timezone awareness. DST changes will shift trading windows.

### M-13: No Health Endpoint for Frontend
**File:** `frontend/` (missing)
**Issue:** No `/health` or `/api/health` endpoint for the Next.js frontend. Can't verify frontend is responsive.

### M-15: No Retry Logic for MT5 HTTP Requests
**File:** `backend/app/api/routes_system.py` (`_mt5_request`)
**Issue:** Single attempt with 5s timeout. Transient network issues cause immediate failure.

### M-16: Frontend Date Formatting Inconsistent
**File:** Multiple frontend files
**Issue:** Some files use `toLocaleDateString()`, others use custom formatting. No consistent date formatting utility.

### M-17: Trade Model Missing Commission/Swap Fields Display
**File:** `frontend/app/dashboard/trades/page.tsx`
**Issue:** Trade table doesn't show commission or swap, even though the backend model has these fields.

### M-20: No Error Boundary in Frontend
**File:** `frontend/app/layout.tsx`
**Issue:** No React error boundary. Any component crash takes down the entire page.

### M-22: No Backup Strategy for DB
**File:** Infrastructure
**Issue:** No automated database backup. PostgreSQL data could be lost on disk failure.

### M-24: No API Versioning
**File:** `backend/app/main.py`
**Issue:** All routes are under `/api/` with no version prefix. Breaking API changes will affect all clients.

### M-25: Frontend Bundle Size Not Optimized
**File:** `frontend/next.config.js`
**Issue:** No bundle analysis or optimization configuration. Recharts and other libraries may bloat the bundle.

### M-26: No Monitoring/Alerting Integration
**File:** Infrastructure
**Issue:** No Prometheus metrics, no Grafana dashboards, no alerting beyond the unimplemented Telegram TODO.

### M-33: Strategy Performance Never Reset
**File:** `backend/app/services/strategy_service.py`
**Issue:** No way to reset strategy performance metrics. If testing produces bad data, it permanently skews metrics.

### M-34: No Audit Trail for Configuration Changes
**File:** Backend
**Issue:** `CONFIGURATION_CHANGED` event is registered but never published. No record of who changed what.

### M-35: Frontend Chart Data Format Mismatch
**File:** `frontend/components/charts/` (various)
**Issue:** Charts expect specific data formats that may not match what the backend actually returns.

---

## LOW Issues (Nice to Have — Code Quality)

### L-01: Unused Imports
**Files:** Multiple backend files
**Issue:** Various unused imports (`Optional`, `Callable`, response models) that should be cleaned up.

### L-02: Inconsistent Naming Conventions
**Files:** Throughout codebase
**Issue:** Mix of snake_case and camelCase in API responses. Frontend types use camelCase, backend uses snake_case, with no consistent transformation layer.

### L-03: TODO Comments in Production Code
**Files:** `handlers.py` (Telegram), `retrainer.py`, `kill_switch.py`
**Issue:** Multiple TODO comments for unimplemented features that should be tracked as issues instead.

### L-04: Magic Numbers
**Files:** Various
**Issue:** Hardcoded values like `20` (symbols limit), `100` (max trades fetch), `5.0` (timeout), `60` (retrainer interval) should be constants.

### L-05: No Type Hints on Some Functions
**Files:** Various backend files
**Issue:** Some functions lack return type annotations, reducing IDE support and code clarity.

### L-06: Frontend Console.error in Production
**Files:** Multiple frontend pages
**Issue:** `console.error()` calls remain in production code. Should use a proper logging service.

### L-07: No Favicon or Meta Tags
**File:** `frontend/app/layout.tsx`
**Issue:** Missing proper favicon, meta description, and Open Graph tags.

### L-09: No .dockerignore
**File:** Root
**Issue:** No `.dockerignore` file. Docker build context may include unnecessary files (node_modules, .git, etc.), slowing builds.

### L-10: Hardcoded MT5 REST URL
**File:** `backend/app/api/routes_system.py` (line 37)
**Issue:** Falls back to `http://jsr-mt5:18812` hardcoded. Should always come from settings.

### L-11: No Commit Message Standards
**File:** Repository
**Issue:** No conventional commits or commit message format enforcement.

### L-12: Frontend Package Lock Not Committed
**File:** `frontend/`
**Issue:** If `package-lock.json` or `yarn.lock` isn't committed, builds may produce different dependency trees.

### L-13: No Pre-commit Hooks
**File:** Repository
**Issue:** No linting, formatting, or type-checking hooks to catch issues before commit.

### L-15: No Security Headers Beyond Caddy
**File:** Backend, Frontend
**Issue:** Backend doesn't set security headers. Relies entirely on Caddy, which may not cover all cases.

### L-16: Database Password in Docker Compose
**File:** `docker-compose.yml`
**Issue:** Database password may be visible in the compose file rather than using Docker secrets.

---

## Priority Fix Order (Recommended)

### Phase 0 — Security Emergency (Do Immediately)
1. **C-22-OLD** Enforce non-default JWT_SECRET and ADMIN_PASSWORD at startup
2. **H-01** Require auth on sensitive read endpoints
3. **H-02** Require auth on brain auto-allocation toggle
4. **H-25** Add CSRF protection
5. **H-27** Add rate limiting on auth/trade/system mutating endpoints

### Phase 1 — Runtime Safety & Stability
1. **H-12** Eliminate two-phase trade write race
2. **M-06** Add backoff on repeated engine failures
3. **M-15** Add retries for MT5 HTTP calls in system routes
4. **H-28** Harden Caddy WebSocket timeout/flush settings

### Phase 2 — Data Integrity & Observability
1. **H-16** Populate and expose usable equity curve data for frontend chart
2. **M-34** Publish CONFIGURATION_CHANGED events for audit trail
3. **M-22** Define and automate database backups
4. **M-26** Add monitoring/alerting integration

### Phase 3 — API & Frontend Maintainability
1. **M-03** Add pagination support for strategies endpoint
2. **M-24** Introduce API versioning strategy
3. **M-20** Add frontend error boundary
4. **M-16** Standardize frontend date formatting utilities
5. **M-17** Display commission/swap in trades table
6. **M-35** Align chart data contracts with backend responses

### Phase 4 — Cleanup & Debt Reduction
1. **H-20** Remove or integrate orphaned frontend components
2. **H-21** Add robust error handling in brain routes
3. **M-33** Add strategy performance reset workflow
4. **L-01/L-02/L-03/L-04/L-05/L-06** Code quality cleanup pass
5. **L-09/L-10/L-11/L-12/L-13/L-15/L-16** Infrastructure and process hygiene
6. **C-19** Implement retrainer or remove/disable service until implemented

---

*Report updated after code-verification audit against current repository state (2026-02-19).*
