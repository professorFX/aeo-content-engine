"""CLI: python -m aeo_engine run | status | review list/approve/reject | publish"""
from __future__ import annotations

import argparse
import json
import sys

from .config import load_settings
from .pipeline import Run


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="aeo_engine")
    ap.add_argument("--root", default=".", help="project folder (config/, skills/, knowledge/)")
    ap.add_argument("--offline", action="store_true", help="use fixtures instead of the LLM API")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="plan, brief, draft, validate and queue a batch for review")
    r.add_argument("--resume", help="run id to resume")
    s = sub.add_parser("status")
    s.add_argument("run_id")
    rv = sub.add_parser("review")
    rv.add_argument("action", choices=["list", "approve", "reject"])
    rv.add_argument("run_id")
    rv.add_argument("item", nargs="?")
    rv.add_argument("--by", default="")
    rv.add_argument("--reason", default="")
    p = sub.add_parser("publish", help="send approved items to the CMS (dry-run unless publish.dry_run is false)")
    p.add_argument("run_id")
    a = ap.parse_args(argv)

    settings = load_settings(a.root)
    if a.offline:
        settings.raw["llm"]["provider"] = "fixtures"

    if a.cmd == "run":
        out = Run(settings, a.resume).run()
    elif a.cmd == "status":
        out = Run(settings, a.run_id).summary()
    elif a.cmd == "review":
        run = Run(settings, a.run_id)
        if a.action == "list":
            out = {k: {"status": v["status"], "flag": v.get("review", {}).get("flag"), "packet": v.get("review", {}).get("packet")}
                   for k, v in run.state["items"].items()}
        else:
            if not a.item:
                ap.error("item is required")
            run.decide(a.item, a.action == "approve", by=a.by, reason=a.reason)
            out = run.summary()
    else:
        out = Run(settings, a.run_id).publish_approved()
    json.dump(out, sys.stdout, indent=2)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
