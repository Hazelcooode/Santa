# Sola — a little help with everyday

## Current connected release

FastAPI + SQLite serves both interfaces. Website Groceries, Price watch, Discover and account Chat, and Mobile Shopping now use account-backed data. Brand, generic details, arbitrary attributes, automatic price lookup, manual Update prices, saved source quotes and user-selected city/chains are implemented. Other prototype controls and external actions are explicitly labeled simulations.

Start with [local testing](docs/local-testing.md), [use cases](docs/use-cases.md), the [current API index](docs/api-route-index.md) and [deployment](docs/deployment.md). These guides supersede older fixture-only descriptions below.

On Windows, after installing `backend/requirements.txt` into `.venv`, run:

```powershell
.\backend\run.ps1 -Port 239 -Reload
```

Open `/register` for a fresh account, `/` for the website, `/mobile/` for mobile, `/integrations` for provider checks and `/docs` for all API functions at `http://127.0.0.1:239`. SQLite creates/upgrades automatically; no separate database server is needed. For real inputs set `DATA_MODE=live`, `EXA_MODE=live`, `SEED_DEMO_ACCOUNT=0` and your keys in `backend/.env`. Disabling seeding does not remove an existing demo account. Do not overwrite your current `.env`.

The static `npm run dev` preview still uses fixtures and cannot share port 239 with FastAPI. Read the guides above before following the historical overview below.

## Validation

```powershell
.\.venv\Scripts\python.exe -m pytest backend\tests -q -p no:cacheprovider
npm run check
npm test
npm run build
```

The mobile interface is a phone-oriented web application, not a native package. `dist/` contains only the static UI demo, not the FastAPI service. The original [challenge](challenge.txt), [ideas](ideas.txt) and [design docs](docs/README.md) are preserved.
