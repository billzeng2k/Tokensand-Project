# UpNext

What you’ll need, before you need it. Repository name: `Tokensand-Project`.

# Tokensand-Project

A local web app and integration harness for a personal shopping agent with an audit trail. A synthetic calendar event becomes a shopping task after checking remembered preferences, ownership, price, size and delivery. The policy is deterministic today; real LLM planning, live calendars and retailer search are future work.

## Start here

- [Mac and Windows local setup](docs/LOCAL_SETUP.md)
- [Firedrill connection and remaining hosted setup](docs/FIREDRILL.md)
- [Sponsor baseline and add-on roadmap](docs/SPONSOR_ROADMAP.md)

After completing local setup:

```sh
npm run app
```

Open **http://localhost:8787** in Chrome, Safari or Edge. The app has a scenario picker, a saved-task result, rejected candidates, memory evidence, tool results and downloadable audit JSON. It does not require Codex. Windows development uses WSL2; a shared hosted backend is not deployed yet.

```sh
npm run demo             # real local Cognee + SingleStore, synthetic external services
npm run test:workflow    # isolated policy + HTTP/JSONL transport tests
npm run telemetry:test  # real Amplitude/Statsig SDKs in offline modes
```

## What is real versus simulated

Cognee memory and SingleStore persistence run locally. Amplitude uses a local file transport; Statsig evaluates offline overrides. Calendar events, products and task-service faults are synthetic. No order is placed or payment collected. Firedrill is connected and registered; cloud simulations still need hosted tools/world configuration and a reviewed credit estimate.

The original storage-cart prototype remains in root `index.html`, `app.js`, and `engine.mjs`. The new standalone browser app is under `web/` with its Python API in `tokensand/server.py`. Only the new server connects to the local workflow. The previously deployed static site is not automatically updated by these backend changes.

## Repo layout

- `tokensand/`: policy, memory, persistence, tool adapters, server and JSONL bridge
- `web/`: browser app
- `fixtures/`: clearly labeled synthetic event, profile and product data
- `tests/`: repeatable offline tests
- `scripts/`: local environment generation, telemetry and Firedrill plan preparation
- `compose.yaml`: loopback-only pinned SingleStore development container
- `requirements.lock`, `package-lock.json`: pinned dependencies

Keep `.env`, `.local`, virtual environments, models and generated Firedrill local plans out of Git. Each teammate maintains independent local state and signs in to services separately.

### Google Calendar with Airbyte

The app can now sync a Google Calendar through the official Airbyte Docker source and use a selected event in the shopping demo. Follow [the Mac/Windows setup and Google sign-in guide](docs/AIRBYTE.md). Start with `npm run calendar:install`, then `npm run calendar:connect` and `npm run calendar:sync`. Gmail remains a future integration. Product data and wardrobe preferences are still demo data; calendar authorization is per developer.
