# RBAC and identity ownership — Increment 6

Roadmap 4.0. [Decisions](../architecture/AUTHORIZATION_DECISIONS.md),
[Report 012](../DEVELOPMENT_REPORT_012.md). Existing tables/seeds are reused;
there is no new migration, role bootstrap or permission-editing API.

## Roles and permissions actually enforced

| Role | Existing seeded permissions |
| --- | --- |
| Visitor | Anonymous; no database role and no private identity access |
| viewer | profile:read, profile:update (own resource) |
| creator | profile:read, profile:update, projects:manage |
| moderator | content:moderate |
| finance_admin | finance:read |
| super_admin | All nine explicitly seeded permissions: profile:read/update, users:read/manage, roles:assign, audit:read, content:moderate, finance:read, projects:manage |

Permissions are the union of explicit current database role-permission links;
there is no implicit role hierarchy, Super Admin wildcard or trust in client/JWT
role claims. A registered account starts with Viewer; adding another role does
not remove Viewer. Unknown permissions/roles default deny. Legacy admin rows are
preserved but inert and nonassignable. Content/project/finance permission names
are recognized by the reusable policy; no media/finance endpoints are delivered.
No payout or financial adjustment permission is invented.

## Endpoints and enforcement

Bearer paths below start at `/api/v1`. Equivalent browser paths start at
`/api/v1/auth/browser`; those use existing HttpOnly cookies and require the existing
CSRF challenge, exact approved Origin/Referer and JSON on every mutation.
Cookies never authorize the bearer adapter; Bearer headers never substitute for
browser cookies. Existing registration/login/action/session routes are preserved.

| Method/path | Required scope |
| --- | --- |
| GET /users/{user_id} | Own profile:read; otherwise explicit users:read plus privileged gate |
| PATCH /users/{user_id} | Own profile:update; otherwise explicit users:manage plus privileged gate |
| GET /users/{user_id}/roles | Same read/ownership rule; returns effective active role codes |
| GET /authorization/roles | roles:assign plus privileged gate; lists the five assignable role codes |
| PUT /users/{user_id}/roles/{role_code} | roles:assign plus privileged gate; add one role |
| DELETE /users/{user_id}/roles/{role_code} | roles:assign plus privileged gate; revoke one role |

PATCH accepts only display_name with existing registration validation. Client
email, password, role, permission and status fields are rejected (422). Roles are
never self-assigned or self-revoked, even by Super Admin. Grants require an active
verified recipient; revocation can remove privileges from a disabled recipient.
The last active verified Super Admin cannot be removed. Idempotent no-op grant/
revoke returns 204 and does not revoke newly issued grants again.

Each actual role change atomically revokes all recipient families, refresh
credentials and legacy/session grants; the recipient must log in again. The actor
credential is unaffected unless it belongs to the target (self-changes are denied).
SecurityEvent binds actor UUID and validated role code in the event string to
subject_user_id; structured logs contain UUIDs and known codes only. Profile
mutation events also identify the actor. Failures roll back role/profile, audit
and revocation changes together. Role administration uses a fixed transaction
advisory lock plus ordered user locks and authorization rechecks. Mutations share
one expiring IP limiter scope across resource IDs and both adapters; changing a
UUID cannot obtain a fresh per-resource rate-limit budget.

Authentication failures are 401. Authenticated permission/ownership failures are
generic 403, including guessed nonexistent other-user IDs before lookup. An
authorized nonexistent resource is 404. Safeguard conflicts are 409; dependency
failures are sanitized 503. Private responses/errors are no-store. `/auth/me` now
requires profile:read: an active account whose effective profile permission is
removed gets 403. Session status, verification/recovery and logout remain usable
without profile permission to avoid blocking recovery/security operations.

## Privileged MFA boundary

**Privileged administration and cross-owner access work only in development/test.**
Staging/production always deny them until real privileged MFA assurance is
implemented. There is no production override, client flag or fabricated MFA claim.
Own-profile operations work in every environment with normal valid authentication.
These are development foundation endpoints, not production-ready administrator
authentication. Do not deploy by labelling a production service development.

No live Super Admin is seeded or promoted by this increment. Disposable test
databases explicitly provision test role assignments to verify positive paths.
First administrator provisioning must be a separately controlled operator step
alongside privileged MFA, not public registration or a hidden bootstrap endpoint.

## Testing and walkthrough

Run `.\.venv-dev\Scripts\python.exe scripts/run_tests.py` with the existing local
PostgreSQL/Redis services. Tests use uniquely named disposable databases; transport
is mocked and live SMTP forbidden. No production secrets are required by CI.

1. Register and verify two test accounts through the existing workflow.
2. Log in as the first user and obtain its UUID from `/auth/me`. GET/PATCH that
   user's resource succeeds; only display_name changes.
3. GET/PATCH the other user's UUID fails 403; role assignment also fails 403.
4. Repeat through browser login with a fresh CSRF header for PATCH. Missing CSRF
   fails 403 before mutation; own access succeeds and cross-user access fails.
5. Administrator positive paths, role revocation, last-admin preservation,
   rollback, concurrent grants and disabled accounts are covered in disposable
   database tests. Do not promote a real account merely to demonstrate them.

MFA, production administrator enablement, controlled bootstrap, future content/
project ownership and production security acceptance remain Phase 2/future work.
Phase 2 is not complete.
