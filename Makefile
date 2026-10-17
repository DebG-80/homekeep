SHELL := /bin/bash
.SHELLFLAGS := -eu -o pipefail -c
.DEFAULT_GOAL := help

IMAGE ?= homekeep:local
UV_RUN := uv run --locked
WEB_DEPS := web/node_modules/.package-lock.json

.PHONY: help sync lint fmt test run stop seed build audit e2e eval

help: ## List the targets
	@grep -E '^[a-z0-9-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-8s %s\n", $$1, $$2}'

sync: ## Install Python and web dependencies exactly as locked
	uv sync --locked
	cd web && npm ci --no-audit --no-fund

$(WEB_DEPS): web/package-lock.json
	cd web && npm ci --no-audit --no-fund

lint: $(WEB_DEPS) ## ruff check, ruff format check, web typecheck
	$(UV_RUN) ruff check .
	$(UV_RUN) ruff format --check .
	cd web && npm run --silent typecheck

fmt: ## Apply ruff fixes and formatting
	$(UV_RUN) ruff check --fix .
	$(UV_RUN) ruff format .

test: ## Unit and contract tests
	$(UV_RUN) pytest

run: ## Local app on :8000 with DynamoDB Local on :8001 (ENV=local), seeded
	docker compose up --build --detach --wait
	@$(MAKE) --no-print-directory seed
	@echo "HomeKeep: http://localhost:8000/healthz  (stop with: make stop)"

seed: ## Create the local table and load the synthetic fixtures into DynamoDB Local
	$(UV_RUN) python -m scripts.seed --target local

stop: ## Stop the local app and DynamoDB Local
	docker compose down

build: ## Build the linux/arm64 image (default tag homekeep:local)
	docker buildx build --platform linux/arm64 --load -t $(IMAGE) .

audit: $(WEB_DEPS) ## Known-vulnerability scan: pip-audit on the lock, npm audit (high+)
	tmp="$$(mktemp)"; trap 'rm -f "$$tmp"' EXIT; \
	uv export --locked --all-groups --no-emit-project --quiet --output-file "$$tmp"; \
	$(UV_RUN) pip-audit --strict --disable-pip --requirement "$$tmp"
	cd web && npm audit --audit-level=high

e2e: $(WEB_DEPS) ## Playwright text-path tests against `make run` (resets local data first)
	docker compose restart dynamodb-local
	@$(MAKE) --no-print-directory seed
	cd web && npx playwright install chromium
	cd web && npx playwright test

eval: ## Real-Bedrock evaluation set, Deb only: needs `make run` and AWS credentials for Bedrock
	@curl -s -o /dev/null http://localhost:8001 || { echo "make eval needs DynamoDB Local: run 'make run' first." >&2; exit 2; }
	set -a; if [ -f .env.eval ]; then . ./.env.eval; fi; set +a; \
	$(UV_RUN) python -m scripts.eval --repeats 3
