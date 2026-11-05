# Mailtrap sandbox — verification and recovery

Roadmap 4.0, Phase 2 Increment 3. Existing verification/recovery endpoints are preserved. Phase 2 is not complete.

## Configuration

Keep credentials only in ignored `.env`; `.env.example` contains empty credential fields. API and worker receive the following explicit Compose environment settings:

| Setting | Local sandbox value |
| --- | --- |
| APP_EMAIL_PROVIDER | mailtrap_sandbox |
| APP_SMTP_HOST | sandbox.smtp.mailtrap.io |
| APP_SMTP_PORT | 2525 or another STARTTLS port supported by your sandbox |
| APP_SMTP_USERNAME / APP_SMTP_PASSWORD | Your sandbox's credentials; never commit or print |
| APP_SMTP_STARTTLS | true; unencrypted SMTP is rejected |
| APP_SMTP_TIMEOUT_SECONDS | 10 by default; configurable 1–30 seconds |
| APP_EMAIL_FROM_ADDRESS | A valid email address; no-reply@example.com is suitable for sandbox testing |
| APP_EMAIL_FROM_NAME | AI Movie Platform, or your configured sender name |

`outbox` preserves the encrypted local CLI delivery mode from the original Increment 3. `smtp` is the configurable transport seam for a future real transactional provider. Production rejects `mailtrap_sandbox` and recognized sandbox hosts even if labeled `smtp`. Production delivery/provider acceptance is not claimed. Sender names cannot contain CR/LF; TLS certificate and hostname verification are mandatory. No SMTP debug mode is enabled.

After saving `.env`, refresh only API/worker when environment values change:

```powershell
docker compose up -d --no-deps --no-build --pull never --wait api worker
```

Existing schema revision 0004 is additive. Before first applying it, back up the development database and verify the archive; never reset/drop existing databases or volumes. Use the existing Alembic procedure (`upgrade head`, `current`, `check`). Do not rerun destructive migration round-trips on live development data.

## Swagger walkthrough

Open [local Swagger](http://127.0.0.1:8000/docs). Use a unique sandbox test email and your own long test password; do not paste passwords or action/access tokens into reports or CI logs.

1. **POST /api/v1/auth/register** with email, display_name, password. Expect generic 202 and a pending Viewer. Login before verification returns 401.
2. The worker polls durable SMTP jobs every 10 seconds. Open your Mailtrap Email Testing sandbox inbox and find **AI Movie Platform — Verify your email** for that test recipient. Inspect its expiry and confirmation endpoint. This inbox capture, rather than only SMTP acceptance, is delivery evidence.
3. **POST /api/v1/auth/verify-email** with the privately copied token in the JSON body. Expect 200; a repeated redemption is rejected. Verification never automatically logs in or assigns privileged roles.
4. **POST /api/v1/auth/login** with verified credentials. Expect 200. Privately put the returned bearer access into Swagger Authorize.
5. **GET /api/v1/auth/me** returns 200 with the safe Viewer profile.
6. **POST /api/v1/auth/forgot-password** with the same email. Expect the generic 202 response. Find **AI Movie Platform — Reset your password** in the same sandbox.
7. **POST /api/v1/auth/reset-password** with the reset token and a new 15–128 character password. Expect 200. Reusing the token returns generic 400.
8. Login with the old password returns 401. The previous bearer token receives 401 from `/me`. New-password login and `/me` with the new access token return 200. Database grant revocation is tested separately from token expiration.

If SMTP status is `submitted`, the server accepted the email; that alone does not prove capture. Check the inbox. No public outbox/inbox API is exposed by this application. The legacy local outbox CLI does not retrieve SMTP messages.

## Transaction and delivery behavior

Registration/resend/recovery commit the action hash and `smtp_deliveries` job metadata atomically. SMTP jobs have no body, raw token or SMTP credential columns. Unlike legacy encrypted local outbox payloads, the SMTP path stores no recoverable action token in PostgreSQL or broker messages.

The worker locks the user/action/job, rechecks eligibility/current email/expiry, generates a token in memory, replaces its purpose-bound digest and commits a delivery lease before SMTP I/O. It then uses EHLO → certificate-verified STARTTLS → EHLO → authentication → message submission. A second poll cannot send an actively leased job. Failed attempts back off and retry at most five times while the action remains eligible and unexpired. Resend/recovery endpoints retain their existing limits, generic responses and single-use protection.

Retries generate a new token and invalidate the prior attempt's token. SMTP acknowledgment and the database status update cannot form one distributed transaction: a crash/ambiguous response may produce duplicate messages, and an older message may become invalid. Use the newest message or request another action. This is bounded retry behavior, not exactly-once delivery. `submitted` is not an inbox-capture or real-recipient-delivery claim.

Celery beat runs in the existing single development worker, with its schedule under writable `/tmp`. Run one scheduler per environment if scaling workers. Periodic task arguments/results contain counters only; no email tokens or passwords enter Celery messages/logs. Current provider error handling stores only generic error codes.

## Verified evidence — 5 November 2026

The owner confirmed receipt of both sandbox emails and supplied their tokens privately for API redemption. Both were redeemed successfully against the matching actions. Automated browser inspection was blocked at Mailtrap's Cloudflare sign-in gate; the capture evidence is owner-confirmed receipt plus successful matching-token redemption, not an automated inbox screenshot.

Live results: registration 202; pending login 401; verification 200; login/me 200; forgot-password 202; reset 200; old password/access 401; new login/me 200; reset replay 400. PostgreSQL confirmed the previous access grant's revoked_at value, so rejection was not inferred solely from an expired JWT. The task-specific private test credential file was removed after success; the sandbox messages and local test account were preserved.

Automated tests prohibit live SMTP by default and inject fake transports/SMTP clients. No Mailtrap credentials or inbox network access are required in CI. See [Report 009](../DEVELOPMENT_REPORT_009.md) for commands, test results and GitHub evidence.

References: [Mailtrap sandbox SMTP integration](https://docs.mailtrap.io/email-sandbox/setup/sandbox-smtp-integration), [Python SMTP STARTTLS](https://docs.python.org/3/library/smtplib.html#smtplib.SMTP.starttls).
