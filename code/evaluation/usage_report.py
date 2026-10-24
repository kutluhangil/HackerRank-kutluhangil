"""Render evaluation/usage_report.md from the usage log written by the run that produced output.csv.

    python3 code/evaluation/usage_report.py [--usage output.usage.json]

Only measured numbers come from the log; the pre-run estimate section is labelled as such.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "code"))
from ghost_audit.llm import PRICES  # noqa: E402

ESTIMATE = """## Pre-run estimate (NOT measured)

Made before any live call, from input sizes; replace by the measured tables above after the live run.

| Workload | Calls | Est. input tokens | Est. output tokens (incl. thinking) |
|---|---|---|---|
| Request intent (375 distinct texts, 25 per call, effort `low`) | ~15 | ~27K | ~6K-36K |
| Screenshots (11 PNG, vision) + PDFs (4, extracted text), effort `medium` | 15 | ~44K | ~15K-45K |
| **Total** | **~30** | **~71K** | **~21K-81K** |

At Claude Opus 5.5 list prices ($4 / $20 per 1M input / output tokens) this is roughly **$0.70-$1.90 for the
whole dataset, i.e. about $0.001-$0.004 per request**. Responses are cached on disk
(`code/cache/llm_cache.json`), so re-running the pipeline repeats no paid calls.
"""


def render(usage: dict) -> str:
    calls = usage.get("calls", [])
    n_req = usage.get("requests", 0)
    live = [c for c in calls if not c["cached"]]
    by_model = defaultdict(lambda: {"calls": 0, "cached": 0, "in": 0, "out": 0})
    by_purpose = defaultdict(lambda: {"calls": 0, "in": 0, "out": 0})
    for c in calls:
        m = by_model[c["model"]]
        m["calls"] += 1
        m["cached"] += c["cached"]
        m["in"] += c["input_tokens"]
        m["out"] += c["output_tokens"]
        p = by_purpose["media" if c["purpose"].startswith("media") else c["purpose"]]
        p["calls"] += 1
        p["in"] += c["input_tokens"]
        p["out"] += c["output_tokens"]

    def cost(model, tin, tout):
        pin, pout = PRICES.get(model, PRICES.get(model.rsplit("-", 1)[0], (0, 0)))
        return tin / 1e6 * pin + tout / 1e6 * pout

    lines = ["# Usage report", "",
             f"Generated {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%MZ')} from `output.usage.json`, "
             f"the log of the run that produced `output.csv`.", "",
             "## Final full-dataset run (measured)", "",
             f"- Requests processed: **{n_req}**",
             f"- Configured model: `{usage.get('model')}` (provider: Anthropic)",
             f"- Live API calls allowed in this run: **{'yes (--live)' if usage.get('live') else 'no (offline/cache mode)'}**",
             f"- Model requests in this run: **{len(calls)}** ({len(live)} sent to the API, {len(calls) - len(live)} served from cache)",
             ""]
    if not calls:
        lines += ["No model calls were made in this run: request intent came from the rule-based fallback and "
                  "PDFs from `pdftotext`; screenshots were not read. Measured tokens and cost are therefore **0** "
                  "(0 input, 0 output, $0.00 total, $0.00 per request).", ""]
    else:
        tot_in = sum(c["input_tokens"] for c in calls)
        tot_out = sum(c["output_tokens"] for c in calls)
        lines += ["| Model | Calls | from cache | Input tokens | Output tokens | Total tokens | Est. cost (USD) |",
                  "|---|---|---|---|---|---|---|"]
        total_cost = 0.0
        for model, m in sorted(by_model.items()):
            c = cost(model, m["in"], m["out"])
            total_cost += c
            lines.append(f"| `{model}` | {m['calls']} | {m['cached']} | {m['in']:,} | {m['out']:,} | "
                         f"{m['in'] + m['out']:,} | ${c:.4f} |")
        lines.append(f"| **Overall** | **{len(calls)}** | **{len(calls) - len(live)}** | **{tot_in:,}** | "
                     f"**{tot_out:,}** | **{tot_in + tot_out:,}** | **${total_cost:.4f}** |")
        lines += ["", "| Purpose | Calls | Input tokens | Output tokens |", "|---|---|---|---|"]
        for purpose, p in sorted(by_purpose.items()):
            lines.append(f"| {purpose} | {p['calls']} | {p['in']:,} | {p['out']:,} |")
        lines += ["", f"- Average tokens per request: **{(tot_in + tot_out) / max(n_req, 1):,.1f}** "
                  f"({tot_in / max(n_req, 1):,.1f} input + {tot_out / max(n_req, 1):,.1f} output)",
                  f"- Estimated cost per request: **${total_cost / max(n_req, 1):.5f}**",
                  "- Cost uses Anthropic list prices per 1M tokens: " +
                  ", ".join(f"`{k}` ${v[0]:.2f} in / ${v[1]:.2f} out" for k, v in PRICES.items()) + ".",
                  "- Cached calls report the tokens of the original paid call; they cost nothing when replayed.", ""]
    extractions = usage.get("media_extractions") or {}
    if extractions:
        lines += ["## What the model read from screenshots and PDFs (for human review)", "",
                  "| File | Resource | Present | Direct identifiers | Enabled | Restore allowed | Identifiers |",
                  "|---|---|---|---|---|---|---|"]
        for eid, records in sorted(extractions.items()):
            for r in records:
                lines.append(f"| {eid} | {r['rid']} | {r['present']} | {r['pii']} | {r['enabled']} | "
                             f"{r['restore_allowed']} | {len(r['idents'])} |")
        lines.append("")
    lines += ["## Where the model is (and is not) used", "",
              "- Request intent: one call per 25 distinct request texts (multilingual DELETE vs NOT_DELETE).",
              "- Screenshots and PDFs: one call per artifact (15 files), producing structured observations.",
              "- Everything else (parsing 79 structured evidence files, identity resolution, state reconstruction, "
              "policy mapping, step ordering) is deterministic Python: 0 tokens.", "",
              ESTIMATE]
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--usage", default=str(ROOT / "output.usage.json"))
    ap.add_argument("--out", default=str(ROOT / "code" / "evaluation" / "usage_report.md"))
    args = ap.parse_args()
    usage = json.loads(Path(args.usage).read_text())
    Path(args.out).write_text(render(usage))
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
