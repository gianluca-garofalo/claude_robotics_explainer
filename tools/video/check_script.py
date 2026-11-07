#!/usr/bin/env python3
"""Spoken-script checks of a run's narration: is it written for the ear?

Usage:
  python3 tools/video/check_script.py runs/<run> --stage draft|final [--out DIR] [--json]

Checks: pauses, contractions, connectives, rhythm, stock, hype; at the final stage also pace and mid pause, from the
narration audio in video/voice/ (thresholds in config/video.json "script"). Exit status 1 on an error.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import subprocess
import sys
from functools import partial
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
from _common import CONFIG, load_json, rel, resolve_run, sha256_file  # noqa: E402
import checks  # noqa: E402
import voice_script as VS  # noqa: E402

DEFAULTS = {
    "errors_block_gate": False,
    "pause_punct_per_100_warn": 1.0, "pause_punct_per_100_error": 3.0,
    "contractions_per_100_min": 1.5, "contraction_share_min": 0.5,
    "connectives_per_100_min": 3.0,
    "sentence_mean_min": 10.0, "sentence_mean_max": 22.0, "sentence_spread_min": 5.0,
    "short_sentence_words": 8, "short_run_min": 3, "scene_spread_min_sentences": 5,
    "stock_ngram": 5,
    "refrain_allow": ["what is left to pay", "left to pay", "by at least what that step costs",
                      "at least what that step costs", "at least what the step costs"],
    "stock_phrases": ["start again from the same point", "watch one number", "here is the trick",
                      "here's the trick", "let's build it", "as we will see", "it turns out that",
                      "in this video", "without further ado", "let's dive in", "buckle up"],
    "hype_words": ["amazing", "incredible", "incredibly", "mind-blowing", "mind blowing", "insane", "crazy",
                   "unbelievable", "shocking", "stunning", "epic", "revolutionary", "game-changer", "game changer",
                   "game-changing", "genius", "magic", "magical", "secret", "ultimate", "obviously", "trivially",
                   "trivial", "simply put", "super easy", "you won't believe"],
    "wpm_min": 140.0, "wpm_max": 160.0, "block_wpm_min": 120.0, "block_wpm_max": 180.0,
    "mid_pause_max_s": 0.7, "mid_pause_error_s": 1.5, "silence_db": -40.0,
}

BOOKMARK = VS.BOOKMARK
WORD = re.compile(r"[A-Za-z0-9][A-Za-z0-9'’\-]*")
PAUSE_PUNCT = re.compile(r"(?<!\d):(?!\d)|;|\(|\[|—|–|\s-\s|--")
CONTRACTION = re.compile(r"\b(?:\w+n['’]t|(?:it|that|here|there|what|who|where|how|let|he|she)['’]s|"
                         r"(?:i|you|we|they)['’](?:re|ve|ll|d)|(?:it|that|there)['’](?:ll|d)|i['’]m|"
                         r"(?:you|we|they)['’]re)\b", re.I)
# where a contraction fits: before another word (a stressed "it is." at a sentence end does not contract)
UNCONTRACTED = re.compile(r"\b(?:(?:it|that|here|there|what) is|let us|(?:we|you|they) are|(?:we|you|they|i) have"
                          r"(?= (?:got|been|seen|done|made|found|paid|shown|used|built)\b)|(?:do|does|did|is|are|was|"
                          r"were|has|have|had|would|could|should|will) not|cannot|i am|(?:it|that|we|you|they) will)"
                          r"(?=\s+[A-Za-z])", re.I)
CONNECTIVES = ["so", "but", "because", "which means", "that means", "meaning", "then", "yet", "still", "instead",
               "since", "though", "although", "even so", "otherwise", "that's why", "which is why", "after all",
               "in other words", "that way", "this way", "now", "until", "unless", "while", "whereas", "which"]
CONNECTIVE = re.compile(r"\b(?:" + "|".join(re.escape(c).replace(r"\ ", r"\s+").replace("'", "['’]")
                                            for c in sorted(CONNECTIVES, key=len, reverse=True)) + r")\b", re.I)
AND_OPENER = re.compile(r"(?:^|(?<=[.!?…]\s))\s*And\b")


def settings() -> dict:
    cfg = dict(DEFAULTS)
    cfg.update({k: v for k, v in load_json(CONFIG / "video.json").get("script", {}).items() if not k.startswith("_")})
    return cfg


Findings = partial(checks.Findings, "check", "severity", "where", "detail")


# --------------------------------------------------------------------------- text measures

def clean(text: str) -> str:
    return " ".join(BOOKMARK.sub("", text).split())


def words(text: str) -> list[str]:
    return WORD.findall(text)


def sentences(text: str) -> list[str]:
    ws = text.split()
    return [" ".join(ws[a:b + 1]) for a, b in checks.sentences(ws)]


def per100(n: int, w: int) -> float:
    return round(100.0 * n / w, 2) if w else 0.0


def measure(text: str) -> dict:
    """Counts of a block, a scene or the whole narration."""
    t = clean(text)
    w = len(words(t))
    pauses = PAUSE_PUNCT.findall(t)
    con = CONTRACTION.findall(t)
    missed = UNCONTRACTED.findall(t)
    conn = CONNECTIVE.findall(t) + AND_OPENER.findall(t)
    lens = [len(words(s)) for s in sentences(t)]
    lens = [n for n in lens if n]
    mean = sum(lens) / len(lens) if lens else 0.0
    sd = math.sqrt(sum((n - mean) ** 2 for n in lens) / len(lens)) if lens else 0.0
    return {"words": w, "pause_punct": len(pauses), "pause_punct_per_100": per100(len(pauses), w),
            "contractions": len(con), "contractions_per_100": per100(len(con), w), "uncontracted": missed,
            "contraction_share": round(len(con) / (len(con) + len(missed)), 2) if con or missed else None,
            "connectives": len(conn), "connectives_per_100": per100(len(conn), w),
            "sentences": len(lens), "sentence_mean": round(mean, 1), "sentence_spread": round(sd, 1),
            "sentence_lengths": lens}


def short_runs(sents: list[str], max_words: int, min_run: int) -> list[list[str]]:
    """Runs of min_run or more consecutive sentences under max_words words."""
    runs, cur = [], []
    for s in sents + [None]:
        if s is not None and len(words(s)) < max_words:
            cur.append(s)
            continue
        if len(cur) >= min_run:
            runs.append(cur)
        cur = []
    return runs


def _norm_words(text: str) -> list[str]:
    return [x.lower().replace("’", "'") for x in words(clean(text))]


def repeated_phrases(texts: list[tuple[str, str]], n: int) -> list[tuple[str, list[str]]]:
    """[(phrase, [names])] of the phrases of n or more words that two or more of [(name, text)] say."""
    grams: dict[str, set[str]] = {}
    toks = [(name, _norm_words(t)) for name, t in texts]
    for name, w in toks:
        for i in range(len(w) - n + 1):
            grams.setdefault(" ".join(w[i:i + n]), set()).add(name)
    out, done = [], set()
    for name, w in toks:
        shared = [len(grams.get(" ".join(w[i:i + n]), ())) > 1 for i in range(len(w) - n + 1)]
        i = 0
        while i < len(shared):
            if not shared[i]:
                i += 1
                continue
            j = i
            while j + 1 < len(shared) and shared[j + 1]:
                j += 1
            phrase = " ".join(w[i:j + n])
            names = sorted(set.intersection(*[grams[" ".join(w[k:k + n])] for k in range(i, j + 1)]) or {name})
            if phrase not in done and not any(phrase in d for d in done):
                done.add(phrase)
                out.append((phrase, sorted(set(names) | {name})))
            i = j + 1
    return out


def phrase_in(phrase: str, text: str) -> bool:
    norm = lambda s: " ".join(x.lower().replace("’", "'") for x in words(s))  # noqa: E731
    return f" {norm(phrase)} " in f" {norm(text)} "


# --------------------------------------------------------------------------- the run's narration

def narration(run: Path) -> list[dict]:
    """[{"class", "file", "role", "blocks", "raw", "resets"}] of the scenes with narration, in plan order."""
    plan_p = run / "video" / "plan.json"
    plan = json.loads(plan_p.read_text(encoding="utf-8")) if plan_p.exists() else {}
    by_class = {}
    for f in checks.scene_files(run):
        for cls, blocks in VS.blocks_by_class(f, markup=True).items():
            if blocks:
                by_class[cls] = (f, blocks)
    out = []
    order = [s for s in plan.get("scenes", []) if s.get("class") in by_class] if plan.get("scenes") else \
        [{"class": c} for c in by_class]
    for s in order:
        f, raws = by_class[s["class"]]
        out.append({"class": s["class"], "file": f.name, "role": s.get("role", "body"),
                    "blocks": [VS.spoken(t) for t in raws], "raw": raws,
                    "resets": [r.get("says", "") for r in s.get("metaphor_resets", []) if r.get("says")]})
    return out


def scene_hashes(run: Path) -> dict:
    return {f.name: sha256_file(f) for f in checks.scene_files(run)}


# --------------------------------------------------------------------------- audio (final stage)

def silences(audio: Path, db: float, min_s: float) -> list[tuple[float, float]]:
    try:
        return checks.silences(audio, db, min_s)
    except (OSError, subprocess.CalledProcessError):
        return []


def planned_offsets(raw: str, cfg: dict) -> list[int]:
    """Text offsets of the words a planned pause ("[pause S]", an ellipsis) comes before."""
    starts = VS.VOICE._word_starts(raw)
    return sorted(starts[n] for n in VS.VOICE.pause_plan(raw, cfg.get("ellipsis_pause_s", 0.7)) if n < len(starts))


def mid_pauses(bounds: list[dict], audio: Path | None, cfg: dict, planned: list[int] | None = None) \
        -> tuple[list[dict], str, float]:
    """(pauses over mid_pause_max_s inside a sentence, how they were measured, the longest pause inside one)."""
    words_ = [b for b in bounds if re.search(r"\w", str(b.get("text", "")))]
    planned = planned or []
    tick = 10_000_000
    found, longest = [], 0.0

    def is_planned(a, b):
        return any(a.get("text_offset", -1) < o <= b.get("text_offset", -1) for o in planned)
    if words_ and all("duration_milliseconds" in b for b in words_):
        for a, b in zip(words_, words_[1:]):
            end_a = a["audio_offset"] / tick + a["duration_milliseconds"] / 1000.0
            gap = b["audio_offset"] / tick - end_a
            if checks.sentence_end(a["text"]) or is_planned(a, b):
                continue
            longest = max(longest, gap)
            if gap > cfg["mid_pause_max_s"]:
                found.append({"after": a["text"], "pause_s": round(gap, 2), "at_s": round(end_a, 2)})
        return found, "reported", round(longest, 2)
    if audio is None or not words_:
        return [], "none", 0.0
    for s0, s1 in silences(audio, cfg["silence_db"], min(0.25, cfg["mid_pause_max_s"])):
        if s0 <= 0.05:
            continue                                   # leading silence
        prev = [b for b in words_ if b["audio_offset"] / tick <= s0]
        nxt = [b for b in words_ if b["audio_offset"] / tick >= s1 - 0.15]
        if not prev or not nxt:
            continue                                   # trailing silence
        if checks.sentence_end(prev[-1]["text"]) or is_planned(prev[-1], nxt[0]):
            continue
        longest = max(longest, s1 - s0)
        if s1 - s0 > cfg["mid_pause_max_s"]:
            found.append({"after": prev[-1]["text"], "pause_s": round(s1 - s0, 2), "at_s": round(s0, 2)})
    return found, "silences", round(longest, 2)


def audio_stats(run: Path, scenes: list[dict], cfg: dict, fd: checks.Findings) -> dict | None:
    """Pace and mid-sentence pauses of the narration audio in video/voice/."""
    vdir = run / "video" / "voice"
    man_p = vdir / "manifest.json"
    if not man_p.exists():
        fd.add("pace", "warning", "video/voice", "no narration audio (video/voice/manifest.json): run "
               "tools/video/synthesize_voice.py first; pace and pauses not measured")
        return None
    man = json.loads(man_p.read_text(encoding="utf-8"))
    blocks = man.get("blocks", {})
    total_w, total_s, per_scene, pauses, how, longest = 0, 0.0, {}, [], set(), 0.0
    for sc in scenes:
        sw, ss = 0, 0.0
        for text, raw in zip(sc["blocks"], sc.get("raw") or sc["blocks"]):
            key = VS.key(raw)
            b = blocks.get(key)
            if not b:
                fd.add("pace", "warning", sc["class"], f"no audio for block {key} ({text[:50]!r}): stale narration")
                continue
            w = len(words(clean(text)))
            sec = float(b.get("seconds") or 0.0)
            sw, ss = sw + w, ss + sec
            if sec > 0:
                wpm = 60.0 * w / sec
                if w >= 8 and not cfg["block_wpm_min"] <= wpm <= cfg["block_wpm_max"]:
                    fd.add("pace", "warning", sc["class"], f"block {key} at {wpm:.0f} words per minute "
                           f"({cfg['block_wpm_min']:.0f}-{cfg['block_wpm_max']:.0f}): {clean(text)[:60]!r}")
            tp = vdir / f"{key}.timings.json"
            audio = vdir / b["file"] if b.get("file") else None
            bounds = json.loads(tp.read_text(encoding="utf-8")) if tp.exists() else []
            found, method, worst = mid_pauses(bounds, audio if audio and audio.exists() else None, cfg,
                                              planned_offsets(raw, cfg))
            how.add(method)
            longest = max(longest, worst)
            for p in found:
                sev = "error" if p["pause_s"] > cfg["mid_pause_error_s"] else "warning"
                fd.add("mid pause", sev, sc["class"], f"{p['pause_s']:.2f} s pause after {p['after']!r} inside a "
                       f"sentence (block {key}, at {p['at_s']:.1f} s; over {cfg['mid_pause_max_s']} s)")
                pauses.append(dict(p, block=key, scene=sc["class"]))
        per_scene[sc["class"]] = round(60.0 * sw / ss) if ss else None
        total_w, total_s = total_w + sw, total_s + ss
    wpm = 60.0 * total_w / total_s if total_s else None
    if wpm is not None and not cfg["wpm_min"] <= wpm <= cfg["wpm_max"]:
        fd.add("pace", "warning", "narration", f"{wpm:.0f} words per minute overall (about {cfg['wpm_min']:.0f}-"
               f"{cfg['wpm_max']:.0f})")
    return {"service": man.get("service"), "voice": man.get("voice_model") or man.get("voice"),
            "seconds": round(total_s, 1), "wpm": round(wpm) if wpm else None, "wpm_by_scene": per_scene,
            "mid_pauses": len(pauses), "longest_mid_pause_s": longest,
            "pause_method": sorted(how - {"none"}) or ["none"]}


# --------------------------------------------------------------------------- the checks

def check(run: Path, stage: str, cfg: dict) -> tuple[checks.Findings, dict]:
    fd = Findings()
    scenes = narration(run)
    whole = " ".join(" ".join(s["blocks"]) for s in scenes)
    stats = {"scenes": {}, "whole": measure(whole)}
    for sc in scenes:
        text = " ".join(sc["blocks"])
        m = measure(text)
        sents = [x for b in sc["blocks"] for x in sentences(clean(b))]
        m["short_runs"] = [len(r) for r in short_runs(sents, cfg["short_sentence_words"], cfg["short_run_min"])]
        stats["scenes"][sc["class"]] = {k: v for k, v in m.items() if k != "sentence_lengths"}
        if m["sentences"] >= cfg["scene_spread_min_sentences"] and m["sentence_spread"] < cfg["sentence_spread_min"]:
            fd.add("rhythm", "warning", sc["class"], f"{m['sentences']} sentences of {m['sentence_mean']} words on "
                   f"average, spread {m['sentence_spread']} (at least {cfg['sentence_spread_min']}): a flat rhythm")
        for r in short_runs(sents, cfg["short_sentence_words"], cfg["short_run_min"]):
            fd.add("rhythm", "warning", sc["class"], f"{len(r)} short sentences in a row (under "
                   f"{cfg['short_sentence_words']} words): " + " / ".join(x[:40] for x in r))
        for b in sc["blocks"]:
            c = clean(b)
            for mt in PAUSE_PUNCT.finditer(c):
                a = max(0, mt.start() - 30)
                fd.add("pauses", "info", sc["class"], f"{mt.group().strip()!r} as a pause: "
                       f"...{c[a:mt.end() + 25]}...")
            low = c.lower()
            for h in cfg["hype_words"]:
                if re.search(rf"\b{re.escape(h.lower())}\b", low):
                    fd.add("hype", "warning", sc["class"], f"hype word {h!r}: {c[:70]!r}")
            for p in cfg["stock_phrases"]:
                if phrase_in(p, c):
                    fd.add("stock", "warning", sc["class"], f"stock phrase {p!r}: word it for this scene")
            for u in UNCONTRACTED.findall(c):
                fd.add("contractions", "info", sc["class"], f"{u!r} could be contracted")
    w = stats["whole"]
    words_n = max(w["words"], 1)
    if w["pause_punct_per_100"] > cfg["pause_punct_per_100_warn"]:
        sev = "error" if w["pause_punct_per_100"] > cfg["pause_punct_per_100_error"] else "warning"
        fd.add("pauses", sev, "narration", f"{w['pause_punct']} colons, semicolons, brackets or dashes in "
               f"{words_n} words ({w['pause_punct_per_100']} per 100; at most {cfg['pause_punct_per_100_warn']})")
    if w["contractions_per_100"] < cfg["contractions_per_100_min"]:
        fd.add("contractions", "warning", "narration", f"{w['contractions']} contractions ({w['contractions_per_100']} "
               f"per 100 words; at least {cfg['contractions_per_100_min']})")
    if w["contraction_share"] is not None and w["contraction_share"] < cfg["contraction_share_min"]:
        fd.add("contractions", "warning", "narration", f"contracted in {w['contraction_share']:.0%} of the places "
               f"where a contraction fits (at least {cfg['contraction_share_min']:.0%})")
    if w["connectives_per_100"] < cfg["connectives_per_100_min"]:
        fd.add("connectives", "warning", "narration", f"{w['connectives']} connectives ({w['connectives_per_100']} "
               f"per 100 words; at least {cfg['connectives_per_100_min']})")
    if not cfg["sentence_mean_min"] <= w["sentence_mean"] <= cfg["sentence_mean_max"]:
        fd.add("rhythm", "warning", "narration", f"sentences average {w['sentence_mean']} words "
               f"({cfg['sentence_mean_min']}-{cfg['sentence_mean_max']})")
    if w["sentence_spread"] < cfg["sentence_spread_min"]:
        fd.add("rhythm", "warning", "narration", f"sentence length spread {w['sentence_spread']} words (at least "
               f"{cfg['sentence_spread_min']}): a flat rhythm")
    # stock: phrases said in more than one scene (overlapping n-grams merged into the whole phrase)
    phrases = repeated_phrases([(sc["class"], " ".join(sc["blocks"])) for sc in scenes], int(cfg["stock_ngram"]))
    allow = [a.lower() for a in cfg["refrain_allow"]]
    def refrain(ph: str) -> bool:                 # what is left once the deliberate refrains are taken out
        for a in allow:
            ph = ph.replace(a, " ")
        return len(ph.split()) < int(cfg["stock_ngram"])
    phrases = [(p, v) for p, v in phrases if not refrain(p)]
    for ph, v in phrases:
        fd.add("stock", "warning", ", ".join(v), f"{ph!r} said in {len(v)} scenes: vary it, or list it in "
               "script.refrain_allow if it is a deliberate refrain")
    says: dict[str, list[str]] = {}
    for sc in scenes:
        for s in sc["resets"]:
            says.setdefault(s.lower().strip(), []).append(sc["class"])
    for s, v in says.items():
        if len(v) > 1:
            fd.add("stock", "warning", ", ".join(v), f"the same meter-reset words {s!r} in {len(v)} scenes: each "
                   "reset says what really happens in its scene")
    stats["repeated_phrases"] = len(phrases)
    if stage == "final":
        a = audio_stats(run, scenes, cfg, fd)
        if a:
            stats["audio"] = a
    stats["scene_sha256"] = scene_hashes(run)
    return fd, stats


def report_md(stage: str, fd: checks.Findings, stats: dict) -> list[str]:
    n_err, n_warn = checks.summary(fd.items).values()
    w = stats["whole"]
    md = [f"# Spoken script ({stage})", "",
          f"{n_err} error(s), {n_warn} warning(s); thresholds in config/video.json \"script\"; the rubric "
          "is .claude/skills/manim-video-producer/spoken-script.md.", "",
          f"- {w['words']} words in {w['sentences']} sentences: mean {w['sentence_mean']} words, spread "
          f"{w['sentence_spread']}",
          f"- pause punctuation {w['pause_punct']} ({w['pause_punct_per_100']} per 100 words); contractions "
          f"{w['contractions']} ({w['contractions_per_100']} per 100, {w['contraction_share']} of the places that "
          f"fit); connectives {w['connectives']} ({w['connectives_per_100']} per 100)",
          f"- phrases repeated across scenes: {stats['repeated_phrases']}"]
    a = stats.get("audio")
    if a:
        md.append(f"- audio ({a['service']} {a.get('voice') or ''}): {a['seconds']} s, {a['wpm']} words per minute; "
                  f"mid-sentence pauses over the limit: {a['mid_pauses']}; the longest pause inside a sentence: "
                  f"{a['longest_mid_pause_s']} s (planned pauses left out; measured from "
                  f"{', '.join(a['pause_method'])})")
    md += [""] + checks.md_table(
        ["Scene", "Words", "Pause punct /100", "Contractions /100", "Connectives /100", "Sentence mean / spread",
         "Short runs"] + (["wpm"] if a else []),
        ([c, v["words"], v["pause_punct_per_100"], v["contractions_per_100"], v["connectives_per_100"],
          f"{v['sentence_mean']} / {v['sentence_spread']}", len(v["short_runs"])]
         + ([a["wpm_by_scene"].get(c) or "-"] if a else []) for c, v in stats["scenes"].items()))
    if fd.items:
        order = {"error": 0, "warning": 1, "info": 2}
        md += [""] + checks.md_table(["Severity", "Check", "Where", "Detail"], (
            [x["severity"], x["check"], x["where"], x["detail"]]
            for x in sorted(fd.items, key=lambda x: order[x["severity"]])))
    return md


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run")
    ap.add_argument("--stage", choices=["draft", "final"], default="draft")
    ap.add_argument("--out", help="output folder (default review/design/<stage>/)")
    ap.add_argument("--json", action="store_true", help="print the stats as JSON")
    a = ap.parse_args()
    run = resolve_run(a.run)
    cfg = settings()
    fd, stats = check(run, a.stage, cfg)
    n_err, n_warn = checks.summary(fd.items).values()
    out = Path(a.out) if a.out else run / "review" / "design" / a.stage
    sha = stats.pop("scene_sha256")
    checks.write_report(out, "check_script", a.stage, fd.items, report_md(a.stage, fd, stats), scene_sha256=sha,
                        stats=stats)
    if a.json:
        print(json.dumps(stats, indent=2))
    for x in fd.items:
        if x["severity"] != "info":
            print(f"{x['severity']} {x['check']} {x['where']}: {x['detail']}")
    print(f"check_script ({a.stage}): {n_err} error(s), {n_warn} warning(s); {rel(out / 'check_script.md')}")
    return 1 if n_err else 0


if __name__ == "__main__":
    sys.exit(main())
