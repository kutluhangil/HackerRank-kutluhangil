# Evaluation report

All numbers below were measured by running the code in this repository; nothing is estimated.
Labelled data available to participants: the 32 public cases in `dataset/sample_output.csv`.
The 518 evaluation requests have no public labels, so they are checked only for contract validity.

> Status of this report: measured on the **offline/cache run** (no Claude API calls: intent from rules,
> PDFs from `pdftotext`, screenshots not read). It will be re-measured after the live Claude run.

## How to reproduce

```bash
python3 code/main.py                                   # 518 requests -> output.csv (offline/cache mode)
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

## Results on the 32 labelled samples (final offline run)

| Metric | Value |
|---|---|
| Case-level status accuracy | **1.000** (32/32) |
| Exact case accuracy | **0.781** (25/32) |
| Step precision | **0.989** |
| Step recall | **0.969** |
| Step F1 | **0.979** |
| Sequence accuracy (LCS) | **0.969** |

| Field | Accuracy |
|---|---|
| phase | 0.974 |
| system_id | 0.933 |
| resource_id | 0.927 |
| operation | 0.933 |
| state | 0.933 |
| evidence_id | 0.974 |

## Contract validation (518 evaluation requests)

`validate_output.py` checks: exact header; 518 rows; same case ids as `deletion_requests.csv`, no duplicates,
sorted; valid JSON arrays with exactly the 7 step fields; `step_no` 1..n; phase order; operation allowed in its
phase and matching state; canonical order inside each phase (operation table order, then system_id, resource_id);
`NOT_APPLICABLE` <-> `[]`; `COMPLETE` contains only verification steps that cite an existing file/activity/audit id
captured at or before `audit_at`; remediation and post-remediation checks of `INCOMPLETE` cases have `""`.

Result: **0 violations** — 518 rows, 3,137 steps, 162 COMPLETE / 346 INCOMPLETE / 10 NOT_APPLICABLE.
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

C4 also exposed a real gap: offline, case_35 resolves only the subject's account. Its search record
(`search_428`) is shown only in a screenshot (`evidence_09`), which is read only in the live run.

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

## Remaining errors on the samples (7 cases)

| Case | Error | Cause |
|---|---|---|
| case_18, case_20 | missing `VERIFY_RECORD_PRESENT` for `audit_record_6645`, `audit_record_5569` | these ids appear in no participant-visible file; not discoverable |
| case_21, case_25, case_26 | missing anonymized analytics record | the record carries no identifier; the only link is a batch of anonymize actions shared with other cases; strict mode declines to guess |
| case_17 | extra `account_6523` | an account looked up with the subject's address earlier in the year is linked to the subject |
| case_23 | `account_7015` instead of `account_410` | two FAILED account deletes in the same batch; the case-id order tie-break picks the wrong one |

## Known risks on the hidden labels

- Screenshots (11) are read only in the live run; until then, cases that depend on them (subjects user_11-user_22) lose records.
- The batch tie-breaks (case-id order) are inferred from 32 samples only.
- Request intent offline uses rules; the live run uses Claude for every distinct request text.
