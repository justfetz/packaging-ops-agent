# Common entry points. CLAUDE.md documents when to use each one.
.DEFAULT_GOAL := help
.PHONY: help install lint format test check run

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-10s %s\n", $$1, $$2}'

install: ## Install the locked dependencies, including the dev group
	uv sync --locked

lint: ## Lint and check formatting without changing files
	uv run ruff check .
	uv run ruff format --check .

format: ## Fix lint issues and reformat
	uv run ruff check --fix .
	uv run ruff format .

test: ## Run the unit tests
	uv run pytest

check: lint test ## Everything CI runs

run: ## Serve the app locally on http://127.0.0.1:8080
	uv run uvicorn app.main:app --reload --port 8080
