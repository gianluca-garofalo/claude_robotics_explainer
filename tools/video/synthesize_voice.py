#!/usr/bin/env python3
"""Synthesize a run's narration once, before rendering, without running any code written during the run.

Usage:
  python3 tools/video/synthesize_voice.py runs/<run> [--service piper|azure|recorded|silent]

Reads every `self.voiceover(text="...")` literal of video/scenes/*.py through the syntax tree (the same extraction
as tools/video/voice_script.py; nothing is imported or executed), asks the speech service of the repository's own
templates/manim/voice.py for each block that has no audio yet, and writes video/voice/<key>.mp3, <key>.timings.json
(word timings, when the service returns them) and video/voice/manifest.json. Render jobs then use
VOICE_SERVICE=recorded and need no text-to-speech key: the keys never reach a job that runs the run's scene code.
Audio already in video/voice/ (your own recordings) is kept; a file this tool made earlier keeps its recorded source.
The service is --service, else $VOICE_SERVICE, else "voice.service" in config/channel.json (piper: offline, no key).
Piper needs its voice model (./setup.sh downloads it; the CI image has it): without it the tool stops and says how to
get it, and never uses another voice instead. The manifest records the service, the Piper voice model and whether the
word timings are measured or estimated. Exit status 1 when a block's text is not a literal or synthesis fails.
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
from _common import CONFIG, load_json, rel, resolve_run, sha256_file, utc_now, write_json  # noqa: E402
import voice_script as VS  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run")
    ap.add_argument("--service")
    a = ap.parse_args()
    run = resolve_run(a.run)
    channel = load_json(CONFIG / "channel.json")
    service = (a.service or os.environ.get("VOICE_SERVICE") or channel.get("voice", {}).get("service", "piper"))
    service = service.strip().lower()
    blocks, problems = {}, []
    for f in sorted((run / "video" / "scenes").glob("*.py")):
        if f.name in ("common.py", "voice.py", "reading_model.py"):
            continue
        for key, text in VS.blocks(f):
            if key is None:
                problems.append(f"{rel(f)}: {text}")
            else:
                blocks.setdefault(key, text)
    if problems:
        print("\n".join(f"error: {p}" for p in problems), file=sys.stderr)
        return 1
    out = run / "video" / "voice"
    out.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(REPO / "templates" / "manim"))
    import voice  # the repository's copy, never the run's

    def existing(key):
        return next((out / f"{key}{s}" for s in voice.AUDIO_SUFFIXES if (out / f"{key}{s}").exists()), None)

    old = load_json(out / "manifest.json") if (out / "manifest.json").exists() else {}
    old_blocks = old.get("blocks", {})

    def made_earlier(key, f):
        """The service this tool used for f in an earlier run, if f is unchanged since (else None: a recording)."""
        prev = old_blocks.get(key, {})
        return prev.get("source") if prev.get("file") == f.name and prev.get("sha256") == sha256_file(f) else None

    todo = []
    for k in blocks:
        f = existing(k)
        before = made_earlier(k, f) if f else None
        if f is None or (before not in (None, "kept", "recorded") and before != service and service != "recorded"):
            todo.append(k)                     # missing, or synthesized earlier with another service: (re)make it
    if service == "recorded" and todo:
        print(f"error: no recording for {len(todo)} block(s): {', '.join(todo)} "
              "(python3 tools/video/voice_script.py lists them)", file=sys.stderr)
        return 1
    manifest = {"schema_version": 1, "run": run.name, "service": service, "created_at": utc_now(),
                "timings": voice.ESTIMATED.get(service, "from the recordings (estimated, linear)"), "blocks": {}}
    if service == "piper":
        manifest["voice_model"] = voice.piper_settings(channel.get("voice", {}))["voice"]
    elif service == "azure":
        manifest["voice_model"] = voice.azure_settings(channel.get("voice", {}))["voice"]
    with tempfile.TemporaryDirectory() as td:
        try:
            svc = voice.speech_service(str(REPO / "templates" / "manim"), name=service, cache_dir=td) if todo else None
        except (RuntimeError, ValueError, ImportError) as exc:   # missing key, model or package: say which, no traceback
            print(f"error: {exc}", file=sys.stderr)
            return 1
        for key, text in blocks.items():
            kept = existing(key)
            if key in todo:
                try:
                    data = svc.generate_from_text(text, cache_dir=td)
                except Exception as exc:  # noqa: BLE001 - report which block failed, then stop
                    print(f"error: {service} failed on block {key} ({text[:60]!r}): {exc}", file=sys.stderr)
                    return 1
                src = Path(td) / data["original_audio"]
                dst = out / f"{key}{src.suffix or '.mp3'}"
                if kept is not None and kept != dst:
                    kept.unlink()
                shutil.copyfile(src, dst)
                timings = out / f"{key}.timings.json"
                if data.get("word_boundaries"):
                    write_json(timings, data["word_boundaries"])
                elif timings.exists():
                    timings.unlink()
                origin = service
            else:
                dst, origin = kept, made_earlier(key, kept) or "kept"
            manifest["blocks"][key] = {"text": text, "file": dst.name, "source": origin, "sha256": sha256_file(dst),
                                       "seconds": round(voice.audio_duration(dst), 3)}
            if key in todo:                    # how the service made it: the prosody rate applied, the takes
                made = data.get("input_data") or {}
                manifest["blocks"][key].update({k: made[k] for k in ("applied_rate_pct", "takes", "fault")
                                                if k in made})
            elif made_earlier(key, dst):
                manifest["blocks"][key].update({k: old_blocks[key][k] for k in ("applied_rate_pct", "takes", "fault")
                                                if k in old_blocks[key]})
    sources = [b["source"] for b in manifest["blocks"].values()]
    manifest["sources"] = {x: sources.count(x) for x in sorted(set(sources))}
    write_json(out / "manifest.json", manifest)
    total_s = sum(b["seconds"] for b in manifest["blocks"].values())
    model = f" ({manifest['voice_model']})" if manifest.get("voice_model") else ""
    print(f"Narration: {len(blocks)} block(s), {len(todo)} synthesized with {service}{model}, "
          f"{len(blocks) - len(todo)} kept "
          f"({', '.join(f'{k}: {v}' for k, v in manifest['sources'].items())}); {total_s:.1f} s of narration"
          f"; word timings {manifest['timings']}; wrote {rel(out / 'manifest.json')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
