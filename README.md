# UpNext

**What you’ll need, before you need it.** Repository: `Tokensand-Project`.

UpNext turns upcoming Google Calendar occasions into **Amazon shopping plans grouped by category**, with product links, relevance explanations, prices and ratings when available. Recipe ideas can accompany a plan. Every workflow has a persistent conversation and audit trail, and an admin observatory shows reliability, usage, latency, feedback and evidence coverage.

## Run locally

Follow [Mac/Windows setup](docs/LOCAL_SETUP.md), then:

```sh
npm ci
npm run app
```

- **App:** http://localhost:8787 — sign in, then try **A Christmas party** in preview mode.
- **Admin:** http://localhost:8788/ — inspect conversations/traces, feedback, metrics and controls.
- **Integration lab:** http://localhost:8788/lab — existing Cognee/SingleStore deterministic scenarios and Airbyte sync.

The main app contains only shopping, events, saved plans and personal preferences. Admin is separate and token-protected: run `npm run admin:token` to sign in on port 8788.

Preview mode uses simulated Amazon-style products/prices/ratings, no LLM calls and no purchases. Live research is implemented through OpenAI Responses web search with Amazon-only domain filtering; it needs an API key and has not been live-tested in this local-first setup. Unknown prices/ratings remain unavailable. Sourced claims are not independently verified. No checkout or payment exists.

## Google accounts and Calendar

The app now requires Google sign-in. Users connect Calendar inside UpNext; developers configure one **Web application OAuth client** first. Follow [Google sign-in setup for Bill and Erica](docs/GOOGLE_SIGN_IN.md). Each account has separate preferences, calendars, conversations and traces. The calendar view shows a year of upcoming occasions, including recurring birthdays, with type filters and a shortcut to plan for an event. Sessions survive refresh and server restarts for seven days. The old Desktop OAuth/CLI flow is retained only for the legacy integration lab.

## Setup guides

- [Local Qwen and Amazon experiment](docs/LOCAL_QWEN.md)

- [Erica: Windows Google OAuth setup, step by step](docs/WINDOWS_GOOGLE_OAUTH.md)

- [Agent, admin, metrics and Amplitude/Statsig setup](docs/AGENT_AND_ADMIN.md)
- [Google Calendar through Airbyte: OAuth and Erica's WSL instructions](docs/AIRBYTE.md)
- [Local Cognee and SingleStore](docs/LOCAL_SETUP.md)
- [Firedrill and remaining hosted configuration](docs/FIREDRILL.md)
- [Sponsor roadmap](docs/SPONSOR_ROADMAP.md)

The default agent uses saved preferences and a persistent local SQLite trace ledger so the app/admin work without sponsor credentials. Admin controls can enable Cognee recall and optional SingleStore trace mirroring. Amplitude and Statsig use real SDKs with offline transports/overrides by default; cloud delivery requires separate project keys. Proactive calendar checks are opt-in and run only while the server is running. Gmail and other retailers remain future integrations.

```sh
npm run test:workflow    # offline policy, agent, calendar and HTTP tests
npm run telemetry:test  # existing sponsor SDK smoke test
npm run demo            # legacy Cognee + SingleStore fixture workflow
```

The browser app is in `web/`; its Python API is `tokensand/server.py`. The older root-level static prototype remains separate and is not deployed by these changes. No shared backend is hosted. This is a single-user local app, not a production multiuser service.

Keep `.env`, `.local`, models and generated Firedrill plans out of Git. Each teammate has independent local state, anonymous analytics identity and service sign-ins. Erica can pull the repository without receiving anyone else's tokens or conversations.
