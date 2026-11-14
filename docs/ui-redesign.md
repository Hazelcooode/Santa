# Sola interface redesign

Implemented on `current_world`, using the supplied Groceries, Price watch and Discover HTML/screenshots as visual references. Sample claims in those references are not treated as real product data or capabilities.

## Shared visual system

`src/interface.css` is the shared stylesheet, with warm cream `#F7F7F3`, ivory `#FFFEFA`, charcoal `#292D2C`, lavender `#ECE8F7`, sage `#E7EEDF` and terracotta `#D6744C`. Plus Jakarta Sans is used for interface text and Space Grotesk for headings, following the supplied HTML references. Google Fonts are optional network-delivered fonts; system fallbacks remain available. Icons are inline SVG in `src/ui.js`, with no icon-font dependency.

The desktop shell uses a 288px sidebar, a session header and a restrained card grid. Smaller layouts collapse the sidebar to icons, then a horizontal navigation bar. The three redesigned pages share components in static and backend-served modes. Other feature screens retain their previous content and clearly labeled simulations.

## Groceries

- Location/store strip and expandable search settings.
- Queued item count, known subtotal and refresh/reload actions.
- Categories saved as generic `attributes.category`; no aisle classification or store stock is invented.
- Item rows with package quantity, source retailer, timestamp, priority, quote and edit/bought/remove actions. Source product images appear when available; missing photos use a simple icon.
- Add/edit form beside the list on desktop and beneath it on small screens.
- Basket comparison bars use fresh source quotes in the chosen currency. Only complete baskets are comparable; incomplete subtotals are explicitly marked. The average comparison requires at least two complete baskets.
- Source diagnostics and comparison strategies remain available.

Shopping quote image URLs are now persisted in an additive `shopping_quotes.image_url` column. Existing SQLite files migrate on server restart. No standalone database service is required.

## Price watch

- Specifications panel with Explore/Exact match, item requirements, target price and city.
- Advanced controls retain country, currency, optional websites and automatic cadence. Frequency labels reflect actual configured hours; no fictional 15-minute scraper or currency conversion is claimed.
- Watch selector, price/recent sorting and responsive offer cards.
- Each card shows source image or placeholder, merchant, availability evidence at check time, full price and actual difference from the user's target. No invented previous prices, confidence scores or savings.
- Latest offers, Save best 1/5/10, saved options, photo animations, diagnostic disclosures and history remain connected to their existing endpoints.

## Discover and trip plans

- Compact prompt/type/destination/date controls, staged trip builder, research history and individual event cards.
- One event per card, with one coherent title, schedule, venue, admission price and original event URL. Event date ranges are preserved; missing fields stay unknown.
- Users select across searches, name the draft and save up to eight unique events as a trip.
- Saved plans retain Cloudinary schedule/preview controls. Real source photos are displayed when available; no stock photos are substituted as event evidence.
- Copy summary uses the user's clipboard. Print/Save PDF opens an owned printable HTML page for browser printing. Calendar export downloads an ICS file with tentative all-day date windows and original local-time text; it does not sync accounts, book tickets or invent a destination timezone.

### Single-event research safeguards

The internal Exa summary prompt explicitly requests exactly ONE event per result at a dedicated event/detail page. The schema requires `event_page_type` (`single_event`, `event_listing`, `article`, `unknown`) and asks for verbatim `event_evidence`. The Planner excludes all non-single-event pages and exposes rejection reasons. If no destination-matching single event is found, the Researcher makes one additional targeted search for official event/detail/ticket pages. Both calls use the existing budget/cache/ledger gateway. A result is still a source claim, not a booking guarantee.

Older saved research outputs without the new single-event classification remain stored, but are not displayed as verified individual event recommendations; existing saved trips remain accessible. Run a new search to obtain current classified results. Multi-option travel research is a separate feature and may intentionally describe a combined trip.

## Entry points

```powershell
# Connected website and mobile web application
.\backend\run.ps1 -Port 239 -Reload
# Website: http://127.0.0.1:239/
# Mobile web: http://127.0.0.1:239/mobile/

# Static frontend preview (run separately, since both default to port 239)
npm run dev
```

The static preview uses `src/preview-api.js`, explicitly gated by `SOLA_LOCAL_PREVIEW` and the absence of `TAIMI_BACKEND`. Fictional settings/items/offers/events are stored in the browser under `sola-interface-preview-v1`. Custom items and watches do not receive invented live quotes. Media requests explain that the backend is required; PDF/calendar exports are not advertised as functional in static mode. No provider call is made by this adapter. Backend-served pages always use the real API and user-owned SQLite data.

## Added export endpoints

| Method | Path | Result |
| --- | --- | --- |
| GET | `/api/v1/itineraries/{id}/print` | Owned printable HTML itinerary, safely escaped |
| GET | `/api/v1/itineraries/{id}/calendar` | ICS attachment for known event date windows |

## Validation

Backend regressions cover event-list rejection, targeted single-event refinement, coherent event details, export ownership, HTML escaping and calendar end-date handling. Frontend tests cover the restored card layouts and the local preview adapter's persistence and rejection of fake live/media results. Both desktop and narrow-screen browser layouts were inspected on disposable preview data, with provider keys blank and the scheduler disabled. Saving a shortlist and building a trip were exercised locally. No real Exa, Gemini or Cloudinary API calls were made. Remote source extraction and provider rendering still require a later live test.
