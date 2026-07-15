# Forge

**Agentic AI orchestration platform — design workflows visually, automate GUIs and terminals, and coordinate agents across machines.**

Build AI-powered workflows that chain LLM reasoning with deterministic logic, automate any desktop or terminal, and orchestrate multiple agents in parallel. Visual DAG editor with 45 node types, cross-platform computer use, multi-model provider support, and real-time execution streaming. Runs fully local with SQLite (zero external accounts) or scales to cloud with Supabase.

![Version](https://img.shields.io/badge/version-3.0.0-blue)
![Tests](https://img.shields.io/badge/tests-977_passing-brightgreen)
![Next.js](https://img.shields.io/badge/Next.js-15-black)
![FastAPI](https://img.shields.io/badge/FastAPI-0.138-teal)
![Python](https://img.shields.io/badge/Python-3.12-blue)
![TypeScript](https://img.shields.io/badge/TypeScript-5-blue)
![License](https://img.shields.io/badge/license-MIT-green)

---

## Features

### Chat & Sessions
Durable, resumable conversations with any model and the full tool plane available
(`dashboard/chat`, `forge chat`, or headless `forge agent run --json`). Switch
models mid-thread, and long threads are compacted automatically (the oldest span
is summarized into a pinned note while the originals are kept, so it is
reversible). When a session has a workspace root, its `AGENTS.md` (falling back
to `CLAUDE.md`) is injected into the system prompt.

### Dynamic Orchestration (agents the planned way)
State a goal; the session model plans a workflow of scoped sub-agents
(`orchestrate.plan`), you approve it on a plan card (web) or `y/e/s/n` prompt
(CLI), and Forge fans out parallel `subagent_run` nodes whose intermediate
state lives in the DAG — not your chat context. An adversarial verify stage
judges every producer against its success criteria with one bounded retry.
Plans can be saved to the library as rerunnable blueprints (`forge workflows
list|run|save`). Sessions carry an `effort` level (`standard|high|ultra`);
at ultra the planner engages automatically for substantive requests. Runs
above a configurable agent threshold always require explicit confirmation.

### Visual Blueprint System
Drag-and-drop DAG workflow builder with 45 node types across 10 categories. Topological execution engine with concurrent layer resolution, context assembly with token budgets, retry policies, and SSE-streamed execution traces.

### Computer Use (GUI + Terminal)
Agents operate machines through GUI automation and terminal orchestration across macOS, Linux, and Windows:

| Capability | Nodes | What It Does |
|-----------|-------|-------------|
| **GUI (Steer)** | 12 | Screenshot, OCR, click, type, hotkey, scroll, drag, focus, find, wait, clipboard, app listing |
| **Terminal (Drive)** | 6 | Session management, command execution, key sending, log capture, polling, parallel fanout |
| **CU Agents** | 4 | LLM-powered Planner, Analyzer, Verifier, Error Handler |
| **Screen Recording** | 1 | Record sessions via CoreGraphics + ffmpeg (works over SSH) |
| **Safety** | — | App/command blocklist, rate limiting, approval gates, audit logging |

### Cross-Platform Support

| Platform | GUI Automation | Terminal | Method |
|----------|---------------|----------|--------|
| macOS | Native Steer CLI (CoreGraphics, cliclick, Vision OCR) | Drive CLI / tmux | Works over SSH |
| Linux | xdotool, scrot, tesseract, wmctrl, xclip | tmux | Xvfb for headless |
| Windows | pyautogui, pytesseract, pygetwindow | PowerShell + WSL/tmux | Python packages |

### Agent-on-Agent Orchestration
Spawn and control external coding agents (Claude Code, Codex CLI, Gemini CLI, Aider) as workers in tmux sessions. Full lifecycle management with 6 agent control blueprint nodes.

### Multi-Machine Dispatch
Route blueprint nodes to different execution targets. Dispatch routing: explicit target → blueprint default → capability-based → local fallback.

### Multi-Model Providers
Provider registry supporting OpenAI, Anthropic, Google, Ollama, and any OpenAI-compatible endpoint. Per-node model selection, health monitoring, and comparison tools. Model capabilities (context window, vision, tool support) are data-driven model cards you can refresh from each provider (`forge providers refresh`) and override per user.

### Knowledge Base + RAG
Document collections with chunked upload, semantic search, and a `knowledge_retrieval` blueprint node for RAG-augmented workflows.

### Eval Framework
Test agent outputs with grading methods: exact_match, contains, json_schema, screenshot_match, ocr_contains. Multi-model comparison and per-prompt-version evaluation.

### Human-in-the-Loop
`approval_gate` blueprint node pauses execution for human review. Approve/reject with inbox UI and CLI.

### MCP (both directions)
Real Model Context Protocol (JSON-RPC 2.0) via the official SDK. **As a client**, agents discover and use tools from stdio or Streamable HTTP MCP servers (`mcp.<server>.<tool>`, outputs fenced as untrusted data). **As a server**, Forge exposes its tool plane to any MCP client such as Claude Code or Codex — see [docs/mcp-server.md](docs/mcp-server.md).

### Observability + Prompt Versioning
Distributed trace recording for all executions. Version prompts like code — diff, rollback, and measure how changes affect output quality.

### Workflow Marketplace
Publish, browse, fork, and rate blueprints. Organization support with member RBAC.

### Workspace IDE
Integrated development environment with CodeMirror 6 web editor, file tree, editor tabs, integrated terminal (xterm.js), and agent activity panel. Real-time file sync via WebSocket — when an agent modifies a file, you see it instantly. Agents operate directly on your files through the tool plane's `workspace.read/write/list/search` tools.

### Tool Plane
Every Forge capability — the 45 blueprint nodes (`node.<key>`), saved blueprints (`blueprint.<slug>`), computer-use actions (`cu.<action>`), workspace ops (`workspace.<op>`), agent control (`agent.<op>`), and discovered MCP tools (`mcp.<server>.<tool>`) — is a callable tool behind one permission policy (allow / ask / deny by `danger_level`, per-user overrides, approvals inbox). Agents call your features seamlessly; the native kernel loop drives them on any provider.

### Live Dashboard + CLI
Real-time monitoring with heartbeat tracking, SSE-powered updates, cost analytics. CLI-first experience with 35+ command groups covering the full platform — no browser required.

---

## Node Types (45)

| Category | Count | Nodes |
|----------|-------|-------|
| Context | 3 | fetch_url, fetch_document, knowledge_retrieval |
| Transform | 2 | text_splitter, template_renderer |
| Validate | 2 | json_validator, run_linter |
| Output | 3 | output_formatter, webhook, approval_gate |
| Agent (LLM) | 5 | llm_generate, llm_summarize, llm_extract, llm_review, llm_implement |
| GUI (Steer) | 13 | steer_see, steer_ocr, steer_click, steer_type, steer_hotkey, steer_scroll, steer_drag, steer_focus, steer_find, steer_wait, steer_clipboard, steer_apps, recording_control |
| Terminal (Drive) | 6 | drive_session, drive_run, drive_send, drive_logs, drive_poll, drive_fanout |
| CU Agent | 4 | cu_planner, cu_analyzer, cu_verifier, cu_error_handler |
| Agent Control | 6 | agent_spawn, agent_prompt, agent_monitor, agent_wait, agent_stop, agent_result |
| Orchestration | 1 | subagent_run |

Every node is also callable directly as a `node.<key>` tool through the
[tool plane](#tool-plane); workspace file operations are available there as
`workspace.read/write/list/search`.

---

## Architecture

```mermaid
graph TB
    subgraph Frontend["Frontend (Next.js 15)"]
        UI[React UI + shadcn/ui]
        Auth[Supabase Auth]
        SSE[SSE Client]
        Editor[Blueprint Editor]
    end

    subgraph Backend["Backend (FastAPI)"]
        API[REST API]
        Engine[Blueprint Engine]
        Orchestrator[Orchestrator]
        Messaging[Messaging Service]
        Providers[Provider Registry]
        CU[Computer Use]
        Dispatch[Multi-Machine Dispatch]
        Agents[Agent-on-Agent]
        Stream[SSE Streaming]
    end

    subgraph ComputerUse["Computer Use Layer"]
        Steer[GUI - Steer/xdotool/pyautogui]
        Drive[Terminal - Drive/tmux/PowerShell]
        Recorder[Screen Recorder]
        Safety[Safety + Audit]
    end

    subgraph External["External Services"]
        OpenAI[OpenAI API]
        Anthropic[Anthropic API]
        Google[Google AI]
        Ollama[Ollama / local]
        Supabase[(Supabase DB)]
        MCP[MCP Servers]
    end

    UI --> API
    UI --> Auth
    SSE --> Stream
    Editor --> Engine
    API --> Engine
    API --> Orchestrator
    Engine --> Providers
    Engine --> CU
    CU --> Steer
    CU --> Drive
    CU --> Recorder
    CU --> Safety
    Dispatch --> CU
    Agents --> Drive
    Orchestrator --> Messaging
    Providers --> OpenAI
    Providers --> Anthropic
    Providers --> Google
    Providers --> Ollama
    API --> Supabase
    API --> MCP
```

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Next.js 15, TypeScript, Tailwind CSS, shadcn/ui, React Flow, Bun |
| Backend | Python 3.12, FastAPI, forge-kernel; OpenAI, Anthropic, Google, Ollama, any OpenAI-compatible |
| Computer Use | CoreGraphics, cliclick, Vision OCR, ffmpeg, tmux, xdotool, pyautogui |
| CLI | Typer, Rich, httpx |
| Database | SQLite (default, zero config) or PostgreSQL via Supabase |
| Auth | Local JWT (default) or Supabase Auth (email + GitHub OAuth) |
| Testing | pytest (868 tests), vitest + testing-library (60 tests) |
| Deployment | Vercel (frontend), Render (backend) |
| CI/CD | GitHub Actions (Ruff, mypy, pytest, ESLint, tsc, vitest) |

---

## Quick Start

```bash
# Clone and setup
git clone https://github.com/AaronCx/Forge.git
cd Forge
./setup.sh

# Add an LLM provider key
edit backend/.env              # Add OpenAI, Anthropic, or use Ollama for local models

# Start everything
forge up

# Open the dashboard
forge dashboard           # Terminal TUI
# or visit http://localhost:3000  # Web GUI
```

Three steps. No database accounts. No migration steps. SQLite is created automatically.

### Prerequisites

- Python 3.11+ (backend + CLI)
- [Bun](https://bun.sh) or Node.js (frontend)
- At least one LLM provider: OpenAI, Anthropic, Google, or a local model via [Ollama](https://ollama.com)

No Supabase account needed for local use — the database (SQLite) and auth (local JWT) are built-in.

### Computer Use (macOS)

```bash
./scripts/bootstrap-macos.sh      # Installs deps, builds native CLIs, checks permissions
./scripts/bootstrap-verify.sh     # Smoke tests all 20 Steer + Drive commands
```

<details>
<summary>Linux / Windows setup</summary>

```bash
# Linux
sudo apt install xdotool scrot tesseract-ocr wmctrl xclip tmux xvfb

# Windows
pip install pyautogui pytesseract pygetwindow pyperclip
```

</details>

### Docker

```bash
cp backend/.env.example .env
docker-compose up --build
```

### Stack Management

```bash
forge up          # Start backend + frontend
forge down        # Stop everything
forge restart     # Restart all services
forge status      # Quick health check
forge dashboard   # Live TUI monitor
```

---

## Deployment Options

### Local (recommended for personal use)
- **Database:** SQLite (zero config, auto-created)
- **Auth:** Local JWT (auto-configured)
- **Setup:** `./setup.sh && forge up`
- **External accounts:** None required

### Docker (self-hosted)
- **Database:** SQLite in mounted volume
- **Auth:** Local JWT
- **Setup:** `docker-compose up`

### Cloud (team deployment)
- **Database:** Supabase PostgreSQL
- **Auth:** Supabase Auth (email + GitHub OAuth)
- **Setup:** Create Supabase project, configure keys, deploy to Vercel + Render

### Showcase (forge-theta-teal.vercel.app)
- Demo mode with simulated data
- Optional BYOK for live LLM calls
- No account required

---

## Environment Variables

### Backend (`backend/.env`)

| Variable | Description |
|----------|-------------|
| `OPENAI_API_KEY` | OpenAI API key (optional — use any provider) |
| `ANTHROPIC_API_KEY` | Anthropic API key (optional) |
| `GOOGLE_API_KEY` | Google AI API key (optional) |
| `OLLAMA_BASE_URL` | Ollama endpoint for local models (optional) |
| `SERPAPI_KEY` | SerpAPI key for web search tool (optional) |
| `FRONTEND_URL` | Frontend URL for CORS |
| `CU_DRY_RUN` | `true` for computer use dry-run mode |
| `SUPABASE_URL` | Supabase project URL (only for cloud mode) |
| `SUPABASE_SERVICE_KEY` | Supabase service role key (only for cloud mode) |

For local mode: only LLM provider keys needed. Database and auth are automatic.

### Frontend (`frontend/.env.local`)

| Variable | Description |
|----------|-------------|
| `NEXT_PUBLIC_API_URL` | Backend API URL (required) |
| `NEXT_PUBLIC_SUPABASE_URL` | Supabase project URL (cloud mode only) |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Supabase anonymous key (cloud mode only) |

---

## API

### Authentication

```
Authorization: Bearer <supabase-access-token>
```

### Core

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/agents` | List agents |
| `POST` | `/api/agents` | Create agent |
| `POST` | `/api/agents/:id/run` | Run agent (SSE) |
| `GET` | `/api/blueprints` | List blueprints |
| `POST` | `/api/blueprints` | Create blueprint |
| `POST` | `/api/blueprints/:id/run` | Run blueprint (SSE) |
| `GET` | `/api/blueprints/node-types` | List all 45 node types |
| `POST` | `/api/orchestrate` | Start orchestration (SSE) |

### Computer Use

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/computer-use/status` | Capability report |
| `GET` | `/api/computer-use/config` | Configuration |
| `POST` | `/api/computer-use/refresh` | Refresh capabilities |
| `GET` | `/api/computer-use/audit-log` | Audit log |

### Additional APIs

Runs, Costs, Dashboard, Messages, Orchestration, Providers, Evals, Approvals, Traces, Prompts, Knowledge, Marketplace, Organizations, MCP, Triggers, Targets, API Keys

---

## CLI

The CLI covers every action available in the web UI. A user who never opens a browser can set up, configure, create agents, build blueprints, run workflows, check costs, manage knowledge bases, run evals, and monitor everything from the terminal.

```bash
# Setup & lifecycle
forge init                             # Create ~/.forge/config.toml
forge up                               # Start backend + frontend
forge down                             # Stop everything
forge restart                          # Restart all services
forge status                           # Quick health check
forge health                           # Detailed system health
forge dashboard                        # Live TUI dashboard

# Auth
forge auth signup --email e --password p   # Create account from CLI
forge auth login --email e --password p    # Login, store token
forge auth logout                          # Clear session
forge auth whoami                          # Current user info

# Configuration
forge config show                      # Display config (keys masked)
forge config set api-key <key>         # Set a config value
forge config set-provider openai <key> # Configure provider (updates .env too)
forge config set-default-model gpt-4o  # Set default model

# Agents
forge agents list                      # List agents
forge agents create --name "X" --prompt "..." --tools web_search
forge agents run <id> --input "..."    # Run with streaming output
forge agents history <id>              # Run history for an agent
forge agents templates                 # List available templates

# Blueprints
forge blueprints list                  # List blueprints
forge blueprints create --from-template research
forge blueprints run <id> --input "..."# Run with node-by-node streaming
forge blueprints export <id> -o bp.json# Export as JSON for version control
forge blueprints import bp.json        # Import from JSON

# Multi-agent orchestration
forge orchestrate "objective text"     # Submit and stream

# Cost tracking
forge costs                            # Summary (today/week/month)
forge costs --breakdown agent          # By agent, model, or provider
forge costs --period month             # Monthly view

# Models & providers
forge models list                      # All models across providers
forge models test anthropic            # Test provider connection
forge models compare --prompt "..." --models "gpt-4o,claude-sonnet-4-20250514"

# Evals
forge evals create --name "Quality" --target agent:<id>
forge evals add-case <suite> --input "X" --expected "Y"
forge evals run <suite-id>             # Run eval suite
forge evals results <run-id>           # Detailed results

# Knowledge base
forge knowledge create --name "Docs"
forge knowledge upload <kb-id> ./docs/ # Upload directory
forge knowledge search <kb-id> --query "text"

# Computer use
forge cu status                        # Capability report
forge cu see                           # Take screenshot
forge cu ocr                           # OCR screen text
forge cu click 500 300                 # Click at coordinates
forge cu type "hello"                  # Type text
forge cu focus Safari                  # Focus app
forge cu find "Button Label"           # Find element by text

# Additional command groups
forge runs list                        # View agent runs
forge triggers list                    # Manage event triggers
forge approvals list                   # Human-in-the-loop inbox
forge traces list                      # Execution traces
forge prompts list <agent-id>          # Prompt versioning
forge marketplace browse               # Browse blueprints
forge mcp list                         # MCP connections
forge targets list                     # Execution targets
forge recordings list                  # Screen recordings
forge keys list                        # API key management
```

---

## Testing

```bash
# Backend (917 tests)
cd backend && source .venv/bin/activate
pytest tests/ -v --cov=app

# Frontend (60 tests)
cd frontend && npx vitest run

# Or use the Makefile
# (the tests badge counts backend 917 + frontend 60 = 977)
make test

# Parity safety net — freezes current node + agent behavior so refactors
# can prove they changed nothing they should not have (docs/harness-plan.md).
make parity
```

---

## Project Structure

```
Forge/
├── frontend/                    # Next.js 15 + TypeScript + Tailwind + shadcn/ui
│   ├── app/dashboard/           # 15+ dashboard routes (incl. chat)
│   ├── components/              # Blueprint editor, dashboard, UI primitives
│   └── lib/                     # API client, auth client, demo data
├── forge-kernel/                # The kernel as a zero-dependency pip package
│   ├── forge_kernel/            # Types, model cards, converters, agent loop
│   └── demo/                    # ~30-line standalone agent
├── backend/                     # FastAPI on the Forge-native kernel loop
│   ├── app/
│   │   ├── kernel/              # Tool plane + permissions (rest re-exports forge-kernel)
│   │   ├── mcp/                 # Real MCP client + Forge-as-MCP-server
│   │   ├── db/                  # Pluggable database layer (SQLite + Supabase)
│   │   ├── routers/             # 34 API route modules (incl. auth API, sessions)
│   │   ├── providers/           # Multi-model provider registry
│   │   └── services/
│   │       ├── blueprint_nodes/ # 45 node type executors
│   │       └── computer_use/    # Steer, Drive, agents, dispatch, recorder
│   │           ├── steer/       # macOS GUI automation
│   │           ├── drive/       # Terminal automation
│   │           ├── linux/       # xdotool/tesseract fallback
│   │           └── windows/     # pyautogui/PowerShell fallback
│   └── tests/                   # 868 tests (incl. the golden parity safety net)
├── cli/                         # Typer + Rich CLI (35+ command groups, incl. chat)
├── scripts/                     # Bootstrap, Steer/Drive CLIs, OCR helper
├── supabase/migrations/         # 28 SQL migrations (cloud mode only)
├── setup.sh                     # One-command project setup
├── Makefile                     # setup, up, down, test, lint, parity targets
├── docs/                        # Harness plan, MCP server guide, API surface, QA reports
└── .github/workflows/           # CI + deployment
```

---

## License

MIT


<!-- lastgate-refresh -->
