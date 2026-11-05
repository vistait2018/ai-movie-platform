# Development report 010 — Phase 2 Increment 4

5 November 2026, Africa/Lagos. Official Roadmap 4.0 unchanged. Branch **codex/phase2-refresh-sessions**. **Local and live acceptance verified; commit/PR/CI completion pending below. Phase 2 is not complete.**

## 1. Executive summary

Implemented opt-in refresh-mode login, rotating digest-only refresh credentials, database session families, strict reuse revocation, logout/logout-all, access/session checks and password-reset revocation. Default login JSON remains compatible with the existing exact-response tests. Local PostgreSQL integration tests, fresh advisory audit, live additive migration and deployed endpoint acceptance now pass. The prior approval-review usage blocker is resolved; commit/PR/CI outcomes are recorded below as completed.

## 2. Baseline and pre-development audit

Baseline HEAD f16a62ae5239e8072ea29c812375a31ff0a8001a, 144 passing tests, SMTP PR #6 OPEN. Remote and PR audit confirmed #3 registration → #4 login → #5 verification/recovery → #6 SMTP dependencies remain open/unmerged. Created the new branch directly from #6. Inspected auth architecture/status/Report 009; identity/grant/action models, revisions 0001–0004, JWT/password handling, routes/dependencies, reset revocation, logging, Redis controls, worker and tests. Existing refresh/session/logout functionality was absent. The unrelated New Text Document.txt is preserved and excluded. [Decisions](architecture/REFRESH_SESSION_DECISIONS.md) were written **before application code edits**.

## 3. Architecture and security decisions

- Keep existing access JWT validation/issuer/audience/subject/expiry rules and Argon2id. New AuthSession and RefreshCredential metadata is PostgreSQL-authoritative; raw refresh credentials (48 random bytes) are never stored. Unique digest/parent constraints and User → family → credential row locks serialize operations.
- Default login preserves its original three fields. Explicit session_mode=refresh returns session_id, refresh_token and refresh_expires_in in addition to access fields. Default lifetimes: 7-day refresh credential, 30-day absolute session, existing short access lifetime. Successors and access are capped by original family expiry.
- Strict replay policy: a consumed token revokes that family and its latest credentials. Concurrent requests can produce one 200 then rejection/revocation; the winning credentials cannot remain usable after reuse commits. There is no grace window. Other devices remain independent. Clients must serialize refresh and reauthenticate after ambiguous/lost-response reuse.
- Browser cookie/BFF and CSRF/origin security remain the next increment. Browser access-only behavior is retained; persistent browser token storage is not introduced. Flutter contracts support independent families and OS-backed refresh storage without implementing mobile UI.

## 4. Files changed

Created app/services/sessions.py, app/api/sessions.py, migrations/versions/0005_refresh_sessions.py, tests/test_sessions.py, this report, docs/development/SESSIONS.md and docs/architecture/REFRESH_SESSION_DECISIONS.md. Modified settings/schema/models, login/auth dependency, password-reset revocation, route inclusion, logging allowlist, reusable rate limiting, Compose/example settings, test isolation and only the existing migration-head expectation. Relevant README, authentication/database architecture, security/API/testing and project status records are updated. No dependency/version change, source deletion, secret overwrite, roadmap edit or unrelated user-file change.

## 5. Migration details

0005 adds auth_sessions, refresh_credentials, constraints/indexes and nullable indexed AccessGrant.session_id with ON DELETE CASCADE. Legacy users/grants remain intact and do not receive fabricated refresh secrets. Existing migrations are unchanged. Disposable database upgrade/downgrade/head/drift checks pass; populated 0004 → 0005 preservation is tested. **The actual development database is now at 0005_refresh_sessions (head)**, applied only after a new verified backup. Host and container Alembic current/check pass with no drift. Earlier 0004-only status described the paused implementation session and is superseded by the verified continuation below. Downgrade discards family state and can unlink still-stored grants; revoke all affected credentials before any separately authorized rollback. No live downgrade/reset/volume deletion is performed.

## 6. API specifications

| Endpoint | Contract |
| --- | --- |
| POST /api/v1/auth/login | Existing default unchanged; session_mode=refresh opts into access/refresh family issuance. |
| POST /api/v1/auth/refresh | JSON refresh_token; atomic rotation, no-store response; generic 401 for invalid/expired/revoked/reused/ineligible credentials. |
| POST /api/v1/auth/logout | Valid signed access Bearer; revoke family or legacy grant; 204; safe repeat with the same unexpired credential. Rotation-revoked access cannot kill a live successor. |
| POST /api/v1/auth/logout-all | Currently valid Bearer, rechecked under user lock; 204 revokes every family and legacy grant for that user. |

No cookie authentication is enabled. Existing register/verify/login/me/forgot/reset behavior is preserved. Rate limits return 429/Retry-After; Redis/database/signing failures fail closed with sanitized 503. Missing/invalid authentication returns 401/WWW-Authenticate. [Detailed API/client contract and walkthrough](development/SESSIONS.md).

## 7. Rotation and revocation behavior

Successful refresh consumes the old credential, revokes prior family access, issues one successor and audits atomically. Reuse is committed before returning a generic rejection and invalidates all family credentials. Account-status/deletion/expiry/session ownership checks apply on refresh and /me. Session deletion cascades linked grants so they never become legacy. Logout-all/password reset revoke every family and all legacy grants under the shared user lock; reset still requires a valid single-use eligible action and never auto-logs in or activates a user. Failed transactions roll back consumption/issuance/revocation/audits together.

## 8. Test results

Baseline regression with new migration/code: **144 passed**, no failures/skips (42.01s). Expanded suite: **176 passed**, no failures/errors/skips, 63.98s; one existing Starlette/httpx warning. The final full suite including populated 0004 → 0005 legacy preservation passed **177 tests**, zero failures/errors/skips, in **52.38s**, with the same one existing warning. This preserves all 144 and adds 33 cases. Cases cover compatibility, hashes, rotation, wrong/expired/revoked/consumed credentials, strict concurrency, multiple devices, logout/repeat/legacy/logout-all, reset revocation and reset rollback, disabled/deleted users, family deletion/expiry bounds, unique successor constraint, database failures for login/refresh/logout/logout-all, sanitized audit/input, Redis throttling and failure behavior. No test was removed or weakened; the prior migration-head assertion advances to revision 0005.

## 9. Security verification

Ruff lint/format (82 files), app mypy (33 files), runner mypy, Bandit app/scripts, pip check and uv lock --check passed on continuation. Fresh pip-audit executed successfully: **No known vulnerabilities found**. The previous approval-review usage failure is resolved; prior results are not substituted for this fresh check. Exact-value scans against local database/JWT/outbox/SMTP secrets and excluded artifacts pass; example SMTP credentials remain empty. No raw credentials/headers are logged, and only UUID/event metadata is allowlisted. Final staged review follows before commit.

## 10. Backup, deployment, live results and CI

Created `.tools/before-refresh010-acfc70a65dcd4129b2772ae50333031e.dump` (25,910 bytes) before migration. Verified both archive TOC and full SQL extraction using pg_restore to /dev/null without executing SQL. Host-copy SHA-256: F00702C53058D2B41C7A5D62908FFB1CF666E9F34219F33DE034CC87BC4A7A30. Backup metadata remains in ignored .tools/refresh010-backup-record.json; no data/credentials are committed. Applied only additive 0005; current=head and drift check passed on host and API container.

Reused the existing successfully built Increment 4 cached-base runtime: compared normalized SHA-256 over app/migration source, Alembic config and locked dependency files against the image, and verified API/worker image IDs match. No redundant build or source rewrite was required. Earlier canonical local build encountered registry DNS failure; independent canonical GitHub build remains mandatory. Refreshed **only API/worker** with --no-deps --no-build --pull never --wait. All five services healthy; PostgreSQL 337d44f5482f and Redis 746130f84b28 are unchanged. Redis PONG and worker inspect ping (one node online) passed; data/volumes preserved.

Live HTTP smoke ran against the updated API at 2026-11-05 14:24:46 UTC. It created a scoped development fixture through the existing registration service in local-outbox mode and then verified it through the actual HTTP verify-email endpoint (200), without SMTP sends or any activation shortcut. The fixture does not change .env/provider settings. Confirmed /health and /ready 200, new OpenAPI routes present, default legacy login's exact three-field response, refresh 200, old-access rejection, strict reuse 401 with successor invalidated, unrelated device still usable, logout/repeat 204, logout-all 204 across devices and legacy grants, two concurrent refresh requests returning [200,401] with the winner subsequently rejected, and fresh login 200 after revocation. Cleanup revoked all **six** fixture sessions and **nine** access grants; no password/token was displayed or persisted. Sanitized proof is in ignored .tools/refresh010-live-evidence.json; the fixture account/audit history is retained.

Continuation official suite: **177 passed**, zero failures/errors/skipped integrations, **101.38s**, one existing warning. Existing 144 tests are preserved. Runtime smoke, security checks and advisory audit passed independently. New CI evidence is recorded below after the dependent PR run.

## 11. Known issues and blockers

The approval-review usage blocker and fresh advisory/deployment gates are resolved. The original local canonical registry DNS limitation is documented; GitHub's canonical container build must pass before final acceptance. No user data, volumes or secrets were reset/overwritten, and no approval gate was bypassed. Full Phase 2 still needs browser cookie/BFF/CSRF security, RBAC/MFA and production acceptance; these are outside this increment. One pre-existing Starlette/httpx test warning remains. No current local test failure is outstanding.

## 12. Git commit and PR information

Baseline **f16a62ae5239e8072ea29c812375a31ff0a8001a** and the dedicated branch are preserved. Source commit, PR URL and current CI run will be recorded below once created/verified. Intended PR base remains **codex/phase2-mailtrap-smtp** (#6). Existing #6 success is not used as this increment's CI evidence. Preserve #3 → #4 → #5 → #6 → Increment 4; never merge automatically or force-push.

## 13. Acceptance checklist

- [x] Pre-development audit/security decisions documented before code.
- [x] Refresh rotation, strict replay/concurrency behavior and family/account revocation implemented and locally tested.
- [x] Logout/logout-all and password-reset family revocation implemented and locally tested.
- [x] All 144 baseline tests preserved; expanded local security tests pass.
- [x] Additive migration/test isolation and legacy data compatibility designed; existing revisions preserved.
- [x] Local lint/type/security/package/lock checks passed; documentation prepared.
- [x] Final populated-migration test run: 177 passed, zero failures/skips.
- [x] Fresh advisory check executed successfully: no known vulnerabilities.
- [x] Fresh backup verified; 0005 applied; matching runtime deployed; all services and live endpoints verified.
- [x] Working-source credential/artifact and diff scan passed.
- [ ] Intended stage/commit/push and dependent PR completed.
- [ ] Required GitHub quality/containers passed for this branch.

## 14. Next increment and handover

Finish the remaining Git/CI acceptance gates; local/live/advisory requirements are now verified. Do not repeat working feature implementation. Then deliver the planned browser cookie/BFF security, CSRF/origin enforcement and client session handling without exposing browser refresh credentials. Remaining full Phase 2 work also includes RBAC/ownership, privileged MFA, production email acceptance and operational security/retention. Phase 2 and Increment 4 acceptance are **not complete** while these gates remain unverified.

Commands run: existing .venv-dev Python scripts/run_tests.py; Ruff check/format; app/runner mypy; Bandit; pip check; uv lock --check; Alembic current; Compose config/build; ignored cached runtime build. The earlier fresh-audit attempt was blocked before execution; the continuation reran it successfully. Current continuation also executed pg_dump/pg_restore verification, backup copy/hash, additive upgrade/current/check, image source comparison, API/worker refresh, service checks and live HTTP acceptance smoke. No .env value was printed or changed.
