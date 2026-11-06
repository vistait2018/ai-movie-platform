# Authentication — Phase 2 Increment 2

Official Roadmap 4.0 unchanged. Shared FastAPI contract for web, Flutter Android and Flutter iOS. Phase 2 remains incomplete. Increment 3 now adds [email verification and password recovery](EMAIL_VERIFICATION_RECOVERY.md); the original access contract below is preserved.

## Delivered API contract

| Endpoint | Contract |
| --- | --- |
| POST /api/v1/auth/register | Existing JSON registration preserved: pending, unverified Viewer; generic 202. |
| POST /api/v1/auth/login | JSON email/password only. Verified active credentials return access_token, token_type=bearer, expires_in (default 600 seconds). Extra fields forbidden; canonical email; password never trimmed. |
| GET /api/v1/auth/me | Authorization: Bearer header; safe id/email/display_name/status/roles. OpenAPI HTTPBearer supports Swagger Authorize. |

Wrong, unknown, pending, suspended and deactivated credentials receive the same 401 message. Missing/invalid/expired/revoked access receives 401 and WWW-Authenticate: Bearer. Dependency/signing failures fail closed with sanitized 503; abuse limits return 429 and Retry-After. Login/profile success responses use Cache-Control: no-store; login also uses Pragma: no-cache. Validation errors omit sensitive input/context. Never place credentials in URLs, logs or analytics.

Both current clients explicitly send bearer headers; no cookie is accepted. Browser access stays in memory, never localStorage/sessionStorage; reload/expiry requires login. Flutter access stays in memory; there is no refresh credential to persist. HTTPS is mandatory outside loopback development. No credentialed CORS wildcard is added. A future browser cookie adapter must implement HttpOnly/Secure cookies, CSRF and origin checks first. This increment delivers backend contracts, not browser or Flutter UI.

## Token and revocation model

Maintained PyJWT signs HS256 with an explicit single-algorithm allowlist. Requires and validates exp/iat/nbf/iss/aud, UUID sub/jti, access purpose and at+jwt type; checks integer timestamps and bounded lifetime. Claims contain no email, roles or secrets. Signature verification precedes subject use.

Additive access_grants records jti UUID, user UUID, created_at, expires_at and optional revoked_at, never the bearer credential. Each authenticated request checks grant ownership/expiration/revocation and active verified account state in PostgreSQL. Database failure cannot authorize access. A trusted database/admin path can set revoked_at; deleting a grant or suspending/deactivating the account also rejects access immediately. No public logout/revoke API exists yet. Replacing the signing key invalidates existing access. Automated record retention and managed key rotation remain future work.

Security events record login success/failure and development fixture verification. Last-login timestamp, grant and success audit commit atomically. Audit failure rolls issuance back. Operational events contain names only. Unknown users perform dummy Argon2id verification. Redis independently limits IP and canonical account, default 10 requests/60 seconds each, with hashed keys, TTL and fail-closed behavior. Raw addresses/emails are absent from keys; hashes remain pseudonymous. Forwarded headers are not blindly trusted. These configurable engineering defaults still require abuse/load tuning.

## Setup and local test procedure

APP_ACCESS_SIGNING_KEY requires a unique cryptographically generated value (at least 32 bytes of entropy). Keep it only in ignored .env or a secret manager. No default is supplied; blank, short and replace-prefixed keys disable authentication with 503. Existing health/registration continue to work. Other settings: APP_ACCESS_TOKEN_SECONDS (60–3600, default 600), APP_ACCESS_TOKEN_ISSUER, APP_ACCESS_TOKEN_AUDIENCE, APP_LOGIN_REQUESTS_PER_WINDOW and APP_LOGIN_WINDOW_SECONDS. Compose explicitly passes the signing key; add explicit overrides for other settings when changing their defaults in containers.

Generate a local key without displaying it; this preserves existing keys and backs up .env to ignored .tools:

```powershell
@'
from pathlib import Path
from secrets import token_urlsafe
from uuid import uuid4
from dotenv import dotenv_values

path = Path(".env")
if not dotenv_values(path).get("APP_ACCESS_SIGNING_KEY"):
    Path(".tools").mkdir(exist_ok=True)
    backup = Path(".tools") / ("before-login-" + uuid4().hex + ".env.backup")
    backup.write_bytes(path.read_bytes())
    lines = [line for line in path.read_text(encoding="utf-8").splitlines()
             if not line.startswith("APP_ACCESS_SIGNING_KEY=")]
    lines.append("APP_ACCESS_SIGNING_KEY=" + token_urlsafe(48))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
'@ | .\.venv-dev\Scripts\python.exe -
```

```powershell
.\.venv-dev\Scripts\python.exe -m alembic upgrade head
.\.venv-dev\Scripts\python.exe -m alembic check
docker compose build api worker
docker compose up -d --no-deps --no-build --wait api worker
```

Register a local account normally and observe pending login rejection. To prepare only an explicitly selected local fixture:

```powershell
.\.venv-dev\Scripts\python.exe -m app.dev_verify --email viewer@example.com --confirm-local-development
```

Requires APP_ENVIRONMENT=development, explicit acknowledgment, a local database host and an existing pending account. Staging/production are refused before connecting. No new user is created, and suspended accounts cannot be reactivated. Writes development_email_verified audit. This prepares a local fixture; it does not prove email ownership or implement production verification. Never switch real production to development mode. Automated tests use isolated databases and verify these guards.

Use /docs to login, Swagger Authorize with the returned access, then /me. Never copy tokens to reports/issues. Swagger is a development tool, not the eventual browser session UI.

## Verification and limits

Official real-service tests: `.\.venv-dev\Scripts\python.exe scripts/run_tests.py`. Tests create/drop only unique disposable databases and remove only their unique Redis keys. Migration round-trip/downgrade is isolated; never downgrade the live development database for a test.

Not implemented: refresh issuance/rotation, logout/revoke APIs, browser cookie/CSRF adapter, real-provider delivery, MFA, device/session management or full RBAC. Privileged MFA is still mandatory for production phase acceptance; no production authentication acceptance is claimed. /me roles are descriptive; future actions must enforce permissions/ownership separately.

Reference: [PyJWT strict decoding and required claims](https://pyjwt.readthedocs.io/en/stable/api.html). Instruction 008's signed-token decision is recorded in the authentication plan.
