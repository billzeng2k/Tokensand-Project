# Firedrill setup and test boundary

Firedrill CLI **3.0.11** is pinned in package-lock.json and runs under the repository's Node **24.11.1**. It is not a fully local service. The agent process runs on your machine; synthetic hosted tools, worlds and reports run in Firedrill's cloud.

## Current verified state

- Bill signed in and selected the `Tokensand` workspace.
- Agent `Tokensand Calendar Shopping` is registered as `4b047ae2-bb98-4583-85ed-39752e4cde56` (descriptor revision 2 at setup).
- The generated local plan passed the CLI driver-availability check.
- A local transport test exercises `jsonl-process.v1` and HTTP tool calls, including a write that succeeds before returning an error.
- **No Firedrill cloud campaign has run.** No simulation credits were spent by this setup.
- No remote MCP connection or Firedrill skill was installed. The CLI is sufficient for this repo's runner setup.

## Erica: connect your account

Use WSL2 on Windows (the CLI's local runner supports macOS/Linux). Do not reuse Bill's credentials or generated machine-local files.

```sh
npm ci
npm run firedrill -- --version
npm run firedrill -- init
npm run firedrill -- status --json
```

Complete sign-in in your browser. Select the team workspace when it is available to your account. GitHub collaborator access does not grant Firedrill workspace membership; ask the workspace owner to invite your Firedrill account separately. Credentials stay in the OS credential store. Follow the CLI's `--session-only` instructions if your WSL environment has no supported store.

## Prepare a machine-local descriptor and plan

```sh
node_modules/node/bin/node scripts/prepare_firedrill.mjs
npm run firedrill -- register --descriptor firedrill/descriptor-local.json --name "Tokensand Calendar Shopping"
```

Copy the returned `descriptor_sha256`, then:

```sh
node_modules/node/bin/node scripts/prepare_firedrill.mjs RETURNED_DESCRIPTOR_DIGEST
npm run firedrill -- status --plan firedrill/plan-local.json --json
```

For an existing agent, use `register --agent <returned-agent-id> --expected-revision <current-revision>` instead of creating another registration. Generate a new revision after changing the bridge or descriptor configuration.

The generated files are gitignored because folder identities and paths are machine-specific. Do not commit them. The process driver launches `.venv/bin/python -m tokensand.bridge`, accepts one JSON request per line and returns the same request ID. Example input:

```json
{"id":"step-1","session":"demo","kind":"message","input":{"event_id":"holiday-dinner-demo"}}
```

The bridge deliberately uses a fixed synthetic memory passage and process-local audit storage. It does not load `.env`, call Cognee, connect to SingleStore, or send analytics. Each new drill gets fresh process state. This isolates policy and tool-failure tests without claiming that fresh processes reset persistent databases. The normal `npm run demo` and web integration mode separately exercise the real local sponsor integrations.

## Tool contract and remaining hosted setup

`tokensand/tools.py` uses Firedrill's documented HTTP envelope:

```json
{"operation":"events.get","arguments":{"event_id":"holiday-dinner-demo"}}
```

Writes also send a stable `idempotency_key`. Routes are injected through `CALENDAR_INVOKE_URL` and `SHOPPING_INVOKE_URL`. Missing routes fail; they never silently switch to real APIs.

Required normalized operations:

| Dependency | Operation | Result |
| --- | --- | --- |
| calendar | `events.get` with `event_id` | Event matching fixture event schema |
| shopping | `products.search` with `category` | Array of fixture-shaped products |
| shopping | `products.get` with `product_id` | Current product snapshot |
| shopping | `tasks.create` with task fields | Saved task, idempotent by `task_key` |
| shopping | `tasks.get` with `task_key` | Saved task or JSON null |

See `fixtures/shopping.json` for event/profile/product schemas and `tokensand/workflow.py` for task fields. This normalized contract is ours; it is **not** a claim that the catalog's Google Calendar schema is identical.

Firedrill's catalog was inspected: Google Calendar is available, but our shopping catalog/task API is custom. Before a hosted drill:

1. Inspect the current catalog tool's operation shapes and adapt the calendar boundary (Google Calendar uses its own event fields).
2. Provide the shopping operations via a custom synthetic tool package, or revise the workflow around a catalog service. `tools init` scaffolds a package, but hosted execution needs a complete valid runtime manifest and implementation; none is fabricated here.
3. Save/pin tool versions and author a world for the registered agent.
4. Run `firedrill plan` to obtain the binding checks and actual credit estimate.
5. Review the exact local command, synthetic destinations and estimate before approving apply/run.
6. Enroll the runner and inspect the report after completion.

The attempted catalog-save command returned `catalog_consent_required`; it was not retried with an approval flag or a guessed cost. This does not block the offline suite or local app.

Suggested hosted scenarios: normal selection; price increase; item sold out; unknown delivery; cancelled event; timeout after task creation; repeated event. Check resulting task state, not only the agent's final text.

## Test the adapter locally today

```sh
npm run test:workflow
```

`tests/test_bridge.py` starts a loopback-only mock service, launches the same JSONL bridge, sends two requests, and verifies one task is saved despite an uncertain write and a repeated invocation. These are local contract tests, not Firedrill-scored results.

Official references:
- https://firedrill.run/agent-setup.md
- https://firedrill.run/run-your-agent.md
- https://docs.firedrill.run/connect/register-agent
- https://docs.firedrill.run/connect/local-plan
- https://docs.firedrill.run/connect/tools
