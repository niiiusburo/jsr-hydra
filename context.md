# JSR Hydra Context

Updated: 2026-02-20
Source of truth: OneContext history (agent-scoped `jsr-hydra` context)

## Scope
This document captures the working project context inferred from OneContext history so future work starts from consistent assumptions.

## OneContext Snapshot
- Context title: `JSR Hydra Context`
- Context description: `JSR Hydra project history`
- Linked history currently spans multiple Hydra-focused sessions (brain/backend/frontend work).
- A large portion of older turn titles/summaries are `LLM API Error - Summary unavailable` because cloud login was missing during imports; raw turn content is still searchable.

## What Recent History Says
1. Brain subsystem was the main focus.
- Refactor trend: move from compact orchestration toward clearer staged functions and pair-specific processing paths.
- Reliability trend: normalize and surface LLM errors (avoid blank error messages), and propagate runtime error state to API/UI.

2. Brain observability and mapping were treated as first-class.
- Dedicated docs were added for maintainability:
  - `backend/app/brain/BRAIN_CODE_OVERVIEW.md`
  - `backend/app/brain/BRAIN_FLOW_MAP.md`
- Error-focused tests were added around LLM behavior.

3. Frontend brain UX was improved for explainability.
- Thought stream and insights UI were updated to expose more explicit state (error badges and clearer metadata).
- Historical intent repeatedly emphasized: make "what the brain is thinking" easier to inspect during live operation.

4. Allocation/dashboard wiring and strategy visibility were repeatedly audited.
- History shows recurring checks around strategy allocations, dashboard aggregation, and clarity of data flow through API/service layers.

5. There is ongoing pressure for enterprise-grade debuggability.
- Repeated direction in history: clear boundaries, explicit mapping docs, predictable error surfaces, and simpler troubleshooting paths.

## Current Constraints and Risks
- OneContext cloud auth state can affect quality of generated turn titles/summaries.
- Search remains usable through content snippets, but metadata quality may be degraded when LLM summary jobs fail.
- The git working tree is actively evolving; maintain docs as living references.

## Working Conventions
- Bootstrap OneContext scope in each terminal:
  - `source scripts/onecontext_hydra.sh`
- Run broad-to-deep history checks before major refactors:
  - `onecontext context show`
  - `onecontext search ... -t session|turn`
  - `onecontext search ... -t content --turns ...`
- Keep architecture docs updated whenever cross-module behavior changes.

## When To Refresh This File
Refresh after any of the following:
- Changes to brain orchestration (`backend/app/brain/brain.py`) or LLM handling (`backend/app/brain/llm_brain.py`)
- API contract changes in brain/strategy/dashboard routes
- Major frontend dashboard/brain UX changes
- Any new recurring production/debugging incidents
