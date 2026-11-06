# Increment 4 — refresh, session revocation and logout

Roadmap 4.0 unchanged. Implemented on codex/phase2-refresh-sessions. The local API is now verified at migration 0005 with refresh, replay, logout and logout-all acceptance checks passed. See [Report 010](../DEVELOPMENT_REPORT_010.md) for current commit/CI acceptance and the recorded client security policy.

## API contract

All routes use `/api/v1/auth`.

| Route | Request | Successful result |
| --- | --- | --- |
| POST /login | Existing email/password, optional session_mode | Default `access` preserves exactly access_token/token_type/expires_in. Set session_mode=`refresh` to additionally receive session_id, refresh_token and refresh_expires_in. |
| POST /refresh | JSON refresh_token | New access/refresh pair in the same session; old refresh is consumed and previous family access grants revoked atomically. |
| POST /logout | Current Authorization: Bearer access | 204, no body. Linked session and all associated credentials revoked; legacy access-only grants revoke individually. |
| POST /logout-all | Current Authorization: Bearer access | 204; every session and legacy/new grant for that user revoked. Other users remain unaffected. |

Credential-bearing success responses use no-store, and login/refresh also use Pragma: no-cache. Authentication failures return generic 401/WWW-Authenticate; missing or malformed JSON returns sanitized 422; rate limits return 429/Retry-After; database/Redis/signing failures fail closed with generic 503. No cookies authorize these routes. Request inputs use SecretStr; responses exclude credentials from model repr. Never put tokens in URLs, reports, browser persistence, analytics or logs.

Logout is idempotent with the same unexpired signed credential once its session/legacy grant is revoked. A rotation-revoked access credential cannot terminate a still-live successor session. Logout-all requires valid current access and rechecks eligibility under a user lock; repeating it after revocation returns 401. If access is expired, refresh first, then logout and discard local credentials. Suspended/deactivated users cannot renew; deletion cascades credentials. Logout can still safely close an otherwise known disabled account's session.

## Rotation policy and client requirements

Refresh credentials contain 48 random bytes and are stored only as purpose-bound SHA-256 digests. PostgreSQL session/user/credential locks and a unique parent reference enforce one successor per credential. Absolute session lifetime defaults to 30 days; each refresh credential defaults to 7 days and is bounded by original session expiry. Refresh/access lifetimes do not extend that absolute boundary. Access remains the existing short-lived signed JWT, with grant and optional session state checked on every authenticated request.

Consumed credentials are retained for replay detection. Reusing one revokes that entire session and its newest access/refresh credentials, while preserving unrelated devices. **No reuse grace window exists.** Concurrent refresh calls can yield one successful response followed by replay detection; after detection commits, that successful response's credentials are unusable. Serialize refresh operations on each client. If a response is lost and retry reports reuse, discard local credentials and log in again. Do not repeatedly retry the consumed token.

Each refresh-mode login is an independent device family. Existing access-only grants are preserved with NULL session_id; no refresh secret is fabricated for them. Password reset and logout-all revoke all families and legacy grants atomically. The password reset does not activate pending or suspended users. Family deletion cascades its grants, preventing them from reverting to legacy access.

Browser clients should continue access-only mode until the upcoming secure cookie/BFF and CSRF/origin increment, or use strictly ephemeral in-memory credentials. Do not store refresh/access tokens in localStorage/sessionStorage. Flutter Android/iOS may keep access in memory and refresh in OS-backed Keychain/Keystore storage; do not embed a client secret. No Flutter UI or cookie transport is implemented here.

Configuration: APP_REFRESH_TOKEN_SECONDS=604800, APP_REFRESH_SESSION_SECONDS=2592000, APP_SESSION_REQUESTS_PER_WINDOW=30, APP_SESSION_WINDOW_SECONDS=60. Refresh lifetime must exceed access lifetime; absolute session lifetime must cover refresh lifetime. Compose explicitly passes these settings. IP/token digests use expiring Redis counters; no raw credential is stored in Redis. Logout limits use IP identity only.

## Swagger sequence after deployment verification

1. Use an existing verified active test account or the implemented email-verification flow. Keep pending/suspended restrictions intact.
2. POST /login with email/password and session_mode=refresh. Privately retain the returned pair.
3. Authorize with access and call /me (200). POST /refresh with the refresh credential; authorize with the new access and call /me (200). The old access now receives 401.
4. Reuse the old refresh once; expect 401. The successor access and refresh now also receive 401. Login again to obtain a clean family.
5. Login on another device/family; logout the first family (204), repeat logout safely (204), and verify the second family still works. Logout-all from the second family revokes both and any legacy grants.
6. Login again, exercise the existing password-reset flow, and confirm every old access/refresh fails while the new password permits a fresh login. Never publish the secrets from these manual tests.

## Migration, rollback and verification

Revision 0005_refresh_sessions adds auth_sessions/refresh_credentials and a nullable AccessGrant.session_id FK/index. Existing users/grants stay intact. Back up the actual development database and verify the backup before applying it. Never reset existing databases/volumes. Migration upgrade/downgrade/drift tests run only on uniquely named disposable databases; a populated 0004 → 0005 test verifies legacy user/grant preservation.

Downgrade removes refresh-family state and the access/session link. Revoke all affected credentials before any explicitly authorized rollback to prevent still-stored access grants from regaining legacy treatment. No live downgrade is performed. Retention/cleanup and administrative session/device inventory are future work; do not delete consumed credentials while a family can still be active.

The pre-development audit and security decisions were recorded before application edits in [REFRESH_SESSION_DECISIONS.md](../architecture/REFRESH_SESSION_DECISIONS.md). Reference: [RFC 9700 replay detection](https://www.rfc-editor.org/rfc/rfc9700.html#section-4.14), [OWASP session storage guidance](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html).

## Increment 5 browser adapter

The earlier browser restriction described Increment 4. Browser clients can now use [HttpOnly cookie sessions with CSRF protection](BROWSER_SESSIONS.md) on the separate browser router. Existing JSON/Bearer endpoints retain their original contracts for Flutter and API clients. All transports share revocation and strict rotation; no refresh credential is returned to browser JavaScript.
