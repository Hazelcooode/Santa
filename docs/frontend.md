# Frontend implementation

## Current implementation

The frontend is dependency-free HTML/CSS/JavaScript. `index.html` imports `src/app.js`; `src/model.js` contains fixtures, validation and basket calculations. Hash navigation supports direct links such as `/#groceries`. `npm run dev` serves static files at port 239.

Visual direction: warm off-white surfaces, lilac assistant branding, muted peach/green task accents, a CSS mascot and compact source labels. The layout becomes a top navigation on phones. No remote image assets are required. Optional Google Fonts has system fallbacks.

| Screen | Interaction | Current source |
| --- | --- | --- |
| Overview | Navigation, mood → chat, source explanation | Fixtures + current browser list |
| Groceries | Add, check off, filter, compare, print, review and save | Fixture prices + local state |
| Laundry | Review sample inventory, checklist, save slot | Fixtures + local flag |
| Discover | Save/unsave three ideas | Fixtures |
| Talk to Sola | Send text or suggestion chip | Deterministic scripted replies |
| Wellbeing | Local check-in, contact concept, preferences | Browser state, no location |

## State and persistence

`sola-demo-v1` stores item records, comparison mode, plan/laundry flags, memory preference, check-in flag and saved discovery IDs. Data is validated when loaded; invalid storage returns a fresh fixture state. Chat messages stay in memory. Text rendering escapes user input. Prices use integer cents. Newly added items have `unknownPrice: true` and are excluded from the known-price subtotal.

The demo approval is a local Boolean, not a real authorization token. Backend integration must replace it with proposal IDs, versions and action status. The sample calendar is fixed; it does not test schedule conflicts. A demo check-in has no date or expiry semantics; real check-ins need timestamps and timezone-aware rules.

## Integration boundary

Create an `api-client.js` adapter with `getDashboard()`, `listItems()`, `createItem()`, `updateItem()`, `createTask()`, `getTask()`, `getProposal()`, `approveProposal()` and `getSources()`. Return normalized data matching [API contracts](api.md). Views should consume server results rather than importing fixture prices. Keep demo mode an explicit runtime choice and visually distinguish it from live mode.

1. Introduce an asynchronous data store with `idle | loading | ready | partial | error` states.
2. Replace local mutations with authenticated requests and reconcile server versions; retain form values when a request fails.
3. Poll task status using the server's `pollAfterMs` until terminal; stop polling on navigation/cancellation.
4. Render each recommendation's source cards with original URL, excerpt, fetched time, applicability and verification state.
5. Render proposal revision, budget and exclusions in the confirmation dialog. On `409` fetch the new proposal and require review again.
6. Show success only after server confirmation. Disable repeated approval while pending and supply an idempotency key.

A future React/Vite migration is optional; reuse the domain model, screen hierarchy and CSS tokens. Add a bundler only when component complexity justifies it.

## Accessibility and edge states

Use semantic navigation, visible focus, labeled inputs, native dialog focus management, live status announcements and reduced-motion support. Navigation has icon accessible labels through links; the active screen uses `aria-current`. Keep main headings readable and restore useful focus after asynchronous updates. Verify contrast with an automated audit before production; subtle small metadata text needs particular review.

For live work handle: no items; all items bought; no source matches; rate limits; unpriced items; stale quote; budget impossible; offline mode; calendar permission absent; action pending, failed or unknown. Provide retry and manual alternatives. Never hide unknown prices behind a complete-looking total.

## Verification

Run `npm run check`, `npm test`, `npm run build`. In a browser test all six screens at desktop and 390 px width, keyboard navigation, Escape closing dialogs, refresh persistence, input escaping, reset, print preview, zero-item list and unpriced-item review. Backend and provider tests are future work; the existing tests cover calculation and input/state recovery only.
