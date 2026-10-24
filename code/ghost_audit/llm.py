"""Thin Claude client: disk cache, usage accounting, graceful offline fallback.

Credentials come from the environment only (ORCHESTRATE_ANTHROPIC_API_KEY, then
ANTHROPIC_API_KEY).  Without a key every call returns None and callers fall back to
their deterministic paths, so the pipeline always completes.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import threading
from pathlib import Path
from typing import Optional

API_URL = "https://api.anthropic.com"          # pinned: the environment may point SDKs elsewhere
DEFAULT_MODEL = os.environ.get("ORCHESTRATE_MODEL", "claude-opus-5-5")
PRICES = {  # USD per 1M tokens (input, output)
    "claude-opus-5-5": (4.00, 20.00),
    "claude-sonnet-5-5": (2.00, 10.00),
    "claude-haiku-5-5": (0.10, 0.50),
}


def _load_dotenv(root: Path):
    env = root / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


class LLM:
    def __init__(self, cache_path: Path, root: Optional[Path] = None, model: str = DEFAULT_MODEL):
        if root:
            _load_dotenv(root)
        self.model = model
        self.cache_path = cache_path
        self.cache: dict = json.loads(cache_path.read_text()) if cache_path.exists() else {}
        self.lock = threading.Lock()
        self.calls: list[dict] = []          # every request made in this run (live or cached)
        key = os.environ.get("ORCHESTRATE_ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")
        self.client = None
        if key:
            try:
                import anthropic
                self.client = anthropic.Anthropic(api_key=key, base_url=API_URL, max_retries=4, timeout=180.0)
            except ImportError:
                self.client = None

    @property
    def online(self) -> bool:
        return self.client is not None

    def ask(self, purpose: str, system: str, content: list, effort: str = "low",
            max_tokens: int = 8000) -> Optional[str]:
        """Return the text answer, from cache when the identical request was made before."""
        key = hashlib.sha256(json.dumps([self.model, system, content, effort], sort_keys=True).encode()).hexdigest()
        with self.lock:
            hit = self.cache.get(key)
        if hit is not None:
            self.calls.append({"purpose": purpose, "model": hit.get("model", self.model), "cached": True,
                               "input_tokens": hit["input_tokens"], "output_tokens": hit["output_tokens"]})
            return hit["text"]
        if not self.online:
            return None
        import anthropic
        try:
            resp = self.client.messages.create(
                model=self.model, max_tokens=max_tokens, system=system,
                output_config={"effort": effort},
                messages=[{"role": "user", "content": content}],
            )
        except (anthropic.APIStatusError, anthropic.APIConnectionError) as e:
            print(f"[llm] {purpose}: request failed ({type(e).__name__}); using fallback")
            return None
        if resp.stop_reason == "refusal":
            return None
        text = "".join(b.text for b in resp.content if b.type == "text")
        rec = {"text": text, "model": resp.model, "input_tokens": resp.usage.input_tokens,
               "output_tokens": resp.usage.output_tokens}
        with self.lock:
            self.cache[key] = rec
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            self.cache_path.write_text(json.dumps(self.cache, indent=1, sort_keys=True))
        self.calls.append({"purpose": purpose, "model": resp.model, "cached": False,
                           "input_tokens": resp.usage.input_tokens, "output_tokens": resp.usage.output_tokens})
        return text


def parse_json(text: Optional[str]):
    """Extract the first JSON value from a model answer (tolerates prose or code fences)."""
    if not text:
        return None
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    candidate = fenced.group(1) if fenced else text
    for opener in ("[", "{"):
        i = candidate.find(opener)
        if i >= 0:
            try:
                return json.loads(candidate[i:candidate.rfind("]" if opener == "[" else "}") + 1])
            except json.JSONDecodeError:
                continue
    return None
