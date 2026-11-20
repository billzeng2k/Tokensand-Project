# Local setup for Bill and Erica

This is the local calendar-to-shopping development harness. It is separate from the static Cartwise page in `index.html`; the page does not call this backend yet.

## What runs where

| Component | Development mode | State |
| --- | --- | --- |
| Cognee 1.6.10 | Real Python library; local GLiNER extraction and embedding models | `.local/cognee/` and `.local/models/` |
| SingleStore | Real Docker development database, bound to localhost | Docker named volume |
| Calendar and products | Synthetic JSON fixtures or HTTP simulation | No Google login or real retailer calls |
| Amplitude | Real Node SDK, custom file transport; no network | `.local/amplitude-events.jsonl` |
| Statsig | Real Node Core SDK, `disableNetwork`, forced gate values | Process memory |
| Firedrill | CLI and agent run locally; account, synthetic tools and reports run in its cloud | Each person signs in separately |

The workflow is currently deterministic policy code, not an LLM shopping agent. It creates a **needs-user-review shopping task**, never an order. Product prices are fictional item prices; tax and shipping are unverified. It uses the retrieved passage for the demo user's explicit wool rejection; the extracted graph is not treated as authoritative inventory.

## Prerequisites

- macOS or Linux, Git, Python and [uv](https://docs.astral.sh/uv/).
- Docker Desktop/Engine running. The database is allocated 4 CPUs and up to 8 GiB RAM.
- Node/npm for `npm ci`. A pinned project-local Node 24.11.1 is installed by npm and used by repository scripts, without changing your global Node installation. Firedrill requires a supported Node release; our pinned runtime meets its requirement.
- Internet for initial package, image and model downloads. Models include an embedding model and an extraction model; initial seeding can take several minutes and uses substantial disk space.

Verified on Apple Silicon. Windows native setup is not tested; Firedrill's local runner documents macOS/Linux support.

## First run

Accept the GitHub collaborator invitation, then:

```sh
git clone https://github.com/billzeng2k/Tokensand-Project.git
cd Tokensand-Project
npm ci
python3 scripts/setup.py
uv venv --python 3.12
uv pip sync requirements.lock
docker compose up -d
```

`setup.py` creates a random database password in a mode-0600 `.env`, only when that file does not exist. Never commit or share `.env`. Every teammate gets their own password, database and memory.

Wait for the database to finish starting, then run:

```sh
npm run db:check
npm run memory:seed
npm run telemetry:test
npm run test:workflow
npm run demo
```

If `db:check` reports connection refused during initial startup, wait briefly and rerun it. Inspect startup with `docker compose logs --tail 40 singlestore`. Do not paste credentials or full environment output into issues.

Expected first demo result: `task_saved`, selecting the fictional Cotton evening jacket for $59. It rejects an owned jacket, a wool jacket based on Cognee's recalled preference, and an item arriving after the event. The task and audit are saved in SingleStore, with a readable report at `.local/run-<id>.json`. A repeated demo returns `already_saved` and retains one task.

The fixed fixture date is December 4, 2026. It is a deterministic test world, not a live upcoming-event scan. Change the fixture deliberately when testing other dates.

## Tests without models or Docker

```sh
npm run test:workflow
npm run telemetry:test
.venv/bin/python -m tokensand.workflow --memory fixture --storage memory --scenario timeout-after-save
```

The test suite uses process-only storage and explicit fixture memory. It does **not** claim to test Cognee or SingleStore. It covers happy path, duplicates, cancelled events, sold-out products, price increases, unknown delivery, and reconciliation after an uncertain write. The transport test launches the Firedrill JSONL bridge against loopback HTTP fixtures; this is **not a hosted Firedrill campaign**.

Other scenarios: `happy`, `sold-out`, `price-increase`, `unknown-delivery`, `cancelled`, `timeout-after-save`. Use `--storage memory` for isolated scenario runs; an existing saved task intentionally wins over a new recommendation for the same user/event.

## Inspect local services

- SingleStore Studio: http://localhost:8088 (user `root`, password from your `.env`).
- MySQL protocol: `127.0.0.1:3307`.
- SingleStore Data API: `127.0.0.1:9008`.
- Cognee retrieval: `.venv/bin/python -m tokensand.memory`.
- Audit SQL: `SELECT run_id, payload FROM audit_runs;`.
- Tasks SQL: `SELECT task_key, payload FROM shopping_tasks;`.
- Local analytics: `.local/amplitude-events.jsonl`.

Cognee runs as a library when the commands run; there is no always-running Cognee HTTP server. Its files persist between runs. SingleStore persists in a named Docker volume. Audit records are evidence logs, not a tamper-proof ledger.

## SingleStore compatibility

The current image failed on this machine with `CPU does not support x86-64-v3`, despite macOS 26 being installed. We pin the official **0.2.62 development image (SingleStore 9.0.9)** by digest, the release before the AlmaLinux 10 base-image change. It is an older development image, bound only to loopback and not intended for production. Do not silently change the image to `latest`.

The volume is named `tokensand_singlestore-compat-data`. A separate empty/failed startup volume from initial setup may exist on Bill's machine; it is not used. Do not reuse a data volume across incompatible server versions. `VERSION()` reports MySQL compatibility; it is not the SingleStore engine version.

Stop without deleting data:

```sh
docker compose stop
```

Restart:

```sh
docker compose start
```

Do not use `docker compose down -v` unless you intentionally want to erase the local database.

## Amplitude and Statsig

Default `.env` values keep both offline:

```dotenv
AMPLITUDE_MODE=local
STATSIG_MODE=local
```

Amplitude's SDK processes events through a custom transport that writes a local file. Its success response means **locally recorded**, not ingested into Amplitude cloud. Statsig uses `disableNetwork: true` and `overrideGate` for `personalized_recommendations`; the smoke test exercises both values. The gate is currently logged with workflow telemetry, not wired to change ranking behavior.

There are no local Amplitude/Statsig dashboards in this setup. To opt into their hosted services, create separate development projects and edit your private `.env`:

```dotenv
AMPLITUDE_MODE=cloud
AMPLITUDE_API_KEY=your-development-project-key
STATSIG_MODE=cloud
STATSIG_SERVER_SECRET=your-server-secret
```

Create `personalized_recommendations` in Statsig. The workflow telemetry sends only the synthetic user ID, run ID, status and mode; it does not include the wardrobe passage or calendar body. Never expose the Statsig server secret in browser code. `npm run telemetry:test` always stays offline, even if cloud mode is configured. Run `npm run demo` to send development telemetry after opting in.

## Team workflow

Pull before starting and work on separate branches. Commit code, fixture data, dependency lockfiles and docs. Keep `.env`, `.venv`, `node_modules`, `.local`, model downloads and generated Firedrill machine-local files untracked. No teammate shares database passwords, OAuth tokens or model caches through Git.

## Sources

- Cognee: https://github.com/topoteretes/cognee
- SingleStore image and changelog: https://github.com/singlestore-labs/singlestoredb-dev-image
- Amplitude Node SDK: https://www.amplitude.com/docs/get-started/install-server-sdk
- Statsig local testing: https://docs.statsig.com/sdks/debugging
- Firedrill: https://firedrill.run/agent-setup.md

## Standalone browser app

```sh
npm run app
```

Open http://localhost:8787. Integration mode uses Cognee and SingleStore. Choosing a fault scenario switches to isolated state automatically, so earlier saved integration tasks do not hide the fault. Export the resulting audit using the button. The server binds only to localhost and serves only the `web/` assets, not your repository or `.env`.

## Windows setup for Erica

Use **WSL2 with Ubuntu** for the development backend and Firedrill runner. Install Docker Desktop for Windows, enable its WSL2 engine and integration with your Ubuntu distribution, then install Git, uv and Node/npm inside Ubuntu. Follow the same first-run commands from the Ubuntu terminal. Clone under your Linux home directory (for example `~/projects/Tokensand-Project`) for better filesystem performance; do not copy Bill's `.venv` or `node_modules`.

Open http://localhost:8787 in Windows Chrome/Edge after starting `npm run app` in WSL. Default WSL localhost forwarding normally makes it reachable; if not, check Windows/WSL networking settings rather than exposing the backend to the public internet. Windows native Python/npm execution is not verified. This WSL setup is documented, but has not been executed on a Windows machine in this session.

For a shared hosted website, only the backend developer needs these services. Hosting the Python service, configuring secrets, and adding user authentication/isolation remain deployment work. The current static Sites URL does not expose this local backend.

## Optional real Google Calendar source

Follow [AIRBYTE.md](AIRBYTE.md) to install the Airbyte source, create a Google Desktop OAuth client, sign in and use real events in the local app. Erica should follow its WSL2 instructions and authorize her own Google account. Gmail stays on the roadmap; no email access is requested.

## UpNext agent and admin (current entry points)

The primary page at `/` is now the grouped Calendar → Amazon recommendation workspace. `/admin` shows conversations, traces and metrics. The original scenario picker and calendar sync controls moved to `/lab`. See [AGENT_AND_ADMIN.md](AGENT_AND_ADMIN.md) for local demo mode, optional live research, telemetry definitions, Statsig controls and proactive scheduling. The new agent defaults to saved preferences plus local SQLite; Cognee and SingleStore are opt-in controls there.
