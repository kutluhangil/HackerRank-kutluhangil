"""Evidence ingestion: turn every supplied evidence file into normalized observations.

Each observation answers one question: "what did this file show about one resource
at one moment?"  Formats differ wildly (SQL replicas, JSON exports, five log
dialects, text handovers, PDFs, screenshots); the planner only ever sees `Obs`.
"""
from __future__ import annotations

import csv
import json
import re
import sqlite3
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional

# Resource-id prefix -> owning system.  Ordered longest prefix first.
PREFIX_SYSTEM = [
    ("email_delivery_", "email_delivery_service"),
    ("audit_record_", "security_service"),
    ("legal_hold_", "legal_service"),
    ("data_flow_", "integration_service"),
    ("tombstone_", "identity_service"),
    ("analytics_", "analytics_platform"),
    ("marketing_", "marketing_platform"),
    ("account_", "account_service"),
    ("support_", "support_platform"),
    ("search_", "search_service"),
    ("export_", "export_service"),
    ("backup_", "backup_service"),
    ("object_", "object_storage"),
    ("cache_", "cache_service"),
]

RID_RE = re.compile(r"\b(?:%s)\d+\b" % "|".join(p for p, _ in PREFIX_SYSTEM))
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PHONE_RE = re.compile(r"\+\d[\d ()-]{6,}\d")
HASH_RE = re.compile(r"\b[0-9a-f]{64}\b")
USER_RE = re.compile(r"\buser_\d+\b")

NULLS = {None, "", "null", "none", "None", "NULL", "no direct identifier"}


def system_of(rid: str) -> Optional[str]:
    for prefix, system in PREFIX_SYSTEM:
        if rid.startswith(prefix):
            return system
    return None


def norm_ident(value) -> Optional[str]:
    """Canonical form for identifier comparison (case/format-insensitive)."""
    if value in NULLS or value is None:
        return None
    s = str(value).strip()
    if not s or s in NULLS:
        return None
    if "@" in s:
        return "email:" + s.lower()
    if HASH_RE.fullmatch(s.lower()):
        return "hash:" + s.lower()
    if USER_RE.fullmatch(s):
        return "user:" + s
    if s.startswith("+") and sum(c.isdigit() for c in s) >= 7:
        return "phone:" + "".join(c for c in s if c.isdigit())
    return None


def idents_in_text(text: str) -> set[str]:
    out = set()
    for rx in (EMAIL_RE, PHONE_RE, HASH_RE, USER_RE):
        for m in rx.findall(text or ""):
            n = norm_ident(m)
            if n:
                out.add(n)
    return out


def text_has_direct_pii(text: str) -> bool:
    return bool(EMAIL_RE.search(text or "") or PHONE_RE.search(text or ""))


@dataclass
class Obs:
    eid: str                     # file_id or activity_id
    t: str                       # when the state was observed (ISO-8601 Z)
    system: str
    rid: str
    present: Optional[bool] = None
    pii: Optional[bool] = None   # direct identifiers still exposed?
    kind: str = ""               # sub-type hint: attachment, contact, message, tombstone...
    enabled: Optional[bool] = None
    restore_allowed: Optional[bool] = None
    retention_until: Optional[str] = None
    idents: set = field(default_factory=set)
    source: str = ""             # parser that produced it (debugging / reports)


@dataclass
class Scope:
    """A snapshot that lists every record of `system` at time `t`: omission => absent."""
    eid: str
    t: str
    system: str
    rids: set


@dataclass
class EvidenceFile:
    eid: str
    path: Path
    origin: str
    captured_at: str


class EvidenceStore:
    def __init__(self):
        self.obs: list[Obs] = []
        self.scopes: list[Scope] = []
        self.files: dict[str, EvidenceFile] = {}
        self.links: list[tuple[str, str, str, set]] = []   # (eid, t, rid, idents) catalogue links

    def add(self, o: Obs):
        if o.rid and o.system:
            self.obs.append(o)


# --------------------------------------------------------------------------- helpers
PII_FIELDS = ("email", "phone", "full_name", "name", "display_name", "email_hash",
              "requester_email", "requester_phone", "requester_name", "owner_email",
              "owner_phone", "customer_email")
REF_FIELDS = ("user_id", "customer_reference", "subject_reference", "subject_selector")


def _idents_of(rec: dict) -> set:
    out = set()
    for k, v in rec.items():
        if isinstance(v, (dict, list)):
            out |= idents_in_text(json.dumps(v))
        elif isinstance(v, str):
            n = norm_ident(v)
            if n:
                out.add(n)
            elif k in ("message_text", "message_excerpt", "document"):
                out |= idents_in_text(v)
    return out


def _has(rec: dict, *keys) -> bool:
    return any(rec.get(k) not in NULLS for k in keys)


def _bool(v) -> Optional[bool]:
    if isinstance(v, bool):
        return v
    if v is None:
        return None
    s = str(v).strip().lower()
    if s in ("true", "1", "yes", "y", "enabled", "allowed"):
        return True
    if s in ("false", "0", "no", "n", "disabled", "blocked"):
        return False
    return None


def obs_from_record(eid: str, t: str, rec: dict, system: Optional[str] = None,
                    collection: str = "", source: str = "") -> Optional[Obs]:
    """Build an observation from a structured record (row / JSON object)."""
    rec = dict(rec)
    if isinstance(rec.get("document"), dict):          # search documents nest their fields
        rec.update({k: v for k, v in rec["document"].items()})
    rid = rec.get("resource_id")
    if not rid:
        return None
    system = system_of(rid) or system
    if not system:
        return None
    o = Obs(eid=eid, t=t, system=system, rid=rid, present=True, idents=_idents_of(rec), source=source)
    col = (collection or "").lower()
    if system == "analytics_platform":
        o.pii = _has(rec, "email", "phone", "email_hash", "user_id", "customer_reference", "full_name", "name")
    elif system == "support_platform":
        text = str(rec.get("message_text") or rec.get("message_excerpt") or "")
        o.pii = _has(rec, "requester_email", "requester_phone", "requester_name") or text_has_direct_pii(text)
        if "attachment" in col or rec.get("file") or rec.get("attachment"):
            o.kind = "attachment"
        else:
            o.kind = "message"
    elif system == "identity_service":
        o.kind = "tombstone"
        o.pii = _has(rec, "name", "full_name", "email", "phone", "email_hash")
    elif system == "account_service":
        status = str(rec.get("account_status") or "").upper()
        if status == "DELETED":
            o.present = False
    elif system == "integration_service":
        o.enabled = _bool(rec.get("enabled"))
    elif system == "backup_service":
        o.restore_allowed = _bool(rec.get("restore_allowed"))
    elif system == "security_service":
        o.retention_until = rec.get("retention_until")
    elif system == "export_service":
        avail = rec.get("download_available", rec.get("available"))
        if _bool(avail) is False:
            o.present = False
    return o


# --------------------------------------------------------------------------- SQL
def ingest_sql(store: EvidenceStore, f: EvidenceFile):
    con = sqlite3.connect(":memory:")
    con.executescript(f.path.read_text())
    tables = [r[0] for r in con.execute("select name from sqlite_master where type='table'")]
    scope_systems = {}
    if "snapshot_scope" in tables:
        scope_systems = {s: t for s, t in con.execute("select origin_system, captured_at from snapshot_scope")}
    present_by_system: dict[str, set] = {}
    for table in tables:
        if table == "snapshot_scope":
            continue
        con.row_factory = sqlite3.Row
        rows = [dict(r) for r in con.execute(f'select * from "{table}"')]
        con.row_factory = None
        for row in rows:
            rec, collection, t = row, table, row.get("updated_at") or row.get("indexed_at") or f.captured_at
            if "record_json" in row:
                rec = json.loads(row["record_json"])
                collection = row.get("collection_name") or table
            if "customer_reference" in rec and "user_id" not in rec:
                rec["user_id"] = rec.get("customer_reference")
            o = obs_from_record(f.eid, t, rec, collection=collection, source=f"sql:{table}")
            if o:
                if "source_resource_id" in rec and rec["source_resource_id"]:
                    o.idents.add("rid:" + rec["source_resource_id"])
                store.add(o)
                present_by_system.setdefault(o.system, set()).add(o.rid)
        # account snapshot tables (primary / replica) list every live profile
        if table.startswith("customer_profiles_"):
            present_by_system.setdefault("account_service", set())
    for system, t in scope_systems.items():
        store.scopes.append(Scope(f.eid, t, system, present_by_system.get(system, set())))
    if not scope_systems and "account_service" in present_by_system and any(
            t.startswith("customer_profiles_") for t in tables):
        store.scopes.append(Scope(f.eid, f.captured_at, "account_service", present_by_system["account_service"]))


# --------------------------------------------------------------------------- JSON
def ingest_json(store: EvidenceStore, f: EvidenceFile):
    data = json.loads(f.path.read_text())
    if "service_exports" in data:
        for service, groups in data["service_exports"].items():
            for group, items in groups.items():
                for it in items:
                    t = it.get("observed_at") or f.captured_at
                    rid = it.get("resource_id")
                    if service == "account_service":
                        prof = it.get("profile")
                        o = Obs(f.eid, t, "account_service", rid, present=it.get("status_code") == 200 or bool(prof),
                                idents=_idents_of(prof or {}), source="json:service_export")
                        store.add(o)
                    elif service == "search_service":
                        hits = it.get("hits")
                        present = (hits or 0) > 0 if isinstance(hits, int) else bool(hits)
                        o = Obs(f.eid, t, "search_service", rid, present=present,
                                idents=_idents_of({"q": it.get("query")}) | idents_in_text(json.dumps(hits)),
                                source="json:service_export")
                        store.add(o)
                    else:
                        o = obs_from_record(f.eid, t, it, system=service, collection=group, source="json:service_export")
                        if o:
                            store.add(o)
        return
    if "snapshots" in data:
        for snap in data["snapshots"]:
            t, ds = snap.get("captured_at") or f.captured_at, snap.get("data_store")
            rids = set()
            for rec in snap.get("records", []):
                o = obs_from_record(f.eid, t, rec, system=ds, collection=snap.get("collection", ""), source="json:snapshot")
                if o:
                    store.add(o)
                    rids.add(o.rid)
            if ds:
                store.scopes.append(Scope(f.eid, t, ds, rids))
        return
    records = data.get("records", [])
    if records and "record_type" in records[0]:
        for r in records:
            add_record_lookup(store, f.eid, r.get("recorded_at") or f.captured_at, r["system"], r["resource_id"],
                              r["record_type"], r["result"], r.get("subject_reference", ""), "json:lookup_table")
        return
    t = data.get("captured_at") or f.captured_at
    for rec in records:
        o = obs_from_record(f.eid, t, rec, collection=data.get("collection", ""), source="json:collection")
        if o:
            store.add(o)


def add_record_lookup(store, eid, t, system, rid, record_type, result, subject, source):
    """Rows of the form system | resource | RECORD_TYPE | RESULT | subject."""
    result, record_type = result.upper(), record_type.upper()
    o = Obs(eid, t, system_of(rid) or system, rid, source=source)
    n = norm_ident(subject)
    if n:
        o.idents.add(n)
    if result in ("FOUND", "IDENTIFIABLE", "ACTIVE", "PRESENT", "REDACTED", "ANONYMIZED", "BLOCKED", "DISABLED"):
        o.present = True
    elif result in ("NOT_FOUND", "ABSENT", "DELETED"):
        o.present = False
    if result == "IDENTIFIABLE":
        o.pii = True
    elif result in ("REDACTED", "ANONYMIZED"):
        o.pii = False
    if record_type == "DATA_FLOW":
        o.enabled = result == "ACTIVE" if result in ("ACTIVE", "DISABLED") else None
    if record_type == "BACKUP_ARCHIVE":
        o.restore_allowed = result == "ACTIVE" if result in ("ACTIVE", "BLOCKED") else None
    if record_type == "SUPPORT_ATTACHMENT":
        o.kind = "attachment"
    elif record_type == "SUPPORT_MESSAGE":
        o.kind = "message"
    elif record_type == "ACCOUNT_TOMBSTONE":
        o.kind = "tombstone"
    store.add(o)


LOOKUP_LINE = re.compile(r"^- (\S+) \| (\S+) \| (\S+) \| (\S+) \| (\S+) \| (.*)$")


def ingest_text(store: EvidenceStore, f: EvidenceFile):
    for line in f.path.read_text().splitlines():
        m = LOOKUP_LINE.match(line.strip())
        if m:
            add_record_lookup(store, f.eid, m[1], m[2], m[3], m[4], m[5], m[6].strip(), "text:handover")


# --------------------------------------------------------------------------- logs
KV_RE = re.compile(r'(\w+)=("(?:[^"\\]|\\.)*"|\S+)')
TS_RE = re.compile(r"^(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ)\s+(.*)$")


def _kv(s: str) -> dict:
    out = {}
    for k, v in KV_RE.findall(s):
        if v.startswith('"') and v.endswith('"'):
            v = v[1:-1].replace('\\"', '"')
        out[k] = v
    return out


def parse_log_line(line: str) -> Optional[tuple[str, dict]]:
    m = TS_RE.match(line.strip())
    if not m:
        return None
    ts, rest = m.groups()
    d: dict = {}
    if rest.startswith("{"):
        try:
            d = json.loads(rest)
        except json.JSONDecodeError:
            return None
    elif rest.startswith("["):                               # [LEVEL] [service] [trace] event: kv
        parts = re.match(r"\[(\w+)\] \[([^\]]+)\] \[([^\]]+)\] (\w+): ?(.*)", rest)
        if not parts:
            return None
        d = _kv(parts[5])
        d.update(level=parts[1], service=parts[2], trace_id=parts[3], event=parts[4])
    elif rest.startswith("|"):
        cols = [c.strip() for c in rest.strip("| ").split("|")]
        if len(cols) < 5:
            return None
        d = _kv(" ".join(cols[4:]))
        d.update(level=cols[0], service=cols[1], trace_id=cols[2], event=cols[3])
    elif rest.startswith("<"):                               # syslog: <pri>1 host app trace - - kv
        toks = rest.split(" ", 6)
        d = _kv(toks[6] if len(toks) > 6 else "")
        d.update(service=toks[2], trace_id=toks[3])
    else:
        d = _kv(rest)
        if "message" in d and "=" in d["message"]:          # cloud runtime: message="k=\"v\" ..."
            inner = _kv(d.pop("message"))
            d.update(inner)
            d.setdefault("trace_id", d.get("requestId"))
            d.setdefault("service", d.get("function"))
    if "trace_id" not in d and "requestId" in d:
        d["trace_id"] = d["requestId"]
    return ts, d


KEY_FIELDS = ("lookup_key", "match_key", "scan_key", "subject_key", "correlation_key", "matched_value",
              "subject_reference", "customer_reference", "customer_email", "owner_email", "requester_email",
              "requester_phone", "email", "phone", "email_hash", "user_id")


def ingest_log(store: EvidenceStore, f: EvidenceFile):
    traces: dict[str, list[tuple[str, dict]]] = {}
    for line in f.path.read_text().splitlines():
        p = parse_log_line(line)
        if not p:
            continue
        ts, d = p
        if d.get("event") == "record_lookup" and d.get("resource_id"):
            add_record_lookup(store, f.eid, ts, d.get("system", ""), d["resource_id"], d.get("record_type", ""),
                              d.get("result", ""), d.get("subject_reference", ""), "log:record_lookup")
            continue
        key = d.get("trace_id") or f"{ts}:{d.get('resource_id')}"
        traces.setdefault(key, []).append((ts, d))
    for events in traces.values():
        idents = set()
        for _, d in events:
            for k, v in d.items():
                if k in ("trace_id", "requestId", "resource_id", "event", "service"):
                    continue
                n = norm_ident(v)
                if n:
                    idents.add(n)
        for ts, d in events:
            o = log_event_obs(f.eid, ts, d)
            if o:
                o.idents |= idents
                store.add(o)


def _int(v, default=None):
    try:
        return int(str(v))
    except (TypeError, ValueError):
        return default


def log_event_obs(eid: str, ts: str, d: dict) -> Optional[Obs]:
    ev, rid = d.get("event", ""), d.get("resource_id")
    if not rid or not system_of(rid):
        return None
    o = Obs(eid, ts, system_of(rid), rid, source=f"log:{ev}")
    if ev in ("profile_lookup_completed", "contact_query_completed", "audit_record_read_completed",
              "contact_lookup_completed"):
        rows, status = _int(d.get("rows")), _int(d.get("http_status"))
        o.present = (rows or 0) > 0 if rows is not None else status == 200
        if ev == "contact_query_completed" or ev == "contact_lookup_completed":
            o.kind = "contact"
        o.retention_until = d.get("retention_until")
    elif ev == "index_query_completed":
        hits = _int(d.get("total_hits"))
        o.present = d.get("result", "").lower() == "hit" or (hits or 0) > 0
    elif ev in ("analytics_profile_read_completed", "analytics_profile_read"):
        o.present = True
        di = _int(d.get("direct_identifiers"))
        o.pii = di > 0 if di is not None else _has(d, "email", "phone", "email_hash", "customer_reference", "user_id")
    elif ev == "analytics_identity_scan":
        o.present, o.pii = True, True
    elif ev == "support_ticket_read_completed":
        o.present, o.kind = True, "message"
        o.pii = _has(d, "requester_email", "requester_phone", "requester_name")
    elif ev == "message_pii_scan":
        o.present, o.pii, o.kind = True, True, "message"
    elif ev == "attachment_pii_scan":
        o.present, o.pii, o.kind = True, True, "attachment"
    elif ev == "deletion_marker_check":
        if _bool(d.get("marker_found")) is False:
            o.present, o.kind = True, "contact"
        elif _bool(d.get("marker_found")):
            o.present = False
    elif ev in ("connector_config_read_completed", "connector_heartbeat"):
        o.present, o.enabled = True, _bool(d.get("enabled"))
    elif ev == "restore_policy_read_completed":
        o.present = _bool(d.get("archive_present")) is not False
        o.restore_allowed = _bool(d.get("restore_allowed"))
    elif ev == "restore_candidate_evaluated":
        o.present = True
        o.restore_allowed = _bool(d.get("eligible")) is True and _bool(d.get("deletion_block")) is not True
    elif ev in ("export_metadata_read_completed", "export_download_check_completed"):
        o.present = _bool(d.get("available")) is not False
    else:
        return None
    return o


# --------------------------------------------------------------------------- activity
def ingest_activity(store: EvidenceStore, rows: Iterable[dict]):
    """Only verifiable checks/observations become observations; workflow results stay claims."""
    for r in rows:
        et, rid, det = r["event_type"], r["resource_id"], r["details"]
        if et == "LINK_RESOURCE_IDENTITY":
            store.links.append((r["activity_id"], r["event_time"], rid, idents_in_text(det)))
        elif et == "CHECK_DATA_FLOW" and "remains enabled" in det:
            store.add(Obs(r["activity_id"], r["event_time"], "integration_service", rid, present=True, enabled=True,
                          source="activity:check"))
        elif et == "CHECK_RESTORE_ACCESS" and "can still be restored" in det:
            store.add(Obs(r["activity_id"], r["event_time"], "backup_service", rid, present=True,
                          restore_allowed=True, source="activity:check"))
        elif "repopulated downstream resource" in det:
            m = RID_RE.search(det.split("resource", 1)[1])
            if m:
                o = Obs(r["activity_id"], r["event_time"], system_of(m[0]), m[0], present=True,
                        source="activity:repopulated")
                o.idents.add("rid:" + rid)        # created by this flow / restore
                store.add(o)


# --------------------------------------------------------------------------- PDFs
def pdf_text(path: Path) -> str:
    try:
        return subprocess.run(["pdftotext", "-layout", str(path), "-"], capture_output=True, text=True,
                              timeout=60).stdout
    except (OSError, subprocess.SubprocessError):
        return ""


# --------------------------------------------------------------------------- driver
def load_manifest(dataset: Path) -> list[EvidenceFile]:
    out = []
    with open(dataset / "evidence_files.csv", newline="") as fh:
        for r in csv.DictReader(fh):
            out.append(EvidenceFile(r["file_id"], dataset / r["file_path"], r["origin"], r["captured_at"]))
    return out


def build_store(dataset: Path, activity_rows: list[dict], media_extractor=None) -> EvidenceStore:
    store = EvidenceStore()
    for f in load_manifest(dataset):
        store.files[f.eid] = f
        if not f.path.exists():
            continue
        suffix = f.path.suffix.lower()
        if suffix == ".sql":
            ingest_sql(store, f)
        elif suffix == ".json":
            ingest_json(store, f)
        elif suffix == ".log":
            ingest_log(store, f)
        elif suffix == ".txt":
            ingest_text(store, f)
        elif suffix in (".png", ".jpg", ".jpeg", ".pdf") and media_extractor is not None:
            for o in media_extractor(f):
                store.add(o)
    ingest_activity(store, activity_rows)
    return store
