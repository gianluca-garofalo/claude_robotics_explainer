#!/usr/bin/env bash
[ -n "${BASH_VERSION:-}" ] || exec bash "$0" "$@"   # started from sh or zsh: run under bash
# Render the Manim scenes of a run and check the resulting files (deterministic; never uploads anything).
#
#   tools/render_video.sh runs/<run> --check                   # every scene at -ql, silent, into video/checks/
#   tools/render_video.sh runs/<run> --quality h               # final renders (1080p60, configured voice) into video/renders/
#   options: --voice NAME (piper, azure, recorded, silent), --fps N (frame rate other than the preset)
#   tools/render_video.sh runs/<run> --quality h --scene hilltop.py:Hilltop        # one scene (CI renders scenes in parallel)
#   tools/render_video.sh --template-check                     # render templates/manim/scene_template.py at -ql
#
# Scenes are video/scenes/*.py (common.py, voice.py excluded); every class deriving from a *Scene class is rendered.
# Each MP4 is copied with its captions (.srt, written by manim-voiceover) when there are any, and with its layout log
# (<Class>.layout.json: text boxes, paths and on-screen timeline, from tools/video/layout_probe.py) for the design and
# reading-time checks. Missing helper modules (voice.py, reading_model.py) are copied from templates/manim/.
# Voice: --voice, else $VOICE_SERVICE, else "voice.service" in config/channel.json (piper). Drafts are silent. A final
# render whose voice cannot work here (Piper without its model: ./setup.sh downloads it) stops before rendering.
# Manim: $MANIM, else .venv/bin/manim, else manim on PATH. Python for the checks: $PYTHON, else .venv/bin/python, else
# python3. Media caches go to video/media/ (git-ignored). Runs under bash (3.2 or later) from any shell.
set -euo pipefail

usage() { sed -n '3,18p' "$0" | sed 's/^# \{0,1\}//'; exit "${1:-0}"; }
case "${1:-}" in -h|--help) usage 0 ;; esac

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MANIM="${MANIM:-$REPO/.venv/bin/manim}"
[ -x "$MANIM" ] || MANIM="$(command -v manim || true)"
PY="${PYTHON:-}"
[ -n "$PY" ] || { [ -x "$REPO/.venv/bin/python" ] && PY="$REPO/.venv/bin/python"; } || true
[ -n "$PY" ] || PY=python3
if [ -z "$MANIM" ]; then
  echo "error: manim not found; run ./setup.sh (creates .venv) or set MANIM=/path/to/manim" >&2
  exit 3
fi
MPY="${MANIM_PYTHON:-}"            # the Python that has Manim, to run the layout probe
for cand in "$(dirname "$MANIM")/python" "$(dirname "$MANIM")/python3"; do
  [ -n "$MPY" ] || { [ -x "$cand" ] && MPY="$cand"; }
done

export CHANNEL_CONFIG="${CHANNEL_CONFIG:-$REPO/config/channel.json}"   # runs outside the repository use its settings

render_one() {  # file class quality media_dir out_file
  local file="$1" cls="$2" q="$3" media="$4" out="$5" dir stem found layout stamp
  dir="$(cd "$(dirname "$file")" && pwd)"; stem="$(basename "$file" .py)"
  stamp="$(mktemp "$media/.stamp.XXXXXX")"     # one per render: renders running side by side cannot clash
  layout="${out%.mp4}"; layout="${layout%_ql}.layout.json"
  echo "== manim -q$q${FPS:+ at $FPS fps} $(basename "$file") $cls (voice: ${VOICE_SERVICE:-silent})"
  if [ -n "$MPY" ]; then
    mkdir -p "$(dirname "$layout")"
    ( cd "$dir" && "$MPY" "$REPO/tools/video/layout_probe.py" --probe-out "$layout" -- \
        -q"$q" ${FPS:+--frame_rate "$FPS"} --media_dir "$media" --disable_caching "$(basename "$file")" "$cls" ) \
      > "$media/$stem.$cls.log" 2>&1 || { tail -n 30 "$media/$stem.$cls.log" >&2; echo "error: render failed: $stem $cls" >&2; rm -f "$stamp"; return 1; }
  else
    echo "   warning: no Python next to $MANIM (set MANIM_PYTHON): rendering without the layout log" >&2
    ( cd "$dir" && "$MANIM" -q"$q" ${FPS:+--frame_rate "$FPS"} --media_dir "$media" --disable_caching \
        "$(basename "$file")" "$cls" ) \
      > "$media/$stem.$cls.log" 2>&1 || { tail -n 30 "$media/$stem.$cls.log" >&2; echo "error: render failed: $stem $cls" >&2; rm -f "$stamp"; return 1; }
  fi
  found="$(find "$media/videos/$stem" -name "$cls.mp4" -newer "$stamp" -print -quit 2>/dev/null || true)"
  rm -f "$stamp"
  [ -n "$found" ] || { echo "error: no mp4 produced for $stem $cls" >&2; return 1; }
  mkdir -p "$(dirname "$out")"; cp "$found" "$out"; echo "   -> $out"
  if [ -f "${found%.mp4}.srt" ]; then cp "${found%.mp4}.srt" "${out%.mp4}.srt"; echo "   -> ${out%.mp4}.srt"; fi
  if [ -f "$layout" ]; then echo "   -> $layout"; fi
}

voice_for() {  # draft|final [name]: the service to use (drafts are silent)
  local py="${MPY:-$PY}" flag=""
  [ "$1" = draft ] && flag="--draft"
  "$py" "$REPO/templates/manim/voice.py" resolve $flag --start "$REPO" ${2:+"$2"}
}

if [ "${1:-}" = "--template-check" ]; then
  export VOICE_SERVICE=silent
  media="$(mktemp -d)"
  render_one "$REPO/templates/manim/scene_template.py" TemplateScene l "$media" "$media/TemplateScene_ql.mp4"
  rc=0; "$PY" "$REPO/tools/check_video.py" "$media/TemplateScene_ql.mp4" --quality l --min-duration 3 || rc=$?
  [ -s "$media/TemplateScene_ql.srt" ] || { echo "error: no captions written" >&2; rc=1; }
  if [ -f "$media/TemplateScene.layout.json" ]; then
    "$PY" "$REPO/tools/video/check_design.py" --layout "$media/TemplateScene.layout.json" --no-frames || rc=1
    "$PY" "$REPO/tools/video/check_reading.py" --layout "$media/TemplateScene.layout.json" || rc=1
    "$PY" "$REPO/tools/video/check_selfcontained.py" --layout "$media/TemplateScene.layout.json" \
      --srt "$media/TemplateScene_ql.srt" || rc=1
  fi
  echo "(temporary folder, delete it when done: $media)"
  exit $rc
fi

[ $# -ge 1 ] || usage 1
case "$1" in -h|--help) usage 0;; esac
RUN="$1"; shift
[ -d "$RUN" ] || RUN="$REPO/$RUN"
[ -d "$RUN/video" ] || { echo "error: $RUN/video not found" >&2; exit 1; }
RUN="$(cd "$RUN" && pwd)"

MODE=final; Q=""; SCENES=(); VOICE_ARG=""; FPS=""
while [ $# -gt 0 ]; do
  case "$1" in
    --check) MODE=check ;;
    --quality) Q="${2:?--quality needs a value: l, m, h or k}"; shift ;;
    --voice) VOICE_ARG="${2:?--voice needs a name}"; shift ;;
    --fps) FPS="${2:?--fps needs a number}"; shift ;;
    --scene) SCENES+=("${2:?--scene needs file.py:Class}"); shift ;;
    -h|--help) usage 0 ;;
    *) echo "unknown argument: $1" >&2; usage 1 ;;
  esac
  shift
done
if [ "$MODE" = check ]; then Q=l; VOICE_SERVICE="$(voice_for draft "$VOICE_ARG")"
else Q="${Q:-m}"; VOICE_SERVICE="$(voice_for final "$VOICE_ARG")"
fi
export VOICE_SERVICE
if [ "$MODE" = final ] && [ -z "$FPS" ]; then   # optional "video.fps" in config/channel.json (e.g. 30 for 1080p30)
  FPS="$("$PY" -c 'import json,sys; print(json.load(open(sys.argv[1])).get("video", {}).get("fps") or "")' \
    "$CHANNEL_CONFIG" 2>/dev/null || true)"
fi
if [ "$MODE" = final ]; then                     # no fallback voice: say what is missing and stop
  "${MPY:-$PY}" "$REPO/templates/manim/voice.py" check "$VOICE_SERVICE" --start "$REPO" >&2 || {
    echo "error: the final render needs the $VOICE_SERVICE voice; nothing was rendered" >&2; exit 1; }
fi
case "$Q" in l|m|h|k) ;; *) echo "error: --quality must be l, m, h or k" >&2; exit 1;; esac
case "$FPS" in ""|[1-9]|[1-9][0-9]|1[0-1][0-9]|120) ;; *) echo "error: --fps must be 1 to 120" >&2; exit 1;; esac

MEDIA="$RUN/video/media"; mkdir -p "$MEDIA"
if [ "$MODE" = check ]; then OUTDIR="$RUN/video/checks"; else OUTDIR="$RUN/video/renders"; fi


for helper in voice.py reading_model.py; do
  if [ -f "$RUN/video/scenes/common.py" ] && [ ! -f "$RUN/video/scenes/$helper" ]; then
    cp "$REPO/templates/manim/$helper" "$RUN/video/scenes/$helper"; echo "copied templates/manim/$helper into video/scenes/"
  fi
done
EXPLICIT=${#SCENES[@]}
if [ ${#SCENES[@]} -eq 0 ]; then
  for f in "$RUN"/video/scenes/*.py; do
    case "$(basename "$f")" in common.py|voice.py|reading_model.py) continue ;; esac
    while read -r cls; do SCENES+=("$(basename "$f"):$cls"); done < <(
      grep -E '^class [A-Za-z_][A-Za-z0-9_]*\([A-Za-z0-9_.]*Scene\):' "$f" | sed -E 's/^class ([A-Za-z0-9_]+)\(.*/\1/')
  done
fi
[ ${#SCENES[@]} -gt 0 ] || { echo "error: no scenes found in $RUN/video/scenes" >&2; exit 1; }

OUTS=(); FAILED=0
for s in "${SCENES[@]}"; do
  file="${s%%:*}"; cls="${s##*:}"
  if [ "$MODE" = check ]; then out="$OUTDIR/${cls}_ql.mp4"; else out="$OUTDIR/${cls}.mp4"; fi
  if render_one "$RUN/video/scenes/$file" "$cls" "$Q" "$MEDIA" "$out"; then OUTS+=("$out"); else FAILED=1; fi
done
[ ${#OUTS[@]} -gt 0 ] || exit 1
report="$OUTDIR/check.json"
if [ "$EXPLICIT" -gt 0 ]; then report="$OUTDIR/check-$(basename "${OUTS[0]}" .mp4).json"; fi
"$PY" "$REPO/tools/check_video.py" "${OUTS[@]}" --quality "$Q" ${FPS:+--fps "$FPS"} --json "$report" || FAILED=1
exit $FAILED
