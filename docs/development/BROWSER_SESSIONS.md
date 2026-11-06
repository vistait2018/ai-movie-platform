# Browser cookie authentication — Increment 5

Roadmap 4.0. This adapter reuses the PostgreSQL families and strict rotation in
[SESSIONS.md](SESSIONS.md). Existing bearer routes remain compatible with Flutter
Android/iOS; cookies never authorize those routes. No frontend is delivered here.

## Endpoints

All paths below start with `/api/v1/auth/browser`.

| Method/path | Contract |
| --- | --- |
| GET /csrf | Returns csrf_token; creates an HttpOnly bootstrap cookie before login. After login binds challenge to the current refresh credential. |
| POST /login | Existing email/password JSON; always creates a new rotating session. Returns authenticated, session_id, expires_in; access/refresh only in HttpOnly cookies. |
| POST /refresh | JSON `{}`; rotates cookies with the existing strict replay policy. Returns safe login metadata. Rejected credentials clear cookies. |
| GET /session | Returns authenticated, user_id, status after authoritative grant/account/family checks. No authentication credentials. |
| POST /logout | JSON `{}`; revokes current family and clears cookies with matching scope/attributes. |
| POST /logout-all | JSON `{}`; valid current access required; revokes all families and legacy grants, then clears cookies. |

Every POST requires an `X-CSRF-Token` challenge and exact approved Origin (or
Referer fallback if Origin is absent), with Content-Type application/json.
The browser router also enforces this for future PUT/PATCH/DELETE routes.
Missing/invalid/expired challenges or origins return generic 403. Missing,
expired/revoked authentication returns 401; dependency failures 503; limits 429.
All authentication responses, including errors, have Cache-Control no-store.

## Local Swagger/browser walkthrough

1. Open `http://127.0.0.1:8000/docs` consistently; do not mix localhost/127.0.0.1.
   Register/verify a development account through the existing workflow. Never
   activate pending accounts as a shortcut.
2. Execute GET browser/csrf. Keep its challenge private; enter it into the
   browser login operation's X-CSRF-Token field. The browser supplies cookies and
   Origin on requests. Use email/password JSON; never paste authentication tokens
   into URLs or browser storage.
3. Execute browser/login, then browser/session. Login returns safe metadata;
   HttpOnly credentials are inaccessible to JavaScript. GET auth/me still requires
   a Bearer header and does not accept these cookies.
4. GET a new csrf challenge after login. Execute browser/refresh with `{}` and
   that header. Obtain another challenge after rotation before logout/logout-all.
   A challenge bound to the old refresh credential receives 403.
5. Logout clears cookies. Password reset revokes every family/legacy grant;
   retained cookies cannot restore a reset session. Use the new password to login.

Cross-origin clients must explicitly use fetch credentials=include from an
approved same-site origin. CORS preflight allows only configured exact origins,
known methods/headers and credentials; wildcard origins are rejected. SameSite=Lax
deliberately does not support cross-site cookie deployments. Deploy a same-site
web/API or reviewed BFF; do not relax SameSite/CSRF to make a cross-site setup work.
Clients must serialize refresh across tabs. Strict concurrent reuse can revoke
the successful successor; discard cookies through logout and login again.

## Deployment configuration

APP_BROWSER_ORIGINS and APP_TRUSTED_HOSTS are JSON arrays. Local defaults support
HTTP localhost/127.0.0.1:8000; testserver is a test-only default host. Set exact
deployment HTTPS origins/hosts and APP_BROWSER_COOKIE_SECURE=true in staging and
production; unsafe defaults/wildcards fail configuration validation. Compose is
a local development configuration; do not use it unchanged for production.

Secure cookies use __Secure-movie_access, __Secure-movie_refresh and temporary
__Secure-movie_bootstrap. Local HTTP uses unprefixed movie_* names. All are
HttpOnly, SameSite=Lax, host-only with no Domain, restricted to
Path=/api/v1/auth/browser. __Host- cannot be used with a restricted path. Host-only
scope and duplicate-cookie rejection reduce shadowing; subdomain governance and
HTTPS are still required. Future cookie-authenticated product routes must live
under this scope or use a separately reviewed BFF; cookies do not silently grant
access to other API routes.

APP_BROWSER_COOKIE_SECONDS defaults to 604800 and caps credential cookie age;
actual access/refresh ages never exceed their server credential/session expiry.
APP_BROWSER_CSRF_SECONDS defaults to 900. Challenges bind to a random HttpOnly
pre-login nonce or current refresh digest using a purpose-separated HMAC key,
signed expiry and random challenge nonce. Login/refresh changes binding. Only
CSRF challenges, never access/refresh values, may be kept in browser memory.

Trusted-host checks, nosniff, frame denial, no-referrer, permissions restrictions
and CSP apply; Swagger/ReDoc retain their required UI scripts. HSTS applies in
staging/production. Configure HTTPS termination and trusted proxy handling in
deployment; no forwarded-origin trust is implemented here. XSS can still act as
the user and needs frontend controls. Full RBAC, privileged MFA, session inventory,
retention and production deployment acceptance remain outstanding.

## Tests and database safety

Run `.\.venv-dev\Scripts\python.exe scripts/run_tests.py`. New tests exercise real
PostgreSQL using the existing uniquely named disposable database fixture, mocked
email transport and existing Redis limit controls. No SMTP credentials are needed
in CI. Test-only cookie restoration preserves cookie Path and Domain; duplicate
cookies deliberately fail closed. No new migration is needed; head remains 0005.
Never reset volumes or apply a live downgrade. See [Report 011](../DEVELOPMENT_REPORT_011.md)
for actual commands/results and [decisions](../architecture/BROWSER_SESSION_DECISIONS.md).
