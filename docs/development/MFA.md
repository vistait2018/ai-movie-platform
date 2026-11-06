# Privileged MFA — Increment 7 review candidate

Roadmap 4.0. Not accepted; Phase 2 remains incomplete. No production privilege
enablement or production bootstrap is provided by this increment.

## Configuration and migration

PyOTP 2.10.0 is locked. Supply `APP_MFA_ENCRYPTION_KEY` as a dedicated generated
Fernet key through protected configuration. There is no default or fallback to
the JWT/outbox key. Preserve this key securely alongside encrypted backups;
losing it prevents authenticator verification. Key rotation automation is outside
this increment. Do not commit keys or put credentials in command arguments.

`0006_privileged_mfa` adds only `mfa_factors`, `mfa_recovery_codes` and
`mfa_assurances`. Existing tables/data and migrations 0001–0005 are unchanged.
Back up and verify a restorable development database backup **before** applying
the migration to an existing database. No existing database migration or
deployment is part of this review delivery. Downgrade locks all new tables and
refuses if any is populated; only empty-schema round trips are allowed.
Credential retirement needs separate review. Deleting an old session cannot
delete a confirmed factor; its enrollment-session reference becomes null.

## API contract

Bearer MFA routes use `/api/v1/auth`. Browser equivalents use
`/api/v1/auth/browser`, existing HttpOnly cookies and CSRF/origin enforcement.
Cookies cannot authorize bearer routes. All responses, including errors, are
no-store. Authentication requires an active verified account and valid access
grant/session. Legacy access-only grants retain ordinary access but cannot enroll
or acquire MFA assurance: sign in with `session_mode: "refresh"` instead.

| POST suffix | JSON body | Result |
| --- | --- | --- |
| `/mfa/enroll` | `password` | 200: one-time `secret` and `provisioning_uri` |
| `/mfa/confirm` | `password`, `code` | 200: eight recovery codes, issued once |
| `/mfa/verify` | `password`, `code` | 204: recent session assurance |
| `/mfa/disable` | `password`, `code` | 204: remove factor/codes/assurances; revoke all account credentials |
| `/users/{user_id}/mfa/reset` | none | 204: authorized administrator resets another account |

Never log/store enrollment responses or recovery codes in application logs or
analytics. Enrollment expires after 600 seconds and confirmation is bound to the
enrolling server-side session. Confirmation rechecks the password and TOTP before
enabling the factor; it also establishes recent assurance. A pending enrollment
can be replaced only after expiry. Enabled factors cannot be overwritten.

Verification accepts a fresh six-digit TOTP or an unused recovery code, plus the
current password. PyOTP verification permits one 30-second step of clock skew
each way. The actual highest accepted counter is persisted under the account
row lock. Concurrent/replayed OTPs and recovery codes are rejected. Recovery
codes have 256 random bits each, stored only as domain/account-bound SHA-256
digests. No recovery-code retrieval endpoint exists. Disable and re-enroll to
replace codes, following the role-retirement rules below.

Each MFA mutation shares fixed Redis scopes across both adapters and endpoints:
five requests per account and IP per 300 seconds by default, including password
reauthentication. Redis failure denies the operation. Bounded settings allow
deployment tuning; changing UUIDs/endpoints cannot obtain a fresh account budget.
Malformed inputs are sanitized 422; invalid proof/ownership is 403, unavailable
configuration/dependencies 503, safeguards/enrollment conflicts 409.

## Session assurance and privileged operations

Assurance is stored in PostgreSQL against the authenticated `AuthSession`, with
a fixed 300-second expiry (bounded configuration, maximum 600 seconds), capped
by session expiry. It is not a JWT claim, request header or client flag. Refresh
rotation retains the session and does not touch assurance timestamps. Another
login/device has no assurance until independently verified. Revoked/expired
grants, sessions and accounts fail authentication; assurance also independently
checks session validity. Logout, password reset and actual role changes use the
existing revocation machinery. Factor retirement deletes assurances by cascade.

Every privileged policy check requires database permission and recent assurance
in development/test. Cross-owner access and role administration use this policy;
mutation checks repeat after existing advisory/account locks and credential
revalidation. Staging/production still deny privileged operations unconditionally,
even after valid MFA. There is no enablement setting. Explicit acceptance and a
separate reviewed production-enablement change are required.

Existing role assignment/removal routes remain the administrator-provisioning
API. They prohibit self-modification and unknown/legacy roles; recipients must
be active, verified and have confirmed MFA before receiving moderator,
finance_admin or super_admin. Actual changes revoke all recipient sessions and
record actor/subject/role. Last-active-verified-super-admin removal is protected.

Self-disable needs password plus fresh TOTP/recovery proof. Administrator reset
needs `roles:assign` plus recent assurance, rejects self-reset and uses the same
role/account locks. **Privileged roles must be removed before either reset or
disable.** Thus losing every factor/code for the only administrator requires a
separately reviewed operator recovery procedure; there is no emergency bypass.
Delegated permissions remain database-controlled; reset revokes all target grants.

## Initial administrator

There is no bootstrap HTTP endpoint or public administrator registration.
An operator with protected OS/database/configuration access can run:

```powershell
.\.venv-dev\Scripts\python.exe -m app.admin_bootstrap --user-id <existing-user-uuid> --confirm-initial-development-admin
```

This command permits development only; the underlying service permits disposable
test execution too. It denies staging/production before opening a database.
It shares the Redis MFA account budget, prompts privately for the existing
account password and a fresh TOTP, and requires active verified status and a
confirmed factor. Recovery codes cannot bootstrap an administrator. No password
or secret is supplied in arguments or printed.

Bootstrap serializes on the existing role-administration advisory lock, refuses
any existing super-admin assignment (including inactive accounts), checks a
permanent provisioning audit marker, grants the existing role and atomically
revokes all old credentials. Re-login and verify MFA afterwards. Further admins
must be provisioned by an authorized administrator through the existing role API.
No live administrator has been provisioned for this delivery.

## Validation

Use the existing official runner with PostgreSQL/Redis:
`.\.venv-dev\Scripts\python.exe scripts/run_tests.py`.
Tests use newly created disposable databases, real migration upgrades, isolated
keys and mocked mail transport. See Report 013 for actual results and limits.
