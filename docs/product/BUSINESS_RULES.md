> Roadmap 4.0 · 30 October 2026 · Documentation baseline prepared under Instruction 001. Owner-dependent decisions remain pending; this document does not itself establish phase acceptance.

# Business rules and approval register

## Roadmap requirements (established scope)
- One authoritative backend governs identities, catalogue, progress, entitlements, coin movements and creator records for web/Android/iOS.
- Roles are enforced server-side; sensitive administrative and financial actions are audited.
- Coin movements are immutable, atomic, idempotent and reconcilable. Coins are non-redeemable; creator USD earnings are separate accounting liabilities.
- Existing valid chapter unlocks cannot be charged twice. Included subscription content must not trigger unnecessary coin deductions.
- Paid AI generation quotes charges, reserves budget/coins, settles once and compensates eligible failures. Provider cost and retries are bounded and recorded.
- Creator uploads and generated projects remain private drafts until approved. Publication requires rights, processing validation and moderation.
- Playback authorization is checked on the server; object storage is private and delivery uses expiring authorization.
- All payment channels are verified server-side before granting access or coins. Duplicate/replayed webhooks cannot duplicate value.
- USD is the financial reporting/reference currency. Original currency, fees, FX, refunds and actual settlement are preserved for reconciliation.
- USD merchant settlement and creator USD payouts only operate through approved arrangements and eligible corridors; no universal coverage promise.
- Mobile digital purchases follow applicable store billing requirements; validate actual policies before commercial implementation. Creator payouts are separate from viewer store purchases.
- Clips require content-owner permission, allowed duration and attribution; direct publishing requires approved API access.

## Owner approval register — no final commercial terms invented
| ID | Decision required | Dependencies / default implementation posture |
| --- | --- | --- |
| BR-01 | Launch markets, legal entity and supported currencies | Keep capability routing deny-by-default until approved |
| BR-02 | Coin packages, USD reference prices and FX quote validity | No real sale prices configured |
| BR-03 | Purchased/promotional coin expiry, spending priority and refund rules | No expiry or sale workflow activated |
| BR-04 | Free previews and Standard/VIP weekly/monthly benefits/prices | No paid entitlement configuration activated |
| BR-05 | Creator commission, revenue attribution, clearing/withholding periods | No earnings allocation or payout performed |
| BR-06 | Minimum payout, approved destinations, KYC and recipient verification | Payouts disabled until eligibility and available funds verified |
| BR-07 | AI providers/models, generation prices and maximum cost/retry budgets | Mocks first; no paid providers in foundation |
| BR-08 | Copyright/licensing agreements, takedown/appeal policy and clip permissions | No public user publishing |
| BR-09 | Age policy, restricted content, privacy/retention and account deletion | Review before identity and upload release |
| BR-10 | Taxes, invoice/refund rules, disputes and FX accounting conventions | Do not invent tax rates or legal conclusions |
| BR-11 | Financial approval thresholds and separation of duties | No sensitive financial operation enabled |
| BR-12 | Operational budget, availability/playback targets and recovery objectives | PRD contains proposals only |
| BR-13 | Product branding, beta scope and acceptance owners | Documentation awaits sign-off |

Record approvals with owner, date, decision and affected roadmap acceptance criteria. Unresolved entries block the relevant release, not reversible foundation engineering. Never substitute a developer's assumption for approved commercial terms.
