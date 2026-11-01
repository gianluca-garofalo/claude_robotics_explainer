"""video/plan.json: what the final video contains (written by the manim-video-producer skill, read by the tools).

{
  "schema_version": 1,
  "title": "YouTube title, at most 90 characters, no angle brackets",
  "summary": "Two to four sentences for the description (at most 900 characters)",
  "tags": ["model predictive control", "..."],
  "scenes": [{"file": "hilltop.py", "class": "Hilltop", "section": "sec-hj", "chapter": "Only one push arrives",
              "role": "body"}],
  "thumbnail": {"scene": "Hilltop", "time": 12.5, "text": "Only H = 0 arrives"}
}
Scenes play in this order; nothing is added before the first (no channel card) and the last is the outro. "section"
is the explainer section the scene draws on (a source, for the review and, only when links are on, the description;
any heading id of the explainer), "chapter" the chapter title viewers see, written for the video (never the
explainer's heading; consecutive scenes with the same chapter form one chapter). "role" (optional, checked by
tools/video/check_series.py): "hook" (first, speech from 0 s), "context" (the spoken series context over the
builds-on frame), "recap" (with "recap_of": the earlier episode it restates, a number or "series:episode"), "body",
"outro" (last: takeaway card, channel name, the teaser).
"""
from __future__ import annotations

import json
import re
from pathlib import Path

CLASS_RE = re.compile(r"^class ([A-Za-z_][A-Za-z0-9_]*)\([A-Za-z0-9_.]*Scene\):", re.M)
FILE_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}\.py$")
NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")
ROLES = ("hook", "context", "recap", "body", "outro")


def load(run: Path) -> dict:
    return json.loads((run / "video" / "plan.json").read_text(encoding="utf-8"))


def topic(run: Path) -> dict:
    """The approved topic: selection.json (automatic mode), approval.json (human mode) or episode.json (series mode)."""
    for name in ("selection.json", "approval.json", "episode.json"):
        if (run / name).exists():
            return json.loads((run / name).read_text(encoding="utf-8"))
    raise FileNotFoundError("no selection.json, approval.json or episode.json: no topic was approved")


def is_series(run: Path) -> bool:
    return (run / "episode.json").exists()


def explainer_slug(run: Path) -> str:
    """Where the explainer is published: the series' explainer for an episode, else the topic's own page."""
    t = topic(run)
    return t.get("explainer_slug") or t["slug"]


def final_video(run: Path) -> Path:
    return run / "video" / "final" / f"{topic(run)['slug']}.mp4"


def explainer_sections(run: Path) -> dict[str, str]:
    """{heading id: section number ('6.3', or '' when unnumbered)} of the run's explainer.html ({} without one)."""
    page = run / "explainer.html"
    if not page.exists():
        return {}
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    import lint_html
    c = lint_html.Collector()
    c.feed(page.read_text(encoding="utf-8"))
    c.close()
    out = {}
    for sid, (_, text, _) in c.headings.items():
        if sid:
            m = re.match(r"^(\d+(?:\.\d+)*)\.?\s", text)
            out[sid] = m.group(1) if m else ""
    return out


def problems(run: Path, plan: dict | None = None) -> list[str]:
    """Every way plan.json is unusable; an empty list means it is fine."""
    out = []
    try:
        plan = plan if plan is not None else load(run)
    except FileNotFoundError:
        return ["video/plan.json is missing"]
    except json.JSONDecodeError as exc:
        return [f"video/plan.json is not valid JSON: {exc}"]
    if plan.get("schema_version") != 1:
        out.append("plan.json: schema_version must be 1")
    title = plan.get("title", "")
    if not isinstance(title, str) or not title.strip() or len(title) > 90 or re.search(r"[<>]", title):
        out.append("plan.json: title must be 1-90 characters without < or >")
    summary = plan.get("summary", "")
    if not isinstance(summary, str) or not summary.strip() or len(summary) > 900 or re.search(r"[<>]", summary):
        out.append("plan.json: summary must be 1-900 characters without < or >")
    tags = plan.get("tags", [])
    if not isinstance(tags, list) or not all(isinstance(t, str) and t.strip() and not re.search(r"[<>,]", t) for t in tags):
        out.append("plan.json: tags must be a list of strings without < > or commas")
    scenes = plan.get("scenes")
    if not isinstance(scenes, list) or not scenes:
        out.append("plan.json: scenes must list at least one scene")
        scenes = []
    seen = set()
    sections = explainer_sections(run)
    for i, s in enumerate(scenes):
        if not isinstance(s, dict):
            out.append(f"plan.json: scenes[{i}] must be an object with file, class and section")
            continue
        f, c = s.get("file", ""), s.get("class", "")
        path = run / "video" / "scenes" / str(f)
        if not (isinstance(f, str) and FILE_RE.match(f) and isinstance(c, str) and NAME_RE.match(c)):
            out.append(f"plan.json: scenes[{i}] needs a plain file name (letters, digits, _ or -, ending in .py) and "
                       "a Python class name")      # these values reach file paths and the CI render matrix
        elif not path.exists():
            out.append(f"plan.json: scenes[{i}] file {f!r} not found in video/scenes/")
        elif c not in CLASS_RE.findall(path.read_text(encoding="utf-8")):
            out.append(f"plan.json: scenes[{i}] class {c!r} is not a Scene class in {f}")
        if c in seen:
            out.append(f"plan.json: class {c!r} listed twice")
        seen.add(c)
        if not s.get("section") and s.get("role") not in ("context", "outro"):
            out.append(f"plan.json: scenes[{i}] needs the explainer section id it draws on (only context and outro "
                       "scenes may omit it)")
        if not isinstance(s.get("chapter"), str) or not s["chapter"].strip() or len(s["chapter"]) > 60 or \
                re.search(r"[<>]", s["chapter"]):
            out.append(f"plan.json: scenes[{i}] needs a \"chapter\": the title viewers see, 1-60 characters")
        if s.get("section") and sections and s["section"] not in sections:
            out.append(f"plan.json: scenes[{i}] section {s['section']!r} is not a heading id of explainer.html")
        role = s.get("role")
        if role is not None and role not in ROLES:
            out.append(f"plan.json: scenes[{i}] role {role!r} is not one of {', '.join(ROLES)}")
        if role == "recap" and not s.get("recap_of"):
            out.append(f"plan.json: scenes[{i}] is a recap: give recap_of, the earlier episode it restates")
    try:
        import check_selfcontained as SC                  # chapter titles and the thumbnail text face the viewer
        st = SC.settings()
        texts = [(f"scenes[{i}] chapter", s.get("chapter")) for i, s in enumerate(scenes) if isinstance(s, dict)]
        texts.append(("thumbnail text", (plan.get("thumbnail") or {}).get("text")))
        for where, text in texts:
            if isinstance(text, str):
                for f in SC.scan_plain(text, st):
                    out.append(f"plan.json: {where} {text!r}: {f['rule']} '{f['match']}' (the video is self-contained)")
    except ImportError:
        pass
    th = plan.get("thumbnail", {})
    if not isinstance(th, dict) or th.get("scene") not in seen or not isinstance(th.get("time"), (int, float)):
        out.append("plan.json: thumbnail needs a listed scene class and a time in seconds")
    elif not isinstance(th.get("text"), str) or not th["text"].strip() or len(th["text"]) > 40:
        out.append("plan.json: thumbnail text must be 1-40 characters (four words or fewer reads best)")
    return out
