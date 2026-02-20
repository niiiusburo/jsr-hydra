# Brain Code Overview

This document is the operational ownership map for the Brain subsystem.
It is designed so a new engineer can debug production issues quickly and safely.

## 1) Scope

Brain is responsible for:
- Pair-level market interpretation (trend, momentum, volatility, regime).
- Thought stream generation (analysis, decisions, learning, plans, AI insights).
- Strategy confidence scoring and next-move intent.
- LLM insight orchestration with runtime provider/model switching.
- Cross-process state sync through Redis (engine writes, API reads).

## 2) File Ownership Map

| File | Responsibility | Key Public Entry Points |
|---|---|---|
| `backend/app/brain/brain.py` | Core coordinator, thought generation, cycle/trade processing, Redis sync | `process_cycle()`, `process_trade_result()`, `get_state()` |
| `backend/app/brain/llm_brain.py` | Provider-agnostic LLM calls + insight history + usage stats | `analyze_market()`, `review_trade()`, `analyze_regime_change()`, `diagnose_losses()` |
| `backend/app/brain/paths.py` | Writable persistence path resolver (`/app` + `/tmp` fallback) | `get_brain_data_dir()`, `resolve_brain_state_path()` |
| `backend/app/brain/analyzer.py` | Deterministic indicator interpretation and next-move generation | `analyze_trend()`, `analyze_momentum()`, `analyze_volatility()`, `generate_next_moves()` |
| `backend/app/brain/learner.py` | RL/Thompson-learning updates and confidence adjustments | `analyze_trade()`, `should_override_signal()`, `get_rl_stats()` |
| `backend/app/api/routes_brain.py` | Auth-protected Brain API surface for dashboard and controls | `/brain/state`, `/brain/llm-insights`, `/brain/llm-config` |
| `frontend/app/dashboard/brain/page.tsx` | Brain dashboard orchestration (polling + model controls) | `fetchBrainState()`, `saveLlmConfig()` |
| `frontend/components/brain/ThoughtStream.tsx` | Human-readable thought cards (pair, price, confidence, trigger) | `ThoughtStream` |
| `frontend/components/brain/LLMInsights.tsx` | AI insight cards + error surfacing + LLM usage footer | `LLMInsights` |

## 3) Pair-First Processing Contract

`Brain.process_cycle()` is intentionally staged and pair-aware:

1. Normalize cycle payload (`signals`, `risk_checks`, `trades`).
2. Build per-pair snapshots via `_process_symbol_payload(symbol, payload)`.
3. Build per-pair next moves via `_build_next_moves_for_symbols(...)`.
4. Emit pair-level candle thoughts via `_emit_new_candle_thoughts(...)`.
5. Evaluate signal decisions (RL override + point guard + risk result).
6. Emit trade/rejection/regime-change thoughts.
7. Emit periodic summary including pair snapshot digest.
8. Schedule LLM analyses (market + optional regime-change).
9. Sync complete state to Redis.

This ensures each pair has a dedicated processing function and emits auditable thought context.

## 4) LLM Reliability Contract

`LLMBrain._call_gpt()` now guarantees non-empty, normalized error payloads.
- HTTP failures: `[LLM Error][HTTP <status>] <detail>`
- Runtime failures: `[LLM Error][<ExceptionType>] <detail>`
- Empty provider payloads: `[LLM Error][EmptyContent] ...`

`Brain` runtime behavior:
- `_set_llm_runtime_error(...)` updates `last_error` surfaced by `/brain/llm-config`.
- `_ingest_llm_insight(...)` marks AI thought metadata with `llm_error=true` when needed.
- Successful LLM calls clear runtime errors (config errors remain untouched).

## 5) Debugging Playbook

### A) Thought clarity by pair
- Confirm `symbols_data` includes each pair with `indicators`, `regime`, `new_candle`, `bid/ask`.
- Verify `_process_symbol_payload()` is called per symbol.
- Verify thought metadata contains `symbol`, `price`, `price_change`, `trigger`.

### B) LLM errors in dashboard
- Check `/brain/llm-config` -> `last_error`.
- Check `/brain/llm-insights` -> `stats.last_error` and `insights[].is_error`.
- Validate provider key + model + base URL in environment (`OPENAI_*` or `ZAI_*`).

### C) API/engine mismatch
- If API process has no local cycles, ensure Redis key `jsr:brain:state` is present and fresh.
- Engine should call `brain.process_cycle(...)` each loop and `brain.process_trade_result(...)` on closes.

### D) Local environment import/runtime failures
- Brain persistence paths resolve via `brain/paths.py`.
- If `/app/data/brain` is not writable, runtime automatically falls back to `/tmp/jsr-hydra/brain`.

## 6) Non-Regression Guardrails

When changing Brain code:
- Keep pair processing in pair-scoped helpers (do not collapse back into one long block).
- Preserve explicit stage boundaries in `process_cycle()`.
- Any new LLM failure path must set a non-empty error string.
- Update `BRAIN_FLOW_MAP.md` if stage order or contracts change.
