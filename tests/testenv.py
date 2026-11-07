"""Points every tool, in this process and its subprocesses, at tests/fixtures (config, sources): import it first."""
from __future__ import annotations

import copy
import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CONFIG = REPO / "tests" / "fixtures" / "config"
SOURCES = REPO / "tests" / "fixtures" / "sources"            # the fixture source documents (a "sources/" folder)
SOURCE_DIR = SOURCES / "fixture-predictive-control"
SOURCE = SOURCE_DIR.relative_to(REPO).as_posix()              # as a series plan names it ("source")
NO_SERIES = REPO / "tests" / "fixtures" / "no-series"         # a series folder that holds no plan (does not exist)
COVERAGE_ARGS = ("--sources", str(SOURCES), "--series", str(NO_SERIES))   # for tools/run.py new and coverage.py


def environ(config: Path = CONFIG) -> dict:
    """The variables that point the tools at a configuration folder."""
    return {"RA_CONFIG_DIR": str(config), "VIDEO_CONFIG": str(config / "video.json"),
            "CHANNEL_CONFIG": str(config / "channel.json")}


def variant(folder: Path, edits: dict) -> Path:
    """folder/config: the fixture configuration with edits merged in, e.g. {"pipeline": {"series": {...}}}."""
    out = Path(folder) / "config"
    out.mkdir(parents=True, exist_ok=True)

    def merge(a: dict, b: dict) -> dict:
        r = copy.deepcopy(a)
        for k, v in b.items():
            r[k] = merge(r[k], v) if isinstance(v, dict) and isinstance(r.get(k), dict) else v
        return r
    for p in CONFIG.glob("*.json"):
        data = json.loads(p.read_text(encoding="utf-8"))
        (out / p.name).write_text(json.dumps(merge(data, edits.get(p.stem, {})), indent=2), encoding="utf-8")
    return out


def env(config: Path = CONFIG, **extra) -> dict:
    """os.environ with the tools pointed at a configuration folder (for subprocess.run(env=...))."""
    return dict(os.environ, **environ(config), **extra)


# a developer's or a cloud session's own keys and choices must not change what the tests see
MACHINE_ENV = ("VOICE_SERVICE", "AZURE_SUBSCRIPTION_KEY", "AZURE_SERVICE_REGION", "ANTHROPIC_API_KEY",
               "CLAUDE_CODE_OAUTH_TOKEN", "YOUTUBE_API_KEY", "YOUTUBE_CLIENT_ID", "YOUTUBE_CLIENT_SECRET",
               "YOUTUBE_REFRESH_TOKEN", "LINKEDIN_ACCESS_TOKEN", "LINKEDIN_AUTHOR_URN")


def activate() -> None:
    """Idempotent; tool modules imported earlier are pointed at the fixtures as well."""
    for k in MACHINE_ENV:               # credentials and choices of this machine never reach a test
        os.environ.pop(k, None)
    os.environ.update(environ())
    for m in list(sys.modules.values()):
        if getattr(m, "CONFIG", None) == REPO / "config":
            m.CONFIG = CONFIG
