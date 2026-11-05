# Increment 5 — pre-development security decisions

Recorded 5 November 2026 before editing application code. Roadmap 4.0 unchanged.
Base db7dbb7b64f27a330597e53e8d1962b4389cd572, PR #7; branch
codex/phase2-browser-sessions. Verified open dependencies #3 → #4 → #5 → #6 → #7.
Unrelated New Text Document.txt is preserved and excluded.

Audit: existing Argon2id authentication, signed access grants, refresh rotation,
user/family/credential lock ordering, strict concurrent replay revocation,
logout/all, reset revocation, migrations 0001–0005 and test isolation are reused.
No new tables, credential stores, dependencies or migration are needed.

## Transport and CSRF

Add /api/v1/auth/browser/{csrf,login,refresh,logout,logout-all,session}.
Access and refresh cookies are HttpOnly, host-only (no Domain), SameSite=Lax,
Path=/api/v1/auth/browser. Secure is mandatory in staging/production; secure
cookies use __Secure- names. Local HTTP uses separate unprefixed names.
Cookie lifetimes are capped by existing credential/session expiry and a configured
cookie cap. No refresh or access credential is returned to JavaScript. Bearer
routes never read cookies; browser routes never fall back to Bearer headers.

GET csrf returns a short-lived, purpose-specific HMAC-signed CSRF challenge.
Before login it binds to a random HttpOnly bootstrap cookie; after login it binds
to the current refresh digest. Random nonce and expiry are mandatory. A custom
X-CSRF-Token header is required on every unsafe browser request, including login
and logout, with exact Origin or parsed Referer fallback validation. Missing/null
origins fail closed; unsafe content must be JSON. Signed challenges use separate
derived key/audience/purpose from access JWTs. Binding changes on login/refresh;
old challenges cannot authorize the successor session. Challenges are readable
by JavaScript but cannot authenticate. Login always creates a fresh family.

Refresh reuses strict replay detection: clients must serialize refresh across
tabs; retry/concurrency can revoke the winning successor. Logout requires current
access, refresh first if it expired. Rejected refresh clears cookies. Reset uses
existing account-wide revocation, so retained cookies cannot resurrect sessions.

## Deployment boundary

Exact configured origins only, credentialed CORS only for allowed origins, no
wildcards. Trusted hosts checked independently. HTTPS origins and non-local
explicit allowlists are required in staging/production. No trust in forwarded
headers for origin decisions. Security headers apply globally; auth responses,
including errors, are no-store. CSP is restrictive outside Swagger/ReDoc docs,
whose existing interactive UI is preserved. HSTS only outside local HTTP.
Apply unsafe-method CSRF dependency to the entire browser router, including
future POST/PUT/PATCH/DELETE routes. Bearer APIs remain mobile compatible.

References: [OWASP CSRF prevention](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html).
This signed session-bound challenge combines custom header, HttpOnly binding
and origin validation; SameSite alone is insufficient. XSS remains able to act
as a user; no frontend or production deployment is claimed by this increment.
