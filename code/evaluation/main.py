"""Evaluation harness: score predictions against labelled cases.

Usage:
    python3 code/evaluation/main.py                       # samples: run agent on sample requests and score
    python3 code/evaluation/main.py --pred P --gold G     # score any two CSV files
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "code"))

FIELDS = ("phase", "system_id", "resource_id", "operation", "state", "evidence_id")


def load(path: Path) -> dict:
    with open(path, newline="", encoding="utf-8") as fh:
        return {r["case_id"]: (r["deletion_status"], json.loads(r["steps_json"])) for r in csv.DictReader(fh)}


def key(s):
    return tuple(s[f] for f in FIELDS)


def lcs(a, b):
    dp = [[0] * (len(b) + 1) for _ in range(len(a) + 1)]
    for i in range(len(a)):
        for j in range(len(b)):
            dp[i + 1][j + 1] = dp[i][j] + 1 if a[i] == b[j] else max(dp[i][j + 1], dp[i + 1][j])
    return dp[-1][-1]


def score(pred: dict, gold: dict, verbose: bool = True) -> dict:
    m = Counter()
    field_hits = Counter()
    failures = []
    for cid, (gstat, gsteps) in sorted(gold.items()):
        pstat, psteps = pred.get(cid, ("MISSING", []))
        m["cases"] += 1
        m["status_ok"] += pstat == gstat
        gk, pk = [key(s) for s in gsteps], [key(s) for s in psteps]
        gset, pset = Counter(gk), Counter(pk)
        tp = sum((gset & pset).values())
        m["tp"] += tp
        m["gold_steps"] += len(gk)
        m["pred_steps"] += len(pk)
        exact = pstat == gstat and gk == pk
        m["exact"] += exact
        m["seq_lcs"] += lcs(gk, pk)
        for i, gs in enumerate(gsteps):                       # field accuracy on positionally aligned steps
            ps = psteps[i] if i < len(psteps) else {}
            for f in FIELDS:
                field_hits[f] += ps.get(f) == gs[f]
        if not exact:
            failures.append((cid, gstat, pstat, sorted(set(gk) - set(pk)), sorted(set(pk) - set(gk))))
    n = m["cases"]
    res = {
        "cases": n,
        "status_accuracy": m["status_ok"] / n,
        "exact_case_accuracy": m["exact"] / n,
        "step_precision": m["tp"] / max(m["pred_steps"], 1),
        "step_recall": m["tp"] / max(m["gold_steps"], 1),
        "sequence_accuracy_lcs": m["seq_lcs"] / max(m["gold_steps"], 1),
        "field_accuracy": {f: field_hits[f] / max(m["gold_steps"], 1) for f in FIELDS},
    }
    p, r = res["step_precision"], res["step_recall"]
    res["step_f1"] = 2 * p * r / (p + r) if p + r else 0.0
    if verbose:
        for cid, gstat, pstat, miss, extra in failures:
            print(f"--- {cid}: gold={gstat} pred={pstat}")
            for s in miss:
                print("    missing:", s)
            for s in extra:
                print("    extra:  ", s)
    print(json.dumps(res, indent=2))
    res["failures"] = failures
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pred")
    ap.add_argument("--gold", default=str(ROOT / "dataset" / "sample_output.csv"))
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()
    if args.pred:
        pred = load(Path(args.pred))
    else:
        from main import run_agent  # noqa: E402  (code/main.py)
        out = ROOT / "code" / "evaluation" / "sample_predictions.csv"
        run_agent(ROOT / "dataset" / "sample_deletion_requests.csv", out)
        pred = load(out)
    score(pred, load(Path(args.gold)), verbose=not args.quiet)


if __name__ == "__main__":
    main()
