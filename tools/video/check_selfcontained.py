#!/usr/bin/env python3
"""Self-contained check: a Remaining Action video stands on its own (house rule, deterministic gate).

Usage:
  python3 tools/video/check_selfcontained.py runs/<run> [--stage draft|final]
  python3 tools/video/check_selfcontained.py --layout X.layout.json [--srt X.srt] [--text "..."]   # ad hoc

A viewer has only the video. Nothing in it may point to the companion material (the explainer, its code and data,
files, links) or to a document's numbering, and it carries no equation labels. Checked:
  on-screen text   every Text and MathTex in the layout logs (video/checks/ for drafts, video/renders/ for the final
                   renders, the intro and outro cards included)
  narration        every voiceover block of video/scenes/*.py (the literal text that CI synthesizes)
  captions         the SRT files of the renders and of the assembled video
  chapters         plan.json "chapter" titles and video/final/chapters.json; plan.json thumbnail text
It fails on: file names and paths (.py, .html, code/, ...); the words explainer, document, companion, script, code,
notebook, repository, GitHub, appendix, website; "in the description", "pinned comment"; link, links, linked (but
not robotics usage: "two-link arm", "link length", "each link"); URLs and domains; "§"; references by number
("Eq. 3", "equation (13)", "Figure 2", "Section 6.5", "Table 1", "Theorem 2", "recall equation 2"); equation labels:
\\tag, \\label, \\eqref, \\ref, \\eqno, a trailing "(13)", "(ii)" or "(★)" after an equation, a text item that is only
such a label, circled numbers; and another episode's equation numbers ("equation 4 of episode 2", "episode 2's
Eq. 3"), whatever the setting below; and hard prerequisites ("you must have watched ...", "watch ... first", "won't
make sense unless ..."): a video recaps what it uses, with at most a soft pointer by title ("the episode on ... has
the full story"). Mentions of other episodes of the series, by title or meaning, are not flagged: the words episode,
series, previously and next time pass ("in the episode on Gauss's principle we saw ...").

Equation numbers are one setting, "equation_numbers" in config/video.json (default false): false rejects every
label, the video's own numbering included; true allows the video's own numbering, labels that start at (1) and count
up in order of first appearance (and symbols such as (★)), and references to them, while a label outside that
sequence, such as the explainer's (13), is still a document tag and fails.

The numbers on screen still come from the companion scripts (the gates check that); only showing or saying where
they come from is forbidden. Third-party sources (a paper's authors and title) are not companion material.
Allowed phrases: config/video.json "self_contained"."allow" (regular expressions, removed before matching).
Writes review/design/<stage>/check_selfcontained.json and .md; exit status 1 when anything is found.
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
from _common import CONFIG, load_json, rel, resolve_run, utc_now, write_json  # noqa: E402
import voice_script as VS  # noqa: E402

HELPERS = {"common.py", "voice.py", "reading_model.py"}
LABEL = (r"(?:\d{1,3}(?:\.\d{1,2})?[a-z]?|[ivx]{1,4}|[IVX]{1,4}|\*{1,3}|[★☆†‡#]"
         r"|\\(?:star|ast|dagger|ddagger|bigstar|S)\b)")
NUMWORDS = ["one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve",
            "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen", "twenty"]
NUMWORD = "|".join(NUMWORDS)
DEFAULT_ALLOW = [r"\b(?:two|three|four|five|six|seven|n|k|multi|single|\d+)-link\b",
                 r"\blinks? (?:lengths?|mass(?:es)?|angles?|frames?|inertias?|\d+)\b",
                 r"\b(?:first|second|third|each|every|end|distal|proximal|lower|upper|rigid|robot|arm) links?\b",
                 r"\bcolou?r code\b"]

# (rule, regex): plain text (narration, captions, chapters, on-screen Text, \text{} inside math)
PLAIN = [
    ("file name", re.compile(r"\b[\w-]+(?:\.[\w-]+)*\.(?:py|ipynb|html?|json|md|npz|csv|txt|svg|log|toml|ya?ml|pdf|tex)"
                             r"\b", re.I)),
    ("folder path", re.compile(r"(?<![\w/])(?:code|video|runs|review|tools|templates|series|sources|examples|draft|data|logs?"
                               r"|notes?|scripts?|merged)/", re.I)),
    ("path", re.compile(r"\b[\w.-]+/[\w.-]+/[\w./-]+")),
    ("URL", re.compile(r"https?://|\bwww\.|\b[\w-]+\.(?:com|org|net|io|dev|ai|edu|gov|app|page|site|me)\b", re.I)),
    ("material outside the video", re.compile(
        r"\b(?:explainers?|documents?|companion|scripts?|code|notebooks?|repositor(?:y|ies)|repo|github|appendix"
        r"|appendices|website|webpage|web page|html|pdf|source files?)\b", re.I)),
    ("the video's description", re.compile(r"\b(?:in|see|check|from) the description\b|\bdescription (?:below|box)\b"
                                           r"|\bpinned comment\b", re.I)),
    ("link", re.compile(r"\blink(?:s|ed|ing)?\b", re.I)),
    ("hard prerequisite", re.compile(
        r"\byou\s+(?:must|need\s+to|have\s+to|should)\s+(?:have\s+)?(?:watched|watch|seen|see)\b"
        r"|\bmake\s+sure\s+(?:you(?:'|’)ve|you\s+have)\s+(?:watched|seen)\b|\bwatch\s+(?:[\w'’]+\s+){0,6}?first\b"
        r"|\b(?:won(?:'|’)t|will\s+not|doesn(?:'|’)t|does\s+not)\s+make\s+(?:much\s+)?sense\s+(?:unless|without)\b"
        r"|\bgo\s+back\s+and\s+watch\b", re.I)),
    ("section sign", re.compile("§")),
    ("numbered reference", re.compile(r"\b(?:eqs?|eqn|fig|figs|sec|secs|tab|tbl|thm|lem|prop|cor|def)\.\s*\(?\s*\d",
                                      re.I)),
    ("numbered reference", re.compile(
        rf"\b(?:figures?|sections?|subsections?|chapters?|tables?|theorems?|lemmas?|propositions?|corollar(?:y|ies)"
        rf"|definitions?|pages?)\s*\(?\s*(?:\d+(?:\.\d+)*|[ivx]{{1,4}}\b|(?:{NUMWORD})\b)", re.I)),
]
# equation references by number: "equation 2", "Eq. (13)", "inequality (16)"; the number decides the label policy
EQREF = [re.compile(rf"\b(?:equations?|formulas?|formulae)\s*\(?\s*(\d+(?:\.\d+)*[a-z]?|[ivx]{{1,4}}|{NUMWORD})\b",
                    re.I),
         re.compile(r"\b(?:expressions?|identit(?:y|ies)|inequalit(?:y|ies)|conditions?|relations?)\s*\(?\s*"
                    r"(\d+(?:\.\d+)*[a-z]?|[ivx]{1,4})\b\)?", re.I),
         re.compile(r"\beqn?s?\.\s*\(?\s*(\d+(?:\.\d+)*[a-z]?)", re.I)]
PLAIN_LABEL = re.compile(rf"(?<![\w)\]}}′'’^_])\(\s*({LABEL})\s*\)")
CIRCLED = re.compile("[\u2460-\u2473\u24ea\u2776-\u2793]")
# another episode's equation numbers, always rejected: "equation 4 of episode 2", "Eq. (4) in the previous episode",
# "result 3 from the episode on ...", "(4) from part two", "episode 2's equation 4" (not "... of this episode")
EQWORD = (r"(?:equations?|eqns?\.?|eqs?\.|formulas?|formulae|results?|inequalit(?:y|ies)|identit(?:y|ies)"
          r"|expressions?|conditions?|relations?)")
NUMREF = rf"(?:\(\s*{LABEL}\s*\)|\d+(?:\.\d+)*[a-z]?\b|[ivx]{{1,4}}\b|(?:{NUMWORD})\b)"
EPISODE = r"(?:episodes?|parts?|videos?|lectures?|instal{1,2}ments?)\b"
OTHER = r"(?:of|in|from)\s+(?!this\b|our\b)(?:the\s+)?(?:[\w'’-]+\s+){0,3}?"
EPISODE_N = rf"{EPISODE}(?:\s+(?:\d+|{NUMWORD})\b)?"
CROSS_EPISODE = [re.compile(rf"\b{EQWORD}\s*{NUMREF}\s*(?:\w+\s+){{0,2}}?{OTHER}{EPISODE_N}", re.I),
                 re.compile(rf"\(\s*{LABEL}\s*\)\s*{OTHER}{EPISODE_N}", re.I),
                 re.compile(rf"(?<!\bthis )(?<!\bour )\b{EPISODE}(?:\s+(?:\d+|{NUMWORD}))?['’]s\s+(?:\w+\s+)?"
                            rf"{EQWORD}\s*{NUMREF}", re.I)]
# LaTeX
MATH_CMD = re.compile(r"\\(label|eqref|ref|eqno|leqno|notag|nonumber|textcircled)\b")
MATH_TAG = re.compile(r"\\tag\*?\{([^{}]*)\}")
MATH_TRAIL = re.compile(rf"(?:\\q?quad|\\hfill|\\enspace|\\[,;:! ]|~|\\text\{{\s*)\s*\(\s*({LABEL})\s*\)\s*\}}?\s*$")
MATH_WHOLE = re.compile(rf"^\s*(?:\\text\{{)?\s*\(\s*({LABEL})\s*\)\s*\}}?\s*$")
TEXT_CMD = re.compile(r"\\(?:text|textrm|textit|textbf|textsf|mathrm|operatorname)\{([^{}]*)\}")


def settings(path: Path | None = None) -> dict:
    v = load_json(path or CONFIG / "video.json")
    sc = v.get("self_contained", {})
    return {"equation_numbers": bool(v.get("equation_numbers", False)),
            "allow": [re.compile(p, re.I) for p in sc.get("allow", DEFAULT_ALLOW)]}


def _blank_allowed(text: str, st: dict) -> str:
    for rx in st["allow"]:
        text = rx.sub(lambda m: " " * len(m.group()), text)
    return text


def _numval(v: str):
    v = v.strip().lower()
    if v.isdigit():
        return int(v)
    return NUMWORDS.index(v) + 1 if v in NUMWORDS else None


def scan_plain(text: str, st: dict) -> list[dict]:
    """Findings in plain text: {rule, match, label?}."""
    t = _blank_allowed(text or "", st)
    spans: list[list[int]] = []
    for a, b in sorted((m.start(), m.end()) for rx in CROSS_EPISODE for m in rx.finditer(t)):
        if spans and a <= spans[-1][1]:
            spans[-1][1] = max(b, spans[-1][1])
        else:
            spans.append([a, b])

    def free(m):  # not inside a cross-episode reference, which is reported once, as a whole
        return not any(a <= m.start() < b for a, b in spans)

    out = [{"rule": "cross-episode equation number", "match": t[a:b].strip()} for a, b in spans]
    out += [{"rule": r, "match": m.group().strip()} for r, rx in PLAIN for m in rx.finditer(t) if free(m)]
    out += [{"rule": "circled number", "match": m.group(), "label": m.group()} for m in CIRCLED.finditer(t)
            if free(m)]
    out += [{"rule": "equation label", "match": m.group(), "label": m.group(1)} for m in PLAIN_LABEL.finditer(t)
            if free(m)]
    seen = set()
    for rx in EQREF:
        for m in rx.finditer(t):
            if m.start() not in seen and free(m):
                seen.add(m.start())
                out.append({"rule": "equation reference", "match": m.group().strip(), "ref": m.group(1)})
    return out


def scan_math(tex: str, st: dict) -> list[dict]:
    """Findings in a LaTeX string: tags, labels, cross-references, and plain rules inside \\text{...}."""
    tex = tex or ""
    out = [{"rule": "equation label command", "match": "\\" + m.group(1)} for m in MATH_CMD.finditer(tex)]
    out += [{"rule": "equation label", "match": m.group(), "label": m.group(1).strip()} for m in MATH_TAG.finditer(tex)]
    m = MATH_WHOLE.search(tex) or MATH_TRAIL.search(tex)
    if m:
        out.append({"rule": "equation label", "match": m.group().strip(), "label": m.group(1)})
    for inner in TEXT_CMD.findall(tex):
        out += [f for f in scan_plain(inner, st) if f["rule"] not in ("equation label",)]
    return out


def srt_text(path: Path) -> str:
    keep = [ln for ln in path.read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.strip().isdigit() and "-->" not in ln]
    return " ".join(keep)


def _scene_order(plan: dict) -> dict[str, int]:
    order = {}
    for i, s in enumerate(plan.get("scenes", [])):
        order[s.get("class", "")] = i
        order[s.get("file", "")] = i
    return order


def collect(run: Path, stage: str) -> list[dict]:
    """Every piece of viewer-facing text of the run at this stage: {source, where, text, kind, order}."""
    items = []
    pp = run / "video" / "plan.json"
    plan = json.loads(pp.read_text(encoding="utf-8")) if pp.exists() else {}
    order = _scene_order(plan)
    for f in sorted((run / "video" / "scenes").glob("*.py")):
        if f.name in HELPERS:
            continue
        for i, (_, text) in enumerate(VS.blocks(f)):
            if text:
                items.append({"source": "narration", "where": f"{f.name}, block {i + 1}", "text": text,
                              "kind": "plain", "order": (order.get(f.name, 999), 1, i)})
    for i, s in enumerate(plan.get("scenes", [])):
        if s.get("chapter"):
            items.append({"source": "chapter", "where": f"plan.json scenes[{i}]", "text": s["chapter"],
                          "kind": "plain", "order": (i, 0, 0)})
    if isinstance(plan.get("thumbnail"), dict) and plan["thumbnail"].get("text"):
        items.append({"source": "thumbnail", "where": "plan.json thumbnail", "text": plan["thumbnail"]["text"],
                      "kind": "plain", "order": (999, 0, 0)})
    folder = run / "video" / ("checks" if stage == "draft" else "renders")
    for lp in sorted(folder.glob("*.layout.json")):
        log_all = json.loads(lp.read_text(encoding="utf-8"))
        for scene, log in log_all.get("scenes", {}).items():
            for item in log.get("timeline", []):
                if item.get("axis"):
                    continue
                t = item.get("events", [[0.0]])[0][0] if item.get("events") else 0.0
                items.append({"source": "screen", "where": f"{scene} t={t:.1f}s", "text": item.get("content", ""),
                              "kind": "math" if item.get("kind") == "math" else "plain",
                              "order": (order.get(scene, 999), 2, t)})
    srts = sorted(folder.glob("*.srt"))
    if stage == "final":
        srts += sorted((run / "video" / "final").glob("*.srt"))
    for p in srts:
        items.append({"source": "captions", "where": rel(p), "text": srt_text(p), "kind": "plain",
                      "order": (998, 0, 0)})
    cp = run / "video" / "final" / "chapters.json"
    if stage == "final" and cp.exists():
        for i, c in enumerate(json.loads(cp.read_text(encoding="utf-8")).get("chapters", [])):
            items.append({"source": "chapter", "where": f"chapters.json [{i}]", "text": c.get("title", ""),
                          "kind": "plain", "order": (997, 0, i)})
    return items


def explainer_headings(run: Path) -> set[str]:
    """Normalised heading titles of the run's explainer.html (without their numbers), for the chapter rule."""
    page = run / "explainer.html"
    if not page.exists():
        return set()
    import lint_html
    c = lint_html.Collector()
    c.feed(page.read_text(encoding="utf-8"))
    c.close()
    return {_norm(re.sub(r"^\d+(?:\.\d+)*\.?\s+", "", text)) for _, (_, text, _) in c.headings.items()}


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", s.replace("$", "").lower()).strip()


def label_policy(findings: list[dict], equation_numbers: bool) -> list[dict]:
    """Apply "equation_numbers": with false every label and numbered equation reference fails; with true the video's
    own sequence (1), (2), ... in order of first appearance on screen, and symbols, pass, as do references to them."""
    labels = [f for f in findings if "label" in f or "ref" in f]
    rest = [f for f in findings if "label" not in f and "ref" not in f]
    if not equation_numbers:
        for f in labels:
            f["detail"] = ("equation labels and numbered references are off (config/video.json equation_numbers is "
                           "false): show the equation again or name it by its meaning")
        return rest + labels
    keep, ok, seq = [], set(), 0
    for f in sorted([x for x in labels if "label" in x and x["source"] == "screen"], key=lambda x: x["order"]):
        v = _numval(f["label"])
        if v is None or v in ok:
            continue                                   # a symbol, roman numeral or a repeat of the video's own label
        if v == seq + 1:
            seq = v
            ok.add(v)
            continue
        f["detail"] = (f"label ({f['label']}) is not the video's own numbering: it must start at (1) and count up in "
                       "order of first appearance (a document's number is a tag the viewer cannot look up)")
        keep.append(f)
    for f in labels:
        if f["source"] == "screen" and "label" in f:
            continue
        v = _numval(f.get("label") or f.get("ref") or "")
        if f["source"] in ("chapter", "thumbnail"):
            f["detail"] = "chapter and thumbnail texts carry no equation labels"
            keep.append(f)
        elif v is None and f.get("label"):
            continue
        elif v not in ok:
            f["detail"] = f"refers to equation {f.get('label') or f.get('ref')}, which the video never labels"
            keep.append(f)
    return rest + keep


def check_items(items: list[dict], st: dict) -> list[dict]:
    findings = []
    for it in items:
        found = scan_math(it["text"], st) if it["kind"] == "math" else scan_plain(it["text"], st)
        for f in found:
            findings.append(dict(f, source=it["source"], where=it["where"], order=it["order"],
                                 excerpt=" ".join(it["text"].split())[:90]))
    findings = label_policy(findings, st["equation_numbers"])
    uniq, seen = [], set()
    for f in sorted(findings, key=lambda x: (x["order"], x["rule"])):
        k = (f["source"], f["where"], f["rule"], f["match"])
        if k not in seen:
            seen.add(k)
            uniq.append(f)
    return uniq


def check(run: Path, stage: str, st: dict | None = None) -> list[dict]:
    items = collect(run, stage)
    findings = check_items(items, st or settings())
    heads = explainer_headings(run)
    for it in items:                                   # chapters are the video's own titles, not the document's
        if it["source"] == "chapter" and _norm(it["text"]) in heads:
            findings.append({"rule": "explainer heading as chapter", "match": it["text"], "source": "chapter",
                             "where": it["where"], "order": it["order"], "excerpt": it["text"],
                             "detail": "write the chapter title for viewers (plan.json \"chapter\")"})
    return findings


def describe(f: dict) -> str:
    extra = f" ({f['detail']})" if f.get("detail") else ""
    return f"{f['source']} {f['where']}: {f['rule']} '{f['match']}'{extra}"


def write_report(run: Path, stage: str, findings: list[dict]) -> Path:
    out = run / "review" / "design" / stage
    out.mkdir(parents=True, exist_ok=True)
    clean = [{k: v for k, v in f.items() if k != "order"} for f in findings]
    write_json(out / "check_selfcontained.json", {"schema_version": 1, "stage": stage, "checked_at": utc_now(),
                                                  "passed": not findings, "findings": clean})
    md = [f"# Self-contained check ({stage})", "",
          f"{len(findings)} finding(s). The video must not point to the explainer, code, files or links, nor carry "
          "equation labels (config/video.json equation_numbers) or another episode's equation numbers.", ""]
    if findings:
        md += ["| Source | Where | Rule | Match | Text |", "|---|---|---|---|---|"]
        md += [f"| {f['source']} | {f['where']} | {f['rule']} | {f['match'].replace('|', '/')} | "
               f"{f['excerpt'].replace('|', '/')} |" for f in findings]
    (out / "check_selfcontained.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    return out / "check_selfcontained.md"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run", nargs="?")
    ap.add_argument("--stage", choices=["draft", "final"], default="draft")
    ap.add_argument("--layout", action="append", default=[])
    ap.add_argument("--srt", action="append", default=[])
    ap.add_argument("--text", action="append", default=[])
    a = ap.parse_args()
    st = settings()
    if a.run:
        run = resolve_run(a.run)
        findings = check(run, a.stage, st)
        md = write_report(run, a.stage, findings)
        for f in findings:
            print(f"ERROR   {describe(f)}")
        print(f"check_selfcontained ({a.stage}): {'ok' if not findings else 'FAIL'} ({len(findings)} finding(s)); "
              f"{rel(md)}")
        return 1 if findings else 0
    items = [{"source": "text", "where": f"--text {i + 1}", "text": t, "kind": "plain", "order": (0, 0, i)}
             for i, t in enumerate(a.text)]
    for p in a.srt:
        items.append({"source": "captions", "where": p, "text": srt_text(Path(p)), "kind": "plain",
                      "order": (998, 0, 0)})
    for lp in a.layout:
        for scene, log in json.loads(Path(lp).read_text(encoding="utf-8")).get("scenes", {}).items():
            for item in log.get("timeline", []):
                if not item.get("axis"):
                    t = item.get("events", [[0.0]])[0][0] if item.get("events") else 0.0
                    items.append({"source": "screen", "where": f"{scene} t={t:.1f}s", "text": item.get("content", ""),
                                  "kind": "math" if item.get("kind") == "math" else "plain", "order": (0, 2, t)})
    findings = check_items(items, st)
    for f in findings:
        print(f"ERROR   {describe(f)}")
    print(f"check_selfcontained: {'ok' if not findings else 'FAIL'} ({len(findings)} finding(s))")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
