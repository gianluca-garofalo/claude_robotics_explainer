"""How long on-screen text and equations must stay visible to be read (Remaining Action house model).

Pure Python, no Manim: the scenes use it for automatic holds (RAScene in common.py) and the gate uses the repository's
copy (tools/video/check_reading.py). Copy it next to the scenes with common.py and voice.py.

    text      orientation_s + words * 60 / text_wpm
    equation  max(equation_min_s, equation_base_s + equation_term_s * terms), terms = top-level terms and relations,
              plus half a term for each fraction, root, integral or sum; words inside \\text{} count as text
    narrated  times narration_factor when narration plays during at least narration_overlap of the display time
    floor     min_display_s for anything, however short

Constants come from config/video.json "reading" (tunable defaults; the file says where each one comes from).

Numbers must also be readable at a glance: fmt() writes them the house way (config/video.json "numbers"), and
tools/video/check_numbers.py checks every number on screen and in the narration against the same rules.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

DEFAULTS = {
    "text_wpm": 200, "orientation_s": 0.6, "equation_base_s": 1.0, "equation_term_s": 0.6, "equation_min_s": 2.0,
    "narration_factor": 1.4, "narration_overlap": 0.5, "min_display_s": 1.0, "error_fraction": 0.75,
    "max_words_on_screen_warn": 40, "max_words_on_screen_error": 60,
    "narration_wpm_target": 150, "narration_wpm_warn": 165, "narration_wpm_error": 180,
}
WORD = re.compile(r"[A-Za-z\u00C0-\u024F\u0370-\u03FF0-9]+(?:['’.,-][A-Za-z0-9]+)*")
TEXT_CMD = re.compile(r"\\(?:text|textrm|textbf|textit|mathrm|operatorname)\s*\{([^{}]*)\}")
HEAVY = re.compile(r"\\(?:frac|dfrac|tfrac|sqrt|int|iint|oint|sum|prod|lim|partial)(?![a-zA-Z])")
RELATIONS = re.compile(r"\\(?:le|leq|ge|geq|ne|neq|approx|equiv|sim|simeq|to|mapsto|Rightarrow|iff|in|subset|"
                       r"subseteq|cdot|times|pm|mp|qquad|quad)\b|[=<>+\-,;]")
SPACING = re.compile(r"\\(?:left|right|big|Big|bigg|Bigg|displaystyle|textstyle|,|;|!|:)|\\[a-zA-Z]+\s*(?=\{)")


def load(start: str | os.PathLike | None = None) -> dict:
    """The "reading" section of config/video.json found upwards from `start` (or $VIDEO_CONFIG), over DEFAULTS."""
    cfg = dict(DEFAULTS)
    path = os.environ.get("VIDEO_CONFIG")
    if not path:
        here = Path(start or Path.cwd()).resolve()
        for d in [here, *here.parents]:
            if (d / "config" / "video.json").exists():
                path = str(d / "config" / "video.json")
                break
    if path:
        try:
            cfg.update(json.loads(Path(path).read_text(encoding="utf-8")).get("reading", {}))
        except (OSError, json.JSONDecodeError):
            pass
    return cfg


def words(text: str) -> int:
    return len(WORD.findall(text or ""))


def equation_terms(tex: str) -> tuple[float, int]:
    """(terms, words in \\text{...}) of a LaTeX string; at least one term."""
    tex = tex or ""
    text_words = sum(words(m) for m in TEXT_CMD.findall(tex))
    body = TEXT_CMD.sub(" T ", tex)
    heavy = len(HEAVY.findall(body))
    depth, flat = 0, []
    for ch in SPACING.sub(" ", body):              # top-level characters; a group (braces, brackets) becomes "X"
        if ch in "{([":
            if depth == 0:
                flat.append("X")
            depth += 1
        elif ch in "})]":
            depth = max(depth - 1, 0)
        elif depth == 0:
            flat.append(ch)
    parts = [p for p in RELATIONS.split("".join(flat)) if re.search(r"[A-Za-z0-9\\]", p)]
    return max(len(parts), 1) + 0.5 * heavy, text_words


def required_seconds(kind: str, content: str, narrated: bool = False, cfg: dict | None = None) -> float:
    """Seconds a text ("text") or equation ("math") item must stay visible to be read once."""
    c = cfg or DEFAULTS
    if kind == "math":
        terms, text_words = equation_terms(content)
        need = max(float(c["equation_min_s"]), c["equation_base_s"] + c["equation_term_s"] * terms)
        need += text_words * 60.0 / float(c["text_wpm"])
        if re.fullmatch(r"\s*[-+]?[\d.,]+\s*", content or "") or len((content or "").strip()) <= 2:
            need = float(c["min_display_s"])          # a single number or symbol: a label, not an equation
    else:
        n = words(content)
        need = c["orientation_s"] + n * 60.0 / float(c["text_wpm"]) if n else float(c["min_display_s"])
    if narrated:
        need *= float(c["narration_factor"])
    return round(max(need, float(c["min_display_s"])), 2)


def on_screen_words(kind: str, content: str) -> float:
    """What an item adds to the words on screen: its words, or an equation's terms."""
    if kind == "math":
        terms, text_words = equation_terms(content)
        return terms + text_words
    return float(words(content))


# --------------------------------------------------------------------------- number format (house rule)
_SUP = str.maketrans("-0123456789", "⁻⁰¹²³⁴⁵⁶⁷⁸⁹")


def _numbers(start: str | os.PathLike | None = None) -> dict:
    """The "numbers" section of config/video.json found upwards from this file (or $VIDEO_CONFIG); {} when absent."""
    path = os.environ.get("VIDEO_CONFIG")
    if not path:
        here = Path(start or Path(__file__).parent).resolve()
        path = next((d / "config" / "video.json" for d in [here, *here.parents]
                     if (d / "config" / "video.json").exists()), None)
    try:
        return json.loads(Path(path).read_text(encoding="utf-8")).get("numbers", {}) if path else {}
    except (OSError, ValueError):
        return {}


NUMBERS = _numbers()                       # config/video.json "numbers": the number-format house rule
MINUS = "\u2212"
_VULGAR = {(1, 2): "½", (1, 3): "⅓", (2, 3): "⅔", (1, 4): "¼", (3, 4): "¾", (1, 8): "⅛"}


def fmt(x, sig=None, decimals=None, unit="", role="label", exact=False, sign=False):
    """A number as a viewer should read it (house rule; config/video.json "numbers"; check_numbers.py checks it).

    fmt(0.500000) -> "0.5" and fmt(1.27712) -> "1.28": at most `sig` significant digits (default by role, numbers.sig:
    readout and label 3, table 4), trailing zeros dropped; integers stay integers (fmt(3.0) -> "3"); a real minus
    sign (U+2212); values below 10^-3 or from 10^6 up in Unicode scientific notation (1.2×10⁻⁵).
    decimals=k: exactly k decimals, trailing zeros kept: for live readouts, whose width must not jump while they
    update; give every number of one quantity in a scene the same k (sum = 1.28, not 1.277 beside it).
    exact=True: the value is exact (a symbolic result): 0 -> "0", 0.5 -> "0.5", 1/3 -> "⅓", never "0.000".
    sign=True: an explicit + on positive values, for a quantity whose sign is the point (−H = +0.14); a value shown
    as zero never carries a sign ("0.00", not "−0.00" or "+0.00").
    unit: appended after a space ("1.2 s").
    """
    x = float(x)
    if exact:
        from fractions import Fraction
        fr = Fraction(x).limit_denominator(12)
        if x == 0:
            s = "0"
        elif abs(float(fr) - x) < 1e-12 and fr.denominator > 1 and (abs(fr.numerator), fr.denominator) in _VULGAR \
                and len(repr(abs(x))) > 5:
            s = ("-" if x < 0 else "") + _VULGAR[(abs(fr.numerator), fr.denominator)]
        else:
            s = f"{x:.6f}".rstrip("0").rstrip(".") if abs(x - round(x, 6)) < 1e-12 else _sig(x, 4)
    elif decimals is not None:
        s = f"{x:.{int(decimals)}f}"
        if float(s) == 0:
            s = s.lstrip("-")                              # no "-0.00"
    elif x == int(x) and abs(x) < 1e6:
        s = str(int(x))
    else:
        s = _sig(x, sig or NUMBERS.get("sig", {}).get(role, 3))
    shown_zero = s.lstrip("-") == "0" or (decimals is not None and float(s) == 0)
    if shown_zero:
        s = s.lstrip("-")
    elif sign and not s.startswith("-"):
        s = "+" + s
    s = s.replace("-", MINUS)
    return f"{s} {unit}" if unit else s


def _sig(x, sig):
    import math
    if x == 0:
        return "0"
    e = math.floor(math.log10(abs(x)))
    if e < -3 or e >= 6:
        m = f"{x / 10 ** e:.{max(sig - 1, 0)}f}".rstrip("0").rstrip(".")
        return f"{m}×10{str(e).translate(_SUP)}"
    s = f"{x:.{max(sig - 1 - e, 0)}f}"
    return s.rstrip("0").rstrip(".") if "." in s else s
