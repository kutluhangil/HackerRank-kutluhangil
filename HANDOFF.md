# Handoff notes (for the next coding session)

State after session 1 (see log.txt for times). Deadline (assumed from the email time 20:33 GMT+3): 2026-10-25 17:33 UTC.

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
- Offline sample score: status 1.00, exact 0.781, step F1 0.979; output.csv validated (0 violations); custom cases 5/5.
- Reports: `code/evaluation/evaluation_report.md` (measured, offline) and `usage_report.md` (generated; offline run = 0 calls).

## Next
0. **Do not make any Claude API call until the user explicitly approves it in chat.** Live calls need `--live`.
1. New session has `ORCHESTRATE_ANTHROPIC_API_KEY` (cloud env variable). After approval: `python3 code/main.py --live`
   (answers are cached), then `python3 code/evaluation/main.py`, `validate_output.py`, `custom_cases.py`,
   `usage_report.py`, and update the numbers in `evaluation_report.md`.
2. Check media extraction output for the 11 PNGs + 4 PDFs (users 11-22 cases 33+).
3. Package: `zip -r code.zip README.md code -x "*/__pycache__/*" "*/.venv/*" "*/venv/*" "*/node_modules/*" "*/.git/*" "*/.DS_Store"`.
4. Keep appending to `log.txt` with real `date -u` timestamps.

## Known gaps
- Some gold resources are not discoverable from participant data (e.g. audit_record_6645, 5569).
- Anonymous policy actions in mixed batches are ambiguous; strict mode only assigns when counts match.
