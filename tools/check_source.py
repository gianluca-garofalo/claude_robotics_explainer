#!/usr/bin/env python3
"""Check a source folder (explainer.html, code/, checks.toml) before series are planned or episodes made from it.

Usage:
  python3 tools/check_source.py sources/<name> [more folders] [--render] [--strict] [--json OUT]
  python3 tools/check_source.py --all [--sources-dir DIR]
  python3 tools/check_source.py sources/<name> --strip-external-scripts [--write]
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import REPO, rel, write_json  # noqa: E402
import lint_html  # noqa: E402
from bs4 import Tag  # noqa: E402
from bs4.element import PreformattedString  # noqa: E402

KATEX_HOST = urlparse(lint_html.KATEX_BASE).hostname        # cdn.jsdelivr.net
# matched in the source, not the tree: strip_scripts cuts the tags out and keeps every other byte
SCRIPT_TAG_RE = re.compile(r"<script\b[^>]*?\bsrc\s*=\s*([\"'])(.*?)\1[^>]*>\s*</script\s*>", re.I | re.S)
SCRIPT_REF_RE = re.compile(r"(?<![\w./-])((?:\./)?(?:[\w-]+/)*[\w-]+\.py)(?![\w])")
BLOCKS = {"p", "li", "td", "th", "dd", "dt", "figcaption", "caption", "pre", "blockquote", "h1", "h2", "h3", "h4",
          "h5", "h6", "summary"}
SKIP = {"script", "style", "svg", "head", "title", "math"}
SECTION_REF_RE = re.compile(r"\bSections?\s+((?:\d+(?:\.\d+)*)(?:\s*(?:,|and|&|[-‐-―]|&ndash;)\s*\d+(?:\.\d+)*)*)")
FIGURE_RE = re.compile(r"\bFig(?:ures?|s?\.)\s*((?:\d+)(?:\s*(?:,|and|&)\s*\d+)*)", re.I)
NUMBER_RE = re.compile(r"(?<![\w.])\d+(?:\.\d+)*(?![\w.])")


class Report:
    def __init__(self, source: Path):
        self.source = source
        self.errors: list[dict] = []
        self.warnings: list[dict] = []
        self.facts: dict = {}

    def err(self, code: str, msg: str, fix: str = ""):
        self.errors.append({"code": code, "message": msg, "fix": fix})

    def warn(self, code: str, msg: str, fix: str = ""):
        self.warnings.append({"code": code, "message": msg, "fix": fix})


# --------------------------------------------------------------------------- the explainer as text blocks
def read_blocks(html: str) -> tuple[list[dict], list[dict], set[int]]:
    """(text blocks with their section and .py links, rows of the verification table, figure numbers)."""
    blocks, rows, figures = [], [], set()
    section = ""

    def walk(el, ver: bool, block: dict | None, row: dict | None) -> str:
        nonlocal section
        out = []
        for c in el.children:
            if not isinstance(c, Tag):
                if not isinstance(c, PreformattedString):
                    out.append(c.replace("\u00a0", " ").translate({0x2060: None, 0x200b: None, 0xfeff: None}))
                continue
            name, href = c.name, c.get("href") or ""
            if name in SKIP:
                continue
            if name == "a" and block is not None and href.endswith(".py") and not re.match(r"^[a-z]+://", href):
                block["hrefs"].append(href)
            in_ver = ver or (name == "section" and c.get("id") == "sec-verification")
            own = {"section": section, "hrefs": []} if name in BLOCKS else None
            new_row = {"cells": [], "section": section} if name == "tr" and in_ver else None
            t = walk(c, in_ver, own or block, new_row or row)
            if own is not None:
                t = " ".join(t.split())
                blocks.append({"text": t, "section": own["section"], "hrefs": own["hrefs"]})
                if row is not None and name in ("td", "th"):
                    row["cells"].append(t)
                t = f" {t} "                       # a nested block's text also belongs to its parent
            if name in ("h2", "h3"):
                head = " ".join(t.split())
                m = re.match(r"^(\d+(?:\.\d+)*)\.?\s", head)
                section = m.group(1) if m else (head.split(".")[0] if head.startswith("Appendix") else head[:40])
            if name == "figcaption" and (m := re.match(r"\s*Figure\s+(\d+)", t)):
                figures.add(int(m.group(1)))
            if new_row is not None:
                rows.append(new_row)
            out.append(t)
        return "".join(out)

    walk(lint_html.parse(html), False, None, None)
    return blocks, rows, figures


def numbering(page: Path) -> tuple[set[str], set[str]]:
    """(section numbers such as '6' and '6.3', heading ids) of the explainer."""
    c = lint_html.Collector()
    c.feed(page.read_text(encoding="utf-8"))
    c.close()
    nums = set()
    for _, (_, text, _) in c.headings.items():
        m = re.match(r"^(\d+(?:\.\d+)*)\.?\s", text)
        if m:
            nums.add(m.group(1))
    return nums, {sid for sid in c.headings if sid}


def section_numbers(text: str) -> set[str]:
    """'Sections 1–7' -> {'1', ..., '7'}; 'Section 6.5' -> {'6.5'}; 'Sections 8.1 and 9.2' -> {'8.1', '9.2'}."""
    out = set()
    for m in SECTION_REF_RE.finditer(text.replace("&ndash;", "–")):
        part = m.group(1)
        rng = re.match(r"^(\d+)\s*[-‐-―]\s*(\d+)$", part.strip())
        if rng and int(rng.group(1)) < int(rng.group(2)) <= int(rng.group(1)) + 40:
            out |= {str(i) for i in range(int(rng.group(1)), int(rng.group(2)) + 1)}
        else:
            out |= set(NUMBER_RE.findall(part))
    return out


def within(tag: str, sections: set[str]) -> bool:
    """A tag agrees with the verification table when it is in one of its top-level sections."""
    return tag.split(".")[0] in {s.split(".")[0] for s in sections}


# --------------------------------------------------------------------------- checks
def code_files(code: Path) -> list[str]:
    if not code.is_dir():
        return []
    return sorted(p.relative_to(code).as_posix() for p in code.rglob("*.py")
                  if "__pycache__" not in p.parts and p.relative_to(code).parts[0] not in ("logs", "figures"))


def script_refs(blocks: list[dict], code: Path) -> tuple[dict, dict]:
    """({name as written: {"resolved", "sections"}} for found scripts, the same for missing ones)."""
    files = code_files(code)
    by_base: dict[str, list[str]] = {}
    for f in files:
        by_base.setdefault(Path(f).name, []).append(f)
    found, missing = {}, {}
    for b in blocks:
        last_dir = None
        tokens = [m.group(1) for m in SCRIPT_REF_RE.finditer(b["text"])] + b["hrefs"]
        for tok in tokens:
            t = re.sub(r"^(\./)+", "", tok)
            t = t[len("code/"):] if t.startswith("code/") else t
            if "/" in t:
                hit = t if (code / t).is_file() else None
                last_dir = str(Path(t).parent)
            else:
                near = f"{last_dir}/{t}" if last_dir else None
                hit = near if near and (code / near).is_file() else (by_base.get(t) or [None])[0]
            entry = (found if hit else missing).setdefault(t if not hit else hit, {"as_written": set(), "sections": set()})
            entry["as_written"].add(tok)
            if b["section"]:
                entry["sections"].add(b["section"])
    return found, missing


def manifest(code: Path, rep: Report) -> list[dict]:
    m = code / "checks.toml"
    if not m.exists():
        if code_files(code):
            rep.err("no-manifest", f"{rel(code)} has scripts but no checks.toml: every episode's code checks would fail",
                    "list the scripts in code/checks.toml (format: templates/run/checks.toml)")
        return []
    try:
        checks = tomllib.loads(m.read_text(encoding="utf-8")).get("check", [])
    except (tomllib.TOMLDecodeError, UnicodeDecodeError) as exc:
        rep.err("manifest-unreadable", f"{rel(m)} does not parse: {exc}")
        return []
    for i, c in enumerate(checks):
        s = c.get("script")
        if not s:
            rep.err("manifest-entry", f"{rel(m)}: [[check]] number {i + 1} has no script")
        elif not (code / s).is_file():
            rep.err("manifest-script-missing", f"{rel(m)} lists {s}, which is not under code/: the code checks of every "
                    "episode would fail", f"add code/{s}, or remove its [[check]] entry")
    return checks


def readme_tags(code: Path) -> list[tuple[str, list[str]]]:
    """[(script, [tags])] from the table of code/README.md whose header has a Section column."""
    p = code / "README.md"
    if not p.exists():
        return []
    out, col = [], None
    for line in p.read_text(encoding="utf-8").splitlines():
        if not line.startswith("|"):
            col = None if not line.strip() else col
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if col is None:
            col = next((i for i, c in enumerate(cells) if c.lower().startswith("section")), None)
            continue
        if set("".join(cells)) <= set("-: ") or col >= len(cells):
            continue
        scripts = re.findall(r"`([\w./-]+\.py)`", line)
        if scripts:
            out.append((scripts[0], [cells[col]]))
    return out


def tag_problems(tags: list[str], nums: set[str], ids: set[str], figures: set[int]) -> list[str]:
    bad = []
    for tag in tags:
        t = re.sub(r"\(.*?\)", "", str(tag))
        for m in FIGURE_RE.finditer(t):
            bad += [f"Figure {n}" for n in re.findall(r"\d+", m.group(1)) if int(n) not in figures]
        t = FIGURE_RE.sub(" ", t)
        t = re.sub(r"\bTables?\s+\d+(?:\s*(?:,|and)\s*\d+)*", " ", t, flags=re.I)
        bad += [x for x in re.findall(r"\bsec-[\w-]+", t) if x not in ids]
        bad += [n for n in NUMBER_RE.findall(re.sub(r"\bsec-[\w-]+", " ", t)) if n not in nums]
    return bad


def check(src: Path, render: bool = False) -> Report:
    rep = Report(src)
    page = src / "explainer.html"
    if not page.is_file():
        rep.err("no-explainer", f"{rel(src)} has no explainer.html", "put the source document there as explainer.html")
        return rep
    html = page.read_text(encoding="utf-8")
    strip = strippable(html)
    stripped_urls = {u for _, _, u, _ in strip}
    cmd = f"python3 tools/check_source.py {rel(src)} --strip-external-scripts --write"
    for line, _, url, host in strip:
        rep.err("external-script", f"explainer.html:{line} loads a script from {host} ({url[:60]}...): explainers are "
                "self-contained and only the pinned KaTeX CDN files may load (a page saved from a viewer can carry "
                "such a tag)", f"remove the tag: {cmd}")
    for i in lint_html.lint(page):
        if i["code"] == "external-resource" and any(u in i["message"] for u in stripped_urls):
            continue
        where = f"explainer.html:{i['line']} " if i.get("line") else "explainer.html "
        (rep.err if i["level"] == "error" else rep.warn)(f"lint-{i['code']}", where + i["message"])
    blocks, rows, figures = read_blocks(html)
    code = src / "code"
    found, missing = script_refs(blocks, code)
    rep.facts.update(scripts_named=len(found) + len(missing), scripts_found=len(found),
                     scripts_missing=sorted(missing))
    for name, e in sorted(missing.items()):
        secs = ", ".join(sorted(e["sections"], key=_num_key)) or "?"
        rep.warn("script-missing", f"the explainer names {name} (section {secs}), which is not under code/: the "
                 "numbers it prints cannot be reproduced, so no episode may show them until it is there",
                 f"add code/{name} (the source's author provides it; never write it from memory)")
    if not code.is_dir():
        rep.warn("no-companion-code", f"{rel(src)} has no code/: every number an episode shows must come from a "
                 "script written in that episode's run code/, never from memory")
        return _render(rep, page, render)
    checks = manifest(code, rep)
    listed = {c.get("script") for c in checks if c.get("script")}
    for f in code_files(code):
        if checks and f not in listed:
            rep.warn("not-in-manifest", f"code/{f} is not in checks.toml (fine for a helper module or a script run "
                     "by hand)")
    nums, ids = numbering(page)
    rows = verification_rows(rows)
    for c in checks:
        s = c.get("script")
        bad = tag_problems([str(t) for t in c.get("sections", [])], nums, ids, figures)
        if bad:
            rep.warn("stale-tag", f"checks.toml: {s} is tagged {', '.join(bad)}, which the explainer does not have "
                     "(renumbered?)", "change the sections of its [[check]] entry to the explainer's numbering")
        else:
            _place(rep, "checks.toml", s, [str(t) for t in c.get("sections", [])], rows)
    for s, tags in readme_tags(code):
        bad = tag_problems(tags, nums, ids, figures)
        if bad:
            rep.warn("stale-tag", f"code/README.md: the row of {s} names {', '.join(bad)}, which the explainer does "
                     "not have (renumbered?)", "change the Section(s) cell to the explainer's numbering")
        else:
            _place(rep, "code/README.md", s, tags, rows)
    return _render(rep, page, render)


def verification_rows(rows: list[dict]) -> dict[str, set[str]]:
    """{script: the sections its rows of the verification table name, else those of the part row above them}."""
    out: dict[str, set[str]] = {}
    part: set[str] = set()
    for r in rows:
        text = " ".join(r["cells"])
        scripts = SCRIPT_REF_RE.findall(text)
        if len(r["cells"]) == 1 and not scripts:
            part = section_numbers(text)
            continue
        secs = section_numbers(text) or part
        last_dir = None
        for tok in scripts:
            if "/" in tok:
                last_dir = str(Path(tok).parent)
                name = tok
            else:
                name = f"{last_dir}/{tok}" if last_dir else tok
            if secs:
                out.setdefault(name, set()).update(secs)
    return out


def _place(rep: Report, where: str, script: str, tags: list[str], rows: dict[str, set[str]]):
    secs = rows.get(script)
    nums = [n for t in tags for n in NUMBER_RE.findall(FIGURE_RE.sub(" ", re.sub(r"\(.*?\)", "", t)))]
    if secs and nums and not any(within(n, secs) for n in nums):
        rep.warn("stale-tag", f"{where}: {script} is tagged {', '.join(nums)}, but the explainer's verification table "
                 f"ties it to section(s) {', '.join(sorted(secs, key=_num_key))} (renumbered?)",
                 "use the explainer's current section numbers")


def _num_key(s: str):
    return [int(x) if x.isdigit() else 0 for x in re.split(r"[.\s]", s)] if s and s[0].isdigit() else [999, s]


def _render(rep: Report, page: Path, render: bool) -> Report:
    if not render:
        return rep
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "check_html.json"
        try:
            r = subprocess.run(["node", str(REPO / "tools" / "check_html.js"), str(page), "--offline", "--json",
                                str(out)], capture_output=True, text=True, timeout=900)
        except (OSError, subprocess.TimeoutExpired) as exc:
            rep.warn("render-not-run", f"tools/check_html.js could not run: {exc}")
            return rep
        if r.returncode == 3:
            rep.warn("render-not-run", "tools/check_html.js could not start (Node, Playwright or Chromium missing): "
                     + r.stderr.strip()[:160])
        elif r.returncode != 0:
            data = json.loads(out.read_text(encoding="utf-8")) if out.exists() else {}
            errs = data.get("errors") or [r.stdout.strip().splitlines()[-1] if r.stdout.strip() else "failed"]
            rep.err("render", f"tools/check_html.js: {len(errs)} error(s), first: {str(errs[0])[:160]}")
        else:
            rep.facts["render"] = "passed"
    return rep


# --------------------------------------------------------------------------- external scripts
def _external_scripts(html: str):
    """(match, url, host) of each empty <script src> tag whose host is not the KaTeX CDN."""
    for m in SCRIPT_TAG_RE.finditer(html):
        url = m.group(2).strip()
        if re.match(r"^(https?:)?//", url, re.I):
            host = urlparse(url if not url.startswith("//") else "https:" + url).hostname
            if host != KATEX_HOST:
                yield m, url, host or "?"


def strippable(html: str) -> list[tuple[int, int, str, str]]:
    """(line, offset, url, host) of each tag strip_scripts removes."""
    return [(html.count("\n", 0, m.start()) + 1, m.start(), url, host) for m, url, host in _external_scripts(html)]


def strip_scripts(html: str) -> tuple[str, int]:
    """The page without those tags (a tag alone on its line takes the line), and their number."""
    found = [m for m, _, _ in _external_scripts(html)]
    for m in reversed(found):
        a, b = m.start(), m.end()
        ls = html.rfind("\n", 0, a) + 1
        le = html.find("\n", b)
        le = len(html) if le < 0 else le
        if not html[ls:a].strip() and not html[b:le].strip():
            a, b = ls, min(le + 1, len(html))
        html = html[:a] + html[b:]
    return html, len(found)


# --------------------------------------------------------------------------- command line
def show(rep: Report, verbose: bool = True) -> None:
    print(f"== {rel(rep.source)}")
    for kind, items in (("ERROR", rep.errors), ("WARN ", rep.warnings)):
        for i in items:
            print(f"{kind}  [{i['code']}] {i['message']}")
            if i.get("fix") and verbose:
                print(f"       fix: {i['fix']}")
    f = rep.facts
    if "scripts_named" in f:
        print(f"       scripts named in the explainer: {f['scripts_named']} ({f['scripts_found']} under code/, "
              f"{len(f['scripts_missing'])} missing)")
    print(f"check_source: {'FAIL' if rep.errors else 'ok'} ({len(rep.errors)} error(s), {len(rep.warnings)} "
          f"warning(s)) {rel(rep.source)}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("sources", nargs="*", help="source folders (sources/<name>)")
    ap.add_argument("--all", action="store_true", help="every folder in sources/ (or --sources-dir)")
    ap.add_argument("--sources-dir", help="the folder --all reads (default sources/)")
    ap.add_argument("--render", action="store_true", help="also run tools/check_html.js")
    ap.add_argument("--strict", action="store_true", help="warnings count as errors")
    ap.add_argument("--json", help="write the reports as JSON")
    ap.add_argument("--strip-external-scripts", action="store_true",
                    help="list the external <script src> tags that are not KaTeX (with --write: remove them)")
    ap.add_argument("--write", action="store_true", help="with --strip-external-scripts: change explainer.html")
    a = ap.parse_args()
    if a.write and not a.strip_external_scripts:
        ap.error("--write only goes with --strip-external-scripts")
    folders = [Path(s) for s in a.sources]
    if a.all:
        root = Path(a.sources_dir) if a.sources_dir else REPO / "sources"
        folders += sorted(p for p in root.iterdir() if p.is_dir() and not p.name.startswith((".", "_"))) \
            if root.is_dir() else []
        if not folders:
            print(f"check_source: no source folders in {rel(root)}: nothing to check")
            return 0
    if not folders:
        ap.error("name a source folder, or pass --all")
    reports, failed = [], False
    for src in folders:
        src = src if src.is_absolute() else (Path.cwd() / src)
        if a.strip_external_scripts and (src / "explainer.html").is_file():
            page = src / "explainer.html"
            html = page.read_text(encoding="utf-8")
            tags = strippable(html)
            for line, _, url, host in tags:
                print(f"{'removing' if a.write else 'would remove'} explainer.html:{line}: <script src> from {host} "
                      f"({url[:60]}...)")
            if tags and a.write:
                new, n = strip_scripts(html)
                page.write_text(new, encoding="utf-8")
                print(f"removed {n} tag(s) from {rel(page)}")
            elif tags:
                print(f"dry run: nothing changed; add --write to remove {len(tags)} tag(s)")
            else:
                print(f"no external script tags to remove in {rel(page)}")
        rep = check(src.resolve(), a.render)
        show(rep)
        reports.append(rep)
        failed |= bool(rep.errors) or (a.strict and bool(rep.warnings))
    if a.json:
        write_json(Path(a.json), {"schema_version": 1, "passed": not failed, "strict": a.strict,
                                  "sources": [{"source": rel(r.source), "errors": r.errors, "warnings": r.warnings,
                                               **r.facts} for r in reports]})
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
