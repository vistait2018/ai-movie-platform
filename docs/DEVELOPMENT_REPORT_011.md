# Development Report 011 — Secure browser sessions and CSRF

5 November 2026 · Official Roadmap 4.0 · Phase 2 Increment 5.

## Scope and audit

Built on accepted Increment 4 commit db7dbb7b64f27a330597e53e8d1962b4389cd572,
branch codex/phase2-browser-sessions. Verified open PR chain #3 registration →
#4 login → #5 verification/recovery → #6 SMTP → #7 refresh sessions. No merges.
Unrelated New Text Document.txt is preserved/excluded. Roadmap 4.0 is unchanged.

Inspected Report 010, project/phase status, authentication architecture, existing
auth/session/action routes and services, JWT/password helpers, models/revisions
0001–0005, fixtures/security tests, settings, Docker/Compose, CI and ignore rules.
[Security decisions](architecture/BROWSER_SESSION_DECISIONS.md) were documented
before application changes. Existing credentials, transactions and revocation
services are reused; no second identity system or new dependency is introduced.

## Implementation and contracts

Added /api/v1/auth/browser GET csrf/session and POST login/refresh/logout/logout-all.
Browser login always creates a fresh existing PostgreSQL family. Access/refresh
are issued only in HttpOnly host-only cookies; no authentication credentials in
response bodies, URLs or JavaScript storage. JSON exposes only authenticated,
session_id/expires_in or user_id/status. Bearer-only endpoints remain unchanged.

Cookies use SameSite=Lax, restricted Path=/api/v1/auth/browser, no Domain,
configured age capped by credential expiry. Staging/production require Secure,
HTTPS origins and explicit deployment hosts; secure cookies use __Secure- names.
Default local HTTP is intentionally insecure-transport development only. Login
fixation is prevented by new families; rotation retains the strict replay policy.
Logout clears matching attributes; expired access requires refresh first.

CSRF challenges have cryptographic nonces, signed expiry, distinct purpose/type/
audience and an HMAC-derived key. They bind to a random HttpOnly bootstrap before
login or current refresh digest afterward. Every unsafe browser request requires
X-CSRF-Token, approved exact Origin or Referer fallback, and application/json.
Login/logout are covered. Binding changes on login/refresh; old challenges fail.
POST/PUT/PATCH/DELETE are protected by the router-wide dependency. Missing/null/
invalid origin, invalid/expired signature and cross-binding reuse fail closed.

Exact credentialed CORS, independent trusted-host validation (including preflight),
no-store on every auth success/error, nosniff, frame denial, no-referrer,
Permissions-Policy and CSP are added. Swagger/ReDoc retain their existing script
support; production/staging add HSTS. Duplicate authentication cookie names fail
closed. Existing login/account/IP throttles and session mutation limits apply;
sanitized errors and existing audit events never record raw secrets.

Reset reuses existing account-wide revocation under the user lock. Old browser
access/refresh and legacy grants cannot restore a reset session. Single-use reset
replay fails; new-password login succeeds. No email provider changes were needed.

## Changed files

New: app/api/browser.py; app/core/browser.py; app/core/browser_middleware.py;
tests/test_browser_sessions.py; this report;
docs/architecture/BROWSER_SESSION_DECISIONS.md;
docs/development/BROWSER_SESSIONS.md.

Updated: app/main.py; app/core/settings.py; .env.example; compose.yaml;
tests/conftest.py (new setting isolation); tests/test_foundation.py (valid deployed
fixture now supplies required secure browser settings, original assertions kept);
README; authentication/session architecture and project/phase records.
No existing auth service/model/migration implementation was replaced.

## Automated verification

Official runner: `.\.venv-dev\Scripts\python.exe scripts/run_tests.py`.
Expanded suite: **225 passed**, zero failures/errors/skipped integrations,
**56.72 seconds** on the first expanded successful run. Preserves all 177 baseline
tests and adds 48 browser/security cases. One pre-existing Starlette/httpx warning.
Final official recheck after tightening preflight Host validation: **225 passed**,
zero failures/skips, **79.79 seconds**. A final isolated header-test fixture change
removes dependence on local .env/database availability; its focused recheck passed
(1 test, 0.45s). No production implementation changed after that full run.

New coverage: cookies/flags/lifetimes, pre-login and authenticated CSRF, all four
unsafe methods, cross-origin/null/suffix/form attacks, signature tampering,
expiration, Referer fallback, fixation, strict concurrent refresh [200,401] and
winner revocation, logout/all, reset and single-use replay, suspended/pending/
deactivated accounts, expired access recovery, bearer isolation/compatibility,
host/CORS/cache/security headers, secret-free captured audits, dependency failure
and throttling. Real PostgreSQL tests use only uniquely named disposable databases;
SMTP is mocked/forbidden by the existing suite isolation.

During development, a new expiry test initially violated the real expiry
constraint; its fixture now moves created_at and expires_at together. A cookie
restoration test initially generated duplicate Path/Domain entries; it now
preserves original scope. These were fixture corrections; checks were not weakened.

Commands passed: Python -m ruff check .; ruff format --check .; mypy (36 app files);
mypy scripts/run_tests.py; bandit -r app scripts -q; pip check; uv lock --check
--python .venv-dev/Scripts/python.exe with UV_PROJECT_ENVIRONMENT=.venv-dev and
UV_CACHE_DIR=.tools/uv-cache. Initial uv default-cache permission failure was
resolved with this workspace cache. Fresh pip_audit --cache-dir
.tools/pip-audit-cache --timeout 15 --progress-spinner off returned **No known
vulnerabilities found**. No lock/dependency changes.

## Database and runtime evidence

No migration is necessary or applied for Increment 5. Alembic current is
0005_refresh_sessions (head); alembic check: No new upgrade operations detected.
Existing revisions and Roadmap V4 are untouched. No live downgrade/reset or volume
operation. The prior verified pre-0005 backup is retained; no new backup gate is
triggered because no migration occurs.

Compose config --quiet passed. Canonical local compose build api worker failed
before compilation at auth.docker.io DNS resolution. A legacy cached-runtime build
initially hit an inaccessible generated cache while packaging the root context.
Resolved local runtime packaging with a unique ignored context containing only
app/migrations/alembic.ini over the existing cached image. Dependencies/lock were
unchanged. Canonical GitHub build remains required independently.

Refreshed API/worker only: compose up -d --no-deps --no-build --pull never --wait
--wait-timeout 120 api worker. Final running-image app/migration/config/lock SHA-256 comparison matched the
reviewed source. Final API 0185b448dbd3 and worker 0dd9a98b79b4 are healthy;
health/readiness 200 and disallowed-Host preflight 400 passed after refresh.
All five services healthy; PostgreSQL 337d44f5482f
and Redis 746130f84b28 remained unchanged. Redis PONG; Celery inspect ping one node
online. No database/cache data or .env was changed.

Live HTTP smoke at **2026-11-05T14:51:54.356804+00:00** passed health/ready 200,
fixture verification 200, browser login/session 200, cookie attributes, bearer
isolation, rotation 200, old-bound CSRF 403, evil-origin logout 403, logout 204 with
cookies cleared, logout-all 204 with legacy bearer revoked, reset/replay 200/400,
retained browser cookies rejected, old password rejected, new login successful.
All **4 fixture families and 6 grants** were revoked afterward. Existing registration
and request_action services used a scoped local outbox and actual HTTP verification/
reset; no activation shortcut, SMTP send or provider configuration change. No raw
credentials persisted or printed. Sanitized proof remains ignored in
.tools/browser011-live-evidence.json; account/audit history retained.

## Git, review and CI

Final source/diff review and exact-value scans against local PostgreSQL, JWT,
outbox and SMTP secrets passed across tracked and intended new files. No ignored
configuration, environment/cache/backup or unrelated file is included. Commit,
dependent PR and actual GitHub Actions results will be recorded after execution. The only intentional unrelated untracked
file is New Text Document.txt. Preserve #3 → #4 → #5 → #6 → #7 → Increment 5.
Never merge automatically or bypass branch protection.

## Limitations and handover

This increment provides a browser API adapter, not a web/Flutter UI or production
deployment. Cookie scope is intentionally limited; future product browser routes
must use this scope or a reviewed BFF. SameSite=Lax requires a same-site deployment;
cross-site third-party-cookie workflows are unsupported. Clients must serialize
refresh across tabs; strict reuse intentionally revokes the winner of a race.
XSS can still act as the user. Production TLS/proxy validation, frontend security,
full RBAC/ownership, privileged MFA, session inventory/retention and production
email/operational acceptance remain. **Do not mark Phase 2 complete.**

[Endpoint contracts and Swagger walkthrough](development/BROWSER_SESSIONS.md).
