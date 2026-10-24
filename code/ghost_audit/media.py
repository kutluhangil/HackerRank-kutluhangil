"""Multimodal evidence: screenshots and PDFs -> observations, via Claude (vision / document text)."""
from __future__ import annotations

import base64
import re

from .evidence import (EMAIL_RE, PHONE_RE, RID_RE, EvidenceFile, Obs, idents_in_text, norm_ident, pdf_text,
                       system_of)
from .llm import LLM, parse_json
from .prompts import MEDIA_SYSTEM

KIND = {"SUPPORT_ATTACHMENT": "attachment", "SUPPORT_MESSAGE": "message", "ACCOUNT_TOMBSTONE": "tombstone",
        "SECONDARY_IDENTIFIER": "contact"}
ISO = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d(:\d\d)?Z$")


def media_extractor(llm: LLM):
    def extract(f: EvidenceFile, aliases: dict) -> list[Obs]:
        suffix = f.path.suffix.lower()
        text = pdf_text(f.path) if suffix == ".pdf" else ""
        hint = ("Data-catalogue labels (label -> resource_id); when the artifact shows one of these labels, "
                "report the record under that resource_id:\n" +
                "\n".join(f"- {label} -> {rid}" for label, rid in sorted(aliases.items())))
        if suffix == ".pdf":
            content = [{"type": "text", "text": f"Artifact {f.path.name} (captured {f.captured_at}), "
                                                f"extracted text:\n\n{text}\n\n{hint}"}]
        else:
            data = base64.standard_b64encode(f.path.read_bytes()).decode()
            content = [{"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": data}},
                       {"type": "text", "text": f"Artifact {f.path.name} (captured {f.captured_at}).\n\n{hint}"}]
        answer = llm.ask(f"media:{f.eid}", MEDIA_SYSTEM, content, effort="medium")
        parsed = parse_json(answer)
        if isinstance(parsed, dict) and isinstance(parsed.get("records"), list):
            out = [o for o in (_to_obs(f, r, aliases) for r in parsed["records"]) if o]
            llm.extractions[f.eid] = [vars(o) | {"idents": sorted(o.idents)} for o in out]
            return out
        if answer is not None:                      # live answer that is not usable JSON
            llm.failures.append(f"media:{f.eid}: unparseable answer")
        return _fallback(f, text)
    return extract


def _to_obs(f: EvidenceFile, r: dict, aliases: dict):
    rid = r.get("resource_id")
    if rid in aliases:
        rid = aliases[rid]
    if not rid or not RID_RE.fullmatch(str(rid)):
        return None
    system = system_of(rid)
    t = r.get("observed_at") if isinstance(r.get("observed_at"), str) and ISO.match(r["observed_at"]) else None
    t = t if t and t <= f.captured_at else f.captured_at
    o = Obs(f.eid, t, system, rid, present=bool(r.get("exists", True)), source="media:llm")
    o.pii = bool(r.get("direct_identifiers_visible"))
    o.kind = KIND.get(str(r.get("record_type", "")).upper(), "")
    o.enabled = r.get("enabled") if isinstance(r.get("enabled"), bool) else None
    o.restore_allowed = r.get("restore_allowed") if isinstance(r.get("restore_allowed"), bool) else None
    o.retention_until = r.get("retention_until") if isinstance(r.get("retention_until"), str) else None
    for i in r.get("identifiers") or []:
        n = norm_ident(i)
        if n:
            o.idents.add(n)
    return o


def _fallback(f: EvidenceFile, text: str) -> list[Obs]:
    """Offline path (no API key): PDFs only - every resource id mentioned is treated as present."""
    if not text:
        return []
    idents = idents_in_text(text)
    pii = bool(EMAIL_RE.search(text) or PHONE_RE.search(text))
    out = []
    for rid in sorted(set(RID_RE.findall(text))):
        o = Obs(f.eid, f.captured_at, system_of(rid), rid, present=True, pii=pii, idents=set(idents),
                source="media:fallback")
        if system_of(rid) == "support_platform" and re.search(r"\.pdf|attachment", text, re.I):
            o.kind = "attachment"
        out.append(o)
    return out
