#!/usr/bin/env python3
"""The text of a built explainer in reading order, section by section.

Usage:
  python3 tools/explainer_text.py runs/<run>/explainer.html --outline           # sections: number, id, words
  python3 tools/explainer_text.py runs/<run>/explainer.html --section 5.2        # one section with its subsections
  python3 tools/explainer_text.py runs/<run>/explainer.html --until 6.2          # everything before Section 6.2
  python3 tools/explainer_text.py runs/<run>/explainer.html --from 5 --until 6.3 # a range, in order
  python3 tools/explainer_text.py runs/<run>/explainer.html --grep 'nabla W' --until 6.2   # was it said before 6.2?
  python3 tools/explainer_text.py runs/<run>/explainer.html                      # the whole text
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _common  # noqa: E402,F401  (runs the script in .venv)
from bs4 import Tag  # noqa: E402
from bs4.element import PreformattedString  # noqa: E402
from lint_html import parse  # noqa: E402

BLOCK = {"p", "div", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "figcaption", "table", "section", "ol", "ul",
         "blockquote", "br", "figure", "header", "footer", "article", "aside", "details", "summary", "pre", "dt", "dd"}
SKIP = {"script", "style", "nav", "button", "head", "template", "noscript"}
HEADING = {"h1": 1, "h2": 2, "h3": 3, "h4": 4}
NUM_RE = re.compile(r"^((?:\d+|[A-Z])(?:\.\d+)*)\.?\s+")


def read(path: Path) -> list[dict]:
    """Text blocks in document order: {"text", "level" (0 for text), "num", "id", "sec", "sec_id"}; a figure is one
    block with its description."""
    blocks, buf, ids = [], [], []          # ids: of the open <section>s, innermost last
    sec, sec_id, heading, cell = "", None, None, False

    def add(text, level=0, num="", hid=None):
        blocks.append({"text": text, "level": level, "num": num, "id": hid, "sec": sec, "sec_id": sec_id})

    def flush():
        nonlocal sec, sec_id
        text = " ".join("".join(buf).split())
        buf.clear()
        if not text:
            return
        if not heading:
            add(text)
            return
        level, hid = heading
        m = NUM_RE.match(text)
        num = m.group(1) if m else ""
        if num:
            sec = num
        elif level <= 2:
            sec = text
        if hid:
            sec_id = hid
        elif level <= 2 or num:            # an unnumbered minor heading stays in its subsection
            sec_id = next((i for i in reversed(ids) if i), None)
        add(text, level, num, sec_id)

    def walk(el):
        nonlocal heading, cell
        for c in el.children:
            if not isinstance(c, Tag):
                if not isinstance(c, PreformattedString):
                    buf.append(c)
                continue
            if c.name in SKIP:
                continue
            if c.name == "svg":
                flush()
                label = c.get("aria-label") or c.get("title") or ""
                add(f"[figure: {label}]" if label else "[figure]")
                continue
            if c.name == "section":
                flush()
                ids.append(c.get("id"))
            elif c.name in HEADING:
                flush()
                heading = (HEADING[c.name], c.get("id"))
            elif c.name in ("td", "th"):
                if cell:
                    buf.append(" | ")
                cell = True
            elif c.name in BLOCK:
                flush()
                if c.name == "li":
                    buf.append("- ")
                if c.name == "tr":
                    cell = False
            walk(c)
            if c.name in HEADING:
                flush()
                heading = None
            elif c.name == "section":
                flush()
                ids.pop()
            elif c.name in BLOCK:
                flush()
                if c.name == "tr":
                    cell = False

    walk(parse(path.read_text(encoding="utf-8")))
    flush()
    return blocks


def matches(block: dict, key: str) -> bool:
    """A heading block named by key: its number (5, 5.2) or its id (sec-momentum)."""
    return bool(block["level"]) and (block["num"] == key.rstrip(".") or block["id"] == key)


def span(blocks: list[dict], key: str, start: int = 0) -> tuple[int, int]:
    """(first, end) of the section named by key: its heading up to the next heading of the same or a higher level."""
    i = next((k for k in range(start, len(blocks)) if matches(blocks[k], key)), None)
    if i is None:
        sys.exit(f"error: no section {key!r} (see --outline)")
    lvl = blocks[i]["level"]
    j = next((k for k in range(i + 1, len(blocks)) if blocks[k]["level"] and blocks[k]["level"] <= lvl), len(blocks))
    return i, j


def render(block: dict) -> str:
    if block["level"]:
        tag = f" {{#{block['id']}}}" if block["id"] else ""
        return "\n" + "#" * block["level"] + " " + block["text"] + tag
    return block["text"]


def select(blocks: list[dict], a) -> list[dict]:
    if a.section:
        spans = sorted(span(blocks, k) for k in a.section)
        return [b for i, j in spans for b in blocks[i:j]]
    start = span(blocks, a.start)[0] if a.start else 0
    end = span(blocks, a.until, start)[0] if a.until else len(blocks)
    return blocks[start:end]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("html")
    ap.add_argument("--outline", action="store_true", help="list the sections with their number, id and word count")
    ap.add_argument("--section", action="append", help="print this section and its subsections (repeatable)")
    ap.add_argument("--from", dest="start", help="start at this section")
    ap.add_argument("--until", help="stop before this section")
    ap.add_argument("--grep", help="print only the blocks matching this regular expression (case-insensitive)")
    a = ap.parse_args()
    path = Path(a.html)
    if path.is_dir():
        path = path / "explainer.html"
    if not path.is_file():
        print(f"error: {a.html}: no explainer.html", file=sys.stderr)
        return 1
    blocks = read(path)
    if a.outline:
        words: dict[int, int] = {}
        current = None
        for i, b in enumerate(blocks):
            if b["level"]:
                current = i
                words[i] = 0
            elif current is not None:
                words[current] += len(b["text"].split())
        for i, b in enumerate(blocks):
            if b["level"]:
                print(f"{'  ' * (b['level'] - 1)}{b['text']}  [{b['id'] or '-'}, {words[i]} words]")
        return 0
    chosen = select(blocks, a)
    if a.grep:
        rx = re.compile(a.grep, re.I)
        for b in chosen:
            if rx.search(b["text"]):
                print(f"[{b['sec'] or '-'}] {b['text']}")
        return 0
    print("\n".join(render(b) for b in chosen).strip())
    return 0


if __name__ == "__main__":
    sys.exit(main())
