.PHONY: help clean clean-pyc clean-build docs install dev-install test test-watch lint format type-check pre-commit run dev build

help:
	@echo "Available commands:"
	@echo "  install      Install production dependencies"
	@echo "  dev-install  Install development dependencies"
	@echo "  test         Run tests"
	@echo "  test-watch   Run tests in watch mode"
	@echo "  lint         Run linting (flake8)"
	@echo "  format       Format code (black + isort)"
	@echo "  type-check   Run type checking (mypy)"
	@echo "  pre-commit   Run pre-commit hooks"
	@echo "  run          Run the MCP Hub server"
	@echo "  dev          Run in development mode"
	@echo "  build        Build the package"
	@echo "  clean        Clean up build artifacts"

# Installation
install:
	pip install -e .

dev-install:
	pip install -e ".[dev]"
	pre-commit install

# Testing
test:
	pytest tests/ -v --cov=app --cov-report=term-missing

test-watch:
	pytest-watch tests/ --cov=app

# Code Quality
lint:
	flake8 src/app tests/

format:
	black src/app tests/
	isort src/app tests/

type-check:
	mypy src/app

pre-commit:
	pre-commit run --all-files

# Running
run:
	python -m app.main

dev:
	uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Building
build:
	python -m build

# Cleaning
clean: clean-build clean-pyc

clean-build:
	rm -fr build/
	rm -fr dist/
	rm -fr *.egg-info

clean-pyc:
	find . -name '*.pyc' -exec rm -f {} +
	find . -name '*.pyo' -exec rm -f {} +
	find . -name '*~' -exec rm -f {} +
	find . -name '__pycache__' -exec rm -fr {} +
