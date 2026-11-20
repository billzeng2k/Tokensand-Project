# Erica: Google sign-in and Calendar on Windows

Use your own Google Cloud project and Web OAuth client. You do not need Bill's `.local/google-web-client.json`, `.env`, sessions, or Calendar tokens. GitHub access does not grant access to his Google Cloud project.

## 1. Prepare Windows and WSL

Install [Ubuntu on WSL2](https://learn.microsoft.com/windows/wsl/install) and [Docker Desktop](https://docs.docker.com/desktop/setup/install/windows-install/). In Docker Desktop, enable its WSL2 engine and **Settings → Resources → WSL Integration → Ubuntu**. Keep Docker Desktop running. Install Git, Python 3, Node/npm and [uv](https://docs.astral.sh/uv/getting-started/installation/) inside Ubuntu. All commands below run in the **Ubuntu terminal**, not PowerShell. Current scripts use `.venv/bin/python`.

Accept the repository invitation and authenticate Git with your GitHub account. For a new checkout:

```sh
mkdir -p ~/projects
cd ~/projects
git clone https://github.com/billzeng2k/Tokensand-Project.git
cd Tokensand-Project
git switch feat/upcoming-calendar-view
npm ci
uv venv --python 3.12
uv pip sync requirements.lock
npm run setup
npm run calendar:install
```

If already cloned, enter that checkout, save any local changes, then `git fetch origin`, `git switch feat/upcoming-calendar-view` and `git pull --ff-only`. After the feature branch is merged, use `main` instead. Run the install/setup commands there. `npm run setup` creates `.env` only if it does not exist. Cognee, SingleStore, Firedrill and telemetry cloud keys are not required for Google sign-in and Calendar sync.

## 2. Configure your Google Cloud project

In your Windows browser, open [Google Cloud Console](https://console.cloud.google.com/):

1. Create/select your own project, for example **UpNext Erica Development**.
2. Open **APIs & Services → Library**, find **Google Calendar API**, and enable it.
3. Open **Google Auth Platform**. Complete **Branding** with an app name, support email and developer contact email.
4. Choose an **External** audience and keep publishing status **Testing**. Under **Audience → Test users**, add the exact Google email you will use to sign in. Add any other people who will test your client explicitly.
5. Under **Data Access**, add `openid`, `email`, `profile`, and `https://www.googleapis.com/auth/calendar.readonly`. The identity scopes may appear under their full Google userinfo names. Do not add Gmail or Calendar write scopes.
6. Under **Clients → Create client**, choose **Web application**, not Desktop app. Name it **UpNext Windows development**.
7. Add this exact **Authorized redirect URI**:

   `http://localhost:8787/auth/google/callback`

   No JavaScript origin is required by UpNext's server-side flow.
8. Create the client and download its JSON. Keep the secret private; download it while Google makes it available.

The same localhost callback works on both computers because each runs its own backend. You are setting up the developer application; future hosted-app users will just sign in.

## 3. Copy the JSON into the WSL checkout

From the repository root in Ubuntu, replace the example Windows username and filename below with your actual download path (quotes handle spaces):

```sh
mkdir -p .local
install -m 600 '/mnt/c/Users/YOUR_WINDOWS_USERNAME/Downloads/YOUR_DOWNLOADED_CLIENT.json' .local/google-web-client.json
```

Keep the checkout under `~/projects`, not under `/mnt/c`. Check the shape without printing the client secret:

```sh
.venv/bin/python - <<'PY'
import json
from pathlib import Path
client = json.loads(Path('.local/google-web-client.json').read_text()).get('web', {})
assert client.get('client_id') and client.get('client_secret'), 'Download a Web application client JSON, not Desktop app JSON'
assert 'http://localhost:8787/auth/google/callback' in client.get('redirect_uris', []), 'Add the exact callback in Google Cloud and download again'
print('Web OAuth configuration looks valid; no secrets printed.')
PY
git check-ignore .local/google-web-client.json .env
```

Both paths should be reported as ignored. Never force-add them. In the local `.env`, set `UPNEXT_APP_URL=http://localhost:8787`. Leave `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` empty when using the JSON file: nonempty environment values override it. Avoid copying Bill's configuration. Restart the app after configuration changes.

## 4. Sign in and sync

```sh
npm run app
```

Leave the Ubuntu terminal running. In Windows Chrome/Edge, open **http://localhost:8787** (not `127.0.0.1`). Sign in with your Google test-user account. Click the Calendar card at the bottom of the sidebar, choose **Connect Google Calendar**, and approve read-only access with the same account. Click **Connected → Sync calendar**. Airbyte runs locally in Docker; the first sync can take a few minutes.

Check that your upcoming primary-calendar events appear. Refresh the page: you should remain signed in. Sessions last seven days unless you sign out or clear cookies/local storage files. Google consent and the UpNext session are separate; Google's Testing mode can require Calendar reconnection after seven days. Separate Holidays/Birthdays calendars are not imported. Without a model API key, shopping results remain clearly labeled samples.

## Troubleshooting

| Symptom | What to check |
| --- | --- |
| Sign-in is unavailable | JSON is in this checkout's `.local`, has a `web` object, and the backend was restarted. |
| `redirect_uri_mismatch` | Callback matches scheme, `localhost`, port 8787 and `/auth/google/callback` exactly; check `.env` overrides. |
| Access blocked / app in testing | Add your Google sign-in email under Audience → Test users in your own project. |
| Calendar connection fails | Use the same Google account as your current UpNext session and approve Calendar access. |
| Sync fails | Run `docker info` inside Ubuntu; enable Docker's Ubuntu WSL integration and run `npm run calendar:install`. Reconnect if consent expired. |
| Browser cannot reach localhost | Keep the backend running; check WSL localhost forwarding and port conflicts. Do not expose the backend/admin publicly. |
| Wrong account's events expected | Only the signed-in account's primary calendar is synced. Local data is not shared between Bill's and Erica's machines. |

This Windows/WSL walkthrough has not been executed on a Windows machine in this session. The app flow was verified on macOS. See [authentication and storage details](GOOGLE_SIGN_IN.md), [Google's server OAuth documentation](https://developers.google.com/identity/protocols/oauth2/web-server), and [Google OAuth client management](https://support.google.com/cloud/answer/15549257).
