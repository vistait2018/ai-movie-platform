# Phase 2 account administration and browser authentication

Local review candidate, 6 November 2026. [Verification report](../DEVELOPMENT_REPORT_014.md).
Increment 7 and Phase 2 are not accepted. Production privileged access remains disabled.

## Account status API

`PATCH /api/v1/users/{user_id}/status` accepts only
`{"status":"pending|active|suspended|deactivated"}` (one literal value).
Browser equivalent: `PATCH /api/v1/auth/browser/users/{user_id}/status`.
Status reads use the existing authorized profile endpoints.

Requires explicit current `users:manage`, valid authentication and recent
session-bound MFA. Browser mutations additionally require the existing CSRF
challenge and approved Origin. Staging/production always deny privileged access.
There is no self-status administration. Permission checks happen before target
lookup and repeat after the shared role-administration advisory lock, ordered user
locks and credential revalidation. The existing shared mutation limiter applies.

Active requires verified email; pending requires unverified email. Administration
cannot verify an email address. Reactivating a privileged account requires confirmed
MFA; remove its privileged roles first if factor recovery is needed. Suspending or
deactivating the last active verified Super Admin is refused. No roles are erased
by a status change, and no new permission or migration is introduced.

Every actual change atomically revokes target access/refresh/session credentials,
consumes outstanding verification/reset actions, and records actor/subject/status.
Reactivation does not resurrect old credentials or email tokens. An unverified
account resumed to pending must request fresh verification. No-op updates preserve
fresh sessions. Failed transactions preserve the status, credentials and actions.

Success returns the existing profile model with current status. Failures: 401 for
invalid/revoked authentication, generic 403 for unauthorized targets, 404 for an
authorized missing resource, 409 for safeguards, 422 for malformed/extra fields,
429 for throttling and sanitized 503 for dependency failures. All are no-store.

## Browser interface

The reviewed source serves `/account` with local Jinja2 HTML, CSS and JavaScript:
registration, sign-in, verification/resend, forgotten-password/reset, profile
read/update, session renewal/logout, MFA enrollment/confirmation/recovery/disable,
and authorized status administration. Existing bearer APIs remain available for
future Flutter clients; native apps belong to Phase 23, broader dashboards to Phase 5.

The browser uses existing HttpOnly cookies, same-origin JSON requests and fresh
CSRF challenges for browser mutations. Tokens are never placed in URLs or browser
storage. Email tokens are pasted into password-type fields. Mutations are serialized
in the page; authentication errors do not automatically replay a mutation or rotate
refresh credentials. Use Renew session explicitly when access expires.

Enrollment secrets/recovery codes appear only at initial issuance; save them
securely before hiding them. The page clears password/code fields after submission
and sensitive outputs on logout/navigation. Rendering uses textContent, not HTML
injection. A page-specific CSP permits only local scripts/styles/connections, with
no inline scripts, external fonts, analytics or third-party QR services. Other API
CSP policies remain unchanged. All account HTML/assets are no-store.
Every form uses a POST fallback to a refused handler, so disabling JavaScript
cannot put passwords, OTPs or email tokens in a GET URL.

The configured approved browser origin must match the origin serving the page.
The existing running containers have not been updated, so their `/account` route
does not represent this local source yet. Deployment/migration need separate review.

## Email and operational boundaries

The existing durable SMTP worker, STARTTLS validation, bounded retries and generic
verification/recovery responses are reused. No SMTP credentials/provider settings
were changed, and no real messages were sent for this review. Existing Mailtrap
acceptance remains historical evidence; fresh automated tests mock external mail.
Production forbids sandbox/outbox delivery and needs approved real SMTP configuration.

Backup and full restore into a disposable database were verified before any possible
existing-database migration. No such migration was applied. See Report 014 for the
archive fingerprint, current schema, container build blocker and owner-review gates.
