.PHONY: setup up down restart test lint parity api-surface

setup:
	./setup.sh

up:
	forge up

down:
	forge down

restart:
	forge restart

test:
	cd backend && .venv/bin/pytest tests/ -v && cd ../frontend && bun test

lint:
	cd backend && .venv/bin/ruff check . && cd ../frontend && bun lint

# Parity safety net: freeze current node + agent behavior (docs/harness-plan.md Phase 0).
# `python -m pytest` (not .venv/bin/pytest) so CI and containers can run it too.
parity:
	cd backend && FORGE_TESTING=1 python -m pytest tests/parity/ -q

# Regenerate the recorded API surface after intentional route changes.
api-surface:
	cd backend && .venv/bin/python scripts/dump_api.py --write
