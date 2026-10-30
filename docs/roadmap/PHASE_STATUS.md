# Roadmap 4.0 phase status

Updated: 30 October 2026 (Africa/Lagos). Instructions 001–003.

## Acceptance summary
**No phase is marked complete.** Phase 0 documentation is prepared for owner review; open business decisions prevent final acceptance. Phase 1 local container and real-service verification now passes. An isolated clean setup has also passed on this machine and the initial commit is finalized under Instruction 003. Actual GitHub CI execution, branch protection/enforcement and an independent second-host setup remain outstanding.

| Phase | Status | Evidence / remaining gate |
| --- | --- | --- |
| 0 | Documentation prepared; approval pending | PRD, MVP scope, business rules, roles, architecture, preliminary database design, decisions, risks and roadmap written to the working tree. BR-01–13 and proposed service targets await owner decisions. |
| 1 | In progress | Local verification passed: Docker 29.8.2 engine/CLI, Compose 5.5.1 config/build/startup, PostgreSQL SELECT 1, Redis PING, live API readiness, real Celery task completion and optional Moto smoke test. Enabled complete suite: 24 passed, no skips; Ruff/format/mypy/Bandit/pip check/lock/audit pass. Instruction 003 repeated this from an isolated source snapshot/new environment/new volumes; actionlint passed. Initial commit finalized; GitHub CI/protections and a second-host setup remain unverified; no remote/push created. |
| 2 | Plan prepared; implementation not started | Proposed web/mobile opaque-session architecture, minimum identity migrations, RBAC, registration/recovery/MFA and implementation sequence documented in AUTHENTICATION_PLAN.md. No auth/schema code added. |
| 3 | Design only | Preliminary entity relationships documented; no SQLAlchemy schema or Alembic migrations. |
| 4 | Not started | Catalogue/content APIs and publishing absent. |
| 5 | Not started | Super Admin/finance dashboards and workflows absent. |
| 6 | Not started | AI story adapter/generation/persistence absent. |
| 7 | Not started | Character/world continuity engine absent. |
| 8 | Not started | Worker foundation exists; no media providers or generation jobs. |
| 9 | Not started | No FFmpeg assembly/rendering implementation. |
| 10 | Not started | No HLS transcoding, media storage integration or CDN. |
| 11 | Not started | No viewer frontend/player. |
| 12 | Not started | No free/premium entitlement enforcement. |
| 13 | Not started | No coin wallet or ledger. |
| 14 | Not started | No gateway or store billing adapters. |
| 15 | Not started | No subscription/VIP lifecycle. |
| 16 | Not started | No AI coin billing or provider-cost accounting. |
| 17 | Not started | No advertising/reward verification. |
| 18 | Not started | No creator onboarding/upload workflow. |
| 19 | Not started | No creator AI Studio. |
| 20 | Not started | No earnings accounting or USD payout workflow. |
| 21 | Not started | No social clips, copyright workflow or moderation. |
| 22 | Not started | No discovery/notification/referral/analytics implementation. |
| 23 | Strategy documented only | Proposed mobile/ Flutter workspace; no Android/iOS project/build. |
| 24 | Not started | No native playback, purchases or creator integration. |
| 25 | Not started as full phase | Baseline secret masking/configuration and scans exist, not full security/recovery acceptance. |
| 26 | Not started as full phase | Foundation regression tests exist, not end-to-end finance/media/mobile/performance validation. |
| 27 | Not started as production phase | Development CI/container definitions exist, not deployed production/mobile pipelines or monitoring. |
| 28 | Not started | No closed beta. |
| 29 | Not started | No commercial/provider/store approval evidence. |
| 30 | Not started | No launch catalogue/submissions/readiness sign-off. |
| 31 | Not started | No commercial operation. |

## Phase 1 acceptance checklist
- [x] Audit and preserve original endpoint behavior; original two tests executed successfully.
- [x] Working Python replacement, dependency declaration and generated cross-platform lock.
- [x] Application package boundaries and documented Flutter workspace strategy.
- [x] Environment separation, secret examples, validated settings and ignored local data.
- [x] Separate liveness/readiness, sanitized failures and structured application logging.
- [x] Celery JSON worker foundation with bounded task execution; no paid integrations.
- [x] Compose/Docker definitions for API, worker, PostgreSQL, Redis and optional disposable S3 emulation.
- [x] Local pytest, Ruff, mypy, Bandit, dependency consistency and advisory scan executed successfully.
- [x] CI definition and Windows setup/troubleshooting documentation.
- [x] Docker build, Compose semantic validation and actual services/worker readiness verified in Instruction 002, including successful task completion and emulator HTTP smoke test.
- [x] Isolated clean setup verified on this host with fresh source directory, virtual environment, credentials and Docker volumes; 24 tests passed, including real dependencies.
- [ ] Clean setup independently verified on another developer/CI host.
- [ ] GitHub workflow execution and required branch protections verified.
- [x] Initial commit reviewed and created as the final step of Instruction 003; resolve SHA with `git log -1 --format=%H`. Remote/push still require separate explicit authorization.

## Next development task
Review owner decision register BR-01–13 and approve Phase 0 baseline. Local Docker and real-service verification is recorded in Instruction 002. Only when remote work is authorized, execute GitHub CI and establish/test branch protections; verify setup on a second host before accepting Phase 1. Then begin Phase 2 with the minimum identity database/migration support from Phase 3, retaining the planned first story-to-catalogue functional slice.

Latest commands, acceptance matrix and Git/Phase 2 preparation: [Instruction 003 report](../DEVELOPMENT_REPORT_003.md). Prior service verification: [Instruction 002 report](../DEVELOPMENT_REPORT_002.md). Historical implementation: [Instruction 001 report](../DEVELOPMENT_REPORT_001.md).

Phase 2 proposal: [Authentication plan](../architecture/AUTHENTICATION_PLAN.md). Remote prerequisites: [GitHub setup](../development/GITHUB_SETUP.md).
