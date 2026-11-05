# Requirements management
sync-requirements:
	@echo "Syncing requirements files from uv.lock..."
	./sync-requirements.sh

requirements: sync-requirements

requirements-check:
	@echo "Checking if requirements files are in sync..."
	@./sync-requirements.sh
	@if ! git diff --quiet requirements-pinned.txt dev-requirements.txt requirements-build.txt; then \
		echo "Requirements files are out of sync. Run 'make sync-requirements' to update them."; \
		git diff requirements-pinned.txt dev-requirements.txt requirements-build.txt; \
		exit 1; \
	else \
		echo "Requirements files are in sync."; \
	fi


# Generate OpenAPI schema files (requires DB to be running for migrations)
generate-openapi-schema:
	@echo "Generating OpenAPI schema..."
	bash tools/generate-openapi.sh

# Validate committed OpenAPI schema files against OpenAPI 3.0 spec (no server required)
validate-openapi-schema: generate-openapi-schema
	@echo "Validating generated OpenAPI schema files..."
	@uv run openapi-spec-validator tools/openapi-schema/metrics-service.yaml
	@uv run openapi-spec-validator tools/openapi-schema/metrics-service.json
	@echo "✓ OpenAPI schema files are valid!"

help:
	@echo help test test-trace-e2e coverage lint fix sync-requirements requirements-check generate-openapi-schema validate-openapi-schema compose compose-service compose-pytest-svc clean psql

test:
	uv run pytest -s -v

# Cross-process trace-continuity test (AAP-79590): starts a real scheduler and
# a real dispatcherd worker as subprocesses. OPT-IN ONLY and NOT run in CI --
# nothing in .github/workflows/pytest.yml sets TRACE_E2E, so `make test`
# collects this file and skips it. Run it explicitly against a PostgreSQL
# instance (~30s). See docs/trace-propagation.md.
test-trace-e2e:
	TRACE_E2E=1 uv run pytest tests/integration/test_trace_continuity_process.py -s -v

coverage:
	uv run pytest -s -v --cov --cov-branch --cov-report=html --cov-report=xml

lint:
	uv run ruff check
	uv run ruff format --check

fix:
	uv run ruff check --fix
	uv run ruff format


METRICS_UTILITY_COMPOSE = ../metrics-utility/tools/docker/docker-compose.yaml
COMPOSE_CMD ?= $(shell command -v podman-compose 2>/dev/null || echo "docker compose")

compose:
	$(COMPOSE_CMD) -f $(METRICS_UTILITY_COMPOSE) up

compose-service:
	$(COMPOSE_CMD) -f $(METRICS_UTILITY_COMPOSE) --profile service up

compose-pytest-svc:
	$(COMPOSE_CMD) -f $(METRICS_UTILITY_COMPOSE) --profile pytest-svc up

clean:
	$(COMPOSE_CMD) -f $(METRICS_UTILITY_COMPOSE) down -v --rmi local

psql:
	$(COMPOSE_CMD) -f $(METRICS_UTILITY_COMPOSE) exec postgres psql -U awx

.PHONY: help test test-trace-e2e coverage lint fix sync-requirements requirements requirements-check generate-openapi-schema validate-openapi-schema compose compose-service compose-pytest-svc clean psql
