#!/usr/bin/env bash
[ -n "${BASH_VERSION:-}" ] || exec bash "$0" "$@"   # started from sh or zsh: run under bash
# Set up the local toolchain for the pipeline (Linux, WSL and macOS; runs under bash from any shell).
#
#   ./setup.sh                        # user-space setup: .venv (Manim, numpy, scipy, sympy, matplotlib, PyYAML,
#                                     # Piper, the Azure voice backend), the Piper voice model (.cache/piper/), npm
#                                     # packages (Playwright, KaTeX 0.16.9), Chromium for Playwright, self-test
#   ./setup.sh --check                # report what is present or missing; change nothing
#   ./setup.sh --with-system-deps     # also install system packages with apt or Homebrew (sudo on Linux unless
#                                     # root; apt runs non-interactively: a cloud environment's setup script)
#   options: --no-node (skip npm and Chromium), --no-browser (skip the Chromium download), --no-voice-model,
#            --system-deps-only (install the system packages, then stop)
#
# System packages (Cairo/Pango headers, ffmpeg, TeX + dvisvgm, Node.js, the DejaVu fonts) are only printed unless
# you pass --with-system-deps. Windows: use WSL (Ubuntu). If ./setup.sh says "permission denied" (an unzip tool
# dropped the exec bit): chmod +x setup.sh tools/*.sh tools/ci/*.sh
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

CHECK=0; SYSDEPS=0; SYSONLY=0; NODE=1; BROWSER=1; VOICE_MODEL=1
for a in ${1+"$@"}; do                 # ${1+...}: bash 3.2 (macOS) treats an empty "$@" as unbound under set -u
  case "$a" in
    --check) CHECK=1 ;;
    --with-system-deps) SYSDEPS=1 ;;
    --system-deps-only) SYSDEPS=1; SYSONLY=1 ;;
    --no-node) NODE=0 ;;
    --no-browser) BROWSER=0 ;;
    --no-voice-model) VOICE_MODEL=0 ;;
    -h|--help) sed -n '3,16p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown option $a" >&2; exit 2 ;;
  esac
done

OS="$(uname -s)"
APT_PKGS="build-essential python3-dev python3-venv pkg-config libcairo2-dev libpango1.0-dev ffmpeg sox \
texlive-latex-base texlive-latex-extra texlive-fonts-recommended texlive-science cm-super dvisvgm nodejs npm \
fonts-dejavu-core fontconfig"
BREW_PKGS="python@3.13 pkg-config cairo pango fontconfig ffmpeg sox node"
BREW_CASKS="mactex-no-gui font-dejavu"            # MacTeX brings latex and dvisvgm; DejaVu is the scenes' font
if [ "$(uname -s)" = Darwin ] && [ -d /Library/TeX/texbin ]; then
  case ":$PATH:" in *:/Library/TeX/texbin:*) ;; *) PATH="$PATH:/Library/TeX/texbin" ;; esac
fi

have() { command -v "$1" >/dev/null 2>&1; }
# a Python >= 3.11 for .venv: macOS's /usr/bin/python3 is 3.9, so look for a newer one first
find_python() {
  PYBIN=""
  for cand in python3.13 python3.12 python3.11 python3; do
    if have "$cand" && "$cand" -c 'import sys; sys.exit(sys.version_info < (3, 11))' 2>/dev/null
    then PYBIN="$cand"; break; fi
  done
}
node_ready() { have node && have npm && node -e 'process.exit(parseInt(process.versions.node, 10) < 18 ? 1 : 0)'; }
find_python

missing=(); sys_missing=()
report() {  # name ok hint [user]  (user = installed by this script; anything else is a system package)
  if [ "$2" = 1 ]; then printf '  %-34s ok\n' "$1"; return; fi
  printf '  %-34s MISSING  %s\n' "$1" "$3"; missing+=("$1")
  [ "${4:-}" = user ] || sys_missing+=("$1")
}

echo "Prerequisites:"
py_ok=0; [ -n "$PYBIN" ] && py_ok=1
report "python >= 3.11" $py_ok "(tools use tomllib; macOS: brew install python@3.13)"
report "pkg-config" "$(have pkg-config && echo 1 || echo 0)" "(builds pycairo/ManimPango)"
cp_ok=0; have pkg-config && pkg-config --exists cairo pangocairo 2>/dev/null && cp_ok=1
report "cairo + pango headers" $cp_ok "(libcairo2-dev libpango1.0-dev / brew cairo pango)"
report "ffmpeg + ffprobe" "$(have ffmpeg && have ffprobe && echo 1 || echo 0)" "(video encode and checks)"
report "latex + dvisvgm" "$(have latex && have dvisvgm && echo 1 || echo 0)" "(MathTex in Manim; drafts work without, NO_LATEX=1)"
font_ok=0
if have fc-list && fc-list 2>/dev/null | grep -i "DejaVu Sans" >/dev/null; then font_ok=1   # no grep -q: pipefail
elif ls "$HOME/Library/Fonts"/DejaVuSans*.ttf /Library/Fonts/DejaVuSans*.ttf >/dev/null 2>&1; then font_ok=1; fi
report "DejaVu fonts" $font_ok "(the scenes' font: another font changes text widths and the design checks)"
node_ok=0; node_ready && node_ok=1
[ $NODE = 1 ] && report "node >= 18 + npm" $node_ok "(HTML render checks)"
report ".venv (Python env)" "$([ -x .venv/bin/python ] && echo 1 || echo 0)" "(created by ./setup.sh)" user
report ".venv manim" "$([ -x .venv/bin/manim ] && echo 1 || echo 0)" "(installed by ./setup.sh)" user
[ $NODE = 1 ] && report "node_modules (playwright, katex)" "$([ -d node_modules/playwright ] && [ -d node_modules/katex ] && echo 1 || echo 0)" "(installed by ./setup.sh)" user
# final renders need their voice: no other voice stands in
if [ -x .venv/bin/python ]; then
  voice_state="$(.venv/bin/python templates/manim/voice.py check piper 2>/dev/null || true)"
  printf '  %-34s %s\n' "piper voice (final renders)" "${voice_state#piper: }"
fi

if [ $CHECK = 1 ]; then
  if [ ${#missing[@]} -gt 0 ]; then
    echo
    if [ ${#sys_missing[@]} -gt 0 ]; then
      case "$OS" in
        Linux) echo "Debian/Ubuntu system packages: sudo apt-get install -y $APT_PKGS" ;;
        Darwin) echo "macOS (Homebrew): brew install $BREW_PKGS && brew install --cask $BREW_CASKS" ;;
      esac
    fi
    echo "Then: ./setup.sh"
    exit 1
  fi
  echo "All prerequisites present."; exit 0
fi

if [ $SYSDEPS = 1 ]; then
  # shellcheck disable=SC2086  # the package lists (and an empty $SUDO) split into words on purpose
  case "$OS" in
    Linux) have apt-get || { echo "apt-get not found: install the packages listed above by hand" >&2; exit 1; }
           SUDO=""                    # root (a container, a cloud environment's setup script): no sudo needed
           if [ "$(id -u)" != 0 ]; then
             have sudo || { echo "not root and no sudo: install the packages listed above as root" >&2; exit 1; }
             SUDO="sudo"
           fi
           pkgs="$APT_PKGS"
           # a Node.js >= 18 with npm is already here (a cloud image's own): leave the distribution's out
           if [ $node_ok = 1 ]; then pkgs="${pkgs/nodejs npm /}"; fi
           $SUDO env DEBIAN_FRONTEND=noninteractive apt-get update \
             || echo "note: apt-get update reported errors; installing from the package lists as they are" >&2
           # no questions at all: debconf (DEBIAN_FRONTEND) and dpkg's changed-config-file prompt (keep the
           # file on the system, dpkg's default answer), which a setup script without a terminal cannot answer
           $SUDO env DEBIAN_FRONTEND=noninteractive apt-get install -y -o Dpkg::Options::=--force-confdef \
             -o Dpkg::Options::=--force-confold $pkgs ;;
    Darwin) have brew || { echo "Homebrew not found: https://brew.sh" >&2; exit 1; }
            brew install $BREW_PKGS && brew install --cask $BREW_CASKS ;;
    *) echo "unsupported OS $OS: use WSL on Windows" >&2; exit 1 ;;
  esac
  if [ $SYSONLY = 1 ]; then echo "System packages installed."; exit 0; fi
  find_python; py_ok=0; [ -n "$PYBIN" ] && py_ok=1          # what the packages just brought
  node_ok=0; node_ready && node_ok=1
elif [ ${#sys_missing[@]} -gt 0 ]; then
  echo
  echo "Some system prerequisites are missing; the steps below may fail. Install them with:"
  case "$OS" in
    Linux) echo "  sudo apt-get install -y $APT_PKGS   (or: ./setup.sh --with-system-deps)" ;;
    Darwin) echo "  brew install $BREW_PKGS && brew install --cask $BREW_CASKS   (or: ./setup.sh --with-system-deps)" ;;
  esac
  echo
fi

echo "== Python venv (.venv)"
[ $py_ok = 1 ] || { echo "Python >= 3.11 is required (macOS: brew install python@3.13)" >&2; exit 1; }
[ -x .venv/bin/python ] || "$PYBIN" -m venv .venv
# a fresh pip/setuptools inside the venv avoids Debian's patched system pip (install_layout errors)
.venv/bin/python -m pip install --upgrade pip setuptools wheel
.venv/bin/python -m pip install -r requirements.txt -r requirements-voice.txt
# optional: without it Google Trends is recorded as unavailable
.venv/bin/python -m pip install -r requirements-search.txt \
  || echo "note: optional requirements-search.txt not installed; Google Trends will be recorded as unavailable"

if [ $NODE = 1 ]; then
  if [ $node_ok = 1 ]; then
    echo "== npm packages (playwright, katex 0.16.9)"
    npm install --no-fund --no-audit
    if [ $BROWSER = 1 ]; then
      echo "== Chromium for Playwright"
      npx playwright install chromium
    fi
  else
    echo "Node.js >= 18 not found: skipping the HTML render checker setup" >&2
  fi
fi

if [ $VOICE_MODEL = 1 ]; then
  echo "== Piper voice model (default narration voice: offline, no key)"
  # from huggingface.co (rhasspy/piper-voices) into .cache/piper/, with its MODEL_CARD (licence)
  .venv/bin/python tools/video/piper_model.py fetch \
    || echo "note: Piper voice model not downloaded (see the message above): final renders stop until it is here" \
            "(run ./setup.sh again); drafts are silent and need none" >&2
fi

echo "== Self-test"
.venv/bin/manim --version
.venv/bin/python tools/lint_project.py --config || echo "warning: the configuration lint reported problems (above)" >&2
.venv/bin/python tools/check_source.py --all \
  || echo "warning: a source document in sources/ has errors (above): /produce-from-source stops on them" >&2
page=""
for f in sources/*/explainer.html; do [ -f "$f" ] && { page="$f"; break; }; done
if [ $NODE = 1 ] && [ -d node_modules/playwright ] && [ -n "$page" ]; then
  rc=0; node tools/check_html.js "$page" --offline || rc=$?
  if [ $rc = 3 ]; then
    echo "Render checker not ready (no Chromium): run 'npx playwright install chromium' (series episodes do not" \
         "need it; new explainers do)" >&2
  elif [ $rc != 0 ]; then echo "warning: the render check of $page reported problems (exit $rc, above)" >&2; fi
fi
echo "Setup done. Next: open Claude Code in this folder and type /produce-from-source sources/<name> (episodes of"
echo "a series made from a source document) or /produce-explainer (from the news). README.md has the map."
