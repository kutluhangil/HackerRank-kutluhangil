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
    r"\binvoices?\b", r"\baccess (to )?my (data|information)\b", r"\bwhat (data|information) you hold\b",
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
