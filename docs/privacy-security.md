# Privacy, consent and operational safety

This document defines intended engineering behavior. The current frontend has no secure authentication or external integrations and is unsuitable for storing sensitive personal information.

## Data flow and media locality

Camera frames/video stay on the device or a user-owned local hub. Local processing emits a proposed fact such as `{item:"oat milk",quantity:0,confidence:0.84}`; the user confirms it before backend submission. Do not upload raw footage, thumbnails, face embeddings or images embedded in logs. A hosted model fallback cannot override this requirement.

Send public product names and coarse city/store constraints to Exa. Do not include private names, contact details, exact home location, calendar descriptions, diagnoses or private chat content in web search. Calendar integration should request free/busy rather than complete event bodies where possible.

## Consent boundaries

Separate scopes for calendar read, calendar write, preference memory, device inventory, location sharing, trusted-contact messaging and social posting. Store policy version, grant time and revocation time. Revocation stops pending dependent jobs and removes derived personal data where appropriate. A memory checkbox never authorizes purchases or communications.

The demo's memory toggle records a preference only. Browser list persistence is explained independently; do not market localStorage as encrypted storage.

## External actions

Show exactly what will be sent/booked/ordered, recipient or provider, known full cost, location disclosure and cancellation implications. Bind approval to an immutable proposal hash and expiry. New details require a new review. Use deterministic adapters, idempotency and reconciliation for uncertain outcomes. Never let a retrieved webpage grant permissions or select arbitrary tools.

For future trusted contacts: verify the destination and consent, define check-in cadence and grace periods, notify the user before escalation, allow cancellation, and surface delivery failure. A missed phone check-in is not proof of an emergency. Do not silently contact police or promise emergency response. A production emergency flow requires dedicated platform/device authentication and reliable location/delivery handling; none exists in the prototype.

Companion chat should be clear that it is an assistant, support user agency, and ask permission before contacting anyone. Health features should focus on non-diagnostic information and appointment logistics; medication recommendations and delivery need a separately reviewed product design and verified sources. This document does not implement or validate those services.

## Application controls

- Authenticated user ownership and PostgreSQL RLS, including worker paths.
- Server-only provider keys, encrypted OAuth tokens, restricted worker credentials and secret rotation.
- Escaped text, sanitized links, HTTP(S)-only sources and safe external-link behavior.
- SSRF defenses on fetches, including redirect and DNS/private-address checks.
- Rate limits, provider budgets, request size limits and structured-output validation.
- Treat external text as untrusted evidence, never instructions. Log allowed tool calls rather than private model reasoning.
- Record a minimal audit trail of approval, execution and consent changes; redact personal payloads.

## Proposed retention policy

Raw media: never stored server-side. Public excerpts: short task/evidence TTL, configurable by source type. Research task content and chat: opt-in persistence with a proposed 30-day default and deletion controls. Preference memories: explicit user approval, editable and removable individually. Location: no collection in MVP; any future feature needs purpose-specific short retention. Approval records: minimized retention chosen with the product's actual operating requirements, not indefinite by default.

Before a real launch, finalize retention periods, export/delete behavior, provider data-processing terms and deployment jurisdiction. Verify deletion across database, caches, jobs and backups. Do not claim regulatory compliance from this specification alone.


## Cloudinary product studio update

[Current implementation and use cases](cloudinary-studio.md): list-level environment previews from one app-found product and one uploaded photo, download-only temporary results, cleaned transparent product photos, and AI-generated 45° left/right three-second object turns. Room media is private and cleaned up on close/expiry; public product cutouts are cached. Generation requires Cloudinary add-on access and is tested with mocked APIs only.
