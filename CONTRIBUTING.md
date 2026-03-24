# Contributing to Forge

Thank you for your interest in contributing to Forge! This guide will help you get started.

## Prerequisites

- [Bun](https://bun.sh) (frontend package manager and runtime)
- [Python 3.12+](https://python.org)
- A [Supabase](https://supabase.com) project (free tier works)
- An [OpenAI API key](https://platform.openai.com)

## Development Setup

### 1. Fork and clone

```bash
git clone https://github.com/<your-username>/Forge.git
cd Forge
```

### 2. Database

Run the SQL migrations in order in your Supabase SQL Editor:

```
supabase/migrations/001_users.sql
supabase/migrations/002_agents.sql
supabase/migrations/003_runs.sql
supabase/migrations/004_api_keys.sql
supabase/migrations/005_agent_heartbeats.sql
supabase/migrations/006_token_usage.sql
supabase/migrations/007_hierarchy.sql
supabase/migrations/008_agent_messages.sql
```

### 3. Backend

```bash
cd backend
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install pytest pytest-asyncio pytest-cov ruff mypy

cp .env.example .env
# Fill in your API keys

uvicorn app.main:app --reload
```

### 4. Frontend

```bash
cd frontend
bun install

cp .env.example .env.local
# Fill in your Supabase keys

bun run dev
```

### 5. CLI (optional)

```bash
cd cli
pip install -e .
forge init
```

### 6. Run tests

```bash
# Backend
cd backend
pytest tests/ -v --cov=app

# Frontend
cd frontend
bun run test
```

## Pull Request Process

1. Create a feature branch from `main`:
   ```bash
   git checkout -b feat/my-feature
   ```

2. Make your changes with clear, atomic commits.

3. Ensure all tests pass and add new tests for new functionality.

4. Update documentation if your change affects the public API or user-facing features.

5. Open a PR against `main` with a clear description of what and why.

## Commit Message Convention

We use [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <description>

[optional body]
```

**Types:**

| Type | Description |
|------|-------------|
| `feat` | New feature |
| `fix` | Bug fix |
| `docs` | Documentation only |
| `test` | Adding or updating tests |
| `refactor` | Code change that neither fixes a bug nor adds a feature |
| `style` | Formatting, missing semicolons, etc. |
| `chore` | Build process, CI, tooling changes |
| `ci` | CI/CD pipeline changes |

**Scopes:** `frontend`, `backend`, `api`, `cli`, `db`, `e2e`

**Examples:**

```
feat(backend): add token tracking service
fix(frontend): correct SSE reconnection logic
test(api): add agent CRUD endpoint tests
docs: update README with CLI instructions
```

## Code Style

### Python (backend)

- Linted with [Ruff](https://docs.astral.sh/ruff/)
- Type checked with [mypy](https://mypy-lang.org/)
- Formatted with Ruff's formatter
- Run `ruff check app/` and `mypy app/` before committing

### TypeScript (frontend)

- Linted with ESLint (Next.js config)
- Type checked with `tsc --noEmit`
- Formatted with Prettier (via ESLint)

### General

- Write tests alongside features, not as an afterthought
- Keep functions focused and small
- Prefer explicit over implicit
- Document non-obvious behavior with comments

## Reporting Issues

- Use GitHub Issues for bug reports and feature requests
- Include steps to reproduce for bugs
- Include expected vs actual behavior
- Include environment details (OS, Python/Node versions)

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
