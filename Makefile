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
	mkdir -p tools/openapi-schema
	uv run python manage.py spectacular --file tools/openapi-schema/metrics-service.yaml
	uv run python manage.py spectacular --format openapi-json --file tools/openapi-schema/metrics-service.json

# Validate committed OpenAPI schema files against OpenAPI 3.0 spec (no server required)
validate-openapi-schema: generate-openapi-schema
	@echo "Validating generated OpenAPI schema files..."
	@uv run openapi-spec-validator tools/openapi-schema/metrics-service.yaml
	@uv run openapi-spec-validator tools/openapi-schema/metrics-service.json
	@echo "✓ OpenAPI schema files are valid!"

help:
	@echo help test coverage lint fix sync-requirements requirements-check generate-openapi-schema validate-openapi-schema compose compose-service compose-pytest-svc clean psql

test:
	uv run pytest -s -v

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

.PHONY: help test coverage lint fix sync-requirements requirements requirements-check generate-openapi-schema validate-openapi-schema compose compose-service compose-pytest-svc clean psql
