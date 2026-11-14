> Current setup: use [local testing](../docs/local-testing.md), [deployment](../docs/deployment.md) and [use cases](../docs/use-cases.md). On Windows run backend/run.ps1 -Port 239 -Reload from the root. The Bash helper below is for Linux/macOS. Both interfaces now have connected Shopping, and the website has live watches. Set DATA_MODE=live to block demo fallback and let users choose their city/chains. SQLite migration adds generic details and source quotes. Older website-fixture-only statements below are superseded.

# Taimi backend

Python (FastAPI) backend covering every feature in `final_function_design.md`, compatible with both existing frontends. It serves the API plus the website (`/`) and the mobile app (`/mobile/`) behind sign-in.

```bash
backend/run.sh            # creates ../.venv on first run, serves http://127.0.0.1:8000
cd backend && ../.venv/bin/python -m pytest -q
```

**Test account:** `test@taimi.app` / `taimi-demo-2026` (change with `TEST_ACCOUNT_EMAIL` / `TEST_ACCOUNT_PASSWORD`). It is seeded with the same fictional data as the mobile prototype.

Configuration lives in `backend/.env` (copy `.env.example`). **Without `EXA_API_KEY` every research endpoint still works with the prototype's demo data, and responses say `"mode": "demo"`.** With a key they return live, sourced results (`"mode": "live"`). `CLOUDINARY_URL` enables the media endpoints. `GEMINI_API_KEY` is optional: it improves chat wording and request parsing and is never used as a search source.

## Frontend compatibility

- **Mobile (`mobile/`)**: `data.js` now reads `USE_BACKEND` from `window.FIGMENT_USE_BACKEND`, which the backend sets only when it serves the page. Opened as static files, the app still runs on its mocks. The six calls it already makes keep their exact request and response shapes: `POST /api/deals`, `/api/explore`, `/api/products`, `/api/medicine`, `/api/wellbeing`, `/api/chat`. Extra fields (`mode`, `notice`, `proposalId`, `unpriced`, `images`…) are additive. `app/static/taimi-bridge.js` loads the first-run state from the signed-in account (`GET /api/v1/state`, same shape as `FigmentAPI.seed()`), redirects to `/login` on 401 and adds "Sign out".
- **Website (`src/`)**: account-connected Groceries and Price watch; other screens are labeled fixtures. Static Node preview is still a fixture-only demo.
- Auth: an HttpOnly session cookie, so the existing same-origin `fetch()` calls work as they are, or `Authorization: Bearer <token>` (from `/api/v1/auth/login`) for native clients.

## Feature map

| Design doc feature | Endpoints (`/api/v1` unless noted) |
| --- | --- |
| Sign-in / log-out / test account | `auth/login`, `auth/register`, `auth/logout`, `/login`, `/logout`, `me`, `me/preferences`, `consents/{scope}` |
| Fridge/storage cameras → shopping list | `devices`, `devices/{fridge,storage}/frames` (mocked frames: milk present → gone), `devices/{key}/scan`, `devices/{key}/observations` (derived detections only, never video), `inventory/regulars` |
| Prioritised shopping list | `shopping/items` CRUD with `expectedVersion` |
| Cheapest deal: any stores / one store / one mall / closest | `/api/deals`, `shopping/deals` (`strategy` = `multi`, `single`, `mall`, `nearest`), `shopping/stores` |
| Order online or print | `shopping/orders` (approval + `Idempotency-Key`, simulated checkout), `shopping/proposals/{id}/print` |
| Grocery run in a free calendar slot, editable | `shopping/trip` (GET/PUT), `shopping/trip/book`, `calendar/events`, `calendar/free-slots` |
| Laundry basket camera → wardrobe runway → loads → reservation | `laundry`, `devices/basket/scan`, `laundry/bookings`, `laundry/wardrobe` |
| Casual chat, consented memories | `/api/chat`, `chat`, `chat/history`, `memories` |
| Background interest research shared from the agent's social account | `companion/posts`, `companion/posts/refresh` (scheduler: at most every 12 h), `social` |
| Call / video chat the agent | `calls` |
| Mental health: ask before reaching out, never encourage harm | crisis/distress detection in chat → care prompt + support lines. `chat/reach-out` requires `confirmed: true` |
| Events and travel with sources, images, social posts | `/api/explore`, `explore` (each result has `sources`, `images`, `posts`) |
| Product search with key features + feedback iteration + photo | `/api/products`, `products/search` (liked/disliked ids → attribute weights. `imageFeatures` from on-device analysis, or a data-URL photo → Cloudinary colour / optional vision) |
| Regular check-in with authentication, escalation with location trail | `auth/challenge`, `safety/checkin` (fingerprint / Face ID challenge or password), `safety/checkin/missed-preview`, `safety/checkin/evaluate` (the scheduler runs this every minute), `safety/locations` |
| SOS: one button, verified, optional type, police option, exact location | `safety/sos`, `safety/sos/active`, `safety/sos/{id}/resolve` |
| Front-door monitoring | `safety/door/events` (on-device detector posts derived events. Loitering rule), `.../review`, `devices/door/scan` (mocked frames) |
| Non-prescription medicine + delivery | `/api/medicine`, `health/medicine` (red-flag symptoms → emergency advice. OTC only), `health/medicine/orders` |
| Appointments from your calendar, ride to hospital | `health/appointments/suggestions`, `health/appointments`, `health/rides/options`, `health/rides` |
| Health device data, caring check-in, meals + activities | `health/vitals`, `health/summary` (anomaly rules + care prompt), `/api/wellbeing` |
| Users worldwide, choose which sites to search | profile `country`, `city`, `siteRegion`, `preferredDomains` → Exa `user_location`, region retailer/pharmacy domains (`app/regions.py`) |
| Cloudinary: rotation video, itinerary image, event teaser | `media/rotation`, `media/itinerary`, `media/event-teaser`, `media` |
| Generic research tasks / proposals (docs/api.md) | `tasks`, `tasks/{id}`, `/clarifications`, `/cancel`, `/proposals`, `/export`, `proposals/{id}`, `proposals/{id}/approve`, `actions/{id}` |
| Price watches (docs/price-watch.md) | `price-watches` CRUD, `/checks`, `/history` |
| Transparency | `usage` (Exa spend ledger), `outbox` (every message sent on your behalf), `bookings`, `dashboard`, `state` |

Interactive docs: `/docs`.

## Exa agent design (and protecting the $50 credit)

Three agents, as in `docs/exa-agents.md` (`app/agents/`):

1. **Coordinator** turns the request into a TaskSpec: intent, region-aware queries, domain filters, missing fields. Queries contain only public search terms: never names, health history or calendar text.
2. **Researcher** makes one Exa `search` per step, with contents inlined: `highlights` plus a **JSON-schema `summary`** that extracts price, date, venue and similar fields from each page in the same call. No separate `/contents` calls, no deep search, `num_results` ≤ 8. At most one refinement (widening from retailer domains to any local page).
3. **Planner** does deterministic ranking and totals in code. A missing price stays unknown (listed in `unpriced`, kept out of the total) and every line keeps its source URL.

Budget guards (`app/exa_client.py`): a shared SQLite cache with a TTL per kind (prices 6 h, events 12 h, evergreen advice 7 d), coalescing of identical in-flight requests, hard caps `EXA_TOTAL_BUDGET_USD=40`, `EXA_DAILY_BUDGET_USD=4` and `EXA_USER_DAILY_REQUESTS=60`, and a ledger of Exa's reported `costDollars` per call. When a cap is reached the API falls back to labelled demo data instead of failing. `EXA_MODE=cache_only` serves only what is already cached, which is useful while judges click around. Background jobs (interest posts, price watches) run only for recently active users, at most every 12 h or at each watch's cadence.

## What is simulated

There are no real payment, delivery, laundry-room, Uber, calendar-provider or SMS/WhatsApp integrations. Those actions return `simulated: true`, and messages land in `/api/v1/outbox` with status `simulated`. Camera and video analysis is designed to run on the device: the backend only receives derived detections, and the demo replays mocked frames. Biometric check-ins accept the one-time server challenge the device signed. Production must verify a WebAuthn assertion.

## Layout

```
app/main.py         app, frontends, CSRF/body-size guard
app/agents/         coordinator, researcher (Exa schemas), planner
app/services/       organiser, laundry, calendar, companion, treats, health, safety, media, tasks, watches, proposals, messaging, home
app/routers/        compat (/api/*), account, organiser, care, research (/api/v1/*)
app/exa_client.py   budgeted cached Exa gateway     app/regions.py  per-country sites
app/db.py           SQLite schema (data/taimi.sqlite3)
tests/              API + live-path tests (fake Exa)
```


Current price validation, saved research/trips and Cloudinary controls are documented in [the workflow](../docs/media-and-trips.md). The website and mobile web app load shared connected watch/Discover modules. Exa and Cloudinary provider calls were mocked during this update.
