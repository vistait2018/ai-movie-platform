> Roadmap 4.0 · 30 October 2026 · Documentation baseline prepared under Instruction 001. Owner-dependent decisions remain pending; this document does not itself establish phase acceptance.

# MVP and delivery scope

## Internal engineering milestones
1. Foundation: Python/FastAPI, reproducible dependencies, PostgreSQL, Redis, Docker, workers, tests, CI and shared authentication.
2. First functional slice: Super Admin enters idea -> structured story -> scenes -> persistent project -> catalogue preview. Mock providers first; paid integration only when explicitly configured with budgets.
3. First playable movie: continuity references, generated assets, FFmpeg rendering and review.
4. Streaming MVP: catalogue, HLS/private storage/CDN, web playback and server-side entitlements.
5. Monetization MVP: wallet, approved purchases, subscriptions/VIP and reconciliation.
6. Creator/social beta: uploads, Studio, earnings, eligible payout workflows and rights-permitted clips.
7. Android/iOS beta: shared account/catalogue/entitlements, native playback and applicable verified store purchases.
8. Commercial release: approved markets, launch catalogue, all platform approvals, operations and monitoring.

## Required final scope
All Roadmap 4.0 phases 0–31 remain required. Web, Flutter Android and Flutter iOS are commercial deliverables; AI filmmaking, series/chapters, coins, subscriptions, VIP, global gateway orchestration, USD reporting/approved settlement, creator earnings/eligible USD payouts and social sharing remain included.

## Outside current foundation implementation
Live AI charges, live payment credentials, actual coin transactions, production deployment and app-store publication. These belong to subsequent acceptance-driven phases, not removed product scope.

## Deliberately uncommitted extensions
No universal payment coverage, guaranteed universal USD payouts, automatic public publishing, unlimited AI generation or unapproved direct social API publishing. Offline protected downloads, live broadcasting and a separate microservice rewrite are not currently specified commitments.

## Acceptance and dependencies
Approve Phase 0 decisions, then verify Phase 1 clean setup/CI before completion. Authentication requires persistent identities: implement the minimal Phase 3 identity schema/migration alongside Phase 2 with documented dependencies, without marking the full Phase 3 schema complete. AI and finance modules need persistent jobs and immutable ledger semantics before billing. Mobile clients use server business rules.

Owner approval pending: launch markets, catalogue size, initial paid-provider selection, exact beta journeys, device matrix and commercial MVP sign-off.
