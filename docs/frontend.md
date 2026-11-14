> Connected-mode update: FastAPI-served Groceries, Price watch, Discover and account Chat use api-client.js, live-shopping.js and live-watches.js. Mobile Shopping shares live-shopping. User-selected city/chains, generic details, automatic lookup, Update prices, persisted quotes and provider checks are implemented. Static mode retains fixtures. See [local testing](local-testing.md) and [use cases](use-cases.md).

# Frontend implementation

## Current implementation

The frontend is dependency-free HTML/CSS/JavaScript. `index.html` imports `src/app.js`; `src/model.js` contains fixtures, validation and basket calculations. Hash navigation supports direct links such as `/#groceries`. `npm run dev` serves static files at port 239.

Visual direction: warm off-white surfaces, lilac assistant branding, muted peach/green task accents, a CSS mascot and compact source labels. The layout becomes a top navigation on phones. No remote image assets are required. Optional Google Fonts has system fallbacks.

| Screen | Interaction | Current source |
| --- | --- | --- |
| Overview | Navigation, mood → chat, source explanation | Fixtures + current browser list |
| Groceries | Add, check off, filter, compare, print, review and save | Fixture prices + local state |
| Price watch | Explore/exact matching, store totals, shortlist, saved watches, target editing, pause/resume, manual simulated checks and history | Multi-category fixtures + browser watch state |
| Laundry | Review sample inventory, checklist, save slot | Fixtures + local flag |
| Discover | Save/unsave three ideas | Fixtures |
| Talk to Sola | Send text or suggestion chip | Deterministic scripted replies |
| Wellbeing | Local check-in, contact concept, preferences | Browser state, no location |

## State and persistence

`sola-demo-v1` stores item records, comparison mode, plan/laundry flags, memory preference, check-in flag and saved discovery IDs. Data is validated when loaded; invalid storage returns a fresh fixture state. Chat messages stay in memory. Text rendering escapes user input. Prices use integer cents. Newly added items have `unknownPrice: true` and are excluded from the known-price subtotal.

The demo approval is a local Boolean, not a real authorization token. Backend integration must replace it with proposal IDs, versions and action status. The sample calendar is fixed; it does not test schedule conflicts. A demo check-in has no date or expiry semantics; real check-ins need timestamps and timezone-aware rules.

## Price-watch implementation

`src/price-model.js` owns the catalog, integer-money parsing, requirement matching, eligible offers, watch lifecycle and storage validation. `src/price-watch.js` owns the `/#prices` view and its delegated events. The app integrates this module through the existing render/dialog/toast helpers. No dependencies or backend were added.

`sola-price-watch-v1` stores up to 50 watches separately from existing state, preserving older grocery/demo storage. Reset clears both keys. Each watch contains criteria, optional pinned product ID, selected sample sites, target, pause state, synthetic check index, bounded history and bounded alerts. Search-form edits are applied by comparison/save actions; current search and shortlist are session-only.

The catalog spans electronics, footwear, clothing and tickets, while arbitrary named custom items can be saved with no fabricated quotes. Exact names/SKUs bind a variant; explore mode uses category, substring query, comma-separated required phrases and total budget. Delivered total includes fixture fees and tax; unavailable offers are excluded. Up to three products can be compared side by side in a dialog. These are mechanical fixture matches, not model recommendations.

Only explicit Simulate check advances a watch, lowering sample prices by 4% of the base for up to eight steps. A target crossing adds one local alert; repeated checks below target do not duplicate it. Paused watches do not advance. Changing target clears previous alerts and re-arms evaluation. History is synthetic and labels the matched product for open searches. Refresh restores watch state, but no task runs on a timer or after closing the page. See [price-watch specification](price-watch.md).

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

Run `npm run check`, `npm test`, `npm run build`. In a browser test all seven screens at desktop and 390 px width, keyboard navigation, Escape closing dialogs, refresh persistence, input escaping, reset, print preview, zero-item list and unpriced-item review. Backend and provider tests are future work; the existing tests cover basket calculations, input/state recovery, cross-category matching, exact variants, fee-aware offer ranking, unavailable offers, threshold alerts, pause behavior, unknown quotes and watch persistence. Browser checks should also exercise category/mode controls, shortlist limits, target edits and refresh.


## Price lookup diagnostics (current implementation)

The account-connected shopping UI (shared by desktop and mobile) shows **Price lookup details** for excluded results. Accepted quote sources are separate from inspected pages: a category page is never presented as evidence of a saved item price. A zero known subtotal with unpriced items does not mean those items are free.

Watches show the last check notice and **Why pages were excluded**. History displays saved quotes and up to 20 recent check attempts separately. `no_matches` means research completed but did not produce a qualifying quote. `error` means the provider failed; `stale` means a previous quote exists but no new matching quote was found. The latest saved quote is retained. Restart the backend and reload both clients after updating code.


## Saved outputs, trip builder and media controls

Discover clears unsaved research on navigation and restores only explicitly saved trips, initially collapsed. Saved trip details contain themed schedule posters and up to three event teasers. Price watch saves named lists and their prompts/schedules; current input and diagnostics are temporary.

Product photos use Cloudinary background removal, enhancement and equal 640×640 padding. The UI never uses an original merchant photo as a fallback. `product-images.js` retries pending cutouts; missing watch photos show the static sad mascot.

`space-preview.js` provides a native modal, opened by **Preview in your space** at list level. Select one app-found product, upload one environment photo, generate, view/download and close. Browser preprocessing limits image dimensions and removes metadata. No uploads or generated results enter localStorage. Escape, closing, page exit and `unmountWatches` clear object URLs and request deletion. If a create request completes after close, its returned session is immediately closed too.

Each product also has **Generate 3D turn**, using the same temporary session UI without a room upload. The player uses the owned same-origin stream with inline MP4 playback. AI proportions and unseen sides are explicitly approximate. See [Cloudinary studio](cloudinary-studio.md) for service setup, limits and cleanup semantics.


Current UI: see [the screenshot-based redesign](ui-redesign.md) for shared layouts, static/connected modes, individual-event filtering and itinerary exports.


Latest behaviour: [manual grocery pricing, strict attributes, temporary research and named lists](current-behavior.md). This supersedes earlier automatic-lookup and restored-research descriptions.


## Preview modes and compact shopping UI

The preview dialog now offers Clothing/shoes, Room item/furniture, and Other placement, with optional user instructions and a prominent AI-quality warning. Room and clothing prompts are separate; paired shoes are treated as a pair when both feet are visible. Object turns use a beige Cloudinary-prepared start frame and a matching background prompt.

The app has one account/preferences control in the sidebar. Version, session/date strip and the global backend banner are removed; simulations remain labeled in the relevant flows. Groceries removes the percentage-comparison hero card and moves the known basket total below item results. Each shop basket expands to a compact image-free list of the lowest current per-item quote, quantity-adjusted amount and merchant link. Missing quotes are crossed out and labeled No current quote. Shops are grouped by website hostname rather than inconsistent extracted store labels; partial totals remain distinguished from complete baskets.
