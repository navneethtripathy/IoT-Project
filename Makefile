# CivicTwin-R — Makefile
# Convenience targets for common development tasks.

.PHONY: help install test run experiments clean lint

PYTHON ?= python3

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-18s %s\n", $$1, $$2}'

install: ## Install Python dependencies
	$(PYTHON) -m pip install -e ".[dev]"

test: ## Run all tests
	$(PYTHON) -m pytest tests/ -v --tb=short

run: ## Start the FastAPI backend (Mode B — no Docker needed)
	$(PYTHON) -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --reload

experiments: ## Run all experiments and generate plots
	$(PYTHON) -m experiments.run_experiments

demo-data: ## Generate demo dataset
	$(PYTHON) scripts/generate_demo_data.py

health: ## Check service health
	$(PYTHON) scripts/health_check.py

lint: ## Run linting
	$(PYTHON) -m ruff check backend/ digital_twin/ experiments/ tests/

clean: ## Remove generated files and caches
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	rm -rf .pytest_cache
	rm -f data/civictwin.db
	@echo "Cleaned."

docker-up: ## Start all Docker services
	docker-compose up -d

docker-down: ## Stop all Docker services
	docker-compose down

docker-logs: ## View Docker service logs
	docker-compose logs -f
