#!/usr/bin/env python3
"""Record the user's approval of a topic in runs/<run>/approval.json (topic_approval "human").

Usage, in your own terminal (in a session the user types /approve-topic and tools/hooks/record_approval.py calls
record(); Claude may not run this file):
  python3 tools/human/approve_topic.py runs/<run> <topic-id> [--note "..."]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _common import ranking_inputs, read_json, rel, resolve_run, sha256_file, utc_now, write_json  # noqa: E402


class ApprovalError(Exception):
    pass


def record(run_arg: str, topic_id: str, via: str, note: str = "", session_id: str | None = None) -> dict:
    try:
        run = resolve_run(run_arg)
    except SystemExit:
        raise ApprovalError(f"run directory not found: {run_arg}")
    ranking_md, ranking_json = run / "ranking.md", run / "ranking.json"
    if not ranking_md.exists() or not ranking_json.exists():
        raise ApprovalError(f"{rel(run)} has no ranking yet: run tools/rank_topics.py first")
    rk = read_json(ranking_json)
    try:
        current = ranking_inputs(run)
    except FileNotFoundError:
        current = None
    if current != rk.get("inputs_sha256"):
        raise ApprovalError("ranking.md is stale (sources.json, scores.json, search.json or the rubric changed): "
                            "rerun tools/rank_topics.py and approve again")
    topic = next((t for t in rk["ranking"] if t["id"] == topic_id), None)
    if topic is None:
        ids = ", ".join(t["id"] for t in rk["ranking"])
        raise ApprovalError(f"unknown topic id {topic_id!r}; ranking.md lists {ids}")
    path = run / "approval.json"
    history = []
    if path.exists():
        try:
            old = read_json(path)
            history = old.pop("history", []) + [old]
        except ValueError:
            history = []
    data = {
        "schema_version": 1,
        "topic_id": topic_id,
        "title": topic["title"],
        "slug": topic["slug"],
        "rank": topic["rank"],
        "total": topic["total"],
        "gate_status": "eligible" if topic["eligible"] else "excluded: " + "; ".join(topic["gate_reasons"]),
        "approved_at": utc_now(),
        "via": via,
        "note": note,
        "ranking_sha256": sha256_file(ranking_md),
        "session_id": session_id or "",
        "history": history,
    }
    write_json(path, data)
    return data


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run")
    ap.add_argument("topic_id")
    ap.add_argument("--note", default="")
    a = ap.parse_args()
    try:
        d = record(a.run, a.topic_id, via="tools/human/approve_topic.py (run by the user)", note=a.note)
    except ApprovalError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"approved {d['topic_id']} ({d['title']}); {d['gate_status']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
