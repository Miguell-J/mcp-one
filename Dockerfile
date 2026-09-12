FROM python:3.12.12-slim@sha256:f3fa41d74a768c2fce8016b98c191ae8c1bacd8f1152870a3f9f87d350920b7c AS builder
WORKDIR /app
ENV UV_LINK_MODE=copy
RUN pip install --no-cache-dir uv==0.12.13
COPY pyproject.toml uv.lock README.md ./
COPY src/ src/
RUN uv sync --locked --no-dev --no-editable

FROM builder AS development
RUN uv sync --locked --no-editable
COPY tests/ tests/
RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin mcpone && chown -R 10001:10001 /app
ENV PATH="/app/.venv/bin:$PATH"
USER 10001:10001
CMD ["python", "-m", "pytest", "-q"]

FROM python:3.12.12-slim@sha256:f3fa41d74a768c2fce8016b98c191ae8c1bacd8f1152870a3f9f87d350920b7c AS runtime
WORKDIR /app
ENV PATH="/app/.venv/bin:$PATH" PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY --from=builder /app/.venv /app/.venv
COPY config.yaml /app/config.yaml
RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin mcpone
USER 10001:10001
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=5s --start-period=20s --retries=3 CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)"]
CMD ["mcp-one", "--config", "/app/config.yaml", "--host", "0.0.0.0"]
