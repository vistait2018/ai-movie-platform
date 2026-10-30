# Windows host integration testing repair

30 October 2026 · Official Master Roadmap Version 4.0 unchanged.

## Verified result
**24 passed, zero failures, zero errors, zero skipped integration tests** in 1.10 seconds using the final host runner and real PostgreSQL/Redis. One existing upstream Starlette/httpx deprecation warning remains. Ruff, formatting, mypy (application and runner) and Bandit checks passed. API runtime image, Compose configuration, application readiness implementation, dependency manifest and local .env were not changed.

## Exact cause and evidence
The old tests/test_services.py read APP_DATABASE_URL and APP_REDIS_URL with os.getenv at module import. If absent, it used hardcoded local credential/localhost defaults. It then constructed Settings with `_env_file=None`, bypassing .env entirely. Capturing the values before function isolation avoided fixture clearing, but also made file-based local configuration ineffective and hid the source of those defaults.

In this session, process URL variables were absent. The fallback credentials happened to match local .env credentials, so an incorrect password was **not** the cause of this reproduced failure. The hostname was the immediate cause:

| Measured probe | Result |
| --- | --- |
| localhost name resolution | 0.012 seconds; IPv6 ::1 precedes IPv4 127.0.0.1 |
| ::1:5432 | TCP connection timed out after 0.602 seconds with a 0.6-second diagnostic limit |
| ::1:6379 | TCP connection timed out after 0.601 seconds with the same limit |
| 127.0.0.1:5432 and :6379 | Each TCP connection succeeded in about 0.001 seconds |
| Actual readiness with localhost URLs | Both unavailable; about 2.043 seconds |
| Actual readiness with the same credentials and IPv4 URLs | Both healthy; about 0.031 seconds |

Compose publishes PostgreSQL/Redis to IPv4 loopback only. Windows attempts IPv6 localhost first; those connection attempts exhaust the two-second outer readiness deadline before successful IPv4 fallback. DNS itself was fast. The correct fix is host-test URL configuration, not changing container service names, enlarging the application timeout or mocking readiness.

The original failure was reproduced with RUN_SERVICE_TESTS=1 and a unique project-local pytest temp directory: **1 failed, 23 deselected**, /ready returned 503 with both dependencies unavailable. No services were stopped to produce that result.

## Changes
- `tests/conftest.py`: session-scoped service_settings loads selected .env through Settings, with process variables taking precedence. Explicit missing files, invalid config and missing service URLs fail with credential-safe messages. On Windows only, exact localhost URL hosts become 127.0.0.1; credentials, explicit port, database and query parameters are preserved. Non-localhost hosts and Linux values remain unchanged.
- The session fixture captures configuration before the existing function-scoped isolation clears APP_* variables. Unit-test cache/dependency isolation is retained.
- `tests/test_services.py`: consumes that fixture; removed import-time credential fallbacks and disabled-dotenv construction. /ready still calls real PostgreSQL SELECT 1 and Redis PING and must return both healthy.
- `scripts/run_tests.py`: uses its own interpreter, explicitly selects repository tests (so pytest loads the custom option), enables RUN_SERVICE_TESTS only in the child, and sets the child environment to test. Runs from repository root regardless of caller location; returns pytest's exit status.
- Unique `.tools/pytest-runs/run-*/` directories hold fresh tmp/cache children. Existing shared temp paths, environments and database volumes are neither reused destructively nor deleted. Credentials/URLs are not printed.
- `.env.example`: host URL examples now use 127.0.0.1; no real credentials added. Existing local .env is untouched.
- README and current status documentation now reference the supported command and this evidence.

No pytest installation was made inside the API image. Dockerfile already intentionally installs only runtime dependencies with uv --no-dev, and .dockerignore excludes tests. `No module named pytest` in that container is expected for the lean runtime. Host development dependencies already provide the test tools.

## Repeatable command and actual execution
Run from the repository in Windows PowerShell using the working environment:
```powershell
.\.venv-dev\Scripts\python.exe scripts/run_tests.py
```
Result: **24 passed, 1 warning, zero failures/errors/skips**; real service checks executed. The runner uses existing local .env and normalizes localhost only in test configuration. Do not place production credentials in this local test file.

For integration only:
```powershell
.\.venv-dev\Scripts\python.exe scripts/run_tests.py --integration-only
```
This was also executed from outside the repository root using absolute interpreter/script paths: **1 passed, 23 deselected, zero skipped**, in 0.31 seconds. No PowerShell environment variables need manual setup or cleanup.

To select another local settings file:
```powershell
.\.venv-dev\Scripts\python.exe scripts/run_tests.py --env-file C:\path\to\local-test.env
```
This option is documented; that sample path is illustrative, not an executed file. Explicit process APP_* URL values override the file, so remove stale overrides if you intend to use file values.

The first runner attempt stopped before collection because pytest did not discover a custom option defined under tests/conftest.py without an explicit tests directory. Added the tests path to its argument list; the next full run passed 24 tests. Subsequent final acceptance run after subprocess review also passed 24 tests in 1.10 seconds. Ruff import/format findings introduced while arranging security comments were fixed before final checks.

## Final quality commands
```powershell
.\.venv-dev\Scripts\python.exe -m ruff check .
.\.venv-dev\Scripts\python.exe -m ruff format --check .
.\.venv-dev\Scripts\python.exe -m mypy
.\.venv-dev\Scripts\python.exe -m mypy scripts/run_tests.py
.\.venv-dev\Scripts\python.exe -m bandit -r app scripts -q
git diff --check
```
Ruff passed; full format check reported 35 files already formatted. Scoped application/test/runner formatting also passed (18 files). Mypy passed for 13 application files and the runner. Bandit initially flagged generic subprocess import/execution checks B404/B603; reviewed the fixed current-interpreter/module argument list and explicit shell=False, documented that reasoning and applied only those two targeted annotations. Final Bandit exited 0 without findings or parser warnings. No shell command is constructed from the settings path.

## Preservation and current state
Read-only Docker checks confirmed all five original containers remain healthy. Existing PostgreSQL/Redis volumes retain creation time 2026-10-30T19:42:08Z. No Docker build, restart, recreation, down command, volume removal or dependency installation was performed for this repair. Dockerfile, compose.yaml, app readiness/settings and pyproject.toml have no diff.

An existing user edit to docs/DEVELOPMENT_REPORT_002.md and untracked New Text Document.txt were present before work and left untouched. No commit, staging, remote operation, live financial transaction, paid AI call or production deployment was performed. Phase 0 approvals and Phase 1 remote CI/branch-protection/second-host gates remain outstanding; this repair does not mark a phase complete.

## Handover note
Continue ai-movie-school under Roadmap 4.0. Windows host integration is repaired and actually verified: 24 tests passed, no failures or skipped integration tests; PostgreSQL and Redis were exercised through real /ready probes. Immediate cause was IPv6-first localhost connections timing out against IPv4-only Docker bindings. The old test also ignored .env and used import-time fallback URLs. The new session fixture loads explicit settings, normalizes only Windows localhost to IPv4 and preserves unit isolation. Use `.venv-dev/Scripts/python.exe scripts/run_tests.py`; it enables real integration in a child process and creates safe unique temp/cache paths. API image remains lean without pytest; Docker configuration, containers and persistent volumes are preserved. Ruff, formatting, mypy and reviewed Bandit checks passed. No phase completion, commit or remote action is claimed. Read this report and PHASE_STATUS.md before continuing.
