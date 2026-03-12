# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
- CLI client (`agentforge`) with typer + rich + httpx
- CLI commands: status, dashboard (live TUI), agents list/run/create
- CLI config from ~/.agentforge/config.toml or environment variables
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
