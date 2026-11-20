# Event chat, purchases and memory

## Pull and start (Bill and Erica)

From the repository checkout, after merging the PR:

```sh
git switch main
git pull --ff-only origin main
npm install
uv pip sync requirements.lock
npm run amazon:install
```

Follow [Local Qwen and Amazon](LOCAL_QWEN.md) to install Ollama, download `qwen3:14b` (or `qwen3:4b` on a smaller machine), and keep `ollama serve` running on localhost. In your own ignored `.env`, set:

```dotenv
UPNEXT_LLM_PROVIDER=ollama
OLLAMA_MODEL=qwen3:14b
AMAZON_RETRIEVAL=local-browser
```

Start `npm run app` and open `http://localhost:8787`. No Amazon extension is needed. The browser worker starts on demand; local Qwen makes no paid API calls. Windows uses the existing WSL Ubuntu setup; headed Chromium needs WSLg, or set `AMAZON_BROWSER_HEADLESS=true`. See [Windows Google OAuth](WINDOWS_GOOGLE_OAUTH.md) for Erica's own Google client and sign-in setup. Do not copy Bill's `.env`, OAuth client JSON, `.local`, session keys, model cache or database.

Existing SQLite stores upgrade automatically with additive tables. No reset or manual migration is needed. Existing preferences and recommendation history remain intact.

## Event workflow

- Click a calendar event. Its shareable local route is `/#event-details/<event-id>`. Refreshing keeps the selected event after Google session restoration. Each account can only open its own synced events.
- Use the right-hand chat to ask for something specific, such as “I also want a turkey hat.” New products are appended to the event's recommendations and deduplicated by Amazon product ID. Existing recommendations remain visible during research or if a later request fails.
- The page polls pending runs every 1.5 seconds, including after refresh. Progress follows the saved run state; completed/failed/blocked/interrupted runs stop polling. Network errors are shown and retried. There is no server-sent-event stream.
- **✓ Purchased** records your report that you purchased the item. It never checks out or charges you. The item moves to Purchase history, with its event and the time you marked it. Displayed prices are observed recommendation prices, not receipt totals. Undo restores the item.
- **× Not for me** hides an item for that event. Restore it under “Not buying for this event.” A dismissal is not treated as permanent dislike of a brand or category.
- Check **Remember this for future events** before sending a preference. The exact note is stored in your account and used in future research. View or forget notes under “What UpNext remembers.” Purchased items are supplied as user-reported possessions so the model can avoid duplicates.

## Persistence and telemetry

Item snapshots and actions are stored in per-user `item_decisions`; explicit notes are in `preference_notes`. Chat remains in the existing per-user run/conversation ledger. All endpoints use the signed-in server-selected account scope, and item actions resolve against saved recommendations rather than trusting client-supplied prices or product data. Purchase/dismiss events send only allowlisted metadata to the existing telemetry outbox; product details and preference text stay in local storage.

Validation includes purchase persistence/idempotency/undo, event-scoped dismissal, cross-account isolation, explicit-memory deletion and event/conversation matching. `npm run test:workflow` runs the test suite.

## Verified in the browser

The purchase marker persisted through a refresh and was undone after testing. An event deep link restored the correct event and chat. A live “turkey hat” follow-up using local Qwen/Amazon added a product alongside the existing recommendations; the page was refreshed while research was pending and polling resumed through completion. No checkout was performed. Backend validation: 83 tests pass.
