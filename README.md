# Ghost Data Still Exists — deletion audit agent

HackerRank Orchestrate (October 2026). Challenge: https://www.hackerrank.com/contests/hackerrank-orchestrate-october26/challenges/ghost-data-still-exists
Full task contract: [`problem_statement.md`](./problem_statement.md).

For every request in `dataset/deletion_requests.csv` the agent decides whether deletion was requested,
reconstructs the subject's current and historical identifiers, rebuilds the state of every related record at
`audit_at` from the evidence, applies `deletion_rules.csv`, and writes ordered findings / remediation /
verification steps to `output.csv`.

## Setup

```bash
python3 --version            # 3.10+
pip install -r code/requirements.txt   # only needed for live Claude calls (anthropic SDK)
# PDF text extraction uses `pdftotext` (poppler-utils), available on most Linux/macOS setups
```

Optional, for live Claude calls: put the key in the environment or in an uncommitted `.env` at the repo root:

```
ORCHESTRATE_ANTHROPIC_API_KEY=...        # ANTHROPIC_API_KEY also works
ORCHESTRATE_MODEL=claude-opus-5-5        # default
```

## Run

```bash
python3 code/main.py            # offline/cache mode: no API calls; writes ./output.csv and ./output.usage.json
python3 code/main.py --dry-run  # prints how many API requests a live run would send (cache misses); writes nothing
python3 code/main.py --live     # additionally lets Claude classify request intent and read screenshots/PDFs
python3 code/evaluation/validate_output.py     # output contract checks
python3 code/evaluation/main.py                # score on the 32 labelled samples
python3 code/evaluation/custom_cases.py        # team-authored evaluation cases
python3 code/evaluation/usage_report.py        # writes code/evaluation/usage_report.md from output.usage.json
```

Model answers are cached in `code/cache/llm_cache.json` (keyed by model + prompt + input), so a re-run with the
same inputs repeats no paid call and gives the same output. The submitted `code.zip` includes this cache, so
`python3 code/main.py` without a key reproduces the submitted `output.csv` exactly.

Live requests opt into Anthropic's server-side refusal fallback (`fallbacks: "default"`). If a safety classifier
declines a request, the API re-runs it on its recommended fallback model; in the final run this happened for one
screenshot, which `claude-opus-4-8` answered.

Safety of a live run: if any model call fails, is refused, is truncated or returns unusable JSON, the run stops
with exit code 2 and `output.csv` is left untouched (successful answers stay cached, so a re-run only retries the
failures). Output is written to a temporary file and swapped in atomically; the previous file is copied to
`backups/` (outside `code/`). The key is read from the environment only and never printed or logged.

Screenshots do not always print resource ids: a console shows `delivery_confirmation_19.pdf` or `user_17`
where the data catalogue (`LINK_RESOURCE_IDENTITY` rows in `system_activity.csv`) maps that label to
`object_19` / `tombstone_17`. These label -> id pairs are given to the model with every artifact and are also
applied deterministically to its answer.

## Architecture

```
dataset/ ──► evidence.py ──► observations (file/activity id, time, system, resource, present?, PII?, enabled?,
   │            ▲              restore allowed?, retention, identifiers)
   │         media.py  (Claude vision for PNG, Claude on pdftotext output for PDF; offline: pdftotext + regex)
   │
   ├──► identity.py   email -> user; all current + historical emails/phones/hashes (sha256 of every email)
   ├──► intent.py     Claude (batched, multilingual) -> DELETE / NOT_DELETE; rules as fallback
   ├──► batch.py      attributes workflow activity that names no person to cases in the same processing batch
   └──► planner.py    related records -> state at audit_at -> deletion_rules.csv -> ordered steps
                       └──► main.py writes output.csv (sorted, deterministic JSON)
```

Key decisions

- **Deterministic core, model at the edges.** 79 of 94 evidence files are structured (SQL, JSON, logs, text) and
  are parsed exactly; the model is used where language or pixels are involved (request intent, 11 screenshots,
  4 PDFs). This keeps answers reproducible and cheap.
- **Claims are not proof.** Workflow `reported_status` and activity `reported_result` never set a state; only
  observations do (read-backs, snapshots, lookups, scans, connector checks, restore checks).
- **State at `audit_at`.** Only evidence captured at or before `audit_at` is used or cited; the latest explicit
  observation wins; absence by omission is inferred only from complete account listings.
- **Policy mapping.** profile/search/cache/export/marketing/attachments -> delete; support messages, email logs,
  tombstones -> redact; analytics -> anonymize; security audit / legal hold -> retain and verify present;
  data flows -> disable; backups -> block restore. Remediation disables flows and blocks restores first.

## Layout

```
code/main.py                     entry point
code/ghost_audit/                evidence, identity, intent, batch, planner, llm, media, prompts
code/evaluation/main.py          sample scoring
code/evaluation/validate_output.py, custom_cases.py, usage_report.py
code/evaluation/evaluation_report.md, usage_report.md
```
