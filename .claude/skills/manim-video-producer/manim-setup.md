# Manim setup and troubleshooting

Tested combination (Ubuntu 24.04): Python 3.13 in a venv, Manim Community 0.22.1 (ManimPango 0.7.1, pycairo 1.29.2,
PyAV 19.0.2), numpy 2.5, ffmpeg 6.1, TeX Live 2023 with dvisvgm 3.2. `./setup.sh` creates `.venv`.

Manim needs:

1. Cairo and Pango **with development headers**: pycairo and ManimPango build from source when no wheel matches the
   Python version. Debian/Ubuntu: `libcairo2-dev libpango1.0-dev pkg-config python3-dev build-essential`.
   macOS: `brew install pkg-config cairo pango`.
2. ffmpeg (recent Manim encodes through PyAV, but the checks use ffprobe/ffmpeg).
3. LaTeX + dvisvgm only for `Tex`/`MathTex`. Debian/Ubuntu: `texlive-latex-base texlive-latex-extra
   texlive-fonts-recommended texlive-science cm-super dvisvgm` (about 440 MB). macOS: MacTeX (or BasicTeX plus
   `sudo tlmgr install standalone preview doublestroke relsize fundus-calligra wasysym physics dvisvgm rsfs wasy
   cm-super everysel setspace`). Windows: MiKTeX, or WSL.

Known failures and fixes:

| Symptom | Cause | Fix |
|---|---|---|
| `pip install manim` fails building ManimPango | missing Pango headers | install `libpango1.0-dev` (or brew `pango`), retry in the venv |
| `AttributeError: install_layout` while building `srt` | Debian's patched system pip/setuptools | use the venv (setup.sh upgrades pip/setuptools/wheel inside it) |
| `LaTeX error converting to dvi` / `dvisvgm not found` | no TeX Live or no dvisvgm | install the packages above, or use `NO_LATEX=1` for drafts |
| a scene renders for many minutes | `MathTex` rebuilt every frame in `always_redraw` | live numbers with `readout()` (Pango Text) |
| `ModuleNotFoundError: common` | rendered from another folder | use `tools/render_video.sh`, which runs from `video/scenes/` |

Check the installation with `.venv/bin/manim checkhealth` and the template with `bash tools/render_video.sh --template-check`.

Docker alternative: `docker run --rm -it -v "$PWD:/manim" manimcommunity/manim:v0.22.1 manim -qm scene.py Scene`.

Narration: `manim-voiceover` (in `requirements.txt`) provides `VoiceoverScene`, bookmark sync and an SRT caption file
per scene. Its "SoX could not be found" warning is harmless; install `sox` (apt or brew) to silence it. The voice is
one setting, `voice.service` in `config/channel.json`: `piper` (the voice of final renders: offline, no key),
`azure`, `recorded` or `silent`. Draft renders (`--check`) are always silent; `--voice NAME` picks the voice of one
final render. A final render whose voice cannot work here stops before rendering and says why: Piper needs its model
in `.cache/piper/` (`./setup.sh` downloads it) and there is no fallback voice. Piper's word timings are estimated
sentence by sentence, so keep animations on bookmarks tolerant of a few tenths of a second. The final narration is
synthesized once in CI (`tools/video/synthesize_voice.py`), with any keys only there; a missing key or model fails
fast with the reason instead of manim-voiceover's interactive prompt, which would hang a CI job.
