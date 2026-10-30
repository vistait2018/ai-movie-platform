> Roadmap 4.0 · 30 October 2026 · Documentation baseline prepared under Instruction 001. Owner-dependent decisions remain pending; this document does not itself establish phase acceptance.

# Roles and permission model

All permissions below describe intended behavior; authentication/authorization is not implemented in Phase 1. UI visibility never substitutes for API/service checks. Users may hold multiple expressly assigned roles; access is scoped to ownership and assigned duties.

| Role | Allowed scope | Restrictions |
| --- | --- | --- |
| Visitor | Public catalogue, permitted trailers, registration | No premium playback or private projects |
| Viewer | Own profile, authorized playback, wallet purchases/unlocks, plans, watchlists/history, approved sharing | No admin actions or other users' records |
| Creator | Viewer abilities plus own creator profile, projects, licensed uploads, AI jobs, submissions, earnings/payout requests | Cannot approve own publication, alter earnings or execute payouts |
| Moderator | Assigned submissions, reports, rights complaints, takedowns and appeals | No wallet corrections, gateway secrets or payout execution |
| Finance Administrator | Authorized reconciliation, refunds, earnings review and payout approval/execution workflow | No unrestricted identity/content/provider administration; cannot approve own sensitive action where dual control applies |
| Super Admin | Platform configuration, roles, catalogue, pricing/provider controls and audited oversight | Financial controls and separation of duties still apply; no unaudited ledger editing |

## Security rules
Deny unless a specific permission and resource scope allow the action. Enforce ownership checks, suspension state, active entitlements and publication state at service/API boundaries. Privileged roles require MFA and audit events. Worker jobs operate with limited service identities and cannot bypass publication or payout authorization. Public catalogue must exclude private drafts. Finance read/export permissions must be separate from money-moving permissions.

Owner approval pending: exact finance approval thresholds, whether separate humans are available for dual control at beta, moderation assignments and support escalation permissions. Add authorization tests during Phase 2 and each feature phase.
