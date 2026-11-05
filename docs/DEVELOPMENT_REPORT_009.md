# Development report 009 — Phase 2 Increment 3

Current follow-up: **5 November 2026, Mailtrap SMTP**. The original local-outbox implementation/evidence below is retained as history; see the SMTP acceptance section at the end for current results.

31 October 2026 (Africa/Lagos). Official Master Roadmap 4.0 unchanged. Branch codex/phase2-verification-recovery, based on Increment 2. Phase 2 is **not complete**.

## Working features

POST /api/v1/auth/request-verification and /forgot-password return generic 202 responses. POST /api/v1/auth/verify-email redeems a pending account's token; POST /api/v1/auth/reset-password changes an eligible account's Argon2id password and revokes all access grants. Registration now commits its verification action and encrypted durable email message atomically. Existing login, signed tokens and /me remain functional.

Actions use random 256-bit single-use tokens, purpose-bound SHA-256 digests, recipient snapshot binding, bounded expiry and consistent user/action row locks. Resends coalesce within 60 seconds, then replace/invalidate older same-purpose actions. Reset invalidates all outstanding actions. Audits, password/status changes, grant revocation, consumption and encrypted-payload removal share one transaction. Suspended/deactivated users cannot activate or recover; pending users cannot reset passwords to bypass verification. No flow changes roles or automatically logs the user in.

Encrypted PostgreSQL development outbox uses a separate generated Fernet key. Acknowledged CLI access is local/development only; **no HTTP outbox endpoint exists**. EmailDelivery.enqueue is a transaction-bound seam for a future provider/job adapter; no paid service or external mail send occurs. Staging/production refuse development delivery and fail closed until a real adapter is configured.

## Actual results

- Official Windows runner: **122 passed**, zero failed/errors/skipped integration tests, 59.85 seconds on the final logging/docs rerun (earlier 26.95 seconds); one existing Starlette/httpx warning. All previous 86 tests preserved, with 36 new action/outbox cases. The initial expanded run was 111 passed/1 failed due to a new test reading a detached ORM instance; corrected the test's captured UUID and reran successfully.
- Tests exercise verification/login, encrypted/digest storage, expiration/wrong-purpose/incorrect tokens, replay, concurrent single-winner redemption for both purposes, concurrent request coalescing, replacement, generic requests, suspended/deactivated/changed-email restrictions, target/role injection, pending/active status changes, reset/grant revocation, audit rollback, delivery/resend rollback, outbox access/key/environment guards, input redaction and real Redis/fail-closed limits. Existing migration round-trip/drift tests now include revision 0003, in disposable databases only.
- Ruff lint/root formatting (70 files), mypy app/runner, Bandit app/scripts, pip check and uv lock --check passed. Locked addition: cryptography 50.0.2. Dependency advisory check: **No known vulnerabilities found**.
- Backed up live PostgreSQL to ignored .tools/before-email009.dump and verified pg_restore listing. Applied additive **0003_auth_actions_outbox** only; Alembic current is head and check reports no new operations. Original migrations and existing database/cache data preserved.
- Local canonical Docker build was blocked by registry DNS resolution. A temporary ignored Dockerfile extending the existing verified runtime image built successfully with the locked new dependency; canonical Dockerfile remains unchanged for independent GitHub verification. Refreshed API/worker only. All five containers healthy; PostgreSQL 337d44f5482f and Redis 746130f84b28 unchanged.
- Live Docker Swagger-contract smoke passed all eight requested steps: registration 202, pending login 401, CLI outbox retrieval, verification 200, login/me 200, recovery 202, reset 200, old password/access 401, new password login 200; both replay attempts 400. /docs, /health and /ready returned 200; no outbox OpenAPI route. No credentials printed. Removed only the two smoke-created exports; one local smoke user remains.
- Local .env backed up under ignored .tools before adding only APP_EMAIL_OUTBOX_KEY. Existing database/signing credentials unchanged; neither key nor local messages/backups/environments/caches belong in source. Historical local/example database-password match reported in 008 remains a separate owner-authorized rotation item.

## Files and commands

Inspected reports 007–008, authentication architecture/status, identity models/migrations, registration/login/dependencies/rate limits, settings, schema, test fixtures, Docker/Compose and CI. Created action/outbox migration, delivery/action services, action router, restricted dev_outbox CLI, action integration tests, Swagger walkthrough and this report. Updated registration to queue atomically, schemas/settings/rate limits/router inclusion, models, example/Compose key, lock, test fixture/migration-head expectation and proportionate project/architecture records. Preserved unrelated New Text Document.txt.

```powershell
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
.\.venv-dev\Scripts\python.exe -m alembic upgrade head
.\.venv-dev\Scripts\python.exe -m alembic check
docker compose build api worker
docker build --pull=false -f .tools/Dockerfile.email009-local -t ai-movie-school-api -t ai-movie-school-worker .
docker compose up -d --no-deps --no-build --pull never --wait --wait-timeout 120 api worker
docker compose exec -T api alembic current
docker compose exec -T api alembic check
```

Docker commands used the installed per-user executable with approved access. The fallback build used a local base tag ai-movie-school-base-email009; ignored .tools/smoke_email009.py ran HTTP assertions and actual app.dev_outbox CLI exports. Test databases and Redis cleanup are limited to uniquely created test artifacts; no live downgrade, database reset or volume deletion occurred.

## Review, limitations and handover

At start, PR #3 (registration, base main) and PR #4 (login, base #3 branch) were both OPEN and unmerged. Increment 3 is stacked on #4; merge order must remain #3, then retarget/recheck #4 against main, then retarget/recheck this increment. No merge, force push, direct main push or production deployment is performed here. Actual commit/PR/check evidence follows after remote verification.

Use [the practical Swagger walkthrough](development/EMAIL_VERIFICATION_RECOVERY.md) for the requested register → local outbox → verify → login → me → recover → reset → old-password rejection flow. Real email transport/retries, post-reset notifications, managed key rotation, retention cleanup and abuse/load tuning remain unimplemented. The raw local export is sensitive and must be removed after inspection. Refresh rotation, logout, browser cookie/CSRF sessions, MFA, full RBAC and complete Phase 2 acceptance remain outstanding. Next application slice: refresh/logout and session security, followed by authorization/MFA; integrate real email delivery before production acceptance. Roadmap 4.0 remains unchanged.

## Verified GitHub evidence and ChatGPT handover

Implementation commit `0ad23e2e35f459221e85019c0a6b9c691f7a1845`. [PR #5](https://github.com/vistait2018/ai-movie-platform/pull/5) is OPEN, based on codex/phase2-login-authentication. [PR workflow 41230214913](https://github.com/vistait2018/ai-movie-platform/actions/runs/41230214913) confirms both required jobs passed: containers 44 seconds, quality 57 seconds. Canonical image build, runtime upgrade/drift checks and real-service suite succeeded on Ubuntu. This independently resolves canonical-build verification despite the local registry DNS limitation. PR #3 and #4 were rechecked and remain OPEN/unmerged; no foundation-order merge was bypassed.

Handover for ChatGPT: Roadmap 4.0 unchanged; Phase 1 accepted, Phase 2 in progress. Increments 1–3 deliver pending Viewer registration, signed access login/me, email verification and password recovery with encrypted durable local delivery. Reset revokes all existing grants; single-use/expiry/purpose/account restrictions and transactional rollback are tested. Windows suite: 122 passed, preserving the previous 86, zero skips; required GitHub jobs passed. Follow development/EMAIL_VERIFICATION_RECOVERY.md for the eight-step Swagger/CLI workflow. Production mail delivery is not configured; development outbox never has an HTTP route and refuses staging/production. Next feature work is refresh/logout/session security, then RBAC/MFA; production delivery/retention/key operations also remain. Respect PR merge order #3 -> #4 -> #5 and retarget/recheck each dependent PR against protected main after prerequisites merge. Do not mark Phase 2 complete.

## Mailtrap SMTP follow-up — 5 November 2026

Branch codex/phase2-mailtrap-smtp, based on unmerged verification/recovery PR #5. Reviewed current registration/login/JWT/action schemas, SMTP/worker configuration, migration 0004, tests and the original report. Existing implementation was preserved; no foundation rebuild or database reset was performed during this continuation.

### Completed checks and actual evidence

- Full official Windows runner: **144 passed**, zero failures/errors/skipped integrations, 54.81 seconds; one existing Starlette/httpx deprecation warning. Preserves all 122 prior cases and adds 22 SMTP cases. Ruff lint/format, app/runner mypy, Bandit, pip check and current pip-audit passed (no known vulnerabilities). No new dependency was needed for standard-library SMTP.
- Mock SMTP tests verify STARTTLS before login with certificate verification, sanitized transport failures, production sandbox rejection, commit-before-send, metadata-only persistence, retry/rotation, lease protection, ineligible jobs, rollback and full verification/reset/grant revocation. Automated tests explicitly forbid unmocked SMTP; CI needs no Mailtrap secrets.
- Additive 0004_smtp_deliveries is applied locally, Alembic current=head and check reports no drift. The pre-migration backup .tools/before-smtp009-20261105.dump was created and pg_restore listing verified in the earlier implementation session. Revisions 0001–0003 are unchanged. Existing PostgreSQL/Redis container IDs remain 337d44f5482f / 746130f84b28; all five services are healthy. Only API/worker were refreshed earlier to load SMTP settings. No volumes were reset/deleted.
- Canonical local build encountered registry DNS lookup failure. An ignored temporary Dockerfile extending the verified cached runtime built successfully; canonical Dockerfile is unchanged. Independent canonical CI verification is required below. The production image still excludes pytest.
- Sandbox SMTP connection, certificate-verified STARTTLS and authentication succeeded. Verification job **41d47c92-147a-43cf-a1f8-ac5dd971a0c1** was submitted once at **2026-11-05 08:05:33 UTC**. Reset job **845ca7a8-1948-4aa3-83ce-16856cc09719** was submitted once at **08:13:43 UTC**. Job metadata is evidence of submission only.
- **Both inbox captures are owner-confirmed**: the owner reported receiving the matching verification and reset messages; redemption of each supplied token succeeded. Automated Mailtrap UI inspection was blocked at Cloudflare/sign-in and no inbox API token was configured. The report does not claim an automated inbox inspection or screenshot.
- Complete live HTTP workflow passed: registration 202, pending login 401, verify-email 200, login/me 200, forgot-password 202, reset-password 200, old-password login 401, previous-access /me 401, new-password login/new-access /me 200, reset replay 400. PostgreSQL independently confirmed **one previous grant revoked**. The workflow used actual SMTP messages and account state, not the development activation shortcut.
- No passwords/action/access tokens appear in application or test-report output. Private temporary test credentials were removed after success; sanitized evidence remains under ignored .tools/mailtrap-smoke-evidence.json. Sandbox messages and the local smoke account are preserved. User-provided token values are not reproduced in this report or source.
- SMTP values initially supplied in tracked .env.example were backed up under ignored .tools and moved to ignored .env. Only email settings were reconciled; existing database/signing secrets were preserved. The example was restored to empty credentials and its sender-variable typo corrected. Do not commit .env, backups, message exports, environments or caches. Unrelated New Text Document.txt remains excluded.

### Implemented delivery contract

EmailDelivery now selects outbox / mailtrap_sandbox / smtp. SMTP requires verified STARTTLS and timeouts and refuses sandbox mode/recognized sandbox hosts in production. The API transaction queues action/job metadata only; the existing worker polls with beat every ten seconds. Under user/action/job locks it rotates the digest and leases the job, commits, then sends the in-memory token. No raw SMTP token is stored in PostgreSQL or broker arguments. Failures use bounded backoff (up to five eligible attempts) and generic audit/error codes. Ambiguous SMTP acknowledgment can cause duplicate mail and token rotation; exactly-once delivery is not claimed. Legacy encrypted development outbox behavior remains intact.

### Commands and remaining acceptance

Re-executed official scripts/run_tests.py; Ruff check/format; app and runner mypy; Bandit app/scripts; pip check/pip-audit; Alembic current/check; Git status/diff and existing PR/authentication/service checks. All used the existing .venv-dev. No new infrastructure implementation or live paid provider was introduced. [Practical Mailtrap Swagger walkthrough](development/MAILTRAP_SANDBOX.md).

Current live acceptance passed using owner-confirmed sandbox capture. PRs #3, #4 and #5 remain open and dependent; the SMTP PR must target codex/phase2-verification-recovery and preserve that foundation-first order. Commit/PR/CI outcomes will be recorded after verification; no merge is authorized here. Phase 2 remains incomplete: refresh/logout, cookie/CSRF sessions, full RBAC, MFA, production provider acceptance, managed keys/retention, post-reset notifications and broader abuse/load verification remain outstanding.
