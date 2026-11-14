# Current price, saved-trip and Cloudinary workflow

This describes the implemented Python/FastAPI + SQLite release. No new external service is required for persistence. Exa is still a tool inside the Researcher in the existing three-agent pipeline; hosted Exa Agent is not enabled by this change.

## Run locally

From the project root in PowerShell:

```powershell
.\backend\run.ps1 -Port 239 -Reload
```

Open `http://127.0.0.1:239/` for the website, `/mobile/` for the mobile web interface and `/docs` for interactive API documentation. Do not run the static Node server on port 239 at the same time. Restart the backend and reload the browser after updating. A hard refresh may help an already open client. SQLite tables are created additively; there is no separate database process to start.

Configure `EXA_API_KEY` and `CLOUDINARY_URL=cloudinary://API_KEY:API_SECRET@CLOUD_NAME` in `backend/.env` or the root `.env`. The server loads these; never put them in frontend code. Restart after changing credentials. `CLOUDINARY_FOLDER` optionally sets the asset folder. Cloudinary media is generated only when the user clicks a media button. Normal browsing and saved results do not trigger generation. Account settings/permissions and transformation limits still apply.

## Grocery prices

1. Choose your own city/country and currency under Groceries. Choose **My selected websites** and enter domains, or explicitly choose **Discover grocery shops in my city**. Discovery finds up to five publicly evidenced grocery retailer websites for that city. It is not an exhaustive directory of all shops or live stock in each branch. A failed discovery asks for manual websites instead of guessing chains.
2. Every item is researched separately for each selected/discovered retailer domain. Expand **Shops searched** to see coverage and provider/budget failures. Quotes from several stores are retained; the item summary shows the cheapest matching package, and comparison strategies can select a basket.
3. Source extraction must provide a displayed `price_text`, a `price_basis` and currency. Python parses the displayed amount with Decimal and converts to integer minor units once. A numeric model value of 249 with displayed `2,49 EUR` saves 249 cents, not 24,900. Ambiguous split typography, ranges, missing basis, and kg/l prices are rejected. The app does not estimate a package price from uncertain weights. Conditional membership, installment and multibuy offers are excluded by the extraction request.
4. Old quotes from before the validation change remain in SQLite for audit but do not qualify for the new quote context. Refresh to collect new package-price evidence. There is no blind factor-of-100 rewrite of saved data. The grocery navigation badge has been removed.

Lookups remain bounded by the existing Exa budgets and request quota. Per-shop coverage uses more calls than one combined search. A denied or inaccessible shop stays unpriced, with an explanation. Delivery, travel and local branch stock are outside the known subtotal.

## Price watch and product media

1. Create a watch with a product/type, requirements, city/country and currency. Websites are optional; an empty list searches the open web within your location scope. Add websites to restrict results.
2. **Check prices** requires an explicit full-item display price and evidence that the exact option is available to purchase now. Unknown availability, sold-out and preorder options are excluded. Availability is a source claim at check time and may change before checkout.
3. Up to ten successful options, including image/source links, are stored in the watch. All accepted options create price observations for that check, rather than just the cheapest. Your latest successful output is restored after sign-out/sign-in. A miss retains the earlier output with its original timestamp.
4. Use **Save best 1 / 5 / 10** to keep that many available results (or fewer if fewer were found), ordered by full-item price. The saved selection survives later checks. This replaces that watch's saved selection; latest results and observation history remain separate.
5. Each saved option has **Create photo rotation**. The Python backend first tries Product JSON-LD and Open Graph image URLs from the source product page, with existing Exa image URLs as a fallback. Remote HTML reads are bounded; private/local addresses and unsafe redirects are rejected. The source must make photos accessible.
6. Cloudinary's Python SDK uploads normalized frames and assembles an MP4. Multiple photos create a gallery animation (photos may have different camera angles). One photo creates an explicitly labeled 2D animation. It does not reconstruct the unseen back of a product or claim to be a verified 360-degree view. A true turntable needs properly ordered multi-angle photos or a 3D asset. Playback and the generated link are saved with the option.

History is monitoring from the first successful observation onward, not a backfill of past retailer prices. Earlier observations remain as recorded and may predate the stricter validation rules. Recent check attempts (up to 20) are shown separately.

## Events and combined trips

1. In **Discover**, enter a prompt such as `Copenhagen, Christmas markets`. The search no longer appends the home city to a nonempty prompt. An optional destination/country override and date interval make the target explicit. Home-country search bias is removed for a prompt-selected destination unless an explicit destination country is supplied.
2. Structured extraction must confirm the event's location matches the request. Nonmatching locations are excluded. Event start/end dates and local times are extracted separately from publication dates. Ongoing date-range events are allowed until their end date; missing times/prices remain unknown.
3. Research outputs are saved automatically to your account. Choose them again under **Saved research outputs** after signing back in. Tick events across different searches, enter a trip name and press **Save selected events as a trip**. One selected event saves a standalone event plan. Up to eight unique events/options can form one plan, ordered by known start dates. You still need to choose a visit time within an opening window and review travel feasibility.
4. Saved trips retain titles, dates/ranges, times, price text/currency where provided, venue, images and source links. They are plans, not bookings. Unknown prices are not added as zero to a fabricated trip total.
5. Press **Create schedule image** for a Cloudinary-rendered PNG card with a real source hero image when available, schedule rows and source price text. Click the image/link to open it for sharing.
6. Tick **Include in event video previews** for 1–3 events with source photos, then request previews. Cloudinary creates short vertical photo-motion clips, a poster and slideshow using the Python SDK and transformations. These illustrate actual source imagery; they are labeled animated photos, not footage of the event taking place. Events without real photos cannot be selected. At most three distinct events per saved trip can have previews, including clips generated earlier. Retrying reuses completed clips. Generated media stays on the saved trip after sign-in.

## Jury walkthrough

Research events in the destination you choose, select three events across searches, save one named trip, generate its schedule card and three source-photo previews. Then open a saved product watch, show several priced/available options and request a product-photo rotation. The judge can inspect original event/product sources alongside the generated media. This connects research, decision-making, persistence and meaningful Cloudinary transformations in one flow.

## Offline validation and limits

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests -q
npm test
npm run check
npm run build
```

Tests replace Exa and Cloudinary with local fakes, blank provider keys and use a temporary database. The frontend rendering tests stub fetch. No real provider calls were made for this update. Real retailer extraction, remote photo permissions and Cloudinary delivery/rendering still need a later test with your configured account. Some Cloudinary transformations can be pending while their first derived asset renders.

Official transformation reference: https://cloudinary.com/documentation/transformation_reference#zoompan

## New persistence and endpoints

- `research_searches`: account-owned query/kind/output snapshots.
- `saved_itineraries`: account-owned selected source snapshots plus schedule/teaser assets.
- Existing watch JSON: `lastOffers`, `savedOptions`, `pricingVersion`, bounded check attempts and diagnostics. All qualifying options are inserted into existing `price_observations`.
- Existing `media_assets`: generated Cloudinary URLs/metadata, owned by the user.

| Method | Endpoint | Purpose |
| --- | --- | --- |
| POST | `/api/v1/price-watches/{id}/options` | Save best 1/5/10 from last successful output |
| POST | `/api/v1/price-watches/{id}/options/{optionId}/rotation` | Generate product photo animation on request |
| GET | `/api/v1/research-searches` | Restore up to 50 recent research outputs |
| GET, POST | `/api/v1/itineraries` | List/create saved event/trip plans |
| DELETE | `/api/v1/itineraries/{id}` | Remove a saved trip |
| POST | `/api/v1/itineraries/{id}/media` | Generate schedule or up to three event teasers |

All source/output lookups are scoped to the signed-in user. The three-event media limit is serialized per plan for the single-worker SQLite deployment. Deleting a trip removes its plan; generated Cloudinary assets remain in the media library (no implicit paid-provider deletion).
