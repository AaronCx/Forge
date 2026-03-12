# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
