# Project status

**6 November 2026 — Phase 2 local verification candidate, NOT accepted.**
Report 013 MFA is preserved; account-status/suspension APIs and a browser account
interface are added. Full suite: **336 passed, zero failed/skipped**. Backup/full
restore verified; existing database remains at 0005. Canonical build is blocked
by Docker registry DNS; current local changes have no GitHub CI. Production
privileges stay disabled. [Report 014](DEVELOPMENT_REPORT_014.md),
[account guide](development/ACCOUNT_ADMINISTRATION.md). Older entries are historical.

Increment 7 MFA/provisioning is a local review candidate, **not accepted**.
See [Report 013](DEVELOPMENT_REPORT_013.md) and [MFA contract](development/MFA.md).
Production privileges remain disabled; Phase 2 remains incomplete. No push,
PR creation, merge or deployment is authorized for this review delivery.

Updated 5 November 2026 (Africa/Lagos). [Official Roadmap Version 4.0](roadmap/ROADMAP_V4.md) is unchanged.

**Current development: Phase 2 Increment 6 RBAC/identity ownership is accepted within its documented development/MFA boundary on codex/phase2-rbac-ownership.** Existing seeded roles/permissions and shared browser/Bearer identity checks are verified by 270 local/Ubuntu tests. Commit e0a7a3f3538f13b7ffc9137f51076864f65f25d4 is in open [PR #9](https://github.com/vistait2018/ai-movie-platform/pull/9), based on #8; [quality/containers passed](https://github.com/vistait2018/ai-movie-platform/actions/runs/42085077043). Production privileged operations deny until MFA. No migration or live administrator bootstrap. [Report 012](DEVELOPMENT_REPORT_012.md), [authorization contract](development/AUTHORIZATION.md). Phase 2 remains incomplete.

Previous Increment 4 is accepted in open PR #7. Older entries below retain historical evidence.

**Phase 1 is complete and formally accepted.** [Acceptance evidence](roadmap/PHASE_1_ACCEPTANCE.md), [current phase status](roadmap/PHASE_STATUS.md), [report 006](DEVELOPMENT_REPORT_006.md).

Verified foundation includes Python 3.12.14/locked dependencies, Docker/Compose, PostgreSQL, Redis, Celery, local storage emulation, health/readiness/logging/errors, tests, real Ubuntu CI and protected-main enforcement. Both local credential sources now authenticate; API /ready is HTTP 200 with both dependencies healthy. Only POSTGRES_PASSWORD was aligned after explicit authorization and ignored backup; only API/worker were refreshed. Existing data, database/cache container identities and volumes were preserved.

Final official suite: 24 passed, zero failures/errors/skipped integration tests. Ruff, format, mypy, Bandit, package consistency, lock and advisory checks pass. GitHub quality/containers passed; deliberate failing PR #1 was blocked, closed unmerged and its branch deleted. Future changes must pass the protected PR workflow.

Phase 0 product/commercial decisions remain pending separately. Phase 2 Increments 1–3 implement registration, login/me, email verification and password recovery with encrypted durable development delivery. Current local suite: 144 passed with real PostgreSQL/Redis; SMTP follow-up required GitHub jobs passed. Real email provider, refresh/logout, MFA, full RBAC and Phase 2 acceptance remain incomplete. AI/movie/streaming/finance/mobile UI features remain unimplemented. See Report 009 for current CI and SMTP evidence.

No credentials, local .env/backups, environments or caches are committed. The unrelated empty New Text Document.txt is preserved. No live finance, paid AI call or production deployment occurred.

## Instruction 007 — functional Increment 1

Phase 1 remains accepted. Phase 2 is now in progress: additive identity schema and pending Viewer registration are implemented, migrated locally and available at /api/v1/auth/register in Docker Swagger. Expanded suite: 45 passed locally, preserving the original 24 tests. No login/token/verification-delivery/admin feature is claimed yet. [Report 007](DEVELOPMENT_REPORT_007.md) and [owner test guide](development/REGISTRATION.md). Next is Increment 2 login/session issuance/current-user APIs.

Current review: [PR #3](https://github.com/vistait2018/ai-movie-platform/pull/3), feature commit `c854776b9b60dadb718cfea9ffa6720f24eacf6a`, [successful CI](https://github.com/vistait2018/ai-movie-platform/actions/runs/41193643965). See [report 007](DEVELOPMENT_REPORT_007.md) and [Swagger registration guide](development/REGISTRATION.md).

## Current increment — Instruction 008

Phase 2 Increment 2 adds verified-active login, short-lived signed bearer access, database-backed grant revocation/account restrictions and protected /me. Registration remains pending by default. Browser/Flutter contracts and safe local fixture preparation are in [AUTHENTICATION.md](development/AUTHENTICATION.md). Production email verification, refresh/logout, recovery, MFA and full RBAC remain incomplete. Current evidence is in [report 008](DEVELOPMENT_REPORT_008.md); earlier sections record historical results. Roadmap 4.0 unchanged.

## Current increment — Instruction 009

Phase 2 Increment 3 implements expiring single-use verification/reset workflows, atomic account/audit/grant changes and encrypted PostgreSQL development outbox with restricted CLI inspection. Local suite: 122 passed, no skipped integrations. Registration/login/me remain functional. [Practical Swagger guide](development/EMAIL_VERIFICATION_RECOVERY.md), [report 009](DEVELOPMENT_REPORT_009.md). Real-provider delivery, refresh/logout, cookie/CSRF sessions, MFA, full RBAC and Phase 2 acceptance remain incomplete. Roadmap 4.0 unchanged. Earlier sections retain historical evidence.

## Current follow-up — Mailtrap SMTP

144 automated tests pass, including the prior 122; local quality/security/dependency/migration checks pass. Additive 0004 provides metadata-only SMTP jobs, verified STARTTLS and worker retries. Both sandbox captures were owner-confirmed and the live verification/login/me/recovery/reset flow passed, including old-password/access rejection and database grant revocation. Automated inbox UI access was blocked at Cloudflare; no automated capture inspection is claimed. Commit 858e6dab4138343324afb0d9508164ed2633216c is in open PR #6 (base #5); workflow 41993609792 confirms both required jobs passed. See [Report 009](DEVELOPMENT_REPORT_009.md) and [Mailtrap guide](development/MAILTRAP_SANDBOX.md). Phase 2 remains incomplete.
