# Email verification and password recovery — Increment 3

Official Roadmap 4.0 unchanged. Existing registration, login and bearer `/me` contracts remain. Phase 2 is incomplete.

## Endpoints

| Endpoint | JSON body | Result |
| --- | --- | --- |
| POST /api/v1/auth/register | email, display_name, password | Existing generic 202; new pending Viewer, verification action and encrypted message commit together. |
| POST /api/v1/auth/request-verification | email | Generic 202 for known/unknown/ineligible accounts. Queues only for pending, unverified users. |
| POST /api/v1/auth/verify-email | token | 200 activates only the pending, unverified account bound to that token/current email. No automatic login. |
| POST /api/v1/auth/forgot-password | email | Generic 202. Queues reset only for active verified users. |
| POST /api/v1/auth/reset-password | token, new_password | 200 replaces the Argon2id hash and revokes every existing access grant. No automatic login. |

Confirmation failure returns the same 400 for unknown, expired, consumed, wrong-purpose or ineligible actions. Protected extra fields are forbidden; validation errors omit input/context. Password policy remains 15–128 characters, Unicode/spaces supported, no trimming. Redis/dependency/delivery failure returns sanitized 503; rate limits return 429/Retry-After. Tokens belong only in JSON POST bodies, never query strings, logs, issue reports or analytics. These responses provide generic account-existence behavior, not a guarantee of identical network latency.

## Practical Swagger walkthrough

Use the existing Windows `.venv-dev` and running PostgreSQL/Redis. Generate a **separate Fernet outbox key**, without displaying it, using this block. It preserves an existing key, backs up `.env` to ignored `.tools`, and changes no database/signing credentials:

```powershell
@'
from pathlib import Path
from uuid import uuid4
from cryptography.fernet import Fernet
from dotenv import dotenv_values

path = Path(".env")
if not dotenv_values(path).get("APP_EMAIL_OUTBOX_KEY"):
    Path(".tools").mkdir(exist_ok=True)
    backup = Path(".tools") / ("before-email-" + uuid4().hex + ".env.backup")
    backup.write_bytes(path.read_bytes())
    lines = [line for line in path.read_text(encoding="utf-8").splitlines()
             if not line.startswith("APP_EMAIL_OUTBOX_KEY=")]
    lines.append("APP_EMAIL_OUTBOX_KEY=" + Fernet.generate_key().decode())
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
'@ | .\.venv-dev\Scripts\python.exe -
```

Apply only additive migrations, then rebuild/refresh API and worker using the existing instructions. Do not delete volumes. A host API alternative is `python -m uvicorn app.main:app --host 127.0.0.1 --port 8001 --no-access-log` from `.venv-dev` after migration; use `/docs` on that port. Docker API Swagger is [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs).

1. In Swagger, **POST /api/v1/auth/register** with a unique local test email, display_name and your own long password. Expect 202; login still returns 401 while pending. Do not include role/status fields.
2. From the repository in a private local terminal, run:

   ```powershell
   .\.venv-dev\Scripts\python.exe -m app.dev_outbox --email viewer@example.com --confirm-local-development
   ```

   Substitute the email you registered. The CLI prints only an export filename under ignored `.tools/outbox`. Open that JSON locally in your editor. Locate `purpose: verify_email` and copy its `token` privately. The durable source is encrypted PostgreSQL, not this export. No HTTP outbox route exists. The export is sensitive plaintext: never share/commit it; delete only your own export after use. Windows inherits the local user's file ACL; Unix creates owner-only mode 0600. Local OS/database/key access is the trust boundary.
3. **POST /api/v1/auth/verify-email** with `{"token":"<privately copied token>"}`. Expect 200. Repeat the same confirmation to see generic 400, proving single use.
4. **POST /api/v1/auth/login** using the original email/password. Expect 200 with short-lived access. Privately paste it into Swagger **Authorize** as a bearer token.
5. **GET /api/v1/auth/me**. Expect 200 with your safe Viewer profile.
6. **POST /api/v1/auth/forgot-password** with the same email. Expect generic 202. Run the same local outbox CLI again and inspect the newly exported message with `purpose: reset_password`.
7. **POST /api/v1/auth/reset-password** with that token and `new_password` satisfying the existing policy. Expect 200. All old access grants are revoked. Old Swagger authorization now receives 401 from `/me`.
8. Login with the **old password**: expect 401. Login with the **new password**: expect 200. Re-authorize with the new access token and `/me` works. Reusing the reset token returns 400. Delete the local exports you created.

The local runtime smoke executed all eight steps against Docker, including CLI export/retrieval, replay rejection and grant revocation. Test passwords/action/access tokens were not printed. Its two temporary exports were removed; one local smoke user remains. Do not use the older development activation shortcut to demonstrate this workflow.

## Security and transaction design

- `0003_auth_actions_outbox` adds only `auth_actions` and `email_outbox`, preserving revisions 0001/0002 and existing data. Each action has UUID, user FK/index, purpose, recipient snapshot, unique SHA-256 digest, UTC creation/expiry and consumed timestamp. Only a purpose-bound digest of a cryptographic 256-bit random token is stored in the action record.
- Email payloads (including token/recipient) are Fernet authenticated-encrypted under a separate environment key in PostgreSQL. Losing/changing the key makes existing messages unreadable; preserve it securely across restarts. No hardcoded key, SMTP call, paid service or public mailbox viewer.
- User-row locks serialize issuance/redemption and login/reset races. Redemption looks up the digest then locks user followed by action; expiry is checked after lock wait. Concurrent redemption has one winner. Recipient snapshot must still match the current user email; clients cannot supply another target user/email/role/status at confirmation.
- Resends coalesce within 60 seconds. A later resend invalidates older same-purpose actions and deletes their encrypted outbox payloads. Success consumes relevant actions and deletes their encrypted payloads. Password reset invalidates **all** outstanding actions and revokes every existing access grant in the same transaction as password/audit changes. Rollback preserves the prior password, grants, tokens and messages.
- Verification never activates active/suspended/deactivated accounts; recovery never activates pending or restores suspended/deactivated users. Only Viewer registration defaults are used; these flows never change role assignments.
- Independent per-IP and hashed email/token limits for each endpoint: requests default 5/300 seconds, confirmations 20/300. Raw emails/tokens/IPs are absent from Redis keys. Existing registration/login limits remain. Security events record requests/completions/rejections and operational rate/dependency events omit sensitive data. Unknown/ineligible request bodies/statuses match eligible ones; delivery misconfiguration fails before account lookup.

Settings: `APP_EMAIL_OUTBOX_KEY`, `APP_VERIFICATION_SECONDS=3600`, `APP_PASSWORD_RESET_SECONDS=900`, `APP_ACTION_RESEND_SECONDS=60`, `APP_ACTION_REQUESTS_PER_WINDOW=5`, `APP_ACTION_CONFIRMATIONS_PER_WINDOW=20`, `APP_ACTION_WINDOW_SECONDS=300`. Compose passes only the outbox key explicitly; add explicit overrides if changing other container defaults. These are configurable engineering defaults.

## Delivery interface and remaining limits

`EmailDelivery.enqueue(session, action_id, message)` is transaction-bound; the current adapter writes encrypted durable development messages. A future real-provider adapter must enqueue a durable delivery job in that transaction, then a worker sends **after commit**, with provider retry/idempotency/status handling. Authentication logic remains unchanged. No network email send belongs inside the account transaction.

The development adapter and export CLI refuse staging/production; CLI additionally requires explicit acknowledgment and a local database hostname. There is no HTTP message-access route in any environment. Until a real adapter is configured, registration and verification/recovery requests fail closed in staging/production. Confirmation logic is implemented, but production email delivery, abuse/load tuning, action/audit retention cleanup, notifications after reset and managed encryption-key rotation remain outstanding. Application DB and secret-key operators can decrypt local outbox messages; it is not a tenant mailbox product.

Refresh rotation, logout APIs, cookie/CSRF browser sessions, MFA, full RBAC/device management and complete Phase 2 acceptance remain future increments. No Phase 2 completion or production launch readiness is claimed.

References: [OWASP recovery guidance](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html), [Fernet authenticated encryption](https://cryptography.io/en/stable/fernet/).
