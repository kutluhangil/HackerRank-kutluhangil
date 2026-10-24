"""Identity resolution: current snapshot + historical audit log -> every identifier of a subject."""
from __future__ import annotations

import csv
import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .evidence import norm_ident


@dataclass
class Subject:
    user_id: str
    name: str
    idents: set = field(default_factory=set)      # normalized identifiers (email:, phone:, hash:, user:)
    history: list = field(default_factory=list)   # audit_ids that contributed historical identifiers


class IdentityIndex:
    def __init__(self, dataset: Path):
        self.users: dict[str, dict] = {}
        self.audit: dict[str, list[dict]] = {}
        with open(dataset / "user_identities.csv", newline="") as fh:
            for r in csv.DictReader(fh):
                self.users[r["user_id"]] = r
        with open(dataset / "user_audit_log.csv", newline="") as fh:
            for r in csv.DictReader(fh):
                self.audit.setdefault(r["user_id"], []).append(r)
        self.by_ident: dict[str, set] = {}
        for uid in self.users:
            for ident in self._all_idents(uid):
                self.by_ident.setdefault(ident, set()).add(uid)

    def _all_idents(self, uid: str, cutoff: Optional[str] = None) -> set:
        u = self.users[uid]
        out = {f"user:{uid}"}
        values = [u["email"], u["phone"], u["email_hash"]]
        for a in self.audit.get(uid, []):
            values.append(a["old_value"])
            if cutoff is None or a["event_time"] <= cutoff:
                values.append(a["new_value"])
        for v in values:
            n = norm_ident(v)
            if n:
                out.add(n)
                if n.startswith("email:"):
                    out.add("hash:" + hashlib.sha256(n[6:].encode()).hexdigest())
        return out

    def resolve(self, email: str, cutoff: Optional[str] = None) -> Optional[Subject]:
        key = norm_ident(email)
        uids = sorted(self.by_ident.get(key, set()))
        if not uids:
            return None
        if len(uids) > 1:            # an address reused by two people: prefer its current owner
            current = [u for u in uids if norm_ident(self.users[u]["email"]) == key]
            uids = current or uids
        uid = uids[0]
        s = Subject(uid, self.users[uid]["name"], self._all_idents(uid, cutoff))
        s.history = [a["audit_id"] for a in self.audit.get(uid, [])]
        return s
