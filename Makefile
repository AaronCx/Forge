.PHONY: setup up down restart test lint

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
