#!/usr/bin/env python3
"""Manage the GitHub Pages site (a checkout of the gh-pages branch): previews, published explainers, ledger, archive.

Usage (SITE is the gh-pages checkout; the workflow commits and pushes it afterwards):
  python3 tools/publish/site.py init SITE
  python3 tools/publish/site.py preview SITE runs/<run> --token T          # preview/<run>-<T>/ (noindex); prints its path
  python3 tools/publish/site.py promote SITE runs/<run> --token T [--video-id ID]   # explainers/<slug>/, index, ledger
  python3 tools/publish/site.py drop-preview SITE <run> --token T
  python3 tools/publish/site.py mark SITE runs/<run> --status staged|published|rejected [--video-id ID] [--reason R]
                                                                          [--by LOGIN] [--linkedin URN]

Published explainers live at explainers/<slug>/ with the explainer (index.html), its companion code (browsable, plus
code.zip) and the review and gate summaries. ledger.json records every run (status, video id, slug, primary sources)
and is what makes staging, publishing and topic selection idempotent; it never stores preview tokens. Rejected runs
get archive/<run>.json with the reason.
"""
from __future__ import annotations

import argparse
import html
import json
import re
import shutil
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "video"))
from _common import CONFIG, load_json, resolve_run, utc_now, write_json  # noqa: E402
import plan as P  # noqa: E402

NOINDEX = '<meta name="robots" content="noindex, nofollow">'
CODE_SKIP = {"__pycache__"}


def ledger(site: Path) -> dict:
    p = site / "ledger.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {
        "schema_version": 1, "channel": load_json(CONFIG / "channel.json")["channel_name"], "runs": {}}


def save_ledger(site: Path, data: dict) -> None:
    write_json(site / "ledger.json", data)


def page(title: str, body: str, noindex: bool = False) -> str:
    ch = load_json(CONFIG / "channel.json")
    return (f"<!DOCTYPE html>\n<html lang=\"en\">\n<head>\n<meta charset=\"UTF-8\">\n"
            f"<meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">\n"
            f"{NOINDEX if noindex else ''}\n<title>{html.escape(title)}</title>\n<style>\n"
            "body{font-family:'Palatino Linotype',Palatino,Georgia,serif;color:#1e293b;max-width:860px;margin:0 auto;"
            "padding:2rem 1rem;line-height:1.6;background:#fff}h1{color:#0f172a;border-bottom:2px solid #3b82f6;"
            "padding-bottom:.4rem}a{color:#3b82f6;text-decoration:none}li{margin:.5rem 0}.muted{color:#64748b}\n"
            f"</style>\n</head>\n<body>\n<p class=\"muted\">{html.escape(ch['channel_name'])}: "
            f"{html.escape(ch['tagline'])}</p>\n{body}\n</body>\n</html>\n")


def copy_code(run: Path, dest: Path) -> None:
    src = run / "code"
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(src, dest, ignore=shutil.ignore_patterns(*CODE_SKIP))
    items = sorted(p.relative_to(dest).as_posix() for p in dest.rglob("*") if p.is_file())
    links = "\n".join(f'<li><a href="{html.escape(i)}">{html.escape(i)}</a></li>' for i in items)
    (dest / "index.html").write_text(page("Companion code", f"<h1>Companion code</h1>\n<p>Every number in the "
                                          f"explainer is printed by one of these scripts. Start with "
                                          f"<a href=\"README.md\">README.md</a>, or download "
                                          f"<a href=\"../code.zip\">code.zip</a>.</p>\n<ul>\n{links}\n</ul>"),
                                     encoding="utf-8")
    with zipfile.ZipFile(dest.parent / "code.zip", "w", zipfile.ZIP_DEFLATED) as z:
        for i in items:
            if i != "index.html":
                z.write(dest / i, f"code/{i}")


def brand_line(video_url: str = "") -> str:
    """One line under the explainer's title: the channel (site index), the video, the code."""
    ch = load_json(CONFIG / "channel.json")
    links = [f'<a href="../../">{html.escape(ch["channel_name"])}</a>']
    if video_url:
        links.append(f'<a href="{html.escape(video_url)}">Watch the video</a>')
    links.append('<a href="code/">The code behind every number</a>')
    return '<div class="date site-links">' + " &middot; ".join(links) + "</div>\n"


def install(run: Path, dest: Path, noindex: bool, video_url: str = "") -> None:
    dest.mkdir(parents=True, exist_ok=True)
    text = (run / "explainer.html").read_text(encoding="utf-8")
    text = text.replace(NOINDEX + "\n", "")
    if noindex:
        text = text.replace('<meta charset="UTF-8">', '<meta charset="UTF-8">\n' + NOINDEX, 1)
    if "</header>" in text:
        text = text.replace("</header>", brand_line(video_url) + "</header>", 1)
    (dest / "index.html").write_text(text, encoding="utf-8")
    copy_code(run, dest / "code")
    rv = dest / "review"
    rv.mkdir(exist_ok=True)
    for name in ("summary.md", "gates.md"):
        if (run / "review" / name).exists():
            shutil.copy(run / "review" / name, rv / name)


def rebuild_index(site: Path) -> None:
    data = ledger(site)
    pubs = sorted((r for r in data["runs"].values() if r.get("status") == "published"),
                  key=lambda r: r.get("published_at", ""), reverse=True)
    items = []
    for r in pubs:
        video = f' &middot; <a href="{html.escape(r["video_url"])}">video</a>' if r.get("video_url") else ""
        path = r.get("explainer_path") or f"explainers/{r['slug']}/"
        ep = f"Episode {r['episode']}: " if r.get("episode") is not None else ""
        items.append(f'<li>{html.escape(ep)}<a href="{html.escape(path)}">{html.escape(r["title"])}</a> '
                     f'<span class="muted">{html.escape(r.get("published_at", "")[:10])}</span>{video} &middot; '
                     f'<a href="{html.escape(path)}code/">code</a></li>')
    ch = load_json(CONFIG / "channel.json")
    body = (f"<h1>{html.escape(ch['channel_name'])}</h1>\n<p>{html.escape(ch['description_footer'])}</p>\n"
            f"<ul>\n{chr(10).join(items) or '<li>Nothing published yet.</li>'}\n</ul>")
    (site / "index.html").write_text(page(ch["channel_name"], body), encoding="utf-8")


def drop_previews(site: Path, run_name: str) -> None:
    """Remove every preview of this run (a re-run of the staging job makes a new token)."""
    for d in (site / "preview").glob(f"{run_name}-*"):
        if d.is_dir() and re.fullmatch(re.escape(run_name) + r"-[0-9a-f]+", d.name):
            shutil.rmtree(d, ignore_errors=True)


def cmd_init(site: Path) -> None:
    site.mkdir(parents=True, exist_ok=True)
    (site / ".nojekyll").write_text("", encoding="utf-8")
    if not (site / "ledger.json").exists():
        save_ledger(site, ledger(site))
    rebuild_index(site)


def entry_for(run: Path, data: dict) -> dict:
    topic = P.topic(run)
    e = data["runs"].setdefault(run.name, {})
    e.update({"slug": topic["slug"], "title": P.load(run)["title"], "topic_id": topic["topic_id"]})
    if P.is_series(run):
        e.update({"series": topic["series"], "episode": topic["episode"],
                  "explainer_path": f"explainers/{P.explainer_slug(run)}/"})
    sp = run / "sources.json"
    sources = json.loads(sp.read_text(encoding="utf-8")) if sp.exists() else {"candidates": []}
    cand = next((c for c in sources["candidates"] if c["id"] == topic["topic_id"]), {"sources": []})
    e["primary_urls"] = [s["url"] for s in cand["sources"] if s.get("primary") and s.get("relation", "subject") == "subject"]
    return e


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    i = sub.add_parser("init")
    i.add_argument("site")
    pv = sub.add_parser("preview")
    pv.add_argument("site")
    pv.add_argument("run")
    pv.add_argument("--token", required=True)
    pr = sub.add_parser("promote")
    pr.add_argument("site")
    pr.add_argument("run")
    pr.add_argument("--token", required=True)
    pr.add_argument("--video-id")
    dp = sub.add_parser("drop-preview")
    dp.add_argument("site")
    dp.add_argument("run_name")
    dp.add_argument("--token", required=True)
    mk = sub.add_parser("mark")
    mk.add_argument("site")
    mk.add_argument("run")
    mk.add_argument("--status", required=True, choices=["staged", "published", "rejected"])
    mk.add_argument("--video-id")
    mk.add_argument("--reason", default="")
    mk.add_argument("--by", default="")
    mk.add_argument("--linkedin", default="")
    mk.add_argument("--playlist", default="", help="series playlist id (series episodes)")
    a = ap.parse_args()
    site = Path(a.site)
    if a.cmd == "init":
        cmd_init(site)
        print("site initialised")
        return 0
    if a.cmd == "drop-preview":
        if not re.match(r"^[\w.-]+$", a.run_name + a.token):
            raise SystemExit("error: bad run name or token")
        shutil.rmtree(site / "preview" / f"{a.run_name}-{a.token}", ignore_errors=True)
        drop_previews(site, a.run_name)
        print("preview removed")
        return 0
    run = resolve_run(a.run)
    cmd_init(site) if not (site / "ledger.json").exists() else None
    data = ledger(site)
    e = entry_for(run, data)
    if a.cmd == "preview":
        rel_path = f"preview/{run.name}-{a.token}/"
        drop_previews(site, run.name)
        install(run, site / rel_path, noindex=True)
        e.setdefault("status", "staged")
        e["staged_at"] = utc_now()
        save_ledger(site, data)
        print(rel_path)
        return 0
    if a.cmd == "promote":
        slug = P.explainer_slug(run)
        install(run, site / "explainers" / slug, noindex=False,
                video_url=f"https://youtu.be/{a.video_id}" if a.video_id else "")
        drop_previews(site, run.name)
        e.update({"status": "published", "published_at": utc_now(), "explainer_path": f"explainers/{slug}/"})
        if a.video_id:
            e.update({"video_id": a.video_id, "video_url": f"https://youtu.be/{a.video_id}"})
        save_ledger(site, data)
        rebuild_index(site)
        print(f"explainers/{slug}/")
        return 0
    # mark
    e["status"] = a.status
    e[f"{a.status}_at"] = utc_now()
    if a.video_id:
        e["video_id"] = a.video_id
    if a.linkedin:
        e["linkedin_post"] = a.linkedin
    if a.playlist and e.get("series"):
        e["playlist_id"] = a.playlist
        data.setdefault("series", {}).setdefault(e["series"], {})["playlist_id"] = a.playlist
    if a.status == "rejected":
        e.update({"reason": a.reason, "rejected_by": a.by})
        write_json(site / "archive" / f"{run.name}.json", {"run": run.name, "title": e.get("title"),
                                                           "reason": a.reason, "rejected_by": a.by,
                                                           "rejected_at": e["rejected_at"],
                                                           "video_id": e.get("video_id")})
    save_ledger(site, data)
    rebuild_index(site)
    print(f"{run.name}: {a.status}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
