# Use-case scenarios

This guide covers every user-facing feature family. The [route index](api-route-index.md) enumerates every current API operation, including CRUD variants. Use `/docs` for endpoints not connected to a UI control. “Real” means the actual API or database path; it does not certify provider data or external delivery.

Start with a fresh account, `DATA_MODE=live`, explicit city/chains, and credentials as described in [local testing](local-testing.md). Use the seeded account only to test fixture-dependent features. Never treat simulated emergency functionality as operational assistance.

## Account and configuration

| Function | Scenario and steps | Expected result / current boundary |
| --- | --- | --- |
| Create account | Open `/register`, supply your email, password, name, city and country. | New account/session; shopping list and price history start empty. Grocery websites are not auto-selected. |
| Sign in/out | Sign in at `/login`, load both interfaces, then Sign out. | Same-origin session cookie; authenticated endpoints reject after logout. |
| Profile/preferences | In `/docs`, PATCH `/api/v1/me/preferences` with your city, country, timezone and optional preferred domains. | Account preferences persist; grocery research separately uses explicitly saved shopping settings. |
| Consent | Grant then revoke a scope through `/api/v1/consents/{scope}`. | Database records the choice; dependent services enforce supported scopes. Consent does not authorize a purchase. |
| Provider readiness | Open `/integrations`; check each configured provider. | Safe configuration report plus manual connectivity result; no secrets returned. Exa/Gemini checks may use credits. |
| Usage/budget | Query `/api/v1/usage` before and after a research request. | Request ledger, cache hits, provider cost or estimate and configured caps. |

## Shopping and household organisation

| Function | Scenario and steps | Expected result / current boundary |
| --- | --- | --- |
| Choose search location/chains | Groceries/Shopping → search settings. Enter city, country, currency and domains you choose. | Persists on the account. Invalid domains are rejected; changing context invalidates prior active quotes. |
| Add a specific product | Add `Chips`, brand `Estrella`, details `sour cream onion`, attribute `package=200 g`, quantity 2. | Saves generic fields in SQLite; best-effort automatic lookup starts if enabled/configured. No category-specific form is required. |
| General attributes | Add boots with `size=EU 42`, `color=black`, or a laptop with `RAM=16 GB`. | Same key/value mechanism; exact required values must appear in product identity before a quote qualifies. |
| Automatic pricing | Save a new/changed item after choosing shops and providing Exa credentials. | Researches the item, reusing valid cache, and appends source-backed quotes. Provider failure never prevents saving the list. |
| Manual price update | Click Update prices after editing the list. | Bypasses app cache, requests fresh Exa content, stores quote history and shows missing-price states. Up to 32 items per refresh, eight per research batch. |
| Persist/reload quotes | Research an item, refresh the page and sign in again. | Exact-item quotes remain with URLs, fetched/expiry times and cache labels; values are not regenerated from fixtures. |
| Edit product identity | Change Estrella to another brand or change flavour/package size. | Incompatible quotes leave the active estimate; new lookup can run. Existing history is retained. |
| Priority/quantity/bought/delete | Edit priority or quantity, mark bought, undo, then remove an item. | Mutations persist on the account with optimistic versions; bought/deleted items are excluded from the current list estimate. |
| Compare across stores | Choose lowest known item prices, then one store. | Deterministic sourced subtotal for eligible prices, plus unpriced items and excluded delivery/travel costs. |
| Nearest/mall strategy | Request nearest or same-centre shopping without measured distances/centre metadata. | Explains the missing metadata instead of inventing proximity or grouping. |
| Print | Compare a list and open Print this sourced plan. | Printable server proposal with sources; no checkout. |
| Order online | Test `/api/v1/shopping/orders` with a proposal and idempotency key. | **Simulated** order/booking. No retailer payment or delivery occurs. |
| Device inventory | POST confirmed derived detections through `/devices/{key}/observations`. | Database observations update supported regular essentials. Raw private footage is not required. |
| Camera replay | Call `/devices/{key}/scan` or try the prototype camera control. | **Mocked** frames/detections; not real computer vision. Some mobile controls remain local demo interactions. |
| Regular essentials | Read `/inventory/regulars`, submit low-stock detections for a configured regular item. | Missing/low items are added or reprioritized; scan rules operate on submitted facts. |
| Grocery trip | Read/update `/shopping/trip`, inspect conflicts and call `/shopping/trip/book`. | Saves an event in the app's calendar. **No Google/Outlook calendar-provider sync**. |
| Calendar CRUD | Add a busy interval, request free slots, then delete it through `/calendar/*`. | SQLite-backed intervals, timezone-aware free/busy calculation. |
| Laundry planning | Read `/laundry`, change wardrobe counts, inspect runway and choose a slot. | App planning/state works; wardrobe observations are supplied/mocked. |
| Laundry reservation | Create/cancel `/laundry/bookings`. | App booking record; **no real laundry-machine reservation service**. |

## Research and price monitoring

| Function | Scenario and steps | Expected result / current boundary |
| --- | --- | --- |
| Open product search | Mobile Products or `/products/search`: ask for an item, requirements and budget. | Live Exa-sourced candidates when available. Unknown prices show unknown, not zero-cost deals. |
| Iterate with feedback | Like/dislike candidate IDs, repeat the product query. | Stored candidate attributes influence the next ranking. |
| Reference image/features | Submit `imageFeatures` or deliberately provide a permitted reference product image. | Derived features can steer search; an uploaded image may invoke Cloudinary/Gemini. Private camera footage is kept out of this flow. |
| Create an open watch | Website Price watch: describe an undecided purchase, details, city/country, sites, target and cadence. | Saves account-backed criteria rather than pinning a fixture product. Any item category can be described. |
| Create an exact watch | Choose Exact item and specify full model/variant plus details. | Qualifying offers must match name/detail terms; missing/ambiguous variants remain unquoted. |
| Manual watch check | Check prices on an active watch. | Runs research, saves the best qualifying item-price observation, exposes sources and last-check state. Fees/stock are not guaranteed. |
| Target alert/history | Set a target, check an offer below it, inspect history. | In-app alert and immutable observations; **no push/email/SMS**. |
| Pause/remove watch | Pause, attempt a check, resume, then remove. | Paused checks are rejected; active due watches are scheduled while the server runs. Removal deletes owned watch history. |
| Expired watch | Set a past buy-by date and check. | Returns an expired-watch error; no silent monitoring continuation. |
| Events | Search a real topic/date/location through Mobile Explore or `/explore`. | Sourced event candidates, images and available public metadata; live mode fails clearly if retrieval is unavailable. |
| Travel | Ask for a destination, then inspect transport/stay/activity results. | Research suggestions only; **not live booking inventory or a ticket purchase**. |
| Generic research tasks | POST `/tasks`, poll its ID, inspect proposal, approve saving/export. | Three-agent trace and persisted task/proposal. Jobs are in-process and may need retry after restart. |
| Cancel research | Cancel a task before completion. | Cancellation is retained; an in-flight provider request may finish, but no later proposal should replace the cancelled task. |
| Proposal approval/retry | Approve the same proposal twice with the same idempotency key. | Stored action replay; changed/expired proposal requires a new review. External-action adapters remain simulated. |

## Companion, health and safety

| Function | Scenario and steps | Expected result / current boundary |
| --- | --- | --- |
| Conversation | Send a chat message, with optional Gemini configured. | Server-backed response/history; model wording is optional and facts use Exa where supported. |
| Memory | Explicitly opt in, state a preference, inspect/remove memories. | Supported preferences persist; opting out blocks new memory storage. |
| Interest discoveries | Refresh `/companion/posts`, inspect sources. | Sourced interest suggestions with bounded cadence; **social posting is simulated**. |
| Social linking / call | Try `/social` and `/calls`. | **Simulated** account/call state; no OAuth connection or actual call. |
| Distress support | Test the companion's care-prompt flow with a non-sensitive test message; decline outreach. | Support-oriented prompt, no automatic external contact. The app is not a crisis-response system. |
| Consented outreach | Submit `confirmed: true` to `/chat/reach-out`; inspect `/outbox`. | **Simulated** message in the outbox, not delivered to another person. |
| Wearable samples | POST test measurements to `/health/vitals`, read `/health/summary`. | App stores supplied data and computes simple rules. **No wearable integration or diagnosis**. Seeded account metrics are fixtures. |
| Meals/activities | Request `/health/wellbeing` using a mood. | Sourced suggestions when available; not medical treatment. |
| Medicine research | Use `/health/medicine`, inspect product/source/OTC fields. | Information search only; verify with a pharmacist. Orders are **simulated**, not pharmacy fulfilment. |
| Appointments / ride | Read suggestions and create an appointment/ride record via `/health/*`. | **Simulated** clinic/transport booking; no provider dispatch. |
| Check-in | Request auth challenge then confirm `/safety/checkin`. | Local account check-in. Demo biometric method is not WebAuthn; production requires password verification. |
| Missed check-in | Configure a short test interval, inspect missed preview/evaluate. | **Simulated** escalation/outbox; no guaranteed contact delivery. |
| Contacts/location | Add a test contact and submit a consented location; revoke the consent and retry. | Ownership/consent-scoped app data. No real contact verification invite or location-device integration. |
| SOS | Submit a test SOS with password verification, inspect active status, resolve it. | **Simulated** incident/outbox, no police/emergency dispatch. The UI must never be relied on for emergency assistance. |
| Door events | Submit derived test detections, review a flagged event. | Rule-based app event; **camera inference and alert delivery are simulated**. |
| Daily tree | Complete prototype daily tasks. | Visual local progress decoration; not proof that external chores were completed. |

## Cloudinary and operations

| Function | Scenario and steps | Expected result / current boundary |
| --- | --- | --- |
| Media connectivity | Integration page → Cloudinary → Check connection. | Read-only credential/access verification; no upload. |
| Itinerary image | `/media/itinerary` with a title and permitted schedule text. | Cloudinary canvas/overlay URL and a saved media record; open the output to verify rendering. |
| Event teaser | `/media/event-teaser` with public permitted event photos. | Cloudinary slideshow/poster/clip URLs; account transformation support may vary. |
| Product rotation | `/media/rotation` with multiple genuine product angles. | Stitched media; a one-photo spin is labeled an effect and does not invent real unseen surfaces. |
| Media gallery | GET `/media` after generating assets. | Account-owned saved media outputs. |
| Backup/restart | Back up SQLite, restart, reload saved shopping/watch data. | Durable records survive; interrupted in-process jobs need retry. See deployment instructions. |
| Live failure | Remove a key in an isolated test configuration or exhaust a tiny test cap. | Explicit failure/unknowns with `DATA_MODE=live`; no synthetic replacement quote. |

The honest release boundary is intentional: working research, persistence and media plus testable, clearly simulated external actions. A real checkout/SMS/calendar/ride integration needs an actual provider contract and adapter; no API-key-only switch for those exists.

## Added scenarios: manual watches and multiple markets

| Function | Scenario | Expected behavior |
| --- | --- | --- |
| Manual-only watch | Set Check every to 0, save, then use Check prices. | Manual checks work; the scheduler never starts a new check for that watch. |
| Change an existing schedule | Set its interval to 0 and choose Save schedule, then later choose 24. | Database preserves zero instead of replacing it with 24; switching back re-enables scheduling. |
| EU search | Keep a real home country, choose European Union scope and your desired shop domains. | Query uses EU market guidance without sending EU as a country code. |
| Multiple countries | Choose Selected countries, enter FI, DE, NL and sites from those markets. | Searches retain all supplied domains without home-country bias. Only same-currency quotes enter a total. |
| Rejected request | A fake provider rejects the schema with HTTP 400. | Clear non-retryable error, no fake replacement prices and no repeated schema-invalid requests. |


## Explaining a failed or empty price check

1. A user adds Chips, brand Estrella, attribute `flavour=hot honey`, chooses their own city and shop domains, and refreshes prices.
2. The Researcher requests product-specific structured evidence. If only category pages are found, it makes one targeted refinement on the same domains. A verified translated product name can match; a category page or unverified flavour cannot.
3. The UI either shows a sourced saved quote or the excluded-page reasons. Old saved quotes remain available and unpriced items stay out of the subtotal.

## Exploring a product and reading history

1. A user watches a laptop with NVIDIA 50xx GPU and 16 GB system RAM, selects websites and requests a manual check.
2. Extraction assesses product type, model family and RAM, distinguishing RAM from VRAM. It must quote supporting page text. Matching offers are ranked by price in the selected currency.
3. History shows the first successful saved quote onward. A later search with no match adds a check attempt without creating a price point. A provider failure is shown as an error. This is monitoring from now onward, not a retrieval of past retailer prices.


## Package prices, saved options and media walkthroughs

For detailed scenarios for multi-shop groceries, opt-in nearby discovery, available watch offers, Save best 1/5/10, restored event searches, multi-search trip plans and Cloudinary schedule/product/event media, follow [the current workflow and jury walkthrough](media-and-trips.md). This supersedes the earlier requirement to enter websites for every watch and the earlier best-price-only observation behavior.


Latest behaviour: [manual grocery pricing, strict attributes, temporary research and named lists](current-behavior.md). This supersedes earlier automatic-lookup and restored-research descriptions.
