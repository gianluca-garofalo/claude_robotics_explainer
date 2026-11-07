#!/usr/bin/env python3
"""Render the fixed reference paragraph with the channel voice, for regression checks (voice policy, README.md).

  python3 tools/video/voice_reference.py [--service azure|piper] [--out voice-reference]

At every voice change (and whenever the vendor may have moved a "Latest" model under the same name) render this
paragraph and keep the result: voice-reference/<date>_<voice>/reference.wav, reference.mp3 (as synthesized),
timings.json (the word timings) and reference.json (voice, settings, duration, words per minute). The folder is
git-ignored: archive it with the run archives. Listen against the previous reference before a new episode ships.
The voice name goes into the folder name with every character other than letters, digits, "." and "-" replaced by
"_" (the HD voices' names hold a colon).
"""
import argparse
import datetime as dt
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "templates" / "manim"))
import voice  # noqa: E402

# Fixed: never edit it, or the references stop being comparable. It covers a question, a planned beat (the
# ellipsis), a number, a comma pause and a long sentence.
REFERENCE = ("A robot never sees the whole road. It plans a short stretch ahead, takes one step, and plans again. "
             "Why does that work? Because the cost still to pay... the remaining action... shrinks with every step. "
             "In this example it falls from 0.42 to 0.17 in four steps, and the robot ends up exactly where a much "
             "longer plan would have taken it.")


def safe_name(voice_id: str) -> str:
    """A voice id as a file or folder name: "en-US-Steffan:DragonHDLatestNeural" -> "en-US-Steffan_DragonHDLatestNeural"."""
    return re.sub(r"[^A-Za-z0-9.-]+", "_", voice_id).strip("_") or "voice"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--service", help="speech service (default: voice.service of config/channel.json)")
    ap.add_argument("--out", default=str(REPO / "voice-reference"), help="parent folder (git-ignored)")
    a = ap.parse_args(argv)
    cfg = voice.channel_config(str(REPO)).get("voice", {})
    service = (a.service or cfg.get("service") or "piper").lower()
    if service not in ("azure", "piper"):
        print(f"error: the reference is rendered with azure or piper, not {service}", file=sys.stderr)
        return 2
    ok, why = voice.available(service, str(REPO))
    if not ok:
        print(f"error: {service}: {why}", file=sys.stderr)
        return 1
    voice_id = voice.azure_settings(cfg)["voice"] if service == "azure" else voice.piper_settings(cfg)["voice"]
    folder = Path(a.out) / f"{dt.date.today().isoformat()}_{safe_name(voice_id)}"
    folder.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as td:
        svc = voice.speech_service(str(REPO / "templates" / "manim"), name=service, cache_dir=td)
        r = svc.generate_from_text(REFERENCE)
        src = Path(td) / r["original_audio"]
        dst = folder / f"reference{src.suffix}"
        dst.write_bytes(src.read_bytes())
    if dst.suffix != ".wav":
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(dst), "-ac", "1", str(folder / "reference.wav")],
                       check=True)
    duration = voice.audio_duration(dst)
    (folder / "timings.json").write_text(json.dumps(r["word_boundaries"], indent=1), encoding="utf-8")
    info = {"voice": voice_id, "service": service, "date": dt.date.today().isoformat(),
            "settings": {k: v for k, v in r["input_data"].items() if k != "input_text"},
            "text": REFERENCE, "duration_s": round(duration, 3),
            "words_per_minute": round(60.0 * voice.spoken_words(REFERENCE) / duration, 1)}
    (folder / "reference.json").write_text(json.dumps(info, indent=2), encoding="utf-8")
    print(f"{folder}: {info['duration_s']} s, {info['words_per_minute']} words per minute ({voice_id})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
