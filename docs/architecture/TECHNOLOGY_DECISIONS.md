> Roadmap 4.0 · 30 October 2026 · Documentation baseline prepared under Instruction 001. Owner-dependent decisions remain pending; this document does not itself establish phase acceptance.

# Technology decisions

| ID | Decision | Reason / status |
| --- | --- | --- |
| ADR-001 | Python 3.12.x for foundation, requires >=3.12,<3.13 | Working 3.12.14 runtime verified; old 3.14 base install inaccessible. Revisit version upgrades explicitly with dependency/test evidence. |
| ADR-002 | pyproject.toml + uv.lock; uv 0.13.6 | Cross-platform resolved versions/hashes, locked CI/container installs; no manual lock fabrication. |
| ADR-003 | FastAPI modular monolith | Roadmap baseline; preserve starter routes and split service/worker boundaries before considering distributed services. |
| ADR-004 | PostgreSQL with SQLAlchemy 2.x/Alembic in Phase 3 | Durable transactional finance and migrations; psycopg currently only supports readiness probes. |
| ADR-005 | Redis + Celery workers, JSON messages | Asynchronous work separate from HTTP; Linux Docker worker runtime. No periodic scheduler until needed. |
| ADR-006 | Jinja2/Tailwind/JavaScript web and Flutter mobile | Roadmap mandated; no frontend implemented here. |
| ADR-007 | Proposed mobile workspace `mobile/` (one Flutter project with android/ios directories) | Documented Phase 1 strategy; later shared API client, secure token storage, platform billing adapters and tests. iOS signing/build requires macOS/Xcode. No generated Flutter skeleton without toolchain validation. |
| ADR-008 | Private S3-compatible storage + CDN HLS | API authorizes, media/CDN delivers. Optional Moto 5.2.4 S3 emulation is development-only, disposable and not production storage. |
| ADR-009 | Separate liveness/readiness | API liveness independent of dependencies; readiness fails closed if database/cache missing. |
| ADR-010 | Environment settings + masked secrets and allowlisted JSON logs | Environment isolation; avoid URL credentials, request data and raw exception leaks in operational events. |
| ADR-011 | Mock-first AI/payment integration | No paid calls or live providers during foundation. Cost, financial and contract tests required before enabling providers. |

## References checked during implementation
- [uv project locking and synchronization](https://docs.astral.sh/uv/concepts/projects/sync/)
- [uv Docker integration](https://docs.astral.sh/uv/guides/integration/docker/)
- [FastAPI lifespan](https://fastapi.tiangolo.com/advanced/events/)
- [Pydantic settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/)
- [Celery introduction and platform support](https://docs.celeryq.dev/en/stable/getting-started/introduction.html)

Provider, store and legal requirements must be reverified from current primary sources during the relevant commercial implementation. This task does not give legal approval or universal coverage assurances.

- [Moto server mode](https://docs.getmoto.org/en/stable/docs/server_mode.html) and [official container package](https://github.com/getmoto/moto/pkgs/container/motoserver)
