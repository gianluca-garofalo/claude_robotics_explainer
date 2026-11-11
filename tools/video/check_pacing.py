#!/usr/bin/env python3
"""Pacing checks of a run's video: what it teaches per minute and the time it gives to take it in (rules P1-P20).

Usage:
  python3 tools/video/check_pacing.py runs/<run> --stage draft|final [--out DIR]

Rules (thresholds in config/video.json "pacing"):
  P1  results per video            P8  pauses between blocks       P15 roadmap, summaries, recap
  P2  starred results apart        P9  words per minute            P16 chapter lengths
  P3  claim rate and spacing       P10 reading rates, slow blocks  P17 share of pauses
  P4  concept rate, pretraining    P11 think prompts               P18 runtime against the idea budget
  P5  new terms                    P12 spoken numbers              P19 holds (check_engagement.py)
  P6  silence after results        P13 equation holds              P20 blocks to rewrite
  P7  stretches without a pause    P14 picture before words
  ideas, coverage, markup: declared ideas not found, detected ideas not declared, markup the voice cannot say;
  voice: blocks every take of which had a fault (video/voice/manifest.json).
Exit status 1 on an error.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import statistics
import sys
from functools import partial
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
from _common import CONFIG, load_json, rel, resolve_run, sha256_file  # noqa: E402
import checks  # noqa: E402
import idea_budget as IB  # noqa: E402
import plan as P  # noqa: E402
import voice_script as VS  # noqa: E402

VOICE = VS.VOICE
DEFAULTS = {
    "errors_block_gate": False,
    "stars_max": 2, "examples_max": 1, "side_max": 1, "star_spacing_s": 90.0,
    "claims_per_min": 1.5, "claims_window_s": 180.0, "claim_spacing_s": 20.0,
    "concepts_per_60": 2.0, "concepts_per_120": 4.0, "pretraining_per_60": 3.0, "pretraining_max": 5,
    "pretraining_break_s": 0.8, "pretraining_summary_break_s": 2.0, "rearrangement_weight": 0.5,
    "terms_per_sentence": 1, "terms_per_30": 2,
    "star_silence_s": 2.5, "star_silence_target_s": 3.0, "restatement_within_s": 10.0, "claim_silence_s": 1.5,
    "silence_long_s": 1.5, "stretch_warn_s": 45.0, "stretch_error_s": 90.0,
    "block_pause_median_s": 0.6, "block_vs_sentence_min": 0.9, "chapter_turn_pause_s": 1.0, "sentence_gap_min_s": 0.6,
    "body_wpm_max": 135.0,
    "rate_floor_pct": -20.0, "block_rate_min_pct": -15.0, "key_wpm_min": 120.0, "key_max_vs_median": 1.0,
    "slow_share_max": 0.67,
    "prompt_every_s": 240.0, "prompt_silence_s": 3.5, "main_prompt_silence_s": 4.0,
    "numbers_per_20": 3,
    "hold_min_s": 3.0, "hold_per_new_symbol_s": 1.0, "hold_per_familiar_s": 0.3, "hold_cap_s": 6.0,
    "picture_lead_max_s": 1.5,
    "roadmap_within_s": 20.0, "summary_chapter_s": 90.0, "chapter_s": [60.0, 120.0],
    "pause_share_min": 0.06,
    "silence_rel_db": -30.0, "silence_min_s": 0.25,
    "undeclared_window_s": 5.0,
    "claim_markers": ["so", "which means", "that means", "that's why", "therefore", "it follows", "this means"],
    "glossary": ["remaining action", "end cost", "end region", "reference step", "rest point", "one-step bill",
                 "stage cost", "terminal cost", "terminal set", "terminal region", "boundary term", "value function",
                 "principle of optimality", "lyapunov function", "asymptotically stable", "recursive feasibility",
                 "receding horizon", "model predictive control"],
}
RESULT_KINDS = ("claim", "star")
GREEK = {"alpha", "beta", "gamma", "delta", "epsilon", "varepsilon", "zeta", "eta", "theta", "vartheta", "iota",
         "kappa", "lambda", "mu", "nu", "xi", "pi", "varpi", "rho", "varrho", "sigma", "varsigma", "tau", "upsilon",
         "phi", "varphi", "chi", "psi", "omega", "Gamma", "Delta", "Theta", "Lambda", "Xi", "Pi", "Sigma", "Upsilon",
         "Phi", "Psi", "Omega", "infty", "nabla", "partial", "ell", "hbar"}
RELATION = re.compile(r"\\(?:leq?|geq?|neq?|lt|gt|approx|sim|simeq|equiv|propto|Longrightarrow|Rightarrow|"
                      r"Longleftrightarrow|Leftrightarrow|iff|implies|to|mapsto|in|subseteq?|supseteq?)(?![A-Za-z])"
                      r"|<=?|>=?|=")
OPERATOR = re.compile(r"\\(?:min|max|sum|int|prod|frac|dfrac|tfrac|cdot|times|sqrt|arg|inf|sup|lim)(?![A-Za-z])"
                      r"|(?<![\^_{])[+\-](?![)}])")
TEXT_GROUP = re.compile(r"\\(?:text|mathrm|operatorname|textrm|mbox|mathbf|mathit|textbf)\s*\{[^{}]*\}")
COMMAND = re.compile(r"\\([A-Za-z]+)")
SYMBOL = re.compile(r"(\\[A-Za-z]+|[A-Za-z])((?:\s*(?:_\{[^{}]*\}|_\\?[A-Za-z0-9]|\^\{[^{}]*\}|\^\\?[A-Za-z0-9+\-*]|'))*)")
NUMBER_WORDS = {"zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
                "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
                "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20, "thirty": 30,
                "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90, "hundred": 100,
                "half": 0.5}
VALUE_MARK = {"point", "percent", "hundred", "half"}
VALUE_BEFORE = {"at", "is", "are", "was", "of", "weight", "about", "exactly", "to", "from", "equals", "times", "by",
                "only", "just", "than", "against", "with"}


def settings() -> dict:
    cfg = dict(DEFAULTS)
    cfg.update({k: v for k, v in (load_json(CONFIG / "video.json").get("pacing") or {}).items()
                if not k.startswith("_") and k != "plan"})
    return cfg


Findings = partial(checks.Findings, "rule", "severity", "where", "detail", "t")


def mmss(t: float) -> str:
    return f"{int(t // 60)}:{t % 60:04.1f}"


def norm(text: str) -> str:
    """Lower case, hyphens and dashes as spaces, no punctuation but apostrophes."""
    t = str(text).lower().replace("’", "'")
    t = re.sub(r"[-‐‑–—/]", " ", t)
    return " ".join(re.sub(r"[^a-z0-9' ]+", " ", t).split())


# --------------------------------------------------------------------------- the timeline of the video

def timeline(run: Path, stage: str) -> dict:
    """Scenes, narration blocks (words with times), plays and on-screen items of the video, in seconds from its start."""
    plan = json.loads((run / "video" / "plan.json").read_text(encoding="utf-8"))
    folder = run / "video" / ("checks" if stage == "draft" else "renders")
    seg = {}
    asm = run / "video" / "final" / "assembly.json"
    if stage == "final" and asm.exists():
        seg = {s.get("class"): s for s in json.loads(asm.read_text(encoding="utf-8")).get("segments", [])}
    ell = VOICE.azure_settings((load_json(CONFIG / "channel.json").get("voice") or {}))["ellipsis_pause_s"]
    t, scenes, blocks, plays, items, hashes = 0.0, [], [], [], [], {}
    for s in plan.get("scenes", []):
        cls = s["class"]
        log, lp = checks.scene_log(folder, cls)
        if lp is not None:
            hashes[cls] = sha256_file(lp)
        off = float(seg[cls]["start"]) if cls in seg else t
        dur = float(seg[cls]["duration"]) if cls in seg else float(log.get("duration") or 0.0)
        sc = {"class": cls, "role": s.get("role") or "body", "chapter": s.get("chapter") or cls, "start": off,
              "end": off + dur, "logged": lp is not None}
        scenes.append(sc)
        for v in log.get("voiceovers") or []:
            b0 = off + float(v.get("start", 0.0))
            b1 = b0 + float(v.get("duration", 0.0))
            raw = v.get("raw") or v.get("text") or ""
            plan_ = VOICE.pause_plan(raw, ell)
            ws = []
            tim = v.get("timings")
            if tim:                                     # [word, start, length or None, word index]
                for k, e in enumerate(tim):
                    ws.append({"w": str(e[0]), "t0": b0 + float(e[1]), "d": e[2], "n": e[3] if len(e) > 3 else k})
            else:                                       # an older log: words spread evenly over the block
                toks = str(v.get("text") or "").split()
                for k, w in enumerate(toks):
                    ws.append({"w": w, "t0": b0 + (b1 - b0) * k / max(len(toks), 1), "d": None, "n": k})
            for k, w in enumerate(ws):                  # where a word ends: its reported length, else the next word
                nxt = ws[k + 1]["t0"] if k + 1 < len(ws) else b1
                if w["d"] is not None:
                    w["t1"] = min(w["t0"] + float(w["d"]), max(nxt, w["t0"]))
                else:
                    gap = sum(float(x) for n, x in plan_.items() if w["n"] < n <= ws[k + 1]["n"]) if k + 1 < len(ws) \
                        else 0.0
                    w["t1"] = max(w["t0"], nxt - gap) if k + 1 < len(ws) else b1
            blocks.append({"scene": cls, "role": sc["role"], "chapter": sc["chapter"], "start": b0, "end": b1,
                           "text": v.get("text") or "", "raw": raw, "words": ws,
                           "bookmarks": {k: off + float(x) for k, x in (v.get("bookmarks") or {}).items()},
                           "slow": VOICE.slow_block(raw)})
        for p in log.get("plays") or []:
            plays.append({"scene": cls, "start": off + float(p["start"]), "end": off + float(p["end"]),
                          "anims": p.get("anims") or []})
        for it in log.get("timeline") or []:
            on = [e for e in it.get("events") or [] if e[1] == 1]
            if not on:
                continue
            t_on = off + float(on[0][0])
            reveal = [p for p in log.get("plays") or [] if float(p["start"]) - 1e-3 <= float(on[0][0]) <= float(p["end"]) + 1e-3]
            t_done = off + max(float(p["end"]) for p in reveal) if reveal else t_on
            items.append({"scene": cls, "role": sc["role"], "kind": it.get("kind"), "content": str(it.get("content") or ""),
                          "live": bool(it.get("live")), "t_on": t_on, "t_done": t_done,
                          "values": [(off + float(a), str(b)) for a, b in it.get("values") or []],
                          "spans": [(off + a, off + b) for a, b in checks.intervals(it.get("events") or [], dur)]})
        t = max(t, off + dur)
    return {"plan": plan, "scenes": scenes, "blocks": blocks, "plays": plays, "items": items, "duration": t,
            "layout_sha256": hashes, "stage": stage}


def body_bounds(tl: dict) -> tuple[float, float]:
    """From the end of the opening (hook and title beat) to the start of the outro."""
    sc = tl["scenes"]
    if not sc:
        return 0.0, 0.0
    start = max([s["end"] for s in sc if s["role"] in ("hook", "context")] or [sc[0]["start"]])
    end = min([s["start"] for s in sc if s["role"] == "outro"] or [sc[-1]["end"]])
    return start, max(start, end)


def chapters(tl: dict) -> list[dict]:
    """Consecutive scenes with the same chapter title, with their roles."""
    out = []
    for s in tl["scenes"]:
        if out and out[-1]["chapter"] == s["chapter"]:
            out[-1]["end"] = s["end"]
            out[-1]["roles"].add(s["role"])
            out[-1]["scenes"].append(s["class"])
        else:
            out.append({"chapter": s["chapter"], "start": s["start"], "end": s["end"], "roles": {s["role"]},
                        "scenes": [s["class"]]})
    return out


# --------------------------------------------------------------------------- silences

def timing_silences(tl: dict, min_s: float) -> list[tuple[float, float]]:
    """Every gap of min_s or more between spoken words, and before the first and after the last."""
    spans = sorted((w["t0"], w["t1"]) for b in tl["blocks"] for w in b["words"])
    out, t = [], 0.0
    for a, b in spans:
        if a - t >= min_s:
            out.append((round(t, 3), round(a, 3)))
        t = max(t, b)
    if tl["duration"] - t >= min_s:
        out.append((round(t, 3), round(tl["duration"], 3)))
    return out


def silence_after(sil: list[tuple[float, float]], t: float, slack: float = 0.35) -> float:
    """Length of the silence after a word ending at t: one starting within slack of t, or the rest of one t is in."""
    best = 0.0
    for a, b in sil:
        if t - slack <= a <= t + slack:
            best = max(best, b - a)
        elif a < t < b:
            best = max(best, b - t)
    return round(best, 2)


# --------------------------------------------------------------------------- sentences, ideas and detectors

def sentences(tl: dict) -> list[dict]:
    out = []
    for bi, b in enumerate(tl["blocks"]):
        for i0, i1 in checks.sentences([w["w"] for w in b["words"]]):
            ws = b["words"][i0:i1 + 1]
            out.append({"block": bi, "scene": b["scene"], "i0": i0, "i1": i1, "t0": ws[0]["t0"], "t1": ws[-1]["t1"],
                        "text": " ".join(x["w"] for x in ws), "question": ws[-1]["w"].rstrip("\"'’)]").endswith("?"),
                        "last": i1 == len(b["words"]) - 1, "slow": bool(b.get("slow"))})
    return out


def find_phrase(tl: dict, scene: str, phrase: str) -> tuple[int, int] | None:
    """(block index, word index) where the words of phrase are said in a scene's narration."""
    want = norm(phrase).split()
    if not want:
        return None
    for bi, b in enumerate(tl["blocks"]):
        if b["scene"] != scene:
            continue
        toks = [norm(w["w"]) for w in b["words"]]
        flat, owner = [], []
        for k, tk in enumerate(toks):
            for x in tk.split():
                flat.append(x)
                owner.append(k)
        for k in range(len(flat) - len(want) + 1):
            if flat[k:k + len(want)] == want:
                return bi, owner[k]
    return None


def place_ideas(tl: dict, sents: list[dict], fd: checks.Findings) -> list[dict]:
    """The declared ideas of plan.json at the start and end of the sentence that states them; unplaced ones warn."""
    out = []
    for k, idea in enumerate(tl["plan"].get("ideas") or []):
        if not isinstance(idea, dict):
            continue
        scene = idea.get("scene")
        hit = None
        if idea.get("bookmark"):
            for bi, b in enumerate(tl["blocks"]):
                if b["scene"] == scene and idea["bookmark"] in b["bookmarks"]:
                    t = b["bookmarks"][idea["bookmark"]]
                    wi = next((i for i, w in enumerate(b["words"]) if w["t0"] >= t - 0.05), len(b["words"]) - 1)
                    hit = (bi, max(wi, 0))
                    break
        elif idea.get("says"):
            hit = find_phrase(tl, scene, idea["says"])
        label = idea.get("id") or f"{idea.get('kind')} {k + 1}"
        if hit is None or not tl["blocks"][hit[0]]["words"]:
            fd.add("ideas", "warning", str(scene), f"declared idea {label!r} ({idea.get('kind')}) is not found in the "
                   "narration of its scene: give it the bookmark at the start of its sentence (or the words it says)")
            continue
        bi, wi = hit
        s = next((x for x in sents if x["block"] == bi and x["i0"] <= wi <= x["i1"]), None)
        w = tl["blocks"][bi]["words"][wi]
        out.append(dict(idea, label=label, t=w["t0"], t_end=s["t1"] if s else w["t1"], sentence=s, block=bi))
    return sorted(out, key=lambda x: x["t"])


def latex_symbols(tex: str) -> list[str]:
    """Letters and Greek letters of a LaTeX formula with their sub- and superscripts (command names are not symbols)."""
    t = TEXT_GROUP.sub(" ", tex)
    t = COMMAND.sub(lambda m: m.group(0) if m.group(1) in GREEK else " ", t)
    t = re.sub(r"\s+", " ", t)
    out = []
    for m in SYMBOL.finditer(t):
        out.append(re.sub(r"\s+", "", m.group(1) + m.group(2)))
    return out


def relations(tex: str) -> int:
    t = TEXT_GROUP.sub(" ", tex)
    return len(RELATION.findall(t)) + len(OPERATOR.findall(t))


def equations(tl: dict, lo: float, hi: float, cfg: dict, labels: list | None = None) -> list[dict]:
    """New equations in order of their reveal (a lone new symbol goes to labels instead)."""
    seen_sym, seen_eq, out = set(), set(), []
    for it in sorted((i for i in tl["items"] if i["kind"] == "math" and not i["live"]), key=lambda i: i["t_on"]):
        key = re.sub(r"\s+", "", it["content"])
        if not key or key in seen_eq:
            continue
        seen_eq.add(key)
        syms = latex_symbols(it["content"])
        new = sorted(set(syms) - seen_sym)
        fam = sorted(set(syms) & seen_sym)
        ops = relations(it["content"])
        seen_sym |= set(syms)
        if not (lo <= it["t_on"] < hi):
            continue
        if ops == 0 and new and labels is not None:
            labels.append({"t": it["t_on"], "content": it["content"], "new": new, "scene": it["scene"]})
        if not (ops >= 2 or (ops >= 1 and new)):
            continue
        out.append({"t": it["t_on"], "t_done": it["t_done"], "content": it["content"], "scene": it["scene"],
                    "new": new, "familiar": fam, "ops": ops, "weight": 1.0 if new else float(cfg["rearrangement_weight"])})
    return out


def term_list(tl: dict, cfg: dict) -> list[str]:
    eng = (load_json(CONFIG / "video.json").get("engagement") or {}).get("jargon") or []
    terms = list(tl["plan"].get("glossary") or []) + list(cfg["glossary"]) + list(eng)
    out, seen = [], set()
    for t in terms:
        n = norm(t)
        if n and n not in seen:
            seen.add(n)
            out.append(n)
    return sorted(out, key=lambda x: -len(x.split()))


def terms(tl: dict, cfg: dict) -> list[dict]:
    """First spoken mention of each term: [{"t", "term", "block", "i"}]."""
    flat = []
    for bi, b in enumerate(tl["blocks"]):
        for wi, w in enumerate(b["words"]):
            for x in norm(w["w"]).split():
                flat.append((x, w["t0"], bi, wi))
    toks = [f[0] for f in flat]
    out, taken = [], set()
    for term in term_list(tl, cfg):
        p = term.split()
        for k in range(len(toks) - len(p) + 1):
            if toks[k:k + len(p)] == p and not any(j in taken for j in range(k, k + len(p))):
                out.append({"t": flat[k][1], "term": term, "block": flat[k][2], "i": flat[k][3]})
                taken.update(range(k, k + len(p)))
                break
    return sorted(out, key=lambda x: x["t"])


def spoken_value(run: list[str]) -> float | None:
    """The value of a run of number words ("zero point five nine" -> 0.59), or None."""
    if "point" in run:
        k = run.index("point")
        whole = spoken_value(run[:k]) if run[:k] else 0.0
        digs = [NUMBER_WORDS.get(x) for x in run[k + 1:]]
        if whole is None or not digs or any(d is None or d > 9 for d in digs):
            return None
        return whole + float("0." + "".join(str(int(d)) for d in digs))
    if run in (["half"], ["one", "half"], ["a", "half"]):
        return 0.5
    total, cur = 0.0, 0.0
    for x in run:
        v = NUMBER_WORDS.get(x)
        if v is None:
            return None
        if v == 100:
            cur = (cur or 1) * 100
        else:
            cur += v
    return total + cur


def ntok(word: str) -> str:
    """A word for the number detector: lower case, digits with their decimal point kept."""
    return re.sub(r"[^a-z0-9.%']", "", str(word).lower().replace("’", "'")).strip(".'")


def numbers(tl: dict) -> list[dict]:
    """Spoken numbers that carry a value: [{"t", "text", "value", "scene"}]."""
    out = []
    for b in tl["blocks"]:
        toks = [ntok(w["w"]) for w in b["words"]]
        k = 0
        while k < len(toks):
            if toks[k] in NUMBER_WORDS or toks[k] == "point" and k and toks[k - 1] in NUMBER_WORDS or \
                    re.fullmatch(r"\d+(?:\.\d+)?", toks[k] or ""):
                j = k
                while j < len(toks) and (toks[j] in NUMBER_WORDS or toks[j] in ("point", "percent") or
                                         re.fullmatch(r"\d+(?:\.\d+)?", toks[j] or "")):
                    j += 1
                run = toks[k:j]
                prev = toks[k - 1] if k else ""
                nxt = toks[j] if j < len(toks) else ""
                digit = any(re.fullmatch(r"\d+(?:\.\d+)?", x) for x in run)
                if run[-1] == "point":                     # "one point" of "checking one point": not a decimal
                    run, j = run[:-1], j - 1
                    nxt = "point"
                body = [x for x in run if x != "percent"]
                is_value = digit or any(x in VALUE_MARK for x in run) or (prev in VALUE_BEFORE and body != ["one"]) or \
                    (nxt in ("steps", "percent") and prev not in ("a", "the", "one", "take", "takes"))
                if is_value and body:
                    val = float(body[0]) if digit and len(body) == 1 else spoken_value(body)
                    out.append({"t": b["words"][k]["t0"], "text": " ".join(run), "value": val, "scene": b["scene"]})
                k = max(j, k + 1)
            else:
                k += 1
    return sorted(out, key=lambda x: x["t"])


def numbers_on_screen(tl: dict, value: float | None, t: float) -> bool:
    """Whether a text visible at t shows the value, to the precision it is written with."""
    if value is None:
        return True
    for it in tl["items"]:
        if not any(a - 0.5 <= t <= b + 0.5 for a, b in it["spans"]):
            continue
        texts = [v for a, v in it["values"] if a <= t + 0.5] or [it["content"]]
        for text in texts[-1:] if it["live"] else texts:
            for m in re.finditer(r"\d+(?:\.\d+)?", str(text).replace(",", "")):
                s = m.group()
                tol = 0.5 * 10 ** -(len(s.split(".")[1]) if "." in s else 0)
                if abs(float(s) - value) <= tol + 1e-9 or abs(float(s) - 100 * value) <= tol + 1e-9:
                    return True
    return False


def windows(events: list[tuple[float, float]], width: float) -> tuple[float, float]:
    """(the largest weighted count in a window of width seconds that starts at an event, its start)."""
    best = (0.0, 0.0)
    for t0, _ in events:
        n = sum(w for t, w in events if t0 <= t < t0 + width)
        if n > best[0]:
            best = (n, t0)
    return best


# --------------------------------------------------------------------------- the rules

def check(run: Path, stage: str, cfg: dict) -> tuple[checks.Findings, dict]:
    fd = Findings()
    tl = timeline(run, stage)
    stats: dict = {"stage": stage, "duration_s": round(tl["duration"], 1)}
    lo, hi = body_bounds(tl)
    body = max(hi - lo, 1e-6)
    stats["body_s"] = [round(lo, 1), round(hi, 1)]
    sents = sentences(tl)
    ideas = place_ideas(tl, sents, fd)
    standalone = not (run / "video" / "series_context.json").exists()
    elsewhere = "cut one, or leave it to the explainer" if standalone else \
        "move one to a neighbouring episode through the series plan"
    stem = run / "video" / "final" / "narration.wav"
    if stage == "final" and stem.exists():
        sil = checks.silences(stem, float(cfg["silence_rel_db"]), float(cfg["silence_min_s"]), relative=True,
                              bridge_s=0.1)
        how = "narration stem"
    else:
        sil, how = timing_silences(tl, float(cfg["silence_min_s"])), "word timings"
    for p in tl["plays"]:                              # a hold of the picture is silence whatever the timings say
        if "Hold" in p["anims"] and p["end"] - p["start"] >= float(cfg["silence_min_s"]):
            sil.append((p["start"], p["end"]))
    sil = merge(sil)
    long_sil = [(a, b) for a, b in sil if b - a >= float(cfg["silence_long_s"])]
    stats["silences_from"] = how
    labels: list[dict] = []
    eqs = equations(tl, lo, hi, cfg, labels)
    trm = [x for x in terms(tl, cfg) if lo <= x["t"] < hi]
    nums = [x for x in numbers(tl) if lo <= x["t"] < hi]
    qs = [s for s in sents if s["question"] and lo <= s["t0"] < hi]
    kinds = {}
    for i in ideas:
        kinds[i.get("kind")] = kinds.get(i.get("kind"), 0) + 1
    stats["declared"] = dict(sorted(kinds.items()))
    stats["detected"] = {"terms": len(trm), "equations": len(eqs),
                         "rearrangements": sum(1 for e in eqs if e["weight"] < 1), "symbol_labels": len(labels),
                         "numbers": len(nums), "questions": len(qs)}
    stars = [i for i in ideas if i.get("kind") == "star"]
    results = [i for i in ideas if i.get("kind") in RESULT_KINDS]

    # P1, P2: starred results
    n_ex = sum(1 for i in ideas if i.get("kind") == "claim" and i.get("example"))
    n_side = sum(1 for i in ideas if i.get("kind") == "claim" and i.get("side"))
    for n, cap, what in ((len(stars), cfg["stars_max"], "starred results"), (n_ex, cfg["examples_max"],
                                                                             "example results"),
                         (n_side, cfg["side_max"], "side results")):
        if n > cap:
            fd.add("P1", "warning", "video", f"{n} {what} (at most {cap}): {elsewhere}")
    for a, b in zip(stars, stars[1:]):
        if b["t"] - a["t"] < float(cfg["star_spacing_s"]):
            fd.add("P2", "warning", b.get("scene", ""), f"starred results {a['label']!r} and {b['label']!r} "
                   f"{b['t'] - a['t']:.0f} s apart (at least {cfg['star_spacing_s']:.0f} s)", b["t"])

    # P3: claim rate and spacing
    body_res = [r for r in results if lo <= r["t"] < hi]
    width = min(float(cfg["claims_window_s"]), body)
    n_max, t_max = windows([(r["t"], 1.0) for r in body_res], width)
    stats["claims_max_per_window"] = [n_max, round(width)]
    if n_max > float(cfg["claims_per_min"]) * width / 60 + 1e-9:
        fd.add("P3", "warning", "video", f"{n_max:g} claims and starred results in {width:.0f} s from {mmss(t_max)} "
               f"(at most {cfg['claims_per_min']:g} per minute)", t_max)
    hold = float(cfg["star_silence_s"])
    for a, b in zip(body_res, body_res[1:]):
        start = a["t_end"] + hold if a.get("kind") == "star" else a["t"]
        if b["t"] - start < float(cfg["claim_spacing_s"]):
            fd.add("P3", "warning", b.get("scene", ""), f"{b['label']!r} comes {b['t'] - start:.0f} s after "
                   f"{a['label']!r}" + (" and its hold" if a.get("kind") == "star" else "")
                   + f" (at least {cfg['claim_spacing_s']:.0f} s)", b["t"])

    # P4, P5: concepts and terms
    declared_concepts = [i for i in ideas if i.get("kind") == "concept"]
    win = float(cfg["undeclared_window_s"])
    events = [(c["t"], 1.0) for c in declared_concepts if lo <= c["t"] < hi]
    for x in trm:
        if not any(abs(c["t"] - x["t"]) <= win for c in declared_concepts):
            events.append((x["t"], 1.0))
    for e in eqs + [dict(x, weight=1.0) for x in labels]:
        if not any(abs(c["t"] - e["t"]) <= win for c in declared_concepts):
            events.append((e["t"], e["weight"]))
    events.sort()
    seg = pretraining(tl, ideas, eqs, sil, fd, cfg, events)
    stats["pretraining"] = seg
    outside = [ev for ev in events if not (seg.get("valid") and seg["t0"] <= ev[0] <= seg["t1"])]
    for width_, cap in ((60.0, cfg["concepts_per_60"]), (120.0, cfg["concepts_per_120"])):
        n, t0 = windows(outside, width_)
        if n > float(cap) + 1e-9:
            fd.add("P4", "warning", "video", f"{n:g} new concepts (declared, terms, new equations) in {width_:.0f} s "
                   f"from {mmss(t0)} (at most {cap:g})", t0)
    stats["concepts_max_per_60"] = windows(events, 60.0)[0]
    jargon = {norm(j) for j in (load_json(CONFIG / "video.json").get("engagement") or {}).get("jargon") or []}
    jargon |= {norm(t) for t in cfg["glossary"]} | {norm(t) for t in tl["plan"].get("glossary") or []}
    tech = [x for x in trm if x["term"] in jargon]
    for s in sents:
        inside = [x for x in tech if x["block"] == s["block"] and s["i0"] <= x["i"] <= s["i1"]]
        if len(inside) > int(cfg["terms_per_sentence"]):
            fd.add("P5", "warning", s["scene"], f"{len(inside)} new terms in one sentence "
                   f"({', '.join(x['term'] for x in inside)}): one new term at a time", s["t0"])
    n, t0 = windows([(x["t"], 1.0) for x in tech], 30.0)
    if n > float(cfg["terms_per_30"]):
        fd.add("P5", "warning", "video", f"{n:g} new terms in 30 s from {mmss(t0)} (at most {cfg['terms_per_30']})",
               t0)

    # P6: silence after results, restatements
    for r in results:
        gap = silence_after(sil, r["t_end"])
        r["silence_after_s"] = gap
        if r.get("kind") == "star":
            if gap < float(cfg["star_silence_s"]):
                fd.add("P6", "error", r.get("scene", ""), f"starred result {r['label']!r} is followed by {gap:.1f} s "
                       f"of silence (at least {cfg['star_silence_s']:g} s, {cfg['star_silence_target_s']:g} s "
                       "intended): end its block there with [pause 3], a hold of the picture", r["t_end"])
            new = changes(tl, r.get("scene"), r["t_end"], r["t_end"] + float(cfg["star_silence_s"]))
            if new:
                fd.add("P6", "warning", r.get("scene", ""), f"the picture changes during the hold after starred result "
                       f"{r['label']!r} ({', '.join(map(repr, new[:2]))} appears): hold it still; a new label or "
                       "equation there splits attention", r["t_end"])
            rest = [i for i in ideas if i.get("kind") == "restatement" and i.get("of") in (r.get("id"), r["label"])]
            if not any(0 <= x["t"] - r["t_end"] <= float(cfg["restatement_within_s"]) + gap for x in rest):
                fd.add("P6", "warning", r.get("scene", ""), f"starred result {r['label']!r} has no restatement in "
                       f"plain words within {cfg['restatement_within_s']:g} s after its hold (a plan.json idea of kind "
                       "restatement with \"of\")", r["t_end"])
        elif gap < float(cfg["claim_silence_s"]) and lo <= r["t"] < hi:
            fd.add("P6", "warning", r.get("scene", ""), f"claim {r['label']!r} is followed by {gap:.1f} s of silence "
                   f"(at least {cfg['claim_silence_s']:g} s: [pause 1.8] inside the block, or [pause 1.5] at its "
                   "end)", r["t_end"])

    # P7: stretches without a pause
    spoken = sorted((w["t0"], w["t1"]) for b in tl["blocks"] for w in b["words"])
    stretches = []
    if spoken:
        edges = [spoken[0][0]]
        for a, b in long_sil:
            if spoken[0][0] < a < spoken[-1][1]:
                edges += [a, b]
        edges.append(spoken[-1][1])
        stretches = [(edges[k], edges[k + 1]) for k in range(0, len(edges) - 1, 2) if edges[k + 1] > edges[k]]
    stats["longest_stretch_s"] = round(max((b - a for a, b in stretches), default=0.0), 1)
    for a, b in stretches:
        if b - a > float(cfg["stretch_warn_s"]):
            sev = "error" if b - a > float(cfg["stretch_error_s"]) else "warning"
            fd.add("P7", sev, scene_at(tl, a), f"{b - a:.0f} s of narration ({mmss(a)}-{mmss(b)}) without a pause of "
                   f"{cfg['silence_long_s']:g} s (warning above {cfg['stretch_warn_s']:g} s, error above "
                   f"{cfg['stretch_error_s']:g} s): a [pause 2] at a sentence end inside a block, or end the block there with "
                   "[pause 1.5]", a)

    # P8: pauses between blocks
    gaps, turns = [], []
    for k in range(1, len(tl["blocks"])):
        a, b = tl["blocks"][k - 1], tl["blocks"][k]
        if not a["words"] or not b["words"]:
            continue
        m = (a["words"][-1]["t1"] + b["words"][0]["t0"]) / 2
        g = max([s1 - s0 for s0, s1 in sil if s0 - 0.15 <= m <= s1 + 0.15] or [0.0])
        gaps.append(g)
        turn = a["chapter"] != b["chapter"]
        if turn:
            turns.append(g)
            if g < float(cfg["chapter_turn_pause_s"]):
                fd.add("P8", "warning", b["scene"], f"{g:.1f} s between the chapters {a['chapter']!r} and "
                       f"{b['chapter']!r} (at least {cfg['chapter_turn_pause_s']:g} s: end the chapter's last block "
                       "with [pause 1.5])", b["words"][0]["t0"])
        lead = b["words"][0]["t0"] - a["words"][-1]["t1"]
        if checks.sentence_end(a["words"][-1]["w"]) and lead < float(cfg["sentence_gap_min_s"]) and not (
                turn and g < float(cfg["chapter_turn_pause_s"])):
            fd.add("P8", "warning", b["scene"], f"the next block starts {lead:.1f} s after the sentence ending "
                   f"{a['text'][-30:]!r} (at least {cfg['sentence_gap_min_s']:g} s): end that block with its default "
                   "pause or [pause S]; [pause 0] only when the sentence continues into the next block",
                   b["words"][0]["t0"])
    paced = set()                                   # blocks the pace cap gave breaks: not their natural rhythm
    man_p = run / "video" / "voice" / "manifest.json"
    if stage == "final" and man_p.exists():
        paced = {k for k, m in (json.loads(man_p.read_text(encoding="utf-8")).get("blocks") or {}).items()
                 if (m.get("pace_break_s") or 0) > 0}
    inner = []                                      # the ordinary pauses between sentences inside blocks: no
    for a, b in zip(sents, sents[1:]):              # planned pause there, and no pace-cap break in the block
        blk = tl["blocks"][a["block"]]
        if a["block"] != b["block"] or VS.key(blk["raw"]) in paced or any(
                blk["words"][a["i1"]]["n"] < n <= blk["words"][b["i0"]]["n"] for n in VOICE.pause_plan(blk["raw"], 0.7)):
            continue
        m = (a["t1"] + b["t0"]) / 2
        inner.append(max([s1 - s0 for s0, s1 in sil if s0 - 0.15 <= m <= s1 + 0.15] or [0.0]))
    if inner:
        stats["sentence_pause_median_s"] = round(statistics.median(inner), 2)
    if gaps:
        med = statistics.median(gaps)
        stats["block_pause_median_s"] = round(med, 2)
        rel_ = float(cfg["block_vs_sentence_min"]) * statistics.median(inner) if inner else 0.0
        need_p8 = max(float(cfg["block_pause_median_s"]), rel_)
        if med < need_p8 - 1e-9:
            fd.add("P8", "warning", "video", f"median pause between narration blocks {med:.2f} s (at least "
                   f"{need_p8:.2f} s: {cfg['block_pause_median_s']:g} s, and {cfg['block_vs_sentence_min']:g} times "
                   "the median ordinary pause between sentences inside blocks: an idea boundary is never shorter "
                   "than a sentence boundary; voice.block_end_pause_s holds the picture after each block)")

    # P9: effective rate
    chs = chapters(tl)
    for c in chs:
        if not c["roles"] & {"body", "recap"} or c["end"] - c["start"] < 30:
            continue
        w = sum(VOICE.spoken_words(b["text"]) for b in tl["blocks"] if c["start"] <= b["start"] < c["end"])
        wpm = 60.0 * w / (c["end"] - c["start"])
        c["wpm"] = round(wpm)
        if wpm > float(cfg["body_wpm_max"]):
            fd.add("P9", "warning", c["chapter"], f"{wpm:.0f} words per minute of running time (at most "
                   f"{cfg['body_wpm_max']:g}, pauses included): more pauses or fewer words", c["start"])
    wb = sum(VOICE.spoken_words(b["text"]) for b in tl["blocks"] if lo <= b["start"] < hi)
    stats["body_wpm"] = round(60.0 * wb / body)

    # P10: rates, slow blocks and key sentences
    manifest = run / "video" / "voice" / "manifest.json"
    man = json.loads(manifest.read_text(encoding="utf-8")) if stage == "final" and manifest.exists() else {}
    for key, m in (man.get("blocks") or {}).items():
        slowest = m.get("slowest_rate_pct", m.get("applied_rate_pct"))
        least = float(cfg["block_rate_min_pct"])
        if m.get("slow") and isinstance(m.get("slow_rate_pct"), (int, float)):
            least = min(least, float(m["slow_rate_pct"]))              # a slow block: down to its own rate
        if isinstance(slowest, (int, float)) and slowest < float(cfg["rate_floor_pct"]) - 0.05:
            fd.add("P10", "error", f"block {key}", f"read at {slowest:g} % (never below {cfg['rate_floor_pct']:g} %: "
                   "the voice drags words): synthesize it again with the current voice settings")
        elif isinstance(m.get("applied_rate_pct"), (int, float)) and m["applied_rate_pct"] < least - 0.05:
            fd.add("P10", "warning", f"block {key}", f"the whole block read at {m['applied_rate_pct']:g} % (no block "
                   f"below {least:g} %, the rate of a slow block: time comes from pauses, not a slower voice)")
        if m.get("pace") == "rewrite":
            fd.add("P20", "warning", f"block {key}", f"still too fast after breaks and the slowest allowed rate "
                   f"({m.get('speech_wpm', '?')} words per minute): shorten or split it ({str(m.get('text', ''))[:50]!r})")
        if m.get("fault"):
            fd.add("voice", "warning", f"block {key}", f"every take had a fault (the kept one: {m['fault']}): "
                   f"synthesize it again, or reword it ({str(m.get('text', ''))[:50]!r})")
    for b in tl["blocks"]:
        if b.get("slow") and b["role"] in ("hook", "context", "recap", "outro"):
            fd.add("P10", "warning", b["scene"], f"a slow block ([slow]) in the {b['role']}: slow blocks are for the "
                   f"derivations and arguments of the body; this narration stays at the base rate "
                   f"({b['text'][:40]!r})", b["start"])
    if stage == "final" and any(w["d"] is not None for b in tl["blocks"] for w in b["words"]):
        keyed = {id(i["sentence"]) for i in ideas if i.get("kind") in ("star", "prompt") and i.get("sentence")}
        ordinary, slow_, key_ = [], [], []
        for s in sents:
            ws = tl["blocks"][s["block"]]["words"][s["i0"]:s["i1"] + 1]
            n = VOICE.spoken_words(" ".join(w["w"] for w in ws))
            if n < 5:
                continue
            span = max(ws[-1]["t1"] - ws[0]["t0"], 1e-6)
            plan_ = VOICE.pause_plan(tl["blocks"][s["block"]]["raw"])
            span -= sum(v for k, v in plan_.items() if ws[0]["n"] < k <= ws[-1]["n"])
            wpm = 60.0 * n / max(span, 1e-6)
            (key_ if id(s) in keyed else slow_ if s["slow"] else ordinary).append((s, wpm))
        med = statistics.median([w for _, w in ordinary]) if ordinary else None       # the base pace
        stats["speaking_wpm_median"] = round(med) if med else None
        if slow_:
            stats["speaking_wpm_slow_median"] = round(statistics.median([w for _, w in slow_]))
        for s, wpm in key_:
            if wpm < float(cfg["key_wpm_min"]):
                fd.add("P10", "warning", s["scene"], f"key sentence at {wpm:.0f} words per minute while speaking (at "
                       f"least {cfg['key_wpm_min']:g}: it drags): {s['text'][:60]!r}", s["t0"])
            elif not s["slow"] and med and wpm > float(cfg["key_max_vs_median"]) * med:
                fd.add("P10", "warning", s["scene"], f"key sentence at {wpm:.0f} words per minute while speaking, "
                       f"faster than the video's ordinary sentences ({med:.0f}): a rushed statement; read it in a "
                       f"slow block ([slow] on its derivation's block, or on a block of its own): {s['text'][:60]!r}",
                       s["t0"])

    # P11: think prompts
    prompts = [i for i in ideas if i.get("kind") == "prompt"]
    need = max(1, math.floor(body / float(cfg["prompt_every_s"])))
    if len([p for p in prompts if lo <= p["t"] < hi]) < need:
        fd.add("P11", "warning", "video", f"{len(prompts)} think prompt(s) in {body / 60:.1f} min of body (at least "
               f"{need}: one per {cfg['prompt_every_s'] / 60:g} min; plan.json ideas of kind prompt)")
    for p in prompts:
        s = p.get("sentence")
        rest = [x for x in sents if s and x["block"] == s["block"] and x["i0"] > s["i1"]]
        answer = [x for x in rest if "pause" not in norm(x["text"]).split()]   # the licence may follow, no answer
        end = rest[-1]["t1"] if rest and not answer else p["t_end"]
        gap = silence_after(sil, end)
        p["silence_after_s"] = gap
        want = float(cfg["main_prompt_silence_s"] if p.get("main") else cfg["prompt_silence_s"])
        if gap < want:
            fd.add("P11", "warning", p.get("scene", ""), f"think prompt {p['label']!r} is followed by {gap:.1f} s of "
                   f"silence (at least {want:g} s with the picture held: end its block with [pause {want:g}])", end)
        if answer:
            fd.add("P11", "warning", p.get("scene", ""), f"think prompt {p['label']!r}: its block goes on after the "
                   "question (the answer belongs in a later block, after the silence)", p["t_end"])
        new = changes(tl, p.get("scene"), end, end + want)
        if new:
            fd.add("P11", "warning", p.get("scene", ""), f"the picture changes during the think time after "
                   f"{p['label']!r} ({', '.join(map(repr, new[:2]))} appears): hold it still", end)
        if p.get("main") and "pause" not in norm(tl["blocks"][p["block"]]["text"]).split():
            fd.add("P11", "warning", p.get("scene", ""), "the main think prompt does not say \"pause here if you "
                   "like\": the spoken licence is what makes a viewer use the pause button", p["t"])

    # P12: numbers
    n, t0 = windows([(x["t"], 1.0) for x in nums], 20.0)
    stats["numbers_max_per_20"] = n
    if n > float(cfg["numbers_per_20"]):
        fd.add("P12", "warning", scene_at(tl, t0), f"{n:g} spoken numbers in 20 s from {mmss(t0)} (at most "
               f"{cfg['numbers_per_20']}): show them, say only the ones compared", t0)
    off_screen = [x for x in nums if not numbers_on_screen(tl, x["value"], x["t"])]
    for x in off_screen[:8]:
        fd.add("P12", "warning", x["scene"], f"the spoken number {x['text']!r} is not on screen while it is said",
               x["t"])

    # P13: equation holds
    others = [(i["t"], i["label"]) for i in ideas if i.get("kind") not in ("restatement", "summary")] + \
        [(x["t"], x["term"]) for x in trm]
    for e in eqs:
        need_s = max(float(cfg["hold_min_s"]), float(cfg["hold_per_new_symbol_s"]) * len(e["new"])
                     + float(cfg["hold_per_familiar_s"]) * len(e["familiar"]))
        e["hold_s"] = round(min(need_s, float(cfg["hold_cap_s"])), 1)
        t1 = e["t_done"] + e["hold_s"]
        clash = [lab for t, lab in others if e["t_done"] + 0.05 < t < t1] + \
            [x["content"][:30] for x in eqs if x is not e and e["t_done"] + 0.05 < x["t"] < t1]
        if clash:
            fd.add("P13", "warning", e["scene"], f"the equation {e['content'][:40]!r} ({len(e['new'])} new, "
                   f"{len(e['familiar'])} familiar symbols) needs a {e['hold_s']:g} s hold after it is written; "
                   f"{', '.join(map(repr, clash[:2]))} comes in it", e["t_done"])
        if need_s > float(cfg["hold_cap_s"]) and not any(
                i.get("kind") in ("restatement", "summary") and e["t_done"] <= i["t"] <= e["t_done"] + need_s
                for i in ideas):
            fd.add("P13", "warning", e["scene"], f"the equation {e['content'][:40]!r} would need {need_s:.0f} s to "
                   f"read: hold {cfg['hold_cap_s']:g} s and restate it in plain words under the hold", e["t_done"])

    # P14: picture first
    leads = []
    for i in ideas:
        if not i.get("shows"):
            continue
        want = norm(i["shows"])
        shown = [it["t_on"] for it in tl["items"] if it["scene"] == i.get("scene") and norm(it["content"]).startswith(want)]
        if not shown and i.get("shows"):
            raw = re.sub(r"\s+", "", i["shows"])
            shown = [it["t_on"] for it in tl["items"] if it["scene"] == i.get("scene")
                     and re.sub(r"\s+", "", it["content"]).startswith(raw)]
        if not shown:
            fd.add("P14", "warning", i.get("scene", ""), f"{i['label']!r}: nothing on screen starts with "
                   f"{i['shows']!r} (plan.json ideas[].shows)", i["t"])
            continue
        lead = min(shown, key=lambda x: abs(x - i["t"])) - i["t"]
        leads.append(lead)
        if lead > float(cfg["picture_lead_max_s"]):
            fd.add("P14", "warning", i.get("scene", ""), f"the words of {i['label']!r} come {lead:.1f} s before its "
                   f"picture {i['shows']!r} (at most {cfg['picture_lead_max_s']:g} s): show it first, or as it is "
                   "named", i["t"])
    for it, t_said in label_leads(tl):
        lead = it["t_on"] - t_said
        leads.append(lead)
        if lead > float(cfg["picture_lead_max_s"]):
            fd.add("P14", "warning", it["scene"], f"the label {it['content'][:40]!r} appears {lead:.1f} s after its "
                   f"words are said (at most {cfg['picture_lead_max_s']:g} s): the picture first", t_said)
    if leads:
        stats["picture_lead"] = {"pairs": len(leads), "words_first": sum(1 for x in leads if x > 0.5),
                                 "median_s": round(statistics.median(leads), 2)}

    # P15: signposts
    opening_end = lo
    title_start = min([s["start"] for s in tl["scenes"] if s["role"] == "context"] or [lo])
    roadmaps = [i for i in ideas if i.get("kind") == "roadmap"]
    if not any(title_start - 1 <= i["t"] <= opening_end + float(cfg["roadmap_within_s"]) for i in roadmaps):
        fd.add("P15", "warning", "video", f"no roadmap within {cfg['roadmap_within_s']:g} s after the title beat (a "
               "plan.json idea of kind roadmap: the three or so moves of the episode, said once)", opening_end)
    for c in chs:
        if not c["roles"] & {"body"} or c["end"] - c["start"] <= float(cfg["summary_chapter_s"]):
            continue
        tail0 = c["end"] - max(30.0, 0.3 * (c["end"] - c["start"]))
        if not any(i.get("kind") == "summary" and tail0 <= i["t"] <= c["end"] for i in ideas):
            fd.add("P15", "warning", c["chapter"], f"a {c['end'] - c['start']:.0f} s chapter ends without a one-"
                   "sentence summary (a plan.json idea of kind summary)", c["end"])
    if hi > lo and not any(i.get("kind") == "recap" and hi - 75 <= i["t"] <= hi + 1 for i in ideas):
        fd.add("P15", "warning", "video", "no recap before the outro (about 20 s, the starred results restated in "
               "the same plain words; a plan.json idea of kind recap)", hi)

    # P16: chapter lengths (a chapter whose body is a recap is short by design, P15)
    c_lo, c_hi = (float(x) for x in cfg["chapter_s"])
    recaps = P.recap_scenes(tl["plan"])
    role_of = {s["class"]: s["role"] for s in tl["scenes"]}
    stats["chapters"] = []
    for c in chs:
        if not c["roles"] & {"body"}:
            continue
        d = c["end"] - c["start"]
        stats["chapters"].append({"chapter": c["chapter"], "s": round(d, 1), "wpm": c.get("wpm")})
        if {x for x in c["scenes"] if role_of[x] == "body"} <= recaps:
            continue
        inner = any(i.get("kind") in ("summary", "restatement") and c["start"] + 0.25 * d <= i["t"] <= c["start"] + 0.85 * d
                    for i in ideas) or any(b - a >= float(cfg["star_silence_s"]) and c["start"] + 0.25 * d <= a <=
                                           c["start"] + 0.85 * d for a, b in sil)
        if d < c_lo or (d > c_hi and not inner):
            fd.add("P16", "warning", c["chapter"], f"chapter of {d:.0f} s ({c_lo:g}-{c_hi:g} s; a longer one needs a "
                   "consolidation beat inside: a summary or a hold)", c["start"])

    # P17: pause share
    share = sum(max(0.0, min(b, hi) - max(a, lo)) for a, b in long_sil) / body
    stats["pause_share"] = round(share, 3)
    stats["long_silences_per_min"] = round(sum(1 for a, b in long_sil if lo <= a < hi) / (body / 60), 2)
    if share < float(cfg["pause_share_min"]):
        fd.add("P17", "warning", "video", f"{share:.1%} of the body is silence of {cfg['silence_long_s']:g} s or more "
               f"(at least {cfg['pause_share_min']:.0%}): planned pauses after results, prompts and chapter ends")

    # P18: the idea budget (the series plan's ideas when the run has them, else the video's own)
    planned = {i.get("id"): i for i in IB.planned_ideas(run)}
    own = IB.budgeted(ideas)
    basis = list(planned.values()) if planned else own
    if basis:
        pc = IB.settings()
        recap_s = sum(s["end"] - s["start"] for s in tl["scenes"] if s["role"] == "recap")
        est = IB.estimate(basis, pc, recap_s)
        stats["budget"] = {"from": "the series plan" if planned else "plan.json", "needs_s": [est["lo_s"], est["hi_s"]],
                           "runtime_s": round(tl["duration"], 1)}
        dense = sorted({x["rule"] for x in fd.items if x["rule"] in ("P3", "P4", "P7", "P13")
                        or (x["rule"] == "P6" and x["severity"] == "error")})        # density, not form
        if tl["duration"] < est["lo_s"] - 30 and dense:
            fd.add("P18", "warning", "video", f"the video runs {tl['duration'] / 60:.1f} min but its ideas need "
                   f"{est['lo_s'] / 60:.1f}-{est['hi_s'] / 60:.1f} min ({stats['budget']['from']}), and the density "
                   f"rules {', '.join(dense)} fire: give the ideas their time, or {elsewhere} (never raise the "
                   "speaking rate)")
        elif tl["duration"] > est["hi_s"] + 60:
            fd.add("P18", "warning", "video", f"the video runs {tl['duration'] / 60:.1f} min, more than the "
                   f"{est['lo_s'] / 60:.1f}-{est['hi_s'] / 60:.1f} min its declared ideas need: it says more than it "
                   "declares (an undeclared idea), or it can be trimmed")
    if planned:
        said = {i.get("id") for i in ideas}
        extra = [i["label"] for i in own if i.get("kind") in RESULT_KINDS and i.get("id") not in planned]
        if extra:
            fd.add("P18", "warning", "video", f"results the series plan does not budget: {', '.join(extra[:5])} (a new "
                   "result goes into the series plan first, tools/series.py validate; a step of a planned idea "
                   "declares it with \"of\")")
        missing = [k for k, i in planned.items() if i.get("kind") in RESULT_KINDS and k not in said]
        if missing:
            fd.add("P18", "warning", "video", f"planned results not declared where they land: {', '.join(missing[:5])} "
                   "(plan.json ideas)")

    # coverage: detected but undeclared; conclusion markers
    near = lambda t: any(abs(i["t"] - t) <= win for i in ideas)  # noqa: E731
    undecl = [f"{x['term']!r} at {mmss(x['t'])}" for x in trm if not near(x["t"])] + \
        [f"equation {e['content'][:25]!r} at {mmss(e['t'])}" for e in eqs if e["weight"] >= 1 and not near(e["t"])]
    if undecl:
        fd.add("coverage", "warning", "video", f"{len(undecl)} detected idea(s) with no declared idea within "
               f"{win:g} s: {'; '.join(undecl[:4])}{' ...' if len(undecl) > 4 else ''}")
    markers = [norm(m) for m in cfg["claim_markers"]]
    loose: dict[str, list[str]] = {}
    for s in sents:
        if not lo <= s["t0"] < hi:
            continue
        t = " " + norm(s["text"]) + " "
        if s["question"]:
            continue
        so = re.match(r"\s*so\b(?!\s+(?:far|that|let's|let’s|here's|here’s|what|now)\b)", s["text"], re.I) or \
            re.search(r",\s*so\b(?!\s+(?:far|that|let's|let’s|here's|here’s|what|now)\b)", s["text"], re.I)
        if so or any(f" {m} " in t for m in markers if m != "so"):
            if not near(s["t0"]) and not near(s["t1"]):
                loose.setdefault(s["scene"], []).append(s["text"][:40])
    for scene, v in loose.items():
        fd.add("coverage", "warning", scene, f"possible undeclared claim(s): {'; '.join(map(repr, v[:3]))}"
               + (" ..." if len(v) > 3 else "") + " (declare the result, or reword if it is not one)")

    # markup that cannot be voiced
    mx = VOICE.azure_settings(load_json(CONFIG / "channel.json").get("voice") or {})["max_break_ms"] / 1000.0
    for b in tl["blocks"]:
        for p in VOICE.markup_problems(b["raw"], mx):
            fd.add("markup", "warning", b["scene"], f"{p} ({b['text'][:40]!r})", b["start"])

    by_role: dict[str, list[float]] = {}               # the time each declared idea got, by its planned role
    for a, b in zip(ideas, ideas[1:]):
        src = planned.get(a.get("id")) or a
        r = IB.role(src) if a.get("kind") in IB.KINDS else str(a.get("kind"))
        by_role.setdefault(r, []).append(round(b["t"] - a["t"], 1))
    stats["calibration"] = {"seconds_to_next_idea_by_role": by_role}
    if stats.get("budget"):
        b = stats["budget"]
        stats["calibration"]["runtime_minus_budget_s"] = [round(b["runtime_s"] - b["needs_s"][0], 1),
                                                          round(b["runtime_s"] - b["needs_s"][1], 1)]
    b0, b1 = body_bounds(tl)                           # the slow reading, to calibrate pacing.plan slow_extra
    spoken = [(b["end"] - b["start"], bool(b.get("slow"))) for b in tl["blocks"] if b0 <= b["start"] < b1]
    if spoken:
        share = sum(d for d, sl in spoken if sl) / max(sum(d for d, _ in spoken), 1e-6)
        slow_cal = {"share_of_body_narration": round(share, 3)}
        if share > float(cfg["slow_share_max"]):
            fd.add("P10", "warning", "video", f"slow blocks are {100 * share:.0f} % of the body's narration time (at "
                   f"most {100 * float(cfg['slow_share_max']):.0f} %): the derivations read slowly against the rest is "
                   "the only rate signal left; read the transitions, the pictures described and the concepts at the "
                   "base rate")
        if stats.get("speaking_wpm_median") and stats.get("speaking_wpm_slow_median"):
            slow_cal["extra_measured"] = round(stats["speaking_wpm_median"] / stats["speaking_wpm_slow_median"] - 1, 3)
        stats["calibration"]["slow"] = slow_cal
    stats["ideas"] = [{"label": i["label"], "kind": i.get("kind"), "scene": i.get("scene"), "t": round(i["t"], 1),
                       **({"silence_after_s": i["silence_after_s"]} if "silence_after_s" in i else {})}
                      for i in ideas]
    stats["equations"] = [{"t": round(e["t"], 1), "content": e["content"][:60], "new": e["new"],
                           "familiar": len(e["familiar"]), "hold_s": e.get("hold_s")} for e in eqs]
    stats["layout_sha256"] = tl["layout_sha256"]
    return fd, stats


def merge(spans: list[tuple[float, float]]) -> list[tuple[float, float]]:
    out = []
    for a, b in sorted(spans):
        if out and a <= out[-1][1] + 0.05:
            out[-1] = (out[-1][0], max(out[-1][1], b))
        else:
            out.append((a, b))
    return out


def scene_at(tl: dict, t: float) -> str:
    return next((s["class"] for s in tl["scenes"] if s["start"] <= t < s["end"]), "video")


def changes(tl: dict, scene: str | None, t0: float, t1: float) -> list[str]:
    """Texts and equations of a scene (not live readouts) that appear between t0 and t1."""
    return [it["content"][:30] for it in tl["items"] if it["scene"] == scene and not it["live"]
            and t0 + 0.05 < it["t_on"] < t1]


def label_leads(tl: dict) -> list[tuple[dict, float]]:
    """(label, when its words are said) for short labels whose words come within 10 s before them, not as they appear."""
    out, done = [], set()
    for it in sorted(tl["items"], key=lambda i: i["t_on"]):
        if it["kind"] != "text" or it["live"] or it["role"] not in ("body", "recap"):
            continue
        words = norm(it["content"]).split()
        if not 1 <= len(words) <= 4 or len(" ".join(words)) < 6 or (it["scene"], " ".join(words)) in done:
            continue
        done.add((it["scene"], " ".join(words)))
        said = []
        for b in tl["blocks"]:
            if b["scene"] != it["scene"]:
                continue
            toks = [norm(w["w"]) for w in b["words"]]
            for k in range(len(toks) - len(words) + 1):
                if toks[k:k + len(words)] == words:
                    said.append(b["words"][k]["t0"])
        if not said:
            continue
        if any(abs(t - it["t_on"]) <= 1.5 or t > it["t_on"] for t in said):
            continue
        before = [t for t in said if it["t_on"] - 10.0 <= t < it["t_on"]]
        if before:
            out.append((it, max(before)))
    return out


def pretraining(tl: dict, ideas: list[dict], eqs: list[dict], sil: list, fd: checks.Findings, cfg: dict,
                events: list | None = None) -> dict:
    """The pretraining segment and whether P4's exception applies (conditions a-g; the first that fails warns)."""
    pre = [i for i in ideas if i.get("kind") == "concept" and i.get("pretraining")]
    if not pre:
        return {}
    t0, t1 = pre[0]["t"], pre[-1]["t_end"]
    summ = next((i for i in ideas if i.get("kind") == "summary" and i["t"] >= pre[-1]["t"]), None)
    fails = []
    inside = [ev for ev in (events if events is not None else [(i["t"], 1.0) for i in pre])
              if t0 - 1e-6 <= ev[0] <= t1 + 1e-6]
    n60 = windows(inside, 60.0)[0]
    total = sum(w for _, w in inside)
    if total > int(cfg["pretraining_max"]) + 1e-9:
        fails.append(f"(a) {total:g} concepts in the segment (at most {cfg['pretraining_max']})")
    elif n60 > float(cfg["pretraining_per_60"]):
        fails.append(f"(a) {n60:g} concepts in 60 s (at most {cfg['pretraining_per_60']:g})")
    for i in pre:
        want = norm(i.get("shows") or "")
        on = [it["t_on"] for it in tl["items"] if want and norm(it["content"]).startswith(want)]
        if not want or not any(abs(x - i["t"]) <= float(cfg["picture_lead_max_s"]) for x in on):
            fails.append(f"(b) {i['label']!r} does not appear on its own object as it is named (plan.json shows)")
            break
    for i in pre:
        if silence_after(sil, i["t_end"]) < float(cfg["pretraining_break_s"]):
            fails.append(f"(c) no {cfg['pretraining_break_s']:g} s break after naming {i['label']!r}")
            break
    if summ is None or silence_after(sil, summ["t_end"]) < float(cfg["pretraining_summary_break_s"]):
        fails.append(f"(d) the segment does not end with a summary and a {cfg['pretraining_summary_break_s']:g} s "
                     "break")
    end = summ["t"] if summ else t1
    if any(t0 <= e["t"] < end and e["ops"] >= 2 for e in eqs):
        fails.append("(e) an equation combining the concepts comes before the summary")
    if any(i.get("kind") in RESULT_KINDS and t0 <= i["t"] <= t1 for i in ideas):
        fails.append("(f) a result inside the segment")
    others = [i for i in ideas if i.get("kind") == "concept" and not i.get("pretraining") and t0 < i["t"] < t1]
    first_star = min([i["t"] for i in ideas if i.get("kind") == "star"] or [math.inf])
    if others or t1 > first_star:
        fails.append("(g) not one segment before the first starred result")
    if fails:
        fd.add("P4", "warning", pre[0].get("scene", ""), "the pretraining exception does not apply: " + fails[0]
               + (f" (and {len(fails) - 1} more)" if len(fails) > 1 else ""), t0)
    return {"t0": round(t0, 1), "t1": round(end, 1), "concepts": len(pre), "valid": not fails, "fails": fails}


def report_md(stage: str, fd: checks.Findings, stats: dict) -> list[str]:
    n_err, n_warn = checks.summary(fd.items).values()
    md = [f"# Pacing ({stage})", "",
          f"{n_err} error(s), {n_warn} warning(s); rules P1-P20 and thresholds in config/video.json "
          "\"pacing\"; silences from the " + stats.get("silences_from", "-") + ".", "",
          f"- runtime {stats['duration_s'] / 60:.1f} min, body {stats['body_s'][0]:.0f}-{stats['body_s'][1]:.0f} s; "
          f"{stats.get('body_wpm', '-')} words per minute of body running time",
          f"- declared ideas by kind: {stats.get('declared') or 'none'}; detected: {stats.get('detected')}",
          f"- longest stretch without a pause: {stats.get('longest_stretch_s', '-')} s; pauses of 1.5 s or more: "
          f"{stats.get('long_silences_per_min', '-')} per minute, {stats.get('pause_share', 0):.1%} of the body; "
          f"median pause between blocks: {stats.get('block_pause_median_s', '-')} s",
          f"- most claims in a window: {stats.get('claims_max_per_window')}; most concepts in 60 s: "
          f"{stats.get('concepts_max_per_60')}; most numbers in 20 s: {stats.get('numbers_max_per_20')}"]
    if stats.get("budget"):
        b = stats["budget"]
        md.append(f"- the ideas need {b['needs_s'][0] / 60:.1f}-{b['needs_s'][1] / 60:.1f} min; the video runs "
                  f"{b['runtime_s'] / 60:.1f} min")
    if stats.get("picture_lead"):
        p = stats["picture_lead"]
        md.append(f"- picture against words: {p['pairs']} pairs, words first in {p['words_first']}, median lead of "
                  f"the words {p['median_s']} s")
    if stats.get("ideas"):
        md += [""] + checks.md_table(["t", "Kind", "Idea", "Scene", "Silence after (s)"], (
            [mmss(i["t"]), i["kind"], i["label"], i["scene"], i.get("silence_after_s", "")] for i in stats["ideas"]))
    if stats.get("chapters"):
        md += [""] + checks.md_table(["Chapter", "s", "wpm"],
                                     ([c["chapter"], c["s"], c.get("wpm") or "-"] for c in stats["chapters"]))
    if fd.items:
        order = {"error": 0, "warning": 1, "info": 2}
        md += [""] + checks.md_table(["Severity", "Rule", "Where", "t", "Detail"], (
            [x["severity"], x["rule"], x["where"], "" if x["t"] is None else mmss(x["t"]), x["detail"]]
            for x in sorted(fd.items, key=lambda x: order[x["severity"]])))
    return md


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run")
    ap.add_argument("--stage", choices=["draft", "final"], default="draft")
    ap.add_argument("--out", help="output folder (default review/design/<stage>/)")
    a = ap.parse_args()
    run = resolve_run(a.run)
    cfg = settings()
    fd, stats = check(run, a.stage, cfg)
    n_err, n_warn = checks.summary(fd.items).values()
    out = Path(a.out) if a.out else run / "review" / "design" / a.stage
    sha = stats.pop("layout_sha256")
    checks.write_report(out, "check_pacing", a.stage, fd.items, report_md(a.stage, fd, stats), layout_sha256=sha,
                        stats=stats)
    for x in fd.items:
        print(f"{x['severity']} {x['rule']} {x['where']}{'' if x['t'] is None else ' at ' + mmss(x['t'])}: "
              f"{x['detail']}")
    print(f"check_pacing ({a.stage}): {n_err} error(s), {n_warn} warning(s); {rel(out / 'check_pacing.md')}")
    return 1 if n_err else 0


if __name__ == "__main__":
    sys.exit(main())
