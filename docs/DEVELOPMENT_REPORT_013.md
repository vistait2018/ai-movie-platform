# Development Report 013 — Privileged MFA and controlled administrator provisioning

5 November 2026 · Official Roadmap 4.0 · **Local implementation candidate; NOT accepted. Phase 2 INCOMPLETE.**

## Base and delivery boundary

Base: accepted Increment 6, PR #9, HEAD `4130a14` after implementation `e0a7a3f`.
Local branch: `codex/phase2-privileged-mfa`. Work is uncommitted for owner review.
No push, PR creation, merge, deployment or live administrator provisioning occurred.
Preserve merge order #3 → #4 → #5 → #6 → #7 → #8 → #9 → Increment 7 PR.
The earlier dependency/network blocker was recorded before implementation;
PyOTP 2.10.0 now imports in `.venv-dev`, and approved dependency resolution succeeded.
No GitHub/CI verification is claimed for these uncommitted changes; it remains a
future delivery/acceptance requirement after authorized remote delivery.

## Implemented controls

Extracted the existing validated User/AccessGrant/AuthSession authentication context;
`current_user()` retains its return contract and ordinary legacy access support.
New MFA endpoints require a real server-side session and current password.
Enrollment stores an account-bound Fernet ciphertext under a dedicated key, expires
in 600 seconds, and confirms only on its enrolling session with a fresh TOTP.
Secrets/URI are returned only on enrollment. Confirmation returns eight independent
256-bit recovery codes once; PostgreSQL retains only account/domain-bound SHA-256
digests, with atomic consumption. PyOTP permits one 30-second step each way;
the actual accepted counter prevents replay, including forward skew.

MFA operations share Redis IP/account budgets across endpoints/adapters; missing
Redis fails closed. Initial provisioning CLI shares the persistent account budget.
All proof consumption serializes on the existing user lock. Password checks, proof
consumption, assurance, and audit changes participate in transactions; dependency
failures are sanitized. Failure events persist without credentials. Existing
validation redaction, no-store, browser CSRF/origin and transport isolation remain.

Recent assurance is stored in PostgreSQL against AuthSession, expires in 300 seconds
by default (maximum configurable 600), and is capped by session expiry. No client
claim/header can establish assurance. Token rotation does not alter timestamps.
Logout, password reset and actual role changes use existing grant/session revocation;
assurance checks independently reject revoked/expired sessions. Factor retirement
cascades recovery/assurance removal and revokes all target credentials.

Privileged checks require database permissions plus recent session assurance in
development/test, including cross-owner access and role administration. Mutation
checks repeat after existing advisory/user locks and credential revalidation.
Staging/production still deny privileged operations unconditionally, even with MFA;
there is no production enablement switch. Privileged role recipients must be
active/verified and have confirmed MFA. Self-role modification, unknown/legacy roles,
last-active-verified-admin safeguards and atomic revocation/auditing are preserved.

Password plus TOTP/recovery authorizes self-disable. Administrator reset of another
account requires roles:assign plus recent assurance. Both require retirement of
privileged roles first, preserving last-admin protection. The operator-only bootstrap
requires explicit development confirmation, an existing active/verified enrolled
account, password and fresh TOTP (not recovery code). It serializes with role changes,
refuses any existing super-admin assignment including inactive accounts, records a
permanent provisioning marker, and atomically grants the existing role/revokes old
credentials. No public bootstrap, self-promotion or default password was added.

`app/services/sessions.py` remains unchanged: its Git blob hash matches HEAD,
`d0104b1eeddc1ce69453051c6f43b6ab3c0f8cfa`.

## Endpoints and operator interface

POST bearer prefix `/api/v1/auth`, browser prefix `/api/v1/auth/browser`:

- `/mfa/enroll`: password; returns secret/provisioning URI once.
- `/mfa/confirm`: password + TOTP; returns recovery codes once.
- `/mfa/verify`: password + TOTP/recovery; establishes session assurance.
- `/mfa/disable`: password + proof; retires own factor/credentials subject to safeguards.
- `/users/{user_id}/mfa/reset`: recent authorized administrator resets another account.

Existing `/api/v1/users/{user_id}/roles/{role_code}` PUT/DELETE routes remain the
administrator role-provisioning/removal interface; browser equivalents remain.
Operator CLI: `python -m app.admin_bootstrap --user-id <uuid> --confirm-initial-development-admin`.
Passwords/OTP are read with getpass, never command arguments. See [MFA contract](development/MFA.md).

## Migration, data and backup status

Additive `0006_privileged_mfa`, based on `0005_refresh_sessions`, creates only
mfa_factors, mfa_recovery_codes and mfa_assurances. No accepted migrations or
existing table definitions are changed. Deleting an old session nulls the enrollment
reference rather than deleting a confirmed factor. Recovery/assurance records
cascade only with their owning factor/session as appropriate.

Downgrade takes exclusive locks and refuses when any new MFA table is populated;
empty disposable-schema round trips remain supported. No enrolled data is erased.
The existing development database was queried read-only and remains at
**0005_refresh_sessions**. No migration was applied to that database and no database
reset/volume replacement occurred. **No development backup was created in this
review delivery**: backup/restore verification is a mandatory prerequisite before
any future migration of the existing database. Automated upgrades used newly created
disposable databases only, including preservation of preexisting legacy users/grants.
No .env changes, live MFA key provisioning or live privileged account creation occurred.

## Tests and checks

Final official command `.\\.venv-dev\\Scripts\\python.exe scripts/run_tests.py`:
**313 passed, 0 failed, 0 skipped**, **161.67 seconds**, real PostgreSQL/Redis.
One existing Starlette/httpx deprecation warning remains. This is local test
verification, not owner acceptance or production enablement.

Preserved the 270 baseline tests and added 43 focused cases. Existing RBAC test
fixtures use real MFA endpoints rather than bypassing policy; assertions remain.
Session fixtures now receive isolated generated MFA keys. The existing migration
round-trip test expects the new head, retaining upgrade/downgrade/drift assertions.
Coverage includes ciphertext/digest storage, reauthentication, confirmation expiry
and session ownership, replay/skew, concurrent TOTP/recovery consumption, device
isolation, refresh expiry preservation, revocation, environment denial, real Redis
limits/failure, browser CSRF, privilege provisioning/reset/retirement, stale
credentials, rollback, bootstrap concurrency/reuse restrictions and safe migration
retirement/session cleanup.

Development evidence: 33 original session tests, 45 RBAC tests, the first 32 MFA
cases, four added administrator/rollback cases and five added limiter/bootstrap
cases passed in targeted runs. The first full run had **310 passed, 1 failed**:
an unconditional downgrade refusal blocked the preserved empty-schema round-trip.
Fixed the migration, retained data-retirement protection, and updated the stale
expected head from 0005 to 0006. Seven targeted migration/preservation/replay/cleanup
checks then passed. No test was removed, skipped to obtain a pass or weakened.

Ruff lint passed. Whole-directory format checking crashed while traversing inaccessible
untracked local test folders; all **64 tracked/intended Python files** passed explicit
format checking. App mypy passed (43 files); runner mypy passed (1 file). Bandit passed.
Pip check passed; uv lock --check passed (89 packages; only PyOTP added).
Fresh approved-network pip-audit: **No known vulnerabilities found**.
Exact-value scanning against local configured secrets passed for intended files;
no credential values were printed. Final whitespace review passed; final exact-secret
review passed for all 24 intended files. Unrelated/untracked data was excluded.

## Files

Created: app/admin_bootstrap.py; app/api/mfa.py; app/schemas/mfa.py;
app/services/mfa.py; migrations/versions/0006_privileged_mfa.py; tests/test_mfa.py;
docs/development/MFA.md; this report.

Modified: app/api/dependencies.py; app/api/authorization.py;
app/services/authorization.py; app/models/identity.py; app/core/settings.py;
app/main.py; compose.yaml; .env.example; pyproject.toml; uv.lock;
tests/conftest.py; tests/test_sessions.py; tests/test_authorization.py;
tests/test_registration.py; docs/development/AUTHORIZATION.md; docs/PROJECT_STATUS.md.
Unrelated New Text Document.txt is preserved/excluded. Roadmap 4.0 is unchanged.

## Remaining limits and acceptance

Owner review/explicit acceptance is pending. Production privileges/provisioning
remain unavailable. No GitHub checks for these uncommitted changes, canonical
container build, existing-database migration, live smoke test or deployment is
claimed. A dedicated MFA encryption key must be provisioned securely before live
MFA use; managed rotation and recovery-key custody need operational procedures.
TOTP is not phishing-resistant. Losing every factor/recovery code for the only
administrator requires separately reviewed operator recovery; no bypass is provided.
No privileged status/suspension UI/API or web/mobile MFA UI is added here.
Phase 2 still requires remaining account-status/suspension administration and
separate production security/enablement acceptance. **Increment 7 is not accepted
or declared complete; Phase 2 remains incomplete.**
