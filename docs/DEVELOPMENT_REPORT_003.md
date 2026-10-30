# Development report — Instruction 003

30 October 2026 · Africa/Lagos · Official Roadmap Version 4.0 unchanged.

## Outcome and limits
Repeated a clean install from the staged 40-file source snapshot in ignored `.tools/clean-003`, with a new virtual environment, generated local credentials, separate Docker Compose project, fresh volumes and dynamic loopback ports. All 24 tests passed with real services enabled. This verifies isolation from the working environment and existing database state **on the same physical machine**, not on a separate developer/CI host. Actual GitHub CI and branch enforcement remain blocking Phase 1 gates; no phase is marked complete.

The initial commit authorized by this instruction is created after final documentation/staged review with title `Establish Roadmap 4.0 documentation and tested FastAPI foundation`. Its exact SHA is returned in the completion message and available through `git log -1 --format=%H`. An in-tree report cannot include its own containing commit hash without changing that hash. Git author/committer identity was verified through `git var GIT_AUTHOR_IDENT`, `git var GIT_COMMITTER_IDENT` and `git config --show-origin --get user.name/user.email`; existing global configuration was used unchanged.

## Independent setup procedure and evidence
No working environment was deleted/recreated and no existing data volume was removed. Exported each staged file through `git ls-files --cached -z` / `git show :<path>` into a new, non-existing directory. Used the documented uv locked-install procedure, with the known working Python path as an environment-specific interpreter and a separate UV_PROJECT_ENVIRONMENT:

```powershell
$cleanRoot = Join-Path (Get-Location) '.tools\clean-003'
$env:UV_PROJECT_ENVIRONMENT = Join-Path $cleanRoot '.venv-dev'
.\.venv-dev\Scripts\uv.exe sync --project $cleanRoot --locked --python .venv-dev\Scripts\python.exe --cache-dir .uv-cache
```

Result: fresh CPython 3.12.14 environment created, 74 dependency packages installed from the existing generated lock, 75 resolved packages including project. The download cache was reused; installed packages/environment were not copied from the working environment.

Copied .env.example to the ignored verification .env and replaced its password placeholder with a cryptographically random local value without printing it. A verification-only override changed published ports, leaving the existing compose.yaml/Dockerfile intact:

```yaml
services:
  api:
    ports: !override ["127.0.0.1::8000"]
  postgres:
    ports: !override ["127.0.0.1::5432"]
  redis:
    ports: !override ["127.0.0.1::6379"]
  storage:
    ports: !override ["127.0.0.1::5000"]
```

Exact Compose invocation shape used for all isolated checks:
```powershell
$dockerCli = 'C:\Users\HP\AppData\Local\Programs\DockerDesktop\resources\bin\docker.exe'
$dcArgs = @('compose','-p','ai-movie-school-clean003','--project-directory',$cleanRoot,'-f',"$cleanRoot\compose.yaml",'-f',"$cleanRoot\compose.verify.yaml",'--env-file',"$cleanRoot\.env",'--profile','storage')
& $dockerCli @dcArgs config --quiet
& $dockerCli @dcArgs up --build -d --wait --wait-timeout 180
& $dockerCli @dcArgs ps --all
& $dockerCli @dcArgs exec -T postgres pg_isready -U movie -d movie
& $dockerCli @dcArgs exec -T postgres psql -U movie -d movie -tAc 'SELECT 1'
& $dockerCli @dcArgs exec -T redis redis-cli PING
& $dockerCli @dcArgs exec -T worker celery -A app.workers.celery_app:celery_app inspect ping
Get-Content .tools/verify_worker_dispatch.py -Raw | & $dockerCli @dcArgs exec -T worker python -
```

All operations passed. Actual isolated bindings: API 127.0.0.1:62536, PostgreSQL 127.0.0.1:64579, Redis 127.0.0.1:64578, Moto 127.0.0.1:64580. Both application images built successfully. PostgreSQL accepted connections and returned 1; Redis returned PONG. All five containers were healthy. HTTP /, /health, /live and /ready returned their exact expected bodies. OpenAPI schema title and all four routes were verified; optional storage returned HTTP 200. Storage evidence is startup/HTTP only, not S3 object-operation coverage.

Celery inspect returned one node/pong. An actual movie.ping dispatch completed with task ID `f5ba7647-85e4-4015-a37b-23c27e9fdc26`, event task-succeeded, result `{"status":"ok"}`. Reused the ignored event-verification helper documented in report 002; it subscribes before dispatch and restores event monitoring afterward. No paid provider operation was involved.

## Fresh-environment tests and quality checks
Ignored helper `.tools/run_clean_tests003.py` read only the isolated .env and recorded ports, set RUN_SERVICE_TESTS=1, APP_ENVIRONMENT=test and IPv4 database/Redis URLs with the generated local password, then executed the following **from the isolated source directory using its new interpreter**:

```powershell
.\.venv-dev\Scripts\python.exe -m pytest -q --basetemp .tools/pytest-003 -o cache_dir=.tools/pytest-cache-003
.\.venv-dev\Scripts\python.exe -m ruff check app tests
.\.venv-dev\Scripts\python.exe -m ruff format --check app tests
.\.venv-dev\Scripts\python.exe -m mypy
.\.venv-dev\Scripts\python.exe -m bandit -r app -q
.\.venv-dev\Scripts\python.exe -m pip check
.\.venv-dev\Scripts\python.exe -m pip_audit --cache-dir .tools/pip-audit-cache --timeout 15 --progress-spinner off
```

First test attempt had 23 passed and one setup error because the verification helper had not created the parent `.tools` directory required by pytest basetemp. Created only that missing ignored parent and repeated. **Final result: 24 passed, no failures/errors/skips, one upstream Starlette/httpx deprecation warning, in 0.92 seconds; exit 0.** No application/test source was changed to obtain this result.

Ruff passed; format check passed for 17 application/test files; mypy passed for 13 application files; Bandit exited 0 with no findings; pip check found no broken requirements; dependency audit reported no known vulnerabilities. No container OS vulnerability scan is claimed. All helper commands exited successfully on the final run.

## Cleanup and preservation
After checks:
```powershell
& $dockerCli @dcArgs down
& $dockerCli volume inspect --format '{{.Name}} {{.CreatedAt}}' ai-movie-school_postgres-data ai-movie-school_redis-data ai-movie-school-clean003_postgres-data ai-movie-school-clean003_redis-data
& $dockerCli compose --env-file .env.example --profile storage ps --all
```

Only isolated verification containers/network were removed; `down -v` was never used. Original PostgreSQL/Redis volumes retained their creation timestamp 2026-10-30T19:42:08Z before and after. New isolated volumes created at 19:49:03Z were also retained. The original five services remained healthy/running at their original loopback ports. Both original virtual environments and ignored clean verification directory remain intact. No machine network, registry, Docker or application configuration was replaced.

## Local workflow validation and remote CI status
`git remote -v` returned no remotes. No repository creation, remote addition or push was attempted. YAML checks verified triggers, read-only contents permissions, quality/container job structure, locked installs, enabled service tests and always-run cleanup.

Downloaded official actionlint 1.7.11 Windows AMD64 release and checksum list into ignored `.tools/actionlint-1.7.11`; SHA-256 matched the official entry. Ran:
```powershell
.tools/actionlint-1.7.11/actionlint.exe -version
.tools/actionlint-1.7.11/actionlint.exe -shellcheck= -pyflakes= .github/workflows/ci.yml
```
Result: actionlint 1.7.11, no findings, exit 0. External ShellCheck/Pyflakes integration was disabled. This is workflow lint, not remote job execution. [GitHub setup instructions](development/GITHUB_SETUP.md) specify repository-owner decisions, future authorization, successful run evidence, required check contexts, branch protections and a failing-PR enforcement test.

## Phase 1 acceptance matrix
| Roadmap requirement | Evidence | Status |
| --- | --- | --- |
| Existing repository audit and valid code retained | Original responses/tests preserved; no application changes in 003 | Verified |
| Python/dependencies/project configuration | Fresh 3.12.14 env; locked install and package consistency | Verified locally |
| Organized application/API/models/schemas/services/workers | Existing package boundaries inspected; business modules intentionally future work | Foundation verified |
| Flutter project or documented workspace strategy | TECHNOLOGY_DECISIONS ADR-007; no app implementation claimed | Documented |
| Backend/worker Dockerfiles and Compose PostgreSQL/Redis | Shared runtime Dockerfile; both isolated image builds, fresh services healthy | Verified locally |
| Celery and local storage emulation | Actual completed job; Moto healthy/HTTP 200 | Verified at foundation scope |
| Development/test/staging/production settings | Validated settings, required production values, passing config tests | Baseline verified; no production deployment claimed |
| Liveness/readiness | Live HTTP checks and real PostgreSQL/Redis tests | Verified |
| Git repository workflow and protections | Initial commit created; no remote/protections | **Blocked on authorized remote setup** |
| GitHub Actions Ruff/type/pytest/dependency checks | Definition reviewed, actionlint and local tools passed | **Remote execution not verified** |
| Reproducible Docker builds | Fresh exported source built with unchanged lock/Dockerfile | Verified locally; second-host proof pending |
| OpenAPI/logging/error handling | Live schema, preserved routes, passing log/error tests | Verified at foundation scope |
| .env example/ignore/secrets guidance | Reviewed placeholder/test-only staged credentials, ignored runtime data | Verified by targeted staged review |
| Setup/testing/troubleshooting documentation | README procedure exercised with isolated directory/ports and documented temp-parent correction | Verified on same host |
| Clean setup on another developer/CI host | Isolated same-machine setup passed; second host unavailable | **Not verified** |
| Completion: clean setup + passing tests + CI rejects broken changes | Local first two pass; CI enforcement test has not run | **Phase 1 remains incomplete** |

Phase 0 approvals remain outstanding. No roadmap or acceptance gate was silently removed to mark completion.

## Git review and commit
Reviewed staged source, configuration, tests, documentation and generated dependency lock. Generated tool environments/caches, local .env files and verification artifacts remain under ignored paths. Targeted content scan checks private-key/common token signatures and embedded service passwords, allowing only explicit placeholder/test fixtures; it cannot prove absence of every possible secret format. The first staged scan stopped on a Windows-encoded dash in PHASE_STATUS.md; normalized that document to UTF-8 and repeated the checks before committing. Review and whitespace checks precede the authorized initial commit. Existing author identity is non-empty and matches committer identity; no identity config was invented or changed.

Final commit command:
```powershell
git commit -m "Establish Roadmap 4.0 documentation and tested FastAPI foundation"
git log -1 --format='%H%n%s'
git status --porcelain=v1
git remote -v
```

The completion response records the actual SHA and final status after execution. Only intentional ignored runtime artifacts remain; no unrelated untracked file is intended for inclusion.

## Phase 2 preparation and next sequence
[Authentication plan](architecture/AUTHENTICATION_PLAN.md) proposes opaque server-side web sessions with CSRF/cookie protections, mobile bearer access credentials and rotated refresh tokens, PostgreSQL authoritative revocation, Argon2id passwords, explicit roles, activation/recovery, privileged MFA and audited bootstrap. Minimum migrations cover identity/RBAC, sessions/credentials, action tokens/MFA/security events/email delivery. TTL/rate-limit choices are proposals requiring review.

Sequence: approve design/policies -> identity ORM/migration foundation -> registration/password service -> verification/recovery/email mocks -> web/mobile sessions and refresh -> RBAC/profile/lifecycle -> privileged MFA/bootstrap -> rate limits/security audit -> complete auth/migration/authorization tests and CI evidence. No Phase 2 code, schema migration or dependency was implemented. Shared web/Android/iOS scope remains intact.

Next required work: owner decisions for Phase 0, authorization for actual GitHub setup/execution/enforcement, and second-host verification. Then implement the prepared Phase 2 sequence under an explicit development instruction. No remote push, production deployment, live finance or paid AI call occurred.
