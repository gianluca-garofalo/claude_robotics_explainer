#!/usr/bin/env python3
"""Sync check: each picture, label and equation appears as the narration names it (temporal contiguity).

Usage:
  python3 tools/video/check_sync.py runs/<run> --stage draft|final [--out DIR]
  python3 tools/video/check_sync.py --scenes DIR [--out DIR]          # the source rule alone, on scene files

Rules (thresholds in config/video.json "sync"):
  early       a text label or equation appears more than lead_max_s before the narration first says its words
              (normalized, simply stemmed); items never spoken, the channel's name (the logo) and the hook's opening
              frame are skipped. Word timings: the draft's silent voice (layout logs), the final narration
              (video/voice/manifest.json).
  unanchored  one play() in a voiceover block reveals two or more separate pictures (FadeIn, Create, Write, the Grow
              animations, DrawBorderThenFill, or a LaggedStart, AnimationGroup or Succession of them) more than
              lead_max_s after the last word timed in the block (a wait_until_word or wait_until_bookmark, or a play
              that runs until a word, with only plays since), or one after another from that word; the members of one
              collection may build up one after another.
Findings are warnings; with sync.errors_block_gate true the early ones are errors. Exit status 1 on an error.
"""
from __future__ import annotations

import argparse
import ast
import re
import statistics
import sys
from functools import partial
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
from _common import CONFIG, load_json, read_json, rel, resolve_run, sha256_file  # noqa: E402
import checks  # noqa: E402
import voice_script as VS  # noqa: E402

DEFAULTS = {"lead_max_s": 1.0, "errors_block_gate": False}
Findings = partial(checks.Findings, "rule", "severity", "where", "detail", "t")

WORD = re.compile(r"[^\W_]+(?:['’][^\W_]+)*")
STOP = {"a", "an", "the", "of", "to", "in", "on", "at", "by", "for", "with", "from", "into", "and", "or", "but", "so",
        "is", "are", "was", "were", "be", "been", "it", "it's", "its", "this", "that", "these", "those", "as", "than",
        "then", "there", "here", "we", "you", "our", "your", "their", "they", "he", "she", "his", "her"}
NUMBER_WORDS = {w: str(i) for i, w in enumerate(("zero", "one", "two", "three", "four", "five", "six", "seven",
                                                 "eight", "nine", "ten", "eleven", "twelve"))}
TEX_WORDS = re.compile(r"\\(?:text|textrm|textit|textbf|mathrm|operatorname|mbox)\s*\{([^{}]*)\}")

REVEALS = {"FadeIn", "Create", "Write", "DrawBorderThenFill", "GrowFromCenter", "GrowFromEdge", "GrowFromPoint",
           "GrowArrow", "SpinInFromNothing"}
GROUPS = {"LaggedStart", "AnimationGroup", "Succession"}
STAGGERS = {"LaggedStart", "LaggedStartMap", "Succession"}
SYNCS = {"wait_until_word", "wait_until_bookmark"}
TIMED = {"play", "wait", "pause", "safe_wait", "read", "wait_for_voiceover"}
WORD_TIMES = {"time_until_word", "time_until_bookmark", "until"}
TEXTS = {"Text", "MarkupText", "Paragraph", "Tex", "MathTex", "SingleStringMathTex", "Title", "BulletedList",
         "DecimalNumber", "Integer", "Variable", "BraceLabel", "BraceText", "eq", "ceq", "caption", "title", "pin",
         "readout", "legend_table", "title_beat", "takeaway_card", "recap_card", "recap_tag", "builds_on"}


def settings() -> dict:
    cfg = dict(DEFAULTS)
    cfg.update({k: v for k, v in (load_json(CONFIG / "video.json").get("sync") or {}).items()
                if not k.startswith("_")})
    return cfg


# --------------------------------------------------------------------------- words

def stem(word: str) -> str:
    """A simple stem: robots -> robot, legged -> leg, circling and circle -> circl, one -> 1."""
    w = word.lower().replace("’", "'")
    w = w[:-2] if w.endswith("'s") else w
    w = NUMBER_WORDS.get(w, w)
    if len(w) > 4 and w.endswith("ies"):
        w = w[:-3] + "y"
    elif len(w) > 4 and w.endswith(("sses", "ches", "shes", "xes", "zes")):
        w = w[:-2]
    elif len(w) > 3 and w.endswith("s") and not w.endswith(("ss", "us", "is")):
        w = w[:-1]
    if len(w) > 5 and w.endswith("ing"):
        w = w[:-3]
    elif len(w) > 4 and w.endswith("ed"):
        w = w[:-2]
    if len(w) > 3 and w[-1] == w[-2] and w[-1] not in "lsz":
        w = w[:-1]
    return w[:-1] if len(w) > 3 and w.endswith("e") else w


def words(text: str) -> list[str]:
    return [m.group().lower().replace("’", "'") for m in WORD.finditer(text)]


def item_words(kind: str, content: str) -> list[tuple[str, ...]]:
    """The stemmed content words an on-screen item shows: a text's words, an equation's \\text{} groups."""
    if kind == "math":
        seqs = [tuple(stem(w) for w in words(g) if w not in STOP and len(w) > 1) for g in TEX_WORDS.findall(content)]
    else:
        seqs = [tuple(stem(w) for w in words(content) if w not in STOP)]
    return [s for s in seqs if s]


# --------------------------------------------------------------------------- the timeline

def word_times(bounds: list, text: str) -> list[list]:
    """[[word, start s]] of the words of `text` a word timing starts on (offsets into the text, as voice.py writes)."""
    at = {m.start(): m.group() for m in re.finditer(r"\S+", VS.VOICE.mask_markup(text))}
    found: dict[int, list] = {}
    for b in bounds or []:
        off = int(b.get("text_offset", -1))
        if off in at and off not in found:
            found[off] = [at[off], float(b.get("audio_offset", 0)) / VS.VOICE.AUDIO_OFFSET_RESOLUTION]
    return [found[k] for k in sorted(found)]


def narration(run: Path) -> dict[str, list]:
    """{block key: [[word, start s]]}: the final narration's word timings (video/voice/manifest.json)."""
    vdir = run / "video" / "voice"
    out = {}
    for key, b in (read_json(vdir / "manifest.json", {}).get("blocks") or {}).items():
        if (vdir / f"{key}.timings.json").exists():
            out[key] = word_times(read_json(vdir / f"{key}.timings.json"), b.get("text") or "")
    return out


def timeline(run: Path, stage: str) -> dict:
    """The narration's timed words by block and the on-screen texts and equations, in seconds from the video's start."""
    plan = load_json(run / "video" / "plan.json")
    folder = run / "video" / ("checks" if stage == "draft" else "renders")
    seg = {}
    if stage == "final":
        seg = {s.get("class"): s for s in read_json(run / "video" / "final" / "assembly.json", {}).get("segments", [])}
    voiced = narration(run) if stage == "final" else {}
    channel = str(load_json(CONFIG / "channel.json").get("channel_name") or "").strip().lower()
    t, blocks, items, sha = 0.0, [], [], {}
    for i, s in enumerate(plan.get("scenes", [])):
        cls = s["class"]
        log, lp = checks.scene_log(folder, cls)
        if lp is not None:
            sha[cls] = sha256_file(lp)
        off = float(seg[cls]["start"]) if cls in seg else t
        dur = float(seg[cls]["duration"]) if cls in seg else float(log.get("duration") or 0.0)
        for v in log.get("voiceovers") or []:
            b0 = off + float(v.get("start", 0.0))
            tim = voiced.get(VS.key(v.get("raw") or v.get("text") or "")) or v.get("timings")
            if not tim:                               # an older log: the words spread over the block
                ws = str(v.get("text") or "").split()
                tim = [[w, float(v.get("duration", 0.0)) * k / max(len(ws), 1)] for k, w in enumerate(ws)]
            blocks.append({"scene": cls, "words": [(b0 + float(e[1]), str(e[0])) for e in tim]})
        for it in log.get("timeline") or []:
            on = [e for e in it.get("events") or [] if e[1] == 1]
            if not on or it.get("live") or it.get("axis") or it.get("kind") not in ("text", "math"):
                continue
            if channel and str(it.get("content") or "").strip().lower() == channel:
                continue                              # the logo's name (brand.py), not a label the narration names
            t0 = float(on[0][0])
            items.append({"scene": cls, "kind": it["kind"], "content": str(it.get("content") or ""), "t": t0,
                          "t_on": off + t0, "opening": i == 0 and t0 <= 0.05})
        t = max(t, off + dur)
    return {"blocks": blocks, "items": items, "layout_sha256": sha}


def mention(stream: list, seq: tuple) -> tuple | None:
    """(time, block, first word, last word) where the narration first says the stemmed words `seq`, or None."""
    k = len(seq)
    for i in range(len(stream) - k + 1):
        part = stream[i:i + k]
        if tuple(x[0] for x in part) == seq and len({x[2] for x in part}) == 1:
            return part[0][1], part[0][2], part[0][3], part[-1][3]
    return None


def early(tl: dict, cfg: dict, fd: checks.Findings) -> dict:
    """Labels and equations shown more than lead_max_s before the narration first says their words."""
    stream = [(stem(tok), t, bi, wi) for bi, b in enumerate(tl["blocks"]) for wi, (t, w) in enumerate(b["words"])
              for tok in words(w) if tok not in STOP]
    first: dict[tuple, dict] = {}
    for it in sorted(tl["items"], key=lambda x: x["t_on"]):
        seqs = tuple(item_words(it["kind"], it["content"]))
        if seqs and seqs not in first:
            first[seqs] = it
    leads, n_early = [], 0
    severity = "error" if cfg.get("errors_block_gate") else "warning"
    for seqs, it in first.items():
        hits = [h for h in (mention(stream, s) for s in seqs) if h]
        if it["opening"] or not hits:
            continue
        t_said, bi, w0, w1 = min(hits)
        lead = t_said - it["t_on"]
        leads.append(lead)
        if lead <= float(cfg["lead_max_s"]):
            continue
        n_early += 1
        block = tl["blocks"][bi]
        said = re.sub(r"^\W+|\W+$", "", " ".join(w for _, w in block["words"][w0:w1 + 1]))
        there = "" if block["scene"] == it["scene"] else f" in {block['scene']}"
        fd.add("early", severity, it["scene"], f"{it['content'][:40]!r} appears {lead:.1f} s before the narration "
               f"says {said!r}{there} (at most {cfg['lead_max_s']:g} s): show it on its words, "
               f"self.wait_until_word({said!r}) before its play()", it["t"])
    return {"items": len(first), "spoken": len(leads), "early": n_early,
            "median_lead_s": round(statistics.median(leads), 2) if leads else None}


# --------------------------------------------------------------------------- scene source

def _name(node) -> str:
    f = node.func if isinstance(node, ast.Call) else None
    return f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else ""


def loop_items(target: ast.AST, it: ast.AST) -> list[tuple[str, ast.expr]]:
    """(name, an item of what it runs over) of a loop: x in xs, a, b in zip(xs, ys), i, x in enumerate(xs)."""
    if isinstance(target, (ast.Tuple, ast.List)) and _name(it) in ("zip", "enumerate"):
        names = target.elts[1:] if _name(it) == "enumerate" else target.elts
        runs = it.args[:1] if _name(it) == "enumerate" else it.args
        return [x for t, r in zip(names, runs) for x in loop_items(t, r)] if len(names) == len(runs) else []
    return [(target.id, ast.Subscript(value=it, slice=ast.Constant(0), ctx=ast.Load()))] \
        if isinstance(target, ast.Name) else []


def assignments(fn: ast.AST) -> dict[str, list[tuple[int, ast.expr]]]:
    """{name: [(line, value)]} of a function's assignments and loop variables in line order; a tuple target's names get
    their elements."""
    out: dict[str, list] = {}
    for n in ast.walk(fn):
        if isinstance(n, ast.For):
            for name, v in loop_items(n.target, n.iter):
                out.setdefault(name, []).append((n.lineno, v))
        if not isinstance(n, ast.Assign):
            continue
        for t in n.targets:
            if isinstance(t, ast.Name):
                out.setdefault(t.id, []).append((n.lineno, n.value))
            elif isinstance(t, (ast.Tuple, ast.List)):
                vals = n.value.elts if isinstance(n.value, (ast.Tuple, ast.List)) and \
                    len(n.value.elts) == len(t.elts) else [n.value] * len(t.elts)
                for e, v in zip(t.elts, vals):
                    if isinstance(e, ast.Name):
                        out.setdefault(e.id, []).append((n.lineno, v))
    return {k: sorted(v, key=lambda x: x[0]) for k, v in out.items()}


class Source:
    """A folder's scene modules: is an expression a text (label, equation, readout) or a picture?"""

    def __init__(self, files: list[Path]):
        self.trees, self.broken = {}, {}
        for f in files:
            try:
                self.trees[f] = ast.parse(f.read_text(encoding="utf-8"), filename=f.name)
            except SyntaxError as exc:
                self.broken[f] = exc
        self.funcs = {}
        trees = list(self.trees.values())
        for n in [n for t in trees for n in t.body] + [n for t in trees for n in ast.walk(t)]:
            if isinstance(n, ast.FunctionDef):           # module helpers first, then methods and helpers inside them
                self.funcs.setdefault(n.name, n)
        self._returns: dict[str, bool] = {}

    def returns_text(self, name: str, depth: int) -> bool:
        if name not in self._returns:
            self._returns[name] = False                  # a recursive helper is a picture
            fn = self.funcs[name]
            env = assignments(fn)
            rets = [r for r in ast.walk(fn) if isinstance(r, ast.Return) and r.value is not None]
            self._returns[name] = bool(rets) and all(self.is_text(r.value, env, r.lineno, depth + 1) for r in rets)
        return self._returns[name]

    def is_text(self, e: ast.AST, env: dict, line: int, depth: int = 0) -> bool:
        if depth > 12:
            return False
        if isinstance(e, ast.Name):
            vals = env.get(e.id, [])
            before = [v for ln, v in vals if ln <= line] or [v for _, v in vals]
            return bool(before) and self.is_text(before[-1], env, line, depth + 1)
        if isinstance(e, (ast.Subscript, ast.Attribute, ast.Starred)):
            return self.is_text(e.value, env, line, depth + 1)
        if isinstance(e, ast.IfExp):
            return self.is_text(e.body, env, line, depth + 1) and self.is_text(e.orelse, env, line, depth + 1)
        if isinstance(e, (ast.List, ast.Tuple, ast.Set)):
            return bool(e.elts) and all(self.is_text(x, env, line, depth + 1) for x in e.elts)
        if isinstance(e, (ast.ListComp, ast.GeneratorExp, ast.SetComp)):
            inner = dict(env, **{k: [(line, v)] for g in e.generators for k, v in loop_items(g.target, g.iter)})
            return self.is_text(e.elt, inner, line, depth + 1)
        if not isinstance(e, ast.Call):
            return False
        name = _name(e)
        if name in TEXTS:
            return True
        if name == "attach":
            return bool(e.args) and self.is_text(e.args[0], env, line, depth + 1)
        if name in ("VGroup", "Group"):
            return bool(e.args) and all(self.is_text(a, env, line, depth + 1) for a in e.args)
        if isinstance(e.func, ast.Attribute) and not (isinstance(e.func.value, ast.Name)
                                                      and e.func.value.id in ("self", "scene")):
            return self.is_text(e.func.value, env, line, depth + 1)      # a mobject's method returns the mobject
        return name in self.funcs and self.returns_text(name, depth)       # a helper, or the scene's own method


def picture_key(e: ast.AST) -> str:
    """The object an expression shows: dot.copy() and dot are one picture, m.frame and m.readout parts of one."""
    node = e
    while True:
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            node = node.func.value
        elif isinstance(node, ast.Subscript):
            node = node.value
        elif isinstance(node, ast.Attribute):
            if isinstance(node.value, ast.Name) and node.value.id == "self":
                return f"self.{node.attr}"
            node = node.value
        else:
            break
    return node.id if isinstance(node, ast.Name) else ast.unparse(e)


def revealed(node: ast.AST, src: Source, env: dict, stagger: bool = False) -> list[tuple[str, int, bool]]:
    """(picture, kind, one after another) of each picture an animation reveals, texts left out; kind 0 is one picture,
    1 the members of one collection (a name, starred or looped over), 2 several separately named ones."""
    line = getattr(node, "lineno", 0)

    def picture(e) -> bool:
        return not src.is_text(e, env, line)

    def several(e) -> int:
        return 1 if isinstance(e, (ast.Name, ast.Attribute, ast.Subscript)) else 2
    if isinstance(node, ast.Starred):
        v = node.value
        if isinstance(v, (ast.ListComp, ast.GeneratorExp)) and isinstance(v.elt, ast.Call) and v.generators \
                and _name(v.elt) in REVEALS and v.elt.args:
            gen, target = v.generators[0], v.elt.args[0]
            loop = isinstance(target, ast.Name) and isinstance(gen.target, ast.Name) and target.id == gen.target.id
            if picture(gen.iter if loop else target):
                return [(ast.unparse(gen.iter), several(gen.iter), stagger)]
        elif isinstance(v, ast.Call) and _name(v) == "map" and len(v.args) > 1 and isinstance(v.args[0], ast.Name) \
                and v.args[0].id in REVEALS and picture(v.args[1]):
            return [(ast.unparse(v.args[1]), several(v.args[1]), stagger)]
        return []
    if not isinstance(node, ast.Call):
        return []
    name, out = _name(node), []
    if name in REVEALS:
        for t in (node.args if name == "FadeIn" else node.args[:1]):
            if isinstance(t, ast.Starred):
                if picture(t.value):
                    out.append((ast.unparse(t.value), several(t.value), stagger))
            elif picture(t):
                out.append((picture_key(t), 0, stagger))
    elif name == "LaggedStartMap":
        if len(node.args) > 1 and isinstance(node.args[0], ast.Name) and node.args[0].id in REVEALS \
                and picture(node.args[1]):
            out.append((ast.unparse(node.args[1]), several(node.args[1]), True))
    elif name in GROUPS:
        lag = next((k.value for k in node.keywords if k.arg == "lag_ratio"), None)
        st = stagger or name in STAGGERS or (lag is not None and not (isinstance(lag, ast.Constant) and not lag.value))
        for a in node.args:
            out += revealed(a, src, env, st)
    return out


def events(body: list, local: set) -> list[tuple[str, ast.Call]]:
    """("sync" | "play" | "timed", call) in source order: the calls that let time pass in a voiceover block."""
    out = []

    def kind(c: ast.Call) -> str | None:
        f, name = c.func, _name(c)
        scene = isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name) and f.value.id in ("self", "scene")
        if scene and (name in SYNCS or name == "wait" and any(
                isinstance(x, ast.Call) and _name(x) in WORD_TIMES for x in ast.walk(c) if x is not c)):
            return "sync"
        if scene and name == "play":
            return "play"
        if scene and name in TIMED | local or isinstance(f, ast.Name) and f.id in local:
            return "timed"
        return "timed" if any(isinstance(a, ast.Name) and a.id in ("self", "scene") for a in c.args) else None

    def visit(node):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)):
            return
        for child in ast.iter_child_nodes(node):
            visit(child)
        k = kind(node) if isinstance(node, ast.Call) else None
        if k:
            out.append((k, node))
    for st in body:
        visit(st)
    return out


def run_time(call: ast.Call) -> float | str | None:
    """A play's seconds when written as a number (1 when not given), "word" when it runs until a word, else None."""
    rt = next((k.value for k in call.keywords if k.arg == "run_time"), None)
    if rt is None:
        return 1.0
    if any(isinstance(x, ast.Call) and _name(x) in WORD_TIMES for x in ast.walk(rt)):
        return "word"
    return float(rt.value) if isinstance(rt, ast.Constant) and isinstance(rt.value, (int, float)) else None


def unanchored(files: list[Path], fd: checks.Findings, window: float = DEFAULTS["lead_max_s"]) -> int:
    """Plays inside voiceover blocks that reveal several pictures off the words that name them: more than `window`
    seconds after the last word timed in the block, with another wait in between, or one after another from it."""
    src, seen = Source(files), set()
    for f, exc in src.broken.items():
        fd.add("source", "warning", f.name, f"not checked: the file does not parse ({exc.msg}, line {exc.lineno})")
    for f, tree in src.trees.items():
        for cls in (n for n in tree.body if isinstance(n, ast.ClassDef)):
            methods = {n.name for n in cls.body if isinstance(n, ast.FunctionDef)}
            for fn in (n for n in cls.body if isinstance(n, ast.FunctionDef)):
                env = assignments(fn)
                local = methods | {n.name for n in ast.walk(fn) if isinstance(n, ast.FunctionDef) and n is not fn}
                for w in (n for n in ast.walk(fn) if isinstance(n, ast.With)
                          and any(_name(it.context_expr) == "voiceover" for it in n.items)):
                    since = None                     # seconds since the last word timed, None: no word in reach
                    for k, call in events(w.body, local):
                        if k != "play":
                            since = 0.0 if k == "sync" else None
                            continue
                        rt, start = run_time(call), since
                        timed = start is not None and isinstance(rt, float)
                        since = 0.0 if rt == "word" else start + rt if timed else None
                        if (f, call.lineno) in seen:
                            continue
                        pics: dict[str, tuple[int, bool]] = {}
                        for a in call.args:
                            for key, kind, st in revealed(a, src, env):
                                old = pics.get(key, (0, False))
                                pics[key] = (max(old[0], kind), old[1] or st)
                        n = sum(2 if kind else 1 for kind, _ in pics.values())
                        near = start is not None and start <= window
                        turns = sum(2 if kind == 2 else 1 for kind, st in pics.values() if st)  # a collection: one
                        if n < 2 or near and turns < 2:
                            continue
                        seen.add((f, call.lineno))
                        staggered = turns > 0
                        names = ", ".join(f"{k}[...]" if kind else k for k, (kind, _) in pics.items())
                        how = ("one after another from one word" if near else
                               "one after another, tied to no word" if staggered else "at once, tied to no word")
                        fd.add("unanchored", "warning", cls.name, f"{f.name}:{call.lineno}: one play() shows "
                               f"{'several' if n > len(pics) else n} pictures ({names}) {how}: show each as the "
                               "narration names it, self.wait_until_word('<its words>') before its own play()",
                               file=f.name, line=call.lineno)
    return len(seen)


# --------------------------------------------------------------------------- report

def check(run: Path, stage: str, cfg: dict) -> tuple[checks.Findings, dict]:
    fd = Findings()
    tl = timeline(run, stage)
    stats = early(tl, cfg, fd)
    files = checks.scene_files(run)
    stats["unanchored"] = unanchored(files, fd, float(cfg["lead_max_s"]))
    stats["layout_sha256"] = tl["layout_sha256"]
    stats["scene_sha256"] = {f.name: sha256_file(f) for f in files}
    return fd, stats


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run", nargs="?")
    ap.add_argument("--stage", choices=["draft", "final"], default="draft")
    ap.add_argument("--scenes", help="a folder of scene files: the source rule alone")
    ap.add_argument("--out", help="output folder (default review/design/<stage>/; with --scenes: none)")
    a = ap.parse_args()
    cfg = settings()
    if a.scenes:
        folder = Path(a.scenes)
        if not folder.is_dir():
            ap.error(f"no such folder: {a.scenes}")
        fd, stage = Findings(), "scenes"
        files = [f for f in sorted(folder.glob("*.py")) if f.name not in checks.HELPERS]
        stats = {"unanchored": unanchored(files, fd, float(cfg["lead_max_s"]))}
        out = Path(a.out) if a.out else None
        sha = {}
    elif a.run:
        run = resolve_run(a.run)
        stage = a.stage
        fd, stats = check(run, stage, cfg)
        out = Path(a.out) if a.out else run / "review" / "design" / stage
        sha = {"layout_sha256": stats.pop("layout_sha256"), "scene_sha256": stats.pop("scene_sha256")}
    else:
        ap.error("give a run or --scenes")
    n_err, n_warn = checks.summary(fd.items).values()
    for x in fd.items:
        print(f"{x['severity']} {x['rule']} {x['where']}{'' if x['t'] is None else ' t=' + str(x['t']) + 's'}: "
              f"{x['detail']}")
    if out is not None:
        md = [f"# Picture and word sync ({stage})", "", f"{n_err} error(s), {n_warn} warning(s); thresholds in "
              "config/video.json \"sync\" (lead_max_s, errors_block_gate).", ""]
        if "items" in stats:
            md.append(f"- labels and equations with words: {stats['items']}, said in the narration: "
                      f"{stats['spoken']}, shown more than {cfg['lead_max_s']:g} s before their words: "
                      f"{stats['early']}; median lead of the words over the picture: {stats['median_lead_s']} s")
        md.append(f"- plays showing several pictures off their words: {stats['unanchored']}")
        if fd.items:
            md += [""] + checks.md_table(["Severity", "Rule", "Where", "t (s)", "Detail"], (
                [x["severity"], x["rule"], x["where"], "" if x["t"] is None else x["t"], x["detail"]]
                for x in fd.items))
        checks.write_report(out, "check_sync", stage, fd.items, md, stats=stats, **sha)
    where = f"; {rel(out / 'check_sync.md')}" if out is not None else ""
    print(f"check_sync ({stage}): {n_err} error(s), {n_warn} warning(s){where}")
    return 1 if n_err else 0


if __name__ == "__main__":
    sys.exit(main())
