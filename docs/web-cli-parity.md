# Web ↔ CLI parity matrix

Forge's pitch is that the CLI covers every action available in the web UI. This
file is the authoritative map between CLI command groups and their matching web
routes. It is checked into the repo so any drift fails review.

The Playwright smoke test at `frontend/e2e/demo-parity.spec.ts` walks every
route listed below in demo mode and asserts that each one loads without an
error fallback. Add a row here when you add a CLI command group **or** a web
route — both must move together.

## Matrix

| CLI command group                                                   | Web route                                          | Status              | Notes                              |
|---------------------------------------------------------------------|----------------------------------------------------|---------------------|------------------------------------|
| `forge init` / `up` / `down` / `restart` / `status` / `health` / `dashboard` (TUI) | —                                                  | CLI-only            | Stack/runtime management           |
| `forge auth signup` / `login` / `logout` / `whoami`                 | `/login`, `/dashboard/settings`                    | ✅                   |                                    |
| `forge config show` / `set` / `set-provider` / `set-default-model`  | `/dashboard/settings`, `/dashboard/providers`      | ✅                   |                                    |
| `forge agents list` / `create` / `run` / `history` / `templates`    | `/dashboard/agents`                                | ✅                   |                                    |
| `forge blueprints list` / `create` / `run` / `export` / `import`    | `/dashboard/blueprints`                            | ✅                   | Demo seeds 5 blueprints (PR 3)     |
| `forge orchestrate`                                                 | `/dashboard/orchestrate`                           | ✅                   |                                    |
| `forge costs` (incl. `--breakdown {agent,model,provider}`)          | `/dashboard#usage`                                 | ✅                   | Provider breakdown added in PR 2   |
| `forge models list` / `test` / `compare`                            | `/dashboard/providers`                             | ✅                   | NEW route, PR 5                    |
| `forge evals create` / `add-case` / `run` / `results`               | `/dashboard/evals`                                 | ✅                   |                                    |
| `forge knowledge create` / `upload` / `search`                      | `/dashboard/knowledge`                             | ✅                   |                                    |
| `forge cu status` / `see` / `ocr` / `click` / `type` / `focus` / `find` | `/dashboard/computer-use`                       | ✅                   | NEW route, PR 5                    |
| `forge runs list`                                                   | `/dashboard/runs`                                  | ✅                   | Each row links to its trace        |
| `forge triggers list`                                               | `/dashboard/triggers`                              | ✅                   |                                    |
| `forge approvals list`                                              | `/dashboard/approvals`                             | ✅                   |                                    |
| `forge traces list`                                                 | `/dashboard/traces`                                | ✅                   |                                    |
| `forge prompts list`                                                | `/dashboard/prompts`                               | ✅                   |                                    |
| `forge marketplace browse`                                          | `/dashboard/marketplace`                           | ✅                   |                                    |
| `forge mcp list`                                                    | `/dashboard/mcp`                                   | ✅                   | NEW route, PR 5                    |
| `forge targets list`                                                | `/dashboard/targets`                               | ✅                   | NEW route, PR 5                    |
| `forge recordings list`                                             | `/dashboard/recordings`                            | ✅                   | NEW route + `/api/recordings`, PR 5|
| `forge keys list`                                                   | `/dashboard/settings/api-keys`                     | ✅                   | NEW route, PR 5                    |
| Workspace operations (CodeMirror + tree + xterm)                    | `/dashboard/workspace`                             | ✅                   | Demo gets read-only sandbox (PR 4) |

## How to extend this matrix

1. Add the row to the table above.
2. Add the route to the `ROUTES` constant in
   `frontend/e2e/demo-parity.spec.ts`. The test will fail if the route 404s
   or renders an error in demo mode.
3. If the route reads from a live API endpoint, mirror it in the demo seed in
   `frontend/lib/demo/seed.ts` (or split into a per-fixture file under
   `frontend/lib/demo/`).
4. Mark every fixture row with `data-seeded="true"` so the smoke test can tell
   a seeded surface from an empty one.
