> Roadmap 4.0 · 30 October 2026 · Documentation baseline prepared under Instruction 001. Owner-dependent decisions remain pending; this document does not itself establish phase acceptance.

# Product Requirements Document

## Purpose and audience
Build one international AI filmmaking and streaming platform for viewers, filmmakers, AI creators, moderators, finance staff and Super Admin. Deliver responsive web, Flutter Android and Flutter iOS against one authoritative FastAPI backend. Commercial launch includes all three platforms, subject to approvals; an internal backend milestone does not reduce final scope.

## Required capabilities
- Catalogue: movies, series, seasons, episodes/chapters, scene structures, genres, languages, ratings, posters, subtitles and trailers.
- Viewing: public previews, adaptive HLS, quality selection, resume/history, watchlists, subtitles and protected premium access.
- Creation: idea to screenplay, character/world continuity, images/voice/audio/video, scene editing, asynchronous FFmpeg assembly, review and publication.
- Finance: non-redeemable coins, immutable wallets, weekly/monthly subscriptions and VIP; international collections, verified mobile billing, USD reporting and supported USD settlement.
- Creators: onboarding, rights attestations, uploads, AI Studio, moderation, analytics, USD earnings and eligible USD payouts separate from coin wallets.
- Discovery: approved social clips, referrals, search, recommendations and notifications.
- Operations: audited admin/finance workflows, Docker, CI/CD, automated tests, monitoring, recovery and cost limits.

## Key journeys and acceptance
| Journey | Acceptance evidence required |
| --- | --- |
| Viewer registers and watches | Authorized browse/play/resume across supported clients, measured playback quality |
| Customer purchases access | Verified transaction credited once, ledger reconciles, correct entitlement across channels |
| Creator makes a film | Validated story and scenes saved, controlled generation costs, playable rendered chapter |
| Creator uploads | Resumable licensed upload, validation and review before publication |
| Finance pays creator | Cleared eligible USD earnings, verified recipient, approved funds, idempotent transfer and reconciliation |
| Admin operates platform | Permission checks, financial approvals and audit records |
| User shares clip | Rights-permitted clip, attribution and working deep link, moderation controls |

## Proposed service targets — owner approval pending
Initial engineering proposals: p95 non-generation API latency below 500 ms under an agreed workload; p95 playback start below 3 seconds and rebuffer ratio below 1% on a defined reference network; monthly availability 99.5%; recovery point 24 hours and recovery time 4 hours for initial beta. These are planning proposals, not measured guarantees. Device matrix, traffic volume, geography, bandwidth profile and budget must be agreed before performance acceptance.

## Release gates
Foundation: clean setup, tests, lint/security checks, actual Docker service readiness and CI evidence. Functional slice: Super Admin enters idea, generates structured story/scenes, saves and previews catalogue. Beta: representative users complete viewing, finance and creator journeys on web and real Android/iOS devices. Commercial: all required phases accepted, security findings resolved, recovery rehearsed, provider/store approvals and support in place.

## Open owner decisions
Product name/branding, initial markets and age policy, MVP acceptance sign-off, prices/commissions, payout eligibility, content agreements, operating budget and numerical service targets. See BUSINESS_RULES and RISK_REGISTER. The supplied roadmap is the scope baseline, not proof these decisions are settled.
