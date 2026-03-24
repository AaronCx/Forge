# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.2.0] - 2026-03-23

### Changed

- **Renamed from AgentForge to Forge** — project name, CLI command (`agentforge` → `forge`), package name (`agentforge-cli` → `forge-cli`), config directory (`~/.agentforge` → `~/.forge`), environment variables (`AGENTFORGE_*` → `FORGE_*`), and all documentation updated throughout.

## [1.9.1] - 2026-03-15

### Added

- **Native macOS Steer CLI** — 13-command Python CLI for GUI automation using CoreGraphics, cliclick, osascript, and Apple Vision OCR. Replaces external brew tap dependency.
- **Native macOS Drive CLI** — 6-command Python CLI wrapping tmux for terminal session management with sentinel-based completion detection.
- **CoreGraphics Screenshot Capture** — Screenshots via CoreGraphics API instead of screencapture. Works over SSH without console session.
- **Screen Recording over SSH** — Record screen via CoreGraphics frame capture piped to ffmpeg. Configurable FPS, quality, and duration. Works fully headless.
- **Swift OCR Helper** — Compiled binary using Apple Vision framework for accurate text extraction with bounding box coordinates.
- **Bootstrap Scripts** — `scripts/bootstrap-macos.sh` for one-command setup, `scripts/bootstrap-verify.sh` for 20-point smoke test across all Steer and Drive commands.
- **Capability Detection** — Extended detector with macOS permission checks (accessibility, screen recording) and system command detection (screencapture, cliclick, osascript, ffmpeg).
- **LastGate Integration** — `.lastgate.yml` configuration for pre-commit security checks.

### Fixed

- OAuth PKCE code exchange in callback and hardened logout flow
- Demo mode checks on Marketplace, Team, Compare, Blueprint Edit, and Trigger pages
- Template seeding FK constraint with auth.users
- Provider system updated to per-user API key pattern
- Type annotation errors in agent executor and knowledge service
- Lint errors in provider config endpoints
- Frontend mobile-responsive dashboard navigation

### Security

- Patched 12 vulnerabilities from comprehensive security audit (105 security tests added)
- Removed accidentally committed Vercel OIDC token and Supabase keys
- Hardened `.gitignore` with `.env.*` pattern

## [1.9.0] - 2026-03-12

### Added

- **Agent-on-Agent Orchestration**: Spawn and control external coding agents (Claude Code, Codex, Gemini CLI, Aider) as workers in tmux sessions
  - Agent backend configuration system with 4 pre-configured backends + custom support
  - Agent runner service with full lifecycle: spawn, prompt, monitor, wait, capture, stop
  - 6 new deterministic node types: agent_spawn, agent_prompt, agent_monitor, agent_wait, agent_stop, agent_result
  - Agent Control category in blueprint editor palette with orange styling
  - Config panels for all agent control nodes (backend selector, session, prompt, timeout, output format)
  - CLI `backends list` and `backends test` subcommands under `cu`
- **Multi-Machine Dispatch**: Route blueprint nodes to different execution targets
  - Execution targets registry (local + remote machines)
  - Dispatch routing: explicit target → blueprint default → capability-based → local fallback
  - REST API endpoints: POST/GET/DELETE /api/targets, POST /api/targets/:id/health, GET /api/targets/capabilities
  - `execution_targets` database table with RLS policies
  - CLI `targets` command group (list, add, health, remove)
  - Target selector dropdown in API client
- **Screen Recording**: Capture video of computer use agent sessions
  - Recorder service with ffmpeg (avfoundation on macOS, x11grab on Linux)
  - recording_control blueprint node type (start/stop, quality settings)
  - Recording storage management with cleanup
  - CLI `recordings` command group (list, play, cleanup)
- **Linux Computer Use**: Full GUI automation on Linux
  - Linux Steer implementation via xdotool, scrot, tesseract, wmctrl, xclip (12 commands)
  - Xvfb virtual display manager for headless Linux environments
  - Platform detection for Linux-specific tools
- **Windows Computer Use**: Full GUI and terminal automation on Windows
  - Windows Steer implementation via pyautogui, pytesseract, pygetwindow, pyperclip (12 commands)
  - Windows Drive implementation via PowerShell subprocess management
  - WSL detection and tmux-via-WSL option for Drive commands
- **Cross-Platform Unification**: Abstract platform layer
  - `platform.py` with get_platform(), get_capabilities(), get_steer_executor(), get_drive_executor()
  - Platform-specific install instructions for macOS, Linux, and Windows
  - Capability detector extended with platform detection, Linux tools, Windows tools, and agent backends
- 3 new blueprint templates: Agent Inception, Parallel Multi-Agent Code Review, Universal Browser Automation
- Platform and agent backend display in settings page
- Demo data for targets, agent-on-agent sessions
- 44 total blueprint node types (was 37)
- 40+ new tests for all v1.9 features

## [1.8.0] - 2026-03-12

### Added

- **Computer Use Extension** — agents can now operate macOS machines through GUI automation and terminal orchestration
- **Steer Integration** — 12 new deterministic blueprint nodes for GUI control: screenshot, OCR, click, type, hotkey, scroll, drag, focus, find, wait, clipboard, and app listing
- **Drive Integration** — 6 new deterministic blueprint nodes for terminal control: session management, command execution with sentinel pattern, key sending, log capture, polling, and parallel fanout
- **Computer Use Agent Nodes** — 4 new LLM-powered nodes: CU Planner (action planning), CU Analyzer (screen analysis), CU Verifier (objective verification), CU Error Handler (self-healing)
- **Remote Execution** — dispatch computer use jobs to a Mac Mini via Listen job server over HTTP/Tailscale
- **Capability Detection** — auto-detect Steer, Drive, tmux availability with install instructions
- **Safety & Security** — app blocklist, command blocklist, rate limiting (30 actions/min), mandatory approval gates, full audit logging
- **Computer Use API** — GET /api/computer-use/status, /config, POST /refresh, /remote/test, GET /audit-log
- **Blueprint Editor** — new "GUI (Steer)" and "Terminal (Drive)" categories with green/amber color coding, config panels for all 22 node types
- **5 Blueprint Templates** — Browser Research Pipeline, Terminal Task Runner, Cross-App Workflow, Self-Healing App Automation, Multi-Terminal Parallel Tasks
- **Eval Grading Methods** — screenshot_match (perceptual hash comparison) and ocr_contains (OCR text verification)
- **CLI Commands** — `forge cu status/see/ocr/click/type/hotkey/run/logs/sessions/apps/remote`
- **Computer Use Settings** — settings page shows component status with green/red indicators and install instructions
- **Dry-run Mode** — CU_DRY_RUN=true for testing without executing real GUI/terminal actions
- **Database Migration** — computer_use_audit_log table with RLS policies
- **33 new tests** covering capability detection, config, safety, node registration, executors, API endpoints, blueprint templates, CLI commands, and eval grading

## [1.0.0] - 2026-03-12

### Added

- Enhanced landing page with feature showcase, template gallery, and tech stack section
- Demo mode (?demo=true) for exploring the dashboard without authentication
- Comprehensive README with full API docs, CLI usage, architecture diagram, setup guide
- Demo data module with sample agents, metrics, heartbeats, timeline, and cost data

### Changed

- Landing page now highlights orchestration, monitoring, messaging, and cost analytics
- Dashboard layout skips auth redirect in demo mode
- Architecture diagram updated with orchestrator and messaging service

## [0.7.0] - 2026-03-12

### Added

- Heartbeat service tests (10): start, update, complete, fail, stalled detection, metrics
- Runs route tests (5): list, get, not found, wrong user, stats
- Token tracker + cost calculation tests (10): pricing models, summaries, projections
- Dashboard timeline test with severity mapping and agent name fallback
- Frontend dashboard tests (6): MetricsBar, AgentStatusGrid, EventTimeline with empty states
- Test coverage badges in README (84 backend, 21 frontend, 66% coverage)

### Changed

- Backend test count: 58 → 84 passing
- Frontend test count: 15 → 21 passing
- Backend coverage: 62% → 66%

## [0.6.0] - 2026-03-12

### Added

- Agent messages table for inter-agent communication with typed messages
- Messaging service with send, broadcast, get_messages, and get_conversation methods
- Message API routes: POST /messages, GET /messages/{group_id}, GET /messages/{group_id}/conversation
- Orchestrator now sends info/handoff/response messages during task execution
- MessageFeed component with type filtering and auto-polling
- Orchestrate page shows agent message feed after completion
- CLI `messages list` and `messages conversation` commands
- 6 message endpoint tests

### Changed

- Orchestrator integrates messaging for start/handoff/completion events

## [0.5.0] - 2026-03-12

### Added

- Agent hierarchy columns (parent_agent_id, agent_role, depth) on agents table
- Task groups and task group members tables with RLS policies
- Orchestrator service: LLM-based task decomposition with dependency graph execution
- Orchestration API: SSE-streamed POST /orchestrate, group listing/detail/result endpoints
- Orchestrate page with objective input, tool selection, live task plan visualization
- Role-colored badges (coordinator/supervisor/worker/scout/reviewer) with state transitions
- CLI `orchestrate` command with Rich-formatted task plan and streaming progress
- 8 orchestration tests (endpoints + decompose logic)

### Changed

- Dashboard sidebar now includes Orchestrate nav item
- CLI client supports POST-based SSE streaming

## [0.4.0] - 2026-03-12

### Added

- Token usage table for per-step cost tracking
- Token tracking service with model pricing (GPT-4o-mini/4o/4-turbo/3.5-turbo)
- Cost API endpoints: summary by period, breakdown by agent/model, per-run usage, monthly projection
- Analytics page with cost summaries, token breakdown bars, agent/model cost tables, projection
- CLI `costs` command with summary, breakdown, and projection display
- 8 new cost endpoint and calculation tests

## [0.3.0] - 2026-03-12

### Added

- Agent heartbeats table for real-time execution monitoring
- Heartbeat service with stalled agent detection (30s threshold)
- Dashboard API: active agents, metrics, event timeline, SSE stream
- Live Monitor page with MetricsBar, AgentStatusGrid, EventTimeline
- SSE-powered real-time updates with auto-reconnect
- CLI client (`forge`) with typer + rich + httpx
- CLI commands: status, dashboard (live TUI), agents list/run/create
- CLI config from ~/.forge/config.toml or environment variables
- Dashboard and CLI tests (14 new tests)

### Changed

- Agent executor now reports heartbeat progress at each workflow step
- Run endpoint creates heartbeats for live monitoring
- Dashboard sidebar now includes Monitor nav item

## [0.2.0] - 2026-03-12

### Added

- CODE_OF_CONDUCT.md (Contributor Covenant v2.1)
- ruff.toml with project-wide Python lint configuration
- mypy.ini for backend type checking
- biome.json for frontend linting and formatting
- Frontend test infrastructure (vitest + testing-library + jsdom)
- 15 frontend component render tests (StatsCards, StepLog, ToolSelector, WorkflowEditor, AgentCard)
- Backend test conftest.py with shared fixtures and Supabase mocking
- 23 backend API tests covering all routes, auth guards, and edge cases

### Changed

- CI workflow updated to use Bun instead of npm for frontend
- CI now runs mypy type checking for backend
- CI now runs frontend tests as a separate job

## [0.1.0] - 2026-03-10

### Added

- Next.js 14 frontend with TypeScript, Tailwind CSS, and shadcn/ui
- FastAPI backend with LangChain and OpenAI integration
- Agent builder UI with tool selector and workflow step editor
- Agent runner with SSE streaming for real-time step-by-step output
- Pre-built agent templates: Document Analyzer, Research Agent, Data Extractor, Code Reviewer
- Dashboard with stats cards, run history, and token usage chart
- Tool library: web_search, document_reader, code_executor, data_extractor, summarizer
- Supabase Auth integration (email + GitHub OAuth)
- API key generation for programmatic access
- Rate limiting (10 runs/hour free tier)
- Database migrations with Row Level Security policies
- Docker support with docker-compose
- GitHub Actions CI/CD (lint + test + deploy)
- Vercel (frontend) and Render (backend) deployment configs
