# Delivery plan and acceptance checks

## Phase 0 — current frontend

Delivered scope: six responsive screens, editable sample list, deterministic basket comparison, printable list, local demo approvals, laundry slot, saved ideas, scripted chat and privacy/check-in concepts. No backend connections. Verify using root scripts and browser walkthrough.

## Phase 1 — one live vertical slice

1. Create TypeScript API/worker projects, validation schemas and initial PostgreSQL migrations.
2. Add user identity, ownership checks and manual shopping inventory.
3. Implement Exa Search/Contents adapter with timeout, usage logs and source normalization.
4. Implement Coordinator TaskSpec, Researcher bundle and Planner draft with exactly three roles.
5. Add deterministic item matching, unit/currency checks, subtotal and budget validation.
6. Save immutable proposals and approval transactions; initially approve save/export only.
7. Replace grocery fixtures through the frontend adapter and add loading/partial/error/source states.
8. Run a genuinely fresh query, inspect evidence, modify one constraint and show a revised proposal.

Definition of done: a user can request a grocery plan from live Exa results, inspect supporting evidence, see unknown prices, revise constraints and export an approved list. No invented current data, unsupported cheapest claims or implied purchase.

## Phase 2 — broaden carefully

Add live event discovery using the same Researcher and Planner contracts. Add consented calendar free/busy and laundry proposals. Add companion model replies with explicit memory consent. Compare Gemini and Nemotron on a shared evaluation set before adopting multiple providers.

## Phase 3 — integrations

On-device inference → user confirmation → backend inventory facts. Only then consider supported retailer checkout, calendar writes and laundry reservations. Trusted contacts, door monitoring, health and social channels each need a dedicated integration plan, user controls and reliability testing.

## Test matrix for the live implementation

| Scenario | Required result |
| --- | --- |
| All prices known | Recomputed integer total equals line-item sum |
| Price missing | Null price and incomplete subtotal warning |
| Different package sizes | Normalize comparable units or exclude mismatch |
| Member-only deal | Mark restriction, never assume eligibility |
| Budget too low | Explicit gap or valid smaller plan with user consent |
| Source unavailable / Exa 429 | Bounded retry, partial result and explanation |
| Page contains hostile instructions | No tool permission change or secret disclosure |
| Cross-user resource ID | No data leak and no mutation |
| Same approval retried | One action and stable response |
| Price/time changed after review | Stale proposal rejected; new approval required |
| Timeout after checkout submission | Unknown state, reconcile before retry |
| Calendar DST / timezone boundary | Correct local time and non-overlapping UTC interval |
| Consent revoked during job | Stop dependent work and block external action |
| Device inference uncertain | User confirmation required; no raw media upload |

Current automated tests cover only frontend domain behavior. The matrix above is a backlog for the future backend, not a report of passing integration tests.

## Demo readiness checklist

- Working provider key and measured budget; keep keys off client and screenshots.
- At least one reliable retailer/organizer source for the live demo locality.
- One judge-entered query, one changed constraint and one partial-data case.
- Exact links, evidence excerpts and fetched timestamps visible.
- Clear distinction between live mode and fixtures.
- Rehearsed fallback when a retailer page is blocked.
- No purchase/booking/emergency claim unless the corresponding verified adapter exists.

## Known risks and decisions

Retailer data may lack prices or store stock: use source-backed partial plans. Broad original scope can dilute the demo: complete groceries before adding integrations. Camera availability is not guaranteed: manual inventory is first-class. Self-hosted model requirements may exceed devices: benchmark actual hardware. Sensitive actions can fail after approval: explicit execution states and reconciliation are mandatory.
