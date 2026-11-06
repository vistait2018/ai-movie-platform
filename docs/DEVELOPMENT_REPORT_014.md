# Development Report 014 â€” Phase 2 verification and remaining gates

6 November 2026 Â· Official Roadmap 4.0 Â· **Owner-review candidate only. Phase 2 NOT ACCEPTED.**

## Baseline and scope

Report 013 is the preserved baseline: Increment 7 MFA/provisioning is implemented
locally but not accepted. Accepted Increments 1â€“6 remain based on PR #9 at
`4130a147e1df16d800ab4c8053e84dbf585f5a65`. Work remains uncommitted on
`codex/phase2-privileged-mfa`. This follow-up adds account lifecycle administration,
a browser identity interface and verification evidence. The official roadmap and
phase numbering are unchanged. No merge, push, new PR or deployment occurred.

## Official Phase 2 comparison

| Official requirement | Current local implementation and evidence | Remaining acceptance gate |
| --- | --- | --- |
| Registration, sign-in, sign-out, recovery | Existing shared services plus browser forms; integration suite and real Chrome sign-in/sign-out pass | Operational/owner review |
| Password hashing, email verification, sessions | Existing Argon2id, single-use actions, SMTP worker/outbox and session validation preserved; real browser verification passed | Production mail configuration and delivery sign-off |
| Viewer, Creator, Moderator, Finance, Super Admin permissions | Current PostgreSQL mappings, explicit default-deny policy, scoped roles and audited assignment preserved | Production privileged access remains deliberately disabled; media/finance features belong to later phases |
| Profile editing, user status, suspension | Existing own-profile editing plus new shared status administration; lifecycle, revocation, verification and last-admin tests pass | Owner review and deployment gate |
| Privileged MFA | Report 013 TOTP/recovery/provisioning, session assurance and recent-MFA privileged enforcement preserved; regressions pass | Increment 7 acceptance, key custody/recovery procedures, separately reviewed production enablement |
| Mobile-compatible authentication APIs | Existing bearer JSON/OpenAPI contracts retained; browser adapter uses same services | Native application UI is Phase 23, not a Phase 2 completion requirement |
| Renewal, revocation, logout | Existing rotation/reuse detection and logout preserved; suspension/deactivation now revoke credentials and actions atomically | Operational/owner review |
| Rate limiting and audit | Redis account/IP controls and fail-closed behavior preserved; status uses existing fixed mutation budget; actor/subject/status audit added | Production threshold/operations sign-off |
| Service/API authorization boundaries | Permission/MFA checks before target lookup and after advisory/user locks; status service enforces lifecycle safeguards | Production enablement remains blocked |
| Automated unauthorized-access tests | Full real PostgreSQL/Redis suite passes; added status and UI cases, plus real-browser smoke | Independent CI for uncommitted candidate remains unavailable until authorized delivery |

The completion criterion requires secure documented shared authentication APIs for
web/future mobile clients and passing permission tests. That is locally evidenced;
it does not establish production or owner acceptance. A minimal Jinja2 browser
interface is now included. Broader dashboards, viewer/player UI and native apps
remain in their official later phases. No unrelated media/financial features were added.

## Implemented account lifecycle

New `PATCH /api/v1/users/{user_id}/status` and browser equivalent
`PATCH /api/v1/auth/browser/users/{user_id}/status` accept only status:
pending, active, suspended or deactivated. Requires current `users:manage`, recent
session-bound MFA and existing throttling; browser mutations also require CSRF/
Origin. Staging/production remain unconditionally denied. Self-administration is
forbidden. Unknown target existence is hidden before authorization.

Mutations reuse the role-administration advisory lock and ordered user locks,
then reauthenticate/recheck authorization. Active requires verified email;
pending cannot erase verification. Privileged reactivation requires confirmed MFA.
The last active verified Super Admin cannot be suspended/deactivated. No-op updates
preserve fresh credentials. Actual changes atomically revoke all target credentials,
consume outstanding email actions and audit actor/subject/status. Reactivation
restores neither old sessions nor old verification/reset tokens. Rollback and
concurrent mutual-suspension tests pass. No new migration is needed for status.

## Browser and email

`/account` serves Jinja2 HTML and local CSS/JS with registration, sign-in,
verification/resend, recovery/reset, profile editing, explicit session renewal,
logout, MFA enrollment/confirmation/verification/recovery/disable and authorized
status administration. It uses existing APIs and HttpOnly cookies; no bearer or
refresh token is placed in browser storage. Password/code fields are cleared after
submission. One-time MFA outputs clear on logout/navigation. Mutations are
serialized and never automatically replayed on authentication errors. Text rendering
uses textContent; account-only CSP allows local assets/connections without inline
scripts or third-party dependencies. Existing API CSP/no-store/transport isolation
remain intact. Every form has a refused POST fallback; unavailable JavaScript cannot
put passwords, OTPs or email tokens in a GET URL. Jinja2 3.1.6 is the only added
dependency since Report 013.

Real installed Chrome verification passed on an ephemeral loopback test server
and a newly created disposable database: email confirmation, login, profile read/
update with HTML-injection resistance, refresh, MFA enrollment/confirmation/recovery,
logout, input/output clearing, absence of browser storage and mobile-width layout.
The final browser rerun also verified JavaScript-disabled submissions use POST and
receive 405 without credentials entering the URL.
No persistent application was deployed; the temporary server/database were removed.
The smoke helper and Playwright installation remain ignored under .tools.

Existing durable SMTP, verified STARTTLS, worker retries and generic account-action
responses are reused. No SMTP/provider settings changed and no real external message
was sent. Automated SMTP tests use mocks; the browser used encrypted disposable
outbox data. Prior Mailtrap live acceptance remains historical Report 009 evidence.
Production rejects sandbox/outbox delivery and requires approved real SMTP setup.

## Database backup, restore and migration status

Before any possible existing-database migration, a full custom-format pg_dump was
created and restored with pg_restore --exit-on-error into a uniquely named disposable
database. Source/restored revision and user/grant/session/audit counts matched;
source fingerprints before/after were unchanged. The verification database and
container temporary files were removed. The backup is retained only in ignored .tools:

`before-phase2-014-4c500e50f9734f0ea464cc217f2affec.dump` â€” 38,428 bytes.

SHA-256: `41126ae1e19f78331dbf371d7ad73c138173587bb91ba60377277e0262514230`.

Sanitized evidence: `.tools/phase2-014-backup-evidence.json`.
No backup contents or credentials were printed or staged. Backup/restore is verified,
but **no migration was applied to the existing database**: it remains at
`0005_refresh_sessions`. Report 013's additive `0006_privileged_mfa` remains the
only pending migration. No new migration, reset, downgrade, volume replacement,
live account promotion or .env change was performed. Backup retention/custody and
any later migration command still require the normal reviewed operational workflow.

## Verification results

Official `.\.venv-dev\Scripts\python.exe scripts/run_tests.py`:
**336 passed, 0 failed, 0 skipped**, **187.21 seconds**, real PostgreSQL/Redis.
All 313 Report 013 tests are retained; 23 cases were added (21 status, 2 UI).
One existing Starlette/httpx deprecation warning remains.

Targeted development: 21 initial status/UI cases passed; positive browser status/
CSRF/concurrency follow-up passed; two additional reactivation/email-action cases
passed. Real Chrome smoke passed. The full suite passed on its first follow-up run.
Static checks initially found an unused import, import placement and one long line;
these were corrected without runtime changes. The two UI tests passed again after
cleanup. Final review then hardened the HTML form fallback against credential-bearing
GET requests. The two UI tests and complete Chrome smoke passed again, including
the new no-JavaScript security assertions; backend behavior did not change. No test
was removed, weakened or skipped to obtain a pass.

Ruff lint passes; all 68 tracked/intended Python files have passed formatting checks
(the three cleanup files were checked again). App mypy passes, 45 files; runner
mypy passes, 1 file. Bandit passes. Pip check passes; uv lock --check passes,
90 packages. Node syntax check passes. Fresh approved-network pip-audit reports
**No known vulnerabilities found**. Final exact-secret/whitespace review passed for
all 37 intended changed/new files; the backup is Git-ignored. Original sessions.py
and Roadmap 4.0 match their HEAD
blob hashes; their content is unchanged.

## Container and deployment readiness

Docker Engine 29.8.2 is available. Canonical Compose configuration with .env.example
and the storage profile validates. All five existing services remain running/healthy:
API `7d5699b8fba0`, worker `d5de2005674c`, PostgreSQL `337d44f5482f`, Redis
`746130f84b28`, storage `bb88aa802c8a`. They still run the previously accepted image;
this is not runtime acceptance of the new source. None was restarted or replaced.

The canonical Docker build was attempted as `ai-movie-school:phase2-review-014`.
It failed before compilation, including on the final 6 November retry, while resolving `ghcr.io/astral-sh/uv:0.13.6`:
Docker's resolver could not resolve ghcr.io (getaddrinfow). Docker reported no HTTPS
proxy for the direct connection. No alternate/unlocked build was substituted and
no build-success claim is made. .dockerignore now allowlists only runtime build
inputs, excluding .env, backups, tooling and unrelated files; app templates/assets
are included by the existing COPY app instruction.

**Deployment readiness is conditional, not verified complete.** Resolve registry
DNS, rerun the canonical build, and obtain new-change CI before release review.
Secure MFA-key and real-mail provisioning, reviewed migration execution, and
production operational/security sign-off remain pending. Production privileged
operations must remain denied throughout this process.

## GitHub status

Approved read-only access succeeded and was refreshed on 6 November; ordinary
sandbox access was denied. All PRs
#3 through #9 remain OPEN and preserve the dependent chain. PR #9 head is
`4130a147e1df16d800ab4c8053e84dbf585f5a65`, base `codex/phase2-browser-sessions`.
Both required quality and containers checks are SUCCESS on that head:
[PR #9](https://github.com/vistait2018/ai-movie-platform/pull/9),
[acceptance CI run 42085581716](https://github.com/vistait2018/ai-movie-platform/actions/runs/42085581716).
These checks cover accepted Increment 6, **not the uncommitted local candidate**.
No push or workflow dispatch was performed. Increment 7/new-change CI remains
pending authorized delivery. Never merge automatically. Preserve
#3 â†’ #4 â†’ #5 â†’ #6 â†’ #7 â†’ #8 â†’ #9 â†’ Increment 7 PR.

## Files in this follow-up

Created: app/services/account_status.py; app/api/account_ui.py;
app/templates/account.html; app/static/account.js; app/static/account.css;
tests/test_account_status.py; tests/test_account_ui.py;
docs/development/ACCOUNT_ADMINISTRATION.md; this report.

Modified since Report 013: app/api/authorization.py; app/schemas/users.py;
app/core/browser_middleware.py; app/main.py; pyproject.toml; uv.lock; .dockerignore;
docs/PROJECT_STATUS.md; docs/roadmap/PHASE_STATUS.md;
docs/development/AUTHORIZATION.md. Report 013 and its MFA implementation are retained.
Unrelated New Text Document.txt and ignored credentials/backups/tools are excluded.

## Owner-review status and remaining blockers

- Increment 7 remains implemented locally but unaccepted; no acceptance is inferred.
- Phase 2 is NOT ACCEPTED and is not declared complete.
- Canonical image build is blocked by Docker registry DNS.
- Current uncommitted changes have no independent GitHub CI or PR.
- Production mail/key custody, sole-administrator recovery policy and operational
  sign-off remain pending; no production privileged enablement is authorized.
- The existing database is backed up/restore-verified but intentionally unmigrated;
  no deployment/live new-source smoke test is claimed.

Stop here for owner review. Do not push, merge, deploy or remove the production
privilege gate without the appropriate subsequent authorization and evidence.
