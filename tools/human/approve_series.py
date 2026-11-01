#!/usr/bin/env python3
"""Record the owner's approval of a series plan (the "plan_approval" field of series/<slug>/series.json).

With "series"."plan_approval": "required" in config/pipeline.json (the default) no episode of a series is made until
its plan is approved, once per series; tools/series.py start checks the record, and so does the gate. The approval
holds the plan's hash (tools/series.py plan_hash: the plan without the explainer's byte hash and timestamps), so any
later change to the story, the episodes, the prerequisites, recaps or teasers needs a new approval.

In your own terminal, not through Claude (it asks you to type the series slug, and refuses without a terminal), from
the repository folder, in zsh or bash (macOS or Linux):
    ./tools/human/approve_series.py series/<slug> [--note "..."]
    ./tools/human/approve_series.py series/<slug> --revoke
It needs Python 3.11 or newer: started with an older python3 (macOS's own is 3.9) it re-runs itself with the
project's .venv/bin/python, which ./setup.sh creates (with Homebrew's Python on a Mac). `.venv/bin/python
tools/human/approve_series.py series/<slug>` does the same. Read series/<slug>/PLAN.md and
`python3 tools/series.py list series/<slug>` first; commit series.json so the GitHub workflow sees the approval.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

if sys.version_info < (3, 11):                          # macOS's /usr/bin/python3: use the project's environment
    venv = Path(__file__).resolve().parent.parent.parent / ".venv" / "bin" / "python"
    if venv.exists() and Path(sys.executable).resolve() != venv.resolve():
        os.execv(str(venv), [str(venv), __file__, *sys.argv[1:]])
    sys.exit("error: this needs Python 3.11 or newer: run ./setup.sh once (it creates .venv), then run this command "
             "again")

import argparse  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _common import rel, utc_now, write_json  # noqa: E402
import series as S  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("series")
    ap.add_argument("--note", default="")
    ap.add_argument("--revoke", action="store_true")
    a = ap.parse_args()
    sp, data = S.load_any(a.series)
    if data.get("schema_version") != 2:
        print(f"error: {rel(sp)} is not a schema-2 series plan (made with /plan-series)", file=sys.stderr)
        return 1
    errs, warns = S.validate_v2(data)
    if errs:
        print("error: the plan does not validate:\n  " + "\n  ".join(errs), file=sys.stderr)
        return 1
    if not sys.stdin.isatty():
        print("error: run this yourself in a terminal: it asks you to type the series slug", file=sys.stderr)
        return 2
    if a.revoke:
        data.pop("plan_approval", None)
        write_json(sp, data)
        print(f"revoked: no new episode of {data['slug']} starts until you approve again")
        return 0
    print(f"{data['title']} ({data['slug']}): {len(data['episodes'])} episode(s), plan hash {S.plan_hash(data)[:12]}")
    for e in data["episodes"]:
        must = ", ".join(map(S.ref_key, (e.get("prerequisites") or {}).get("must", []))) or "nothing"
        print(f"  {e['number']}. {e['short_title']} ({e['kind']}, {e.get('length_min')} min), builds on {must}")
    for w in warns:
        print(f"  warning: {w}")
    typed = input(f"Type the slug ({data['slug']}) to approve this plan: ").strip()
    if typed != data["slug"]:
        print("not approved", file=sys.stderr)
        return 1
    data["plan_approval"] = {"status": "approved", "by": "owner", "date": utc_now()[:10],
                             "via": "tools/human/approve_series.py (typed by the owner)", "note": a.note,
                             "plan_sha256": S.plan_hash(data)}
    write_json(sp, data)
    print(f"approved: {rel(sp)} (commit it so the workflow sees the approval: git add {rel(sp)} && git commit -m "
          f"\"Approve the {data['slug']} plan\")")
    return 0


if __name__ == "__main__":
    sys.exit(main())
