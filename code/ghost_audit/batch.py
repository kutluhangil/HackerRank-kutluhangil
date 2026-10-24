"""Link workflow activity to cases when no evidence names the subject.

The deletion worker processes requests in batches that end at the workflow's `reported_at`.
Inside a batch the activity rows carry only resource ids, so we attribute them by elimination:

* the account delete's `reported_result` mirrors the case's `reported_status`
  (SUCCESS <-> COMPLETE, PARTIAL <-> PARTIALLY_COMPLETE, FAILED <-> NOT_STARTED);
* a resource already tied to someone by evidence belongs to that person only;
* what is left is matched in processing order (account deletes and the policy actions that
  follow them run in the same order).
"""
from __future__ import annotations

from datetime import datetime, timedelta

from .evidence import system_of

STATUS_RESULT = {"COMPLETE": "SUCCESS", "PARTIALLY_COMPLETE": "PARTIAL", "NOT_STARTED": "FAILED"}
POLICY_EVENTS = {"ANONYMIZE_RECORD", "REDACT_RECORD", "DISABLE_DATA_FLOW", "BLOCK_RESTORE", "DELETE_RECORD",
                 "RETAIN_RECORD"}
MODE = "strict"
BEFORE, AFTER = timedelta(hours=3), timedelta(minutes=30)


def _ts(s: str) -> datetime:
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ")


def case_num(cid: str) -> int:
    tail = cid.rsplit("_", 1)[-1]
    return int(tail) if tail.isdigit() else 0


def batch_links(requests: list[dict], subjects: dict, owners: dict, activity: list[dict]) -> dict[str, set]:
    """requests: all known request rows; subjects: case_id -> Subject|None;
    owners: rid -> set(user_id) from evidence.  Returns case_id -> set(rid)."""
    links: dict[str, set] = {}
    batches: dict[str, list[dict]] = {}
    for r in requests:
        if subjects.get(r["case_id"]) is not None:
            batches.setdefault(r["reported_at"], []).append(r)
    for reported_at, cases in batches.items():
        lo, hi = _ts(reported_at) - BEFORE, _ts(reported_at) + AFTER
        window = [a for a in activity if a["source_system"] == "deletion_worker" and lo <= _ts(a["event_time"]) <= hi]
        uid = {c["case_id"]: subjects[c["case_id"]].user_id for c in cases}
        by_user = {}
        for cid, u in uid.items():
            by_user.setdefault(u, []).append(cid)

        # ---- accounts
        accounts = sorted((a for a in window if a["event_type"] == "DELETE_RECORD"
                           and a["target_system"] == "account_service"), key=lambda a: a["event_time"])
        acct_of: dict[str, dict] = {}
        free_accounts = []
        for a in accounts:
            own = owners.get(a["resource_id"], set())
            mine = [cid for u in own for cid in by_user.get(u, [])]
            if mine:
                for cid in mine:
                    acct_of.setdefault(cid, a)
            elif not own:
                free_accounts.append(a)
        open_cases = sorted((c for c in cases if c["case_id"] not in acct_of), key=lambda c: case_num(c["case_id"]))
        for c in open_cases:
            want = STATUS_RESULT.get(c["reported_status"])
            pick = next((a for a in free_accounts if a["reported_result"] == want), None)
            if pick is not None:
                acct_of[c["case_id"]] = pick
                free_accounts.remove(pick)
        for cid, a in acct_of.items():
            links.setdefault(cid, set()).add(a["resource_id"])

        # ---- policy actions on other systems, in account-processing order
        order = sorted(uid, key=case_num)
        by_system: dict[str, list[dict]] = {}
        for a in window:
            if a["event_type"] in POLICY_EVENTS and a["target_system"] != "account_service":
                by_system.setdefault(a["target_system"], []).append(a)
        owned_systems = {}
        for rid, users in owners.items():
            sys_ = system_of(rid)
            for u in users:
                for cid in by_user.get(u, []):
                    owned_systems.setdefault(cid, set()).add(sys_)
        for system, acts in by_system.items():
            # cases whose own record of this system is already known from evidence don't take anonymous actions
            claimed = {cid for cid in uid if system in owned_systems.get(cid, set())}
            free = []
            for a in sorted(acts, key=lambda a: a["event_time"]):
                own = owners.get(a["resource_id"], set())
                mine = [cid for u in own for cid in by_user.get(u, [])]
                if mine:
                    for cid in mine:
                        links.setdefault(cid, set()).add(a["resource_id"])
                        claimed.add(cid)
                elif not own:
                    free.append(a)
            takers = [cid for cid in order if cid not in claimed]
            if MODE == "strict" and len(free) != len(takers):
                continue
            for a, cid in zip(free, takers):
                links.setdefault(cid, set()).add(a["resource_id"])
    return links
