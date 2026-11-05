# Development Report 012 — RBAC and resource ownership

5 November 2026 · Official Roadmap 4.0 · Phase 2 Increment 6.

## Scope and audit

Base accepted Increment 5 commit 3121c3a26b9b681e599c279c701ff9d0e3208b70,
branch codex/phase2-rbac-ownership, dependent on PR #8. Verified open merge chain
#3 → #4 → #5 → #6 → #7 → #8. No merges, forced pushes or history changes.
Unrelated New Text Document.txt is preserved/excluded. Roadmap 4.0 unchanged.

Inspected identity/role/permission/grant/session models, registration seed usage,
0001–0005 migrations, auth dependencies/routes, browser CSRF, session/recovery
services, roles/architecture/status documents and security/integration fixtures.
[Necessary decisions](architecture/AUTHORIZATION_DECISIONS.md) were recorded
before editing application code. No models, migrations or dependencies changed.

## Implementation

Reused the five roadmap authenticated roles: viewer, creator, moderator,
finance_admin and super_admin; Visitor is anonymous. Existing legacy admin data
is preserved but cannot authorize or be assigned through new routes. Nine existing
permission codes are recognized; unknown roles/permissions default deny. Permission
sets come from current PostgreSQL mappings, never request/JWT claims. No implicit
wildcard/hierarchy or new business permission is added.

Added shared bearer/browser profile read/update, effective-role read, assignable
role catalogue and individual grant/revoke routes. Profile ownership is backed by
the authenticated user UUID and database checks. Cross-owner access requires
explicit users:read/manage permission. Profile updates allow only display_name;
mass assignment is rejected. Existing /auth/me now enforces profile:read. Existing
authentication, registration, cookies, CSRF, rotation and recovery remain intact.

**Privileged operations are development/test only.** Staging/production deny role
administration and cross-owner access until real privileged MFA is implemented;
there is no client flag/configuration bypass. No live privileged account is
created. This is a documented security boundary, not a claim that MFA exists.

Role changes require roles:assign, forbid self-modification and legacy/unknown
roles, reject grants to disabled/unverified recipients and protect the last active
verified Super Admin. Revocation can remove roles from inactive accounts without
blocking cleanup merely because another account is the only active administrator.
Actual changes atomically revoke recipient families/refresh credentials/all access
grants and record actor/subject/role audit identity. Idempotent no-ops preserve
fresh grants. Role mutations serialize on a transaction advisory lock plus ordered
user locks; all mutations reauthenticate and recheck permissions after locking.
Preliminary authorization prevents unauthorized callers from locking targets.

The new mutation limiter shares a fixed scope across UUIDs/adapters to prevent
per-resource budget bypass, using existing Redis counters/timeouts and settings.
Existing auth limiter semantics are unchanged. Authentication errors are 401;
authorization/ownership failures generic 403; authorized missing resources 404;
last-admin conflicts 409; failures sanitized 503. New private successes/errors
are no-store; browser mutations retain router-wide CSRF/origin enforcement.

## Changed files

New: app/services/authorization.py, app/api/authorization.py, app/schemas/users.py,
tests/test_authorization.py, docs/architecture/AUTHORIZATION_DECISIONS.md,
docs/development/AUTHORIZATION.md and this report.

Modified: app/api/auth.py (/me permission dependency); app/main.py (route inclusion);
app/core/logging.py (safe actor/subject/role metadata); app/core/browser_middleware.py
(private resource cache headers); app/services/rate_limits.py (optional named scope
and authorization mutation dependency); relevant role/architecture/project records.
No existing auth service is replaced, and no financial/media feature is introduced.

## Tests and security evidence

Final official command `.\.venv-dev\Scripts\python.exe scripts/run_tests.py`: **270 passed**,
zero failures/errors/skipped integrations, **101.44 seconds**; one existing
Starlette/httpx warning. All 225 baseline tests are preserved; 45 focused cases
were added. Earlier 268-test runs passed before the two final hardening cases.

Coverage includes authorized own/privileged reads/updates, generic IDOR failures
for existent/nonexistent UUIDs, every non-admin role boundary, assignment/revocation,
self-escalation, unknown/legacy roles, last-admin preservation, disabled recipients,
disabled/revoked actors, signed-but-ignored role claims, role-less users, browser
CSRF/transport isolation, stale credential/permission checks, rollback, concurrent
idempotent grants, audit sanitization, read-versus-write permission separation,
production MFA denial and real Redis throttling across changing resource IDs.

An early last-admin test counted other administrator fixtures retained by prior
cases; its disposable-database setup now temporarily deactivates and restores
only those fixtures. Bandit initially identified a type-narrowing assert; replaced
with an explicit 401 check. Neither issue was hidden or suppressed.

Ruff lint/format, application mypy (39 files), runner mypy, Bandit, pip check and
uv lock --check ran. Fresh pip_audit returned **No known vulnerabilities found**.
Final Ruff lint/format, app/runner mypy and Bandit passed. Exact-value scans
against local database/JWT/outbox/SMTP secrets passed across tracked/intended new
files; no credentials were printed. Final staged/committed artifact checks follow. Dependencies and
lock unchanged; uv uses the existing ignored workspace cache.

## Database and local services

No migration is needed/applied. Alembic current: 0005_refresh_sessions (head);
check: No new upgrade operations detected. Existing data, migration history, ignored
.env and PostgreSQL/Redis volumes are preserved. No reset/downgrade or implicit
role bootstrap. No backup-before-migration operation is triggered because there
is no live migration.

Compose config --quiet passed. Canonical local build failed at registry metadata
resolution (ghcr.io DNS), before compilation. The existing cached locked runtime
was rebuilt with only reviewed app/migration/config files in a unique ignored
context. API/worker only refreshed with --no-deps --no-build --pull never --wait;
canonical independent GitHub build remains mandatory. Normalized SHA-256 over
all app/migration Python, Alembic config and locked dependency files matches the
running image. All five services are healthy: API 7d5699b8fba0, worker d5de2005674c,
PostgreSQL 337d44f5482f, Redis 746130f84b28 and storage bb88aa802c8a. Existing
PostgreSQL/Redis identities are unchanged. Redis PONG and Celery ping (one node
online) passed.

Live smoke at **2026-11-05T18:29:28.359825+00:00** passed readiness/health 200,
verified ordinary account profile GET/PATCH 200, no-store, cross-user GET/PATCH 403,
guessed other-user UUID 403, privileged escalation 403, mass assignment 422, browser
own-profile GET/PATCH 200, missing CSRF 403, browser cross-user 403 and logout-all
204 followed by old bearer 401. Two scoped local-outbox fixtures used the existing
registration service plus actual HTTP verification; no SMTP send or provider/.env
change. Fixture grants were revoked; account/audit history remains. No live
privileged account was provisioned. Sanitized evidence remains ignored in
.tools/rbac012-live-evidence.json. Administrator positive cases were exercised
through real HTTP test clients against disposable PostgreSQL, not live user data.

## Git and acceptance

Commit SHA, dependent PR URL and actual quality/container CI results are pending
execution. Do not mark Increment 6 accepted until those checks are verified.
Never merge automatically. Required order: #3 → #4 → #5 → #6 → #7 → #8 → Increment 6.

## Handover and limitations

Use [the endpoint/matrix contract](development/AUTHORIZATION.md). Scope is identity
resource ownership only; movie/project/financial ownership belongs to later
features. Moderator/finance/project permission names are recognized without
claiming their feature endpoints exist. Privileged production operations remain
blocked pending MFA and controlled first-administrator provisioning. Frontend/
mobile UI, privileged MFA and production acceptance remain incomplete.
**Do not mark Phase 2 complete.**

Reference reviewed: [OWASP authorization guidance](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html).
