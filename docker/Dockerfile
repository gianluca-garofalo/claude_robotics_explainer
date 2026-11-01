# CI image for the deterministic jobs: final renders with narration, assembly, gates, render checks.
# No secrets inside; built and pushed to GitHub Container Registry by .github/workflows/ci-image.yml.
# Base: the official Manim Community image (Debian, Python venv in /opt/venv with Manim, TeX Live with dvisvgm).
FROM manimcommunity/manim:v0.22.1

USER root
ENV DEBIAN_FRONTEND=noninteractive \
    PLAYWRIGHT_BROWSERS_PATH=/opt/ms-playwright \
    NODE_PATH=/opt/node/node_modules \
    KATEX_DIST=/opt/node/node_modules/katex/dist \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    MPLBACKEND=Agg

# ffmpeg CLI (assembly, checks), SoX (voice speed), fonts for captions and thumbnails, Node.js for the HTML check
RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg sox git ca-certificates fontconfig fonts-dejavu-core nodejs npm \
 && rm -rf /var/lib/apt/lists/*

# Python: the project's stack (with Piper), the Azure text-to-speech backend and the publishing clients
COPY requirements.txt requirements-voice.txt requirements-publish.txt /tmp/req/
RUN /opt/venv/bin/python -m pip install -r /tmp/req/requirements.txt -r /tmp/req/requirements-voice.txt \
        -r /tmp/req/requirements-publish.txt \
 && rm -rf /tmp/req

# Piper voice model of the default no-key narration voice ("voice.piper" in config/channel.json), downloaded once
# into the image from huggingface.co (repository rhasspy/piper-voices) with its MODEL_CARD (licence) and SHA-256
COPY config/channel.json /tmp/piper/config/channel.json
COPY tools/video/piper_model.py /tmp/piper/tools/video/piper_model.py
RUN /opt/venv/bin/python /tmp/piper/tools/video/piper_model.py fetch --dest /opt/piper && rm -rf /tmp/piper
ENV PIPER_MODEL_DIR=/opt/piper

# Node: Playwright + KaTeX 0.16.9 at the locked versions, and Chromium with its system libraries
COPY package.json package-lock.json /opt/node/
RUN cd /opt/node && npm ci --no-audit --no-fund \
 && npx playwright install --with-deps chromium \
 && npm cache clean --force && rm -rf /var/lib/apt/lists/*

ENV PATH=/opt/venv/bin:$PATH
RUN python --version && manim --version && ffmpeg -version | head -n 1 && node --version \
 && latex --version | head -n 1 && dvisvgm --version && fc-match "DejaVu Sans:bold" \
 && python -c "import piper" && ls /opt/piper
WORKDIR /work
