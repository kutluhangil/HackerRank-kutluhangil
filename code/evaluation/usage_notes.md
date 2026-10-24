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
