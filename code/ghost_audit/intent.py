"""Does the request text authorize deletion?  LLM first (multilingual), rules as fallback."""
from __future__ import annotations

import re

# Non-deletion intents that explicitly keep the account (checked first: they win over "delete" words).
KEEP_PATTERNS = [
    r"\b(keep|leave) (the |my )?(account|profile)", r"continue using", r"leave (my|the) .* in place",
    r"\bkeep the account\b", r"\b(download|send|get|need|receive|want) (me )?(a )?(copy|export|download)\b", r"\bdownload (my|a|the)\b", r"\bportable format\b",
    r"\b(change|update|replace|correct) (the |my )?(email|e-mail|phone|mobile|number|address|name)",
    r"\b(unsubscribe|opt[- ]out|stop (sending|marketing)|marketing (emails|messages))",
    r"\b(do not|don't|dont) (delete|erase|remove|close)", r"\bnot (want|asking) .*delet",
    r"\binvoices?\b", r"without (removing|deleting|erasing)", r"marketing (lists?|emails?|messages?)",
    r"\bnot a request to\b", r"\binformation request\b", r"\bpromotional\b", r"\bresetting the login\b", r"\baccess (to )?my (data|information)\b", r"\bwhat (data|information) you hold\b",
]
DELETE_PATTERNS = [
    r"delet", r"eras", r"remov", r"\bclose (my|this|the) account", r"supprim", r"elimin", r"lösch", r"borr",
    r"apag", r"exclu", r"suppression", r"\bis gone\b", r"cannot identify me", r"no longer (exist|identif)", r"verwijder", r"usu[nń]", r"cancel+ (my|this) account", r"削除", r"삭제", r"删除", r"forget me",
]


def classify_rules(text: str) -> bool:
    t = (text or "").lower()
    if any(re.search(p, t) for p in KEEP_PATTERNS):
        return False
    return any(re.search(p, t) for p in DELETE_PATTERNS)


def classify_all(llm, rows: list[dict], batch_size: int = 25) -> dict[str, bool]:
    """case_id -> authorizes deletion.  Identical texts are asked once; rules cover any gap."""
    from .llm import parse_json
    from .prompts import INTENT_SYSTEM

    texts = sorted({r["request_text"] for r in rows})
    verdict: dict[str, bool] = {}
    for start in range(0, len(texts), batch_size):
        chunk = texts[start:start + batch_size]
        payload = "\n".join(f"[{i}] {t}" for i, t in enumerate(chunk))
        answer = parse_json(llm.ask("intent", INTENT_SYSTEM, [{"type": "text", "text": payload}], effort="low"))
        if isinstance(answer, list):
            for item in answer:
                try:
                    verdict[chunk[int(item["id"])]] = str(item["label"]).upper() == "DELETE"
                except (KeyError, ValueError, IndexError, TypeError):
                    continue
    return {r["case_id"]: verdict.get(r["request_text"], classify_rules(r["request_text"])) for r in rows}
