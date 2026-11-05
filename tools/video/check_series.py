#!/usr/bin/env python3
"""Structure of the video's opening and ending (every run) and of the series beats (series episodes): warnings only.

Usage:
  python3 tools/video/check_series.py runs/<run> [--stage draft|final]

House rules (the owner's decisions, 2026-10; thresholds in config/video.json "series"):
  hook first     a full, moving picture from the first frame (content covering at least first_frame_min_coverage
                 of the graphics-safe area at t = 0: self.add() it before the first play()); narration starts within
                 speech_start_max_s (a beat of motion and music may come first); the hook's question (a "?" in its
                 narration) is spoken by question_by_s; the body (the first scene with role "body") starts by
                 body_by_s; nothing before the first scene (no channel card); the title beat (role "context")
                 at most title_beat_max_s long and at least title_beat_min_speech of it spoken
  outro          the last scene (plan.json role "outro") lasts outro_min_s to outro_max_s, shows the channel name and
                 keeps x > endscreen_x_min (the right ~40 % of the frame) empty for YouTube's end-screen elements;
                 a series episode says "In the next episode, ..." there, the finale does not
  series context (series episodes) a scene with role "context" starting context_min_s to context_max_s into the
                 video, whose narration places the episode ("episode three of five") over the builds-on frame:
                 "Episode n of N" and the short titles of the episodes it builds on, shown builds_on_min_s to
                 builds_on_max_s
  recaps         one recap scene (role "recap", recap_of) per must prerequisite, with the "Recap" tag, a chapter that
                 starts with "Recap" and the recap's card on screen
  body mentions  a body scene that names an earlier episode (by short title or number) whose result this video
                 does not show (no recap of it)
  freshness      video/series_context.json made from the current series plan
  packaging      (every run) the title at most title_max_chars characters, containing plan.json "search_term" and
                 not the series title; the thumbnail text at most thumbnail_max_words words; the thumbnail frame from
                 the hook within its first thumbnail_by_s seconds ("click match": the promise is shown early)
Data: plan.json, the layout logs (video/checks/ or video/renders/), video/series_context.json, and at the final stage
video/final/assembly.json and the captions. Writes review/design/<stage>/check_series.json and .md; exit status 0
(the gate shows the warnings; the video design and final-cut reviewers judge them).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
from _common import CONFIG, REPO, load_json, rel, resolve_run, utc_now, write_json  # noqa: E402
import voice_script as VS  # noqa: E402

DEFAULTS = {"speech_start_max_s": 3.0, "question_by_s": 15, "first_frame_min_coverage": 0.02, "body_by_s": 45,
            "title_max_chars": 60, "thumbnail_max_words": 3, "thumbnail_by_s": 15, "title_beat_max_s": 6.5,
            "title_beat_min_speech": 0.5, "context_min_s": 30, "context_max_s": 90, "builds_on_min_s": 4,
            "builds_on_max_s": 6, "recap_min_s": 15, "recap_max_s": 75, "outro_min_s": 15, "outro_max_s": 20,
            "endscreen_x_min": 1.4}
NUMWORDS = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve"]


def settings() -> dict:
    cfg = dict(DEFAULTS)
    cfg.update(load_json(CONFIG / "video.json").get("series", {}))
    return cfg


def number_said(text: str, n: int) -> bool:
    words = [str(n)] + ([NUMWORDS[n]] if n < len(NUMWORDS) else [])
    return any(re.search(rf"\bepisode\s+{w}\b", text, re.I) for w in words)


def norm_tex(t: str) -> str:
    return re.sub(r"\s+|\\[,;:! ]|\\q?quad", "", t or "")


class Warnings:
    def __init__(self):
        self.items: list[dict] = []

    def add(self, check: str, t: float | None, detail: str):
        self.items.append({"check": check, "t": None if t is None else round(t, 1), "detail": detail})


def scene_logs(run: Path, stage: str, plan: dict) -> dict:
    folder = run / "video" / ("checks" if stage == "draft" else "renders")
    out = {}
    for s in plan.get("scenes", []):
        lp = folder / f"{s['class']}.layout.json"
        if lp.exists():
            log_all = json.loads(lp.read_text(encoding="utf-8"))
            out[s["class"]] = log_all["scenes"].get(s["class"]) or next(iter(log_all["scenes"].values()), {})
    return out


def texts_of(log: dict) -> list[dict]:
    return [x for x in log.get("timeline", []) if not x.get("axis")]


def visible_span(item: dict) -> float:
    """Seconds an item is visible, from its timeline events."""
    total, on = 0.0, None
    for ev in item.get("events", []):
        if ev[1] == 1 and on is None:
            on = ev[0]
        elif ev[1] == 0 and on is not None:
            total += ev[0] - on
            on = None
    return total + (item["events"][-1][0] - on if on is not None and item.get("events") else 0.0)


def first_frame_coverage(log: dict) -> float | None:
    """Share of the graphics-safe area covered by visible content in the first snapshot (t = 0), as check_design.py
    measures space use; None without a snapshot at 0."""
    import check_design as CD
    snaps = [x for x in log.get("snapshots", []) if x.get("t", 1) <= 0.05]
    if not snaps:
        return None
    d = dict(CD.load_cfg()["design"]) if hasattr(CD, "load_cfg") else \
        dict(load_json(CONFIG / "video.json").get("design", {}))
    fw, fh = 14.222, 8.0
    inset = d.get("graphics_safe_inset", 0.05)
    gfx = [-fw / 2 * (1 - 2 * inset), -fh / 2 * (1 - 2 * inset), fw / 2 * (1 - 2 * inset), fh / 2 * (1 - 2 * inset)]
    best = 0.0
    for snap in snaps:
        texts, paths, _ = CD.front(snap, {}, d)
        best = max(best, CD.space_usage(texts, paths, gfx, d).get("coverage", 0.0))
    return best


def hook_checks(scenes: list[dict], logs: dict, starts: dict, narration: dict, cfg: dict, w: "Warnings") -> None:
    """The opening (owner's rule, 2026-11): a full moving picture from frame 0, a beat before the first word, the
    question early, the body soon."""
    first = logs.get(scenes[0]["class"]) or {}
    if first:
        cov = first_frame_coverage(first)
        if cov is not None and cov < cfg["first_frame_min_coverage"]:
            w.add("hook first", 0.0, f"the first frame is {cov:.0%} covered (at least {cfg['first_frame_min_coverage']:.0%}"
                  "): open on a full picture (self.add() it before the first play()), not on an empty frame")
    asked = None
    for s in scenes:
        if s.get("role") not in (None, "hook", "context"):
            break
        for vo in (logs.get(s["class"]) or {}).get("voiceovers", []):
            text = vo.get("text", "")
            if "?" in text:
                k = text.index("?") / max(len(text), 1)
                asked = starts.get(s["class"], 0.0) + vo["start"] + k * vo.get("duration", 0.0)
                break
        if asked is not None:
            break
    if first and asked is None:
        w.add("hook first", None, "the hook asks no question (no \"?\" in its narration): open with the question the "
              "video answers")
    elif asked is not None and asked > cfg["question_by_s"]:
        w.add("hook first", asked, f"the hook's question comes at {asked:.0f} s (by {cfg['question_by_s']} s)")
    for s in [s for s in scenes if s.get("role") == "context"][:1]:
        log = logs.get(s["class"]) or {}
        dur = log.get("duration", 0.0)
        said = sum(v.get("duration", 0.0) for v in log.get("voiceovers", []))
        if log and dur > cfg["title_beat_max_s"]:
            w.add("title beat", starts.get(s["class"]), f"the title beat lasts {dur:.1f} s (at most "
                  f"{cfg['title_beat_max_s']:g} s): one spoken sentence over the title, then the body")
        if log and dur and said / dur < cfg["title_beat_min_speech"]:
            w.add("title beat", starts.get(s["class"]), f"the title beat is {said / dur:.0%} speech (at least "
                  f"{cfg['title_beat_min_speech']:.0%}): no long silent hold on the title card")
    body = next((s for s in scenes if s.get("role") in (None, "body")), None)
    if body is not None and body["class"] in starts and (logs.get(body["class"]) or starts[body["class"]] > 0):
        t0 = starts[body["class"]]
        if t0 > cfg["body_by_s"]:
            w.add("hook first", t0, f"the body starts at {t0:.0f} s (by {cfg['body_by_s']} s): shorten the hook and "
                  "the series context")


def packaging(plan: dict, cfg: dict, w: "Warnings") -> None:
    """Title and thumbnail rules (warnings): short, with the search term, without the series name; few words on the
    thumbnail; its picture shown early in the hook."""
    title = plan.get("title", "")
    if len(title) > cfg["title_max_chars"]:
        w.add("packaging", None, f"the title has {len(title)} characters (at most {cfg['title_max_chars']} show in full)")
    term = plan.get("search_term")
    if not term:
        w.add("packaging", None, "plan.json has no \"search_term\" (the words viewers search for, e.g. \"MPC\")")
    elif term.lower() not in title.lower():
        w.add("packaging", None, f"the title does not contain the search term {term!r}")
    series_title = (plan.get("_series_title") or "")
    if series_title and series_title.lower() in title.lower():
        w.add("packaging", None, "the title repeats the series name: the playlist and the description carry it")
    th = plan.get("thumbnail") or {}
    words = len(str(th.get("text", "")).split())
    if words > cfg["thumbnail_max_words"]:
        w.add("packaging", None, f"the thumbnail text has {words} words (at most {cfg['thumbnail_max_words']}; one "
              "bold picture carries it)")
    scenes = plan.get("scenes", [])
    hook = scenes[0]["class"] if scenes else None
    if th.get("scene") != hook or float(th.get("time", 1e9)) > cfg["thumbnail_by_s"]:
        w.add("packaging", None, f"the thumbnail frame is not from the hook's first {cfg['thumbnail_by_s']} s: show "
              "the thumbnail's picture early (click match)")


def check(run: Path, stage: str, cfg: dict) -> tuple[list[dict], dict]:
    w = Warnings()
    plan = json.loads((run / "video" / "plan.json").read_text(encoding="utf-8"))
    ctx0 = run / "video" / "series_context.json"
    if ctx0.exists():
        plan["_series_title"] = json.loads(ctx0.read_text(encoding="utf-8")).get("series_title", "")
    scenes = plan.get("scenes", [])
    logs = scene_logs(run, stage, plan)
    channel = load_json(CONFIG / "channel.json").get("channel_name", "Remaining Action")
    starts, t = {}, 0.0
    asm_p = run / "video" / "final" / "assembly.json"
    if stage == "final" and asm_p.exists():
        asm = json.loads(asm_p.read_text(encoding="utf-8"))
        segs = asm.get("segments", [])
        if segs and segs[0].get("kind") != "scene":
            w.add("hook first", 0.0, f"the video opens with an {segs[0].get('kind')} card: nothing comes before the "
                  "hook (no channel card)")
        starts = {s.get("class"): s["start"] for s in segs if s.get("kind") == "scene"}
    else:
        for s in scenes:
            starts[s["class"]] = t
            t += (logs.get(s["class"]) or {}).get("duration", 0.0)
    narration = {}
    for f in sorted((run / "video" / "scenes").glob("*.py")):
        if f.name not in ("common.py", "voice.py", "reading_model.py"):
            for cls, blocks in VS.blocks_by_class(f).items():
                narration[cls] = " ".join(b for b in blocks if b)
    # hook first
    if scenes:
        first = logs.get(scenes[0]["class"]) or {}
        vo = first.get("voiceovers") or []
        start = vo[0]["start"] if vo else None
        if scenes[0].get("role") not in (None, "hook"):
            w.add("hook first", 0.0, f"the first scene has role {scenes[0].get('role')!r}: the video opens with its hook")
        if start is None:
            w.add("hook first", 0.0, f"no narration in the first scene ({scenes[0]['class']}): speech starts at 0 s")
        elif start > cfg["speech_start_max_s"]:
            w.add("hook first", start, f"narration starts at {start:.1f} s (at most {cfg['speech_start_max_s']} s)")
    if scenes:
        hook_checks(scenes, logs, starts, narration, cfg, w)
    packaging(plan, cfg, w)
    # outro
    if scenes:
        last = scenes[-1]
        log = logs.get(last["class"]) or {}
        dur = log.get("duration", 0.0)
        t0 = starts.get(last["class"])
        if last.get("role") != "outro":
            w.add("outro", t0, f"the last scene ({last['class']}) is not marked role \"outro\" (takeaway card, channel "
                  "name, teaser)")
        if log and not cfg["outro_min_s"] <= dur <= cfg["outro_max_s"]:
            w.add("outro", t0, f"the outro lasts {dur:.1f} s ({cfg['outro_min_s']}-{cfg['outro_max_s']} s give "
                  "YouTube's end screen its window)")
        if log and not any(channel.lower() in (x.get("content") or "").lower() for x in texts_of(log)):
            w.add("outro", t0, f"the outro does not show the channel name ({channel}): use outro()")
        for snap in log.get("snapshots", []):
            busy = [x.get("content", "")[:30] for x in snap.get("texts", []) if x["bbox"][2] > cfg["endscreen_x_min"]
                    and x.get("opacity", 1) >= 0.3]
            busy += ["a shape" for p in snap.get("paths", []) if p["bbox"][2] > cfg["endscreen_x_min"] + 0.05 and
                     (p["stroke_opacity"] >= 0.3 or p["fill_opacity"] >= 0.3) and
                     (p["bbox"][2] - p["bbox"][0]) < 13.5]
            if busy:
                w.add("outro", (t0 or 0) + snap["t"], f"content in the end-screen area (x > {cfg['endscreen_x_min']}): "
                      f"{busy[0]!r}; keep the right of the frame empty during the outro")
                break
    ctx_p = run / "video" / "series_context.json"
    ctx = json.loads(ctx_p.read_text(encoding="utf-8")) if ctx_p.exists() else None
    info = {"series": bool(ctx)}
    if scenes and ctx:
        said = narration.get(scenes[-1]["class"], "")
        has_next = bool(re.search(r"\bnext\s+episode\b", said, re.I))
        if ctx.get("kind") == "finale" and has_next:
            w.add("teaser", starts.get(scenes[-1]["class"]), "the finale has no teaser ('next episode' in its outro)")
        if ctx.get("kind") != "finale" and ctx.get("teaser") and not has_next:
            w.add("teaser", starts.get(scenes[-1]["class"]), "the outro does not say \"In the next episode, ...\" "
                  f"(teaser: {ctx['teaser'][:80]})")
    if not ctx:
        return w.items, info
    n, total = ctx["episode"], ctx["episodes_total"]
    # series context and the builds-on frame
    context = [s for s in scenes if s.get("role") == "context"]
    if total > 1 and not context:
        w.add("series context", None, "no scene with role \"context\": after the hook, say where this episode sits "
              "over the builds-on frame (builds_on())")
    for s in context[:1]:
        t0 = starts.get(s["class"], 0.0)
        if not cfg["context_min_s"] <= t0 <= cfg["context_max_s"]:
            w.add("series context", t0, f"the series context starts at {t0:.0f} s (the first natural break, about "
                  f"{cfg['context_min_s']}-{cfg['context_max_s']} s)")
        if not number_said(narration.get(s["class"], ""), n):
            w.add("series context", t0, f"the context narration does not say which episode this is (\"episode "
                  f"{NUMWORDS[n] if n < len(NUMWORDS) else n} of ...\")")
        log = logs.get(s["class"]) or {}
        heading = f"Episode {n} of {total}"
        items = texts_of(log)
        head = [x for x in items if (x.get("content") or "").strip() == heading]
        if log and not head:
            w.add("series context", t0, f"no \"{heading}\" on screen (builds_on())")
        elif head:
            shown = max(visible_span(x) for x in head)
            if not cfg["builds_on_min_s"] <= shown <= cfg["builds_on_max_s"] + 0.5:
                w.add("series context", t0, f"the builds-on frame shows for {shown:.1f} s "
                      f"({cfg['builds_on_min_s']}-{cfg['builds_on_max_s']} s)")
        for k in ctx["prerequisites"]["must"]:
            title = ctx["short_titles"].get(k, k)
            if log and not any((x.get("content") or "").strip() == title for x in items):
                w.add("series context", t0, f"the builds-on frame does not name '{title}' (episode {k})")
    # recaps
    recaps = {str(s.get("recap_of")): s for s in scenes if s.get("role") == "recap"}
    for k in ctx["prerequisites"]["must"]:
        s = recaps.get(str(k))
        title = ctx["short_titles"].get(k, k)
        if not s:
            w.add("recap", None, f"no recap of episode {k} ('{title}'), which this one builds on: recap everything used")
            continue
        t0 = starts.get(s["class"])
        log = logs.get(s["class"]) or {}
        dur = log.get("duration", 0.0)
        if log and not cfg["recap_min_s"] <= dur <= cfg["recap_max_s"]:
            w.add("recap", t0, f"the recap of '{title}' lasts {dur:.0f} s (about {cfg['recap_min_s']}-"
                  f"{cfg['recap_max_s']} s)")
        if not str(s.get("chapter", "")).startswith("Recap"):
            w.add("recap", t0, f"the recap of '{title}' needs its own chapter starting with \"Recap\"")
        if log and not any((x.get("content") or "").strip() == "Recap" for x in texts_of(log)):
            w.add("recap", t0, f"the recap of '{title}' shows no \"Recap\" tag (recap_tag())")
        card = next((rc.get("card") for rc in ctx.get("recaps", []) if str(k) in rc.get("from", [])), None) or []
        shown = {norm_tex(x.get("content")) for x in texts_of(log) if x.get("kind") == "math"}
        missing = [c for c in card if norm_tex(c) not in shown]
        if log and card and missing:
            w.add("recap", t0, f"the recap of '{title}' does not show its card ({missing[0][:40]}...; recap_card())")
    # other episodes named in the body without a recap
    body = [s for s in scenes if s.get("role") in (None, "body")]
    known = {k: v for k, v in ctx.get("short_titles", {}).items()}
    for s in body:
        said = narration.get(s["class"], "")
        for k, title in known.items():
            num = k.split(":")[-1]
            named = (title and title.lower() in said.lower()) or (num.isdigit() and number_said(said, int(num)))
            if named and str(k) not in recaps:
                w.add("body mentions", starts.get(s["class"]), f"{s['class']} names episode {k} ('{title}'), whose "
                      "result this video does not show (no recap of it)")
    # freshness
    sp = REPO / "series" / ctx["series"] / "series.json"
    if sp.exists():
        import series as S
        if S.plan_hash(json.loads(sp.read_text(encoding="utf-8"))) != ctx.get("plan_sha256"):
            w.add("freshness", None, "video/series_context.json was made from an earlier version of the series plan")
    info.update(episode=n, episodes_total=total, kind=ctx.get("kind"))
    return w.items, info


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run")
    ap.add_argument("--stage", choices=["draft", "final"], default="draft")
    a = ap.parse_args()
    run = resolve_run(a.run)
    items, info = check(run, a.stage, settings())
    out = run / "review" / "design" / a.stage
    out.mkdir(parents=True, exist_ok=True)
    write_json(out / "check_series.json", {"schema_version": 1, "tool": "check_series", "stage": a.stage,
                                           "checked_at": utc_now(), "info": info, "warnings": items})
    md = [f"# Opening, ending and series beats ({a.stage})", "", f"{len(items)} warning(s); house rules and "
          "thresholds in config/video.json \"series\".", ""]
    if items:
        md += ["| Check | t (s) | Detail |", "|---|---|---|"]
        md += [f"| {x['check']} | {'' if x['t'] is None else x['t']} | {x['detail'].replace('|', '/')} |" for x in items]
    (out / "check_series.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    for x in items:
        print(f"warning {x['check']}{'' if x['t'] is None else ' t=' + str(x['t']) + 's'}: {x['detail']}")
    print(f"check_series ({a.stage}): {len(items)} warning(s); {rel(out / 'check_series.md')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
