# Google Calendar through Airbyte

We run the official `airbyte/source-google-calendar:1.1.0` Docker connector directly using the Airbyte protocol. This is a local source integration, not a full Airbyte server or Airbyte Cloud deployment. No Airbyte account is required. Gmail is deferred; we request no Gmail scopes.

## Mac and Erica's Windows setup

1. Pull the repository and follow [LOCAL_SETUP.md](LOCAL_SETUP.md) first. On Windows, run these commands inside **Ubuntu on WSL2**, with Docker Desktop's WSL integration enabled. Keep the checkout in your WSL home directory. The scripts use `.venv/bin/python`, so native PowerShell is not supported.
2. Install the connector: `npm run calendar:install`. Docker must be running. The app invokes the Linux amd64 image on both platforms; Apple Silicon uses Docker emulation.
3. Create Google OAuth credentials as described below. Each developer signs into their own Google account and keeps their own local token.
4. Run `npm run calendar:connect`. A browser opens for Google sign-in. If it does not (common in WSL), copy the printed authorization URL into the Windows browser on the same machine. WSL localhost forwarding must be enabled. The callback listens only on 127.0.0.1, uses an ephemeral port, and expires after three minutes. Retry the command if it expires.
5. Run `npm run calendar:sync`. A successful command prints only connection status, sync timestamp and event count. `npm run calendar:status` reads local status without contacting Google.
6. Run `npm run app` and open http://localhost:8787. Select an upcoming event, describe what you need, then click **Think ahead**. The shopper UI shows grouped recommendations and saved plans. Sync manually with `npm run calendar:sync`; the token-protected integration lab is at http://localhost:8788/lab (sign in using `npm run admin:token`).

The app refreshes the calendar before researching a selected real event. The event supplies the occasion and deadline. Without an OpenAI API key, recommendations are explicitly fictional preview data. With a key, the agent uses Amazon-only web research; see [AGENT_AND_ADMIN.md](AGENT_AND_ADMIN.md) for limitations and setup. Nothing is purchased. The integration lab retains the separate deterministic jacket workflow for testing Cognee and SingleStore.

## Google Cloud setup, step by step

1. Open https://console.cloud.google.com/ and create/select a project (for example `UpNext`).
2. Go to **APIs & Services → Library**, search **Google Calendar API**, and enable it.
3. Open **Google Auth Platform** and complete **Branding** with an app name, support email and developer contact email. Select **External** under **Audience** unless your organization requires Internal.
4. Keep the app in testing while developing. Add your Google email and Erica's Google email as **Test users** if you share the Cloud project. The address must match the account used for Google sign-in.
5. In **Data Access**, add `https://www.googleapis.com/auth/calendar.readonly`. We do not need Calendar write access, Gmail, or ACL access.
6. Under **Clients**, create an OAuth client with application type **Desktop app**. Download its JSON. Save it as `.local/google-oauth-client.json` in this checkout. Confirm the downloaded JSON exists before leaving the creation screen: Google may only show the secret once. Preserve the JSON; do not paste it into source code or chat. If a browser download fails and the secret is masked, the project owner must add a new client secret through the client details and save it securely, or create/download a replacement Desktop client.
7. Run the connect command above and approve Calendar read access. The script writes `.local/airbyte-calendar.json` with your refresh token and `calendarid: "primary"`. You can change `calendarid` locally to one specific calendar ID from Google Calendar settings. Empty values (all calendars) are disallowed.

Erica may use her own Cloud project/client, or the team's desktop client distributed privately; she must obtain her own refresh token by signing in herself. Repository access does not grant Google Cloud project access. Do not copy another person's `.local` folder or `.env`.

Google may expire refresh tokens after seven days for External apps in Testing; rerun `calendar:connect` when authorization expires. On `access_denied`, check the OAuth app's test users and Workspace administrator policy. On connection failure, check Docker is running and the API is enabled, then reconnect. The app intentionally does not expose upstream logs or tokens in error messages.

## Data flow and audit

`Google Calendar → Airbyte events stream → private atomic snapshot → selected event + preferences → Amazon research (or labeled preview) → grouped review plan + audit`

Only the `events` stream is selected. Each sync performs a full refresh of the single configured calendar; there is no `start_date` cutoff because that field filters modification dates, not upcoming occasions. The app then shows the next 90 calendar days. Full refresh is a deliberate small-calendar MVP choice; incremental sync/checkpoints are future work. Optional proactive scans are configured in the private admin console and require the local server to remain running.

The connector returns recurring series without expanding occurrences. Series with a recurrence rule are excluded in this first version; use a one-off event for the demo. Returned concrete exceptions can appear. Dates retain the event's source timezone, with the local machine date determining the 90-day display window.

Calendar identity includes both `calendar_id` and Google event ID. Task deduplication also includes the event revision (`updated`), so a changed event can create a new review task; old tasks remain historical and are not automatically withdrawn. Before a new run, a removed/cancelled/out-of-window event is treated as unavailable and cannot create a task. A failed or incomplete sync preserves the previous snapshot but **blocks the new run**, rather than silently using stale evidence.

The audit records source, calendar/event IDs, original start, updated timestamp and sync timestamp. Calendar text is data, never agent instructions. Event titles are escaped in the UI. Titles and raw events are not sent to analytics by this integration.

## Local privacy and limitations

OAuth JSON, refresh tokens, calendar snapshots and audit reports live under gitignored `.local/`. Token/snapshot writes use owner-only permissions on Mac/Linux and atomic replacement. Treat `.local`, the SingleStore volume, audit exports and Cognee data as private; there is no app-level encryption at rest. This server is for a single local user and binds to loopback, not a publicly hosted multiuser app.

To disconnect, revoke the app in your Google Account's third-party connections and delete `.local/airbyte-calendar.json` and `.local/calendar-events.json`. Existing audit/task history is separate and is not erased by disconnecting.

## Tests and current verification

`npm run test:workflow` covers calendar identity isolation, date handling, cancelled/deleted-event blocking, incomplete-sync preservation, events-only selection and task deduplication alongside shopping fault cases. These use synthetic Airbyte protocol records; they do not prove Google authorization. A live sync requires each developer's completed OAuth sign-in.

## Next integrations

Gmail is a future opt-in connector for receipts, shipping updates and purchase history. No Gmail code or scopes are enabled. Add future sources behind the same normalized event boundary, with their own consent, freshness, cancellation and deduplication rules. Recurring-event expansion is future work. Optional background scans and the live Amazon research path are described in [AGENT_AND_ADMIN.md](AGENT_AND_ADMIN.md); live research still requires a configured API key and end-to-end verification.

References: [Airbyte Calendar connector](https://docs.airbyte.com/integrations/sources/google-calendar), [Airbyte protocol](https://docs.airbyte.com/platform/understanding-airbyte/airbyte-protocol), [Google Desktop OAuth](https://developers.google.com/identity/protocols/oauth2/native-app), [Google OAuth token expiration](https://developers.google.com/identity/protocols/oauth2#expiration).
