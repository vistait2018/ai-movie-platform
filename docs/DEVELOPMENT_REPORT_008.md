# Development report 008 — Phase 2 Increment 2

31 October 2026 · Official Master Roadmap 4.0 unchanged · branch codex/phase2-login-authentication.

## Delivered and boundaries

- POST /api/v1/auth/login: existing Argon2id verification, generic credential/account rejection, active verified users only, signed short-lived bearer access, atomic grant/audit/last-login persistence.
- GET /api/v1/auth/me: reusable HTTPBearer dependency; strict JWT signature, allowlisted algorithm, issuer/audience/expiry/subject/identifier/type/purpose validation; PostgreSQL ownership, grant expiration/revocation and current account eligibility checked every request. Returns only safe profile fields/current roles.
- Redis independent IP/account login counters, configurable default 10/60 seconds, hashed keys, TTL, Retry-After and fail-closed behavior. Unknown accounts perform dummy Argon2id work. Operational events and public errors exclude credentials.
- Additive migration 0002_access_grants over unchanged 0001_identity_core. Stores grant metadata only, never bearer credentials. Existing registration/security controls remain functional.
- Explicitly guarded local fixture verification command; refuses staging/production, unconfirmed use, remote database hosts and non-pending accounts. Production email verification remains absent.
- Shared bearer contract for browser/Flutter Android/iOS, OpenAPI security/response documentation, in-memory access storage and no-store responses. Instruction 008 signed-access decision updates the earlier opaque-access proposal without changing Roadmap 4.0.

This is access authentication only. No refresh rotation, logout/revoke API, production email verification, recovery, cookie/CSRF adapter, privileged MFA or full RBAC/session management is claimed. Phase 2 is not complete. Until MFA and remaining security work pass, production authentication acceptance is not claimed.

## Actual verification

- Official Windows runner: **86 passed**, zero failures/errors/skipped tests, 11.50 seconds. One existing Starlette/httpx deprecation warning. Preserves all 45 Increment 1 tests (including the original 24) and adds 41 authentication cases.
- PostgreSQL-backed tests cover correct/incorrect/unknown credentials, pending/suspended/deactivated users, safe profile, audit persistence and redaction, atomic rollback on audit failure, subject/grant mismatch, expired/manipulated/missing tokens, wrong issuer/audience/subject/jti/type/purpose, missing expiry, unsigned algorithm, future validity, lifetime/type checks, database revocation/account changes, missing/weak configuration and development guards.
- Real Redis tests exercise independent account/IP throttling, TTL and infrastructure fail-closed behavior. Tests remove only their uniquely created keys. Migration upgrade/downgrade/upgrade and metadata comparison run on disposable databases only.
- Ruff lint and root formatting passed (61 files formatted/checked); mypy passed for 25 app files and separately the official runner; Bandit app/scripts passed; pip check passed; uv lock --check passed. PyJWT 2.15.1 locked. Dependency advisory audit: **No known vulnerabilities found**.
- Canonical Dockerfile build succeeded for API/worker; both refreshed using --no-deps --no-build. Live Alembic current: 0002_access_grants (head); check: No new upgrade operations detected.
- Live Docker HTTP smoke: /health and /ready 200; registration 202; pending login 401; explicitly prepared local verified login and /me 200; missing/revoked access 401; Swagger HTTPBearer schema present. Password/token generated only in memory, never displayed or saved. One local smoke account retained with its grant revoked.
- All five containers healthy. PostgreSQL ID 337d44f5482f and Redis ID 746130f84b28 unchanged. Redis PONG; Celery inspect ping reported one node online. No PostgreSQL/Redis volume deletion/reset/recreation.
- Before additive live migration: PostgreSQL custom-format dump saved under ignored .tools/before-auth008.dump; pg_restore --list succeeded. Before adding the local signing key, .env was backed up under ignored .tools; existing credentials unchanged. Only APP_ACCESS_SIGNING_KEY was added. The generated signing key is excluded from source/report output. A pre-existing local database/example password match is documented below.

## Inspected and changed files

Inspected authentication plan, Phase 2 records/report 007, identity models/migration, registration/schema/passwords, database session/settings/rate limits, existing test fixtures/tests, pyproject/lock, Dockerfile/Compose, .env.example, ignore rules and GitHub workflow. No infrastructure redesign or paid service introduced.

Created app/core/tokens.py, app/services/authentication.py, app/api/dependencies.py, app/dev_verify.py, migrations/versions/0002_access_grants.py, tests/test_authentication.py, docs/development/AUTHENTICATION.md and this report.

Modified auth router/schema/settings, identity model, existing rate-limit module, Compose signing-key environment mapping, example settings, pyproject/uv.lock, test-isolation fixture, migration-head expectation, README and proportionate architecture/status documents. The original migration is unchanged. Unrelated New Text Document.txt is preserved/excluded. Local .env, backups, smoke script, environments/caches remain ignored and excluded.

## Executed commands

```powershell
git status --short
git switch -c codex/phase2-login-authentication
$env:UV_PROJECT_ENVIRONMENT='.venv-dev'
.\.venv-dev\Scripts\uv.exe lock --python .venv-dev\Scripts\python.exe --cache-dir .uv-cache
.\.venv-dev\Scripts\uv.exe sync --locked --python .venv-dev\Scripts\python.exe --cache-dir .uv-cache
.\.venv-dev\Scripts\python.exe scripts/run_tests.py
.\.venv-dev\Scripts\python.exe -m ruff check .
.\.venv-dev\Scripts\python.exe -m ruff format --check .
.\.venv-dev\Scripts\python.exe -m mypy
.\.venv-dev\Scripts\python.exe -m mypy scripts/run_tests.py
.\.venv-dev\Scripts\python.exe -m bandit -r app scripts -q
.\.venv-dev\Scripts\python.exe -m pip check
.\.venv-dev\Scripts\python.exe -m pip_audit --cache-dir .tools/pip-audit-cache --timeout 15 --progress-spinner off
.\.venv-dev\Scripts\uv.exe lock --check --offline --python .venv-dev\Scripts\python.exe --cache-dir .uv-cache
docker compose build api worker
docker compose up -d --no-deps --no-build --pull never --wait --wait-timeout 120 api worker
docker compose exec -T api alembic upgrade head
docker compose exec -T api alembic current
docker compose exec -T api alembic check
docker compose exec -T redis redis-cli ping
docker compose exec -T worker celery -A app.workers.celery_app:celery_app inspect ping
git diff --check
```

Docker commands used the installed per-user Docker executable with approved access. The development key-generation block is documented in development/AUTHENTICATION.md; it outputs no key. Ignored .tools/smoke_auth008.py performed the HTTP assertions. The existing working .venv-dev is preserved. Initial implicit uv environment selection encountered the already-inaccessible .venv; explicit UV_PROJECT_ENVIRONMENT and Python path resolved dependency installation without deleting source. Initial sandbox dependency-audit network access was denied; the approved network retry succeeded. An initial Bandit false-positive on the public JWT purpose label was resolved by using the unambiguous purpose claim; final scans pass without suppressing it.

## GitHub and handover

Increment 1 PR #3 was still open at implementation start. This increment is stacked on that branch, preserving valid registration work. No direct main push, force push, merge, production deployment, paid AI request or financial transaction. Commit/PR and required-check evidence are recorded below after GitHub verification.

Next application task: production email-verification actions and durable mocked delivery, followed by recovery, refresh/logout and authorization/MFA increments. Keep pending accounts blocked and preserve the current signed-access contract. Full Phase 2 acceptance remains outstanding.

## Credential review correction

The exact-value scan detected that the existing local PostgreSQL password matches the pre-existing committed .env.example value (confirmed against the parent revision). A command-handling error allowed the first feature commit to proceed after that failed scan. Corrected the current example and two pre-existing documentation/test sample occurrences to a distinct explicit placeholder and enforced scan failure handling before further pushes. The new signing key was never committed/displayed. Local database credentials were not changed and volumes remain intact. Earlier public history still contains the old example; owner-authorized local password rotation is recommended separately. No history rewrite was performed.
