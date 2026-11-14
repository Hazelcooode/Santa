> Current runtime: Python/FastAPI + SQLite now exists. Start with [local testing](local-testing.md), [use cases](use-cases.md), [API index](api-route-index.md) and [deployment](deployment.md). Planning choices below are historical specifications.

# Implementation documentation

These files describe the intended product and how to implement it. The root README is the source of truth for what currently runs. The current runtime is Python/FastAPI with SQLite; older architecture proposals below are historical.

| Document | What it answers |
| --- | --- |
| [Product](product.md) | Audience, main journey, MVP, later work and success criteria |
| [Price watch](price-watch.md) | Any-item comparison, exact variants, saved searches, alerts and live-monitor integration |
| [Frontend](frontend.md) | Screens, state, accessibility and replacing fixtures |
| [Backend](backend.md) | Services, jobs, state transitions, approvals and deployment |
| [Exa agents](exa-agents.md) | Exactly three agents, inputs, tools, outputs and budgets |
| [Database](database.md) | PostgreSQL tables, relationships, indexes and ownership |
| [API](api.md) | Request/response examples, errors and frontend contracts |
| [Use / README](use/readme.md) | User walkthrough and judge demo |
| [Features and models](features.md) | Roadmap plus Gemini and Nemotron experiments |
| [Privacy and security](privacy-security.md) | Camera locality, consent, sensitive actions and retention |
| [Implementation plan](implementation-plan.md) | Build order, acceptance checks, risks and test cases |

## Architecture decision record

- **Prototype:** plain ES modules, CSS and a static Node file server. This gets the UI running without installation and does not commit the team to a framework.
- **Proposed backend:** TypeScript, Fastify, PostgreSQL, a separate worker and server-side provider adapters. These are decisions for implementation, not installed dependencies.
- **Three agent roles:** Coordinator, Researcher, Planner. Models are interchangeable inference providers inside those roles; adding Gemini or Nemotron does not add agents.
- **Exa is the research layer:** current web evidence and readable source records. It is not a checkout, stock, calendar or emergency API.
- **MVP vertical slice:** groceries first, with a second event-search use case if time permits. Cameras, bookings and safety automation are later integrations.
- **Local media:** raw camera images/video never go to Exa or a hosted model under the current product requirement.
- **Approval:** user confirmation binds to a specific immutable proposal version. Any material change invalidates approval.

Provider documentation was reviewed on **14 November 2026**. Recheck exact model availability, API fields and pricing before implementation; use the primary links in the agent and feature specifications.


- [Current package-price, saved trip and Cloudinary workflow](media-and-trips.md): implemented controls, configuration, limitations and a jury walkthrough.


Current UI: see [the screenshot-based redesign](ui-redesign.md) for shared layouts, static/connected modes, individual-event filtering and itinerary exports.


Latest behaviour: [manual grocery pricing, strict attributes, temporary research and named lists](current-behavior.md). This supersedes earlier automatic-lookup and restored-research descriptions.

- [Cloudinary product studio](cloudinary-studio.md): environment previews, product cutouts, object turns, setup and deletion lifecycle.
