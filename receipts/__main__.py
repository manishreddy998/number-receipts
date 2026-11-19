"""Command line: check an answer or a transcript, exit 1 if any number has no receipt (so it can gate CI).

  python -m receipts check transcript.json          # Anthropic / OpenAI / LangChain message list
  python -m receipts check case.json                # {"answer": "...", "tools": {...}}
  python -m receipts check runs.jsonl --json        # one case or transcript per line
"""
from __future__ import annotations

import argparse
import json
import sys

from .adapters import check_transcript
from .core import check


def _one(obj):
    if isinstance(obj, list):
        return check_transcript(obj)
    if "messages" in obj:
        return check_transcript(obj["messages"])
    return check(obj["answer"], obj.get("tools") or obj.get("tool_outputs") or [])


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="receipts")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check")
    c.add_argument("path")
    c.add_argument("--json", action="store_true")
    c.add_argument("--strict", action="store_true", help="also fail on weak (value-only) matches")
    args = ap.parse_args(argv)
    raw = sys.stdin.read() if args.path == "-" else open(args.path, encoding="utf-8").read()
    items = [json.loads(ln) for ln in raw.splitlines() if ln.strip()] if args.path.endswith(".jsonl") else [json.loads(raw)]
    failed = 0
    for i, obj in enumerate(items):
        report = _one(obj)
        ok = report.passed(strict=args.strict)
        failed += not ok
        if args.json:
            print(report.to_json())
        else:
            if len(items) > 1:
                print(f"--- {i + 1}")
            print(report.to_text())
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
