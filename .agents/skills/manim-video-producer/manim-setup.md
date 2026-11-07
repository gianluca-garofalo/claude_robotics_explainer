# Manim setup and troubleshooting

Tested on Ubuntu 24.04: Python 3.13 in a venv, Manim Community 0.22.1 (ManimPango 0.7.1, pycairo 1.29.2, PyAV 19.0.2),
numpy 2.5, ffmpeg 6.1, TeX Live 2023 with dvisvgm 3.2. `./setup.sh` creates `.venv`.

Manim needs:

1. Cairo and Pango **with development headers** (pycairo and ManimPango build from source when no wheel matches the
   Python version). Debian/Ubuntu: `libcairo2-dev libpango1.0-dev pkg-config python3-dev build-essential`. macOS:
   `brew install pkg-config cairo pango`.
2. ffmpeg (the checks use ffprobe and ffmpeg).
3. LaTeX and dvisvgm, only for `Tex`/`MathTex`. Debian/Ubuntu: `texlive-latex-base texlive-latex-extra
   texlive-fonts-recommended texlive-science cm-super dvisvgm`. macOS: MacTeX (or BasicTeX plus `sudo tlmgr install
   standalone preview doublestroke relsize fundus-calligra wasysym physics dvisvgm rsfs wasy cm-super everysel
   setspace`). Windows: MiKTeX, or WSL.

| Symptom | Cause | Fix |
|---|---|---|
| `pip install manim` fails building ManimPango | missing Pango headers | install `libpango1.0-dev` (or brew `pango`), retry in the venv |
| `AttributeError: install_layout` while building `srt` | Debian's patched system pip/setuptools | use the venv (setup.sh upgrades pip/setuptools/wheel in it) |
| `LaTeX error converting to dvi` / `dvisvgm not found` | no TeX Live or no dvisvgm | install the packages above, or `NO_LATEX=1` for drafts |
| a scene renders for many minutes | `MathTex` rebuilt every frame in `always_redraw` | live numbers with `readout()` |
| `ModuleNotFoundError: common` | rendered from another folder | use `tools/render_video.sh`, which runs from `video/scenes/` |
| "SoX could not be found" | manim-voiceover's optional dependency | harmless; install `sox` to silence it |

Check the installation with `.venv/bin/manim checkhealth` and the template with
`bash tools/render_video.sh --template-check`. Docker alternative:
`docker run --rm -it -v "$PWD:/manim" manimcommunity/manim:v0.22.1 manim -qm scene.py Scene`.

Narration: `manim-voiceover` gives `VoiceoverScene`, bookmark sync and one SRT caption file per scene. The voice is one
setting, `voice.service` in `config/channel.json`: `azure` (the channel's voice; `AZURE_SUBSCRIPTION_KEY` and
`AZURE_SERVICE_REGION` from the environment, never a file), `piper` (keyless and offline; its model in `.cache/piper/`,
which `./setup.sh` downloads), `recorded` (the owner's recordings) or `silent`. Drafts (`--check`) are always silent;
`--voice NAME` picks the voice of one final render. The final narration is synthesized once
(`tools/video/synthesize_voice.py`); a missing key or model stops it with the reason before anything renders, and no
other voice stands in.
