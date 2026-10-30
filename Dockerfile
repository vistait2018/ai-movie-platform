FROM python:3.12.14-slim AS runtime
COPY --from=ghcr.io/astral-sh/uv:0.13.6 /uv /usr/local/bin/uv
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_PROJECT_ENVIRONMENT=/opt/venv PATH="/opt/venv/bin:$PATH"
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project && groupadd --gid 10001 movie && useradd --uid 10001 --gid movie --no-create-home movie
COPY --chown=movie:movie app ./app
USER movie
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/live', timeout=2)"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
