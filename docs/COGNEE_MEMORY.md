# Cognee shopping memory

Set `UPNEXT_COGNEE_MEMORY=1` in your local `.env` and restart `npm run app`. Cognee 1.6.10 is already pinned in the Python dependencies; Erica uses the same WSL setup as the app. No Cognee cloud account or paid API key is needed.

Before each signed-in user's recommendation workflow, UpNext passes the current explicit preferences, reported purchases, and event-specific dismissals through Cognee's `remember(QAEntry)` and `recall(scope="session")` APIs. The retrieved snapshot becomes the model's shopping context. The audit trail includes a `cognee.session_recall` span and `memory_backend=cognee-session-local`.

This is persistent local **session-memory retrieval**, not semantic graph search. Self-improvement and graph retrieval are disabled, so this integration does not call a paid model. SQLite remains the source of truth for user actions. A new preference, forget, purchase, dismissal, or undo rebuilds that event's derived memory before retrieval. Unchanged memory is recalled from the existing Cognee store.

Each account and event has a separate filesystem store and subprocess under ignored `.local/users/<account>/cognee-shopping/<event>/`. A worker never searches another account's store. When an old event is next researched, its memory is rebuilt from current settings; obsolete derived stores are not used for another event. If Cognee fails, the workflow uses the current SQLite snapshot and records `profile-fallback` and a memory warning instead of claiming successful recall.
