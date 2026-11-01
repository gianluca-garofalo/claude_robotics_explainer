#!/usr/bin/env python3
"""List every voiceover block of a run's scenes, for recording them in your own voice.

Usage:
  python3 tools/video/voice_script.py runs/<run>      # writes video/voice/SCRIPT.md and prints it

Each `self.voiceover(text="...")` string literal in video/scenes/*.py becomes one line: its block key, the scene and
the text to read (bookmarks removed). Record each block as video/voice/<key>.wav (or .mp3, .m4a, .flac, .ogg), then
render with VOICE_SERVICE=recorded (or set "voice": {"service": "recorded"} in config/channel.json). The key is the
same one templates/manim/voice.py computes, so a changed sentence needs a new recording and an unchanged one does not.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _common import rel, resolve_run  # noqa: E402

BOOKMARK = re.compile(r"<bookmark\s*mark\s*=['\"]\w*[\"']\s*/>")   # as manim_voiceover.helper.remove_bookmarks


def key(text: str) -> str:
    words = " ".join(BOOKMARK.sub("", text).split())
    return hashlib.sha1(words.encode("utf-8")).hexdigest()[:10]


def blocks(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and getattr(node.func, "attr", "") == "voiceover":
            for kw in node.keywords:
                if kw.arg == "text":
                    try:
                        text = ast.literal_eval(kw.value)
                    except ValueError:
                        yield None, f"(computed text at line {node.lineno}: write it as a literal to record it)"
                        continue
                    yield key(text), " ".join(BOOKMARK.sub("", text).split())


def blocks_by_class(path: Path) -> dict[str, list[str]]:
    """{scene class: [narration text, ...]} in source order (literal texts, bookmarks removed; computed texts skipped)."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out = {}
    for cls in (n for n in tree.body if isinstance(n, ast.ClassDef)):
        found = []
        for node in ast.walk(cls):
            if isinstance(node, ast.Call) and getattr(node.func, "attr", "") == "voiceover":
                for kw in node.keywords:
                    if kw.arg == "text":
                        try:
                            found.append((node.lineno, " ".join(BOOKMARK.sub("", ast.literal_eval(kw.value)).split())))
                        except ValueError:
                            pass
        out[cls.name] = [t for _, t in sorted(found)]
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run")
    a = ap.parse_args()
    run = resolve_run(a.run)
    lines = ["# Voice-over script", "", "Record each block as `video/voice/<key>.wav` (one file per block).", "",
             "| Key | Scene | Text |", "|---|---|---|"]
    n = 0
    for f in sorted((run / "video" / "scenes").glob("*.py")):
        for k, text in blocks(f):
            lines.append(f"| {k or '-'} | {f.stem} | {text.replace('|', '/')} |")
            n += 1
    out = run / "video" / "voice" / "SCRIPT.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print(f"\n{n} block(s); wrote {rel(out)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
