#!/usr/bin/env python3
"""Compose the YouTube metadata for the final video (deterministic).

Usage:
  python3 tools/video/metadata.py runs/<run> [--links on|off|config] [--site-base https://<user>.github.io/<repo>]

Writes video/final/youtube.json: snippet (title, description, tags, category, languages), status (review privacy,
made-for-kids and synthetic-media declarations, licence) and the run's links decision. The description carries the
plan's summary, the primary sources (third-party attribution), the chapters (from chapters.json), the disclosure
line, a "Music:" credit when the mix carries music (from video/final/music.json: "original, generated"), the
Remaining Action footer and a "Run:" marker that makes uploads idempotent. A series episode's description
starts "Episode n of N · <series>", with links to the channel's own published episodes it builds on and to the series
playlist (our own YouTube videos: included even with links off; from video/series_context.json). Links to the
explainer and its
code are opt-in, per run, and only ever in the description: "links.include" in config/channel.json (default false),
overridden by --links or $INCLUDE_LINKS (on/off, set by the pipeline's "links" input). With links on, the site base URL
(--site-base or $SITE_BASE_URL) is required; with links off it is not used. Limits enforced here and re-checked by
tools/gate.py: title at most 100 characters, description at most 5,000 bytes, tags at most 500 characters in total,
no angle brackets anywhere. With
"contains_synthetic_media": "auto" (config/channel.json) the video is declared as containing synthetic media whenever
the narration is synthetic ($VOICE_SERVICE or voice.service other than "recorded").
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import CONFIG, load_json, rel, resolve_run, write_json  # noqa: E402
import plan as P  # noqa: E402

LIMIT_TITLE, LIMIT_DESC_BYTES, LIMIT_TAGS = 100, 5000, 500


def clean(s: str) -> str:
    return re.sub(r"[<>]", "", s)


def tags_length(tags: list[str]) -> int:
    return len(",".join(f'"{t}"' if " " in t else t for t in tags))


def synthetic_voice(channel: dict, run: Path | None = None) -> bool:
    """The narration voice is synthetic unless the run uses the user's own recordings.

    With video/voice/manifest.json (written by synthesize_voice.py) the answer comes from what made each block: any
    block from a speech service (piper, azure, ...) makes the voice synthetic; only recordings ("kept") do
    not. Without it: $VOICE_SERVICE, else voice.service, anything but "recorded".
    """
    man = run / "video" / "voice" / "manifest.json" if run else None
    if man is not None and man.exists():
        blocks = load_json(man).get("blocks", {})
        if blocks:
            return any(b.get("source", "kept") not in ("kept", "recorded") for b in blocks.values())
    service = (os.environ.get("VOICE_SERVICE") or channel.get("voice", {}).get("service", "silent")).strip().lower()
    return service != "recorded"


def synthetic_flag(channel: dict, run: Path | None = None) -> bool:
    """status.containsSyntheticMedia: true/false from config, or "auto" = true whenever the voice is synthetic."""
    v = channel["youtube"].get("contains_synthetic_media", "auto")
    return synthetic_voice(channel, run) if v == "auto" else bool(v)


def music_line(run: Path) -> str:
    """The description's music credit, from the provenance stamp assemble.py left (empty without music)."""
    asm_p, st_p = run / "video" / "final" / "assembly.json", run / "video" / "final" / "music.json"
    if not asm_p.exists() or not st_p.exists():
        return ""
    used = ((load_json(asm_p).get("audio") or {}).get("music") or {}).get("used")
    st = load_json(st_p)
    if not used:
        return ""
    if st.get("source") == "generated":
        return "Music: original, generated for this video."
    return ""


def links_included(channel: dict, override: str | None = None) -> bool:
    """The run's links decision: --links/$INCLUDE_LINKS (on/off/true/false) if given, else links.include."""
    v = (override if override is not None else os.environ.get("INCLUDE_LINKS", "")).strip().lower()
    if v in ("on", "true", "yes", "1"):
        return True
    if v in ("off", "false", "no", "0"):
        return False
    return bool(channel.get("links", {}).get("include", False))


def build(run: Path, site_base: str, include_links: bool | None = None) -> dict:
    plan = P.load(run)
    topic = P.topic(run)
    channel = load_json(CONFIG / "channel.json")
    yt = channel["youtube"]
    slug = topic["slug"]
    links = links_included(channel) if include_links is None else include_links
    base = site_base.rstrip("/") if links else ""
    if links and not base:
        raise ValueError("links are on for this run but there is no site base URL (--site-base or SITE_BASE_URL)")
    page = P.explainer_slug(run)
    anchor = f"#{topic['section_ids'][0]}" if P.is_series(run) and topic.get("section_ids") else ""
    explainer_url = f"{base}/explainers/{page}/{anchor}" if base else ""
    code_url = f"{base}/explainers/{page}/code/" if base else ""
    sp = run / "sources.json"
    sources = json.loads(sp.read_text(encoding="utf-8")) if sp.exists() else {"candidates": []}
    cand = next((c for c in sources["candidates"] if c["id"] == topic["topic_id"]), {"sources": []})
    primary = [s for s in cand["sources"] if s.get("primary")][:5]
    chs = []
    cp = run / "video" / "final" / "chapters.json"
    if cp.exists():
        data = json.loads(cp.read_text(encoding="utf-8"))
        chs = data["chapters"] if data.get("valid") else []

    ctx_p = run / "video" / "series_context.json"
    ctx = json.loads(ctx_p.read_text(encoding="utf-8")) if ctx_p.exists() else None

    def series_lines() -> list[str]:
        """"Episode n of N · <series>", then links to the channel's own published episodes this one builds on and to
        the playlist: YouTube links to our own videos, included whether or not links.include is on."""
        if not P.is_series(run):
            return []
        total = topic.get("episodes_total") or (ctx or {}).get("episodes_total")
        out = [f"Episode {topic['episode']}" + (f" of {total}" if total else "") + f" · {topic['series_title']}"]
        if ctx:
            built = [f"{ctx['short_titles'].get(k, k)}: https://www.youtube.com/watch?v={ctx['published'][k]}"
                     for k in ctx["prerequisites"]["must"] if ctx.get("published", {}).get(k)]
            if built:
                out += ["Builds on (restated in this video):"] + built
            if ctx.get("playlist_id"):
                out.append(f"The whole series: https://www.youtube.com/playlist?list={ctx['playlist_id']}")
        return out + [""]

    def compose(summary: str, n_sources: int) -> str:
        parts = series_lines() + [summary.strip(), ""]
        if explainer_url:
            parts += [f"Explainer with the equations, figures and references: {explainer_url}",
                      f"Code that reproduces every number: {code_url}", ""]
        if n_sources:
            parts.append("Primary sources:")
            parts += [f"- {s['title']} ({s['publisher']}): {s['url']}" for s in primary[:n_sources]]
            parts.append("")
        if chs:
            parts += ["Chapters:"] + [c["label"] for c in chs] + [""]
        note = channel["voice"].get("synthetic_voice_note", "") if synthetic_voice(channel, run) else ""
        parts += [" ".join(x for x in (note, channel["voice"]["disclosure"]) if x)]
        if music_line(run):
            parts.append(music_line(run))
        parts += ["",
                  f"{channel['channel_name']}: {channel['tagline']}",
                  channel["description_footer"]]
        if explainer_url and channel.get("links", {}).get("footer"):
            parts.append(channel["links"]["footer"])
        parts += ["", f"Run: {run.name}"]
        return clean("\n".join(parts))

    desc = compose(plan["summary"], len(primary))
    n = len(primary)
    while len(desc.encode("utf-8")) > LIMIT_DESC_BYTES and n > 0:
        n -= 1
        desc = compose(plan["summary"], n)
    if len(desc.encode("utf-8")) > LIMIT_DESC_BYTES:
        desc = compose(plan["summary"][:400] + "...", 0)
    tags, seen = [], set()
    for t in list(plan.get("tags", [])) + list(yt.get("default_tags", [])):
        t = clean(t).strip()
        if t and t.lower() not in seen and tags_length(tags + [t]) <= LIMIT_TAGS:
            tags.append(t)
            seen.add(t.lower())
    title = clean(plan["title"]).strip()[:LIMIT_TITLE]
    return {
        "schema_version": 1, "run": run.name, "marker": f"Run: {run.name}", "slug": slug,
        "links": {"included": bool(explainer_url), "explainer_url": explainer_url, "code_url": code_url},
        "music": music_line(run),
        "explainer_url": explainer_url, "code_url": code_url,
        "files": {"video": f"video/final/{slug}.mp4", "captions": f"video/final/{slug}.srt",
                  "thumbnail": "video/final/thumbnail.jpg"},
        "snippet": {"title": title, "description": desc, "tags": tags, "categoryId": yt.get("category_id", "28"),
                    "defaultLanguage": channel.get("language", "en"),
                    "defaultAudioLanguage": channel.get("language", "en")},
        "status": {"privacyStatus": yt.get("review_privacy", "private"),
                   "selfDeclaredMadeForKids": bool(yt.get("made_for_kids", False)),
                   "containsSyntheticMedia": synthetic_flag(channel, run),
                   "license": yt.get("license", "youtube"), "embeddable": bool(yt.get("embeddable", True)),
                   "publicStatsViewable": bool(yt.get("public_stats_viewable", True))},
        "publish": {"mode": yt.get("publish_mode", "public"),
                    "schedule_delay_hours": yt.get("schedule_delay_hours", 0)},
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run")
    ap.add_argument("--site-base", default=os.environ.get("SITE_BASE_URL", ""))
    ap.add_argument("--links", choices=["on", "off", "config"], help="override links.include for this run "
                    "(default: $INCLUDE_LINKS, else config/channel.json)")
    a = ap.parse_args()
    run = resolve_run(a.run)
    channel = load_json(CONFIG / "channel.json")
    include = links_included(channel, None if a.links in (None, "config") else a.links)
    try:
        meta = build(run, a.site_base, include)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    out = run / "video" / "final" / "youtube.json"
    write_json(out, meta)
    s = meta["snippet"]
    print(f"wrote {rel(out)}: title {len(s['title'])} chars, description {len(s['description'].encode())} bytes, "
          f"{len(s['tags'])} tags ({tags_length(s['tags'])} chars), privacy {meta['status']['privacyStatus']}"
          + ("; explainer and code linked in the description" if meta["links"]["included"]
             else "; no links (links.include off for this run)"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
