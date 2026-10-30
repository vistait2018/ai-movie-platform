> Roadmap 4.0 · 30 October 2026 · Documentation baseline prepared under Instruction 001. Owner-dependent decisions remain pending; this document does not itself establish phase acceptance.

# Risk register

| ID | Risk | Impact | Mitigation / gate | Owner status |
| --- | --- | --- | --- | --- |
| R01 | Commercial policies and markets unresolved | High | Approve BR-01–13 before dependent release | Product owner pending |
| R02 | Old Python installation inaccessible | Medium | Preserve old env; working 3.12 replacement, lock dependencies | Engineering workaround implemented |
| R03 | Docker absent; startup/build cannot be demonstrated here | High | Verify Compose/build/readiness/worker on Docker host and CI | Engineering pending verification |
| R04 | AI costs/failures and inconsistent characters | High | Mock contracts, budgets, reservations, quotas, continuity checks | Engineering/product before paid AI |
| R05 | Wallet races, duplicate credits/payouts | Critical | Immutable double-entry/coin records, atomicity/idempotency and concurrency tests | Finance/engineering before money movement |
| R06 | Gateway/store coverage, FX/settlement mismatch | High | Approved corridors, capability routing, server verification and reconciliation | Finance/compliance before launch |
| R07 | Copyright and unauthorized clips/content | High | Rights records, review, takedowns/appeals, private drafts | Content owner before uploads |
| R08 | Playback buffering and bandwidth costs | High | Source-aware HLS, CDN, realistic network benchmarks and budget | Engineering/product target approval |
| R09 | Account compromise and privileged misuse | Critical | Secure sessions, MFA, scoped roles, dual-control finance and audit | Security before sensitive features |
| R10 | Data loss/privacy and retention errors | High | Approve retention, backups/restore drills, access controls | Owner/security before beta |
| R11 | iOS build/store restrictions and mobile billing rejection | High | macOS pipeline, real-device testing and store policy review | Mobile/commercial before release |
| R12 | Full scope exceeds budget/timeline | High | Incremental milestones, acceptance gates and measured spend | Owner planning decision |
| R13 | Remote branch protections/CI not yet established | High | First reviewed commit, remote setup only when authorized, configure required checks | Repository owner pending |
| R14 | Local object storage emulator differs from production S3 | Medium | Verify emulator startup and later contract-test against the actual private storage provider | Engineering pending |

No risk is considered closed merely because it is documented. Assign named operational owners when the team is established and update evidence at each acceptance review.
