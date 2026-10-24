# Usage report

Generated 2026-10-24T21:50Z from `output.usage.json`, the log of the run that produced `output.csv`.

## Final full-dataset run (measured)

- Requests processed: **518**
- Configured model: `claude-opus-5-5` (provider: Anthropic)
- Live API calls allowed in this run: **yes (--live)**
- Model requests in this run: **31** (1 sent to the API, 30 served from cache)

| Model | Calls | from cache | Input tokens | Output tokens | Total tokens | Est. cost (USD) |
|---|---|---|---|---|---|---|
| `claude-opus-4-8` | 1 | 0 | 3,481 | 296 | 3,777 | $0.0248 |
| `claude-opus-5-5` | 30 | 30 | 66,512 | 15,657 | 82,169 | $0.5792 |
| **Overall** | **31** | **30** | **69,993** | **15,953** | **85,946** | **$0.6040** |

| Purpose | Calls | Input tokens | Output tokens |
|---|---|---|---|
| intent | 16 | 26,398 | 6,921 |
| media | 15 | 43,595 | 9,032 |

- Average tokens per request: **165.9** (135.1 input + 30.8 output)
- Estimated cost per request: **$0.00117**
- Cost uses Anthropic list prices per 1M tokens: `claude-opus-5-5` $4.00 in / $20.00 out, `claude-opus-4-8` $5.00 in / $25.00 out, `claude-sonnet-5-5` $2.00 in / $10.00 out, `claude-haiku-5-5` $0.10 in / $0.50 out.
- Cached calls report the tokens of the original paid call; they cost nothing when replayed.

## What the model read from screenshots and PDFs (for human review)

| File | Resource | Present | Direct identifiers | Enabled | Restore allowed | Identifiers |
|---|---|---|---|---|---|---|
| evidence_04 | account_5762 | True | True | None | None | 3 |
| evidence_04 | support_9538 | True | False | None | None | 0 |
| evidence_09 | search_428 | True | True | None | None | 2 |
| evidence_09 | search_1874 | True | True | None | None | 1 |
| evidence_14 | data_flow_1121 | True | True | True | None | 1 |
| evidence_14 | data_flow_9846 | True | True | True | None | 1 |
| evidence_18 | export_1842 | True | True | None | None | 2 |
| evidence_19 | analytics_7438 | True | True | None | None | 2 |
| evidence_23 | export_1261 | True | True | None | None | 1 |
| evidence_23 | export_1260 | True | True | None | None | 1 |
| evidence_23 | export_1259 | True | True | None | None | 1 |
| evidence_23 | export_1258 | True | True | None | None | 1 |
| evidence_27 | tombstone_17 | True | False | None | None | 1 |
| evidence_28 | support_1034 | True | True | None | None | 1 |
| evidence_32 | backup_9291 | True | True | None | None | 1 |
| evidence_32 | backup_9288 | True | True | None | None | 1 |
| evidence_32 | backup_9287 | True | True | None | None | 1 |
| evidence_32 | backup_9286 | True | True | None | None | 1 |
| evidence_32 | backup_9281 | True | False | None | None | 0 |
| evidence_37 | audit_record_003 | True | False | None | None | 1 |
| evidence_37 | audit_record_002 | True | False | None | None | 1 |
| evidence_37 | audit_record_001 | True | False | None | None | 1 |
| evidence_37 | audit_record_006 | True | False | None | None | 1 |
| evidence_37 | audit_record_005 | True | False | None | None | 1 |
| evidence_37 | audit_record_004 | True | False | None | None | 1 |
| evidence_42 | tombstone_17 | True | False | None | None | 1 |
| evidence_46 | object_19 | True | False | None | None | 0 |
| evidence_55 | audit_record_003 | True | False | None | None | 1 |
| evidence_58 | support_001 | True | True | None | None | 2 |
| evidence_60 | marketing_001 | True | True | None | None | 2 |

## Where the model is (and is not) used

- Request intent: one call per 25 distinct request texts (multilingual DELETE vs NOT_DELETE).
- Screenshots and PDFs: one call per artifact (15 files), producing structured observations.
- Everything else (parsing 79 structured evidence files, identity resolution, state reconstruction, policy mapping, step ordering) is deterministic Python: 0 tokens.

## Pre-run estimate (NOT measured)

Made before any live call, from input sizes; kept only for comparison with the measured tables above.

| Workload | Calls | Est. input tokens | Est. output tokens (incl. thinking) |
|---|---|---|---|
| Request intent (375 distinct texts, 25 per call, effort `low`) | ~15 | ~27K | ~6K-36K |
| Screenshots (11 PNG, vision) + PDFs (4, extracted text), effort `medium` | 15 | ~44K | ~15K-45K |
| **Total** | **~30** | **~71K** | **~21K-81K** |

At Claude Opus 5.5 list prices ($4 / $20 per 1M input / output tokens) this is roughly **$0.70-$1.90 for the
whole dataset, i.e. about $0.001-$0.004 per request**. Responses are cached on disk
(`code/cache/llm_cache.json`), so re-running the pipeline repeats no paid calls.


## All API traffic behind the final output (session of 2026-10-24)

The table above describes the last invocation only. Every paid request made to produce `output.csv`:

| Invocation | Requests sent | Result |
|---|---|---|
| Smoke test (one-word prompt, same client settings) | 1 | OK; 18 input / 4 output tokens |
| `main.py --live` #1 | 31 (16 intent + 15 media) | 30 answered and cached; 1 media request (`evidence_09`) declined by a safety classifier (`stop_reason=refusal`). The run aborted with exit code 2 and left `output.csv` untouched, because a parser bug also rejected the 14 media answers |
| `main.py --live` #2, after fixing the parser and enabling server-side fallback | 1 (`evidence_09`) | Served by `claude-opus-4-8` through `fallbacks: "default"`; the 30 answers from #1 were replayed from the cache |

- Paid requests in total: **33** (31 + 1 + 1). The 30 cached answers in the table were paid once, in invocation #1, and are counted only once above.
- The declined request in invocation #1 recorded no usage, so its tokens are **not** in the tables. Its input was the same size as the fallback call, about 3.5K tokens. Even if all of it was billed at the Opus 5.5 input price, it would add at most about $0.014.
- Measured total for the final output: about **$0.60** ($0.58 for `claude-opus-5-5` + $0.02 for the `claude-opus-4-8` fallback), or about **$0.0012 per request**. The pre-run estimate was $0.70-$1.90.
