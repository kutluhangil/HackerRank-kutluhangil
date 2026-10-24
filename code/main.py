"""Ghost Data Still Exists - deletion audit agent.

    python3 code/main.py                      # audits dataset/deletion_requests.csv -> ./output.csv
    python3 code/main.py --requests R --out O # any request file
    python3 code/main.py --dry-run            # how many API calls a live run would make (no network)
    python3 code/main.py --live               # additionally allow Claude API calls (otherwise cache/offline)
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import sys
from datetime import datetime, timezone
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


class LiveRunFailed(RuntimeError):
    pass


def run_agent(requests_path: Path, out_path: Path, dataset: Path = DATASET, live: bool = False,
              dry_run: bool = False) -> list[dict]:
    with open(dataset / "system_activity.csv", newline="", encoding="utf-8") as fh:
        activity = list(csv.DictReader(fh))
    llm = LLM(ROOT / "code" / "cache" / "llm_cache.json", root=ROOT, live=live, dry_run=dry_run)
    if live and not llm.online:
        raise LiveRunFailed("--live needs ORCHESTRATE_ANTHROPIC_API_KEY (or ANTHROPIC_API_KEY) and the anthropic package")
    store = build_store(dataset, activity, media_extractor(llm))
    identities = IdentityIndex(dataset)
    planner = Planner(store, activity)
    with open(requests_path, newline="", encoding="utf-8") as fh:
        requests = list(csv.DictReader(fh))
    context = all_requests(requests, dataset)
    intent = classify_all(llm, context)
    if dry_run:
        print(f"dry run: {len(llm.planned)} API request(s) would be sent "
              f"({sum(p == 'intent' for p in llm.planned)} intent, "
              f"{sum(p.startswith('media') for p in llm.planned)} media); "
              f"{sum(c['cached'] for c in llm.calls)} answer(s) already cached. Nothing written.")
        return []
    if llm.failures:   # never mix live answers with silent fallbacks: keep the previous output untouched
        raise LiveRunFailed("live run had failed model calls (successful answers are cached; re-run to retry): "
                            + "; ".join(llm.failures))
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

    # write next to the target, then swap atomically; keep the previous file as a timestamped backup
    tmp = out_path.with_name(out_path.name + ".tmp")
    with open(tmp, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["case_id", "deletion_status", "steps_json"], lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    if out_path.exists():
        backups = ROOT / "backups"            # outside code/, so never packaged
        backups.mkdir(exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        shutil.copy2(out_path, backups / f"{out_path.stem}.{stamp}{out_path.suffix}")
    os.replace(tmp, out_path)
    meta = {"model": llm.model, "live": llm.online, "requests": len(rows), "calls": llm.calls,
            "media_extractions": llm.extractions}
    out_path.with_suffix(".usage.json").write_text(json.dumps(meta, indent=1, default=sorted))
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--requests", default=str(DATASET / "deletion_requests.csv"))
    ap.add_argument("--out", default=str(ROOT / "output.csv"))
    ap.add_argument("--live", action="store_true",
                    help="allow Claude API calls (needs ORCHESTRATE_ANTHROPIC_API_KEY); default: cache + offline fallback")
    ap.add_argument("--dry-run", action="store_true",
                    help="count the API requests a live run would send (cache misses); no network, nothing written")
    args = ap.parse_args()
    try:
        rows = run_agent(Path(args.requests), Path(args.out), live=args.live, dry_run=args.dry_run)
    except LiveRunFailed as e:
        print(f"ERROR: {e}\n{args.out} was not modified.")
        sys.exit(2)
    if not args.dry_run:
        print(f"wrote {len(rows)} rows to {args.out} ({'live' if args.live else 'offline/cache'} mode)")


if __name__ == "__main__":
    main()
