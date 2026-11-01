#!/usr/bin/env python3
"""The text of a built explainer in reading order, section by section (for reviewers who read front to back).

Usage:
  python3 tools/explainer_text.py runs/<run>/explainer.html --outline           # sections: number, id, words
  python3 tools/explainer_text.py runs/<run>/explainer.html --section 5.2        # one section with its subsections
  python3 tools/explainer_text.py runs/<run>/explainer.html --until 6.2          # everything before Section 6.2
  python3 tools/explainer_text.py runs/<run>/explainer.html --from 5 --until 6.3 # a range, in order
  python3 tools/explainer_text.py runs/<run>/explainer.html --grep 'nabla W' --until 6.2   # was it said before 6.2?
  python3 tools/explainer_text.py runs/<run>/explainer.html                      # the whole text

A section is named by its number (5, 5.2) or its id (sec-momentum). Headings print as Markdown headings with their
number and id; math stays as written ($...$ and $$...$$ with \\tag numbers), figures as one line with their
description, tables as rows of cells; scripts, styles, the contents sidebar and the page controls are left out.
Standard library only; deterministic.
"""
from __future__ import annotations

import argparse
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

BLOCK = {"p", "div", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "figcaption", "table", "section", "ol", "ul",
         "blockquote", "br", "figure", "header", "footer", "article", "aside", "details", "summary", "pre", "dt", "dd"}
SKIP = {"script", "style", "nav", "button", "head", "template", "noscript"}
HEADING = {"h1": 1, "h2": 2, "h3": 3, "h4": 4}
NUM_RE = re.compile(r"^((?:\d+|[A-Z])(?:\.\d+)*)\.?\s+")


class Reader(HTMLParser):
    """Collects blocks of text in document order: {"text", "level" (0 for text), "num", "id", "sec", "sec_id"}."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.blocks: list[dict] = []
        self.buf: list[str] = []
        self.skip = 0                  # depth inside a skipped element
        self.svg = 0                   # depth inside an inline <svg>
        self.heading = None            # (level, id) while inside a heading
        self.ids: list[str | None] = []    # id of each open <section>, innermost last
        self.sec, self.sec_id = "", None
        self.cell = False

    def flush(self):
        text = " ".join("".join(self.buf).split())
        self.buf = []
        if not text:
            return
        if self.heading:
            level, hid = self.heading
            m = NUM_RE.match(text)
            num = m.group(1) if m else ""
            if num:
                self.sec = num
            elif level <= 2:
                self.sec = text
            if hid:
                self.sec_id = hid
            elif level <= 2 or num:            # an unnumbered minor heading stays in its subsection
                self.sec_id = next((i for i in reversed(self.ids) if i), None)
            self.blocks.append({"text": text, "level": level, "num": num, "id": self.sec_id, "sec": self.sec,
                                "sec_id": self.sec_id})
        else:
            self.blocks.append({"text": text, "level": 0, "num": "", "id": None, "sec": self.sec,
                                "sec_id": self.sec_id})

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if self.skip:
            if tag in SKIP:
                self.skip += 1
            return
        if tag in SKIP:
            self.skip = 1
            return
        if tag == "svg":
            if not self.svg:
                self.flush()
                label = a.get("aria-label") or a.get("title") or ""
                self.blocks.append({"text": f"[figure: {label}]" if label else "[figure]", "level": 0, "num": "",
                                    "id": None, "sec": self.sec, "sec_id": self.sec_id})
            self.svg += 1
            return
        if self.svg:
            return
        if tag == "section":
            self.flush()
            self.ids.append(a.get("id"))
        elif tag in HEADING:
            self.flush()
            self.heading = (HEADING[tag], a.get("id"))
        elif tag in ("td", "th"):
            if self.cell:
                self.buf.append(" | ")
            self.cell = True
        elif tag in BLOCK:
            self.flush()
            if tag == "li":
                self.buf.append("- ")
            if tag == "tr":
                self.cell = False

    def handle_endtag(self, tag):
        if self.skip:
            if tag in SKIP:
                self.skip -= 1
            return
        if tag == "svg" and self.svg:
            self.svg -= 1
            return
        if self.svg:
            return
        if tag in HEADING:
            self.flush()
            self.heading = None
        elif tag == "section":
            self.flush()
            if self.ids:
                self.ids.pop()
        elif tag in BLOCK:
            self.flush()
            if tag == "tr":
                self.cell = False

    def handle_data(self, data):
        if not self.skip and not self.svg:
            self.buf.append(data)

    def close(self):
        super().close()
        self.flush()


def read(path: Path) -> list[dict]:
    r = Reader()
    r.feed(path.read_text(encoding="utf-8"))
    r.close()
    return r.blocks


def matches(block: dict, key: str) -> bool:
    """A heading block named by key: its number (5, 5.2) or its id (sec-momentum)."""
    return bool(block["level"]) and (block["num"] == key.rstrip(".") or block["id"] == key)


def span(blocks: list[dict], key: str, start: int = 0) -> tuple[int, int]:
    """(first, end) indices of the section named by key: its heading and everything up to the next heading of the
    same or a higher level."""
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
