#!/usr/bin/env python3
"""What the channel already covers, for the scout's coverage check (deterministic).

Usage:
  python3 tools/coverage.py runs/<run>          # writes runs/<run>/covered.json (tools/run.py new runs it too)
  options: --sources DIR (folder of source documents, default sources/), --series DIR (folder of series plans,
           default series/); the tests point both at fixtures

Collects, each with its keywords:
  ledger    runs in published.json (the ledger: ledger.json on the Pages branch, copied in by CI; tools/run.py new
            creates an empty one locally) with status published, staged or rejected
  source    every source document in sources/ (the explainers the series are made from): its title and each
            top-level section title
  series    every series in series/: its title and each episode title
The scout reads covered.json and records per candidate {"status": "new" | "partly_covered" | "covered", "by": [...]};
tools/validate.py warns when a candidate called new shares keywords with a covered item, and tools/rank_topics.py
excludes covered candidates.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import REPO, rel, resolve_run, utc_now, write_json  # noqa: E402

GENERIC = re.compile(r"^(abstract|references|verification status|synthesis|conclusions?|outlook|appendix.*|"
                     r"setting, notation and road map|notation.*)$", re.I)
STOP = set("a an and the of for in on to with by from at as is are be via its it this that new using how why what "
           "robot robots robotics control learning".split())


def keywords(text: str) -> list[str]:
    return sorted({w for w in re.findall(r"[a-z][a-z0-9-]{2,}", (text or "").lower()) if w not in STOP})


def explainer_items(html: Path) -> list[dict]:
    sys.path.insert(0, str(REPO / "tools"))
    import lint_html
    c = lint_html.Collector()
    text = html.read_text(encoding="utf-8")
    c.feed(text)
    c.close()
    m = re.search(r"<title>(.*?)</title>", text, re.S)
    title = re.sub(r"\s+", " ", m.group(1)).strip() if m else html.parent.name
    where = rel(html)
    items = [{"source": "source document", "title": title, "where": where, "status": "published", "keywords": keywords(title)}]
    for sid, (level, head, _) in c.headings.items():
        if level == 2:
            head = re.sub(r"^\d+(\.\d+)*\.?\s+", "", head).replace("$", "")
            if GENERIC.match(head):
                continue
            items.append({"source": "source document", "title": f"{title}: {head}", "where": f"{where}#{sid}",
                          "status": "published", "keywords": keywords(head)})
    return items


def build(run: Path, series_root: Path | None = None, sources_root: Path | None = None) -> dict:
    """series_root: the folder holding <slug>/series.json (default series/); sources_root: the folder holding
    <name>/explainer.html (default sources/). A file that cannot be read is listed in "skipped", never fatal."""
    items = []
    led_p = run / "published.json"
    led = json.loads(led_p.read_text(encoding="utf-8")) if led_p.exists() else {"runs": {}}
    for name, e in led.get("runs", {}).items():
        if e.get("status") in ("published", "staged", "rejected"):
            items.append({"source": "ledger", "title": e.get("title") or name, "where": name, "status": e["status"],
                          "slug": e.get("slug"), "primary_urls": e.get("primary_urls", []),
                          "keywords": keywords(f"{e.get('title', '')} {e.get('slug', '')}")})
    skipped = []
    src_root = Path(sources_root or REPO / "sources")
    for html in sorted(src_root.glob("*/explainer.html")):
        try:
            items += explainer_items(html)
        except (OSError, UnicodeDecodeError) as exc:
            skipped.append(f"{rel(html)}: {exc}")
    ser_root = Path(series_root or REPO / "series")
    for sp in sorted(ser_root.glob("*/series.json")):
        try:
            s = json.loads(sp.read_text(encoding="utf-8"))
            items.append({"source": "series", "title": s["title"], "where": rel(sp), "status": "series",
                          "keywords": keywords(s["title"])})
            for ep in s.get("episodes", []):
                items.append({"source": "series", "title": f"{s['title']}, episode {ep['number']}: {ep['title']}",
                              "where": rel(sp), "status": "planned", "keywords": keywords(ep["title"])})
        except (OSError, ValueError, KeyError, TypeError) as exc:
            skipped.append(f"{rel(sp)}: {exc}")
    return {"schema_version": 1, "made_at": utc_now(), "tool": "tools/coverage.py",
            "sources": {"ledger": rel(led_p) if led_p.exists() else None,
                        "sources": f"{rel(src_root)}/*/explainer.html", "series": f"{rel(ser_root)}/*/series.json"},
            "items": items, "skipped": skipped}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run")
    ap.add_argument("--sources", help="folder of source documents (default sources/)")
    ap.add_argument("--series", help="folder of series plans (default series/)")
    a = ap.parse_args()
    run = resolve_run(a.run)
    data = build(run, Path(a.series) if a.series else None, Path(a.sources) if a.sources else None)
    write_json(run / "covered.json", data)
    by = {}
    for it in data["items"]:
        by[it["source"]] = by.get(it["source"], 0) + 1
    print(f"wrote {rel(run / 'covered.json')}: " + ", ".join(f"{n} {k} item(s)" for k, n in sorted(by.items())))
    for s in data["skipped"]:
        print(f"warning: skipped {s}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
