# Instruction 006 — owner approvals and completed verification

31 October 2026 · Roadmap 4.0 unchanged.

## Verified current state
Both GitHub runs 41126826693 and 41143591217 succeeded. Exact required check contexts are `quality` and `containers`, both supplied by GitHub Actions App ID 15368. Active authenticated GitHub user and repository owner are vistait2018, with admin permission on vistait2018/ai-movie-platform. Classic main protection returned 404; repository rulesets and active main rules are empty.

Official host runner: 24 passed, zero failures/skips, one existing upstream deprecation warning, in 2.07 seconds. Ruff, formatting, application/runner mypy, Bandit and pip check passed.

## Proposed main protection
Concrete API payload: MAIN_PROTECTION_PROPOSAL.json. Require pull requests, both successful Actions checks bound to App 15368, an up-to-date branch, resolved conversations, admin enforcement, and no force pushes or deletions. No bypass actor is configured. Require zero third-party approvals so a sole owner can merge their own green PR; this still requires a PR and successful checks. If a second reviewer is available, owner may instead request one mandatory approval.

Owner explicitly authorized this policy; it has been applied and read back successfully. It will prevent direct pushes to main, including future documentation changes; those must use a passing PR.

## Disposable enforcement test — completed
Create a uniquely named codex/phase1-governance-proof-* branch from current main and a clearly labeled DO NOT MERGE PR containing only a deliberately failing test. Confirm the actual quality check fails and the GitHub server reports the PR merge state BLOCKED under the applied requirements. Never issue a merge call or merge the branch, even as a test. Close the PR and delete only the temporary branch/test artifact; retain its URL/check results as audit evidence. Do not modify user branches or bypass protection.

## Credential findings and proposed reconciliation
APP_DATABASE_URL authenticates to the existing PostgreSQL volume and SELECT 1 succeeds. POSTGRES_PASSWORD differs from the URL password, and a connection built from POSTGRES_* is rejected. No passwords were displayed or changed during this instruction.

Recommended data-preserving strategy: back up local .env in ignored .tools, set only local POSTGRES_PASSWORD to the already verified password encoded in APP_DATABASE_URL (decode URI escaping), and keep the database password/volume unchanged. Verify equality and both authentication paths. If the running API/worker still hold stale environment settings, recreate only those two services with the same Compose file and verify /ready; do not recreate/reset the database or Redis. Alternative, rotating the database credential to the desired local password would require a separate explicitly approved coordinated database/client rotation, and is not proposed here.

Credential edits/service refresh were held until explicit owner approval, then completed under the subsequently authorized conditions. No database reset/deletion is permitted.

## Phase 2 readiness
Existing AUTHENTICATION_PLAN.md reviewed. Sequence remains: approve session/security policy -> minimum SQLAlchemy/Alembic identity schema -> registration/password hashing -> verification/recovery/email mocks -> web/mobile sessions and rotation -> RBAC/profile lifecycle -> privileged MFA/bootstrap -> rate limiting/audit -> migration/auth/permission regression and CI acceptance. Web uses protected same-origin cookie sessions; Flutter Android/iOS use secure device storage and short-lived bearer/rotating refresh credentials through shared FastAPI APIs. No Phase 2 code is implemented here.

## Acceptance state
Governance enforcement is verified. Phase 1 remains incomplete until local configuration consistency and live API readiness are resolved and verified under the separately required credential authorization. Phase 0 owner decisions remain pending separately. Roadmap 4.0 is preserved.

Primary API reference: https://docs.github.com/en/rest/branches/branch-protection

Governance result: PR #1 quality failed at the intentional assertion (1 intentional failure, 24 passed), GitHub merge state BLOCKED. PR closed unmerged, temporary branch deleted, main unchanged. See DEVELOPMENT_REPORT_006.md for actual run links and cleanup evidence. The separate credential authorization was subsequently received and completed as recorded below.

## Subsequent explicit credential authorization — completed

Owner authorized data-preserving local reconciliation. Verified authentication before edit, backed up .env, changed only POSTGRES_PASSWORD, preserved database/cache IDs and volumes, refreshed API/worker only, then verified both authentication paths, Redis, live API and worker execution. Official suite passed 24 tests and quality/security checks passed. Phase 1 is formally accepted; see report 006 and PHASE_1_ACCEPTANCE.md. Earlier pending wording above is historical, not a current approval request.
