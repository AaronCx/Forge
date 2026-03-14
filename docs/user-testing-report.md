# AgentForge User Testing Report

**Date:** 2026-03-14
**Tester:** Claude Code (autonomous user simulation)
**Frontend:** https://agentforge-six.vercel.app
**Backend:** https://agentforge-api.onrender.com (v1.9.0)
**Method:** Playwright browser automation against live deployment

---

## What Worked Out of the Box

- **Landing page** — Hero section, feature cards, "Try Demo" button, Sign Up / Sign In links all functional
- **Authentication** — Email/password login with Supabase, GitHub OAuth button present, session persistence via cookies
- **Dashboard** — Stats cards (Total Agents, Total Runs, Tokens Used, Runs This Hour), recent blueprints, recent runs sections
- **Agent list** — Shows user agents and 4 template agents (Document Analyzer, Research Agent, Data Extractor, Code Reviewer) with Run/Edit buttons and tool badges
- **Agent creation** — Form with name, description, system prompt, model selector (6 providers), tool checkboxes. Agent appears in list after creation
- **Blueprint list** — Shows 13 blueprint templates with node type badges, "Use Template" and "New Blueprint" buttons
- **Blueprint editor** — React Flow canvas renders correctly. Node Palette has 44 node types across 9 categories (Context, Transform, Validate, Agent, Output, GUI, Terminal, CU Agent, Agent Control). Config panel appears on node click with appropriate fields. Save, Run, Delete Node all present
- **Monitor page** — Live status indicator, active agent cards with progress bars, event timeline with agent filters. Demo mode shows realistic data
- **Analytics page** — Cost summary cards (Today/Week/Month), monthly projection, token breakdown (Input/Output), cost by agent, cost by model. Handles zero data gracefully
- **Orchestrate page** — Objective input, tool selection buttons (Web Search, Document Reader, Code Executor, Data Extractor, Summarizer), Start Orchestration button
- **Settings page** — Provider config with 6 providers (OpenAI, Anthropic, Ollama, Groq, Together AI, Fireworks AI), API key input, MCP Connections section with Add Server, API Keys management with Generate/Delete, Computer Use dependency checker
- **Triggers page** — Shows webhook and cron triggers with demo data, webhook URL displayed, fire count and last-fired timestamps, History/Disable/Delete actions, New Trigger form with type/target/cron expression
- **Approvals page** — Pending/All tab filter, empty state message about approval gates
- **Traces page** — Summary cards (Total Spans, Errors, Error Rate, Total Tokens, Avg Latency), span type filters (agent step, llm call, tool call, node execution, blueprint step)
- **Prompts page** — "Select an agent to view prompt versions" guidance
- **Knowledge page** — New Collection button, two-pane layout (collections list + document viewer/search)
- **Evals page** — New Suite button, description text
- **Compare page** — Model selection (0/5), system prompt, user prompt, temperature/max tokens controls, Compare Models button
- **Runs page** — Run history with empty state guidance
- **CLI** — 35 commands covering agents, blueprints, runs, costs, evals, triggers, knowledge, marketplace, teams, orchestration, MCP, computer-use, recordings, targets, tools. `agentforge --help` and `agentforge version` work
- **API docs** — Swagger UI loads at /docs with 126 endpoints across 101 path groups

## What Was Broken and Fixed

| # | What Was Broken | Fix | Commit |
|---|---|---|---|
| 1 | Vercel env vars had literal `\n` appended, corrupting Supabase URL and causing "Unsupported provider" login error | Removed and re-added all NEXT_PUBLIC env vars via `npx vercel env rm/add` | (env fix, no code commit) |
| 2 | CI tests patched removed `provider_registry` global instead of `create_user_registry` | Updated test mocks to patch `create_user_registry` with AsyncMock | `e89af35` |
| 3 | Template seeding failed with FK constraint — system UUID not in auth.users | Changed seed code to look up first real user_id from agents table | `7bce67e` |
| 4 | Trigger page used hardcoded `process.env.NEXT_PUBLIC_API_URL \|\| "http://localhost:8000"` | Replaced with `API_URL` from shared constants module | `9dee701` |
| 5 | Blueprint templates not loading in demo mode (no API call made) | Added `api.blueprints.templates().then(setTemplates)` in demo mode branch | `9dee701` |
| 6 | Compare page redirected to /login in demo mode (no `isDemoMode()` check) | Added `if (isDemoMode()) return;` early return in useEffect | `5fc55ec` |
| 7 | Blueprint Edit page redirected to /login in demo mode | Added `if (isDemoMode()) return;` early return in load() | `5fc55ec` |
| 8 | Marketplace page hung on "Loading..." in demo mode (API call with no token) | Added `isDemoMode()` check to skip API calls and show empty state | `aa610b9` |
| 9 | Team page hung on "Loading..." in demo mode (API call with no token) | Added `isDemoMode()` check to skip API calls and show empty state | `aa610b9` |
| 10 | Placeholder OPENAI_API_KEY on Render registered a broken global provider | Removed via Render API PUT to env vars endpoint | (env fix, no code commit) |

## What's Still Broken / Not Testable

- **Agent execution (Run)** — Requires a configured LLM provider with a valid API key. Cannot test SSE streaming, run history population, or token/cost tracking without real API keys
- **Blueprint execution** — Same as above — node status animation and execution trace require LLM calls
- **Orchestration execution** — Requires LLM to decompose objectives into tasks
- **Eval suite execution** — Cannot run eval cases without a configured model
- **Knowledge base RAG** — Upload and embedding generation require backend processing with an embedding model
- **Marketplace publishing** — No existing marketplace listings to test fork/install flow
- **Computer Use** — Requires macOS GUI tools (Steer, Drive) which are not installed; server-side detection shows Linux deps instead of macOS
- **CLI remote commands** — CLI defaults to localhost; needs `agentforge init` with Render URL to work against deployed backend

## Missing Features

- **Runs page** — No demo data for run history in demo mode (shows empty state while other pages show demo data)
- **Marketplace** — No demo listings in demo mode
- **Team** — No demo organizations in demo mode
- **Prompts** — No demo agent list to select from in demo mode (just shows "Select an agent" with nothing to select)
- **Knowledge** — No demo collections in demo mode
- **Evals** — No demo suites in demo mode

## UX Issues

1. **Node Palette z-index** — In the blueprint editor, the Node Palette sidebar overlaps the main dashboard sidebar navigation links, making them unclickable when the palette is expanded
2. **Computer Use platform detection** — Shows Linux dependencies (apt install xdotool, etc.) even when the user's machine is macOS. Detection runs server-side on Render instead of client-side
3. **Demo mode inconsistency** — Some pages (Monitor, Analytics, Triggers, Agents, Dashboard) have rich demo data, while others (Runs, Marketplace, Team, Knowledge, Prompts, Evals) show empty states. This makes the demo feel incomplete
4. **Settings user email** — The email in the sidebar briefly shows empty before loading, causing a flash
5. **CLI requires manual init** — No guidance on first run about configuring the API URL for remote deployment

## Recommended Priority Fixes

1. **Add demo data to remaining pages** — Runs, Marketplace, Evals, Knowledge, and Prompts pages should show demo data like the rest of the app for a consistent demo experience
2. **Fix Node Palette z-index** — The palette overlay blocking sidebar navigation is a usability issue that affects all blueprint editing sessions
3. **Fix Computer Use platform detection** — Should detect the user's actual platform (client-side) rather than the server platform
4. **Add CLI init guidance** — Show a helpful message on first CLI command pointing users to `agentforge init` with instructions for configuring the API URL
5. **Add empty state CTAs** — Pages like Runs ("No runs yet") should link directly to the agent creation or agent run page to reduce friction

---

## Test Coverage Summary

| Journey | Description | Status |
|---|---|---|
| 1 | Visitor discovers project | Pass — landing page, demo mode, all pages load |
| 2 | New user creates first agent | Pass — login, agent creation, agent list |
| 3 | Configure model providers | Pass — settings page, provider form with 6 providers |
| 4 | Blueprint editor | Pass — canvas, nodes, edges, config panel, palette |
| 5 | Analytics/costs | Pass — cost cards, projections, breakdowns, zero-data handling |
| 6 | Monitor live agents | Pass — live status, active agents, event timeline |
| 7 | Orchestration | Partial — UI loads, cannot test execution without LLM key |
| 8 | Evals | Partial — page loads with New Suite button, cannot run without LLM |
| 9 | MCP connections | Pass — Settings MCP section with Add Server button |
| 10 | Triggers | Pass — webhook/cron triggers, create form, history |
| 11 | Knowledge/RAG | Partial — UI loads with collection management, cannot test upload/search |
| 12 | Marketplace | Pass — search, category filters, listing grid (no data in demo) |
| 13 | Approvals | Pass — pending/all tabs, empty state |
| 14 | Traces | Pass — span filters, summary cards |
| 15 | CLI | Pass — 35 commands available, help works, needs remote init |
| 16 | API docs | Pass — Swagger UI loads, 126 endpoints documented |

**Pages tested:** 17/17
**Fixes applied:** 10
**Commits:** 5 code commits + 2 environment fixes
