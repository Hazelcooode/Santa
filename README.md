# Sola — a little help with everyday

A personal assistant for young people living alone, based on [ideas.txt](ideas.txt) and the [Exa Junction challenge](challenge.txt). Sola turns everyday research into a short, sourced plan that the user can approve.

**Implemented:** a responsive frontend with fictional data and local interactions. **Not implemented:** backend, live Exa research, model calls, authentication, camera processing, actual calendars, purchases, reservations, messaging or emergency services.

## Run the UI

Requires Node.js 20+. No dependency installation or API keys needed.

```powershell
cd 'current folder'
npm run dev
```

Open **http://127.0.0.1:239**. Use `Ctrl+C` to stop the preview. If the port is occupied, run `$env:PORT=240` before `npm run dev`. The Node server serves static files only; it is not the proposed backend.

```powershell
npm run check
npm test
npm run build
```

The build copies the frontend into `dist/` for any root-mounted static host. Do not open `index.html` directly with `file://`; browser ES modules need HTTP. Google Fonts is optional; system sans-serif fallback keeps the UI usable offline. All illustrations are CSS and emoji, with no image downloads.

## Explore

1. Overview → review the day and choose a mood.
2. Groceries → check off items, add an item, filter essentials, switch one-store versus split-store comparison.
3. Review plan → save a **local demo** approval. Nothing is ordered or scheduled.
4. Laundry → review and save a **local demo** slot.
5. Discover → save and unsave sample ideas.
6. Talk to Sola → test short scripted responses; this is not a language model.
7. Wellbeing → demo check-in and privacy preferences.
8. Price watch → explore any item category or enter an exact model/SKU, compare up to three items and sample store totals, save a search/item watch, set a target, simulate drops, pause/resume and inspect synthetic history. Electronics, footwear, clothing and tickets have fixtures; custom items remain unquoted.

Lists, preferences, saved ideas and plan flags persist under `sola-demo-v1` in browser localStorage. Price watches persist separately under `sola-price-watch-v1`; they run only through manual simulation, never in the background. Chat stays in memory. Settings → Reset demo data clears the saved state. Avoid entering sensitive information into this shared prototype.

## Project map

| Path | Purpose |
| --- | --- |
| `src/app.js` | Seven screens, dialog flows and mock interaction controller |
| `src/model.js` | Fixture data, money calculations, safe text rendering and storage validation |
| `src/price-model.js`, `src/price-watch.js` | General item matching, offer totals, saved watches, alerts and price-watch screen |
| `src/styles.css` | Responsive design, CSS mascot, keyboard focus and print styling |
| `scripts/` | Dependency-free static preview and build |
| `tests/` | Core basket, input and storage recovery tests |
| `docs/` | Implementation specifications, not claims of implemented services |

Start with the [documentation index](docs/README.md), [scope](docs/product.md), [frontend](docs/frontend.md), [backend](docs/backend.md), [three agents](docs/exa-agents.md), [database](docs/database.md), [API](docs/api.md), [usage guide](docs/use/readme.md), [price watch](docs/price-watch.md), [feature ideas](docs/features.md), [privacy](docs/privacy-security.md), and [delivery plan](docs/implementation-plan.md).

The working name **Sola**, Helsinki setting, Alex persona, euro prices and sample times are editable design assumptions. The original challenge and ideas files are preserved.
