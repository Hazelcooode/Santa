> Implemented routes: consult the generated [API route index](api-route-index.md) and runtime /docs. The original planning contract below is not the definitive route list.

# Proposed HTTP API

Specification only; none of these endpoints exists in the static preview. Prefix `/api/v1`. JSON request/response, authenticated cookie or bearer session, ownership enforced server-side. Return UTC ISO-8601 timestamps and integer minor-unit amounts. MVP currency is EUR.

## Endpoints

| Method and path | Purpose |
| --- | --- |
| `GET /me` | Profile, timezone, consent and integration capability flags |
| `PATCH /me/preferences` | Validated preferences; does not silently grant consent |
| `POST /consents` / `DELETE /consents/:scope` | Record explicit opt-in / revoke |
| `GET /dashboard` | Task summaries, inventory alerts, proposed day plan |
| `GET /shopping-lists/:id/items` | Items and version, paginated |
| `POST /shopping-lists/:id/items` | Add item; unknown price remains null |
| `PATCH /shopping-items/:id` | Change item with `expectedVersion` |
| `POST /tasks` | Queue research; return 202 with task ID |
| `GET /tasks/:id` | Progress, current result and `pollAfterMs` |
| `POST /tasks/:id/clarifications` | Answer requested fields and resume |
| `POST /tasks/:id/cancel` | Cancel pending work; reconcile already-submitted actions |
| `GET /tasks/:id/proposals` | Proposal revisions with citations and warnings |
| `GET /proposals/:id` | Full immutable proposal |
| `POST /proposals/:id/approve` | Approve expected version/hash; return action status |
| `GET /actions/:id` | Execution/reconciliation status |
| `GET /sources/:id` | Evidence, original URL, freshness and applicability |
| `GET /tasks/:id/export` | Printable HTML/list; sanitize all text and links |

## Research request

```json
{
  "intent": "groceries",
  "request": "Breakfast essentials under €20, one store this afternoon",
  "listId": "uuid-list",
  "constraints": {
    "budgetMinor": 2000,
    "currency": "EUR",
    "city": "Helsinki",
    "storeMode": "one",
    "dietaryRules": ["vegan"],
    "windowStart": "2026-11-14T11:00:00Z",
    "windowEnd": "2026-11-14T16:00:00Z"
  }
}
```

Response `202`: `{"id":"uuid-task","status":"queued","pollAfterMs":1500}`. Validate timezone, budget, list ownership, text length and allowed intent. `GET /tasks/:id` returns `status`, human-readable `progress`, `proposalId` if ready, `missingFields` if clarifying, and a safe error if failed. Do not expose internal prompts or private model reasoning.

## Proposal response

Illustrative values, not live research:

```json
{
  "id": "uuid-proposal",
  "version": 1,
  "payloadHash": "sha256:example",
  "status": "awaiting_approval",
  "kind": "shopping_plan",
  "items": [{
    "name": "Oat milk",
    "quantity": 1,
    "unit": "L",
    "lineTotalMinor": 179,
    "currency": "EUR",
    "sourceIds": ["uuid-source"],
    "verification": "unverified"
  }],
  "knownSubtotalMinor": 179,
  "hasUnknownCosts": true,
  "excludedCosts": ["travel", "delivery"],
  "warnings": ["Illustrative response only"],
  "expiresAt": "2026-11-14T13:00:00Z",
  "actionPreview": {"type":"save_plan","externalWrite":false}
}
```

Each source response includes `id`, `url`, `title`, `excerpt`, `fetchedAt`, `publishedAt` (nullable), `expiresAt`, `applicableLocation`, `retrievalStatus` and `verification`. Keep claim-level source mappings so a general retailer homepage cannot appear as proof of a specific price.

## Approval

```http
POST /api/v1/proposals/uuid-proposal/approve
Idempotency-Key: client-generated-uuid
Content-Type: application/json

{"expectedVersion":1,"payloadHash":"sha256:example"}
```

Response `202`: `{"actionId":"uuid-action","status":"pending"}`. The key is user-scoped; persist request hash and response. Replaying the same key/body returns the same result. Reusing the key with different content returns 409. Approval does not imply action success. Action reads can return `unknown` when the provider outcome needs reconciliation.

## Error contract

```json
{"error":{"code":"PROPOSAL_STALE","message":"Prices changed. Review the updated plan.","retryable":false,"requestId":"uuid"}}
```

Use 400 invalid input, 401 unauthenticated, 403 missing permission, 404 absent or inaccessible resource, 409 version/idempotency conflict, 410 expired proposal, 422 impossible constraints, 429 rate limit, 502 provider failure and 503 temporarily unavailable. Partial research is a successful task response with explicit gaps, not an invented complete answer. Include `Retry-After` for rate limits.

## Security and limits

CSRF protection for cookie writes, strict CORS allowlist, body-size limits, per-user task quotas and safe URL handling. Retrieved URLs must be HTTP(S); backend fetch helpers block loopback/private networks and recheck redirects. Never return API keys or OAuth tokens. Paginate with `{items,nextCursor}` and authorize cursor context.

## Product comparison and price watches

Additional search/watch/check/history endpoints and payload semantics are specified in [Price watch](price-watch.md#proposed-api-additions). These remain proposed endpoints; the implemented frontend uses fixtures and local storage.


## Implemented Cloudinary studio endpoints

See [Cloudinary studio API](cloudinary-studio.md#api) for temporary `/visual-previews` creation/status/content/deletion and `/product-images/{key}`. Generic flat-photo `/media/rotation` is removed (410). Watch-option `/rotation` now returns a temporary generative job (202), not saved media.


## Current Discover request

`POST /api/v1/explore` accepts `{query, location, people?, admission?, context?, dateFrom?, dateTo?}`. `location` must be nonempty (legacy `destination` is accepted as an alias); admission is `any`, `free` or `paid`, people is an optional integer 1–1000, context is at most 600 characters. This website endpoint always researches events internally and returns at most 20 distinct sourced events/specific activities. Generic roundups are not cards. Legacy country fields are not exposed in the website. Optional group size guides suitability, not claimed ticket inventory or fabricated total cost. `activityIdea` and `eventPageType=activity` may be included for an actionable sourced suggestion.

`GET/POST /api/v1/visual-previews` responses now include `expiresInSeconds`. A video session expires after seven minutes from creation; an image-placement session after fifteen minutes. Lifetime includes generation. Expired content remains inaccessible and provider cleanup is retried.
