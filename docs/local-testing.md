# Run and test with real inputs

The runnable backend is FastAPI + SQLite. Planning documents describing PostgreSQL are not the current runtime. Both interfaces are served by FastAPI; `npm run dev` is an independent fixture-only preview.

## Windows PowerShell

```powershell
cd C:\Users\lonis\projects\hackathon\junction_2026\exa
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
```

If you already have a virtual environment, skip its creation. If `backend/.env` is missing, copy `backend/.env.example` to it; do not overwrite an existing file containing keys. Configure these settings in that file:

```dotenv
APP_ENV=development
DATA_MODE=live
SEED_DEMO_ACCOUNT=0
AUTO_PRICE_LOOKUP=1
EXA_MODE=live
EXA_API_KEY=<your Exa key>
CLOUDINARY_URL=cloudinary://<api-key>:<secret>@<cloud-name>
ANTHROPIC_API_KEY=<optional Anthropic key: chat agent and wording>
LLM_MODEL=<optional, defaults to claude-haiku-5-5>
COOKIE_SECURE=0
ALLOWED_HOSTS=localhost,127.0.0.1
```

Leave optional keys blank when unused. Do not copy placeholder values literally. The app works without an Anthropic key; it reports missing Cloudinary for media operations. Live mode is now the default, and demo-account seeding is off by default. `DATA_MODE=demo` / `SEED_DEMO_ACCOUNT=1` explicitly opt into fixtures. `DATA_MODE=live` prevents demo research fallback. Existing environment variables override `.env`; restart after configuration changes.

```powershell
.\backend\run.ps1 -Port 239 -Reload
```

If script execution is blocked, use the direct command without changing your execution policy:

```powershell
cd backend
..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 239 --reload
```

Open:

- Website: `http://127.0.0.1:239/`
- Mobile interface: `http://127.0.0.1:239/mobile/`
- Create an account: `http://127.0.0.1:239/register`
- Provider status and explicit connection checks: `http://127.0.0.1:239/integrations`
- API explorer: `http://127.0.0.1:239/docs`
- Database/process health: `http://127.0.0.1:239/healthz`

No separate database process is needed. Startup creates or upgrades `backend/data/taimi.sqlite3` with additive migrations. Keep this file private and back it up before upgrading. `SEED_DEMO_ACCOUNT=0` stops new fixture seeding; it does not delete existing records or the existing test account. Use a new registered account or a separate `TAIMI_DB` file to isolate real tests.

## Real grocery test

1. Register a fresh account rather than using the seeded test account.
2. Open Website → Groceries, or Mobile → Shopping.
3. Expand **Your search location & grocery chains**. Enter the city, country code, currency and exact grocery-chain domains you want. Nothing is selected automatically. Save.
4. Add an item with a precise description. For example, name `Chips`, brand `Estrella`, details `sour cream onion`, attributes `package=200 g`. Prefer the retailer's product language/naming to reduce ambiguous matches. Quantity means number of matching packages.
5. Saving schedules a best-effort automatic lookup. It reuses valid application cache to reduce spend. Reload the saved list if the initial lookup is still finishing.
6. Click **Update prices** for an explicit refresh. This bypasses the application search cache and asks Exa for fresh page content (`max_age_hours=0`). It still cannot guarantee the retailer published a usable current local price.
7. Inspect each saved quote's product, store, source URL, retrieval time, cache indicator and expiry. Quotes are claims from pages, not guaranteed stock or checkout prices. Prices without matching brand/details/attributes or currency remain unknown.
8. Reload the page and sign in again: list details and quotes remain in SQLite. Edit the flavour, brand, package or selected chains: incompatible old quotes disappear from the active estimate, but historical records remain in the database.
9. **Compare current list** proposes a store strategy. Missing prices are excluded from the known subtotal, not valued at zero. Print the sourced proposal; no purchase is performed.

Lookups are bounded to eight items per agent run. Update prices refreshes up to 32 open items in batches; larger lists need selected `itemIds` through the API. Basket comparison reuses fresh persisted quotes for all matching items and researches up to eight missing items per request. Refresh the full list first to populate larger baskets; items without a valid quote remain unpriced.

If prices are missing: open the original retailer page, check that the exact variant and store price are public without login/store selection, narrow the domains, try the retailer's exact product name, and inspect the quota at `/api/v1/usage`. Exa cannot reliably retrieve prices that exist only in private retailer sessions. Do not relax exact requirements just to manufacture a result.

## Other products and watches

Website → Price watch now uses account-backed watches when served by FastAPI. Choose explore or exact mode, a query and required details, city, country, currency, domains, target, cadence and optional buy-by date. Save → Check prices → inspect sources/history. Pause blocks checks. The server scheduler operates while the process runs; in-app alerts do not send emails or SMS. Required details apply to any product; exact mode also requires the product-name terms to match.

Ticket dates, fares, quantities and fees need explicit requirements and source review. Current watch prices are page item prices and do not claim complete delivered/booking totals. For complex offers use the original checkout page. Static `npm run dev` retains its separate synthetic watch demo.

The mobile Events/Travel, Products and Chat screens call the backend, while many other mobile interactions remain local demonstrations. The integration banner and per-screen notice identify that boundary. All backend features can be exercised through `/docs`; see [use-case scenarios](use-cases.md) and [complete API route index](api-route-index.md).

## Provider checks and media

The authenticated integration page shows configured/missing keys without exposing values. Its Check connection buttons make a bounded Exa query, read-only Cloudinary ping or a short Gemini request; they may consume provider credits and have a 30-second cooldown. Credential presence alone is not verification.

Use `/docs` to test `POST /api/v1/media/itinerary` with a title and time/title items, `/media/event-teaser` with public permitted image URLs, or `/media/rotation` with public multi-angle product images. Those operations upload/transform media and may consume Cloudinary credits. A single-image spin is explicitly a visual effect, not recovered 3D geometry. The household-camera requirement remains local processing; do not send private fridge/door footage to these endpoints.

Exa and Cloudinary credential probes were successful during this implementation. The language model is Claude (Anthropic SDK); Gemini is no longer used. A probe verifies access, not every transformation, every retailer, model or real-world price. Automated tests use fake providers and do not spend credits.

## Checks

```powershell
.\.venv\Scripts\python.exe -m pytest backend\tests -q -p no:cacheprovider
npm run check
npm test
npm run build
```

For local UI-only mock previews, use `npm run dev` for the website or `python -m http.server 5180 --bind 127.0.0.1 --directory mobile` for mobile. These static modes do not use backend keys or the database.

## Price-refresh troubleshooting, manual watches and cross-border searches

The earlier `contents.summary.schema.properties.price.type` error was caused by an unsupported union-type array in the Exa schema. The price property now uses scalar `type: number` and is optional; an absent price stays unknown. Provider schema rejection is shown as a visible error instead of looking like a no-op. HTTP 422 can separately indicate missing shopping settings, an empty list or a list beyond the refresh limit; the UI shows the specific reason and opens settings when needed.

Restart the backend after pulling the fix, then hard-refresh the browser (Ctrl+Shift+R). No API keys or database reset are needed for this schema correction.

Price watch now accepts `cadenceHours: 0` for **manual-only** checking. It is excluded from the scheduler but **Check prices** still works. Positive integers 1–720 enable that hourly interval. Existing watches have an interval input and **Save schedule** button, so they can be changed to zero without recreating them.

**Your country** remains a real ISO country code such as FI, SE or DE. EU is not a country and is not sent as Exa's country-location bias. The new **Search scope** choices are local country, European Union, selected countries and worldwide. For selected countries enter, for example, `FI, DE, NL`. Supply the exact websites you want from any of those countries. Broad scopes omit home-country bias and add market guidance to the query; they do not prove where a retailer delivers or enforce a legal/geographic boundary.

Comparison uses only the chosen currency. For example, EUR offers can be compared across Finland and Germany, while an SEK-only Swedish listing remains outside an EUR total. No exchange rate, international shipping fee or tax adjustment is invented.

This correction was checked using offline mocked provider tests only. No real provider/API test was performed for this revision.


## Offline price regression checks

Run `.\.venv\Scripts\python.exe -m pytest backend/tests -q` from the project root. The test configuration blanks provider keys and uses a temporary database; live code paths use fake Exa responses. No real provider calls are needed. Regression cases cover a Finnish product name for an English grocery request, rejecting category pages, cached translated quotes, natural-language laptop requirements, units/model families, no-match attempts, successful history and preserving an older quote after a miss.

For a later user-run real check, choose the city/country/currency and shop domains yourself, then press Update prices or Check prices. Expand lookup details if no quote appears. A category-only result requires an indexed, readable individual product page; a provider key cannot make inaccessible prices public. No real API test was performed for this update.


## Testing saved trips and Cloudinary controls

Follow [the current walkthrough](media-and-trips.md). Restart the backend on port 239 and hard-refresh clients. New SQLite tables are additive. Old grocery quotes are intentionally excluded until refreshed under the new package-price validation context. The regression suite covers Decimal price parsing, per-shop coverage, nearby discovery, sign-in persistence, destination filtering, source ownership, Python Cloudinary calls with fakes and the three-event lifetime preview limit. No live API test was performed.


Latest behaviour: [manual grocery pricing, strict attributes, temporary research and named lists](current-behavior.md). This supersedes earlier automatic-lookup and restored-research descriptions.
