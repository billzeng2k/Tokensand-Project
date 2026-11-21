# Daily calendar recommendations

Open **Settings** in UpNext after signing in. Choose a daily time, an IANA timezone (for example `America/Los_Angeles` or `America/New_York`), and a lookahead in positive whole days (default 30, with no 30-day cap). Enable the schedule and save. Home uses the same lookahead. The calendar connector currently exposes the next 365 days, so longer settings cannot add events outside that sync window. Settings belong to the signed-in account and persist locally; Erica configures her own schedule after Google sign-in.

**Sync calendar** also automatically queues recommendation research using the saved lookahead, even when the daily schedule is disabled. Internal calendar refreshes during product research do not queue another batch. Repeated syncs while a batch is queued or running are coalesced.

The built-in scheduler checks every 15 seconds while the app is running. It syncs the primary calendar through Airbyte, excludes events titled exactly “Sleep” (case-insensitive, ignoring surrounding spaces), and researches Amazon products with the configured model. It skips sleep events, events with existing live recommendations, and queued/running research. Demo recommendations do not block real research. A prior live “no action needed” result is also respected. Purchased/dismissed recommendations are not automatically regenerated.

Each account has one persistent daily claim in its local timezone, including across daylight saving changes and server restarts. If the computer was asleep or UpNext was stopped at the scheduled time, it catches up once after starting that day. It does not replay older missed days. A failed sync preserves old data but does not research against it. Research failure stops the batch; uncovered events are eligible the next day. Completed recommendation runs and their conversations remain in the existing local audit ledger. Settings shows the last batch result.

## Running locally on Mac or Windows

Keep these running:

1. Docker Desktop (or the WSL Docker integration) for Airbyte.
2. Ollama using the model directory and commands in [LOCAL_QWEN.md](LOCAL_QWEN.md).
3. UpNext: `npm run app` from the repository root.

The browser tab can be closed. The computer must remain awake, logged in, and online; Amazon research may open browser windows. This is an app-managed daily scheduler, not an OS cron installation or a hosted service. Changing the time in Settings takes effect without editing a crontab. Local Qwen incurs no paid model API usage. If you change to a paid provider later, scheduled research uses that provider too.

Windows users should follow [WINDOWS_GOOGLE_OAUTH.md](WINDOWS_GOOGLE_OAUTH.md) and [LOCAL_SETUP.md](LOCAL_SETUP.md). No credentials or account scheduling data should be committed or shared.

Disable the checkbox to pause future work. An already running product lookup finishes, then the batch stops before the next event. Saving a new time after today's batch does not run another batch that day.
