# Sponsor roadmap

Scope: a browser app that turns a calendar event into a shopping task, using personal memory and an inspectable audit. This document distinguishes proposed integration work from installed dependencies. Prize categories come from the event screenshots supplied on November 20, 2026; eligibility and prize stacking must be confirmed with organizers.

## Baseline

| Sponsor | Intended responsibility | Current state / next step |
| --- | --- | --- |
| Cognee | Personal memories and retrieved evidence: preferences and earlier choices | Installed locally; synthetic wardrobe stored and recalled. Source passages take precedence over imperfect extracted graph facts. |
| SingleStore | Confirmed tasks, execution records and evidence snapshots | Local development DB running; task and audit persisted. Inventory is currently a fixture, not a DB feature yet. |
| Firedrill | Repeatable agent failure scenarios | CLI connected, descriptor registered, local transport tested. Hosted tool bindings/world and reviewed credits remain. |
| Amplitude | Product outcomes: runs, selections, completed tasks | SDK with local file transport; cloud project optional. |
| Statsig | Feature flags and controlled comparison of ranking strategies | SDK offline overrides tested. Gate currently recorded, not changing ranking yet. |
| Senso | Curated, attributable shopping context shared across agent steps | **Proposed next addition.** Evaluate its API/MCP to ingest approved product specs and return-policy documents, retrieve relevant passages, and record document IDs in the audit. |

### Why Senso fits

The screenshot's Senso track directly asks for a shopping agent connected to its Context Layer, with meaningful action and a decision trail. Senso describes a shared source of truth and agent-accessible context. Use it for curated external knowledge, Cognee for personal memory, and SingleStore for transactional records. Avoid ingesting the same facts into all three without ownership rules.

A useful demo: a candidate jacket looks suitable, but retrieved merchant policy evidence says it is final sale. The agent shows that source and asks the user to review the tradeoff. Source freshness and actual retailer inventory still need independent checks; Senso is not automatically a live shopping catalog.

## Next additions

| Sponsor | Proposed feature | Why defer / entry criterion |
| --- | --- | --- |
| Arcee AI | Model provider for event-to-brief extraction and evidence-grounded explanations | Strong fit for the first real LLM step. Benchmark structured-output accuracy, completion rate, latency and cost over the same scenario set before picking a model. Current app is deterministic, not Arcee-powered. |
| Superlinked SIE | Rerank candidates or embed outfit/product images | Add when catalog relevance becomes a bottleneck. Confirm model availability. One screenshot track explicitly requires SIE Serverless; local SIE alone does not demonstrate that requirement. |
| Airbyte | Bring calendar events and later receipt/inventory context into the app | Add once connector support and OAuth scope for the chosen services are confirmed. Self-hosted replication and cloud agent context are distinct. |
| Tokens& | Developer request timing, errors, evaluation comparisons and project presentation | Useful optional developer integration. Screenshot describes private request monitoring; current public site also describes quality/speed/cost evals. Verify the event integration guide before adding instrumentation; avoid duplicating Amplitude events unnecessarily. |

Arcee's “Pareto frontier” category suggests an evaluation story: compare candidate models on quality, latency and cost, then choose an option for which improving one metric requires sacrificing another. Report measured values and the test-set size; do not claim a universal winner from a small demo.

## Later / only when needed

- **Persona:** verify the human behind an agent for actions that genuinely require it. Our current outfit recommendation and review-task workflow does not justify identity-document collection. Persona verification is not purchase authorization; our app would still need explicit action approval.
- **Guild AI:** consider as the hosted orchestration/runtime once we need scheduled durable jobs, retries and deployment management. Choose one orchestration owner rather than running parallel schedulers in our app and Guild.
- **Chrome extension:** later, for “save this product,” “add this to my wardrobe,” or capturing an inspiration image from an open page. Share the web backend. Do not make the extension own model keys, scheduling or the audit database.

## Product platform

Baseline is a responsive web app usable in Chrome on Mac and Windows. Local development uses the Python backend and browser UI; Windows developers use WSL2 plus Docker. End users should eventually visit a shared hosted URL without installing Python, Docker or sponsor tools. A shared hosted deployment needs backend hosting, per-user authentication/data separation, and secret configuration; the original static Cartwise deployment is not that backend.

## Public sources checked

- Senso: https://docs.senso.ai/docs/overview and https://docs.senso.ai/docs/shared-context-quickstart
- Arcee API: https://docs.arcee.ai/
- Persona KYA: https://help.withpersona.com/articles/CmxigxTOZVhlr4bn7xSX9S/
- Tokens&: https://tokensand.com/
- Cognee: https://github.com/topoteretes/cognee
- SingleStore: https://github.com/singlestore-labs/singlestoredb-dev-image
- Firedrill: https://firedrill.run/
- Superlinked: https://superlinked.com/docs/quickstart
- Airbyte: https://docs.airbyte.com/platform/context-layer/agent-access
- Amplitude: https://www.amplitude.com/docs/amplitude-ai/agent-analytics/faq
- Statsig: https://docs.statsig.com/sdks/debugging
