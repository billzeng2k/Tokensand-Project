# UpNext: Calendar → Amazon plans + agent observatory

## Scope and what is working

UpNext has a local recommendation workspace at `/`, an admin observatory at `/admin`, and the previous deterministic integration harness at `/lab`. The active product scope is **Google Calendar occasions and Amazon.com shopping**, with USD prices. Gmail, additional retailers, Senso claim checks and checkout automation are future work.

The agent produces an event plan grouped into categories, with alternatives rather than a single flat list. A Christmas-party demo shows two trees, three stocking variants and two recipe ideas. Each product card contains a name, price, star rating/review count, relevance explanation and uncertainty notes. Live cards link to the Amazon product page. A recipe has ingredients, preparation steps and optional links to researched Amazon ingredients; it has no fabricated recipe rating or price.

**Demo mode is functional without API keys.** It is deterministic simulation, not an LLM. Product names, prices and ratings are clearly synthetic and are not offered as real Amazon purchase links. It uses the same persistent conversations, review tasks, traces, feedback, metrics and sponsor SDK integration as live mode.

**Live mode is implemented but requires an OpenAI API key and has not been exercised against the live API in this local-first setup.** It uses Responses API hosted web search, restricted to `amazon.com`, followed by a structured extraction request. The model can search/read public web content through that tool. This is not a signed-in Chrome shopping bot, and it cannot click checkout, bypass Amazon restrictions, retrieve a private cart or guarantee access to JS-only/blocked pages. No order is placed.

## Erica's setup

Follow [LOCAL_SETUP.md](LOCAL_SETUP.md) for dependencies. On Windows, use Ubuntu/WSL2 with Docker Desktop integration. Then:

```sh
git pull
npm ci
npm run app
```

Open http://localhost:8787 and select **A Christmas party**, then **Think ahead**. Open http://localhost:8787/admin to inspect the result. Select a run to see its conversation, sources, execution spans, flags, usage and telemetry delivery. Feedback is recorded once per run, and only when a user clicks a feedback choice. Demo feedback stays distinguishable from live feedback through the mode filter.

The new agent defaults to saved preferences and a local SQLite ledger, so it works without starting Cognee or SingleStore. Admin controls can enable local Cognee retrieval or mirror finished traces to SingleStore. These are genuine optional integrations; if Cognee fails, the run fails rather than inventing a memory result. If SingleStore mirroring fails, the local trace remains and records the mirror error. SingleStore mirrors snapshots at run completion; later feedback/telemetry retries remain authoritative in the local ledger.

The default preferences and $80 item budget are a **demo persona**. Edit them in the admin controls before personal use. A dollar amount in a request narrows the item budget (the smallest dollar amount is used conservatively); follow-ups inherit the previous budget unless a new amount is supplied. The admin item budget is an upper bound. Budget is per product, not the cost of buying every alternative or all ingredients; shipping/tax are unknown.

## Conversations and actions

Each conversation can have multiple runs. The ledger retains all messages and runs, while the live model receives the latest 12 user/assistant messages and up to three prior recommendation plans to bound context. Current supplied context and memory source are recorded separately. The complete original history remains available in the local ledger even when earlier turns are outside the model window.

On a useful result, UpNext saves a durable `needs_user_review` plan to the local `review_tasks` table. A repeated save of the same run is idempotent. The saved plan is visible when reopening its conversation. Follow-up runs are new revisions and can save new plans. No-purchase decisions are valid outcomes and do not create unnecessary shopping tasks. An unsuccessful provider call does not silently switch to demo data.

Products are grouped into at most four categories, with up to three alternatives per category. Up to two generated recipe ideas can accompany the plan. Live product URLs must be HTTPS Amazon.com URLs with a product identifier (`/dp/ASIN` or `/gp/product/ASIN`) and appear in the model's retrieved source list. Non-Amazon links, search/category pages, untraceable URLs, invalid prices/ratings and products above the item budget are rejected. Missing prices/ratings remain unknown. Source membership is **not independent verification of the model's extracted claims**. Retailer details must still be checked before purchasing.

## Turning on live research later

Add to your local, gitignored `.env` and restart the server:

```dotenv
OPENAI_API_KEY=your-own-key
OPENAI_MODEL=gpt-6.2-astra
```

Select **Live** in the app. The workflow uses at most two model requests: research with up to eight hosted web-tool calls and 5,000 output tokens, then structured extraction with up to 5,000 output tokens. Each HTTP request has a 120-second timeout. There is no automatic provider retry, to avoid hidden duplicate costs. These are call/token bounds, not a guaranteed dollar ceiling; set provider billing limits too.

Live runs send the selected occasion's title/date, saved preferences, bounded conversation history and research context to OpenAI. Calendar descriptions, attendee lists, OAuth tokens and application credentials are not deliberately included. Requests use `store: false`; this is not a promise of zero provider retention. Hidden model reasoning is not saved or shown.

Amazon may omit price/rating information or block access. The correct behavior is missing information or no eligible result, not a fabricated number. Some source URLs may contain variants or redirects; the current exact-source-URL check is deliberately conservative and can reject a valid alternative URL.

Cost estimates are optional. Configure current model-specific rates yourself:

```dotenv
OPENAI_INPUT_USD_PER_MILLION=
OPENAI_OUTPUT_USD_PER_MILLION=
OPENAI_WEB_SEARCH_USD_PER_CALL=
```

With any missing rate, live cost is **unknown**, not $0. Estimates use reported tokens and observed web actions; they do not model cache discounts, all provider billing nuances, Cognee inference, other vendor fees or tax. Runs with failed model calls are unknown because usage may be incomplete. Demo runs have zero actual model calls/tokens and $0 estimated API cost.

## Calendar-driven proactive recommendations

Connect Google Calendar using [AIRBYTE.md](AIRBYTE.md). In Admin:

1. Edit preferences and item budget.
2. Choose demo or live proactive mode.
3. Enable proactive checks, choose a lookahead window and interval, then save.
4. Use **Check upcoming events now**, or leave the app running for the interval check.

Proactivity is off by default. A scan refreshes Airbyte rather than using stale data, considers upcoming events and starts at most two runs per scan within a configurable daily cap (counted by UTC date). Event ID + revision + mode + trigger-policy version is the deduplication key. A failure or blocked run still consumes its reservation; retry manually through the recommendation form after correcting the issue. A changed event revision is eligible again. Cancelled/deleted events cannot produce a new recommendation. Existing saved historical plans are not automatically withdrawn.

The local process must remain running. This is not a hosted/background OS service. Calendar authentication is required for actual scans, including demo-provider scans. Recurring series are excluded pending expansion, as documented in AIRBYTE.md. No Gmail scopes or integration are added.

## Admin access and local privacy

The server binds to `127.0.0.1`, validates the Host header and rejects cross-origin POSTs. By default, `/admin` is a **single-user local developer console without a password**. Optionally set a long random `UPNEXT_ADMIN_TOKEN` in `.env` and restart. Admin routes then require sign-in, using an HttpOnly/SameSite=Strict session cookie valid for eight hours. This guards admin settings, not multiuser customer isolation: shopper conversation endpoints still belong to the one local workspace. Do not expose this server publicly. Production needs authentication, per-user ownership, TLS, rate limiting and a deployment/retention design.

`.local/agent-traces.sqlite3` stores conversations, messages, public model output, provided context, sources, spans, review tasks, feedback, automation reservations and the telemetry outbox. Files are gitignored; the SQLite file has owner-only permissions. There is no automatic retention deletion or encryption at rest. Keep exports private. Basic key/token patterns are redacted, but this is not comprehensive PII detection. Do not put credentials or sensitive personal details into prompts.

Traces are persisted at step boundaries. On restart, previously queued/running runs become `interrupted`, not successful. The run detail provides JSON export. The conversation picker shows the latest 100 conversations; the admin table shows the latest 100 runs within the selected window, while aggregates include all matching runs. Older data remains in SQLite. The old deterministic lab retains its existing audit mechanism and is not retroactively imported into the new conversation metrics.

## Amplitude and Statsig

The real Node SDKs run locally. Defaults require no cloud account:

- Amplitude uses a local transport writing `.local/agent-amplitude-events.jsonl`.
- Statsig evaluates explicit offline gate/experiment overrides. Outcome event calls are mirrored to `.local/agent-statsig-events.jsonl` for inspection because networking/logging are disabled.
- There are no self-hosted Amplitude/Statsig cloud dashboards. UpNext's admin reads the local ledger.
- Each checkout gets a persistent anonymous analytics user ID. Erica's install has a separate ID. No email is used for assignment.

To enable cloud delivery later, set the keys and modes in `.env` and restart:

```dotenv
AMPLITUDE_MODE=cloud
AMPLITUDE_API_KEY=your-project-key
STATSIG_MODE=cloud
STATSIG_SERVER_SECRET=your-server-secret
```

Create these Statsig gates:

| Gate | Behavior |
| --- | --- |
| `shopping_agent_enabled` | Required for every new recommendation run |
| `web_research_enabled` | Required for live research |
| `proactive_recommendations` | Required for proactively triggered runs |

Create experiment `shopping_recommendation_strategy`, with string parameter `strategy`: `evidence_first` or `budget_first`. The evidence strategy prioritizes source clarity; the budget strategy prioritizes lower evidenced prices. Demo category alternatives are actually sorted by price under budget-first. Gate results, rule IDs, experiment group and effective strategy are stored in each trace. Offline mode uses the admin-selected strategy and is **not a randomized experiment**. In cloud mode, Statsig supplies the assignment; local kill switches remain additional restrictions. Gate/config service failure blocks the run rather than bypassing controls.

Outcome events are sent to both SDKs after the run. A durable outbox retains unsent events; Admin can retry. Amplitude gets stable `insert_id`s for deduplication. Statsig custom-event retries are at-least-once and can duplicate during partial-delivery failures; its event metadata includes `event_id`. The local ledger remains authoritative. No experiment performance claim is justified by the tiny demo sample.

## Telemetry schema and metric definitions

| Event in Amplitude | Statsig event | Purpose |
| --- | --- | --- |
| `Agent Workflow Started` | `agent_workflow_started` | Workflow entry, mode, trigger, conversation/run correlation |
| `Agent Model Call Finished` | `agent_model_call_finished` | Whole-request latency, call status, reported tokens and failure code per model attempt |
| `Agent Workflow Finished` | `agent_workflow_finished` | Terminal outcome, aggregate tokens, sources/items/categories/recipes and missing-field counts |
| `Recommendation Feedback` | `recommendation_feedback` | One explicit helpful/not-helpful/dismissed response per run |

All events have an anonymous user ID, stable event ID, UTC timestamp and schema version. Allowed properties include run/conversation IDs, demo/live mode, manual/proactive trigger, model, prompt version, strategy, status, latency, token counts, cost estimate, item/source/category/recipe counts, missing-price/rating counts and feedback. **No full prompt, message, event title, memory text, product URL, raw tool output or credentials are included in analytics events.** Those remain in the local ledger. Statsig separately sends its evaluation/exposure data in cloud mode.

| Dashboard metric | Exact meaning / caveat |
| --- | --- |
| Workflow runs | All matching run records, including queued/running/terminal |
| Completion rate | (`completed` + `no_action`) / terminal runs; blocked, failed and interrupted stay in denominator |
| Recommendations saved | `completed` runs with a saved review plan, not products purchased |
| Helpful feedback | helpful / (helpful + not_helpful); dismissals and unrated runs excluded; show denominator |
| p50/p95 workflow latency | Nearest-rank percentiles, execution to saving/result, excluding queue wait and telemetry delivery |
| Model calls/errors | Model-attempt spans, with failure counted separately; hosted web actions are not extra model requests |
| Model latency | Whole HTTP request duration; individual hosted web actions have unknown latency |
| Tokens | Usage returned by successful/incomplete provider responses; failed requests may have unreported usage |
| Cost/coverage | Sum of known estimates and fraction of terminal runs with an estimate; unknown is not zero |
| Source-linked items | Items with recorded source URLs; not factual verification or Amazon availability |
| Price/rating coverage | Items with reported price/rating / suggested items; demo values are simulated |
| Unverified items | Items with unresolved facts; currently every product requires a retailer recheck |
| Proactive scan results | Eligible events, newly created runs, duplicate reservations suppressed, failure/paused state |
| Pending telemetry | Undelivered outbox rows across the workspace, independent of dashboard filters |

Use **Live research only** to assess real calls. Demo and live are explicitly separate dimensions. The UI currently covers correctness of bookkeeping, operational reliability and explicit feedback; it does not measure factual accuracy, revenue, purchase conversion, retention or causal experiment lift. Senso checks and reviewer-labeled evals could later supply factual-quality measurements.

## Validation

`npm run test:workflow` includes isolated tests for conversations, feedback deduplication, pause gates, live-key failures without fallback, schema/evidence checks, Amazon-only product links, rating bounds, grouped Christmas plans, budget carryover, cancelled-event handling, proactive dedup/caps, interruption recovery, telemetry retry/allowlists, HTTP host/origin/admin access and a mocked Responses request/response contract. Live provider availability, Amazon extraction accuracy, cloud analytics delivery and real calendar authorization require the corresponding accounts and are not proven by these tests.

References: [OpenAI web search](https://developers.openai.com/api/docs/guides/tools-web-search), [Responses API](https://developers.openai.com/api/reference/resources/responses/methods/create), [Statsig Node SDK](https://docs.statsig.com/server-core/node-core), [Amplitude Node SDK](https://amplitude.com/docs/sdks/analytics/node/node-js-sdk/reference).
