.PHONY: help install lint format test test-cov serve worker demo eval db-init clean

PYTHON := python3.12
VENV := .venv

help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

install:  ## Create venv and install dev extras (PyPI index, no auth proxy)
	$(PYTHON) -m venv $(VENV)
	$(VENV)/bin/pip install --upgrade pip -i https://pypi.org/simple
	$(VENV)/bin/pip install -e ".[dev]" -i https://pypi.org/simple

lint:  ## Run ruff + mypy
	$(VENV)/bin/ruff check src tests
	$(VENV)/bin/mypy src

format:  ## Format with black + ruff --fix
	$(VENV)/bin/black src tests
	$(VENV)/bin/ruff check --fix src tests

test:  ## Run pytest
	$(VENV)/bin/pytest -v

test-cov:  ## Run pytest with coverage
	$(VENV)/bin/pytest --cov=src/vigil --cov-report=term

serve:  ## Run FastAPI console on :8000
	$(VENV)/bin/python -m vigil.cli.main serve

worker:  ## Run RQ worker (production async path)
	$(VENV)/bin/python -m vigil.cli.main worker

demo:  ## Seed a synthetic store + messages, resolve every case end-to-end
	$(VENV)/bin/python -m vigil.cli.main demo

eval:  ## Backtest the agent over labeled synthetic cases and print metrics
	$(VENV)/bin/python -m vigil.cli.main eval

db-init:  ## Create tables (dev) for the configured Postgres database
	$(VENV)/bin/python -m vigil.cli.main db-init

clean:  ## Remove build artifacts & caches
	rm -rf build dist *.egg-info
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type d -name ".pytest_cache" -exec rm -rf {} +
	find . -type d -name ".ruff_cache" -exec rm -rf {} +
	find . -type d -name ".mypy_cache" -exec rm -rf {} +
	rm -rf htmlcov .coverage
