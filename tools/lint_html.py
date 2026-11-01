#!/usr/bin/env python3
"""Fast static lint for explainer HTML (no browser, standard library only, well under a second).

Usage:
  python3 tools/lint_html.py runs/<run>/explainer.html [--run-dir runs/<run>] [--strict] [--json out.json]
  python3 tools/lint_html.py runs/<run>/draft/30-model.html --part      # a draft part before the build

Checks (errors unless noted): math delimiters closed exactly as KaTeX auto-render will split them; \\tag numbers
1..N in order; internal links resolve; no duplicate ids; TOC entries match the headings they point to; every
#ref- link has an entry (uncited entries: warning); figures have captions; no external resources except the
pinned KaTeX 0.16.9 CDN files; required sections (abstract, verification, references); attribution statement
(warning, error with --strict); no leftover build markers; unverified references (warning, error with --strict);
with --run-dir, every script named in the verification table exists under code/.
The full rendering check (KaTeX errors, overlaps, overflow at 390 px) is tools/check_html.js.
Exit status: 0 = no errors, 1 = errors.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

KATEX_BASE = "https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/"
KATEX_FILES = ("katex.min.css", "katex.min.js", "contrib/auto-render.min.js")
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track",
        "wbr"}
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


def split_math(text: str):
    """Split a text node like KaTeX auto-render with delimiters [$$ display, $ inline].

    Returns (segments, unclosed): segments are (kind, content) with kind in text|display|inline;
    unclosed is the remainder that starts with a delimiter that is never closed (None if all closed)."""
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


class Collector(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack: list[tuple[str, dict]] = []
        self.ids: dict[str, int] = {}
        self.dups: list[tuple[str, int]] = []
        self.links: list[tuple[str, int]] = []
        self.external: list[tuple[str, str, int]] = []
        self.katex_urls: list[str] = []
        self.nodes: list[tuple[str, int, bool]] = []  # (text, line, math_allowed)
        self.buf: list[str] = []
        self.buf_line = 0
        self.buf_math = True
        self.headings: dict[str, tuple[int, str, int]] = {}  # target id -> (level, text, line)
        self.heading_order: list[str] = []
        self.toc: list[tuple[str, str, int]] = []
        self.refs: list[str] = []
        self.figures: list[dict] = []
        self.ver_code: list[tuple[str, int]] = []
        self.unknown_tags: list[tuple[str, int]] = []
        self.unverified_refs = 0
        self._cap: list[list] = []  # capture stacks: [kind, key, parts, line]

    # -- helpers
    def _flush(self):
        if self.buf:
            self.nodes.append(("".join(self.buf), self.buf_line, self.buf_math))
            self.buf = []

    def _math_allowed(self) -> bool:
        return not any(t in NO_MATH for t, _ in self.stack)

    def _in(self, tag: str, cls: str | None = None) -> dict | None:
        for t, a in reversed(self.stack):
            if t == tag and (cls is None or cls in (a.get("class") or "").split()):
                return a
        return None

    # -- parser callbacks
    def handle_starttag(self, tag, attrs):
        self._start(tag, attrs, void=tag in VOID)

    def handle_startendtag(self, tag, attrs):
        self._start(tag, attrs, void=True)

    def _start(self, tag, attrs, void):
        self._flush()
        line = self.getpos()[0]
        a = {k: (v if v is not None else "") for k, v in attrs}
        in_svg = self._in("svg") is not None or tag == "svg"
        if tag not in HTML_TAGS and not (in_svg and tag in SVG_TAGS):
            self.unknown_tags.append((tag, line))
        if "id" in a:
            if a["id"] in self.ids:
                self.dups.append((a["id"], line))
            self.ids[a["id"]] = line
        href = a.get("href") or a.get("xlink:href")
        if tag == "a" and href and href.startswith("#"):
            self.links.append((href[1:], line))
        for attr in ("src", "href", "data", "xlink:href"):
            url = a.get(attr, "")
            if tag != "a" and re.match(r"^(https?:)?//", url):
                if tag in ("link", "script") and url.startswith(KATEX_BASE):
                    self.katex_urls.append(url)
                else:
                    self.external.append((tag, url, line))
        if tag == "li" and a.get("id", "").startswith("ref-"):
            self.refs.append(a["id"])
        if tag == "span" and "unverified" in (a.get("class") or "").split():
            self.unverified_refs += 1
        if tag == "figure":
            self.figures.append({"line": line, "caption": False, "graphic": False, "svg_labelled": True})
        if self.figures and self._in("figure") is not None:
            f = self.figures[-1]
            if tag == "figcaption":
                f["caption"] = True
            if tag in ("svg", "img"):
                f["graphic"] = True
                if tag == "svg" and not (a.get("role") == "img" and a.get("aria-label")):
                    f["svg_labelled"] = False
        # captures: headings, toc links, verification-table code
        if tag == "h2":
            sec = self._in("section")
            key = sec.get("id") if sec and sec.get("id") else a.get("id")
            self._cap.append(["h2", key, [], line])
        elif tag in ("h3", "h4") and a.get("id"):
            self._cap.append([tag, a["id"], [], line])
        elif tag == "a" and self._in("nav", "toc") is not None and href and href.startswith("#"):
            self._cap.append(["toc", href[1:], [], line])
        elif tag == "code" and self._in("table", "ver") is not None:
            self._cap.append(["vercode", None, [], line])
        if not void:
            self.stack.append((tag, a))
        self.buf_math = self._math_allowed()

    def handle_endtag(self, tag):
        self._flush()
        for cap in reversed(self._cap):
            kind = cap[0]
            if (kind == tag) or (kind == "toc" and tag == "a") or (kind == "vercode" and tag == "code"):
                self._cap.remove(cap)
                text = norm("".join(cap[2]))
                if kind in ("h2", "h3", "h4") and cap[1]:
                    self.headings[cap[1]] = (int(kind[1]), text, cap[3])
                    self.heading_order.append(cap[1])
                elif kind == "toc":
                    self.toc.append((cap[1], text, cap[3]))
                elif kind == "vercode":
                    self.ver_code.append((text, cap[3]))
                break
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                del self.stack[i:]
                break
        self.buf_math = self._math_allowed()

    def handle_data(self, data):
        if not self.buf:
            self.buf_line = self.getpos()[0]
            self.buf_math = self._math_allowed()
        self.buf.append(data)
        for cap in self._cap:
            cap[2].append(data)

    def close(self):
        super().close()
        self._flush()


SVG_ATTR_DECL = re.compile(r'(?<=\s)([a-z][\w-]*-style)="([^"]*:[^"]*)"')


def lint_svg_attributes(src: str) -> list[dict]:
    """Presentation attributes that hold CSS declarations, such as font-style="fill: color-mix(...); italic" (left by
    the SVG theming before its fix): the label loses its italics and its dark-mode colour."""
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

    # math delimiters and equation tags
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

    # unknown tags (often a '<' inside math: write \lt or &lt;)
    for tag, line in p.unknown_tags:
        add("error", "unknown-tag", f"unexpected tag <{tag}> (a '<' inside math? write \\lt or &lt;)", line)

    # external resources
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

    # leftover markers and TODOs
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

    # ids and links
    for i, line in p.dups:
        add("error", "duplicate-id", f"duplicate id '{i}'", line)
    for target, line in p.links:
        if target not in p.ids:
            add("error", "dangling-link", f"link to #{target} has no target", line)

    # required structure
    for rid in ("abstract", "sec-verification", "sec-references"):
        if rid not in p.ids:
            add("error", "missing-section", f"required element id='{rid}' is missing")
    if "attribution" not in p.ids:
        add("error" if strict else "warning", "attribution",
            "no attribution statement (id='attribution'); the build inserts it from templates/explainer/attribution.html")
    if p.unverified_refs:
        add("error" if strict else "warning", "unverified-refs",
            f"{p.unverified_refs} reference(s) still marked [unverified]")

    # table of contents
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

    # citations and references
    cited = {t for t, _ in p.links if t.startswith("ref-")}
    for r in p.refs:
        if r not in cited:
            add("warning", "uncited-ref", f"reference #{r} is never cited")

    # figures
    for f in p.figures:
        if not f["caption"]:
            add("error", "figure-caption", "figure without <figcaption>", f["line"])
        if not f["graphic"]:
            add("error", "figure-empty", "figure without svg or img", f["line"])
        if not f["svg_labelled"]:
            add("warning", "figure-a11y", "inline svg without role=\"img\" and aria-label", f["line"])

    # verification table -> scripts exist
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
