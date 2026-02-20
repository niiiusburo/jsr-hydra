# Brain Flow Map

This is the execution map for the Brain subsystem.
Use it as the single source of truth for data flow and debugging paths.

## 1) Runtime Flow (Engine -> Brain -> API -> UI)

```mermaid
flowchart TD
    E["Engine Main Loop\n(engine.py)"] --> C["cycle_summary\n(symbols_data, signals, risk_checks, trades)"]
    C --> B["Brain.process_cycle()"]

    B --> S1["_process_symbol_payload(pair)"]
    S1 --> S2["_build_next_moves_for_symbols()"]
    S2 --> S3["_emit_new_candle_thoughts()"]
    S3 --> S4["Signal Decisions\n(RL override + point guard + risk)"]
    S4 --> S5["Trade/Rejection Thoughts"]
    S5 --> S6["_emit_regime_change_thoughts()"]
    S6 --> S7["_generate_periodic_summary()"]
    S7 --> S8["_schedule_llm_analyses()"]
    S8 --> R["_sync_to_redis()"]

    R --> API1["/brain/state"]
    R --> API2["/brain/llm-insights"]
    R --> API3["/brain/llm-config"]

    API1 --> UI1["ThoughtStream"]
    API2 --> UI2["LLMInsights"]
    API3 --> UI3["Model Selector + last_error"]
```

## 2) LLM Error Propagation Map

```mermaid
flowchart LR
    L1["LLMBrain._call_gpt()"] -->|error| L2["[LLM Error][Type] detail"]
    L2 --> L3["insight.is_error = true"]
    L3 --> B1["Brain._ingest_llm_insight()"]
    B1 --> B2["Brain._set_llm_runtime_error()"]
    B2 --> API["/brain/llm-config last_error\n/brain/llm-insights stats.last_error"]
    API --> UI["LLMInsights red error card + footer"]
```

## 3) Pair Processing Map

For each symbol/pair in `symbols_data`:
- `Brain._process_symbol_payload(pair, payload)`
  - updates market snapshot
  - updates strategy scores for that pair
  - detects regime change for that pair
  - checks RSI/ADX crossings for that pair
- pair snapshot is then used by:
  - `ThoughtStream` thought metadata (`symbol`, `price`, `price_change`)
  - `NextMoves` generation per pair
  - periodic pair digest
  - LLM market payload (`symbol_data`)

## 4) API Response Ownership

| Endpoint | Source of Truth |
|---|---|
| `/brain/state` | local Brain if engine process, otherwise Redis state |
| `/brain/llm-insights` | local LLM history if engine process, otherwise Redis state |
| `/brain/llm-config` | runtime provider/model + `last_error` from Brain |

## 5) Quick Triage Checklist

1. If a pair has no thoughts: confirm pair exists in `symbols_data` and `new_candle` toggles.
2. If LLM card is red: inspect `/brain/llm-config.last_error` and provider env vars.
3. If API has stale data: validate Redis health and key freshness (`jsr:brain:state`).
4. If strategy behavior seems off for one pair: inspect pair-specific score/reason and point-guard status.
5. If startup/import fails around brain state files: verify writable brain data dir (`BRAIN_DATA_DIR` or `/tmp/jsr-hydra/brain` fallback).
