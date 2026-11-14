# Deployment preparation

This release supports a **single-instance pilot with real research/media and clearly labeled simulated external actions**. It is not a production emergency service, retailer checkout or authenticated biometric system. Adding keys cannot enable providers that have no integration.

## What runs

One FastAPI process serves API + website + mobile UI. SQLite stores accounts, tasks, inventory and append-only shopping quotes. The scheduler and task executor run inside that process. Run exactly one worker/instance: multiple replicas would duplicate scheduler activity and in-process locks/rate limits. For multi-instance service, first move jobs/locks to durable shared infrastructure and replace SQLite appropriately.

## Local container rehearsal

Create `backend/.env` with server-only provider keys as in [local testing](local-testing.md). From the project root:

```powershell
docker compose up --build
```

Open `http://127.0.0.1:239/register`, create an account and set your search location/chains. Compose binds only to loopback, uses live research mode, disables fixture-account seeding and retains SQLite in named volume `taimi-data`. Local HTTP requires `COOKIE_SECURE=0`, which the development compose file supplies.

```powershell
docker compose down
```

This stops the app and retains the database volume. Do not add `--volumes` unless deliberately deleting the database. The image excludes `.env`, database files, Git and virtual environments, and runs as an unprivileged user. The build installs pinned Python requirements; no Node build is needed for the served interfaces.

## HTTPS deployment

Provision an HTTPS reverse proxy and set your real hostname:

```powershell
$env:PUBLIC_HOST='your-app.example.com'
docker compose -f compose.yaml -f compose.production.yaml up --build -d
```

The reverse proxy forwards to loopback port 239 and must pass the original Host header. Configure forwarding only from your trusted proxy. The production override sets `APP_ENV=production`, `DATA_MODE=live`, `COOKIE_SECURE=1`, disables demo seeding and adds the explicit hostname to `ALLOWED_HOSTS`. Startup rejects insecure production-cookie or seed settings. Keep the API on the same origin as both frontends; CORS is unnecessary for this layout.

Use a **new production database volume** rather than shipping the local seeded database. Disabling seeding does not remove an already-created demo account. Keep provider secrets in deployment secret management; the env-file recipe is for a small pilot. Never put `CLOUDINARY_URL`, API keys or DB files in the public image/repository. Production biometric challenges are blocked; use password verification for simulated safety actions until actual WebAuthn verification exists.

## Operational verification

1. `/healthz` returns OK (process/database).
2. Registration/sign-in works through HTTPS and cookies carry Secure/HttpOnly/SameSite flags.
3. `/integrations` reports live mode and no fixture account was seeded. Test providers explicitly.
4. Save a real item with user-selected chains, update prices, reload, verify exact attributes and original evidence.
5. A missing/bad key, quota or blocked source yields a visible failure/unknown result; live mode never substitutes a demo quote.
6. Verify cross-account isolation, stale edit conflicts and pause behavior with the automated tests.
7. Generate a permitted Cloudinary asset and open its returned output; validate your account's transformation support and cost.
8. Verify logs exclude keys, private chat/media and passwords. Gemini keys are sent in a header rather than URL query parameters.
9. Back up SQLite using its online backup API, test a restore and set file/volume access permissions. WAL-mode backup must include a consistent database snapshot; copying the active file alone is insufficient.
10. Stop/restart the server. Failed in-process price refreshes become retryable failed records; saved quotes persist. Generic task jobs are not a durable queue and require manual retry after a process crash.

Security controls in this release include ownership-scoped queries, hashed passwords and session tokens, same-origin cookie writes, trusted-host validation, no-store authenticated responses, frame protection, production sign-in throttling and provider budgets. They are not a substitute for a deployment-specific security review. Currency/domain and product matching are conservative rather than a universal retailer inventory guarantee.

## Validation status

Docker Compose configuration was validated. A Docker image build, HTTPS deployment, proxy behavior and Cloudinary transformation outputs have not been verified in this session. The project is packaged for rehearsal, not claimed to be publicly deployed. See the implementation report in the chat for executed tests and remaining limits.


## Temporary Cloudinary previews

Use one backend worker process for the bounded in-process generation pool. Keep SQLite on persistent storage; its identifier-only cleanup ledger must survive restarts. The media cleanup thread runs independently of the Exa scheduler, every 15 seconds, retrying provider failures at five-minute intervals. Cloudinary credentials need upload/destroy and signed upload-preset administration permissions, plus Image Generation / Image to Video entitlement. [Setup and privacy details](cloudinary-studio.md#local-setup). No live generation was exercised during this update.
