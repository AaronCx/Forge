# Web ↔ CLI parity matrix

> The noun a user clicks is the noun they type. Six workspaces + a flat system
> layer, two renderings.

Forge's pitch is that the CLI covers every action available in the web UI.
Every sidebar group on the dashboard maps 1:1 to a `forge <workspace>` namespace
in the CLI (PR-2 of the unified-IA spec), and every old top-level CLI noun
keeps resolving as a back-compat alias so muscle memory and scripts don't
break.

This file is the authoritative map between the two surfaces. It is checked
into the repo so any drift fails review. The Playwright smoke test at
`frontend/e2e/demo-parity.spec.ts` walks every route listed below in demo mode
and asserts that each one loads without an error fallback. Add a row here when
you add a CLI command group **or** a web route — both must move together.

---

## Studio · `forge studio`

> Agents, blueprints, prompts/knowledge (library), and the embedded workspace.

| Web surface | CLI canonical | CLI legacy alias | Notes |
| --- | --- | --- | --- |
| `/dashboard/agents` | `forge studio agents …` | `forge agents …` | list / create / run / show / edit / delete / templates |
| `/dashboard/blueprints` | `forge studio blueprints …` | `forge blueprints …` | list / create / show / run / export / import / inspect |
| `/dashboard/library` (tab: Prompts) | `forge studio prompts …` | `forge prompts …` | PR-4 tabbed home; `/dashboard/prompts` still resolves |
| `/dashboard/library` (tab: Knowledge) | `forge studio knowledge …` | `forge knowledge …` | PR-4 tabbed home; `/dashboard/knowledge` still resolves |
| `/dashboard/workspace` | `forge studio workspace …` | `forge workspace …` | files / read / write / search / open / history |

---

## Operations · `forge ops`

> The run-lifecycle workspace. PR-5 added a kanban board (`/dashboard/ops`)
> across **Queued · Running · Awaiting Approval · Done · Failed**; the CLI
> mirrors the columns via `--status`.

| Web surface | CLI canonical | CLI legacy alias | Notes |
| --- | --- | --- | --- |
| `/dashboard/ops` (board) | `forge ops runs list --status <col>` | `forge runs list --status <col>` | columns: queued, running, awaiting-approval, done, failed |
| `/dashboard/ops` (board, single card) | `forge ops runs show <id>` | `forge runs show <id>` | run detail incl. trace + recording links |
| `/dashboard/ops` (card cancel) | `forge ops runs cancel <id>` | `forge runs cancel <id>` |  |
| `/dashboard/ops/approvals` | `forge ops approvals list` | `forge approvals list` | Awaiting-Approval column items |
| inline Approve on board | `forge ops approve <id>` *or* `forge ops approvals approve <id>` | `forge approvals approve <id>` | PR-5 shortcut + legacy form |
| inline Reject on board | `forge ops reject <id>` *or* `forge ops approvals reject <id>` | `forge approvals reject <id>` | PR-5 shortcut + legacy form |
| `/dashboard/triggers` (deep link from board) | `forge ops triggers …` | `forge triggers …` | list / create / toggle / edit / delete / history |
| `/dashboard/traces` (drawer) | `forge ops traces …` | `forge traces …` / `forge trace <id>` | list / stats / get |
| `/dashboard/recordings` (drawer) | `forge ops recordings …` | `forge recordings …` | list / play / delete |
| `/dashboard/messages` (drawer) | `forge ops messages …` | `forge messages …` / `forge mail …` | list / conversation |
| `/dashboard/orchestrate` | `forge ops orchestrate …` | `forge orchestrate …` | submit objective |
| `/dashboard/orchestrate` (group view) | `forge ops groups …` | `forge orchestrate-groups …` | spec rename: orchestrate-groups → groups |

---

## Evals · `forge evals`

> Eval suites and side-by-side model comparison.

| Web surface | CLI canonical | CLI legacy alias | Notes |
| --- | --- | --- | --- |
| `/dashboard/evals` (tab: Suites) | `forge evals list` / `run` / `create` / `add-case` | — | PR-4 tabbed home; backing route unchanged |
| `/dashboard/evals` (tab: Compare) | `forge evals compare …` | `forge compare …` | `/dashboard/compare` still resolves as deep link |

---

## Connections · `forge connections`

> Model providers, MCP servers, execution targets, computer-use config, tools.
> PR-4 tabbed home; the Computer-Use **live view** is still one click away as a
> deep link from any workspace.

| Web surface | CLI canonical | CLI legacy alias | Notes |
| --- | --- | --- | --- |
| `/dashboard/connections` (tab: Providers) | `forge connections providers …` | `forge models …` | spec rename: models → providers |
| `/dashboard/connections` (tab: MCP) | `forge connections mcp …` | `forge mcp …` | connect / list / test / tools |
| `/dashboard/connections` (tab: Targets) | `forge connections targets …` | `forge targets …` |  |
| `/dashboard/connections` (tab: Computer Use, config) | `forge connections computer-use …` | `forge computer-use …` / `forge cu …` | `backends_app` nested inside |
| `/dashboard/computer-use` (live view) | — | — | wow feature — kept reachable in 1 click |
| (no dedicated route) | `forge connections tools …` | `forge tools …` | list built-in + MCP tools |

---

## Marketplace · `forge marketplace`

| Web surface | CLI canonical | CLI legacy alias | Notes |
| --- | --- | --- | --- |
| `/dashboard/marketplace` | `forge marketplace browse / publish / show / rate / fork / unpublish` | — | name unchanged |

---

## Settings · `forge settings`

| Web surface | CLI canonical | CLI legacy alias | Notes |
| --- | --- | --- | --- |
| `/dashboard/team` | `forge settings team …` | `forge teams …` | spec rename: teams → team |
| `/dashboard/settings/api-keys` | `forge settings api-keys …` | `forge keys …` | spec rename: keys → api-keys |
| `/dashboard/settings` (preferences) | `forge settings config …` | `forge config …` | show / set / set-provider / set-default-model |
| `/login` | `forge auth …` | `forge login` / `forge logout` / `forge whoami` | signup / login / logout / whoami / keys |

---

## System layer (flat, no workspace)

> Lifecycle and observability of the local stack.

| Command | Purpose |
| --- | --- |
| `forge init` | One-time config bootstrap |
| `forge up` / `down` / `restart` | Start, stop, recycle backend + frontend |
| `forge status` | Active runs table |
| `forge health` | Service liveness summary |
| `forge dashboard` | Rich TUI dashboard |
| `forge version` | CLI version |
| `forge costs` | Token + cost rollup |
| `forge map` | Print the workspace → command tree (mirrors the sidebar). PR-6. |

---

## Vocabulary table (web ↔ CLI)

Every label in the sidebar matches a CLI namespace. Drift is a defect.

| Web label | CLI namespace | Renamed from |
| --- | --- | --- |
| Studio | `studio` | (new grouping) |
| Operations | `ops` | (new grouping) |
| Evals | `evals` | — |
| Connections | `connections` | (new grouping) |
| Marketplace | `marketplace` | — |
| Settings | `settings` | (new grouping) |
| Library | `studio` (Prompts + Knowledge tabs) | (new grouping) |
| Providers | `connections providers` | Models |
| Team | `settings team` | Teams |
| API Keys | `settings api-keys` | keys |
| Computer Use (config) | `connections computer-use` | — |
| Computer Use (live view) | (link from any workspace) | — |

---

## How to extend this matrix

1. Add the row under the relevant workspace section above.
2. If you added a web route: register it in the `ROUTES` constant in
   `frontend/e2e/demo-parity.spec.ts` so the smoke test catches a 404 / error
   fallback.
3. If you added a CLI command group: put it in the right
   `cli/forge/commands/<workspace>.py` module and mount it on the workspace
   parent in `main.py`. If the old top-level name was already in use, keep it
   working as an alias (`_mod.register(app)` already does this for sub-apps).
4. If the route reads from a live API endpoint, mirror it in the demo seed in
   `frontend/lib/demo/seed.ts` (or split into a per-fixture file under
   `frontend/lib/demo/`).
5. Mark every fixture row in the web component with `data-seeded="true"` so
   the smoke test can tell a seeded surface from an empty one.
