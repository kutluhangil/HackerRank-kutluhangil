"""Ghost Data Still Exists - deletion audit agent.

    python3 code/main.py                      # audits dataset/deletion_requests.csv -> ./output.csv
    python3 code/main.py --requests R --out O # any request file
    python3 code/main.py --live               # additionally allow Claude API calls (otherwise cache/offline)
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from ghost_audit.batch import batch_links  # noqa: E402
from ghost_audit.evidence import build_store  # noqa: E402
from ghost_audit.identity import IdentityIndex  # noqa: E402
from ghost_audit.intent import classify_all  # noqa: E402
from ghost_audit.llm import LLM  # noqa: E402
from ghost_audit.media import media_extractor  # noqa: E402
from ghost_audit.planner import Planner  # noqa: E402

DATASET = ROOT / "dataset"


def case_sort_key(cid: str):
    head, _, num = cid.rpartition("_")
    return (head, int(num)) if num.isdigit() else (cid, 0)


def all_requests(requests, dataset) -> list[dict]:
    """The given requests plus every other participant-visible request (batch context)."""
    context = {r["case_id"]: r for r in requests}
    for name in ("deletion_requests.csv", "sample_deletion_requests.csv"):
        path = dataset / name
        if path.exists():
            with open(path, newline="", encoding="utf-8") as fh:
                for r in csv.DictReader(fh):
                    context.setdefault(r["case_id"], r)
    return list(context.values())


def workflow_links(context, identities, planner, activity, intent) -> dict[str, set]:
    """Attribute batch workflow activity to deletion cases."""
    rows = [r for r in context if intent.get(r["case_id"])]
    subjects = {r["case_id"]: identities.resolve(r["email"], r["audit_at"]) for r in rows}
    owners = planner.owners(max(r["audit_at"] for r in rows), identities) if rows else {}
    # legacy accounts keep the subject's number in their id (account_005 <-> user_05)
    for uid in identities.users:
        num = uid.split("_")[1]
        legacy = f"account_{int(num):03d}"
        if num.startswith("0") and not owners.get(legacy):
            owners[legacy] = {uid}
    return batch_links(rows, subjects, owners, activity)


def run_agent(requests_path: Path, out_path: Path, dataset: Path = DATASET, live: bool = False) -> list[dict]:
    with open(dataset / "system_activity.csv", newline="", encoding="utf-8") as fh:
        activity = list(csv.DictReader(fh))
    llm = LLM(ROOT / "code" / "cache" / "llm_cache.json", root=ROOT, live=live)
    store = build_store(dataset, activity, media_extractor(llm))
    identities = IdentityIndex(dataset)
    planner = Planner(store, activity)
    with open(requests_path, newline="", encoding="utf-8") as fh:
        requests = list(csv.DictReader(fh))
    context = all_requests(requests, dataset)
    intent = classify_all(llm, context)
    links = workflow_links(context, identities, planner, activity, intent)

    rows = []
    for req in sorted(requests, key=lambda r: case_sort_key(r["case_id"])):
        status, steps = "NOT_APPLICABLE", []
        if intent[req["case_id"]]:
            subj = identities.resolve(req["email"], req["audit_at"])
            if subj is not None:
                status, steps = planner.plan(subj, req["audit_at"], links.get(req["case_id"], set()))
            else:
                status = "COMPLETE"
        rows.append({"case_id": req["case_id"], "deletion_status": status,
                     "steps_json": json.dumps(steps, ensure_ascii=False, separators=(",", ":"))})
    with open(out_path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["case_id", "deletion_status", "steps_json"], lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    usage_path = out_path.with_suffix(".usage.json")
    usage_path.write_text(json.dumps({"model": llm.model, "live": llm.online, "requests": len(rows),
                                      "calls": llm.calls}, indent=1))
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--requests", default=str(DATASET / "deletion_requests.csv"))
    ap.add_argument("--out", default=str(ROOT / "output.csv"))
    ap.add_argument("--live", action="store_true",
                    help="allow Claude API calls (needs ORCHESTRATE_ANTHROPIC_API_KEY); default: cache + offline fallback")
    args = ap.parse_args()
    rows = run_agent(Path(args.requests), Path(args.out), live=args.live)
    print(f"wrote {len(rows)} rows to {args.out} ({'live' if args.live else 'offline/cache'} mode)")


if __name__ == "__main__":
    main()
