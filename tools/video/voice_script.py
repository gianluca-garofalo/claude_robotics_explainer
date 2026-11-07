#!/usr/bin/env python3
"""List every voiceover block of a run's scenes with its key, for recording them as video/voice/<key>.wav.

Usage:
  python3 tools/video/voice_script.py runs/<run> [--out PATH]      # default video/voice/SCRIPT.md; also printed
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.util
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _common import REPO, rel, resolve_run  # noqa: E402

BOOKMARK = re.compile(r"<bookmark\s*mark\s*=['\"]\w*[\"']\s*/>")   # as manim_voiceover.helper.remove_bookmarks


def _voice():
    """templates/manim/voice.py, loaded by path (the repository's copy, never a run's)."""
    spec = importlib.util.spec_from_file_location("ra_template_voice", REPO / "templates" / "manim" / "voice.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


VOICE = _voice()


def spoken(text: str) -> str:
    """A block as it is heard: bookmarks and pacing markup removed, spaces normalised."""
    return VOICE.strip_markup(BOOKMARK.sub("", text))


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


def blocks_by_class(path: Path, markup: bool = False) -> dict[str, list[str]]:
    """{scene class: [narration text, ...]} in source order, as spoken() unless markup=True (then key() applies)."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out = {}
    for cls in (n for n in tree.body if isinstance(n, ast.ClassDef)):
        found = []
        for node in ast.walk(cls):
            if isinstance(node, ast.Call) and getattr(node.func, "attr", "") == "voiceover":
                for kw in node.keywords:
                    if kw.arg == "text":
                        try:
                            text = " ".join(BOOKMARK.sub("", ast.literal_eval(kw.value)).split())
                        except ValueError:
                            continue
                        found.append((node.lineno, node.col_offset, text if markup else spoken(text)))
        out[cls.name] = [t for _, _, t in sorted(found)]
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run")
    ap.add_argument("--out", help="where to write the script (default: video/voice/SCRIPT.md of the run)")
    a = ap.parse_args()
    run = resolve_run(a.run)
    lines = ["# Voice-over script", "", "Record each block as `video/voice/<key>.wav` (one file per block).", "",
             "| Key | Scene | Text |", "|---|---|---|"]
    n = 0
    for f in sorted((run / "video" / "scenes").glob("*.py")):
        for k, text in blocks(f):
            lines.append(f"| {k or '-'} | {f.stem} | {text.replace('|', '/')} |")
            n += 1
    out = Path(a.out) if a.out else run / "video" / "voice" / "SCRIPT.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print(f"\n{n} block(s); wrote {rel(out)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
