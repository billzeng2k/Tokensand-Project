# Local Qwen and Amazon

UpNext supports Qwen3 through local Ollama for both search planning and recommendation explanations. No OpenAI key, paid search API, or cloud fallback is used in this mode. Calendar context stays in the local model; only generic product queries go to Amazon. The normal app saves recommendations, source excerpts, retrieval timestamps, model timings and token counts in the signed-in user's audit history. Amplitude and Statsig reuse the existing local telemetry/gating pipeline; their cloud dashboards still require separate configuration.

## Start Ollama (Mac)

Install Ollama from its official distribution or Homebrew (`brew install ollama`). From the repository root, keep this terminal running:

```sh
OLLAMA_MODELS="$PWD/.local/ollama-models" OLLAMA_HOST=127.0.0.1:11434 OLLAMA_NO_CLOUD=1 ollama serve
```

In a second terminal:

```sh
ollama pull qwen3:14b
npm run amazon:install
```

14B downloads about 9.3 GB and requires additional inference memory. For a smaller machine, use `qwen3:4b` (about 2.5 GB). Both are installed on Bill's Mac. Do not expose Ollama or UpNext's servers publicly.

Set these values in your own ignored `.env`:

```dotenv
UPNEXT_LLM_PROVIDER=ollama
OLLAMA_MODEL=qwen3:14b
AMAZON_RETRIEVAL=local-browser
```

Restart `npm run app` after changing environment settings.

## Local browser worker (recommended)

Run `npm run amazon:install` after syncing `requirements.lock`. The app starts a dedicated Playwright Chromium worker on its first research request. It uses Amazon's homepage search form, reads product pages, and supplies their text to local Qwen. No extension, browser pairing, extra server port, or manually opened tab is required. It uses a fresh anonymous browser context, not your personal Chrome profile. A browser window is visible by default; `AMAZON_BROWSER_HEADLESS=true` runs it without a window but may change Amazon's response. It stops on robot checks; it does not solve challenges or add anything to a cart.

Only generic queries leave the local model. Product links, page excerpts, timestamps, failures, model requests/responses and token counts stay in the per-user local audit. No hidden reasoning is recorded. Local model API cost is zero. Price/rating fields may remain unknown if the page does not support them, and Prime-only price conditions must be rechecked on Amazon.

On Windows/WSL, run `npm run amazon:install` inside WSL. Headed Chromium needs WSLg (available on supported Windows 11 installations); otherwise configure headless mode. Install any Linux browser dependencies listed by Playwright's installer. Do not expose Ollama or the app outside localhost. See [Playwright browser installation](https://playwright.dev/python/docs/browsers).

## Erica: Windows

Use the project's WSL Ubuntu setup. Install Ollama inside WSL using the [official Linux instructions](https://docs.ollama.com/linux), then run the same commands above in the WSL checkout. Choose 4B if 14B exceeds available RAM/VRAM. Acceleration depends on her GPU/WSL configuration.

From WSL, sync Python dependencies with `uv pip sync requirements.lock`, run `npm run amazon:install`, set the three `.env` values above and start `npm run app`. No extension is needed. This Windows path still needs verification on Erica's machine.

Google OAuth setup is separate: follow [Windows Google OAuth](WINDOWS_GOOGLE_OAUTH.md) and create your own credentials. Gmail remains a future integration.

## CLI and failure tests

`npm run qwen:test -- --model qwen3:14b` tests local inference and writes `.local/qwen-potluck-14b.json`. It uses the same local browser worker as the app. Add `--transport http` only to diagnose direct HTTP retrieval. `blocked_by_amazon` is a failed retrieval, not successful recommendations.

Run `npm run test:workflow` for automated tests. Fixture tests verify bounded retrieval, unsupported numeric fields, unavailable companion, timeout cleanup, and no paid fallback. They are not a Firedrill cloud campaign. Model API spend is zero; electricity, hardware and internet costs are excluded.

## Optional Chrome companion (experimental)

The companion remains available with `AMAZON_RETRIEVAL=browser`, but the local worker is the default. Codex's embedded browser rejected background extension tabs and interrupted the trial. Use regular Chrome if testing this optional transport.

Direct Amazon HTTP search returned 503 during testing, while ordinary browser search worked. The companion uses Chrome to read Amazon search/product pages. It opens temporary foreground tabs and closes only those it created. It never adds to cart or checks out, and stops on robot checks rather than attempting to solve them.

1. Run `npm run amazon:setup`. It prints the absolute path to `.local/amazon-extension`.
2. Open `chrome://extensions`, enable Developer mode, choose **Load unpacked**, and select that folder.
3. Click **UpNext Amazon Companion** in Chrome's extensions menu. Keep its tab open. It should say **Connected** while `npm run app` runs.
4. In UpNext, open the calendar event and request recommendations. Qwen plans up to two searches, reads up to three Amazon products, then groups recommendations and explains their relevance.

Only `www.amazon.com` and the local bridge at `127.0.0.1:8789` are allowed. The generated extension contains a random local pairing token. Do not commit/share the generated directory, token file, or `.env`. Each teammate generates their own copy. After pulling extension code changes, run setup again and click Reload in `chrome://extensions`. Pause the companion or close its tab to stop accepting work. This is a development companion, not a published Chrome Web Store extension.

Amazon pages may still be unavailable, incomplete, or blocked. The app reports that honestly and never substitutes demo products. Missing price/rating/review count stays unknown. Prices are observations, not guaranteed checkout prices. The companion is trusted local software and can submit page evidence; it is not a cryptographic proof of Amazon content. Never load a modified companion from an untrusted source.

## Verified local run

On November 20, 2026, the app completed real Amazon research with Qwen3 14B on Bill's Mac: two Amazon searches, three retrieved product pages, and two local model calls. The first run returned three products in about 127 seconds; the thumbnail-enabled run selected two products in about 106 seconds. Both selected product images loaded in the app. Product links, prices, ratings, variants and Prime-price conditions were displayed; unavailable review counts stayed unknown. Generated recipe ideas are labeled separately. No paid model/search API was called. Automated validation: 78 tests passing. Windows setup remains unverified on Erica's hardware.
