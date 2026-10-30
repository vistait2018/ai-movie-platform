# Development report — Instruction 006

31 October 2026 · Africa/Lagos · Roadmap Version 4.0 unchanged.

## Current authorization state
Repository owner explicitly approved the prepared main protection and disposable verification. Applied the policy and completed the failing-PR enforcement proof and cleanup. The repository owner subsequently explicitly authorized local reconciliation under ten data-preservation conditions. Verified the live password, backed up .env and changed only POSTGRES_PASSWORD; refreshed only API/worker. Final verification passed and Phase 1 is now formally accepted. Historical pending observations below describe the state before this later authorization.

## GitHub evidence
Run 41126826693: success for ec605fa7aa082c8ed20b79bb400b987387339682. Latest records run 41143591217: success for 3c69ec161ac1ec19e1ed331b203d96cbfe8074dd. Queried the commit check-runs API: exact contexts quality and containers, both success, GitHub Actions App ID 15368. Active account matches owner vistait2018 and has admin permission on vistait2018/ai-movie-platform; default branch main.

Before authorization, classic protection returned HTTP 404, repository rulesets returned [], and active main-branch rules returned []. After explicit approval, the classic main protection was applied and read back successfully. Concrete JSON proposal: docs/governance/MAIN_PROTECTION_PROPOSAL.json. It requires an up-to-date branch, both checks from the identified App, PRs, resolved conversations and administrator enforcement; denies force pushes/deletions. Zero third-party approvals is an explicit solo-owner proposal, not an omission of PR requirements. The effective policy has no configured bypass actor.

## Applied policy and disposable enforcement proof
Owner response: "Approve policy and disposable verification". Applied `PUT repos/vistait2018/ai-movie-platform/branches/main/protection` with the reviewed JSON. The first request was schema-rejected (422) because legacy contexts and App-bound checks were supplied together; removed only the mutually exclusive legacy contexts field and reapplied the identical approved policy successfully. Readback confirmed:
- quality and containers bound to App 15368; strict/up-to-date checks true.
- PR required, zero third-party approvals, administrators enforced.
- force pushes false and deletions false.

Created only `codex/phase1-governance-proof-006-8366561e5c` and [DO NOT MERGE PR #1](https://github.com/vistait2018/ai-movie-platform/pull/1), from unchanged main SHA `3c69ec161ac1ec19e1ed331b203d96cbfe8074dd`. It added only tests/test_governance_gate_006.py with an intentional AssertionError. Initial temporary-file upload lacked a trailing newline, causing an incidental format failure; corrected that disposable file only and reran, so the final evidence reaches the actual intended assertion.

Final proof head: `cfecb5e6c65299d9eee4ad65a2a2db0899d9e2d8`. [Pull-request run 41144795636](https://github.com/vistait2018/ai-movie-platform/actions/runs/41144795636): quality failed at the official test step with **1 intentional failure, 24 passed**, zero unrelated test failures; containers succeeded. Logs identified test_disposable_governance_check and the exact intentional assertion. Ruff, format, mypy, Bandit and dependency checks passed before the assertion.

GitHub read-only PR state after completed checks: `mergeable=MERGEABLE`, `mergeStateStatus=BLOCKED`, quality FAILURE and containers SUCCESS. The branch was conflict-free and based on current main; required-check failure blocked it. No merge command/API call was issued, and no unsafe force-push or main-deletion attempt was made.

Closed PR #1; API confirmed `state=closed`, `merged=false`. Deleted only its uniquely identified temporary branch; follow-up ref lookup returned expected 404. Main remained exactly `3c69ec161ac1ec19e1ed331b203d96cbfe8074dd`. Removed only local payload/body/failing-test helpers created for this proof. Ignored audit metadata/proof JSON are retained for evidence. The deliberately failing test never entered main or the local tests directory.

Protection remains active after cleanup. Main's successful baseline workflows remain the evidence for healthy production-source CI; the separate disposable workflow failure is intentional enforcement evidence.

## Credential evidence and safe proposal
Inspected local configuration without displaying secret values. APP_DATABASE_URL authenticates to the existing PostgreSQL volume and SELECT 1 returns 1. Its password differs from POSTGRES_PASSWORD; authentication using POSTGRES_* is rejected. The running API /ready returned HTTP 503 with database unavailable and Redis healthy, confirming stale/inconsistent client configuration still affects the live application even though host tests use the working URL.

Proposed non-rotation reconciliation: back up .env under ignored .tools, align only POSTGRES_PASSWORD to the verified password already represented in APP_DATABASE_URL, keep database credentials and all volumes unchanged, then recreate only API/worker if necessary to load corrected settings. Verify both credential sources and /ready. This action was held until the separate explicit credential authorization; it has now been received and completed below. Do not reset/delete/reinitialize any volume.

## Actual checks
Official command `.venv-dev/Scripts/python.exe scripts/run_tests.py`: **24 passed**, zero failures/errors/skipped integration tests, one existing Starlette/httpx deprecation warning, in 2.07 seconds. Real PostgreSQL and Redis connections exercised. Ruff check/format passed; mypy passed for 13 app files and one runner; Bandit app/scripts passed; pip check found no broken requirements. Dependency advisory refresh also passed with no known vulnerabilities. Proposal JSON parsed and required fields checked; effective GitHub settings and actual blocked-PR evidence are recorded above.

## Phase 1 acceptance review
| Requirement group | Evidence/status |
| --- | --- |
| Retain code, Python/dependencies, organized packages, mobile workspace strategy | Already verified in 003–005; unchanged |
| Docker application/worker, Compose PostgreSQL/Redis, Celery/storage | Independent Ubuntu run and earlier local setup verified; no configuration overwritten |
| Environment separation and secret guidance | Verified; owner-authorized local password-setting alignment completed with ignored backup; both authentication paths pass |
| Health/readiness, logging and errors | Unit/integration checks pass; final live /health healthy and /ready HTTP 200 after API/worker-only refresh |
| Reproducible build/clean setup/OpenAPI/docs | Verified in prior isolated local setup and actual GitHub jobs; unchanged |
| Ruff/type/tests/dependency security in CI | Both actual GitHub jobs success, exact required contexts confirmed |
| Protected Git workflow/enforcement | Verified after owner approval: active protection, failed quality check, BLOCKED PR, closed without merge and branch deleted |
| Initial commit and authorized remote | Complete, published history preserved |
| Completion decision | Phase 1 complete: governance enforcement and final authorized local reconciliation/readiness verification passed; formal acceptance recorded |

Phase 0 owner decisions remain pending separately. No roadmap requirement was removed to claim acceptance.

## Phase 2 readiness
Reviewed docs/architecture/AUTHENTICATION_PLAN.md. Proposed sequence: approve policy/TTLs -> SQLAlchemy/Alembic identity/RBAC -> registration/password hashing -> verification/recovery/mock email -> web cookies/mobile access-refresh sessions -> permissions/profile lifecycle -> privileged MFA/bootstrap -> throttling/audit -> migration/API/security/authorization tests and CI. Web, Flutter Android and Flutter iOS use the same FastAPI business rules and identities. No authentication feature, migration, new application dependency or mobile code implemented.

## Files and preservation
Created governance JSON, approval/reconciliation procedure and this report; updated status references. Existing unrelated New Text Document.txt is preserved. No production secret, local .env, environment or cache belongs in Git. Governance mutation was performed only after explicit owner authorization. Only the subsequently authorized local setting edit and API/worker refresh occurred. No database password rotation/reset, data loss or Phase 2 implementation occurred. Phase 1 acceptance is recorded after final verification. Documentation remains local/uncommitted; main is now protected and future publication must use a passing PR.

## Primary reference
https://docs.github.com/en/rest/branches/branch-protection

## Historical handover before credential authorization
Roadmap 4.0 unchanged. Governance is authorized, applied and verified: main requires PRs, up-to-date quality/containers checks from GitHub Actions App 15368, administrator enforcement, no force pushes or deletions. Disposable PR #1 failed its intentional test and was BLOCKED; it was closed unmerged and its branch deleted, with main unchanged. Official local suite passed 24 real-service tests and quality/security checks passed. Credential reconciliation has NOT been authorized: APP_DATABASE_URL works, POSTGRES_PASSWORD differs/rejects, and running API /ready remains 503. Await the second owner decision before editing .env or refreshing API/worker. Phase 1 is not complete; Phase 2 sequence is reviewed but no implementation exists. Records are updated locally.

## Historical formatting log clarified

The later user-pasted report-002 Ruff spacing error was confirmed as historical run 41121325151 at initial commit 62ef9bc. Current main is 3c69ec161ac1ec19e1ed331b203d96cbfe8074dd; both main runs 41126826693 and 41143591217 are success. Rechecked report 002 and full repository formatting: passes, 39 files formatted. The required blank lines at 99 and 104 are already committed. No new main CI failure was found.

## Authorized credential reconciliation — completed
The owner explicitly authorized the strategy and required verification, ignored backup, POSTGRES_PASSWORD-only alignment, no database/Redis recreation or volume deletion, and only API/worker refresh if required. Verified APP_DATABASE_URL by authenticating and SELECT 1 before editing. Backed up exact .env bytes into a unique ignored .tools/local-env-before006-reconciliation-*.env file. Decoded the verified URL password and set only POSTGRES_PASSWORD via dotenv; programmatically confirmed every other parsed setting was unchanged. No secret value was displayed, logged, staged, committed or pushed.

Both the original APP_DATABASE_URL and correctly URL-encoded POSTGRES_* connection path then authenticated and SELECT 1 passed. No PostgreSQL password ALTER/reset was executed.

Recorded existing database/cache container IDs before service refresh. Ran only:
```powershell
docker compose config --quiet
docker compose up -d --no-deps --no-build --pull never --wait --wait-timeout 120 api worker
```
Only API/worker were recreated. PostgreSQL and Redis container IDs remained identical; both original named volume creation timestamps remain 2026-10-30T19:42:08Z. No down, database/cache recreation, reset, volume removal or destructive command was used. All five services are healthy.

Final service verification: PostgreSQL accepting connections and both host authentication paths pass; Redis PONG; live GET /health healthy and GET /ready ready with database/Redis healthy (HTTP 200). Celery inspect ping passed and actual dispatched movie.ping task ea6229c9-7a4a-4e34-bd8d-c6b68ce081c5 completed with status ok.

Official `.venv-dev/Scripts/python.exe scripts/run_tests.py`: **24 passed, zero failures/errors/skipped integration tests**, one existing deprecation warning, 1.97 seconds. Ruff/format passed, app mypy (13 files) and runner mypy (one file) passed, Bandit passed, pip check passed, lock check passed (75 packages including project), advisory refresh reported no known vulnerabilities.

## Formal Phase 1 acceptance and Phase 2 handover
All mandatory Phase 1 technical criteria now have positive evidence; the previous local readiness/credential gap is closed under authorization. [Formal acceptance](roadmap/PHASE_1_ACCEPTANCE.md) and current PHASE_STATUS.md mark Phase 1 complete as of 31 October 2026. Phase 0 business approvals remain separate and pending. No Phase 2 feature has been implemented in this instruction.

The next application work is the minimum identity data model/migration plus registration and verification, followed by shared web/Android/iOS login/session contracts, recovery/revocation, RBAC, privileged MFA and tests. Existing AUTHENTICATION_PLAN.md supplies the sequence. Do not add unrelated infrastructure or paid integrations.

Acceptance records use the protected PR workflow and are merged only after both required checks succeed. Local .env/backups, caches/environments and unrelated New Text Document.txt remain excluded. The deliberately failing PR #1 remains closed and unmerged.
