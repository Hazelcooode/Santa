# Current shopping, event and price-list behaviour

Implemented on `current_world`. This document supersedes earlier notes about automatic grocery lookups, restoring event research history and unnamed watch shortlists.

## Groceries

- Adding or editing an item saves it only. New/identity-changed items show **Price unknown** until the user chooses **Update prices**. The add button no longer promises an automatic lookup. Legacy `AUTO_PRICE_LOOKUP` does not enable a lookup from these routes.
- Changing **Lowest known item prices / One store** immediately compares current saved quotes, including in nearby-shop mode, without starting a new item or shop search. The selected basket shows shop groups, quantity × unit price, line totals and a known total. Unknown items remain unpriced; a partial basket is not presented as complete.
- Each item row displays the quantity-adjusted line total, with its unit price and multiplier underneath. Six individually priced bananas use six times the per-item quote; six packages use six times the full-package quote. A kg/l quote is not silently treated as a piece/package price. The user should describe the required package size or purchase unit when it matters.
- Product thumbnails are larger. Expanded source entries have clear separators.
- Every explicit attribute must be evidenced exactly (case/spacing/unit typography are normalized). Positive AI matching cannot bypass these checks. Structured attribute checks bind values to their keys; numeric fat percentage cannot be justified by a protein percentage. Category/aisle is included in the complete search requirements and checked as product identity, so seasoning for ground beef cannot qualify as ground beef. Missing evidence produces an unknown price and a reason, not a substitute.
- Complete requirements are included in the extraction prompt even when the shorter search query is truncated. New quote-context version 3 excludes older, less strictly validated quotes until the user explicitly refreshes them.

## Events and trips

Saved trips start collapsed. Their header shows name, event count, copy summary, calendar export, Print/Save PDF and an expand/collapse arrow. Event details, media controls and generated images are inside the collapsed section.

Unsaved research is not written to the research-history table and is not restored in the UI. The old Saved research outputs selector is removed. Short-lived server references (30 minutes, bounded in memory, scoped to the account) exist only to let the user explicitly save chosen events into a trip. The list-history endpoint returns an empty list. Existing explicitly saved trip snapshots remain available. To get an old unsaved output again, submit a new prompt. Switching sections clears the current event results, draft prompt and staged selection. Old research-history database rows are not exposed or reused.

### Illustrated schedule images

**Create themed schedule image** builds a colourful vector timetable from the selected events' title, description, tags, schedule, venue and price. It chooses an illustrative AI/science, culture/music, nature or general-adventure theme from that information. It never uses an event photo. The Python Cloudinary SDK uploads the generated SVG and delivers its PNG rendition. This is procedural themed illustration, not a photorealistic generative-model image.

Existing schedule images are not regenerated automatically; click **Recreate themed schedule image** to replace an old card. Source-photo event videos remain a separate feature, with the existing three-events-per-trip limit and truthful animated-photo labels.

## Named price lists and temporary research

1. Fill in a price prompt and choose **Research prices**. The request creates no saved watch/list. Results and source diagnostics exist only in the current page response.
2. Enter a required list name and choose **Save best 1 / 5 / 10**. The server verifies the short-lived signed research proof, then stores only the selected list, its exact prompt/settings and update interval. Changing another account's proof or modifying its contents cannot create a list. Proofs expire after 30 minutes and after a server restart.
3. Each saved list has **Rerun prices manually**, its own update interval (0 = manual only), pause/resume, editable-as-new prompt and price history. Reruns update the saved list's configured number of best matches. Successful observations remain history; rejected-source diagnostics do not enter saved watch JSON or check history.
4. Starting to edit the prompt clears its previous output/diagnostics. Navigating to another application section clears prompt drafts, diagnostics and unsaved results. Returning shows saved lists, not the last temporary search. A saved prompt is displayed separately and can be explicitly loaded as a new search.
5. Legacy diagnostic and unsaved-offer fields are discarded on backend startup. Existing explicitly saved options and price observations are retained. Legacy watches without a list name remain accessible under their original query.

Source URLs for explicitly saved successful quotes are retained for product links/history. Temporary rejected-source diagnostics are not persisted. The existing Exa budget ledger and shared retrieval cache remain operational; they are not a restorable frontend research history.

### Cloudinary product studio

All grocery and watch product photos now use uploaded Cloudinary assets with background removal, mild enhancement and transparent 640×640 padding. Original merchant photos are never a UI fallback. Missing watch photos use the static sad Sola mascot. Pending cutouts are retried before falling back.

**Preview in your space** is a list-level action on current research and saved lists. Choose one app-found product and upload one environment photo. The browser resizes/re-encodes it before uploading. Cloudinary generates a contextual replacement or addition with approximate proportions. Only viewing/downloading is offered; there is no account gallery. Closing, Escape or navigation revokes access and requests deletion; abandoned sessions expire after 15 minutes and failed provider deletions are retried.

**Generate 3D turn** requests AI object yaw 45° left and right with a fixed camera. The four-second generated motion is accelerated into a three-second MP4. Unseen geometry is inferred, not measured. The old flat/mirrored image animation is removed. Generation is user-requested and temporary, not persisted on a watch.

See [Cloudinary studio](cloudinary-studio.md) for setup, privacy, add-on permissions, APIs, cleanup details and use cases. CLOUDINARY_URL alone does not activate the required generation add-ons. Real API outputs have not been tested.

## API and persistence changes

| Endpoint | Purpose |
| --- | --- |
| POST `/api/v1/shopping/deals` | Defaults to `cachedOnly: true`; compare saved quotes without research |
| POST `/api/v1/price-watch-research` | Unsaved price research, temporary diagnostics and a signed save proof |
| POST `/api/v1/price-watch-lists` | Requires `name`, `count`, `saveToken`; accepts per-list cadence |
| GET `/api/v1/media/{id}/playback` | Owned, inline range-capable video stream |

`shopping_quotes.price_basis` is an additive SQLite column. The backend migrates the existing file on startup; there is no separate database service. Watch JSON stores names, selected options and prompts, but no new diagnostics or unsaved last-result arrays. Event draft references are held in memory only. The static preview follows the same interaction rules using fictional data and browser-local explicitly saved lists/trips; media generation still requires the backend.

## Run and verify

Restart the backend and hard-refresh the browser:

```powershell
.\backend\run.ps1 -Port 239 -Reload
```

For an old grocery quote, explicitly choose Update prices to collect the new stricter evidence. For an old schedule card, explicitly regenerate it. Price lists retain their own manual/automatic update interval.

Offline validation uses fake Exa/Cloudinary responses, temporary databases and mocked video bytes. Regression checks cover identity/attribute binding, no auto-lookup on item changes, saved-quote strategies and quantities, temporary output lifetime, named-list ownership/proofs, no-photo themed schedules, video range/MIME handling, collapsed trips and static sad mascots. Browser checks use a disposable fictional-data preview. External provider results were not tested.

Cloudinary reference: [background removal](https://cloudinary.com/documentation/background_removal). Background removal does not support fetched images; the backend uploads product sources first.


Latest UI update: [preview modes and compact shopping UI](frontend.md#preview-modes-and-compact-shopping-ui). Cloudinary placement now separates clothing/paired-shoe try-on, room items and other contexts, prioritizes generation quality and preserves photo orientation. Object turns start on warm beige. Shop totals expand to text-only item breakdowns, with missing quotes crossed out. The main basket total sits below the item results.
