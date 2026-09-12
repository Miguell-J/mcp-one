UV ?= uv
.PHONY: sync check lint test test-contract test-integration test-e2e schema run build
sync:
	$(UV) sync --locked
lint:
	.venv/bin/ruff check .
	.venv/bin/ruff format --check .
	.venv/bin/mypy
check: lint test
test:
	.venv/bin/python -m pytest --cov=mcp_one --cov-report=term-missing -q
test-contract:
	.venv/bin/python -m pytest -m contract -q
test-integration:
	.venv/bin/python -m pytest -m integration -q
test-e2e:
	.venv/bin/python -m pytest -m e2e -q
schema:
	.venv/bin/python -m mcp_one.server --schema > docs/config.schema.json
run:
	.venv/bin/mcp-one
build:
	$(UV) build --no-sources
