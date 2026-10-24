# Usage report

Generated 2026-10-24T21:30Z from `output.usage.json`, the log of the run that produced `output.csv`.

## Final full-dataset run (measured)

- Requests processed: **518**
- Configured model: `claude-opus-5-5` (provider: Anthropic)
- Live API calls allowed in this run: **no (offline/cache mode)**
- Model requests in this run: **0** (0 sent to the API, 0 served from cache)

No model calls were made in this run: request intent came from the rule-based fallback and PDFs from `pdftotext`; screenshots were not read. Measured tokens and cost are therefore **0** (0 input, 0 output, $0.00 total, $0.00 per request).

## Where the model is (and is not) used

- Request intent: one call per 25 distinct request texts (multilingual DELETE vs NOT_DELETE).
- Screenshots and PDFs: one call per artifact (15 files), producing structured observations.
- Everything else (parsing 79 structured evidence files, identity resolution, state reconstruction, policy mapping, step ordering) is deterministic Python: 0 tokens.

## Pre-run estimate (NOT measured)

Made before any live call, from input sizes; replace by the measured tables above after the live run.

| Workload | Calls | Est. input tokens | Est. output tokens (incl. thinking) |
|---|---|---|---|
| Request intent (375 distinct texts, 25 per call, effort `low`) | ~15 | ~27K | ~6K-36K |
| Screenshots (11 PNG, vision) + PDFs (4, extracted text), effort `medium` | 15 | ~44K | ~15K-45K |
| **Total** | **~30** | **~71K** | **~21K-81K** |

At Claude Opus 5.5 list prices ($4 / $20 per 1M input / output tokens) this is roughly **$0.70-$1.90 for the
whole dataset, i.e. about $0.001-$0.004 per request**. Responses are cached on disk
(`code/cache/llm_cache.json`), so re-running the pipeline repeats no paid calls.
