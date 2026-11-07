"""What the video checks share: findings and their reports, sentences, silences, captions and layout logs."""
from __future__ import annotations

import json
import subprocess
import sys
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _common import utc_now, write_json  # noqa: E402

HELPERS = ("common.py", "voice.py", "reading_model.py")      # copied next to the scenes; not scenes themselves
SENTENCE_END = (".", "!", "?", "…")


class Findings:
    """A check's findings in order: add() takes `fields` then named values; a repeat of `key` is dropped or counted."""

    def __init__(self, *fields: str, key: tuple[str, ...] = (), count: bool = False, t_digits: int = 1, **defaults):
        self.fields, self.key, self.count, self.t_digits, self.defaults = fields, key, count, t_digits, defaults
        self.order = [f for f in fields if f != "t"]
        if "t" in fields:
            self.order.insert(self.order.index("detail") if "detail" in self.order else len(self.order), "t")
        self.items: list[dict] = []
        self._seen: dict[tuple, dict] = {}

    def add(self, *values, key: tuple = (), **named) -> None:
        given = {**self.defaults, **dict(zip(self.fields, values)), **named}
        f = {k: given.get(k) for k in self.order}
        f.update((k, v) for k, v in given.items() if k not in f)
        if f.get("t") is not None:
            f["t"] = round(f["t"], self.t_digits)
        ident = tuple(f[k] for k in self.key) + tuple(key)
        if ident and ident in self._seen:
            if self.count:
                self._seen[ident]["count"] += 1
            return
        if self.count:
            f["count"] = 1
        if ident:
            self._seen[ident] = f
        self.items.append(f)


def summary(findings: list[dict]) -> dict:
    return {"errors": sum(f.get("severity") == "error" for f in findings),
            "warnings": sum(f.get("severity") == "warning" for f in findings)}


def write_report(out: Path, tool: str, stage: str, findings: list[dict], md: list[str], **data) -> None:
    """<out>/<tool>.json (data, then the findings) and <tool>.md."""
    s = summary(findings)
    out.mkdir(parents=True, exist_ok=True)
    write_json(out / f"{tool}.json", {"schema_version": 1, "tool": tool, "stage": stage, "checked_at": utc_now(),
                                      "passed": not s["errors"], "summary": s, **data, "findings": findings})
    (out / f"{tool}.md").write_text("\n".join(md) + "\n", encoding="utf-8")


def md_table(header: list[str], rows) -> list[str]:
    """A Markdown table; a "|" inside a cell becomes "/"."""
    return [f"| {' | '.join(header)} |", "|" + "---|" * len(header)] + \
        [f"| {' | '.join(str(c).replace('|', '/') for c in row)} |" for row in rows]


def scene_files(run: Path) -> list[Path]:
    return [f for f in sorted((run / "video" / "scenes").glob("*.py")) if f.name not in HELPERS]


def scene_log(folder: Path, cls: str) -> tuple[dict, Path | None]:
    """A scene's layout log in folder and its path ({} and None without one)."""
    lp = folder / f"{cls}.layout.json"
    if not lp.exists():
        return {}, None
    scenes = json.loads(lp.read_text(encoding="utf-8")).get("scenes", {})
    return scenes.get(cls) or next(iter(scenes.values()), {}), lp


def intervals(events: list, end: float) -> list[tuple[float, float]]:
    """Visible spans from timeline events [t, visible, ...]; one still open at the last event ends at end."""
    out, start = [], None
    for ev in events:
        if ev[1] == 1 and start is None:
            start = ev[0]
        elif ev[1] == 0 and start is not None:
            out.append((start, ev[0]))
            start = None
    if start is not None:
        out.append((start, end))
    return out


def sentence_end(word: str) -> bool:
    return word.rstrip("\"'’)]").endswith(SENTENCE_END)


def sentences(words: list[str]) -> list[tuple[int, int]]:
    """(first, last) word index of each sentence of a run of words."""
    out, start = [], 0
    for i, w in enumerate(words):
        if sentence_end(w) or i == len(words) - 1:
            out.append((start, i))
            start = i + 1
    return out


def captions(path: Path) -> list[str]:
    """The text of each cue of an SRT file, its lines joined by spaces."""
    import media
    import srt
    try:
        return [text for _, _, text in media.read_srt(path) if text]
    except srt.SRTParseError as exc:
        raise ValueError(f"{path.name}: not SRT captions ({exc})") from None


def _samples(path: Path):
    """Mono samples, their rate and full scale: a PCM WAV as it is, anything else decoded by ffmpeg."""
    import numpy as np
    try:
        with wave.open(str(path), "rb") as w:
            rate, ch, dtype = w.getframerate(), w.getnchannels(), {2: np.int16, 4: np.int32}[w.getsampwidth()]
            raw = w.readframes(w.getnframes())
    except (wave.Error, EOFError, KeyError):
        rate, ch, dtype = 16000, 1, np.int16
        raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-f", "s16le", "-ac", "1", "-ar", str(rate),
                              "-"], capture_output=True, check=True).stdout
    x = np.frombuffer(raw, dtype=dtype).astype(np.float64).reshape(-1, ch).mean(axis=1)
    return x, rate, -float(np.iinfo(dtype).min)


def silences(path: Path, db: float, min_s: float, relative: bool = False, bridge_s: float = 0.0) \
        -> list[tuple[float, float]]:
    """Silences of at least min_s seconds: 10 ms frames whose 30 ms level is under db dBFS, or with relative under the
    speech level (95th percentile) + db; quiet runs merge across sounds shorter than bridge_s."""
    import numpy as np
    x, rate, full = _samples(path)
    hop, win = max(1, int(0.01 * rate)), max(2, int(0.03 * rate))
    starts = np.arange(max(1, 1 + (len(x) - win) // hop)) * hop
    sq = np.concatenate([[0.0], np.cumsum(x * x)])
    rms = np.sqrt(np.maximum((sq[np.minimum(starts + win, len(x))] - sq[starts]) / win, 0.0))
    level = 20 * np.log10(rms + 1e-9) - 20 * np.log10(full)
    if relative:
        loud = level[level > level.max() - 60] if level.size else level
        db += np.percentile(loud, 95) if loud.size else 0.0
    runs, s0 = [], None
    for i, quiet in enumerate(list(level < db) + [False]):
        if quiet and s0 is None:
            s0 = i
        elif not quiet and s0 is not None:
            runs.append([s0 * 0.01, i * 0.01 + 0.02])
            s0 = None
    merged = []
    for a, b in runs:
        if merged and a - merged[-1][1] < bridge_s:
            merged[-1][1] = b
        else:
            merged.append([a, b])
    return [(round(a, 3), round(b, 3)) for a, b in merged if b - a >= min_s]
