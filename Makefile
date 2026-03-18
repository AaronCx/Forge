.PHONY: setup up down restart test lint

setup:
	./setup.sh

up:
	agentforge up

down:
	agentforge down

restart:
	agentforge restart

test:
	cd backend && .venv/bin/pytest tests/ -v && cd ../frontend && bun test

lint:
	cd backend && .venv/bin/ruff check . && cd ../frontend && bun lint
