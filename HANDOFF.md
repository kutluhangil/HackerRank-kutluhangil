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

## Session 2 (2026-10-24, final live run) - DONE
- Live run completed: 518 rows, 0 contract violations; 33 paid requests in total, about $0.60 (see usage_report.md).
- Bugs found live and fixed: `parse_json` read the inner `[` of `{"records": [...]}` (all media answers rejected);
  `evidence_09` refused by a classifier -> server-side `fallbacks: "default"` (answered by claude-opus-4-8).
- Samples live: status 1.000, exact 0.750, F1 0.969 (offline was 0.781 / 0.979): two cases gained steps from
  media evidence that predates their request (case_07 object_19, case_17 tombstone_17). Left as is, documented.
- Keyless `python3 code/main.py` reproduces output.csv byte-for-byte from the cache.

## Next (historical, session 1 plan)
0. **Do not make any Claude API call until the user explicitly approves it in chat.** Live calls need `--live`.
1. Preview without network: `python3 code/main.py --dry-run` (expected: 31 requests = 16 intent + 15 media).
2. After approval: `python3 code/main.py --live`. Exit code 2 = some call failed; output.csv untouched; re-run retries only failures.
3. Then (all offline, cache only):
   `python3 code/evaluation/validate_output.py`
   `python3 code/evaluation/main.py`
   `python3 code/evaluation/custom_cases.py`
   `python3 code/evaluation/usage_report.py`
   Review the media table in usage_report.md; update numbers/status lines in evaluation_report.md.
4. Package: `zip -r code.zip README.md code -x "*/__pycache__/*" "*/.venv/*" "*/venv/*" "*/node_modules/*" "*/.git/*" "*/.DS_Store"`.
5. Keep appending to `log.txt` with real `date -u` timestamps.

## Known gaps
- Some gold resources are not discoverable from participant data (e.g. audit_record_6645, 5569).
- Anonymous policy actions in mixed batches are ambiguous; strict mode only assigns when counts match.
