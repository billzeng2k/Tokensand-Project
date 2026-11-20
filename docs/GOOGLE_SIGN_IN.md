# Google sign-in and Calendar: Bill and Erica

## User experience

Open http://localhost:8787, select **Sign in with Google**, then **Connect Google Calendar**. Approve read-only Calendar access using the **same Google account**, then select **Sync calendar**. Upcoming events appear in the occasion selector. Sign-in alone does not grant Calendar access. Users never provide API keys, download credential files, or open Airbyte's dashboard.

The backend runs the official pinned Airbyte Google Calendar Docker source. OAuth obtains the user's grant; Airbyte performs discovery and an events-only full refresh of their primary calendar. This is the direct connector runtime, not Airbyte Cloud or a full self-hosted Airbyte platform.

## One-time developer setup

On Mac use Terminal. On Windows use Ubuntu in WSL2 with Docker Desktop's WSL integration enabled; clone inside the WSL filesystem. Native PowerShell is not supported by the current npm scripts.

```sh
git pull
npm ci
uv venv --python 3.12
uv pip sync requirements.lock
npm run setup
npm run calendar:install
```

Google requires the application owner to configure a Web OAuth client once:

1. Select the UpNext project in [Google Cloud Console](https://console.cloud.google.com/). Enable **Google Calendar API**.
2. Configure Google Auth Platform branding, support/developer contact email, and External audience. Keep publishing status **Testing** for development. Add Bill's and Erica's Google accounts under **Audience → Test users**. Each person's email must match their Google sign-in account.
3. Under **Data Access**, declare `openid`, `email`, `profile`, and `https://www.googleapis.com/auth/calendar.readonly`. No Gmail, Calendar write, or ACL scopes are needed.
4. Under **Clients**, create a **Web application** client named `UpNext web development`. The previous **Desktop app** client is for the legacy CLI only and cannot replace this client.
5. Register the exact authorized redirect URI **`http://localhost:8787/auth/google/callback`**. Use `localhost` when opening the app, not `127.0.0.1`. No JavaScript origin is needed for this backend authorization-code flow.
6. Download the Web client's JSON immediately and save it as `.local/google-web-client.json`. Alternatively put `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` in the ignored `.env`. Verify the download before leaving the creation page, since Google may hide the secret afterward. Never commit it or paste it into chat.
7. Set `UPNEXT_APP_URL=http://localhost:8787` in `.env` and restart `npm run app`.

Erica can create her own Web client/project using the same localhost callback, or obtain the team's development client through a private credential channel. Each machine runs its own local backend and storage. Sharing this development credential does **not** share user sessions or Calendar refresh tokens. Do not copy `.local` or `.env` between developers.

Google login and Calendar permissions open within the browser. There is no terminal OAuth callback script in the normal app flow. On WSL, open localhost:8787 in the Windows browser; localhost forwarding must be enabled. Google redirects back to this running backend.

## Verify the flow

1. Sign in, save a preference, create a sample plan, then sign out.
2. Sign in as a second test user (or use a separate browser profile). The first user's preferences, events and plans must not appear.
3. Connect Calendar, then sync. Missing Docker, denied permission, an account mismatch, or incomplete Airbyte sync yields an error; the app does not silently use a synthetic calendar.
4. Select an event and run a plan. Without `OPENAI_API_KEY` the product recommendations are explicitly labeled samples. Live Amazon research needs the app owner's OpenAI key on the backend; shoppers do not supply one.
5. Open http://localhost:8788 and sign in with `npm run admin:token`. Select an account to inspect its metrics, traces and settings. The legacy workspace remains a separate choice.

Automated verification: `npm run test:workflow`. OAuth exchanges and Google signatures are mocked at the provider boundary in integration tests; a real Google sign-in and real Airbyte sync are separate checks requiring the Web client and consent. Passing tests does not claim a live Google connection.

## Storage and access boundaries

- Verified Google `sub`, not email or a browser-supplied account ID, determines the internal account identity. ID tokens are checked with Google's `google-auth` library for signature, audience, issuer and expiry, plus an explicit nonce check.
- Browser-bound, short-lived, single-use OAuth state and PKCE protect the callback. Calendar consent must match both the signed-in session and Google identity. Denied/partial permission is rejected.
- Random session tokens use HttpOnly/SameSite cookies; only token hashes persist. Sign-out revokes the session. Sessions expire after seven days. HTTPS configuration adds Secure cookies.
- Account identities and sessions live in `.local/accounts.sqlite3`. Calendar refresh tokens are encrypted with Fernet. The encryption key comes from `UPNEXT_TOKEN_ENCRYPTION_KEY`, or an automatically generated owner-only `.local/token-encryption.key`. Preserve the key securely across restarts; do not commit it. The key and database on the same disk do not protect against an attacker who controls that machine.
- Each account has its own `.local/users/<internal-id>/agent-traces.sqlite3` and Calendar snapshot, covering conversations, runs, preferences, review tasks, feedback, telemetry outbox and scan deduplication. Request scope is selected server-side and propagated to worker jobs. Shopper-supplied account headers are ignored.
- Existing demo history is **not** assigned to the first person who signs in. Shared legacy Cognee memory and SingleStore trace mirroring are disabled for signed-in users until those integrations have account isolation. Their standalone lab remains available to the operator.
- Calendar **Disconnect** removes the stored grant and local event snapshot, serializes against active syncs, and stops future Calendar reads. Previously saved plans/audits remain. To revoke permission at Google as well, remove UpNext in Google Account → Third-party connections.
- Google credentials are never returned to the frontend or included in request logs. Airbyte receives credentials only in temporary owner-only files, removed when the connector finishes. Full calendar/conversation data stays on the backend. Amplitude/Statsig retain their existing optional metadata-only delivery, using an account-specific anonymous identifier.

## Troubleshooting and hosting boundary

- **Sign-in unavailable:** configure the Web client and restart the backend. A Desktop JSON is intentionally not accepted.
- **redirect_uri_mismatch:** register the exact callback above; scheme, host, port and path must match `UPNEXT_APP_URL`.
- **Access blocked:** ensure both accounts are test users. The app is not publicly verified. External apps in Testing may issue refresh tokens that expire after seven days; use **Reconnect Google Calendar**.
- **Calendar connection failed:** use the same account as your UpNext sign-in and approve Calendar access. Sign out first to switch accounts.
- **Sync failed:** ensure Docker is running and the connector is installed; reconnect if authorization expired. A failed sync preserves the last snapshot, and research refreshes the calendar before using an event.

This change adds authentication and account isolation, but it does **not** deploy a public service. The Python HTTP server and admin listener still bind to loopback. Production deployment needs a supported application server/reverse proxy, trusted host/origin configuration, HTTPS, secrets management, backups/retention, abuse/rate controls, and Google's publication/verification requirements. Do not expose the existing admin listener publicly. Separate developer machines do not synchronize app data.

References: [Google server OAuth](https://developers.google.com/identity/protocols/oauth2/web-server), [Google OpenID Connect](https://developers.google.com/identity/openid-connect/openid-connect), [Airbyte Calendar source](https://docs.airbyte.com/integrations/sources/google-calendar).
