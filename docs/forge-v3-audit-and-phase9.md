# Forge v3.0.0 Verification Audit + Phase 9: Dynamic Orchestration

Audited at commit b005a3b on a fresh clone. Method: read every new subsystem (kernel, providers, toolplane, loop, MCP v2, sessions), traced the safety-critical paths, and executed the full backend suite in a clean container.

## Verdict

The transformation is real and it holds up. All 8 phases landed as described in the commit history, and more importantly they landed as described in the code. Test run in a clean environment: **845 passed, 23 skipped, 0 failed, 31s**. The skips are all environmental (CLI binary and typer not installed in my container), not masked failures.

Verified correct, in order of how likely I was to find them faked:

1. **LangChain is genuinely gone.** Zero references under `backend/app`, removed from requirements. The agent loop is now `forge_kernel.loop.run_agent_turn` over the registry: provider-neutral, budgeted, cancellable, tool results appended as kernel blocks.
2. **The kernel extraction is clean.** `forge-kernel/` is a zero-dependency package (`py.typed`, own pyproject, models.json bundled); `backend/app/kernel/*` are thin re-export shims keeping import paths stable, while `toolplane.py` and `permissions.py` correctly stay backend-side where the DB and safety live. Installed via `../forge-kernel` in requirements.
3. **Providers speak kernel for real.** Anthropic `turn`/`stream_turn` map `tool_use` blocks bidirectionally (the original sin from my first audit is fixed). Google is a native httpx adapter against the Gemini REST API: text, inline base64 images, function calling, streaming, dependency-light and mockable. Vision routing is `ModelCard.vision`, the `_VISION_MODEL_HINTS` hack is gone.
4. **FallbackPolicy is right.** Default off, 4xx never retried (`_is_client_error` guard with a comment explaining why), per-user policy loadable. This was one of the dangerous behaviors from audit one; fixed as specified.
5. **MCP is actually MCP now.** `client_v2.py` uses the official SDK: `ClientSession`, `stdio_client`, `streamablehttp_client`, `initialize` then `tools/list`/`tools/call`, SSRF checks kept on HTTP. `server.py` exposes the ToolPlane via `mcp.server.Server` with `cu.*` and `agent.*` excluded unless explicitly opted in. The create-connection endpoint only accepts `stdio|http`, so no new legacy rows can be born.
6. **Safety survived the rewiring.** `cu.*` ToolPlane executors delegate to the same node functions in `computer_use/{steer,drive}/nodes.py` that call `check_command_blocklist`, `check_rate_limit`, `check_approval_required`, and `log_action`. One enforcement point serves both blueprint runs and agent tool calls, which is the correct topology.
7. **Sessions and compaction match spec.** 0.8 context ratio from the ModelCard, last 8 messages kept verbatim, compaction is an event that marks history replaced rather than deleting it (reversible), mid-session model switch is a one-field update, which is the plug-and-play payoff made visible.
8. **Truth pass mostly done.** v3.0.0, LangChain scrubbed from README, node count now consistently 44, which matches the live registry (I counted `NODE_REGISTRY` at runtime: 44; the old README's "48" table header was the wrong one, including in my first audit which repeated it).

## Issues found, ranked

**H1. Approvals are input-blind. Fix this first.** `ToolPlane._approval_state` keys approvals on `(run_id, "tool:{name}")`. Approving one call of a dangerous tool approves every subsequent call of that tool with any arguments for the rest of the run or session. Concretely: a human approves `cu.drive_run` with input `ls -la`, and the model can then run `cu.drive_run` with any command it likes, unreviewed, because the lookup finds `status=approved`. The approval context stores the input for the human to read, but the reuse check ignores it. Fix: for `danger_level="dangerous"`, include a stable hash of `tool_use.input` in the approval key so each distinct invocation is reviewed; for `caution`, per-tool approval is a reasonable convenience but should be a policy choice (`approve_scope: "call"|"tool"|"session"`), not an accident. Add a regression test where an approved `drive_run("ls")` is followed by `drive_run("rm -rf /")` and assert the second call goes back to pending.

**M1. Legacy REST-MCP code still wired.** `app/mcp/client.py` (the not-really-MCP client) is still imported by `main.py`, `routers/mcp.py`, and `tool_registry.py` to serve pre-existing `legacy` transport rows. Phase 8 called for a one-time migrator and removal. Acceptable as transitional debt, but decide a kill date: ship `forge system mcp migrate-legacy` (re-register each legacy row's URL as `http` transport, mark the row, warn on any that fail), then delete client.py and its branches.

**M2. No streaming tool-call events from native adapters.** `ToolUseStart`/`ToolUseDelta` exist in the kernel and are emitted only by `kernel_bridge.py`. Anthropic/OpenAI/Google `stream_turn` yield text deltas and then deliver tool calls all at once inside `TurnDone`. Functionally correct (the loop keys off TurnDone), but the chat UI cannot show "calling cu.steer_click..." until the model's whole turn finishes, which will feel laggy exactly when Forge is doing its most impressive work. The Anthropic SDK surfaces `input_json_delta` stream events; wire them through, same for OpenAI tool-call deltas.

**M3. APPROVAL_PENDING is delivered as an error and relies on the model to retry.** The pending state returns `is_error=True`, and nothing in `sessions.py` re-executes pending tools after a human approves; the flow works because the approval lookup succeeds on the model's next attempt, but the model has to choose to attempt again, and error-shaped results push models toward apologizing and giving up. Two-part fix: return pending as a non-error informational result with explicit instructions ("tell the user to approve in the inbox, then this tool can be retried"), and on the next session message, auto-retry any tool calls whose approvals flipped to approved before invoking the model.

**L1.** `AnthropicProvider.count_tokens` is a `len//4` estimate while compaction thresholds depend on it; Anthropic exposes a real token-counting endpoint now, use it with the estimate as fallback.
**L2.** `make parity` shells into `backend/.venv/bin/pytest`, which does not exist outside your machine; use `python -m pytest` so CI and containers can run it (the parity tests themselves pass, they ran inside the main suite).
**L3.** Lint: 8 ruff findings in `backend/app` (5 are import-order I001), and `cli/` is outside CI's lint scope (`ruff check app/` only) with a large backlog; extend the workflow to `cli/`.
**L4.** README tests badge says 928; backend collects 868. If the number includes frontend vitest and CLI suites, document the composition; otherwise it is stale.

None of these regress the audit-one findings; H1 is the only one I would block a release on, and it is a small diff.

---

## Phase 9: Dynamic Orchestration (agents the ultracode way)

**Goal.** Stop requiring users to hand-assemble agents (name, system_prompt, tools, workflow_steps) before anything can happen. Instead, the model plans and spawns scoped sub-agents on demand: the user states a goal, Forge's session model decides whether it warrants a workflow, writes the workflow as a structured artifact, fans out parallel sub-agents whose intermediate state lives in the DAG rather than the parent context, verifies results adversarially, and offers to save the workflow as a rerunnable blueprint. Manual agent creation remains as a template library (guardrail: zero feature loss), but it stops being the front door.

**Why Forge is unusually close.** You already have the four hard parts: a DAG engine with concurrent layer execution (the "orchestration script"), a sessions surface with budgets, an approvals inbox, and multi-machine dispatch plus tmux agent control that Claude Code itself does not have. Phase 9 is mostly compilation and glue.

### 9.1 Kernel types (forge-kernel)

Add to `forge_kernel/types.py` (bump forge-kernel to 0.2.0):

```
SubAgentSpec  = { role, prompt, tools: list[str] | "inherit", model: str | None,
                  budget: {max_tokens, max_seconds} | None, success_criteria: str,
                  inputs: dict, outputs: list[str] }
WorkflowStage = { id, kind: "fanout"|"single"|"verify"|"reduce",
                  agents: list[SubAgentSpec], depends_on: list[str],
                  concurrency: int | None, target: str | None }   # target = dispatch machine
WorkflowSpec  = { title, rationale, stages: list[WorkflowStage],
                  max_concurrent: int = 16, max_agents_total: int = 200,
                  worker_model: str | None, verify: bool = True }
WorkflowPlanProposed / WorkflowProgress / WorkflowDone  # new StreamEvents for the session feed
```

Publish the JSON schema for `WorkflowSpec` from the dataclasses (reuse `serialize.py`) so the planner tool's input_schema is generated, never hand-maintained.

### 9.2 Planner

New builtin ToolSpec `orchestrate.plan` (safe): given the goal and a capability inventory (tool names + descriptions from the ToolPlane, available ModelCards, dispatch targets), the session model returns a `WorkflowSpec`. Prompt template lives in the existing prompt-versioning system as `planner/v1` so it is diffable and eval-able. Additive `effort` column on `sessions` (`standard|high|ultra`, default standard): at `ultra` the loop invokes the planner automatically for any substantive message (heuristic: model self-classifies via a cheap card); at lower effort it fires only on explicit request or the literal keyword `ultra`/`workflow` in the prompt, mirroring how the Claude Code keyword opt-in works. Planner always runs on the session's model; `worker_model` defaults to the cheapest ModelCard with `tools=True` unless a stage overrides, so fan-out stages do not burn flagship tokens.

### 9.3 Compiler

`backend/app/services/orchestration/compiler.py`: `WorkflowSpec -> blueprint dict` targeting the existing engine, plus ephemeral agents. Additive columns on `agents`: `ephemeral bool default false`, `spawned_by_session text null`, `spec_json text null`. Each `SubAgentSpec` becomes an ephemeral agent row (auditable, visible in the dashboard, garbage-collectible) and a node in the compiled blueprint. New node type `subagent_run` (registry entry number 45): executes a scoped `run_agent_turn` with its own message list seeded from `inputs`, the spec's tool allowlist resolved through the ToolPlane, its own `Budget`, and the parent's permission policy (inherit, never elevate). Its return value is the node output, so intermediate state lives in DAG edges, not the parent context: the same trick that keeps ultracode's main context clean. `fanout` stages compile to N parallel `subagent_run` nodes in one topological layer; add a per-run semaphore honoring `max_concurrent` and a hard `max_agents_total` ceiling that aborts compilation, not execution.

### 9.4 Verification stage

Unless `verify=false`, the planner template appends a `verify` stage: a reviewer sub-agent that receives the goal, each producer's `success_criteria`, and their outputs, and must return `{verdict: pass|fail, findings}` per item; failures route back through one bounded retry of the producing agent with the findings attached. This generalizes `cu_verifier` from computer use into the whole platform and is the piece that makes fan-out trustworthy: the judge never wrote the answer it is judging.

### 9.5 Session integration and consent

When a plan is produced, the loop does not execute it. It emits `WorkflowPlanProposed` carrying the spec; the chat UI renders a plan card (stages, agent counts, models, estimated token budget) with Run / Edit / Save / No, and the CLI prints the same with y/e/s/n. Runs above a configurable agent threshold require the explicit confirm even at `ultra`. Save persists the compiled blueprint to the library with the spec as metadata: rerunnable, forkable, marketplace-publishable. That is your equivalent of ultracode's save-the-script loop, except Forge's saved artifact is a visual DAG a user can open in the editor, which is a genuinely better version of the idea. During execution, `WorkflowProgress` events feed a live progress strip (per stage: running/done agent counts, tokens spent from aggregated Budgets, elapsed), and the recorder captures every sub-agent's transcript so time-travel replay and fork work at workflow scale: no competing harness has that.

### 9.6 Surfaces and demotions

`dashboard/orchestrate` becomes the live view of dynamic runs (the old task_groups Orchestrator with its coordinator/supervisor/worker roles is superseded; port its inter-agent messaging into `subagent_run` as an optional mailbox, then retire `orchestration.py` routes behind a deprecation window). `dashboard/agents` is relabeled Agent Templates; the planner may reference saved templates by name as roles, so manual creation gains a purpose instead of losing one. CLI: `forge chat --effort ultra`, `forge workflows list|run|save`.

### 9.7 Tests and exit criteria

Golden: a fixed goal + FakeProvider planner output compiles to a deterministic blueprint snapshot. Behavior: fan-out of 6 with `max_concurrent=2` never exceeds 2 in flight; a seeded wrong answer is caught by the verify stage and corrected on retry; parent context token count stays flat while sub-agents process a 50-item corpus; cancellation mid-fanout stops all children; budget exhaustion halts scheduling of new agents; a saved workflow reruns from the library with identical structure; `ephemeral` agents are excluded from the default agents list but visible with a filter; the full parity suite and all manual-agent flows pass untouched. Exit demo: in chat at `ultra`, "audit every router for missing auth checks" produces a plan card, fans out one scout per router file on the cheap model, a verifier cross-checks findings on the session model, and the result cites files, all within the run's budget, resumable after a backend restart.

### Suggested CC prompt

"Read docs/harness-plan.md and docs/forge-v3-audit-and-phase9.md. First fix H1 (input-scoped approvals for dangerous tools) with the regression test described, then M3, then implement Phase 9 sections 9.1 through 9.7 in order under the existing guardrails: additive migrations, no feature removal, parity suite green before every commit, one commit per section. Stop and report if the compiler or subagent_run design conflicts with existing engine behavior rather than choosing silently."
