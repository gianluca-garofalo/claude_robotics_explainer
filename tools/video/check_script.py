#!/usr/bin/env python3
"""Spoken-script checks of a run's narration: is it written for the ear? (thresholds in config/video.json "script";
report only, like the engagement checks).

Usage:
  python3 tools/video/check_script.py runs/<run> --stage draft     # the voiceover strings of video/scenes/*.py
  python3 tools/video/check_script.py runs/<run> --stage final     # the same, plus the narration audio in video/voice/
  options: --out DIR (default review/design/<stage>/), --json (print the stats as JSON)

Why: the owner found episode 1's narration (v5) unnatural to listen to, and an A/B with the same Azure voice showed the
script was the main cause: colons, semicolons and brackets used as pauses, runs of short flat sentences, few
contractions and connectives, and stock phrases the other checks require ("start again from the same point" even in
the hook, where nothing had started). These checks measure those habits on the voiceover strings; the rubric that
the reviewers score (.claude/skills/manim-video-producer/spoken-script.md) covers what a count cannot.

  pauses        pause punctuation (":" ";" brackets, dashes) per 100 words above pause_punct_per_100_warn (error
                above pause_punct_per_100_error): a listener hears punctuation only as the voice's pauses, and a
                synthetic voice places odd ones at colons and brackets. Say "which means", "so", "that's"
  contractions  contractions (it's, here's, can't ...) per 100 words below contractions_per_100_min, or below
                contraction_share_min of the places where one fits ("it is", "do not", "cannot" ... before another
                word): written English, not spoken
  connectives   clause connectives (so, but, because, which means, then, yet, still, instead ...; a sentence that
                opens with "And") per 100 words below connectives_per_100_min: sentences that do not lean on each
                other sound like a list
  rhythm        sentence length (words): mean outside sentence_mean_min..sentence_mean_max, spread (standard
                deviation) below sentence_spread_min (over the narration, and in every scene of at least
                scene_spread_min_sentences sentences), and every run of short_run_min or more consecutive sentences
                under short_sentence_words words (within a scene, across its blocks)
  stock         a phrase of stock_ngram words said in two or more scenes (refrain_allow lists the deliberate
                refrains, such as the meter's label), a plan.json metaphor_resets "says" used by two or more
                scenes, and every phrase of stock_phrases (generic wording the checks once required): word each
                required beat (meter resets, title beat, teaser) for its own scene
  hype          words of hype_words (amazing, incredible, mind-blowing, obviously ...): a calm, honest register
  pace (final)  words per minute of each block and of the whole narration (video/voice/manifest.json): outside
                wpm_min..wpm_max overall is a warning, a block outside block_wpm_min..block_wpm_max too
  mid pauses    (final) a pause longer than mid_pause_max_s inside a sentence (not after . ? ! or an ellipsis, the
                planned beat): from the word timings with durations (Azure), else from the audio's silences
                (ffmpeg silencedetect at silence_db) placed with the estimated timings (Piper, recordings)
Writes <out>/check_script.json and .md; the JSON records the SHA-256 of every scene file read, so tools/gate.py can
tell a stale report. Exit status 1 when there is an error (the gate reports it; it blocks only when
script.errors_block_gate is true).
"""
from __future__ import annotations

import argparse
import json
import math
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
from _common import CONFIG, load_json, rel, resolve_run, sha256_file, utc_now, write_json  # noqa: E402
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
SENTENCE_END = re.compile(r"(?:[.!?]+|\.\.\.|…)[\"'’)\]]*(?=\s|$)")
PAUSE_PUNCT = re.compile(r"(?<!\d):(?!\d)|;|\(|\[|—|–|\s-\s|--")
CONTRACTION = re.compile(r"\b(?:\w+n['’]t|(?:it|that|here|there|what|who|where|how|let|he|she)['’]s|"
                         r"(?:i|you|we|they)['’](?:re|ve|ll|d)|(?:it|that|there)['’](?:ll|d)|i['’]m|"
                         r"(?:you|we|they)['’]re)\b", re.I)
# places where a contraction fits: before another word (a stressed "it is." at a sentence end does not contract)
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


class Findings:
    def __init__(self):
        self.items: list[dict] = []

    def add(self, check: str, severity: str, where: str, detail: str):
        self.items.append({"check": check, "severity": severity, "where": where, "detail": detail})


# --------------------------------------------------------------------------- text measures

def clean(text: str) -> str:
    return " ".join(BOOKMARK.sub("", text).split())


def words(text: str) -> list[str]:
    return WORD.findall(text)


def sentences(text: str) -> list[str]:
    """Sentences of a text: they end at . ! ? or an ellipsis followed by a space or the end (decimals stay whole)."""
    out, start = [], 0
    for m in SENTENCE_END.finditer(text):
        if text[start:m.end()].strip():
            out.append(text[start:m.end()].strip())
        start = m.end()
    if text[start:].strip():
        out.append(text[start:].strip())
    return out


def per100(n: int, w: int) -> float:
    return round(100.0 * n / w, 2) if w else 0.0


def measure(text: str) -> dict:
    """Counts of one text (a block, a scene or the whole narration)."""
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
    """Phrases of n or more words said in two or more of the texts [(name, text)]: [(phrase, [names])], each
    phrase reported once, from the first text that says it, as the longest run of shared n-grams."""
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
    """[{"class", "file", "role", "blocks": [text, ...], "resets": [says, ...]}] in plan order (all scene classes
    with narration when there is no plan.json)."""
    scenes_dir = run / "video" / "scenes"
    plan_p = run / "video" / "plan.json"
    plan = json.loads(plan_p.read_text(encoding="utf-8")) if plan_p.exists() else {}
    by_class = {}
    for f in sorted(scenes_dir.glob("*.py")):
        if f.name in ("common.py", "voice.py", "reading_model.py"):
            continue
        for cls, blocks in VS.blocks_by_class(f).items():
            if blocks:
                by_class[cls] = (f, blocks)
    out = []
    order = [s for s in plan.get("scenes", []) if s.get("class") in by_class] if plan.get("scenes") else \
        [{"class": c} for c in by_class]
    for s in order:
        f, blocks = by_class[s["class"]]
        out.append({"class": s["class"], "file": f.name, "role": s.get("role", "body"), "blocks": blocks,
                    "resets": [r.get("says", "") for r in s.get("metaphor_resets", []) if r.get("says")]})
    return out


def scene_hashes(run: Path) -> dict:
    return {f.name: sha256_file(f) for f in sorted((run / "video" / "scenes").glob("*.py"))
            if f.name not in ("common.py", "voice.py", "reading_model.py")}


# --------------------------------------------------------------------------- audio (final stage)

def _ends_sentence(word: str) -> bool:
    w = word.rstrip("\"'’)]")
    return w.endswith((".", "?", "!", "…"))


def silences(audio: Path, db: float, min_s: float) -> list[tuple[float, float]]:
    """(start, end) of silences of at least min_s in an audio file (ffmpeg silencedetect)."""
    try:
        out = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(audio), "-af",
                              f"silencedetect=noise={db}dB:d={min_s}", "-f", "null", "-"],
                             capture_output=True, text=True, check=True).stderr
    except (OSError, subprocess.CalledProcessError):
        return []
    starts = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", out)]
    ends = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", out)]
    return list(zip(starts, ends))


def mid_pauses(bounds: list[dict], audio: Path | None, cfg: dict) -> tuple[list[dict], str]:
    """Pauses longer than mid_pause_max_s inside a sentence of one block: [{"after", "pause_s", "at_s"}], and how
    they were measured ("reported" word durations, or "silences" of the audio placed with estimated timings)."""
    words_ = [b for b in bounds if re.search(r"\w", str(b.get("text", "")))]
    tick = 10_000_000
    found = []
    if words_ and all("duration_milliseconds" in b for b in words_):
        for a, b in zip(words_, words_[1:]):
            end_a = a["audio_offset"] / tick + a["duration_milliseconds"] / 1000.0
            gap = b["audio_offset"] / tick - end_a
            if gap > cfg["mid_pause_max_s"] and not _ends_sentence(a["text"]):
                found.append({"after": a["text"], "pause_s": round(gap, 2), "at_s": round(end_a, 2)})
        return found, "reported"
    if audio is None or not words_:
        return [], "none"
    for s0, s1 in silences(audio, cfg["silence_db"], cfg["mid_pause_max_s"]):
        if s0 <= 0.05:
            continue                                   # leading silence
        prev = [b for b in words_ if b["audio_offset"] / tick <= s0]
        nxt = [b for b in words_ if b["audio_offset"] / tick >= s1 - 0.15]
        if not prev or not nxt:
            continue                                   # trailing silence
        if not _ends_sentence(prev[-1]["text"]):
            found.append({"after": prev[-1]["text"], "pause_s": round(s1 - s0, 2), "at_s": round(s0, 2)})
    return found, "silences"


def audio_stats(run: Path, scenes: list[dict], cfg: dict, fd: Findings) -> dict | None:
    """Pace and mid-sentence pauses of the synthesized or recorded narration (video/voice/)."""
    vdir = run / "video" / "voice"
    man_p = vdir / "manifest.json"
    if not man_p.exists():
        fd.add("pace", "warning", "video/voice", "no narration audio (video/voice/manifest.json): run "
               "tools/video/synthesize_voice.py first; pace and pauses not measured")
        return None
    man = json.loads(man_p.read_text(encoding="utf-8"))
    blocks = man.get("blocks", {})
    total_w, total_s, per_scene, pauses, how = 0, 0.0, {}, [], set()
    for sc in scenes:
        sw, ss = 0, 0.0
        for text in sc["blocks"]:
            key = VS.key(text)
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
            found, method = mid_pauses(bounds, audio if audio and audio.exists() else None, cfg)
            how.add(method)
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
            "mid_pauses": len(pauses), "longest_mid_pause_s": max((p["pause_s"] for p in pauses), default=0.0),
            "pause_method": sorted(how - {"none"}) or ["none"]}


# --------------------------------------------------------------------------- the checks

def check(run: Path, stage: str, cfg: dict) -> tuple[Findings, dict]:
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


def report_md(stage: str, fd: Findings, stats: dict) -> str:
    errs = [x for x in fd.items if x["severity"] == "error"]
    warns = [x for x in fd.items if x["severity"] == "warning"]
    w = stats["whole"]
    md = [f"# Spoken script ({stage})", "",
          f"{len(errs)} error(s), {len(warns)} warning(s); thresholds in config/video.json \"script\"; the rubric "
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
                  f"mid-sentence pauses over the limit: {a['mid_pauses']} (longest {a['longest_mid_pause_s']} s; "
                  f"measured from {', '.join(a['pause_method'])})")
    md += ["", "| Scene | Words | Pause punct /100 | Contractions /100 | Connectives /100 | Sentence mean / spread | "
           "Short runs |" + (" wpm |" if a else ""), "|---|---|---|---|---|---|---|" + ("---|" if a else "")]
    for c, v in stats["scenes"].items():
        md.append(f"| {c} | {v['words']} | {v['pause_punct_per_100']} | {v['contractions_per_100']} | "
                  f"{v['connectives_per_100']} | {v['sentence_mean']} / {v['sentence_spread']} | "
                  f"{len(v['short_runs'])} |" + (f" {a['wpm_by_scene'].get(c) or '-'} |" if a else ""))
    if fd.items:
        md += ["", "| Severity | Check | Where | Detail |", "|---|---|---|---|"]
        order = {"error": 0, "warning": 1, "info": 2}
        md += [f"| {x['severity']} | {x['check']} | {x['where']} | {x['detail'].replace('|', '/')} |"
               for x in sorted(fd.items, key=lambda x: order[x["severity"]])]
    return "\n".join(md) + "\n"


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
    errs = [x for x in fd.items if x["severity"] == "error"]
    warns = [x for x in fd.items if x["severity"] == "warning"]
    out = Path(a.out) if a.out else run / "review" / "design" / a.stage
    out.mkdir(parents=True, exist_ok=True)
    write_json(out / "check_script.json", {
        "schema_version": 1, "tool": "check_script", "stage": a.stage, "checked_at": utc_now(), "passed": not errs,
        "summary": {"errors": len(errs), "warnings": len(warns)}, "scene_sha256": stats.pop("scene_sha256"),
        "stats": stats, "findings": fd.items})
    (out / "check_script.md").write_text(report_md(a.stage, fd, stats), encoding="utf-8")
    if a.json:
        print(json.dumps(stats, indent=2))
    for x in fd.items:
        if x["severity"] != "info":
            print(f"{x['severity']} {x['check']} {x['where']}: {x['detail']}")
    print(f"check_script ({a.stage}): {len(errs)} error(s), {len(warns)} warning(s); {rel(out / 'check_script.md')}")
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())
