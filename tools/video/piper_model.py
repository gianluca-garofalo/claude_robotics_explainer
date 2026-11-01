#!/usr/bin/env python3
"""Download and check the Piper voice model of the default no-key narration voice (voice.service "piper").

Usage:
  python3 tools/video/piper_model.py fetch [--voice NAME] [--dest DIR] [--force]
  python3 tools/video/piper_model.py path  [--voice NAME]     # where the model is; exit status 1 when it is missing
  python3 tools/video/piper_model.py info  [--voice NAME]     # source, licence lines of the model card, SHA-256
  python3 tools/video/piper_model.py list  [--lang en]        # voices in the catalogue (needs the network)

Where it comes from: the Hugging Face repository rhasspy/piper-voices (https://huggingface.co/rhasspy/piper-voices),
where the Piper project publishes its voices: <voice>.onnx (the model), <voice>.onnx.json (its config) and the
voice's MODEL_CARD (training data and licence), saved next to the model with <voice>.source.json (URLs, revision,
SHA-256, size, date). The default voice, en_US-ljspeech-medium, was trained on the LJ Speech dataset (public-domain
LibriVox readings by Linda Johnson, compiled by Keith Ito); read the saved MODEL_CARD before publishing with it.

Settings, "voice.piper" in config/channel.json:
  voice     <lang>_<REGION>-<name>-<quality>, e.g. en_US-ljspeech-medium (default)
  revision  branch, tag or commit of rhasspy/piper-voices (default main)
  sha256    expected SHA-256 of <voice>.onnx: set it after the first download to pin the file (empty: not checked)
Destination: --dest, else $PIPER_MODEL_DIR, else .cache/piper/ of the repository (git-ignored). The CI image keeps
it in /opt/piper ($PIPER_MODEL_DIR).

Network: huggingface.co, which redirects the model file to its download CDN, a host under hf.co (cdn-lfs.hf.co,
cdn-lfs-us-1.hf.co or cas-bridge.xethub.hf.co, depending on how the file is stored). When a host is unreachable or
blocked, fetch stops with exit status 2 and names the host; then allow the host, or copy the three files in by hand
from a machine that can reach it. Final renders need the model (no other voice stands in for it); draft renders are
silent and need none. Standard library only: the CI image runs it before the project's packages are installed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
HUB = "https://huggingface.co/rhasspy/piper-voices"
DEFAULT_VOICE = "en_US-ljspeech-medium"
VOICE_RE = re.compile(r"^(?P<lang>[a-z]{2,3})_(?P<region>[A-Za-z0-9]{2,3})-(?P<name>[A-Za-z0-9_]+)-"
                      r"(?P<quality>x_low|low|medium|high)$")
HOSTS_HINT = ("allow huggingface.co and its download CDN (hosts under hf.co: cdn-lfs.hf.co, cdn-lfs-us-1.hf.co, "
              "cas-bridge.xethub.hf.co)")


def settings() -> dict:
    path = Path(os.environ["CHANNEL_CONFIG"]) if os.environ.get("CHANNEL_CONFIG") else REPO / "config" / "channel.json"
    try:
        cfg = json.loads(path.read_text(encoding="utf-8")).get("voice", {}).get("piper") or {}
    except (OSError, ValueError):
        cfg = {}
    return {"voice": os.environ.get("PIPER_VOICE") or cfg.get("voice") or DEFAULT_VOICE,
            "revision": cfg.get("revision") or "main", "sha256": (cfg.get("sha256") or "").lower()}


def files_of(voice: str, revision: str) -> dict[str, str]:
    """{local file name: download URL} for a voice."""
    m = VOICE_RE.match(voice)
    if not m:
        raise SystemExit(f"error: {voice!r} is not a Piper voice name (<lang>_<REGION>-<name>-<quality>, "
                         f"e.g. {DEFAULT_VOICE})")
    folder = f"{m['lang']}/{m['lang']}_{m['region']}/{m['name']}/{m['quality']}"
    base = f"{HUB}/resolve/{urllib.parse.quote(revision, safe='')}/{folder}"
    return {f"{voice}.onnx": f"{base}/{voice}.onnx?download=true",
            f"{voice}.onnx.json": f"{base}/{voice}.onnx.json?download=true",
            f"{voice}.MODEL_CARD": f"{base}/MODEL_CARD?download=true"}


def destination(arg: str | None) -> Path:
    return Path(arg or os.environ.get("PIPER_MODEL_DIR") or REPO / ".cache" / "piper")


def find(voice: str) -> Path | None:
    """The model as templates/manim/voice.py finds it ($PIPER_MODEL, $PIPER_MODEL_DIR, .cache/piper/)."""
    places = [Path(os.environ["PIPER_MODEL"])] if os.environ.get("PIPER_MODEL") else []
    if os.environ.get("PIPER_MODEL_DIR"):
        places.append(Path(os.environ["PIPER_MODEL_DIR"]) / f"{voice}.onnx")
    places.append(REPO / ".cache" / "piper" / f"{voice}.onnx")
    return next((p for p in places if p.is_file() and Path(f"{p}.json").is_file()), None)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


class _Trail(urllib.request.HTTPRedirectHandler):
    """Remembers every host a download was redirected to, to name the one that failed."""

    def __init__(self):
        self.hosts: list[str] = []

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        self.hosts.append(urllib.parse.urlsplit(newurl).hostname or newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class FetchError(Exception):
    def __init__(self, message: str, network: bool):
        super().__init__(message)
        self.network = network


def download(url: str, dest: Path) -> tuple[str, int]:
    """Stream url into dest (atomically); returns (SHA-256, bytes)."""
    trail = _Trail()
    opener = urllib.request.build_opener(trail)
    host = urllib.parse.urlsplit(url).hostname
    try:
        with opener.open(urllib.request.Request(url, headers={"User-Agent": "remaining-action-pipeline"}),
                         timeout=60) as r:
            h, n = hashlib.sha256(), 0
            with tempfile.NamedTemporaryFile(dir=dest.parent, prefix=f".{dest.name}.", delete=False) as tmp:
                for block in iter(lambda: r.read(1 << 20), b""):
                    tmp.write(block)
                    h.update(block)
                    n += len(block)
            Path(tmp.name).replace(dest)
            return h.hexdigest(), n
    except urllib.error.HTTPError as exc:
        where = trail.hosts[-1] if trail.hosts else host
        if exc.code == 404:
            raise FetchError(f"{url.split('?')[0]}: not found (404); is the voice name right? "
                             "python3 tools/video/piper_model.py list", network=False) from exc
        raise FetchError(f"{where}: HTTP {exc.code} {exc.reason}", network=exc.code in (403, 407, 451)) from exc
    except (urllib.error.URLError, OSError) as exc:
        where = trail.hosts[-1] if trail.hosts else host
        reason = getattr(exc, "reason", exc)
        raise FetchError(f"{where}: {reason}", network=True) from exc


def fetch(a) -> int:
    s = settings()
    voice = a.voice or s["voice"]
    out = destination(a.dest)
    out.mkdir(parents=True, exist_ok=True)
    files = files_of(voice, s["revision"])
    model = out / f"{voice}.onnx"
    if model.is_file() and (out / f"{voice}.onnx.json").is_file() and not a.force:
        digest = sha256_file(model)
        if s["sha256"] and digest != s["sha256"] and voice == s["voice"]:
            print(f"error: {model} has SHA-256 {digest}, config pins {s['sha256']}: fetch --force", file=sys.stderr)
            return 1
        print(f"{voice}: already in {out} (SHA-256 {digest[:16]}...)")
        return 0
    record = {"voice": voice, "repository": HUB, "revision": s["revision"], "fetched_at":
              time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "files": {}}
    for name, url in files.items():
        try:
            digest, size = download(url, out / name)
        except FetchError as exc:
            if name.endswith("MODEL_CARD") and not exc.network:
                print(f"warning: no MODEL_CARD for {voice} ({exc}); check the licence on {HUB}", file=sys.stderr)
                continue
            print(f"error: could not download {name}: {exc}", file=sys.stderr)
            if exc.network:
                print(f"error: the network refused the download: {HOSTS_HINT}. Nothing was bypassed. Until then, "
                      "copy the model in by hand (.cache/piper/ or $PIPER_MODEL_DIR) from a machine that can reach "
                      "it: final renders stop without it; draft renders are silent and need none.", file=sys.stderr)
            return 2 if exc.network else 1
        record["files"][name] = {"url": url.split("?")[0], "sha256": digest, "bytes": size}
    digest = record["files"][f"{voice}.onnx"]["sha256"]
    if s["sha256"] and voice == s["voice"] and digest != s["sha256"]:
        model.unlink()
        print(f"error: downloaded {voice}.onnx has SHA-256 {digest}, config pins {s['sha256']}; removed it",
              file=sys.stderr)
        return 1
    (out / f"{voice}.source.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    mb = record["files"][f"{voice}.onnx"]["bytes"] / 1e6
    print(f"{voice}: {mb:.1f} MB into {out} (SHA-256 {digest})")
    for line in licence_lines(out / f"{voice}.MODEL_CARD"):
        print(f"  model card: {line}")
    if not s["sha256"]:
        print(f"  to pin this file, set voice.piper.sha256 in config/channel.json to {digest}")
    return 0


def licence_lines(card: Path) -> list[str]:
    if not card.is_file():
        return ["(no MODEL_CARD saved: check the licence on the repository page)"]
    lines = card.read_text(encoding="utf-8", errors="replace").splitlines()
    keep = [ln.strip(" *-") for ln in lines if re.search(r"licen[cs]e|dataset|url", ln, re.I)]
    return keep or ["(the MODEL_CARD names no licence: check the repository page)"]


def path_cmd(a) -> int:
    voice = a.voice or settings()["voice"]
    p = find(voice)
    if p is None:
        print(f"{voice}: not found (python3 tools/video/piper_model.py fetch)", file=sys.stderr)
        return 1
    print(p)
    return 0


def info(a) -> int:
    voice = a.voice or settings()["voice"]
    p = find(voice)
    if p is None:
        print(f"{voice}: not downloaded. Source: {HUB} ({list(files_of(voice, settings()['revision']).values())[0]})")
        return 1
    src = p.with_name(f"{voice}.source.json")
    print(f"{voice}: {p}")
    if src.is_file():
        rec = json.loads(src.read_text(encoding="utf-8"))
        print(f"  from {rec['repository']} at {rec['revision']}, fetched {rec['fetched_at']}")
    print(f"  SHA-256 {sha256_file(p)}")
    for line in licence_lines(p.with_name(f"{voice}.MODEL_CARD")):
        print(f"  model card: {line}")
    return 0


def list_cmd(a) -> int:
    url = f"{HUB}/resolve/main/voices.json?download=true"
    try:
        with urllib.request.urlopen(url, timeout=60) as r:
            voices = json.load(r)
    except (urllib.error.URLError, OSError) as exc:
        print(f"error: {url.split('?')[0]}: {getattr(exc, 'reason', exc)}; {HOSTS_HINT}", file=sys.stderr)
        return 2
    for name in sorted(voices):
        if not a.lang or name.startswith(a.lang):
            print(name)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fetch")
    f.add_argument("--voice")
    f.add_argument("--dest")
    f.add_argument("--force", action="store_true")
    for name in ("path", "info"):
        sub.add_parser(name).add_argument("--voice")
    sub.add_parser("list").add_argument("--lang", default="en")
    a = ap.parse_args()
    return {"fetch": fetch, "path": path_cmd, "info": info, "list": list_cmd}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
