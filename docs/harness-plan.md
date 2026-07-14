# Forge Harness Transformation: Implementation Plan for Claude Code

This document is an execution plan for Claude Code working in the Forge repo. Work one phase per session where possible. Every phase ends with the full test suite green (`pytest backend/tests`), lint clean (`ruff check`), and a commit per completed task. Drop this file into the repo as `docs/harness-plan.md` and tell Claude Code: "Read docs/harness-plan.md, complete Phase N, follow the guardrails."

## Global guardrails (apply to every phase)

1. **Zero feature loss.** Nothing in the Feature Parity Checklist below may break or be removed. New systems are built alongside old ones and cut over behind flags. Old code paths are deleted only in Phase 8, after parity is proven.
2. **Additive schema only.** New tables and columns are fine; never drop or rename existing tables in `backend/app/db/sqlite_schema.py`. Ship both SQLite and Supabase variants of every migration.
3. **Shims over rewrites.** When a type or function signature changes, keep the old name as a thin wrapper emitting a `DeprecationWarning` until Phase 8. All 743 existing test functions must keep passing without edits, except where a test asserts implementation details of a path being replaced (then port the test, do not delete the behavior it covers).
4. **Feature flags.** Add `backend/app/config/flags.py` reading env vars: `FORGE_NATIVE_LOOP`, `FORGE_MCP_V2`, `FORGE_SESSIONS`. Default all to off until each phase's exit criteria pass.
5. **No new hardcoded model knowledge.** Model names, context windows, and capabilities live in data files after Phase 1, never in Python constants.
6. **Every phase updates CHANGELOG.md** and, where user-visible, README.md. README claims must be true (see Phase 8 truth pass).

## Feature Parity Checklist (verify at the end of every phase)

Blueprints: 48 node types execute, DAG editor loads, SSE traces stream, retry policies work. Computer use: Steer (13 GUI nodes), Drive (6 terminal nodes), CU agents (4), screen recording, safety layer (blocklist, rate limit, approval gates, audit log to `computer_use_audit_log`). Agent-on-agent: spawn/prompt/monitor/wait/stop/result for Claude Code, Codex CLI, Gemini CLI, Aider in tmux. Multi-machine dispatch routing. Knowledge base + RAG (`knowledge_retrieval` node). Evals: all 5 grading methods, multi-model comparison. Approvals inbox (web + CLI). Prompt versioning with diff/rollback. Observability traces. Time-travel: record, replay, fork against `NullRecorder` default. Marketplace publish/browse/fork/rate, org RBAC. Workspace IDE: CodeMirror, file tree, xterm.js terminal, WebSocket file sync, 4 workspace nodes. Live dashboard heartbeats, cost analytics. CLI: all 8 command modules (`auth, connections, evals, marketplace, ops, settings, studio, system`). Both DB backends: SQLite default, Supabase optional. Onboarding + custom instructions weaving (`prepend_about`).

---

## Phase 0: Safety net

**Goal:** Freeze current behavior so later phases can prove they changed nothing they should not have.

Tasks:
1. Create `backend/tests/parity/` with golden-transcript tests: for each of the 48 node types, execute the node with fixed inputs against a `FakeProvider` (add one in `backend/app/providers/fake_provider.py` implementing `LLMProvider` with canned responses) and snapshot the output dict to `backend/tests/parity/golden/<node_key>.json`. Assert equality on subsequent runs.
2. Add a parity test that runs `AgentRunner.execute` end to end with the fake provider and snapshots the full ordered SSE event list (the `{"type": "step"|"token", ...}` dicts from `agent_executor.py`).
3. Add `make parity` target running only these tests. Wire into `.github` CI.
4. Record current public API surface: script `scripts/dump_api.py` that prints all FastAPI routes + methods to `docs/api-surface.txt`; commit it. Later phases diff against it.

Exit criteria: `make parity` green twice in a row; `docs/api-surface.txt` committed.

---

## Phase 1: The kernel

**Goal:** A Forge-owned, provider-neutral representation of agentic exchanges. Pure types, zero behavior change.

Tasks:
1. Create `backend/app/kernel/types.py` with frozen dataclasses (or Pydantic models, match repo style):
   - `TextBlock{text}`, `ImageBlock{media_type, data|url}`, `ToolUseBlock{id, name, input}`, `ToolResultBlock{tool_use_id, output, is_error}`, `ThinkingBlock{text}`; union alias `Block`.
   - `KMessage{role: "system"|"user"|"assistant"|"tool", blocks: list[Block]}`.
   - `TurnResult{blocks, stop_reason: "end"|"tool_use"|"max_tokens"|"error", usage: Usage{input_tokens, output_tokens}, model, provider, latency_ms}`.
   - `StreamEvent` union: `TextDelta`, `ThinkingDelta`, `ToolUseStart{id,name}`, `ToolUseDelta{partial_json}`, `UsageEvent`, `TurnDone{turn: TurnResult}`.
   - `ToolSpec{name, description, input_schema: dict, source: "builtin"|"mcp"|"blueprint"|"computer_use"|"workspace", source_id, requires_approval: bool, danger_level: "safe"|"caution"|"dangerous"}`.
2. Create `backend/app/kernel/models.py`: `ModelCard{id, provider, display_name, context_window, max_output, vision: bool, tools: bool, thinking: bool, family}` loaded from `backend/app/kernel/models.json`. Seed models.json with current OpenAI, Anthropic, Gemini, and common Ollama entries. Add `load_model_cards()` with per-user override merge from a new `model_overrides` JSON column on `provider_configs` (additive migration). Add CLI `forge system models refresh` that pulls each registered provider's `list_models()` and updates the user override file.
3. Create `backend/app/kernel/convert.py` with lossless converters: `from_openai_messages(list[dict]) -> list[KMessage]` and back, so old string-content callers can enter the kernel world. Round-trip property tests in `backend/tests/test_kernel.py` (text-only, image, tool_use, tool_result cases).
4. Delete nothing. `ANTHROPIC_MODELS` and `MODEL_PROVIDER_MAP` stay for now; add TODO(phase-8) comments.

Exit criteria: `test_kernel.py` passes with round-trip coverage for all block types; `models.json` validates against `ModelCard`; parity suite untouched and green.

---

## Phase 2: Provider adapters speak kernel

**Goal:** Every provider converts kernel to native and native to kernel, including tool calls, images, tool results, and streaming. This unblocks everything.

Tasks:
1. Extend `LLMProvider` (base.py) with two new abstract methods, keeping the old ones working:
   - `async def turn(self, messages: list[KMessage], model: str, *, tools: list[ToolSpec] | None, temperature, max_tokens) -> TurnResult`
   - `async def stream_turn(...) -> AsyncIterator[StreamEvent]`
2. Implement both in `openai_provider.py` and `anthropic_provider.py` as pure converter pairs plus transport. Anthropic: map ToolUseBlock/ToolResultBlock to native `tool_use`/`tool_result` content blocks; support base64 image blocks. OpenAI: map to `tool_calls`/role `tool` messages; support `image_url` blocks. Do not drop `tool_use` blocks anywhere.
3. Implement `turn`/`stream_turn` for `ollama_provider.py` and `generic_provider.py` via their OpenAI-compatible shapes; degrade gracefully when a `ModelCard` says `tools=False` (return a clear error TurnResult, never a silent text-only call).
4. Add `google_provider.py` (native Gemini API) implementing the same interface, registered on `GOOGLE_API_KEY` in `create_registry()` and in `create_user_registry()`. This makes the README's Google claim true.
5. Registry upgrades in `registry.py`:
   - `async def turn(...)` and `async def stream(...)` that resolve provider then delegate.
   - Replace prefix routing over time: `resolve_provider` first consults `ModelCard.provider` from models.json, then explicit `provider/model` syntax, then legacy prefix map.
   - Fallback policy object: `FallbackPolicy{enabled: bool, same_capabilities_only: bool, exclude_client_errors: bool}` default `enabled=False`. Never retry on 4xx. When a fallback fires, emit a `StreamEvent`-visible warning and record it in traces. Old `complete()` keeps its current behavior behind the shim rule.
6. Rewrite `LLMResponse` construction to derive from `TurnResult` internally (old dataclass remains as the public shim: `content` = joined text blocks).
7. Vision routing: delete usage of `_VISION_MODEL_HINTS` logic in favor of `ModelCard.vision` lookups. Keep the constant itself until Phase 8. `_prepare_attachments` in `agent_executor.py` now produces kernel `ImageBlock`s and converts per provider.
8. Tests: `test_providers.py` additions with recorded fixtures per provider covering a full tool round trip (assistant tool_use, tool result, assistant final) and a streaming tool call. Use `respx`/mock transports, no live keys.

Exit criteria: a single integration test executes the same two-tool conversation through OpenAI, Anthropic, Gemini, and Ollama adapters (mocked transports) and gets structurally identical `TurnResult`s. Parity suite green.

---

## Phase 3: One tool plane

**Goal:** Every capability Forge already has becomes a `ToolSpec` an agent can call, behind one permission policy. This is the "AI uses your features seamlessly" phase.

Tasks:
1. Create `backend/app/kernel/toolplane.py`:
   - `ToolPlane.list(user_id, context) -> list[ToolSpec]` aggregating all sources below.
   - `ToolPlane.execute(tool_use: ToolUseBlock, ctx: ExecContext) -> ToolResultBlock` with uniform timeout, error capture, audit logging, and permission checks.
2. Sources to register:
   - **Builtin tools:** strip the LangChain `@tool` decorators from `services/tools/*` into plain async functions plus ToolSpecs (keep thin LangChain wrappers exported from the same modules so the legacy loop still imports them until Phase 4).
   - **Blueprint nodes as tools:** `NodeType` in `blueprint_nodes/registry.py` already carries `input_schema`/`output_schema`; write `nodetype_to_toolspec()` and an executor that invokes the node exactly as `blueprint_engine` does. Namespace as `node.<key>` (for example `node.knowledge_retrieval`, `node.fetch_url`). All 48 become callable.
   - **Blueprints as tools:** each saved blueprint becomes `blueprint.<slug>` with its declared inputs as schema; executing it runs the full DAG and returns final outputs. This turns the visual builder into a tool factory, a real differentiator.
   - **Computer use:** expose Steer/Drive/CU actions as `cu.<action>` ToolSpecs with `danger_level` set (`cu.steer_click` = caution, `cu.drive_run` = dangerous, and so on). Execution MUST route through the existing `computer_use/safety.py` functions (`check_command_blocklist`, `check_rate_limit`, `check_approval_required`, `log_action`). Do not reimplement safety.
   - **Workspace:** `workspace.read/write/list/search` mapping to the existing workspace nodes, scoped to the session's workspace root.
   - **Agent control:** `agent.spawn/prompt/monitor/wait/stop/result` wrapping `computer_use/agents/agent_runner.py`, so a Forge agent can drive Claude Code and Codex as sub-workers.
3. Permission policy: `backend/app/kernel/permissions.py` with `PolicyDecision = allow|ask|deny`. Resolution order: per-session override, per-user tool policy (new additive table `tool_policies(user_id, tool_name, decision)`), then default by `danger_level` (safe=allow, caution=ask, dangerous=ask). `ask` creates a row in the existing `approvals` table and pauses the loop exactly like `approval_gate` does today, surfacing in the existing approvals inbox (web + CLI). One inbox for everything, no new UI needed yet.
4. MCP tools plug into the plane later (Phase 5) via the same interface; leave a registration hook.
5. Tests: toolplane lists include all sources; executing `node.json_validator` matches the golden output from Phase 0; `cu.*` execution is blocked by blocklist and creates approvals; denied tools return `ToolResultBlock(is_error=True)` with a clear message, never an exception that kills the loop.

Exit criteria: `ToolPlane.list()` returns 70+ specs on a seeded install; an integration test has the fake provider call `node.template_renderer` then `workspace.read` in one conversation and both round-trip. Parity green.

---

## Phase 4: Forge-native agent loop

**Goal:** Replace the LangChain/ChatOpenAI loop with a kernel loop on the registry, behind `FORGE_NATIVE_LOOP`. Any provider, any tool, streamed.

Tasks:
1. Create `backend/app/kernel/loop.py`:
   ```
   async def run_agent_turn(messages, tools, model, *, plane, policy, recorder, tracer, budget) -> AsyncIterator[StreamEvent]:
       for _ in range(max_iterations):            # default 12, from config not constant
           async for ev in registry.stream(messages, tools, model): yield ev
           if turn.stop_reason != "tool_use": return
           results = await plane.execute_all(turn.tool_calls, policy)   # approvals may pause here
           messages += assistant(turn.blocks) + tool_results(results)
   ```
   Include cancellation (asyncio task cancel on client disconnect), a wall-clock budget, and a token budget from `budget`.
2. Port the observers, this is the migration's real cost and MUST NOT be skipped:
   - Time-travel: `timetravel/recorder.py` gains kernel hooks (`model_turn(turn)`, `tool_call(tool_use, result)`); `replayer.py` and `fork.py` read both old and new event shapes. `response_cache` keys on a hash of kernel messages so replay/fork still avoid re-paying.
   - Observability: `trace_service` records per-turn spans with model, provider, usage, tool timings.
   - Heartbeats and `token_usage` accounting write identically to today.
3. Rewire `AgentRunner.execute` (agent_executor.py): when `FORGE_NATIVE_LOOP` is on, translate agent_config workflow steps into the kernel loop and emit legacy SSE events (`{"type": "step"|"token", ...}`) alongside new rich events `{"type": "tool_use"|"tool_result"|"thinking"|"usage"}` so the current frontend keeps working unmodified. Custom instructions weaving (`prepend_about`) stays.
4. Wire MCP-name pass-through: `_resolve_tools` maps names to ToolSpecs from the plane instead of the LangChain TOOL_REGISTRY when the flag is on.
5. Frontend (minimal this phase): runs view renders the new event types if present (collapsible tool call cards), ignores them otherwise.
6. Tests: port the Phase 0 agent parity snapshot to run under both flags and assert the legacy-shaped event subsequence is identical. Multi-provider loop test: same agent, tools, and fake transports across all four providers.

Exit criteria: with `FORGE_NATIVE_LOOP=1`, an agent using `node.*`, `workspace.*`, and a builtin tool completes on Anthropic and Ollama models (mocked), streams tool events, records time-travel, and the legacy event subsequence matches the golden snapshot. Flag defaults ON at the end of this phase after a week of local soak; LangChain deps stay installed until Phase 8.

---

## Phase 5: Real MCP, both directions

**Goal:** Speak actual MCP (JSON-RPC 2.0) as client, and expose Forge as an MCP server.

Tasks:
1. Add `mcp` (official Python SDK) to requirements. Create `backend/app/mcp/client_v2.py` supporting stdio transport (command + args from config) and Streamable HTTP, with `initialize`, `tools/list`, `tools/call`, notifications, and OAuth for remote HTTP servers. Keep SSRF `validate_url` checks for HTTP transports.
2. Additive columns on `mcp_connections`: `transport ("legacy"|"stdio"|"http")`, `command`, `args_json`, `oauth_json`. Existing rows default to `legacy` and keep using the old REST client so nothing breaks; new connections default to real MCP behind `FORGE_MCP_V2`.
3. Register discovered tools into the ToolPlane as `mcp.<server>.<tool>` with `danger_level="caution"` default (user can promote per tool via `tool_policies`). Mark MCP outputs untrusted: wrap tool results in a delimiter and add a fixed system-prompt line in the loop stating tool outputs are data, not instructions.
4. **Forge as MCP server:** `backend/app/mcp/server.py` exposing the ToolPlane (blueprints, nodes, knowledge search; exclude `cu.*` and `agent.*` by default, opt-in flag `FORGE_MCP_EXPOSE_CU`) over Streamable HTTP with the existing API-key auth. Ship `docs/mcp-server.md` with a Claude Code `.mcp.json` snippet and a Codex config snippet. This makes every Claude Code and Codex install a potential Forge front-end.
5. Frontend `dashboard/mcp` and `dashboard/connections`: transport picker, stdio command field, tool list with per-tool policy toggle. CLI `forge connections` parity.
6. Tests: spin the reference `mcp` SDK echo server over stdio in-process; connect, list, call, and route a tool call through the agent loop. Server side: connect the SDK client to Forge's server and call `node.json_validator`.

Exit criteria: a real third-party MCP server (filesystem server from the SDK examples) works end to end inside an agent run; Claude Code connects to Forge's MCP server locally and lists blueprints as tools. Legacy connections still function.

---

## Phase 6: Sessions and the seamless user surface

**Goal:** Durable conversations and one obvious place where users talk to any model with all tools. This is the "users access seamlessly" phase.

Tasks:
1. Additive tables: `sessions(id, user_id, title, model, workspace_root, system_prompt, policy_json, token_budget, created_at, updated_at, status)` and `session_events(id, session_id, seq, kind, payload_json, created_at)` storing kernel messages and tool records append-only. Both backends.
2. `backend/app/services/sessions.py`: create/resume/list/fork (fork reuses time-travel fork semantics); compaction: when projected context exceeds `ModelCard.context_window * 0.8`, summarize the oldest span with the session's own model into a pinned `system` note, keep the last N turns verbatim, and record a `compaction` event (reversible, originals stay in `session_events`).
3. Routers: `POST /sessions`, `POST /sessions/{id}/messages` (SSE stream of StreamEvents), `GET /sessions/{id}`, plus mid-session model switching (just changes `sessions.model`; the kernel makes this trivial, which is the plug-and-play payoff made visible).
4. Frontend: new `dashboard/chat` (or promote it to the landing surface): thread list, streaming transcript with tool-call cards, inline approval prompts (reusing the approvals flow), a model picker fed by `ModelCard`s grouped by provider with vision/tools badges, and a tool drawer showing ToolPlane specs grouped by source with allow/ask/deny toggles. Attachments flow through the Phase 2 image path so screenshots work on Claude and Gemini too.
5. CLI: `forge chat` interactive REPL and `forge agent run --model X --prompt "..." --json` headless mode emitting one JSON StreamEvent per line for CI use.
6. Workspace convention: when a session has `workspace_root`, read `AGENTS.md` (and fall back to `CLAUDE.md`) from the root and inject it into the system prompt, capped at N tokens. Document in README.
7. Tests: session round-trip persistence, resume mid-tool-call, compaction preserves originals, model switch mid-session, headless JSON mode snapshot.

Exit criteria: from the web UI, start a chat on Gemini, switch to Claude mid-thread, have it call `node.knowledge_retrieval` and a `workspace.write` that triggers an approval, approve from the inbox, and resume the session after a backend restart. Same flow works in `forge chat`.

---

## Phase 7: Hardening and platform

**Goal:** Safe enough to let other people build on.

Tasks:
1. Code execution graduates to containers: `code_executor` gains a Docker backend (image with pinned stdlib-only Python, `--network none`, read-only rootfs, mem/CPU/pids limits, tmpfs workdir) used when Docker is available, current AST sandbox kept as fallback. Config knob per install.
2. Cost budgets: per-session and per-user daily token/dollar budgets (prices in models.json), enforced in the loop, surfaced in the existing cost analytics dashboard.
3. Fallback policy UI: expose Phase 2's `FallbackPolicy` in settings; default off; when on, only same-capability models per models.json.
4. Injection posture: red-team tests in `backend/tests/test_security.py` for MCP-output prompt injection, tool results attempting to trigger `cu.*` calls (must hit `ask`), and SSRF via `node.fetch_url` (existing validator covers it; add regression tests).
5. SDK extraction: publish the kernel, loop, and provider adapters as `forge-kernel` (pip). Keep it dependency-light: no FastAPI, no LangChain. Backend imports it. Optional stretch: a thin TS client for StreamEvents.
6. Rate-limit the new session endpoints with the existing `slowapi` setup.

Exit criteria: security test additions green; a demo script embeds `forge-kernel` in a 30-line standalone agent.

---

## Phase 8: Cutover and cleanup

**Goal:** One stack, honest docs.

Tasks:
1. Flip all flags default-on; run full suite plus parity plus a manual QA pass of the Feature Parity Checklist; capture in `docs/` per your QA playbook habit.
2. Remove: LangChain/langgraph deps and the `ChatOpenAI` path in `services/llm.py` (keep `get_user_openai_key`; generalize to `get_user_provider_key(provider)`), `_VISION_MODEL_HINTS`, `ANTHROPIC_MODELS`, prefix-first routing, legacy MCP client (after migrating any `legacy` rows with a one-time converter or documented manual step), all Phase 1-4 shims and DeprecationWarnings.
3. README truth pass: update provider claims (now genuinely OpenAI, Anthropic, Google, Ollama, any OpenAI-compatible), tests badge to the real count, node count consistency (48, the doc currently says both 44 and 48), CLI command claim made precise, new sections for Sessions, Tool Plane, MCP server mode.
4. Version bump to 3.0.0, full CHANGELOG entry.

Exit criteria: no imports of langchain remain (`grep -r "langchain" backend/app` empty); API surface diff against Phase 0's `api-surface.txt` shows only additions plus documented removals; parity suite green on the single stack.

---

## Suggested per-session prompt for Claude Code

"Read docs/harness-plan.md. We are on Phase N. Complete the tasks in order. Obey the Global guardrails: no feature removal, additive migrations only, shims for changed signatures, run `pytest backend/tests` and `ruff check` before every commit, one commit per task with a message referencing the phase and task number. If a task conflicts with existing behavior, stop and list the conflict instead of choosing silently. Finish by verifying the phase exit criteria and the Feature Parity Checklist, and report anything you could not verify."

## Sequencing notes

Phases 1 and 2 are the critical path; nothing else starts until 2's exit test passes. Phase 3 and Phase 5's client work can interleave after 2. Phase 4 must precede 6. If you want a visible win early, do the Phase 4 interim option first (swap `ChatOpenAI` for `init_chat_model` in `services/llm.py` with per-provider keys); it gives multi-provider agents in one session, but treat it as scaffolding you will remove, not a foundation.

---

## Implementation notes (maintained as phases land)

- **Node count ground truth is 44, not 48.** `NODE_REGISTRY` and the union of all
  executor dispatch tables both contain exactly 44 keys (10 deterministic, 5 llm_*,
  12 steer_*, 6 drive_*, 4 cu_*, 6 agent_*, 1 recording_control). Everywhere this
  plan says "48 node types", read 44. The Phase 8 README truth pass standardizes
  on 44.
