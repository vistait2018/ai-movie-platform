# AI Movie Streaming & Creator Platform

Shared FastAPI foundation for web, Flutter Android and Flutter iOS. Roadmap 4.0 is authoritative; this is not yet a streaming or AI product. See [phase status](docs/roadmap/PHASE_STATUS.md) and [latest development report](docs/DEVELOPMENT_REPORT_006.md).

## Windows setup

Use Python 3.12 (64 bit) and uv 0.13.6. Existing `.venv` is preserved because its Python 3.14 base installation is inaccessible in the Codex session. `.venv-dev` is the verified replacement environment. Do not copy packages from the old environment.

```powershell
# Locate your installed interpreter:
Get-Command python,py -All -ErrorAction SilentlyContinue
where.exe python
py -0p
# Install uv using your working Python, if needed:
py -3.12 -m pip install uv==0.13.6
$env:UV_PROJECT_ENVIRONMENT = '.venv-dev'
uv sync --locked --python 3.12
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
# Edit .env: replace local password placeholders before startup.
uv run --no-sync uvicorn app.main:app --reload --no-access-log
```

In the audited session, the working Python was `C:\Users\HP\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe`; it is an environment-specific fallback, not a required installation path. Use a normally installed Python 3.12 on other machines. Windows Celery development uses Docker; native Windows workers are not our supported runtime.

`GET /` and `GET /health` retain their original responses. `/live` checks the API process; `/ready` returns 200 only when PostgreSQL and Redis probes succeed, otherwise 503 with sanitized states. Without service URLs, readiness intentionally returns 503. OpenAPI: `/docs`, `/openapi.json`. Never use the current unauthenticated API as a production deployment.

## Docker development

Install and start Docker Desktop with Linux containers. Use a URL-safe alphanumeric local database password in `.env` (URL-encode special characters if constructing the connection URL yourself).

For a per-user Docker Desktop install, a terminal opened before installation may lack its CLI on PATH. The verified installation on this machine is below; this changes PATH only for the current PowerShell session:

```powershell
$dockerBin = Join-Path $env:LOCALAPPDATA 'Programs\DockerDesktop\resources\bin'
if (Test-Path (Join-Path $dockerBin 'docker.exe')) { $env:PATH = "$dockerBin;$env:PATH" }
docker version
docker compose version
```

Codex sandbox execution may require approved elevated execution of that binary; access denied alone does not establish Docker is absent. Instruction 002 found Docker Desktop running and verified the engine with its full executable path.


```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
# Edit .env first.
docker compose config --quiet
docker compose up --build --wait
Invoke-RestMethod http://localhost:8000/ready
docker compose exec worker celery -A app.workers.celery_app:celery_app inspect ping
docker compose --profile storage up -d storage # optional local S3 emulation
# Stops containers, preserves data volumes:
docker compose down
```

PostgreSQL and Redis are bound to loopback for local tests; Compose is development-only. The optional Moto service emulates S3 at http://localhost:5000 with disposable in-memory data and test-only credentials. It has no application/bucket integration yet. Never use it for durable or production storage. No scheduler is needed until periodic jobs exist. Do not use `down -v` unless intentionally destroying local data. Service startup and Docker builds must be verified on a Docker-capable host; see report for actual evidence.

## Validation and dependency policy

Install development dependencies on the Windows host, using the working Python 3.12 environment. Keep the existing PostgreSQL/Redis services running. Store their actual local connection URLs in ignored `.env`; the example now uses IPv4 loopback. Do not copy production credentials into test configuration.

```powershell
$env:UV_PROJECT_ENVIRONMENT = '.venv-dev'
uv sync --locked
# Full suite, real PostgreSQL/Redis enabled, unique safe temp/cache directories:
.\.venv-dev\Scripts\python.exe scripts/run_tests.py
# Only the real-service integration test:
.\.venv-dev\Scripts\python.exe scripts/run_tests.py --integration-only
# Select a different local settings file explicitly:
.\.venv-dev\Scripts\python.exe scripts/run_tests.py --env-file C:\path\to\local-test.env
uv run --no-sync ruff check .
uv run --no-sync ruff format --check .
uv run --no-sync mypy
uv run --no-sync bandit -r app scripts -q
uv run --no-sync pip-audit --cache-dir .tools/pip-audit-cache
```

The runner uses its current interpreter, executes pytest from the repository root and enables integration only in the child process. It does not change your PowerShell environment, start/stop containers, install packages or alter database volumes. It creates a unique ignored `.tools/pytest-runs/run-*/` parent and gives pytest fresh `tmp`/`cache` children, avoiding inaccessible shared temp directories and deletion/reuse of existing paths. Test artifacts are retained there for inspection.

`service_settings` is a session-scoped pytest fixture: process `APP_DATABASE_URL`/`APP_REDIS_URL` override the selected file; the default file is repository `.env`. Explicit missing files, invalid settings and absent service URLs fail clearly. No credential fallback is hardcoded in the integration test. The fixture captures settings before function-scoped unit isolation clears APP_*; unit tests still clear cached settings and dependency overrides per test.

On Windows only, the fixture maps the exact URL hostname `localhost` to `127.0.0.1`, preserving credentials, port, database and query parameters. Other hosts and Linux CI values are unchanged. Compose exposes IPv4 loopback; Windows tried IPv6 `::1` first, whose connections timed out before the two-second readiness deadline. This was a connection-family problem, not slow DNS lookup or unhealthy services. Do not lengthen the application deadline or change working container service names to fix host-side tests.

The API Docker image intentionally uses `uv sync --no-dev` and excludes tests. `No module named pytest` inside that runtime is expected. Run this host command instead of installing pytest into the API container. No production image or Compose service change is required. [Exact diagnosis and executed results](docs/LOCAL_INTEGRATION_TESTING.md).

`pyproject.toml` declares Python and dependency ranges; `uv.lock` records resolved versions and hashes across supported platforms. Change dependencies intentionally with `uv lock`, review the diff and audit, then use `uv sync --locked` in CI. Docker uses the same lock without development tools. Base image tags are versioned; digest pinning and image scanning remain production hardening work.

Configuration uses `APP_` variables, OS environment overriding `.env`. `APP_ENVIRONMENT` accepts development/test/staging/production. Staging and production require explicit password-bearing service URLs and reject known placeholders; provisioning TLS, secret-manager injection and network isolation remain deployment tasks. Secrets are masked in settings and excluded from probe logs. Do not commit `.env`. Logs contain event, request ID, status and duration, without query strings, request payloads or raw exceptions.

GitHub CI is now verified for repair commit `ec605fa7aa082c8ed20b79bb400b987387339682`: [quality and containers both passed](https://github.com/vistait2018/ai-movie-platform/actions/runs/41126826693). Main branch protection and failing-PR enforcement are now verified; [Phase 1 is formally accepted](docs/roadmap/PHASE_1_ACCEPTANCE.md). Branch protections require a remote repository and owner configuration. The initial foundation commit is recorded by Instruction 003; inspect `git log -1` for its SHA. Remote setup and pushing still require authorization. See [GitHub setup gates](docs/development/GITHUB_SETUP.md) and the [proposed Phase 2 authentication plan](docs/architecture/AUTHENTICATION_PLAN.md). Mobile workspace strategy is documented in the architecture decisions; no Flutter app is claimed implemented.

## Troubleshooting

- Access denied: inspect `.venv/pyvenv.cfg`, run its base interpreter directly and inspect `Get-Acl`. An inaccessible base install cannot be fixed by activating the environment. Create `.venv-dev` with a working Python; do not delete source or weaken filesystem ACLs.
- Package downloads blocked: use an approved network-enabled terminal; do not disable TLS verification.
- Docker registry DNS lookup errors: check `Resolve-DnsName registry-1.docker.io`, `production.cloudfront.docker.com`, `ghcr.io` and `pkg-containers.githubusercontent.com`; transient errors recovered during Instruction 002 after successful host lookups and build retries. Do not rewrite the Dockerfile or weaken TLS to work around a network lookup failure.
- Readiness 503: check service URLs and `docker compose ps`/logs; database/cache absence does not affect liveness.
- Existing `.pytest_cache` cannot be read in the audited session; pytest now uses `.test-cache` and the old directory is ignored.

## Phase 2 Increment 1 — registration

`POST /api/v1/auth/register` now persists pending Viewer accounts with Argon2id passwords, atomic uniqueness/role/audit handling and a Redis abuse guard. See the [Swagger walkthrough and migration instructions](docs/development/REGISTRATION.md). Apply `alembic upgrade head` before registration. Login, verification delivery/confirmation, recovery and session endpoints are not yet implemented; Phase 2 remains in progress.

### Phase 2 access authentication

`POST /api/v1/auth/login` authenticates verified active users; `GET /api/v1/auth/me` accepts the returned short-lived bearer token. Registration stays pending. Configure a generated signing key and use the guarded local fixture command in [the authentication guide](docs/development/AUTHENTICATION.md). Refresh/logout and production email verification are not implemented yet.
