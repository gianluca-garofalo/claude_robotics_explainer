#!/usr/bin/env python3
"""Static lint of an explainer page or draft part: math, equation tags, links, ids, contents, figures, resources.

Usage:
  python3 tools/lint_html.py runs/<run>/explainer.html [--run-dir runs/<run>] [--strict] [--json out.json]
  python3 tools/lint_html.py runs/<run>/draft/30-model.html --part
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

if __name__ == "__main__":
    import _common  # noqa: F401  (runs the script in .venv; not on import: the edit hook has already read its stdin)
from bs4 import BeautifulSoup, NavigableString, Tag
from bs4.element import PreformattedString

KATEX_BASE = "https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/"
KATEX_FILES = ("katex.min.css", "katex.min.js", "contrib/auto-render.min.js")
NO_MATH = {"script", "style", "svg", "code", "pre", "textarea", "math", "title"}
HTML_TAGS = set("""html head body meta link title style script nav article header footer section div span p a em strong
b i u s sub sup small br wbr hr ol ul li dl dt dd table thead tbody tfoot tr th td caption colgroup col figure
figcaption img h1 h2 h3 h4 h5 h6 blockquote code pre kbd samp var abbr cite q mark time details summary video audio
source track iframe noscript main aside label button input textarea select option template picture del ins""".split())
SVG_TAGS = set("""svg g defs path line polyline polygon rect circle ellipse text tspan textpath marker clippath mask
use symbol lineargradient radialgradient stop pattern image title desc style metadata foreignobject filter
fegaussianblur feoffset feblend feflood fecomposite femerge femergenode switch a""".split())
MARKER_RE = re.compile(r"\[\[(eq|fig|figdef|sec|cite|citet):[^\]]*\]\]|<!--SVG:|<!--REFERENCES-->")
TODO_RE = re.compile(r"\b(TODO|FIXME|XXX|TBD)\b")
SCRIPT_PATH_RE = re.compile(r"^[\w./-]+\.(py|js|sh|jl|m|ipynb|toml)$")


def parse(html: str) -> BeautifulSoup:
    """The page as a tree; whitespace-only text stays as written, so the lines of text can be counted."""
    return BeautifulSoup(html, "html.parser", preserve_whitespace_tags={BeautifulSoup.ROOT_TAG_NAME})


def text(el: Tag) -> str:
    """The text under el, without comments."""
    return "".join(s for s in el.descendants
                   if isinstance(s, NavigableString) and not isinstance(s, PreformattedString))


def split_math(text: str):
    """Split a text node like KaTeX auto-render with delimiters [$$ display, $ inline]: (segments, unclosed), segments
    (kind, content) with kind text|display|inline, unclosed the rest from a delimiter never closed (None if all are)."""
    segs = []
    while True:
        m = re.search(r"\$\$|\$", text)
        if not m:
            break
        idx = m.start()
        if idx > 0:
            segs.append(("text", text[:idx]))
            text = text[idx:]
        left = "$$" if text.startswith("$$") else "$"
        end = _find_end(left, text, len(left))
        if end == -1:
            if text:
                segs.append(("text", text))
            return segs, text
        segs.append(("display" if left == "$$" else "inline", text[len(left):end]))
        text = text[end + len(left):]
    if text:
        segs.append(("text", text))
    return segs, None


def _find_end(delim: str, text: str, start: int) -> int:
    i, level = start, 0
    while i < len(text):
        if level <= 0 and text.startswith(delim, i):
            return i
        ch = text[i]
        if ch == "\\":
            i += 1
        elif ch == "{":
            level += 1
        elif ch == "}":
            level -= 1
        i += 1
    return -1


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def _ancestor(el: Tag, name: str, cls: str | None = None) -> Tag | None:
    return next((p for p in el.parents if p.name == name and (cls is None or cls in p.get("class", ()))), None)


def _text_runs(soup: BeautifulSoup, src: str) -> list[tuple[str, int, bool]]:
    """(text, line, math allowed) of the text between two tags; comments do not end a run."""
    lines, pending, runs, last = {}, [], [], None
    for el in [*soup.descendants, None]:
        if el is None or isinstance(el, Tag):     # only tags carry a line: count back through the strings before it
            line = src.count("\n") + 1 if el is None else el.sourceline
            for s in reversed(pending):
                line -= s.count("\n")
                lines[id(s)] = line
            pending, last = [], None
            continue
        pending.append(el)
        if isinstance(el, PreformattedString):
            continue
        if last is not None and last.parent is el.parent and last.next_sibling is not el:
            runs[-1][0] += el                     # only comments since the last string (adjacent ones had an end tag)
        else:
            runs.append([str(el), el, not any(p.name in NO_MATH for p in el.parents)])
        last = el
    return [(t, lines[id(s)], allowed) for t, s, allowed in runs]


class Collector:
    """What lint() checks, from one parse of the page: feed() it, then close()."""

    def __init__(self):
        self._src: list[str] = []

    def feed(self, data: str):
        self._src.append(data)

    def close(self):
        src = "".join(self._src)
        soup = parse(src)
        self.nodes = _text_runs(soup, src)
        self.ids: dict[str, int] = {}
        self.dups, self.links, self.external, self.katex_urls, self.refs = [], [], [], [], []
        self.headings: dict[str, tuple[int, str, int]] = {}     # target id -> (level, text, line)
        self.heading_order, self.toc, self.figures, self.ver_code, self.unknown_tags = [], [], [], [], []
        self.unverified_refs = 0
        for t in soup.find_all(True):
            name, line = t.name, t.sourceline
            if name not in HTML_TAGS and not (name in SVG_TAGS and (name == "svg" or _ancestor(t, "svg"))):
                self.unknown_tags.append((name, line))
            if t.has_attr("id"):
                if t["id"] in self.ids:
                    self.dups.append((t["id"], line))
                self.ids[t["id"]] = line
            href = t.get("href") or t.get("xlink:href")
            if name == "a" and href and href.startswith("#"):
                self.links.append((href[1:], line))
                if _ancestor(t, "nav", "toc"):
                    self.toc.append((href[1:], norm(text(t)), line))
            for url in ([] if name == "a" else [t.get(k, "") for k in ("src", "href", "data", "xlink:href")]):
                if re.match(r"^(https?:)?//", url):
                    if name in ("link", "script") and url.startswith(KATEX_BASE):
                        self.katex_urls.append(url)
                    else:
                        self.external.append((name, url, line))
            if name == "li" and t.get("id", "").startswith("ref-"):
                self.refs.append(t["id"])
            if name == "span" and "unverified" in t.get("class", ()) and _ancestor(t, "ol", "references"):
                self.unverified_refs += 1                    # the build's marker, not an evidence box's status
            if name == "figure":
                svgs = t.find_all("svg")
                self.figures.append({"line": line, "caption": t.find("figcaption") is not None,
                                     "graphic": bool(svgs) or t.find("img") is not None,
                                     "svg_labelled": all(s.get("role") == "img" and s.get("aria-label") for s in svgs)})
            if name in ("h2", "h3", "h4"):
                sec = _ancestor(t, "section") if name == "h2" else None    # an h2 is known by its section's id
                key = (sec.get("id") if sec else None) or t.get("id")
                if key:
                    self.headings[key] = (int(name[1]), norm(text(t)), line)
                    self.heading_order.append(key)
            if name == "code" and _ancestor(t, "table", "ver"):
                self.ver_code.append((norm(text(t)), line))


SVG_ATTR_DECL = re.compile(r'(?<=\s)([a-z][\w-]*-style)="([^"]*:[^"]*)"')


def lint_svg_attributes(src: str) -> list[dict]:
    """Presentation attributes holding CSS declarations (font-style="fill: ...; italic"): the label loses its style."""
    return [{"level": "error", "code": "svg-attribute", "line": src.count("\n", 0, m.start()) + 1,
             "message": f'{m.group(1)}="{m.group(2)[:50]}..." holds CSS declarations: they belong in the style '
                        f'attribute, and {m.group(1)} keeps only its own value'}
            for m in SVG_ATTR_DECL.finditer(src)]


def lint(path: Path, run_dir: Path | None = None, strict: bool = False, part: bool = False) -> list[dict]:
    src = path.read_text(encoding="utf-8")
    issues: list[dict] = []

    def add(level, code, msg, line=None):
        issues.append({"level": level, "code": code, "line": line, "message": msg})

    p = Collector()
    p.feed(src)
    p.close()

    tags, math_count = [], 0
    for text, line, allowed in p.nodes:
        if "$" not in text:
            continue
        segs, unclosed = split_math(text)
        if not allowed:
            continue
        for kind, content in segs:
            if kind != "text":
                math_count += 1
                for t in re.findall(r"\\tag\*?\{([^}]*)\}", content):
                    tags.append((t, line))
                if kind == "inline" and "\\tag" in content:
                    add("error", "tag-inline", "\\tag inside inline math $...$ (use $$...$$)", line)
        if unclosed is not None:
            snippet = norm(unclosed)[:70]
            add("error", "math-unclosed", f"unclosed math delimiter; KaTeX will leave raw '$' here: {snippet!r}", line)
    if not part:
        nums = []
        for t, line in tags:
            if not t.isdigit():
                add("error", "tag-format", f"equation tag {{{t}}} is not a plain number (build markers resolved?)", line)
            else:
                nums.append((int(t), line))
        for i, (n, line) in enumerate(nums, 1):
            if n != i:
                add("error", "tag-sequence", f"equation tag ({n}) found where ({i}) was expected", line)
                break

    for tag, line in p.unknown_tags:
        add("error", "unknown-tag", f"unexpected tag <{tag}> (a '<' inside math? write \\lt or &lt;)", line)
    for tag, url, line in p.external:
        add("error", "external-resource", f"<{tag}> loads {url}: explainers are self-contained (original figures, "
                                          "inline SVG or files under the run); only the pinned KaTeX CDN is allowed", line)
    issues += lint_svg_attributes(src)
    other_katex = re.findall(r"katex@(?!0\.16\.9/)[\w.\-]+", src)
    if other_katex:
        add("error", "katex-version", f"KaTeX version must be 0.16.9 (found {sorted(set(other_katex))})")
    if math_count and not part:
        for f in KATEX_FILES:
            if KATEX_BASE + f not in p.katex_urls:
                add("error", "katex-missing", f"math present but {KATEX_BASE + f} is not loaded")

    for m in MARKER_RE.finditer(src):
        if not part:
            line = src.count("\n", 0, m.start()) + 1
            add("error", "build-marker", f"unresolved build marker {m.group(0)[:40]!r} (run tools/build_explainer.py)", line)
    if part:
        for m in re.finditer(r"\[\[([a-z]+):([^\]]*)\]\]", src):
            if m.group(1) not in ("eq", "fig", "figdef", "sec", "cite", "citet") or not re.match(r"^[\w-]+$", m.group(2)):
                add("error", "marker-syntax", f"malformed marker {m.group(0)!r}", src.count("\n", 0, m.start()) + 1)
    for text, line, allowed in p.nodes:
        if allowed and TODO_RE.search(text):
            add("error" if strict else "warning", "todo", f"placeholder text: {norm(text)[:60]!r}", line)

    if part:
        return issues

    for i, line in p.dups:
        add("error", "duplicate-id", f"duplicate id '{i}'", line)
    for target, line in p.links:
        if target not in p.ids:
            add("error", "dangling-link", f"link to #{target} has no target", line)

    for rid in ("abstract", "sec-verification", "sec-references"):
        if rid not in p.ids:
            add("error", "missing-section", f"required element id='{rid}' is missing")
    if "attribution" not in p.ids:
        add("error" if strict else "warning", "attribution",
            "no attribution statement (id='attribution'); the build inserts it from templates/explainer/attribution.html")
    if p.unverified_refs:
        add("error" if strict else "warning", "unverified-refs",
            f"{p.unverified_refs} reference(s) still marked [unverified]")

    if not p.toc:
        add("error", "toc-missing", "no <nav class=\"toc\"> entries")
    toc_targets = set()
    for target, text, line in p.toc:
        toc_targets.add(target)
        if target not in p.ids:
            continue  # reported as dangling link
        h = p.headings.get(target)
        if h is None:
            if target != "abstract":
                add("error", "toc-target", f"TOC entry '{text}' points to #{target}, which is not a heading", line)
            continue
        if norm(h[1]) != norm(text):
            add("error", "toc-text", f"TOC entry '{text}' differs from heading '{h[1]}'", line)
    for hid in p.heading_order:
        level = p.headings[hid][0]
        if level in (2, 3) and hid not in toc_targets:
            add("error", "toc-incomplete", f"heading '{p.headings[hid][1]}' (#{hid}) is not in the TOC",
                p.headings[hid][2])

    cited = {t for t, _ in p.links if t.startswith("ref-")}
    for r in p.refs:
        if r not in cited:
            add("warning", "uncited-ref", f"reference #{r} is never cited")

    for f in p.figures:
        if not f["caption"]:
            add("error", "figure-caption", "figure without <figcaption>", f["line"])
        if not f["graphic"]:
            add("error", "figure-empty", "figure without svg or img", f["line"])
        if not f["svg_labelled"]:
            add("warning", "figure-a11y", "inline svg without role=\"img\" and aria-label", f["line"])

    if run_dir is not None:
        code = run_dir / "code"
        names = {q.relative_to(code).as_posix() for q in code.rglob("*") if q.is_file()} if code.is_dir() else set()
        bases = {Path(n).name for n in names}
        for text, line in p.ver_code:
            t = text.replace("\u200b", "").strip()
            if not SCRIPT_PATH_RE.match(t):
                continue
            if t not in names and Path(t).name not in bases:
                add("error", "ver-script-missing", f"verification table names {t}, which is not under code/", line)
    return issues


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("file")
    ap.add_argument("--run-dir")
    ap.add_argument("--strict", action="store_true", help="placeholders, missing attribution, unverified refs are errors")
    ap.add_argument("--part", action="store_true", help="lint a draft part (before the build)")
    ap.add_argument("--json", help="write the issues as JSON to this file")
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()
    path = Path(a.file)
    if not path.exists():
        print(f"error: {a.file} not found", file=sys.stderr)
        return 1
    issues = lint(path, Path(a.run_dir) if a.run_dir else None, a.strict, a.part)
    errors = [i for i in issues if i["level"] == "error"]
    if a.json:
        Path(a.json).write_text(json.dumps({"file": a.file, "issues": issues}, indent=2) + "\n", encoding="utf-8")
    if not a.quiet or errors:
        for i in issues:
            loc = f":{i['line']}" if i["line"] else ""
            print(f"{i['level'].upper():7} {a.file}{loc} [{i['code']}] {i['message']}")
    print(f"lint_html: {'FAIL' if errors else 'ok'} ({len(errors)} error(s), {len(issues) - len(errors)} warning(s)) {a.file}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
