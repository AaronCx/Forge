#!/usr/bin/env bash
set -euo pipefail

# Forge — one-time project setup
# Defaults to SQLite (zero external dependencies). No accounts needed.
# Idempotent: safe to run multiple times.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

ok()   { echo -e "${GREEN}✓${NC} $1"; }
warn() { echo -e "${YELLOW}⚠${NC}  $1"; }
fail() { echo -e "${RED}✗${NC} $1"; }

# ── 1. Check system tools ──────────────────────────────────────────

missing=()
command -v python3 >/dev/null 2>&1 || missing+=("python3")
command -v git     >/dev/null 2>&1 || missing+=("git")

# Accept bun OR node/npm for frontend
has_bun=false
has_node=false
command -v bun  >/dev/null 2>&1 && has_bun=true
command -v node >/dev/null 2>&1 && has_node=true

if ! $has_bun && ! $has_node; then
  missing+=("bun or node")
fi

if [ ${#missing[@]} -gt 0 ]; then
  fail "Missing required tools: ${missing[*]}"
  echo "Install them and re-run this script."
  exit 1
fi

echo ""
echo "═══════════════════════════════════════════"
echo "  Forge Setup"
echo "═══════════════════════════════════════════"
echo ""

# ── 2. Backend setup ───────────────────────────────────────────────

echo "── Backend ──"

if [ ! -d "backend/.venv" ]; then
  python3 -m venv backend/.venv
  ok "Created Python virtual environment"
else
  ok "Virtual environment exists"
fi

backend/.venv/bin/pip install --quiet -r backend/requirements.txt
ok "Backend dependencies installed"

if [ ! -f "backend/.env" ]; then
  cp -n backend/.env.example backend/.env
  ok "Created backend/.env (SQLite default — no Supabase keys needed)"
else
  ok "backend/.env exists"
fi

# ── 3. Frontend setup ──────────────────────────────────────────────

echo ""
echo "── Frontend ──"

if $has_bun; then
  (cd frontend && bun install --silent)
  ok "Frontend dependencies installed (bun)"
else
  (cd frontend && npm install --silent)
  ok "Frontend dependencies installed (npm)"
fi

if [ ! -f "frontend/.env.local" ]; then
  cp -n frontend/.env.example frontend/.env.local
  ok "Created frontend/.env.local (API URL only — no Supabase keys needed)"
else
  ok "frontend/.env.local exists"
fi

# ── 4. CLI setup ───────────────────────────────────────────────────

echo ""
echo "── CLI ──"

backend/.venv/bin/pip install --quiet -e cli/
ok "CLI installed (forge command available via venv)"

# Initialize config + SQLite database
if [ ! -f "$HOME/.forge/config.toml" ]; then
  backend/.venv/bin/forge init
  ok "CLI config initialized"
else
  ok "CLI config exists"
fi

# ── 5. Database ───────────────────────────────────────────────────

echo ""
echo "── Database ──"

# SQLite database is created automatically on first backend startup.
# No migration step needed — schema is built-in.
ok "SQLite database will be created on first run (~/.forge/forge.db)"

# For Supabase users: generate combined migration file
if [ -d "supabase/migrations" ]; then
  combined="supabase/migrations/combined_all.sql"
  if [ ! -f "$combined" ]; then
    echo "-- Forge: Combined Supabase migrations (for cloud mode)" > "$combined"
    echo "" >> "$combined"
    for f in supabase/migrations/001_*.sql supabase/migrations/002_*.sql \
             supabase/migrations/003_*.sql supabase/migrations/004_*.sql \
             supabase/migrations/005_*.sql supabase/migrations/006_*.sql \
             supabase/migrations/007_*.sql supabase/migrations/008_*.sql \
             supabase/migrations/20260312_*.sql; do
      if [ -f "$f" ]; then
        echo "-- ════ $(basename "$f") ════" >> "$combined"
        cat "$f" >> "$combined"
        echo "" >> "$combined"
      fi
    done
  fi
fi

# ── 6. Computer Use (macOS only) ───────────────────────────────────

echo ""
echo "── Computer Use ──"

if [[ "$(uname)" == "Darwin" ]]; then
  if [ -x "scripts/bootstrap-macos.sh" ]; then
    echo "Running macOS bootstrap..."
    ./scripts/bootstrap-macos.sh || warn "Computer use bootstrap had issues (non-fatal)"
    ok "macOS computer use setup complete"
  else
    warn "scripts/bootstrap-macos.sh not found or not executable"
  fi
else
  ok "Skipped (not macOS) — see README for Linux/Windows setup"
fi

# ── 7. Summary ─────────────────────────────────────────────────────

echo ""
echo "═══════════════════════════════════════════"
echo "  Setup Complete"
echo "═══════════════════════════════════════════"
echo ""
ok "Backend dependencies installed"
ok "Frontend dependencies installed"
ok "CLI installed"
ok "SQLite database (default — zero config)"
echo ""

if [ -f "backend/.env" ] && ! grep -q "^OPENAI_API_KEY=\S" "backend/.env" 2>/dev/null; then
  warn " Add an LLM API key to backend/.env (OpenAI, Anthropic, or use Ollama for local models)"
fi

echo ""
echo "Run 'forge up' to start everything."
echo "(Or: source backend/.venv/bin/activate && forge up)"
echo ""
