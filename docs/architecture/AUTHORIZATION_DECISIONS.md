# Increment 6 — authorization decisions

5 November 2026, Roadmap 4.0. Recorded before application changes. Based on
accepted Increment 5 (3121c3a), branch codex/phase2-rbac-ownership, dependent on PR #8.
Verified open merge chain #3 → #4 → #5 → #6 → #7 → #8. Preserve unrelated
New Text Document.txt and existing authentication/migrations.

Existing 0001 seeds viewer, creator, moderator, finance_admin, super_admin and a
legacy admin row. Visitor is anonymous, not a grantable role. No new roles or
permissions are needed. Keep legacy admin data but make that unroadmapped role
inert/nonassignable. Effective roles/permissions are read from PostgreSQL on each
operation; never from request fields or JWT role claims. Known permission codes
are explicit, unknown codes deny. No implicit Super Admin wildcard or hierarchy.
Users retain Viewer through additive role grants; no commercial/media features
or invented permission grants are added.

Add own profile read/update using existing profile:read/profile:update; only
display_name may change. Cross-owner profile reads/updates require explicit
users:read/users:manage respectively and privileged assurance. Add role inventory
and assignment/revocation through roles:assign, with no self-role changes, no
assignment to disabled/unverified accounts, no legacy/unknown roles and no removal
of the last active verified Super Admin. Never bootstrap an administrator or
alter existing user roles automatically.

The roadmap requires privileged MFA, which is not implemented. New privileged
operations are therefore **development/test only** and fail closed in staging/
production until a real MFA assurance service replaces this gate. There is no
setting or client header to bypass the production gate. Local development still
requires a currently valid existing credential plus database permission. This
increment delivers RBAC/ownership, not production administrator authentication.
No live privileged account is provisioned as part of acceptance.

Both bearer and CSRF-protected browser adapters call the same authorization
services. Existing /auth/me gains profile:read enforcement (security correction:
an active account with no effective profile permission now gets 403); browser
session metadata and recovery/logout stay available independently of profile
permissions. Authentication/account/grant/family failures remain 401; authenticated
authorization failures are generic 403, including inaccessible/unknown other-user
IDs before any existence disclosure. Unknown authorized resources use 404.

Mutations serialize on a database-wide role-administration advisory transaction
lock, then lock actor/target users in UUID order. Profile mutations lock the actor/
target users in the same order. Recheck credential eligibility/revocation and
permissions after acquiring locks, before writes, to prevent stale authorization.
Role administration serializes last-admin checks; role changes atomically revoke
the target's existing sessions/grants and record actor/subject/role IDs in safe
structured audit metadata plus existing SecurityEvent rows. Transaction failure
rolls back both roles and revocation. No schema migration is necessary.

Scope: existing identity resources only. MFA, production privileged enablement,
content/project ownership, finance controls and full Phase 2 acceptance remain
future work. Do not mark Phase 2 complete.
