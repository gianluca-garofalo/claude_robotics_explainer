#!/usr/bin/env python3
"""Automatic topic approval: the best eligible topic of ranking.json by a fixed rule, with its reasons logged.

Usage:
  python3 tools/auto_select.py runs/<run> [--published runs/<run>/published.json]   # selection.json, selection.md
  Exit 1 when no topic qualifies (config/pipeline.json auto_selection): nothing is written or uploaded.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import (CONFIG, load_json, ranking_inputs, read_json, rel, resolve_run, sha256_file, utc_now,  # noqa: E402
                     write_json)


def ledger_index(path: Path | None, statuses) -> tuple[dict[str, str], dict[str, str]]:
    """slug -> status and primary-source URL -> status for ledger entries whose status is in `statuses`."""
    slugs, urls = {}, {}
    if path and path.exists():
        for entry in read_json(path).get("runs", {}).values():
            st = entry.get("status")
            if st in statuses:
                if entry.get("slug"):
                    slugs[entry["slug"]] = st
                urls.update({u: st for u in entry.get("primary_urls", [])})
    return slugs, urls


def select(run: Path, published: Path | None) -> tuple[dict | None, list[dict]]:
    policy = load_json(CONFIG / "pipeline.json").get("auto_selection", {})
    rk = load_json(run / "ranking.json")
    if ranking_inputs(run) != rk.get("inputs_sha256"):
        raise SystemExit("error: ranking.json is stale; rerun tools/rank_topics.py first")
    sources = {c["id"]: c for c in load_json(run / "sources.json")["candidates"]}
    slugs, urls = ledger_index(published, set(policy.get("skip_ledger_statuses", ["published", "staged", "rejected"])))
    skipped, chosen = [], None
    for t in rk["ranking"]:
        prim = [s["url"] for s in sources[t["id"]]["sources"]
                if s.get("primary") and s.get("relation", "subject") == "subject"]
        reasons = []
        if policy.get("require_eligible", True) and not t["eligible"]:
            reasons.append("excluded by the rubric gates: " + "; ".join(t["gate_reasons"]))
        if t["total"] < policy.get("min_total", 0):
            reasons.append(f"total {t['total']} below the minimum {policy.get('min_total')}")
        if policy.get("skip_same_slug", True) and t["slug"] in slugs:
            reasons.append(f"already {slugs[t['slug']]} on the channel (same slug)")
        same = sorted(set(prim) & set(urls))
        if policy.get("skip_same_primary_url", True) and same:
            reasons.append(f"already {urls[same[0]]} on the channel (same primary source)")
        if reasons:
            skipped.append({"id": t["id"], "title": t["title"], "rank": t["rank"], "total": t["total"],
                            "reasons": reasons})
        elif chosen is None:
            chosen = dict(t, primary_urls=prim)
    return chosen, skipped


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run")
    ap.add_argument("--published", help="ledger of published runs (default: <run>/published.json if present)")
    a = ap.parse_args()
    run = resolve_run(a.run)
    pub = Path(a.published) if a.published else run / "published.json"
    chosen, skipped = select(run, pub if pub.exists() else None)
    lines = [f"# Topic selection: {run.name}", "",
             "Mode: automatic (config/pipeline.json). The rule: highest-ranked topic that passes the rubric gates, "
             "reaches the minimum total and is not already published, staged or rejected on the channel. The human "
             "review happens on the finished video, before anything is made public.", ""]
    if skipped:
        lines += ["Skipped, in rank order:", ""]
        lines += [f"- {s['rank']}. {s['id']} {s['title']} (total {s['total']}): {'; '.join(s['reasons'])}" for s in skipped]
        lines.append("")
    if chosen is None:
        lines += ["**No topic qualifies.** The run stops here; nothing is written or uploaded."]
        (run / "selection.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"no topic qualifies; see {rel(run / 'selection.md')}", file=sys.stderr)
        return 1
    scores = ", ".join(f"{k} {'unknown' if v is None else v}" for k, v in chosen["scores"].items())
    lines += [f"**Selected: {chosen['id']} {chosen['title']}** (rank {chosen['rank']}, total {chosen['total']}; {scores}).",
              "", "The per-criterion reasons and sources are in ranking.md."]
    (run / "selection.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    write_json(run / "selection.json", {
        "schema_version": 1, "mode": "auto", "topic_id": chosen["id"], "title": chosen["title"], "slug": chosen["slug"],
        "rank": chosen["rank"], "total": chosen["total"], "scores": chosen["scores"],
        "primary_urls": chosen["primary_urls"], "selected_at": utc_now(), "rule": "tools/auto_select.py",
        "ranking_sha256": sha256_file(run / "ranking.md"), "skipped": skipped})
    print(f"selected {chosen['id']} ({chosen['title']}), total {chosen['total']}; reasons in {rel(run / 'selection.md')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
