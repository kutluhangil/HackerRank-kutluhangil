# Handoff notes (for the next coding session)

State as of 2026-10-24 ~23:45 UTC (session 1). Deadline (assumed): 2026-10-25 17:33 UTC (20:33 Turkey time).

## Done
- `code/ghost_audit/evidence.py` – parsers for SQL / JSON / 5 log dialects / text handover / activity checks -> `Obs`.
- `identity.py` – current + historical identifiers (audit log, sha256 email hashes).
- `planner.py` – relevance, state at audit_at (explicit evidence > omission; omission only for account tables),
  policy mapping to steps, ordering.
- `batch.py` – attributes anonymous workflow activity to cases (reported_status <-> reported_result,
  evidence ownership, case-id order, strict mode for anonymous policy actions).
- `intent.py` + `llm.py` + `media.py` + `prompts.py` – Claude for request intent and screenshots/PDFs,
  disk cache in `code/cache/llm_cache.json`, offline fallback (rules / pdftotext).
- `code/evaluation/main.py` – scores against sample_output (status, exact, step P/R/F1, LCS sequence, field accuracy).
- Offline sample score: status 1.00, exact 0.75, step F1 0.974.

## Next
1. New session must have `ORCHESTRATE_ANTHROPIC_API_KEY` (cloud env variable). Run `python3 code/main.py`
   (live LLM calls are cached), then `python3 code/evaluation/main.py`.
2. Check media extraction output for the 11 PNGs + 4 PDFs (users 11-22 cases 33+).
3. Write `code/evaluation/evaluation_report.md` (metrics + >=3 custom cases + failures/improvements)
   and `code/evaluation/usage_report.md` (from `output.usage.json`).
4. Root `README.md` run instructions; package `code.zip`; keep appending to `log.txt`.

## Known gaps
- Some gold resources are not discoverable from participant data (e.g. audit_record_6645, 5569).
- Anonymous policy actions in mixed batches are ambiguous; strict mode only assigns when counts match.
