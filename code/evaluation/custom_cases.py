"""Team-authored evaluation cases that target failure modes the public samples do not isolate.

Each case rewrites one request (same case_id, so batch context stays consistent), runs the agent
offline, and checks an explicit expectation.

    python3 code/evaluation/custom_cases.py
"""
from __future__ import annotations

import csv
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "code" / "evaluation"))
sys.path.insert(0, str(ROOT / "code"))          # code/main.py must win over evaluation/main.py

from main import run_agent  # noqa: E402
from validate_output import validate  # noqa: E402

DATASET = ROOT / "dataset"


def load_rows(name: str) -> dict:
    with open(DATASET / name, newline="", encoding="utf-8") as fh:
        return {r["case_id"]: r for r in csv.DictReader(fh)}


SAMPLES = load_rows("sample_deletion_requests.csv")
GOLD = {cid: (r["deletion_status"], json.loads(r["steps_json"])) for cid, r in load_rows("sample_output.csv").items()}
TEST = load_rows("deletion_requests.csv")


def run_one(row: dict) -> tuple[str, list, list]:
    with tempfile.TemporaryDirectory() as tmp:
        req, out = Path(tmp) / "req.csv", Path(tmp) / "out.csv"
        with open(req, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(row))
            w.writeheader()
            w.writerow(row)
        run_agent(req, out)
        errors = validate(out, req)
        with open(out, newline="", encoding="utf-8") as fh:
            r = next(csv.DictReader(fh))
        return r["deletion_status"], json.loads(r["steps_json"]), errors


def case_new_email_same_subject():
    """C1 identity: case_29 was filed with the subject's OLD address; filing it with the NEW
    address (audit_284) must resolve the same person and give the gold answer."""
    row = dict(SAMPLES["case_29"], email="noah.f4380@outlook.com")
    status, steps, errors = run_one(row)
    gold = GOLD["case_29"]
    return status == gold[0] and steps == gold[1] and not errors, f"status={status} steps={len(steps)} gold_steps={len(gold[1])}"


def case_audit_cutoff_hides_later_evidence():
    """C2 time: case_11 cites the 2026-10-01 handover (evidence_03). Moving audit_at one day
    earlier must stop the agent from citing it or anything captured after the new cut-off."""
    row = dict(SAMPLES["case_11"], audit_at="2026-09-30T12:00:00Z")
    status, steps, errors = run_one(row)
    cited = {s["evidence_id"] for s in steps if s["evidence_id"]}
    return "evidence_03" not in cited and not errors, f"status={status} cited={sorted(cited)}"


def case_non_deletion_multilingual():
    """C3 intent: a Turkish correction request that says 'do not delete' must be NOT_APPLICABLE with [],
    while a German erasure request for the same person must be audited."""
    keep = dict(SAMPLES["case_05"], request_text="Hesabımı silmeyin, lütfen sadece telefon numaramı güncelleyin.")
    erase = dict(SAMPLES["case_05"], request_text="Bitte löschen Sie mein Konto und alle zugehörigen Daten.")
    s1, st1, e1 = run_one(keep)
    s2, st2, e2 = run_one(erase)
    ok = s1 == "NOT_APPLICABLE" and st1 == [] and s2 == GOLD["case_05"][0] and not (e1 or e2)
    return ok, f"turkish={s1} german={s2}"


def case_decoy_lookalike_address():
    """C4 decoys: logs search for 'g.silva76.jr@gmail.com' (another person). The audit for
    g.silva76@gmail.com (case_35) must not include records reached only through the look-alike."""
    status, steps, errors = run_one(dict(TEST["case_35"]))
    rids = {s["resource_id"] for s in steps}
    return "search_1874" not in rids and not errors, f"status={status} resources={sorted(rids)}"


def case_uppercase_identifier():
    """C5 normalisation: case_54 is filed as BCARVALHO6517@GMAIL.COM; evidence stores the address in
    upper and lower case. Matching must be case-insensitive and find the profile's search record."""
    status, steps, errors = run_one(dict(TEST["case_54"]))
    rids = {s["resource_id"] for s in steps}
    return "search_3995" in rids and not errors, f"status={status} resources={sorted(rids)}"


CASES = [case_new_email_same_subject, case_audit_cutoff_hides_later_evidence, case_non_deletion_multilingual,
         case_decoy_lookalike_address, case_uppercase_identifier]


def main():
    passed = 0
    for fn in CASES:
        ok, detail = fn()
        passed += ok
        print(f"{'PASS' if ok else 'FAIL'}  {fn.__name__}: {detail}")
    print(f"{passed}/{len(CASES)} custom cases passed")
    sys.exit(0 if passed == len(CASES) else 1)


if __name__ == "__main__":
    main()
