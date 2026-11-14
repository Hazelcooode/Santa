# Product and scope

## Problem and audience

Young adults living alone carry many small recurring tasks: remembering essentials, comparing shopping options, fitting chores around their calendar and finding something enjoyable to do. Sola reduces the research and planning burden while keeping the user in control.

Primary persona: a student or early-career person in Helsinki, with a modest budget, a busy calendar and limited energy for household administration. Location, dietary preferences and budget must be user supplied in the real product; Helsinki is only the demo setting.

## Main journey

User says: “Help me restock breakfast for under €20, one store, sometime this afternoon.” The Coordinator identifies items and missing constraints. Researcher uses Exa to find relevant retailer pages, retrieves evidence and records any missing prices. Planner compares matching products, proposes a basket and a calendar slot, and cites each claim. User reviews the total, exclusions, sources and proposed time before approval. In the MVP the result is a printable list or retailer link; checkout is later work.

Do not promise a global cheapest basket. Say “lowest known price among these matched sources.” If a local retailer does not publish reliable price or store availability, show an explicit unknown and ask for a manual choice.

## Scope by release

| Area | Frontend now | First live MVP | Later |
| --- | --- | --- | --- |
| Groceries | Editable list, sample comparison, print, local plan flag | Exa evidence, constrained basket, approval, printable result | Retailer checkout and receipts |
| Inventory | Seeded editable facts | Manual stock entry | On-device camera inference and user confirmation |
| Price watch | Multi-category comparisons, exact/open watches, synthetic history and target alerts | Live any-item Exa research with normalized variants and fees | Scheduled refresh and consented notifications |
| Laundry | Sample wardrobe, slot and checklist | Manual task and proposed calendar slot | Actual laundry-room reservation API |
| Discovery | Three saved sample ideas | Live Exa event/product research with sources | Travel bundles and monitoring |
| Companion | Scripted text and mood handoff | Model chat with explicit memory consent | Voice, social account integrations |
| Wellbeing | Local check-in and privacy concept | User-owned reminders only | Consented trusted-contact escalation |
| Health | No advice or actions implemented | Out of MVP | Appointment search, verified non-diagnostic information |

The original safety, door monitoring, medicine delivery and social messaging ideas remain in the roadmap. They need dedicated consent, reliability and integration design before becoming usable features.

## Requirements

- Every recommendation involving a price, venue or deadline carries source IDs, retrieval time and uncertainty.
- Users can edit inferred facts before research; store preference, dietary requirements, budget and travel limits are explicit constraints.
- Expired, incomplete or inconsistent evidence is visible. Absence of a price does not mean zero.
- Read-only research runs without repeated approval. Purchases, reservations and communications require a review of concrete details.
- The UI works on a 390 px phone and desktop, supports keyboard operation and shows loading, empty, partial, error and stale states.
- The backend accepts a new judge-supplied query; it cannot rely only on seeded examples.

## Evaluation

Use the five challenge criteria equally: useful outcome, live Exa retrieval, source clarity, originality and working implementation. Track task completion, supported claims / all factual claims, price matching accuracy, time to first useful result, accepted plans, and actual per-run provider usage. Proposed initial targets: first useful result within 15 seconds, terminal result or clear partial result within 60 seconds, zero unapproved external writes. These are targets to measure, not achieved results.

Original angle: an assistant connecting local household facts to web-grounded plans, with evidence and approval as part of the everyday flow rather than a separate research report.
