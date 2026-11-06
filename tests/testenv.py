"""The test environment: every test and dry run imports this module first.

The tests never depend on what the owner may change: the preferences in config/, the source documents in sources/,
the series plans in series/ and the wording of the documents. activate() points every tool, in this process and in
the subprocesses it starts, at tests/fixtures/config, a frozen copy of the preferences the tests were written for
($RA_CONFIG_DIR for tools/, $VIDEO_CONFIG and $CHANNEL_CONFIG for the scene helpers). Source documents come from
tests/fixtures/sources (SOURCE below); tests/test_sources_smoke.py is the only test that reads sources/.
"""
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
    """A copy of the fixture configuration in folder/config with edits merged in ({"pipeline": {"series":
    {"plan_approval": "required"}}}); returns the folder to pass as $RA_CONFIG_DIR (see env())."""
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


# Credentials and per-machine choices the tools read from the environment. A test that needs one sets it itself;
# otherwise a developer's or a cloud session's own keys would change what the tests see.
MACHINE_ENV = ("VOICE_SERVICE", "AZURE_SUBSCRIPTION_KEY", "AZURE_SERVICE_REGION", "ANTHROPIC_API_KEY",
               "CLAUDE_CODE_OAUTH_TOKEN", "YOUTUBE_API_KEY", "YOUTUBE_CLIENT_ID", "YOUTUBE_CLIENT_SECRET",
               "YOUTUBE_REFRESH_TOKEN", "LINKEDIN_ACCESS_TOKEN", "LINKEDIN_AUTHOR_URN")


def activate() -> None:
    """Point this process and its subprocesses at the fixtures (idempotent). Called first in every test module and
    dry run, before any tool is imported; tool modules imported earlier are pointed at the fixture as well."""
    for k in MACHINE_ENV:               # credentials and choices of this machine never reach a test
        os.environ.pop(k, None)
    os.environ.update(environ())
    for m in list(sys.modules.values()):
        if getattr(m, "CONFIG", None) == REPO / "config":
            m.CONFIG = CONFIG
