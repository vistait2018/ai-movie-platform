# Phase 2 authentication implementation plan

Roadmap 4.0 · Instruction 003 · 30 October 2026. **Proposed design only; no authentication code, schema, migration or dependency added by this instruction.** Shared web, Flutter Android and Flutter iOS scope is preserved. Review technical choices before implementation; outstanding Phase 0 commercial decisions remain separate.

## Instruction 008 decision — 31 October 2026

The owner explicitly requires signed access tokens. Increment 2 supersedes the original opaque-access proposal for the delivered access slice: PyJWT HS256, configurable 10-minute lifetime, strict claims and PostgreSQL access_grants for immediate revocation/account-state checks. Refresh and full browser cookie sessions remain proposed. Both current web and Flutter clients use bearer headers with access held in memory; cookies never authenticate. The future cookie adapter must implement CSRF/origin requirements before use. A guarded local fixture verifier does not implement production email verification. See [implemented contract](../development/AUTHENTICATION.md). The original proposal below describes future work where not superseded here.

## Instruction 009 implemented increment

Verification/reset use purpose-bound SHA-256 digests of random 256-bit single-use credentials, user/action row locks, recipient snapshots, expiry and atomic audit/account/grant changes. Additive 0003_auth_actions_outbox stores actions plus Fernet-encrypted durable development delivery. EmailDelivery.enqueue is the transaction-bound adapter seam; no provider network send occurs inside authentication transactions. Local inspection requires an acknowledged development CLI and local database; no HTTP outbox endpoint exists. Development delivery refuses staging/production, which fail closed until a real adapter is integrated. [Working endpoints and Swagger walkthrough](../development/EMAIL_VERIFICATION_RECOVERY.md). Refresh/logout, cookie/CSRF sessions, MFA and full RBAC remain future work.

## Architecture proposal
One FastAPI identity/authorization service with PostgreSQL as authority. Use first-party stateful sessions and opaque random credentials rather than implementing a custom OAuth authorization server. API, web route handlers and background services share authorization/ownership checks. Redis supplies bounded rate-limit counters, not the only source of account/session revocation truth.

| Client | Proposed transport | Storage and protection |
| --- | --- | --- |
| Same-origin Jinja2 web | Opaque session cookie; backend resolves hashed credential to session and user | Production `__Host-session`, Secure, HttpOnly, Path=/, no Domain, SameSite=Lax; synchronizer CSRF token plus Origin validation on unsafe requests, including login/logout; no auth credentials in browser localStorage/sessionStorage |
| Flutter Android/iOS | Short-lived opaque bearer access token plus rotating opaque refresh token | Access token held in memory where possible; refresh token in OS-backed Keychain/Keystore secure storage; HTTPS only outside isolated development; no embedded client secret |
| Future third-party login | Established OIDC provider with authorization code + PKCE | External system browser on mobile, exact approved redirects; no implicit or password grant; separate reviewed integration, not an additional Phase 2 scope commitment |

Generate at least 256-bit random session/action credentials using a cryptographic RNG. Store only SHA-256 digests of random tokens; use Argon2id for passwords, not fast hashes. Pick a maintained hashing library and benchmark its cost on deployment hardware against current OWASP guidance. JWTs are not required by the roadmap; opaque access credentials provide straightforward immediate revocation with one authoritative lookup. Revisit signed tokens only through a documented architecture decision.

Use separate web and mobile login/session adapters over the same credential-verification service, not a caller-supplied role or entitlement. OpenAPI describes each transport; browser cookies must not accidentally authorize bearer-only APIs. Configure exact allowed origins and credential policy; avoid wildcard credentialed CORS.

## Proposed endpoint contract
- `POST /api/v1/auth/register`: normalized unique email and validated password; create pending user/profile and verification action, default Viewer only; generic public responses where needed to avoid account enumeration.
- `POST /api/v1/auth/verify-email`, `/resend-verification`: single-use expiring action; rate-limited; verified account activation.
- `POST /api/v1/auth/web/login` and `/mobile/login`: shared validation and throttling, transport-specific issuance; generic bad-credential errors and comparable failure work for missing users.
- `POST /api/v1/auth/mobile/refresh`: atomic refresh rotation, consumed-token reuse detection and family revocation; client must serialize refresh attempts. Define retry/replay behavior explicitly and test concurrent attempts before release.
- `POST /api/v1/auth/logout`, `/logout-all`: revoke current/all applicable server sessions and credentials; web clears cookie with matching attributes; mobile removes secure local credentials.
- `GET /api/v1/auth/me`, `PATCH /api/v1/users/me`: authenticated profile access, allowed field list; no role/status edits via profile payload.
- `POST /api/v1/auth/forgot-password`, `/reset-password`, `/change-password`: enumeration-resistant recovery, one-use digest-only tokens, password rehash and session revocation on reset; current credential/step-up checks for sensitive changes.
- MFA enrollment/confirmation/challenge/recovery endpoints: privileged accounts cannot obtain full privileged access before MFA completion; sessions distinguish pending challenge from fully authenticated state.

Endpoint names are implementation proposals. Keep request schemas bounded and response models explicit. Return 401 for invalid authentication, 403 for forbidden authorization/CSRF and 429 for enforced limits without leaking account existence. Do not log passwords, raw cookies/tokens, recovery links, TOTP secrets or authorization headers.

## Minimum identity schema and migrations
Use SQLAlchemy 2.x and Alembic with PostgreSQL integration tests. UUID primary keys, UTC timestamps, explicit constraints and indexes. This is only the Phase 3 identity subset required by Phase 2, not completion of the whole financial/media schema.

| Migration proposal | Tables / essential constraints |
| --- | --- |
| `0001_identity_core` | `users`: id, normalized email unique, password_hash, status (pending/active/suspended/deactivated), verified_at, security_version, created/updated timestamps. `user_profiles`: user_id unique/FK, display name and minimal non-financial profile fields. `creator_profiles`: optional one-to-one lightweight profile/status only; complete onboarding/KYC remains Phase 18/20. `roles`, `permissions`, `user_roles`, `role_permissions`: unique codes and association keys, FKs, assigned_by/at audit context. Seed explicit role/permission codes; no seeded login credentials. |
| `0002_auth_sessions` | `auth_sessions`: user FK, channel, created/last_seen, absolute/idle expiry, revoked_at, MFA assurance and security_version. `session_credentials`: session FK, token kind (web/access/refresh), unique digest, expiry, consumed/revoked fields, refresh family/parent relationships. Atomic row locks/conditional transitions prevent duplicate refresh use. |
| `0003_auth_security` | `account_action_tokens`: user, purpose, unique digest, expiry, used/revoked timestamps. `mfa_factors`: user, factor type, encrypted secret/key version, verification state; `mfa_recovery_codes`: digest and used_at. `security_events`: event code, actor/subject, outcome, correlation ID, minimized metadata. `email_outbox`: durable dispatch reference/status and encrypted short-lived delivery payload if it must contain a raw one-use link. |

No raw authentication credential should be persisted as ordinary plaintext in database/outbox/logs. Random-token digests alone cannot reconstruct an email link: use authenticated encryption and managed key separation for any queued secret delivery payload, then remove it after send/expiry. Password hashes remain one-way. MFA secrets require encryption because verification needs access to them; recovery codes are digest-only. Key provisioning and SMTP/provider settings must be explicit and tested with mocks before real delivery.

Migration verification: upgrade empty isolated PostgreSQL, inspect constraints/seed roles, test upgrade from previous revision, test rollback only on disposable data, and document forward recovery for releases. Never apply schema experiments to existing persistent developer volumes without a reviewed migration command. Alembic revision names above are planned, not files that already exist.

## Roles and lifecycle rules
Visitor is anonymous, not a database role. Viewer, Creator, Moderator, Finance Administrator and Super Admin are explicit scoped roles. Self-registration never grants privileged roles; creator intent/profile is separate from publication approval. Role/permission assignment requires an authorized audited workflow; initial Super Admin bootstrap uses an explicit interactive management command, no default password and no public bootstrap endpoint. Sensitive financial controls remain mandatory even for Super Admin.

Email verification precedes full activated-account access. Suspension/deactivation, password reset and security-sensitive role changes invalidate relevant sessions immediately through authoritative state/security_version. Profile ownership and resource status are checked server-side. Privileged MFA and audited recovery are Phase 2 requirements, not deferred to the admin dashboard phase.

## Session and abuse policy proposals needing review
Proposed starting values: mobile access expiry 10 minutes, refresh family absolute lifetime 30 days; web idle timeout 30 minutes and absolute lifetime 12 hours, shorter privileged sessions. These are engineering proposals, not approved owner policy. Specify remember-me behavior, mobile reinstall/lost-device revocation and session/device-list privacy before coding.

Configure per-IP and per-account rate limits, progressive backoff, bounded hash work and generic errors. Approve actual thresholds after abuse/load tests; do not hardcode arbitrary commercial/security commitments. Sensitive auth flows fail safely if required throttling infrastructure is unavailable. MFA reset, email/password changes and privilege elevation require reauthentication and audit. Recovery cannot bypass suspension or privileged-account safeguards.

## Implementation sequence and acceptance evidence
1. Approve transport/session decisions, TTL/rate-limit proposals, email activation and privileged recovery policy. Record unresolved Phase 0 age/privacy/retention constraints.
2. Add reviewed SQLAlchemy/Alembic and hashing dependencies with lock update; implement DB configuration/session boundary, migration scaffolding and identity-core migration/fixtures.
3. Add password verification/hashing service, pending-account registration and minimal profiles; prove uniqueness under concurrency and non-escalating role seeds.
4. Implement action tokens and mocked durable email delivery; verify activation, resend, recovery expiry/single use and enumeration resistance.
5. Implement web/mobile login, session issuance, request authentication and atomic mobile refresh rotation; enforce CSRF, cookie flags and logout/revocation.
6. Add role/permission and ownership dependencies, user lifecycle/profile updates, sensitive-change reauthentication and audit events.
7. Add privileged MFA enrollment/challenge/recovery, encrypted secrets and explicit secure Super Admin bootstrap.
8. Extend Redis throttling, abuse/error handling and operational logs; test infrastructure failures without exposing secrets.
9. Run migration/API/PostgreSQL integration tests, web CSRF/cookie tests and mobile-token contract tests; document OpenAPI and setup changes, then verify required CI before Phase 2 acceptance.

Required regression cases: duplicate email/races, malformed input, correct/incorrect/dummy password paths, disabled/unverified users, expired/reused action and refresh tokens, concurrent refresh, logout-all/password-reset revocation, session fixation, CSRF/origin failures, profile mass assignment, every role boundary, privileged MFA bypass attempts, reset abuse, rate limits, missing Redis, audit/log redaction and account privacy. Flutter apps are not implemented in Phase 2; API contracts must support them from the beginning. The phase is complete only when its roadmap permission/security acceptance criteria pass.

## Primary references checked
- [OWASP Password Storage](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html)
- [OWASP Session Management](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html)
- [OWASP Authentication](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html)
- [RFC 9700 — OAuth security best practice](https://www.rfc-editor.org/rfc/rfc9700.html)
- [RFC 8252 — native apps](https://www.rfc-editor.org/rfc/rfc8252.html)

Opaque first-party session design is this project's proposal; the OAuth RFCs guide refresh-token threat handling and any future OIDC/native integration rather than claiming the current API is an OAuth authorization server.

## Ready-to-implement handover — 31 October 2026
Phase 1 is accepted after protected-main enforcement and authorized credential reconciliation. Begin actual application delivery with the existing stack. First feature slice: users/roles/profile migration plus secure registration and verification contracts; then login/session behavior shared by responsive web and Flutter Android/iOS clients. Implement and test each slice before expanding, using PRs and existing CI. Do not rebuild infrastructure or introduce live paid providers for these features. This document remains a plan; no authentication implementation is included in the Phase 1 acceptance change.
