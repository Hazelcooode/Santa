# Feature roadmap and model ideas

Roadmap entries below describe future live functionality. A frontend-only [general-item price watch](price-watch.md) is now implemented with fixtures and manual simulation. Preserve the three roles in [Exa agents](exa-agents.md); different models power those roles rather than becoming additional agents.

## Ranked feature ideas

| Priority | Feature | Value | Dependencies / acceptance |
| --- | --- | --- | --- |
| P0 | Live grocery research | Immediate household usefulness and strong Exa demo | Exact item matching, primary evidence, transparent missing prices |
| P0 | Source drawer and “why this?” | Trust and challenge source clarity | Claim-to-source mapping, retrieval time and applicability |
| P0 | Budget + one-store/split-store options | User-controlled tradeoffs | Integer totals, comparable units, excluded fees visible |
| P1 | Live weekend discovery | A positive, personal second use case | Exa organizer sources, current dates, timezone and cancellation info |
| P1 | Any-item comparison + price monitoring | Choose by requirements or track a specific variant across sites | Frontend demo implemented; live evidence, scheduled refresh, fee/variant matching and consented alerts remain |
| P1 | Manual pantry + recurring essentials | Useful without cameras | Editable stock thresholds, no overconfident inference |
| P1 | Calendar-aware chores | Less scheduling friction | Consented free/busy read, timezone handling, no overlapping plan |
| P2 | Local camera inventory | Household context without uploading video | On-device inference, confidence threshold, confirmation queue |
| P2 | Preference memory | Personal help without repeated setup | Explicit opt-in, editable facts, provenance, expiry and deletion |
| P2 | Product search from user criteria | Iterative shopping support | User-confirmed attributes, visual privacy decision, sourced comparisons |
| P3 | Checkout / laundry booking | Complete approved errands | Official provider integration, stock/price recheck and idempotency |
| P3 | Travel planning | Flights, stays and local inspiration | Reliable live booking inventory, total fees and cancellation terms |
| P3 | Trusted-contact routine | Consented check-in escalation | Verified contacts, grace period, delivery proof and cancellation |
| P3 | Door monitoring / health integrations | Possible later support | Local processing, rigorous validation and separate sensitive-data design |

## Gemini ideas

Gemini supports schema-constrained output, useful for extracting candidate facts from Exa text into typed product/event records. Google documents JSON Schema and SDK schema support in [Structured outputs](https://ai.google.dev/gemini-api/docs/structured-output). Schema compliance does not establish factual correctness: validate every numerical value and citation against evidence.

Google's [Function calling guide](https://ai.google.dev/gemini-api/docs/function-calling) describes model-proposed calls executed by application code. Use this inside Coordinator for allowlisted read tools; route any material write through server-side approval checks. Verify the selected model's supported tool/output combinations instead of assuming every Gemini variant behaves the same.

Proposed experiments:

- **Research extraction:** Exa pages → Gemini structured product/event objects → deterministic validator. Measure supported-field accuracy and missing-field handling.
- **Friendly explanations:** Planner turns validated options into short, casual summaries with source IDs. Measure clarity and citation correctness; do not ask it to calculate basket totals.
- **Multilingual requests:** Coordinator normalizes a Finnish/English request to the same TaskSpec. Evaluate dietary constraints and location preservation with bilingual examples.
- **Optional visual product clarification:** only for explicitly consented, non-camera uploads in a separately designed feature. Do not send fridge, basket or door-camera imagery to hosted Gemini; the original local-media requirement takes precedence.

Use the currently available suitable Gemini model behind `MODEL_ID`; do not hard-code a speculative model name or claim unmeasured cost savings.

## NVIDIA Nemotron ideas

NVIDIA offers a range of Nemotron models; capability and deployment requirements differ. Its [Nemotron model catalog](https://build.nvidia.com/explore/discover?search=nemotron) and individual model cards must guide selection. For example, the [Nemotron multimodal model card](https://build.nvidia.com/nvidia/nemotron-3-nano-omni-30b-a3b-reasoning/modelcard) describes a specific deployment profile, not a guarantee that it runs on a phone.

Proposed experiments:

- **Planner reasoning:** evaluate a suitable Nemotron reasoning model for budget/constraint tradeoffs using the same typed inputs as Gemini. Deterministic code still validates every plan.
- **Private local inference:** investigate a compatible small/quantized model on the user's actual laptop or home hub for intent routing and consented memory summarization. Measure hardware memory, latency and task accuracy before promising local deployment.
- **Evidence consistency check:** call Nemotron as a bounded function inside Researcher to flag unsupported claims or mismatched package sizes. This is a validation step within one of the three roles, not a fourth autonomous agent.
- **Local perception study:** evaluate a genuinely local vision model separately from planning. If the chosen Nemotron cannot fit the device or perform the task reliably, select a dedicated local detector. Never fall back to cloud media upload silently.

NVIDIA's [NIM structured generation documentation](https://docs.nvidia.com/nim/large-language-models/latest/structured-generation.html) is a starting point for constrained-output support; check the exact model/backend combination and validate responses independently.

## Provider-neutral routing

```ts
interface ModelAdapter {
  generate<T>(input: {
    role: 'coordinator' | 'researcher' | 'planner';
    prompt: string;
    schema: object;
    evidence: object[];
    privacy: 'public' | 'personal' | 'device-only';
    deadlineMs: number;
  }): Promise<{ data: T; provider: string; model: string; usage: object }>;
}
```

Keep provider-specific tooling in adapters. A privacy router rejects `device-only` input for hosted providers. API keys stay on the backend. Exa remains the live information source even if the chosen model offers its own search tools, so evidence attribution stays clear. Fail over only when the replacement meets privacy and capability requirements, and record which provider produced a result.

## Evaluation before choosing models

Create at least 30 representative requests covering groceries, laundry, discovery, ambiguous intent, unavailable prices, dietary restrictions, conflicting evidence, malicious page instructions, unsupported requests and two languages. Hold Exa evidence fixed to compare model quality, then separately test live retrieval. Measure valid schema rate, source fidelity, constraint satisfaction, latency, token usage and measured task cost. Add adversarial cases where the right output is “unknown.”

Try a simple configuration first: one model for all three roles, Exa for retrieval, code for validation. Add mixed providers only when measurements show a useful improvement. Documentation links reviewed 14 November 2026; no benchmark or price advantage is claimed here.
