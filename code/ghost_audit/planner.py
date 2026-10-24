"""Per-case reasoning: which resources belong to the subject, what state they were in at
`audit_at`, what the policy requires, and the ordered findings/remediation/verification plan."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from .evidence import EvidenceStore, Obs, system_of
from .identity import Subject

FINDING_ORDER = ["REPORT_REMAINING_RECORD", "REPORT_EXPOSED_PII", "REPORT_ACTIVE_DATA_FLOW", "REPORT_RESTORE_RISK"]
REMEDIATION_ORDER = ["DISABLE_DATA_FLOW", "BLOCK_RESTORE", "DELETE_RECORD", "REDACT_RECORD", "ANONYMIZE_RECORD"]
VERIFICATION_ORDER = ["VERIFY_RECORD_ABSENT", "VERIFY_RECORD_PRESENT", "VERIFY_RECORD_REDACTED",
                      "VERIFY_RECORD_ANONYMIZED", "VERIFY_DATA_FLOW_DISABLED", "VERIFY_RESTORE_BLOCKED"]
STATE = {
    "REPORT_REMAINING_RECORD": "PRESENT", "REPORT_EXPOSED_PII": "PRESENT", "REPORT_ACTIVE_DATA_FLOW": "ACTIVE",
    "REPORT_RESTORE_RISK": "ACTIVE", "DISABLE_DATA_FLOW": "DISABLED", "BLOCK_RESTORE": "BLOCKED",
    "DELETE_RECORD": "ABSENT", "REDACT_RECORD": "REDACTED", "ANONYMIZE_RECORD": "ANONYMIZED",
    "VERIFY_RECORD_ABSENT": "ABSENT", "VERIFY_RECORD_PRESENT": "PRESENT", "VERIFY_RECORD_REDACTED": "REDACTED",
    "VERIFY_RECORD_ANONYMIZED": "ANONYMIZED", "VERIFY_DATA_FLOW_DISABLED": "DISABLED",
    "VERIFY_RESTORE_BLOCKED": "BLOCKED",
}


RETAINED_SYSTEMS = {"security_service", "legal_service"}
# Snapshots are complete listings only for the account tables; other collections are samples.
OMISSION_SYSTEMS = {"account_service"}


@dataclass
class ResourceView:
    rid: str
    system: str
    category: str          # deletion_rules data_category
    action: str            # DELETE / REDACT / ANONYMIZE / RETAIN / DISABLE / BLOCK
    latest: Optional[Obs]  # state-defining observation at audit_at


def category_of(system: str, obs: list[Obs]) -> tuple[str, str]:
    kinds = {o.kind for o in obs if o.kind}
    if system == "account_service":
        return "USER_PROFILE", "DELETE"
    if system == "search_service":
        return "SEARCH_INDEX_ENTRY", "DELETE"
    if system == "cache_service":
        return "CACHE_ENTRY", "DELETE"
    if system == "export_service":
        return "USER_EXPORT", "DELETE"
    if system == "marketing_platform":
        return "MARKETING_PROFILE", "DELETE"
    if system == "object_storage":
        return "SUPPORT_ATTACHMENT", "DELETE"
    if system == "analytics_platform":
        if "contact" in kinds:
            return "SECONDARY_IDENTIFIER", "DELETE"
        return "ANALYTICS_PROFILE", "ANONYMIZE"
    if system == "support_platform":
        if "attachment" in kinds or "contact" in kinds:
            return "SUPPORT_ATTACHMENT", "DELETE"
        return "SUPPORT_MESSAGE", "REDACT"
    if system == "email_delivery_service":
        return "EMAIL_DELIVERY_LOG", "REDACT"
    if system == "security_service":
        return "SECURITY_AUDIT_LOG", "RETAIN"
    if system == "legal_service":
        return "LEGAL_HOLD_RECORD", "RETAIN"
    if system == "identity_service":
        return "ACCOUNT_TOMBSTONE", "REDACT"
    if system == "integration_service":
        return "DATA_FLOW", "DISABLE"
    if system == "backup_service":
        return "BACKUP_ARCHIVE", "BLOCK"
    return "UNKNOWN", "DELETE"


class Planner:
    def __init__(self, store: EvidenceStore, activity_rows: list[dict]):
        self.store = store
        self.by_rid: dict[str, list[Obs]] = {}
        for o in store.obs:
            self.by_rid.setdefault(o.rid, []).append(o)
        self.activity = activity_rows
        self.activity_rids = {r["resource_id"] for r in activity_rows}

    # -- availability: nothing captured after the audit cut-off may be used
    def available(self, o: Obs, audit_at: str) -> bool:
        if o.t > audit_at:
            return False
        f = self.store.files.get(o.eid)
        return f is None or f.captured_at <= audit_at

    def owners(self, cutoff: str, identities) -> dict[str, set]:
        """rid -> user_ids whose identifiers appear in evidence about it (available at cutoff)."""
        out: dict[str, set] = {}
        for o in self.store.obs:
            if self.available(o, cutoff):
                for i in o.idents:
                    for u in identities.by_ident.get(i, ()):
                        out.setdefault(o.rid, set()).add(u)
        for eid, t, rid, idents in self.store.links:
            if t <= cutoff:
                for i in idents:
                    for u in identities.by_ident.get(i, ()):
                        out.setdefault(rid, set()).add(u)
        return out

    def related_resources(self, subj: Subject, audit_at: str, extra: set = frozenset()) -> set[str]:
        rids = set(extra)
        for o in self.store.obs:
            if o.idents & subj.idents and (self.available(o, audit_at) or (
                    o.t <= audit_at and o.system in RETAINED_SYSTEMS)):
                rids.add(o.rid)
        for eid, t, rid, idents in self.store.links:
            if t <= audit_at and idents & subj.idents:
                rids.add(rid)
        # records recreated by a flow/restore that belongs to the subject
        changed = True
        while changed:
            changed = False
            for o in self.store.obs:
                if o.rid not in rids and self.available(o, audit_at) and any(
                        i.startswith("rid:") and i[4:] in rids for i in o.idents):
                    rids.add(o.rid)
                    changed = True
        if not any(system_of(r) == "account_service" for r in rids):
            m = re.match(r"user_(\d+)$", subj.user_id)
            guess = f"account_{int(m[1]):03d}" if m else None
            if guess and int(m[1]) < 100:
                rids.add(guess)
        return rids

    def state_at(self, rid: str, audit_at: str) -> Optional[Obs]:
        system = system_of(rid)
        cands = [o for o in self.by_rid.get(rid, []) if self.available(o, audit_at)]
        for sc in self.store.scopes:
            if sc.system == system and system in OMISSION_SYSTEMS and rid not in sc.rids and sc.t <= audit_at and \
                    self.store.files[sc.eid].captured_at <= audit_at:
                cands.append(Obs(sc.eid, sc.t, system, rid, present=False, source="scope:omission"))
        if not cands:
            return None
        # explicit observations beat inference from omission; then the latest one wins
        explicit = [o for o in cands if o.source != "scope:omission"]
        pool = explicit or cands
        pool.sort(key=lambda o: (o.t, o.eid.startswith("evidence")))
        return pool[-1]

    def plan(self, subj: Subject, audit_at: str, extra: set = frozenset()) -> tuple[str, list[dict]]:
        findings, remediation, verification = [], [], []
        for rid in sorted(self.related_resources(subj, audit_at, extra)):
            system = system_of(rid)
            hist = [o for o in self.by_rid.get(rid, []) if self.available(o, audit_at)]
            category, action = category_of(system, hist)
            st = self.state_at(rid, audit_at)
            if st is None and action == "RETAIN":
                # retained records may be known only from a later export of an earlier snapshot:
                # enough to plan a future check, never enough to cite as proof
                later = [o for o in self.by_rid.get(rid, []) if o.t <= audit_at]
                st = max(later, key=lambda o: o.t, default=None)
                if st is not None:
                    st = Obs("", st.t, st.system, rid, present=st.present, retention_until=st.retention_until)
            if st is None:
                continue
            ev = st.eid
            if action == "DELETE":
                if st.present:
                    findings.append(("REPORT_REMAINING_RECORD", system, rid, ev))
                    remediation.append(("DELETE_RECORD", system, rid))
                verification.append(("VERIFY_RECORD_ABSENT", system, rid, ev))
            elif action in ("REDACT", "ANONYMIZE"):
                if st.present is False:
                    continue
                pii = st.pii
                if pii is None:   # state unknown in this observation: fall back to latest one that says
                    known = [o for o in hist if o.pii is not None and o.t <= st.t]
                    pii = known[-1].pii if known else False
                verb = "REDACT" if action == "REDACT" else "ANONYMIZE"
                if pii:
                    findings.append(("REPORT_EXPOSED_PII", system, rid, ev))
                    remediation.append((f"{verb}_RECORD", system, rid))
                verification.append((f"VERIFY_RECORD_{verb}D" if verb.endswith("E") else f"VERIFY_RECORD_{verb}ED", system, rid, ev))
            elif action == "RETAIN":
                if st.present is False:
                    continue
                if st.retention_until and st.retention_until < audit_at:
                    continue
                verification.append(("VERIFY_RECORD_PRESENT", system, rid, ev))
            elif action == "DISABLE":
                if st.enabled:
                    findings.append(("REPORT_ACTIVE_DATA_FLOW", system, rid, ev))
                    remediation.append(("DISABLE_DATA_FLOW", system, rid))
                verification.append(("VERIFY_DATA_FLOW_DISABLED", system, rid, ev))
            elif action == "BLOCK":
                if st.restore_allowed:
                    findings.append(("REPORT_RESTORE_RISK", system, rid, ev))
                    remediation.append(("BLOCK_RESTORE", system, rid))
                verification.append(("VERIFY_RESTORE_BLOCKED", system, rid, ev))
        status = "INCOMPLETE" if findings else "COMPLETE"
        steps = []
        for op, system, rid, ev in sorted(findings, key=lambda x: (FINDING_ORDER.index(x[0]), x[1], x[2])):
            steps.append(_step("FINDING", system, rid, op, ev))
        for op, system, rid in sorted(remediation, key=lambda x: (REMEDIATION_ORDER.index(x[0]), x[1], x[2])):
            steps.append(_step("REMEDIATION", system, rid, op, ""))
        for op, system, rid, ev in sorted(verification, key=lambda x: (VERIFICATION_ORDER.index(x[0]), x[1], x[2])):
            steps.append(_step("VERIFICATION", system, rid, op, ev if status == "COMPLETE" else ""))
        for i, s in enumerate(steps, 1):
            s["step_no"] = i
        return status, steps


def _step(phase, system, rid, op, ev):
    return {"step_no": 0, "phase": phase, "system_id": system, "resource_id": rid,
            "operation": op, "state": STATE[op], "evidence_id": ev}
