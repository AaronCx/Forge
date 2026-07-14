# Harness cutover QA (Phase 8)

Verification that the single (Forge-native, LangChain-free) stack preserves the
Feature Parity Checklist from `docs/harness-plan.md`. Run on the `main`-based
Phase 8 branch with all flags default-on.

## Automated gates

- **Backend suite:** 845 passed, 23 skipped (`FORGE_TESTING=1 pytest tests/`).
- **Parity safety net:** `make parity` green twice in a row (51 golden tests —
  all 44 node types + the agent SSE stream, unchanged since Phase 0).
- **Lint/type:** `ruff check app/` and `mypy app/` clean.
- **No LangChain:** `grep -rn langchain backend/app` is empty; full suite passes
  with `langchain*`/`langgraph*` uninstalled from the venv (CI parity).
- **Frontend:** `bun run lint` + `tsc --noEmit` + 60 vitest + demo-parity gate.

## Feature Parity Checklist

| Feature | Preserved by | Evidence |
|---|---|---|
| 44 node types execute, DAG editor, SSE traces, retry | blueprint_engine unchanged | node parity goldens (44) |
| Computer use: Steer/Drive/CU/agents, screen recording, safety | executors + `safety.py` unchanged; also `cu.*`/`agent.*` on the plane | test_computer_use, test_toolplane |
| Agent-on-agent (spawn/prompt/monitor/wait/stop/result) | agent_runner unchanged; `agent.*` on the plane | test_computer_use |
| Multi-machine dispatch | dispatch service unchanged | test_dispatcher |
| Knowledge base + RAG (`knowledge_retrieval`) | knowledge service; chunker rewritten dependency-free | test_knowledge |
| Evals (5 grading methods, multi-model compare) | evals unchanged | test_evals |
| Approvals inbox (web + CLI) | one inbox; plane `ask` routes here | test_toolplane, test_hardening |
| Prompt versioning (diff/rollback) | unchanged | test_e2e |
| Observability traces | native loop records spans | test_observability, test_native_loop |
| Time-travel: record/replay/fork | native no-tools path keeps the cache/recorder seam | test_time_travel (11) |
| Marketplace publish/browse/fork/rate, org RBAC | unchanged | test_marketplace |
| Workspace IDE + `workspace.*` | workspace service; plane tools | test_toolplane |
| Live dashboard heartbeats, cost analytics | native loop writes heartbeats + token usage; budgets added | test_heartbeat, test_hardening |
| CLI (8 command modules) + `chat`/`agent run` | unchanged + new | cli compiles |
| Both DB backends (SQLite default, Supabase) | additive migrations both backends | schema tests |
| Onboarding + custom instructions (`prepend_about`) | woven in the native loop | test_custom_instructions |

## New surfaces (Phases 1–7)

Kernel + model cards · provider `turn`/`stream_turn` (incl. Google) · tool plane
(82 tools) + permissions · native loop · real MCP (client + server) · sessions +
chat · Docker code-exec · cost budgets · `forge-kernel` SDK.

## Notes / deferred

- The legacy REST MCP client (`app/mcp/client.py`) is retained for
  `transport='legacy'` rows; new connections use the real JSON-RPC client.
  Migrate legacy rows by re-adding them with `forge connections mcp add`.
- Frontend fallback-policy toggle / budget widget: API is ready
  (`/costs/budget`, preferences); the UI is a follow-up.
- `forge-kernel` currently vendors the pure kernel; consolidating `app/kernel`
  to import the package is a follow-up (kept separate to avoid an import churn).
