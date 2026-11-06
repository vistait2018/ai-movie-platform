# Development report 007 — Phase 2 Increment 1

31 October 2026 · Official Roadmap 4.0 unchanged · Feature branch codex/phase2-identity-registration.

## Delivered
- SQLAlchemy users (UUID, canonical unique email, display name, Argon2id hash, constrained status, verification/created/updated/last-login timestamps).
- Extensible roles/permissions and association tables. Seeds Viewer, Creator, Admin, Super Admin plus existing roadmap Moderator/Finance Administrator; no privileged account or default password.
- Additive Alembic revision **0001_identity_core** with registration security-event records.
- **POST /api/v1/auth/register**: validated/canonical email, 15–128 character password, default pending Viewer, transactional user/role/audit writes, concurrent uniqueness and generic duplicate-safe 202 response. Protected input fields are rejected.
- pwdlib recommended Argon2id hashes with random salts; sensitive validation input/context removed from errors; generic DB failures and sanitized operational events.
- Basic atomic Redis registration guard (10 requests/60 seconds by default, configurable), fail-closed behavior and no raw email/password in keys.
- Working Docker-hosted Swagger/registration and safe online migrations, without pytest in the lean image.

This is Increment 1 only. Verification delivery/confirmation, login/access-refresh sessions, recovery, profile/admin APIs, MFA and full permission enforcement remain later increments. New accounts stay pending and no session/token is issued; no email has been promised/sent by this slice. Phase 2 is **not complete**.

## Files
Created app/db/base.py, app/db/session.py, app/models/identity.py, app/core/passwords.py, app/schemas/auth.py, app/services/registration.py, app/services/rate_limits.py, app/api/auth.py, alembic.ini, migrations/env.py, migration template and versions/0001_identity_core.py; tests/test_registration.py, tests/test_identity_security.py; docs/development/REGISTRATION.md and this report.

Modified app/main.py (router and sanitized exception handlers), settings (two abuse-guard defaults), pyproject/uv.lock, existing test fixtures, Dockerfile (copy migration assets), CI (runtime migration checks), .env.example, README and proportionate architecture/phase/status docs. Preserved existing endpoints, source, five-container Compose architecture and unrelated New Text Document.txt. No credentials, .env, dumps, environments or caches are included in source changes.

## Database and data preservation
Before the live upgrade, verified there were zero public tables/no identity name collisions. Created a custom-format pg_dump backup in ignored .tools and verified the archive listing. Applied only additive upgrade 0001_identity_core to existing movie database; Alembic current reports head and check reports no new operations. No existing volume/database was reset or deleted. PostgreSQL and Redis container IDs remained unchanged; both original data-volume creation timestamps remain 2026-10-30T19:42:08Z. Only API/worker were rebuilt/refreshed; all five services are healthy.

Tests create uniquely named movie_auth_test_* databases on explicitly local services, apply real migrations and dispose/drop only those newly created databases. Downgrade/upgrade round-trip runs only there. Redis tests delete only their unique created key; no FLUSH operation. Development .env is unchanged.

## Executed checks
- Official Windows runner: **45 passed**, zero failures/errors/skipped integration tests, one existing Starlette/httpx warning, 4.50 seconds on the final safety-guard run (earlier expanded run 3.76 seconds). Preserves the original 24 tests and adds 21 identity/security/migration cases.
- Tests cover persistence/default Viewer/unverified status, normalized email, hash verification/salt, generic duplicates/unchanged password, invalid/redacted input, privilege-field injection, four concurrent duplicate requests, rollback on role/audit failure, safe DB-error response, real Redis throttle/fail-closed behavior, seeded roles, ORM/migration drift and isolated migration round-trip.
- Ruff lint/format passed; mypy passed for 21 app files; Bandit app/scripts passed. New Redis library typing findings were corrected before final checks.
- pip check passed; dependency audit reported no known vulnerabilities. Locked runtime additions: SQLAlchemy 2.1.6, Alembic 1.20.1, pwdlib 0.3.1/argon2-cffi 25.1.0, email-validator 2.3.0 and resolved transitive packages. No custom crypto.
- Host and runtime Alembic upgrade/current/check passed; no metadata/schema drift.
- Real Docker HTTP registration smoke returned 202 and was verified in PostgreSQL as pending Viewer with Argon2id; password was generated only in memory and never displayed. Swagger/OpenAPI expose the request/response schema. /ready remains healthy. One development smoke account was intentionally retained.
- Runtime inspection confirmed pytest absent. Real PostgreSQL and Redis were exercised, not substituted with SQLite or mocked readiness.

Commands:
```powershell
.\.venv-dev\Scripts\python.exe scripts/run_tests.py
.\.venv-dev\Scripts\python.exe -m ruff check .
.\.venv-dev\Scripts\python.exe -m ruff format --check .
.\.venv-dev\Scripts\python.exe -m mypy
.\.venv-dev\Scripts\python.exe -m bandit -r app scripts -q
.\.venv-dev\Scripts\python.exe -m pip check
.\.venv-dev\Scripts\python.exe -m pip_audit --cache-dir .tools/pip-audit-cache --timeout 15 --progress-spinner off
.\.venv-dev\Scripts\python.exe -m alembic upgrade head
.\.venv-dev\Scripts\python.exe -m alembic current
.\.venv-dev\Scripts\python.exe -m alembic check
```

## Docker/network evidence
Canonical Dockerfile build attempts failed while resolving GHCR/Docker registry authentication hostnames. No machine DNS/registry configuration was changed. To make local Swagger functional, an ignored temporary Dockerfile reused the existing cached Python/uv runtime, installed only the same locked runtime dependencies and copied the same app/migration assets. That local image built, and only API/worker were refreshed with --no-deps --no-build --pull never. The canonical repository Dockerfile retains the original architecture plus migration COPY statements; GitHub PR containers run 41193643965 independently built it and passed runtime upgrade/check on Ubuntu. Do not misreport the network-failed local canonical build as successful.

This is an environmental local rebuild limitation, not evidence of a feature test failure. GitHub confirmed run 41193643965 success for feature commit c854776b9b60dadb718cfea9ffa6720f24eacf6a: quality passed in 51 seconds and containers in 46 seconds; Ubuntu test logs reported 45 passed, zero failures/skips, one upstream warning, in 2.51 seconds. No success was inferred from configuration alone. Runtime stays usable for owner testing even while registry lookup is unreliable.

## Owner test and next increment
Open http://127.0.0.1:8000/docs → Authentication → POST /api/v1/auth/register → Try it out. Use your own new local email, display name and 15–128 character password. Expect 202 with a generic activation-required message; duplicates return the same response and do not replace the account. Extra role/status fields or invalid input produce redacted 422. Full instructions: [registration guide](development/REGISTRATION.md).

No genuine business-owner decision blocks this increment. Engineering choices (case-insensitive canonical accounts, generic 202, password length and configurable local throttle defaults) are documented. They do not invent prices, commissions or commercial policy.

Next is **Increment 2**: secure login, access/refresh issuance, protected current-user endpoint and authentication tests, followed by Increment 3 local mock verification/recovery. Full Phase 2 acceptance stays open until every authentication/session/permission/security requirement passes.

Git: dedicated Phase 2 branch; meaningful implementation commit and reviewable PR only; never direct push to protected main, no force push or failing merge. Exact commit/PR and final required-job results are supplied in the completion report and available in Git/GitHub history. No paid AI/email/payment integration or production credential change occurred.

## Verified GitHub handover

Feature commit `c854776b9b60dadb718cfea9ffa6720f24eacf6a`, branch codex/phase2-identity-registration. [Reviewable PR #3](https://github.com/vistait2018/ai-movie-platform/pull/3) is open, not merged. [GitHub run 41193643965](https://github.com/vistait2018/ai-movie-platform/actions/runs/41193643965) confirmed both required quality and containers successful; canonical image build, runtime Alembic upgrade and metadata check passed. This closes canonical-build verification; local registry DNS remains an environment limitation only. Documentation evidence is committed separately without rewriting feature history. Phase 2 stays in progress; next is Increment 2 login/token/current-user behavior.
