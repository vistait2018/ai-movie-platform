# Phase 1 verification report — Instruction 002

30 October 2026 · Africa/Lagos · Official Roadmap Version 4.0, phases 0–31 remains authoritative.

## Outcome
Local Phase 1 container/service verification succeeded without changes to application source, dependencies, tests, Dockerfile, compose.yaml or .env.example. Both application images built, all five development services became healthy, real database/cache/API checks passed, and a real Celery task completed. The complete test suite with real-service integration enabled passed **24 tests, zero skips**. Phase 1 remains **in progress**, pending the remaining acceptance requirements below.

## Files inspected and changed
Read PROJECT_STATUS.md, PHASE_STATUS.md, report 001, compose.yaml, Dockerfile, .env.example, workflow, integration test and fixture, Git status and staged contents. Inspected installed Celery event receiver code to use its actual event-consumer API for dispatch verification.

Modified existing README.md (per-user Windows Docker discovery, DNS troubleshooting, IPv4 integration URLs and pytest permission workaround), PROJECT_STATUS.md and PHASE_STATUS.md. Added a historical-evidence link to report 001. Created only this new report. A temporary `.tools/verify_worker_dispatch.py` helper is ignored and excluded from staging. No configuration replacement, duplicated application file or roadmap scope change.

## Exact commands and actual results
All commands ran from `C:/Users/HP/Documents/ai-movie-school` in PowerShell. Docker and live host integration commands used approved elevated execution because the session sandbox denied the installed Docker executable. Shell command batches sometimes ended with a successful read-only command after an earlier failure; individual results below describe each operation, not just the batch's final exit status.

### Docker discovery
```powershell
Get-Command docker -All -ErrorAction SilentlyContinue
where.exe docker
Get-Item 'C:\Program Files\Docker\Docker\resources\bin\docker.exe', 'C:\ProgramData\DockerDesktop\version-bin\docker.exe' -ErrorAction SilentlyContinue
Get-Process -Name 'Docker Desktop','com.docker.backend' -ErrorAction SilentlyContinue | Select-Object -Unique ProcessName,Path
Get-Service -Name com.docker.service -ErrorAction SilentlyContinue
Test-Path '\\.\pipe\docker_engine'
Test-Path '\\.\pipe\dockerDesktopLinuxEngine'
$dockerCli = 'C:\Users\HP\AppData\Local\Programs\DockerDesktop\resources\bin\docker.exe'
& $dockerCli --version
& $dockerCli version
& $dockerCli compose version
```
`docker` was absent from PATH and the usual system-wide locations. Running Desktop/backend processes exposed the per-user installation. Both engine pipes existed. No service entry was returned by the service-name query; that did not mean the user-mode engine was absent. Direct sandbox execution returned access denied. Approved elevated execution succeeded:

| Component | Verified result |
| --- | --- |
| CLI | Docker 29.8.2, build 7fc2dff, windows/amd64 |
| Engine | Docker 29.8.2, Docker Desktop 4.94.0, linux/amd64 |
| Context | desktop-linux |
| Compose | v5.5.1 |

### Compose, builds and startup
```powershell
& $dockerCli compose --env-file .env.example --profile storage config --quiet
& $dockerCli compose --env-file .env.example ps --all
& $dockerCli compose --env-file .env.example build
& $dockerCli image inspect --format '{{.Id}}' postgres:17.6-bookworm redis:7.4.6-bookworm ai-movie-school-api ai-movie-school-worker
& $dockerCli compose --env-file .env.example up -d --wait --wait-timeout 60 postgres redis
Resolve-DnsName registry-1.docker.io
Resolve-DnsName ghcr.io
Resolve-DnsName production.cloudfront.docker.com
Resolve-DnsName pkg-containers.githubusercontent.com
Resolve-DnsName auth.docker.io
Resolve-DnsName production.cloudflare.docker.com
Resolve-DnsName pypi.org
Resolve-DnsName files.pythonhosted.org
# Build retried as the registry/CDN lookups recovered:
& $dockerCli compose --env-file .env.example build
& $dockerCli compose --env-file .env.example up -d --wait --wait-timeout 180
& $dockerCli compose --env-file .env.example --profile storage up -d --wait --wait-timeout 120 storage
Invoke-WebRequest http://127.0.0.1:5000/ -UseBasicParsing | Select-Object StatusCode
& $dockerCli compose --env-file .env.example --profile storage ps --all
```
- Compose semantic validation: **passed**, exit 0.
- Initial build failed resolving registry-1.docker.io. Initial service startup failed fetching a Docker CDN blob; required images were not cached. A retry progressed to a GHCR CDN lookup failure. Host DNS checks resolved required hosts; the extra production.cloudflare.docker.com check failed, but that hostname was not required by the eventual successful pulls.
- Final build: **passed**; API and worker images built using the unchanged Dockerfile, Python 3.12.14 and locked runtime dependencies. No registry/TLS/proxy settings were modified.
- Final core startup: **passed**, exit 0; PostgreSQL, Redis, API and worker healthy.
- Optional Moto startup: **passed**, exit 0; container healthy and HTTP 200. This is emulator startup/HTTP smoke evidence, not S3 upload/download or production storage validation.
- Isolated local verification used existing .env.example placeholder credentials, loopback port bindings and fresh Docker volumes. No actual credential file was created.

### Service readiness and Celery dispatch
```powershell
& $dockerCli compose --env-file .env.example exec -T postgres pg_isready -U movie -d movie
& $dockerCli compose --env-file .env.example exec -T postgres psql -U movie -d movie -tAc 'SELECT 1'
& $dockerCli compose --env-file .env.example exec -T redis redis-cli PING
Invoke-RestMethod http://localhost:8000/ready | ConvertTo-Json -Compress
& $dockerCli compose --env-file .env.example exec -T worker celery -A app.workers.celery_app:celery_app inspect ping
Get-Content .tools/verify_worker_dispatch.py -Raw | & $dockerCli compose --env-file .env.example exec -T worker python -
```

| Service | Actual result | Local binding |
| --- | --- | --- |
| PostgreSQL | Healthy; accepting connections; SELECT 1 returned 1 | 127.0.0.1:5432 |
| Redis | Healthy; PONG | 127.0.0.1:6379 |
| FastAPI | Healthy; `/ready` returned status ready and both dependencies healthy | 127.0.0.1:8000 |
| Celery | Healthy; inspect ping returned pong, one node online; dispatched task succeeded | No published worker port |
| Moto | Healthy; HTTP 200 | 127.0.0.1:5000 |

Actual task completion event: task ID `e39557b1-70d0-4dae-8e05-f6491f6bdfba`, event `task-succeeded`, result `{"status":"ok"}`. Worker event monitoring was enabled temporarily and disabled in `finally`. The helper subscribed before dispatch and waited for the matching task UUID; this verifies execution, not just a broker enqueue or worker-control ping.

Helper source for reproducibility (the on-disk helper is deliberately ignored):
```python
import ast
import json
import socket
import time
from app.workers.celery_app import celery_app

outcome = {}
expected_id = None


def completed(event):
    if event.get("uuid") == expected_id:
        outcome.update(event)


enabled = celery_app.control.enable_events(reply=True, timeout=5)
assert enabled, "No worker acknowledged event monitoring"
try:
    with celery_app.connection() as connection:
        receiver = celery_app.events.Receiver(
            connection,
            handlers={"task-succeeded": completed, "task-failed": completed},
        )
        with receiver.consumer_context() as (consumer_connection, channel, consumers):
            task = celery_app.send_task("movie.ping")
            expected_id = task.id
            deadline = time.monotonic() + 20
            while not outcome and time.monotonic() < deadline:
                try:
                    consumer_connection.drain_events(timeout=2)
                except socket.timeout:
                    pass
    assert outcome.get("type") == "task-succeeded"
    result = ast.literal_eval(outcome["result"])
    assert result == {"status": "ok"}
    print(json.dumps({"task_id": expected_id, "event": outcome["type"], "result": result}))
finally:
    celery_app.control.disable_events(reply=True, timeout=5)
```

### Tests, including failures before final success
1. Baseline `python -m pytest -q`: **23 passed, 1 skipped**, one upstream Starlette/httpx deprecation warning; integration opt-in was disabled.
2. Enabled `python -m pytest -m integration -q` before services started: **1 failed, 23 deselected**; /ready correctly returned 503 with both dependencies unavailable.
3. Enabled full host run using localhost and the default temp/cache paths: **22 passed, 1 failed, 1 error**. Integration probes timed out; pytest tmp_path setup hit an inaccessible existing Windows temp directory and cache writes also warned. The live container API was nevertheless ready.
4. Corrected host command using explicit IPv4 loopback, a fresh project-local temp directory and disabled shared cache provider:

```powershell
$env:RUN_SERVICE_TESTS = '1'
$env:APP_ENVIRONMENT = 'test'
$env:APP_DATABASE_URL = 'postgresql://movie:replace-local-password@127.0.0.1:5432/movie'
$env:APP_REDIS_URL = 'redis://127.0.0.1:6379/0'
$pytestTemp = ".tools/pytest-002-host-$PID"
if (Test-Path $pytestTemp) { throw 'Refusing to reuse existing pytest temporary directory' }
.\.venv-dev\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp $pytestTemp
```

**Final result: 24 passed, zero failures, zero errors, zero skips, in 1.05 seconds; exit 0.** Two warnings: upstream Starlette/httpx deprecation and unknown cache_dir config because this particular command disabled the cache plugin. Both are documented; neither indicates a failed test. For future runs, use a fresh `-o cache_dir=.tools/<unique-cache>` instead of disabling the plugin. Keep secrets in ignored local configuration and use actual local test credentials when they differ from the example.

### Complete quality/security commands
The following checks were executed, not inferred from configuration:
```powershell
.\.venv-dev\Scripts\python.exe --version
.\.venv-dev\Scripts\python.exe -m ruff check .
.\.venv-dev\Scripts\python.exe -m ruff format --check .
.\.venv-dev\Scripts\python.exe -m mypy
.\.venv-dev\Scripts\python.exe -m bandit -r app -q
.\.venv-dev\Scripts\python.exe -m pip check
.\.venv-dev\Scripts\uv.exe lock --check --offline --python .venv-dev\Scripts\python.exe --cache-dir .uv-cache
.\.venv-dev\Scripts\python.exe -m pip_audit --cache-dir .tools/pip-audit-cache --timeout 15 --progress-spinner off
git diff --cached --check
git remote -v
```
Python: 3.12.14. Ruff: passed. Formatting: 30 files already formatted. Mypy: passed, 13 application source files. Bandit: exit 0, no findings. pip check: no broken requirements. Lock check: passed, 75 resolved packages including project. pip-audit: exit 0, no known vulnerabilities found at verification time. Staged whitespace check: passed. No Git remote configured. The advisory check does not scan container OS packages; production image security remains separate work.

## Staged-source inspection
Inspected index contents through `git ls-files --cached -z` and `git show :<path>`, rather than trusting working-tree files. Initial scan covered 39 staged files; forbidden path checks excluded `.env`, virtual environments, caches and common signing-key file extensions. Content checks searched private-key headers, common AWS/GitHub/OpenAI token patterns and embedded database/broker passwords. Nine URL password matches were approved placeholder/test fixtures in .env.example, tests and CI; no unrecognized matches were found. The staged template retained placeholder credentials. This is a targeted heuristic review, not a guarantee against every possible secret format. After documentation staging, the repeated index scan covered 40 files with 10 approved test/placeholder URL matches and zero findings. Staged whitespace checks passed, and no unstaged differences remained.

## Remaining acceptance requirements
- GitHub CI jobs must actually execute successfully, including Linux integration/container jobs; none has run because no remote exists.
- Repository owner must establish the remote workflow and required branch protections when authorized. No remote, push, deployment or commit was created in this instruction.
- Independently repeat a documented clean setup on another developer/CI host. Local first-time container bootstrap was verified here, not on a second host.
- Review/create the prepared first commit and record Phase 1 acceptance after the remaining gates. No phase is marked complete automatically.
- Phase 0 owner approvals remain BR-01–13 and proposed targets. Product scope and all future roadmap commitments are unchanged.

Initial network and Windows permission/name-resolution failures were recovered for this local verification; they are documented setup constraints rather than current core-service blockers. The upstream test-client warning remains. Optional S3 object operations are not yet implemented or tested.

## Runtime state and handover note
The five local development containers are left running for continued work, bound to loopback where ports are published. PostgreSQL and Redis named volumes are retained. To stop them without deleting data: `& $dockerCli compose --env-file .env.example --profile storage down`. Do not use `down -v` unless intentionally deleting development data.

Continue the existing ai-movie-school project under Roadmap 4.0. Instruction 002 verified the existing Phase 1 infrastructure without replacing application or Docker configurations. Docker CLI/engine 29.8.2 and Compose 5.5.1 work through the per-user Docker Desktop executable with approved elevated execution. Compose configuration, both application builds, PostgreSQL, Redis, live FastAPI readiness, actual Celery task completion and optional Moto HTTP startup all passed. The final complete suite with real-service tests enabled passed 24 tests without skips; Ruff, formatting, mypy, Bandit, dependency consistency, lock check and vulnerability audit passed. Earlier DNS, localhost timeout and pytest temporary-directory failures were resolved by retries/host lookups, IPv4 test URLs and an isolated temp directory. Staged review found only approved test/placeholder credentials and no environments/caches. No live financial transaction, paid AI call, commit, remote, push or production deployment occurred. Phase 0 still needs owner approvals; Phase 1 still needs independently verified setup, actual GitHub CI, branch protections and final commit/acceptance. Do not mark a phase complete or claim business/AI/streaming/mobile features exist. Read PHASE_STATUS.md and this report before continuing.
