# Test registration — Phase 2 Increment 1

Roadmap 4.0. Registration is implemented; Phase 2 is not complete. Login, session issuance, email delivery/confirmation, password recovery, profile and admin endpoints are subsequent increments. Accounts deliberately remain pending and cannot yet be activated through a public endpoint.

## Swagger walkthrough
1. Open http://127.0.0.1:8000/docs and expand **Authentication → POST /api/v1/auth/register**.
2. Click Try it out. Enter a new local test email, display_name and your own 15–128 character password. Use a passphrase; Unicode/spaces are supported and no forced composition rule is imposed.
3. Execute. Expect **202** with only a generic message: registration request received; activation requires email verification. No user ID, password/hash, token or role is returned.
4. Resubmit the same email (including a case variation). Expect the same 202 response; the existing password/profile/role is unchanged.
5. Try invalid email, a short password or extra role/status/password_hash fields. Expect **422** with input values removed from validation errors. Never include real credentials in screenshots or reports.
6. More than the configured requests from one source within the window returns **429**; wait for expiry. Redis/DB failure returns sanitized **503**, not an unguarded fallback.

Email verification locally, login, protected /me, refresh/logout, password reset and administrative role tests are **not available yet**. They will be documented with their actual implementation in the following increments; this guide does not invent endpoints that do not exist.

## Database state and migration commands
The API does not create tables at startup. A backed-up, existing development database receives an explicit additive migration:
```powershell
.\.venv-dev\Scripts\python.exe -m alembic upgrade head
.\.venv-dev\Scripts\python.exe -m alembic current
.\.venv-dev\Scripts\python.exe -m alembic check
# Once the updated API image is built, equivalent runtime commands:
docker compose exec -T api alembic upgrade head
docker compose exec -T api alembic check
```

Never downgrade the persistent development database to test rollback: 0001 downgrade removes identity tables/data. Round-trip tests use uniquely named disposable test databases only. No existing database/volume is reset. Test connections must be local and need CREATE DATABASE permission in the development/CI PostgreSQL account; production credentials must not be used.

The migration seeds Viewer, Creator, Admin and Super Admin plus the roadmap's Moderator and Finance Administrator roles; no administrator account or password is seeded. Visitor remains anonymous. Permission/role assignment tables are extensible. Public registration always selects Viewer; elevated input fields are forbidden. Display name currently belongs to users; richer creator profiles are later work.

## Registration behavior and security
- EmailStr validation, whitespace removal and casefold canonicalization; canonical email is unique in PostgreSQL.
- Atomic PostgreSQL INSERT ON CONFLICT DO NOTHING protects duplicate and concurrent submissions. User, Viewer association and audit record commit together; write failure rolls everything back.
- Argon2id uses pwdlib's maintained recommended hasher with per-password random salt. Existing accounts are never updated by registration. No plaintext password is stored, returned or logged.
- The same response is used for new/duplicate valid emails; both paths perform password hashing. This reduces enumeration signals without claiming identical end-to-end network timing.
- Redis Lua INCR/EXPIRE is atomic. Keys use hashed request client address, no submitted password/email; TTL bounds retention. Defaults: 10 requests / 60 seconds, configurable with APP_REGISTRATION_REQUESTS_PER_WINDOW and APP_REGISTRATION_WINDOW_SECONDS. Request X-Forwarded-For is not manually trusted. Production proxy/abuse tuning and broader authentication throttles are later hardening.
- Validation excludes input/ctx data; database/runtime failure logs contain only event and error type. HTTP success is not an active-account/session grant.
- The endpoint sets no authentication cookies and issues no tokens in this increment. Do not use this partial authentication slice as a public commercial release.

## Verification
```powershell
.\.venv-dev\Scripts\python.exe scripts/run_tests.py
.\.venv-dev\Scripts\python.exe -m ruff check .
.\.venv-dev\Scripts\python.exe -m ruff format --check .
.\.venv-dev\Scripts\python.exe -m mypy
.\.venv-dev\Scripts\python.exe -m bandit -r app scripts -q
```
The full suite preserves the initial 24 tests and adds registration, migration consistency/round-trip, hashing, rollback, concurrency, privilege-input and Redis guard tests. Fixtures create and delete only unique movie_auth_test_* databases and one unique Redis key; no existing data store is reset. CI runs real PostgreSQL/Redis and also migrates/checks the lean Docker runtime. pytest is intentionally not installed in that image.

Primary references: [SQLAlchemy PostgreSQL conflict handling](https://docs.sqlalchemy.org/en/20/dialects/postgresql.html), [Alembic connection sharing](https://alembic.sqlalchemy.org/en/latest/cookbook.html), [pwdlib](https://frankie567.github.io/pwdlib/reference/pwdlib/), [OWASP authentication](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html).

## Increment 3 update

New registrations now atomically queue an expiring single-use verification action and encrypted durable development message. Existing generic 202/pending Viewer/login restrictions remain. Use [the verification and recovery walkthrough](EMAIL_VERIFICATION_RECOVERY.md), rather than the old development activation shortcut, to test the full workflow. A separately generated local outbox key is required; real-provider production delivery remains unconfigured.
