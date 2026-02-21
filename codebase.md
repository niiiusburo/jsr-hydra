# JSR Hydra Codebase Map

Updated: 2026-02-20
Purpose: Fast orientation + debugging map for contributors.

## System Shape
JSR Hydra is a full-stack trading platform with:
- Python backend (FastAPI + engine + strategy/risk/brain layers)
- Next.js frontend dashboard
- Dockerized local runtime (backend, frontend, infra services)

Primary entrypoints:
- Backend API: `backend/app/main.py`
- Engine runtime: `backend/app/engine/engine_runner.py`
- Frontend app shell: `frontend/app/layout.tsx`
- Compose orchestration: `docker-compose.yml`

## Repository Top Level
- `backend/`: API, engine, trading logic, persistence layer
- `frontend/`: dashboard UI and realtime client state
- `infra/`: runtime infrastructure configs
- `scripts/`: utility/bootstrap scripts (including OneContext bootstrap)
- `context.md`: project working context (history-derived)
- `ONECONTEXT_SETUP.md`: OneContext operational setup notes

## Backend Map (`backend/app`)

### API Layer
- `api/routes_brain.py`: brain state/insights/thought-related endpoints
- `api/routes_strategies.py`: strategy and allocation endpoints
- `api/routes_trades.py`: trade lifecycle endpoints
- `api/routes_system.py`: system/health/config endpoints
- `api/routes_ws.py`: websocket routes
- `api/auth.py`: auth helpers/dependencies

### Brain Layer
- `brain/brain.py`: orchestration, thought pipeline, insight scheduling, cross-module coordination
- `brain/llm_brain.py`: LLM providers, prompt execution, insight formatting/error normalization
- `brain/learner.py`: learning logic (RL/statistics/override behavior)
- `brain/auto_allocator.py`: allocation and rebalance logic
- `brain/strategy_xp.py`: strategy XP progression
- `brain/memory.py`: brain memory persistence
- `brain/paths.py`: writable path resolution/fallback for brain persistence
- `brain/analyzer.py`, `brain/patterns.py`, `brain/prompts.py`: analysis/pattern/prompt helpers
- Docs:
  - `brain/BRAIN_CODE_OVERVIEW.md`
  - `brain/BRAIN_FLOW_MAP.md`

### Engine and Trading Runtime
- `engine/engine.py`: main cycle execution
- `engine/regime_detector.py`: market regime classification
- `engine/retrainer.py`: model retraining loop placeholder/runtime

### Bridge/Execution
- `bridge/connector.py`: external connector integration
- `bridge/order_manager.py`: order execution bridge
- `bridge/data_feed.py`: market data bridge
- `bridge/account_info.py`: account state bridge

### Domain and Service Layers
- Models: `models/*.py`
- Schemas: `schemas/*.py`
- Services: `services/*.py` (dashboard/account/strategy/trade/regime)
- Risk: `risk/*.py` (kill switch, sizing, risk manager)
- Strategies: `strategies/strategy_a.py` ... `strategy_e.py`, plus `signals.py`
- Indicators: `indicators/*.py`

### Infrastructure/Support
- Config: `config/settings.py`, `config/constants.py`
- DB: `db/*` (engine/base/seed)
- Events: `events/*` (bus, handlers, types)
- Utils: `utils/*`

## Frontend Map

### App Router
- `frontend/app/dashboard/page.tsx`: dashboard landing
- `frontend/app/dashboard/brain/page.tsx`: brain view
- `frontend/app/dashboard/strategies/page.tsx`: strategy overview
- `frontend/app/dashboard/trades/page.tsx`: trade views
- `frontend/app/dashboard/risk/page.tsx`: risk views
- `frontend/app/dashboard/settings/page.tsx`: settings views

### Brain UI Components
- `frontend/components/brain/ThoughtStream.tsx`
- `frontend/components/brain/LLMInsights.tsx`
- `frontend/components/brain/MarketAnalysis.tsx`
- `frontend/components/brain/StrategyScores.tsx`
- `frontend/components/brain/NextMoves.tsx`

### Shared Dashboard Components
- `frontend/components/dashboard/*`
- `frontend/components/layout/*`
- `frontend/components/ui/*`

### Client Data Layer
- `frontend/lib/api.ts`: REST client
- `frontend/lib/ws.ts`: websocket client
- `frontend/lib/types.ts`: UI types
- `frontend/store/useAppStore.ts`: app state
- `frontend/store/useLiveStore.ts`: live data state

## Debugging and Observability Pointers

Start here for brain issues:
1. `backend/app/brain/brain.py`
2. `backend/app/brain/llm_brain.py`
3. `backend/app/api/routes_brain.py`
4. `frontend/components/brain/ThoughtStream.tsx`
5. `frontend/components/brain/LLMInsights.tsx`

Start here for allocation/strategy issues:
1. `backend/app/services/dashboard_service.py`
2. `backend/app/api/routes_strategies.py`
3. `backend/app/brain/auto_allocator.py`
4. `frontend/components/strategies/AllocationManager.tsx`

## Known Operational Caveats
- Frontend build artifacts (`frontend/.next`) and dependencies (`frontend/node_modules`) are local/runtime artifacts, not architectural source.
- OneContext turn metadata quality depends on login state; content search is more reliable than title/summary when cloud LLM jobs fail.

## Maintenance Rule
Whenever behavior crosses module boundaries (brain <-> API <-> UI), update this map and `context.md` in the same change set.
