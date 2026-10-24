# Evaluation report

All numbers below were measured by running the code in this repository; nothing is estimated.
Labelled data available to participants: the 32 public cases in `dataset/sample_output.csv`.
The 518 evaluation requests have no public labels, so they are checked only for contract validity.

> Status of this report: measured on the **final live run** of 2026-10-24 (`main.py --live`; request intent,
> 11 screenshots and 4 PDFs read by Claude, all 15 media files produced observations). The earlier offline
> numbers are kept next to them for comparison.

## How to reproduce

```bash
python3 code/main.py --live                            # 518 requests -> output.csv (cached answers are replayed)
python3 code/evaluation/validate_output.py             # contract checks on output.csv
python3 code/evaluation/main.py                        # run on the 32 samples and score vs sample_output.csv
python3 code/evaluation/custom_cases.py                # team-authored cases below
```

## Metrics definitions

| Metric | Definition |
|---|---|
| Case-level status accuracy | share of cases whose `deletion_status` equals the label |
| Exact case accuracy | status equal **and** the full ordered `steps_json` equal (all 7 fields, same order) |
| Step precision / recall / F1 | multiset match of steps on (phase, system_id, resource_id, operation, state, evidence_id) |
| Field accuracy | per field, predicted step at position *i* vs labelled step at position *i* |
| Sequence accuracy | length of the longest common subsequence of predicted and labelled step lists / labelled steps |

## Results on the 32 labelled samples

| Metric | Final live run | Offline run (no media reading) |
|---|---|---|
| Case-level status accuracy | **1.000** (32/32) | 1.000 (32/32) |
| Exact case accuracy | **0.750** (24/32) | 0.781 (25/32) |
| Step precision | **0.969** | 0.989 |
| Step recall | **0.969** | 0.969 |
| Step F1 | **0.969** | 0.979 |
| Sequence accuracy (LCS) | **0.969** | 0.969 |

| Field | Final live run | Offline run |
|---|---|---|
| phase | **0.959** | 0.974 |
| system_id | **0.922** | 0.933 |
| resource_id | **0.917** | 0.927 |
| operation | **0.917** | 0.933 |
| state | **0.927** | 0.933 |
| evidence_id | **0.964** | 0.974 |

**The live run scores slightly lower on the samples than the offline run.** Recall is unchanged; all of the
difference is 5 extra steps in two cases, both caused by correctly read media evidence that is older than the
request (see the table of remaining errors below). The live answers were not changed to recover the offline score.
Fitting the planner to these two labels would mean dropping evidence that participant data and policy support.
On the 518 evaluation requests, the media readings change 12 rows; 8 of them go from COMPLETE to INCOMPLETE.
Each of those 8 cites a screenshot or PDF captured between `requested_at` and `audit_at` for the right subject
(e.g. case_35: `search_428` in `evidence_09`; case_61: `object_19` in `evidence_46`). This is the remaining-data
pattern the challenge targets, and the offline path cannot see it.

## Contract validation (518 evaluation requests)

`validate_output.py` checks: exact header; 518 rows; same case ids as `deletion_requests.csv`, no duplicates,
sorted; valid JSON arrays with exactly the 7 step fields; `step_no` 1..n; phase order; operation allowed in its
phase and matching state; canonical order inside each phase (operation table order, then system_id, resource_id);
`NOT_APPLICABLE` <-> `[]`; `COMPLETE` contains only verification steps that cite an existing file/activity/audit id
captured at or before `audit_at`; remediation and post-remediation checks of `INCOMPLETE` cases have `""`.

Result (final live output): **0 violations** — 518 rows, 3,173 steps, 154 COMPLETE / 354 INCOMPLETE / 10 NOT_APPLICABLE.
The same validator also passes on `dataset/sample_output.csv`, which confirms the checks match the official format.

## Team-authored evaluation cases (`custom_cases.py`)

Each case rewrites one request (keeping its case_id so batch context stays consistent), runs the agent and
checks an explicit expectation. Result: **5/5 pass**.

| # | Case | What it isolates | Expectation | Result |
|---|---|---|---|---|
| C1 | case_29 filed with the subject's **new** address (`audit_284` changed it) instead of the old one | identity resolution across email history | same subject, output identical to the label (14 steps) | PASS |
| C2 | case_11 with `audit_at` moved one day earlier (2026-09-30) | time cut-off | the 2026-10-01 handover (`evidence_03`) and anything captured later are never cited | PASS |
| C3 | case_05 rewritten as a Turkish "do not delete, only update my phone" request, and as a German erasure request | intent, multilingual, explicit negation | Turkish -> `NOT_APPLICABLE` with `[]`; German -> audited like the original | PASS |
| C4 | case_35 (`g.silva76@gmail.com`) while logs search for `g.silva76.jr@gmail.com` | decoy look-alike identifiers | no record reached only through the look-alike (`search_1874`) | PASS |
| C5 | case_54 filed as `BCARVALHO6517@GMAIL.COM` | identifier normalisation | upper/lower-case variants match; the subject's `search_3995` is found | PASS |

C4 also exposed a real gap in the offline path: there, case_35 resolves only the subject's account, because its
search record (`search_428`) is shown only in a screenshot (`evidence_09`). In the final live run, C4 finds
`account_013` and `search_428` and still never reaches the look-alike `search_1874`.

## Failures found and improvements made

Measured on the 32 samples after each change (step F1 / exact-case accuracy / status accuracy).

| # | Change | Failure it fixed | F1 | Exact | Status |
|---|---|---|---|---|---|
| 1 | Baseline: parsers + identity + planner | — | 0.834 | 0.281 | 0.875 |
| 2 | Attribute workflow batches: account delete result mirrors `reported_status` (SUCCESS/PARTIAL/FAILED) | accounts known only from activity rows (e.g. `account_5521`) were missing | 0.843 | 0.344 | 0.938 |
| 3 | Explicit observations beat "absent by omission"; legacy `account_0NN` ownership; fix intent rule that read "copy of my profile" as an export request | wrong evidence ids; case_05 wrongly NOT_APPLICABLE | 0.926 | 0.500 | 0.969 |
| 4 | Take identifiers from every field of a log trace (e.g. `subject_ref`); retained records may be discovered from later exports of earlier snapshots (never cited) | missing `VERIFY_RECORD_PRESENT` for security audit records | 0.932 | 0.531 | 0.969 |
| 5 | Omission implies absence only for account tables (other snapshot collections are partial) | retained audit records wrongly treated as deleted | 0.945 | 0.594 | 0.969 |
| 6 | Anonymous policy actions go only to cases without an evidence-owned record of that system, and only when counts match ("strict") | false anonymized-analytics steps (precision 0.948 -> 0.978) | 0.955 | 0.656 | 0.969 |
| 7 | PDF evidence via `pdftotext` fallback; intent wired through `classify_all` | support attachment in a PDF (case_07) | 0.974 | 0.750 | 1.000 |
| 8 | An inventory capture with zero rows is a failed export, not proof of absence; empty JSON listings still count | wrong evidence id for absent accounts (case_04, case_31) | 0.979 | 0.781 | 1.000 |
| 9 | Live run: `parse_json` decoded the first `[` before the first `{`, so every `{"records": [...]}` media answer was parsed as its inner list and rejected (14/15 media files). The abort guard stopped the run with `output.csv` untouched. Fix: decode from whichever opener comes first | all screenshot/PDF answers lost | — | — | — |
| 10 | Live run: one screenshot (`evidence_09`) was declined by a safety classifier (`stop_reason=refusal`). Fix: server-side `fallbacks: "default"`; the request was answered by `claude-opus-4-8` | a case_35 search record would have been lost | — | — | — |
| 11 | Final live run with media observations | — | 0.969 | 0.750 | 1.000 |

## Remaining errors on the samples (8 cases, final live run)

| Case | Error | Cause |
|---|---|---|
| case_07 | extra finding/delete/verify for `object_19` | `evidence_46` (2026-02-13) shows the subject's attachment `delivery_confirmation_19.pdf` = `object_19`. That is half a year before this request (2026-08-31), and the gold steps leave it out. The planner treats the latest observation as current state, even when it predates the request |
| case_18, case_20 | missing `VERIFY_RECORD_PRESENT` for `audit_record_6645`, `audit_record_5569` | these ids appear in no participant-visible file; not discoverable |
| case_21, case_25, case_26 | missing anonymized analytics record | the record carries no identifier; the only link is a batch of anonymize actions shared with other cases; strict mode declines to guess |
| case_17 | extra `account_6523`; extra `VERIFY_RECORD_REDACTED` for `tombstone_17` | an account looked up with the subject's address earlier in the year is linked to the subject. The tombstone is already compliant according to `evidence_42`/`evidence_27`, which also predate the request; gold verifies tombstones only in COMPLETE cases or after redacting them |
| case_23 | `account_7015` instead of `account_410` | two FAILED account deletes in the same batch; the case-id order tie-break picks the wrong one |

## Known risks on the hidden labels

- Media evidence captured **before** a request is still used as current state (case_07, case_17 above). Only 2 of 32
  samples are affected, so no rule was fitted to them.
- Media extraction depends on the model; its readings are listed per file in `usage_report.md` for human review.
  I checked them by hand for evidence_09 and evidence_46, and they match the images.
- The batch tie-breaks (case-id order) are inferred from 32 samples only.
- Request intent offline uses rules; the live run uses Claude for every distinct request text.
