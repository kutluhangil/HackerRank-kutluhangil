"""Contract checks for output.csv (no labels needed).

    python3 code/evaluation/validate_output.py [--out output.csv] [--requests dataset/deletion_requests.csv]
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATASET = ROOT / "dataset"

OPS = {
    "FINDING": {"REPORT_REMAINING_RECORD": "PRESENT", "REPORT_EXPOSED_PII": "PRESENT",
                "REPORT_ACTIVE_DATA_FLOW": "ACTIVE", "REPORT_RESTORE_RISK": "ACTIVE"},
    "REMEDIATION": {"DISABLE_DATA_FLOW": "DISABLED", "BLOCK_RESTORE": "BLOCKED", "DELETE_RECORD": "ABSENT",
                    "REDACT_RECORD": "REDACTED", "ANONYMIZE_RECORD": "ANONYMIZED"},
    "VERIFICATION": {"VERIFY_RECORD_ABSENT": "ABSENT", "VERIFY_RECORD_PRESENT": "PRESENT",
                     "VERIFY_RECORD_REDACTED": "REDACTED", "VERIFY_RECORD_ANONYMIZED": "ANONYMIZED",
                     "VERIFY_DATA_FLOW_DISABLED": "DISABLED", "VERIFY_RESTORE_BLOCKED": "BLOCKED"},
}
PHASES = list(OPS)
FIELDS = {"step_no", "phase", "system_id", "resource_id", "operation", "state", "evidence_id"}


def _ids(path: Path, col: str, time_col: str) -> dict:
    with open(path, newline="", encoding="utf-8") as fh:
        return {r[col]: r[time_col] for r in csv.DictReader(fh)}


def validate(out: Path, requests: Path) -> list[str]:
    errors: list[str] = []
    evidence_time = {}
    evidence_time.update(_ids(DATASET / "evidence_files.csv", "file_id", "captured_at"))
    evidence_time.update(_ids(DATASET / "system_activity.csv", "activity_id", "event_time"))
    evidence_time.update(_ids(DATASET / "user_audit_log.csv", "audit_id", "event_time"))
    with open(requests, newline="", encoding="utf-8") as fh:
        req = {r["case_id"]: r for r in csv.DictReader(fh)}
    with open(out, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames != ["case_id", "deletion_status", "steps_json"]:
            errors.append(f"header is {reader.fieldnames}")
        rows = list(reader)
    ids = [r["case_id"] for r in rows]
    if len(rows) != len(req):
        errors.append(f"{len(rows)} rows, expected {len(req)}")
    if set(ids) != set(req):
        errors.append(f"case ids differ: missing {sorted(set(req) - set(ids))[:5]} extra {sorted(set(ids) - set(req))[:5]}")
    dup = [c for c, n in Counter(ids).items() if n > 1]
    if dup:
        errors.append(f"duplicate case ids {dup[:5]}")
    num = [int(c.rsplit("_", 1)[1]) for c in ids]
    if num != sorted(num):
        errors.append("rows are not sorted by case_id")
    for r in rows:
        cid, status = r["case_id"], r["deletion_status"]
        where = f"{cid}:"
        if status not in ("COMPLETE", "INCOMPLETE", "NOT_APPLICABLE"):
            errors.append(f"{where} bad status {status}")
        try:
            steps = json.loads(r["steps_json"])
        except json.JSONDecodeError as e:
            errors.append(f"{where} invalid JSON ({e})")
            continue
        if not isinstance(steps, list):
            errors.append(f"{where} steps_json is not an array")
            continue
        if status == "NOT_APPLICABLE" and steps:
            errors.append(f"{where} NOT_APPLICABLE with steps")
        if status != "NOT_APPLICABLE" and not steps:
            errors.append(f"{where} {status} without steps")
        phases = [s.get("phase") for s in steps]
        if status == "COMPLETE" and any(p != "VERIFICATION" for p in phases):
            errors.append(f"{where} COMPLETE contains non-verification steps")
        if status == "INCOMPLETE" and "FINDING" not in phases:
            errors.append(f"{where} INCOMPLETE without findings")
        if [PHASES.index(p) for p in phases if p in PHASES] != sorted(PHASES.index(p) for p in phases if p in PHASES):
            errors.append(f"{where} phases out of order")
        audit_at = req.get(cid, {}).get("audit_at", "9999")
        for i, s in enumerate(steps, 1):
            if set(s) != FIELDS:
                errors.append(f"{where} step {i} fields {sorted(s)}")
                continue
            if s["step_no"] != i:
                errors.append(f"{where} step_no {s['step_no']} at position {i}")
            ops = OPS.get(s["phase"])
            if ops is None or s["operation"] not in ops:
                errors.append(f"{where} step {i} operation {s['operation']} not allowed in {s['phase']}")
            elif ops[s["operation"]] != s["state"]:
                errors.append(f"{where} step {i} state {s['state']} for {s['operation']}")
            ev = s["evidence_id"]
            future = s["phase"] == "REMEDIATION" or (status == "INCOMPLETE" and s["phase"] == "VERIFICATION")
            if future and ev != "":
                errors.append(f"{where} step {i} future step cites {ev}")
            if not future:
                if ev not in evidence_time:
                    errors.append(f"{where} step {i} unknown evidence '{ev}'")
                elif evidence_time[ev] > audit_at:
                    errors.append(f"{where} step {i} cites {ev} captured after audit_at")
        for phase in PHASES:                         # within a phase: operation table order, then system, resource
            seq = [(list(OPS[phase]).index(s["operation"]), s["system_id"], s["resource_id"])
                   for s in steps if s.get("phase") == phase and s.get("operation") in OPS[phase]]
            if seq != sorted(seq):
                errors.append(f"{where} {phase} steps not in canonical order")
    return errors


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "output.csv"))
    ap.add_argument("--requests", default=str(DATASET / "deletion_requests.csv"))
    args = ap.parse_args()
    errors = validate(Path(args.out), Path(args.requests))
    with open(args.out, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    steps = sum(len(json.loads(r["steps_json"])) for r in rows)
    print(f"rows={len(rows)} steps={steps} statuses={dict(Counter(r['deletion_status'] for r in rows))}")
    print("OK - no contract violations" if not errors else f"{len(errors)} violation(s):")
    for e in errors[:50]:
        print("  ", e)
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
