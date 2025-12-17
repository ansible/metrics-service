# Makefile for Metrics Service
#
# Provides common development and deployment tasks for all container configurations
#

.PHONY: help
help: ## Show this help message
	@echo "Metrics Service - Make Targets"
	@echo "==============================="
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-30s\033[0m %s\n", $$1, $$2}'
	@echo ""
	@echo "Configuration Variables:"
	@echo "  CONTAINER_ENGINE   Container runtime (default: podman)"
	@echo "  IMAGE_REGISTRY     Container registry (default: localhost)"
	@echo "  IMAGE_TAG          Image tag (default: latest)"
	@echo ""

# Configuration
CONTAINER_ENGINE ?= podman
IMAGE_REGISTRY ?= localhost
IMAGE_TAG ?= latest
DOCKER_COMPOSE ?= docker compose
PROJECT_ROOT := $(shell pwd)

# Image names
IMAGE_BASE := $(IMAGE_REGISTRY)/metrics-service-base:$(IMAGE_TAG)
IMAGE_WEB := $(IMAGE_REGISTRY)/metrics-service-web:$(IMAGE_TAG)
IMAGE_DISPATCHER := $(IMAGE_REGISTRY)/metrics-service-dispatcher:$(IMAGE_TAG)
IMAGE_SCHEDULER := $(IMAGE_REGISTRY)/metrics-service-scheduler:$(IMAGE_TAG)
IMAGE_ALL_IN_ONE := $(IMAGE_REGISTRY)/metrics-service-all-in-one:$(IMAGE_TAG)
IMAGE_ALL_IN_ONE_SIMPLE := $(IMAGE_REGISTRY)/metrics-service-all-in-one-simple:$(IMAGE_TAG)

##@ Development

.PHONY: dev-install
dev-install: ## Install development dependencies
	uv sync --dev

.PHONY: dev-run
dev-run: ## Run development server (all-in-one process)
	python manage.py metrics_service run

.PHONY: dev-migrate
dev-migrate: ## Run database migrations
	python manage.py migrate

.PHONY: dev-init
dev-init: dev-migrate ## Initialize development environment
	python manage.py metrics_service init-service-id
	python manage.py metrics_service init-system-tasks

.PHONY: dev-superuser
dev-superuser: ## Create Django superuser
	python manage.py createsuperuser

.PHONY: dev-shell
dev-shell: ## Open Django shell
	python manage.py shell

.PHONY: docker-compose
docker-compose: ## Start services with docker-compose
	$(DOCKER_COMPOSE) --file docker-compose.yml up

##@ Testing

.PHONY: test
test: ## Run all tests
	pytest

.PHONY: test-unit
test-unit: ## Run unit tests only
	pytest -m unit

.PHONY: test-integration
test-integration: ## Run integration tests only
	pytest -m integration

.PHONY: test-coverage
test-coverage: ## Run tests with coverage report
	pytest --cov=metrics_service --cov=apps --cov-report=term-missing --cov-report=html

##@ Code Quality

.PHONY: lint
lint: ## Run linting (ruff)
	ruff check .

.PHONY: lint-fix
lint-fix: ## Fix linting issues automatically
	ruff check . --fix

.PHONY: format
format: ## Format code (black + isort)
	black .
	isort .

.PHONY: typecheck
typecheck: ## Run type checking (mypy)
	mypy .

.PHONY: quality
quality: format lint-fix typecheck ## Run all code quality checks

.PHONY: sync-requirements
sync-requirements: ## Sync requirements files from uv.lock
	@echo "Syncing requirements files from uv.lock..."
	./sync-requirements.sh

.PHONY: requirements
requirements: sync-requirements

.PHONY: requirements-check
requirements-check: ## Check if requirements files are in sync
	@echo "Checking if requirements files are in sync..."
	@./sync-requirements.sh
	@if ! git diff --quiet requirements-pinned.txt dev-requirements.txt requirements-build.txt; then \
		echo "Requirements files are out of sync. Run 'make sync-requirements' to update them."; \
		git diff requirements-pinned.txt dev-requirements.txt requirements-build.txt; \
		exit 1; \
	else \
		echo "Requirements files are in sync."; \
	fi

##@ Container Builds - 3 Separate Containers (Recommended for Production)

.PHONY: build-base
build-base: ## Build base container image
	$(CONTAINER_ENGINE) build \
		-f deployment/containers/Containerfile.base \
		-t $(IMAGE_BASE) \
		.

.PHONY: build-web
build-web: build-base ## Build web service container
	$(CONTAINER_ENGINE) build \
		-f deployment/containers/Containerfile.web \
		-t $(IMAGE_WEB) \
		.

.PHONY: build-dispatcher
build-dispatcher: build-base ## Build dispatcher service container
	$(CONTAINER_ENGINE) build \
		-f deployment/containers/Containerfile.dispatcher \
		-t $(IMAGE_DISPATCHER) \
		.

.PHONY: build-scheduler
build-scheduler: build-base ## Build scheduler service container
	$(CONTAINER_ENGINE) build \
		-f deployment/containers/Containerfile.scheduler \
		-t $(IMAGE_SCHEDULER) \
		.

.PHONY: build-all
build-all: build-base build-web build-dispatcher build-scheduler ## Build all 3 separate container images
	@echo ""
	@echo "✓ All images built successfully:"
	@$(CONTAINER_ENGINE) images | grep metrics-service | grep $(IMAGE_TAG)

##@ Container Builds - All-in-One Options

.PHONY: build-all-in-one
build-all-in-one: build-base ## Build all-in-one container (supervisor-based)
	$(CONTAINER_ENGINE) build \
		-f deployment/containers/Containerfile.all-in-one \
		-t $(IMAGE_ALL_IN_ONE) \
		.

.PHONY: build-all-in-one-simple
build-all-in-one-simple: build-base ## Build all-in-one container (simple shell script)
	$(CONTAINER_ENGINE) build \
		-f deployment/containers/Containerfile.all-in-one-simple \
		-t $(IMAGE_ALL_IN_ONE_SIMPLE) \
		.

##@ Local Testing - 3 Separate Containers

.PHONY: run-local
run-local: build-all ## Run all 3 containers locally
	./deployment/scripts/run-containers-local.sh

.PHONY: run-web
run-web: build-web ## Run only web container locally
	$(CONTAINER_ENGINE) run -d \
		--name metrics-service-web \
		-p 8000:8000 \
		-e METRICS_SERVICE_MODE=production \
		-e METRICS_SERVICE_SECRET_KEY=dev-secret-key \
		-e METRICS_SERVICE_ALLOWED_HOSTS=localhost,127.0.0.1 \
		-v metrics-service-sqlite:/opt/app-root/src:Z \
		$(IMAGE_WEB)

.PHONY: run-dispatcher
run-dispatcher: build-dispatcher ## Run only dispatcher container locally
	$(CONTAINER_ENGINE) run -d \
		--name metrics-service-dispatcher \
		-e METRICS_SERVICE_MODE=production \
		-e METRICS_SERVICE_SECRET_KEY=dev-secret-key \
		-v metrics-service-sqlite:/opt/app-root/src:Z \
		$(IMAGE_DISPATCHER)

.PHONY: run-scheduler
run-scheduler: build-scheduler ## Run only scheduler container locally
	$(CONTAINER_ENGINE) run -d \
		--name metrics-service-scheduler \
		-e METRICS_SERVICE_MODE=production \
		-e METRICS_SERVICE_SECRET_KEY=dev-secret-key \
		-v metrics-service-sqlite:/opt/app-root/src:Z \
		$(IMAGE_SCHEDULER)

##@ Local Testing - All-in-One

.PHONY: run-all-in-one
run-all-in-one: build-all-in-one ## Run all-in-one container (supervisor)
	$(CONTAINER_ENGINE) run -d \
		--name metrics-service-all-in-one \
		-p 8000:8000 \
		-e METRICS_SERVICE_MODE=production \
		-e METRICS_SERVICE_SECRET_KEY=dev-secret-key \
		-e METRICS_SERVICE_ALLOWED_HOSTS=localhost,127.0.0.1 \
		-v metrics-service-data:/opt/app-root/src:Z \
		$(IMAGE_ALL_IN_ONE)
	@echo ""
	@echo "✓ All-in-one container started"
	@echo "  Web: http://localhost:8000"
	@echo "  Logs: $(CONTAINER_ENGINE) logs -f metrics-service-all-in-one"
	@echo "  Stop: make stop-all-in-one"

.PHONY: run-all-in-one-simple
run-all-in-one-simple: build-all-in-one-simple ## Run all-in-one container (simple)
	$(CONTAINER_ENGINE) run -d \
		--name metrics-service-all-in-one-simple \
		-p 8000:8000 \
		-e METRICS_SERVICE_MODE=production \
		-e METRICS_SERVICE_SECRET_KEY=dev-secret-key \
		-e METRICS_SERVICE_ALLOWED_HOSTS=localhost,127.0.0.1 \
		-v metrics-service-data:/opt/app-root/src:Z \
		$(IMAGE_ALL_IN_ONE_SIMPLE)
	@echo ""
	@echo "✓ All-in-one (simple) container started"
	@echo "  Web: http://localhost:8000"
	@echo "  Logs: $(CONTAINER_ENGINE) logs -f metrics-service-all-in-one-simple"
	@echo "  Stop: make stop-all-in-one-simple"

##@ Container Management

.PHONY: stop
stop: ## Stop all 3 separate containers
	$(CONTAINER_ENGINE) stop metrics-service-web metrics-service-dispatcher metrics-service-scheduler 2>/dev/null || true
	$(CONTAINER_ENGINE) rm metrics-service-web metrics-service-dispatcher metrics-service-scheduler 2>/dev/null || true

.PHONY: stop-all-in-one
stop-all-in-one: ## Stop all-in-one container
	$(CONTAINER_ENGINE) stop metrics-service-all-in-one 2>/dev/null || true
	$(CONTAINER_ENGINE) rm metrics-service-all-in-one 2>/dev/null || true

.PHONY: stop-all-in-one-simple
stop-all-in-one-simple: ## Stop all-in-one simple container
	$(CONTAINER_ENGINE) stop metrics-service-all-in-one-simple 2>/dev/null || true
	$(CONTAINER_ENGINE) rm metrics-service-all-in-one-simple 2>/dev/null || true

.PHONY: stop-all
stop-all: stop stop-all-in-one stop-all-in-one-simple ## Stop all running containers

.PHONY: logs
logs: ## View logs from web container
	$(CONTAINER_ENGINE) logs -f metrics-service-web

.PHONY: logs-web
logs-web: ## View web container logs
	$(CONTAINER_ENGINE) logs -f metrics-service-web

.PHONY: logs-dispatcher
logs-dispatcher: ## View dispatcher container logs
	$(CONTAINER_ENGINE) logs -f metrics-service-dispatcher

.PHONY: logs-scheduler
logs-scheduler: ## View scheduler container logs
	$(CONTAINER_ENGINE) logs -f metrics-service-scheduler

.PHONY: logs-all-in-one
logs-all-in-one: ## View all-in-one container logs
	$(CONTAINER_ENGINE) logs -f metrics-service-all-in-one

.PHONY: ps
ps: ## Show running containers
	$(CONTAINER_ENGINE) ps --filter "name=metrics-service-"

.PHONY: shell-web
shell-web: ## Open shell in web container
	$(CONTAINER_ENGINE) exec -it metrics-service-web /bin/bash

.PHONY: shell-all-in-one
shell-all-in-one: ## Open shell in all-in-one container
	$(CONTAINER_ENGINE) exec -it metrics-service-all-in-one /bin/bash

##@ Container Registry

.PHONY: push
push: ## Push all 3 container images to registry
	$(CONTAINER_ENGINE) push $(IMAGE_WEB)
	$(CONTAINER_ENGINE) push $(IMAGE_DISPATCHER)
	$(CONTAINER_ENGINE) push $(IMAGE_SCHEDULER)

.PHONY: push-all-in-one
push-all-in-one: ## Push all-in-one image to registry
	$(CONTAINER_ENGINE) push $(IMAGE_ALL_IN_ONE)

.PHONY: pull
pull: ## Pull all 3 container images from registry
	$(CONTAINER_ENGINE) pull $(IMAGE_WEB)
	$(CONTAINER_ENGINE) pull $(IMAGE_DISPATCHER)
	$(CONTAINER_ENGINE) pull $(IMAGE_SCHEDULER)

.PHONY: pull-all-in-one
pull-all-in-one: ## Pull all-in-one image from registry
	$(CONTAINER_ENGINE) pull $(IMAGE_ALL_IN_ONE)

##@ Clean

.PHONY: clean-containers
clean-containers: stop-all ## Remove all metrics-service containers
	@echo "✓ All containers stopped and removed"

.PHONY: clean-images
clean-images: ## Remove all metrics-service images
	$(CONTAINER_ENGINE) rmi $(IMAGE_WEB) 2>/dev/null || true
	$(CONTAINER_ENGINE) rmi $(IMAGE_DISPATCHER) 2>/dev/null || true
	$(CONTAINER_ENGINE) rmi $(IMAGE_SCHEDULER) 2>/dev/null || true
	$(CONTAINER_ENGINE) rmi $(IMAGE_ALL_IN_ONE) 2>/dev/null || true
	$(CONTAINER_ENGINE) rmi $(IMAGE_ALL_IN_ONE_SIMPLE) 2>/dev/null || true
	$(CONTAINER_ENGINE) rmi $(IMAGE_BASE) 2>/dev/null || true
	@echo "✓ All images removed"

.PHONY: clean-volumes
clean-volumes: ## Remove all metrics-service volumes
	$(CONTAINER_ENGINE) volume rm metrics-service-sqlite 2>/dev/null || true
	$(CONTAINER_ENGINE) volume rm metrics-service-data 2>/dev/null || true
	@echo "✓ All volumes removed"

.PHONY: clean-all
clean-all: clean-containers clean-images clean-volumes ## Clean everything (containers, images, volumes)
	@echo "✓ Complete cleanup finished"

.PHONY: clean-python
clean-python: ## Clean Python cache files
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	rm -rf .pytest_cache htmlcov .coverage .mypy_cache .ruff_cache
	@echo "✓ Python cache cleaned"

##@ Production Deployment (systemd + Podman)

.PHONY: deploy-systemd
deploy-systemd: build-all ## Deploy to systemd (3 separate containers)
	@echo "Installing systemd units..."
	sudo ./deployment/scripts/install-systemd-services.sh
	@echo ""
	@echo "Next steps:"
	@echo "  1. Configure: sudo vi /etc/metrics-service/environment"
	@echo "  2. Start: sudo systemctl start metrics-service.target"
	@echo "  3. Status: sudo systemctl status metrics-service.target"

.PHONY: systemd-start
systemd-start: ## Start systemd services (3 containers)
	sudo systemctl start metrics-service.target

.PHONY: systemd-stop
systemd-stop: ## Stop systemd services
	sudo systemctl stop metrics-service.target

.PHONY: systemd-restart
systemd-restart: ## Restart systemd services
	sudo systemctl restart metrics-service.target

.PHONY: systemd-status
systemd-status: ## Check systemd services status
	sudo systemctl status metrics-service.target

.PHONY: systemd-logs
systemd-logs: ## View systemd service logs
	sudo journalctl -u 'container-metrics-service-*' -f

##@ Database Operations (for container deployments)

.PHONY: db-migrate
db-migrate: ## Run database migrations in container
	$(CONTAINER_ENGINE) run --rm \
		-e METRICS_SERVICE_MODE=production \
		-e METRICS_SERVICE_SECRET_KEY=temp \
		-v $(PROJECT_ROOT):/opt/app-root/src:Z \
		$(IMAGE_WEB) \
		python manage.py migrate

.PHONY: db-init
db-init: db-migrate ## Initialize database (migrate + init-service-id + init-tasks)
	$(CONTAINER_ENGINE) run --rm \
		-e METRICS_SERVICE_MODE=production \
		-e METRICS_SERVICE_SECRET_KEY=temp \
		-v $(PROJECT_ROOT):/opt/app-root/src:Z \
		$(IMAGE_WEB) \
		python manage.py metrics_service init-service-id
	$(CONTAINER_ENGINE) run --rm \
		-e METRICS_SERVICE_MODE=production \
		-e METRICS_SERVICE_SECRET_KEY=temp \
		-v $(PROJECT_ROOT):/opt/app-root/src:Z \
		$(IMAGE_WEB) \
		python manage.py metrics_service init-system-tasks

.PHONY: db-shell
db-shell: ## Open database shell in container
	$(CONTAINER_ENGINE) run --rm -it \
		-e METRICS_SERVICE_MODE=production \
		-e METRICS_SERVICE_SECRET_KEY=temp \
		-v $(PROJECT_ROOT):/opt/app-root/src:Z \
		$(IMAGE_WEB) \
		python manage.py dbshell

##@ Utilities

.PHONY: version
version: ## Show version information
	@echo "Metrics Service"
	@echo "==============="
	@echo "Container Engine: $(CONTAINER_ENGINE)"
	@echo "Image Registry: $(IMAGE_REGISTRY)"
	@echo "Image Tag: $(IMAGE_TAG)"
	@echo ""
	@echo "Images:"
	@$(CONTAINER_ENGINE) images | grep metrics-service || echo "  No images built"

.PHONY: health
health: ## Check health of running containers
	@echo "Checking container health..."
	@for container in metrics-service-web metrics-service-dispatcher metrics-service-scheduler metrics-service-all-in-one; do \
		if $(CONTAINER_ENGINE) ps -q -f name=$$container 2>/dev/null | grep -q .; then \
			status=$$($(CONTAINER_ENGINE) inspect --format='{{.State.Health.Status}}' $$container 2>/dev/null || echo "no-healthcheck"); \
			echo "  $$container: $$status"; \
		fi \
	done

##@ Quick Start Recipes

.PHONY: quick-dev
quick-dev: dev-install dev-init dev-run ## Quick start for development (install + init + run)

.PHONY: quick-test-3containers
quick-test-3containers: build-all run-local ## Quick test with 3 separate containers
	@echo ""
	@echo "✓ All 3 containers running"
	@echo "  Web: http://localhost:8000"
	@echo "  Stop: make stop"

.PHONY: quick-test-all-in-one
quick-test-all-in-one: build-all-in-one run-all-in-one ## Quick test with all-in-one container
	@echo ""
	@echo "✓ All-in-one container running"
	@echo "  Web: http://localhost:8000"
	@echo "  Stop: make stop-all-in-one"

# Default target
.DEFAULT_GOAL := help
