# General item comparison and price monitoring

## Product behavior

For any planned purchase—laptop, boots, clothes, concert ticket, train journey or another item—the user can either ask for help choosing or track an already selected variant. The two paths share budget, target, selected sites, evidence and a saved watch. They do not require another agent.

**Implemented frontend:** seven-screen navigation includes Price watch at `/#prices`. Fictional fixtures cover electronics, footwear, clothing and tickets/travel. Users can filter, compare up to three candidates, inspect per-store item/fee totals, save an exact item or open search, change targets, pause/resume/remove, manually simulate checks and inspect history/target alerts. Custom items save without invented matches. There are no website requests, scheduler, email/push or actual purchases.

**Live implementation backlog:** arbitrary item research, configurable retailer/organizer sites, evidence-backed matching, periodic checks, stale states, real price snapshots and notifications. Do not describe the current UI as an operating background monitor.

## Two entry paths

- **Help me choose:** category, optional product phrase, requirements, maximum total, target and site preferences. Return eligible candidates with explainable tradeoffs. Save the criteria while undecided; once chosen, pin a canonical variant. The frontend uses comma-separated substring matching only; live interpretation belongs to the Coordinator.
- **Exact item:** canonical product name/model/SKU or, in the live version, a verified product URL. The user confirms the variant before monitoring. In the demo a full sample name/SKU matches; unknown names save with no quote. Do not substitute a different size, configuration or ticket tier silently.

The prototype is EUR-only and fixtures represent one new/standard-condition variant per item. A future UI should add buy-by date, region, delivery/pickup preference, condition, seller requirements and notification cadence. These fields are not implemented yet.

## What counts as the same item?

| Category | Identity / required match dimensions |
| --- | --- |
| Electronics | Manufacturer model, configuration, RAM/storage, regional keyboard, condition, warranty |
| Footwear | Model, EU/UK/US size system and size, width, color, condition |
| Clothing | Brand/style, size system/size, color, material or edition, condition |
| Tickets | Event/route, date/time/timezone, venue or endpoints, seat/fare category, traveler quantity and eligibility, transfer/refund terms |
| Other | User-confirmed canonical identity and category-specific attributes; absent fields remain unknown |

Keep attributes as versioned structured JSON with category schemas. Preserve seller SKU/GTIN where available, but do not assume every SKU is globally unique. A change of variant is a new candidate, not a price drop. For tickets, exclude invalid resale listings and compare mandatory booking/service fees; availability is short-lived and does not imply a reservation.

## Ranking and alerts

Eligible offer total = item price × quantity + mandatory shipping/service/booking fees + taxes not already included. Require same currency, location applicability, allowed seller, required attributes, known mandatory costs and available stock. Unknown fees produce an incomplete quote and must not win a fully priced ranking. Deduplicate retailer listings; distinguish membership/coupon conditions and new/refurbished/resale offers.

Recommend the lowest known eligible total among retrieved offers, not a globally guaranteed “best price.” Present fit and price separately when the user is undecided. Open-search history can switch candidates: label each snapshot with its product; do not chart it as one SKU's historical price.

The frontend simulation lowers fixture base prices by 4% per check (maximum eight), includes fees, excludes unavailable stores, and adds one local alert when an eligible total first reaches the target. Repeated below-target checks do not duplicate alerts. Changing the target re-arms the demo threshold. Pause prevents checks; remove clears that saved watch. No external notifications are sent.

For live monitoring, compare against the last valid equivalent snapshot, enforce target and maximum budget, deduplicate alerts by watch/rule/observation, apply cooldown and re-arm only after a genuine above-threshold observation. Retrieval failure or unknown price is not an above-threshold observation. Recheck before presenting a time-sensitive deal. Buying still requires a separate immutable proposal and approval.

## Three-agent handoff and scheduler

1. Coordinator converts free text into `ProductSearchSpec` and asks about missing identity dimensions.
2. Researcher discovers original product/seller pages through Exa Search, extracts Contents and stores claim-backed offers with retrieval timestamps. Treat arbitrary product URLs as untrusted input; validate schemes, redirects and network destinations.
3. Planner compares deterministic eligible totals and requirements, explains tradeoffs, and produces the shortlist/watch recommendation.

A deterministic scheduler queues due watches and invokes these same roles; it is not a fourth agent. Start with a user-selected daily cadence, per-watch/task budgets, per-domain rate limits and jitter. Check pause/deletion/consent before enqueue and again before notification. Use job leases, retry/backoff, overlap prevention, and unique watch/scheduled-window keys. Stop after buy-by expiry or explicit purchase. Provider monitor APIs can be evaluated separately; web-content change signals alone do not guarantee a comparable price or stock update.

Exa references: [Search](https://exa.ai/docs/reference/search) and [Contents](https://exa.ai/docs/reference/get-contents). Validate actual fields/quotas at integration time. Keep Exa/model credentials server-side.

## Proposed API additions

| Endpoint | Contract |
| --- | --- |
| `POST /api/v1/product-searches` | Criteria or canonical identity → 202 research task |
| `GET /api/v1/product-searches/:id` | Candidates, eligible/incomplete offers, sources and gaps |
| `POST /api/v1/price-watches` | Criteria/canonical variant, target, budget, sites, cadence, buy-by and notification consent |
| `GET /api/v1/price-watches` | User-owned paginated watches and latest check state |
| `PATCH /api/v1/price-watches/:id` | Expected version + pause/criteria/target; rule change re-evaluated explicitly |
| `DELETE /api/v1/price-watches/:id` | Stop future jobs/deliveries and remove saved watch |
| `POST /api/v1/price-watches/:id/checks` | Idempotent manual refresh → task ID; enforce quota |
| `GET /api/v1/price-watches/:id/history` | Immutable comparable observations with variant, timestamp and source |

Reuse [API](api.md) authentication, ownership, error, version and idempotency contracts. Separate `idle/checking/ready/partial/stale/error` from watch `active/paused/expired` state. A failed check preserves the last quote and labels it stale rather than overwriting it with zero.

## Proposed database additions

- `products`: canonical identity, category, variant-schema version and normalized attributes; no speculative identity merges.
- `product_offers`: product ID, seller, canonical listing URL, applicable region, condition and source claim references.
- `price_observations`: offer ID, task/run ID, item/mandatory-fee/total minor units (nullable), currency, stock, restrictions, observed/fetched/expiry times and evidence IDs. Append-only.
- `price_watches`: user ID, criteria JSON, optional pinned variant ID, target/budget/currency, sites, cadence, next/due/check timestamps, buy-by, status and optimistic version.
- `watch_checks`: watch ID, scheduled window, run ID, result/status and error; unique scheduled-window key.
- `price_alerts`: watch/rule version, qualifying observation ID, state, deduplication key and delivery/cooldown timestamps.

All personal rows include user ownership and composite foreign keys/RLS as in [database](database.md). Index due active watches, observation `(offer_id, observed_at DESC)` and per-user watch lists. Keep alert delivery in a transactional outbox; reconcile uncertain delivery before retry. Removing a watch cancels jobs and notifications without deleting shared public product facts needed by other users.

## Frontend integration and acceptance

Replace `price-model.js` fixtures behind async adapters for search, watches and history. Keep the current form/view flow; add loading/partial/stale/error states, server-authenticated persisted watches, editable real domains, original evidence links and actual notification opt-in. Never label simulated prices as live.

Test each supported category, identity mismatches, shipping reversing the cheapest ranking, unknown fees, out-of-stock deals, exact-only matching, custom/no-match queries, target crossings and recovery, pause/resume, alert deduplication, refresh persistence and multiple users. Ticket tests need date/time/fare mismatches and fees per ticket versus per booking. Verify no purchase or message occurs through a read-only check.
