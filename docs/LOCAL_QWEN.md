# Local Qwen / Amazon experiment

This is a bounded command-line experiment, not yet the shopper app's provider. It calls Qwen3 4B through local Ollama, asks for up to two generic product searches, and reads at most three Amazon product pages. It uses no cloud inference or paid search APIs. Amazon can reject both browser and HTTP access; a local model cannot resolve that restriction. Blocked retrieval must never turn into invented products, prices or ratings.

## Mac

Install Ollama from its official distribution or Homebrew (`brew install ollama`). From the repository root, start a local-only server in one terminal:

```sh
OLLAMA_MODELS="$PWD/.local/ollama-models" OLLAMA_HOST=127.0.0.1:11434 OLLAMA_NO_CLOUD=1 ollama serve
```

In another terminal:

```sh
ollama pull qwen3:4b
npm run qwen:test
```

For the larger 14B model, run `ollama pull qwen3:14b`, then `npm run qwen:test -- --model qwen3:14b`. The 14B download is about 9.3 GB.

The 4B model download is about 2.5 GB; inference needs additional memory. Keep this server running for the test. It is not configured to start automatically at login. If Ollama is already listening on port 11434, use that server only after verifying it is local and has cloud inference disabled.

## Erica: Windows

The existing project scripts run in WSL Ubuntu. Install the official Linux Ollama distribution inside WSL (see [Ollama Linux setup](https://docs.ollama.com/linux)), then use the same server and test commands above from the WSL checkout. Hardware acceleration and speed depend on her Windows GPU/WSL configuration; this path has not been tested on her machine. Do not expose Ollama on a public interface. Do not copy Bill's model cache, credentials or environment file; download the model on her machine.

## Result and audit

The private result is `.local/qwen-potluck-test.json`. It contains query-planning output, retrieval URLs/statuses, timestamps, local token counts, model duration, validated recommendations, and source excerpts when pages are readable. Hidden reasoning is not saved. The default occasion is Thanksgiving potluck; override with `npm run qwen:test -- --event 'Birthday picnic'`.

`blocked_by_amazon` means no eligible product evidence was obtained. A successful model response alone is not a successful shopping task. No checkout occurs. Model API spend is zero; local hardware, electricity and internet are not priced in that figure. The app remains on its existing provider until this experiment proves useful; no OpenAI key or credits are used by this script.

## Sponsor additions that fit

- **Firedrill:** replay Amazon failure, missing prices and timeouts against the retrieval boundary. Local failure tests are included; these are not a Firedrill cloud campaign.
- **Amplitude / Statsig:** reuse the app's existing metadata-only telemetry and gates when this provider is integrated. Measure retrieval success separately from JSON validity and recommendation usefulness. This standalone experiment currently writes only its local audit.
- **Cognee:** add per-user remembered preferences and past choices after account isolation is implemented. Never send unrelated user memories into a run.
- **SingleStore:** mirror per-user source snapshots and task history after isolation is ready. Current app histories remain in SQLite.
- **Senso:** possible later curated product/context source; not a confirmed Amazon catalog or a fix for blocked retailer pages.

References: [Qwen3 4B model](https://ollama.com/library/qwen3:4b), [Ollama Chat API](https://docs.ollama.com/api/chat).

## Verified local smoke test (November 20, 2026)

Qwen3 4B completed two local model calls in approximately 3.7 seconds combined on Bill’s 48 GB Apple Silicon Mac. It generated an Amazon query, observed HTTP 503, and returned zero products with questions about guest count, dietary restrictions, hosting role and existing belongings. This verifies local inference and failure handling, not successful Amazon product research. No model API charges were incurred.
