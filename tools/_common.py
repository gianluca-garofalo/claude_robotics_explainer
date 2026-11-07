"""Small helpers shared by the project's tools (standard library only)."""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
_VENV_PY = REPO / ".venv" / "bin" / "python"
if (sys.prefix == sys.base_prefix and _VENV_PY.exists() and not os.environ.get("RA_NO_VENV")
        and Path(sys.argv[0]).resolve().is_relative_to(REPO / "tools")):   # python3 tools/x.py -> the .venv
    os.execv(_VENV_PY, [str(_VENV_PY), *sys.argv])
RUNS = REPO / "runs"
# $RA_CONFIG_DIR points the tools at the tests' frozen copy of config/ (tests/testenv.py).
CONFIG = Path(os.environ["RA_CONFIG_DIR"]).resolve() if os.environ.get("RA_CONFIG_DIR") else REPO / "config"
TEMPLATES = REPO / "templates"

SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_REQUIRED = object()


def die(msg: str, code: int = 1) -> None:
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(code)


def load_json(path: Path):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        die(f"missing file: {rel(path)}")
    except json.JSONDecodeError as exc:
        die(f"{rel(path)} is not valid JSON: {exc}")


def read_json(path: Path | str, default=_REQUIRED):
    """Like load_json, but raises instead of exiting, and returns `default` (when given) for a missing file."""
    path = Path(path)
    if default is not _REQUIRED and not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
        fh.write("\n")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def md_cell(text, bar: str = "\\|") -> str:
    """A Markdown table cell: one line, "|" escaped (or replaced by `bar`)."""
    return str(text).replace("|", bar).replace("\n", " ").strip()


def rel(path: Path | str) -> str:
    """The path relative to the repository when it is inside it (reports never print absolute paths)."""
    p = Path(path).resolve()
    try:
        return str(p.relative_to(REPO))
    except ValueError:
        return str(path)


def resolve_run(arg: str) -> Path:
    """Accept 'runs/<name>', '<name>' or a path; return the run directory (must exist)."""
    candidates = [Path(arg), REPO / arg, RUNS / arg]
    project_dir = os.environ.get("CLAUDE_PROJECT_DIR")
    if project_dir:
        candidates.insert(0, Path(project_dir) / arg)
    for c in candidates:
        if c.is_dir():
            return c.resolve()
    die(f"run directory not found: {arg}")
    raise SystemExit  # for type checkers


def parse_date(s: str) -> _dt.date:
    if not isinstance(s, str) or not DATE_RE.match(s):
        raise ValueError(f"not an ISO date (YYYY-MM-DD): {s!r}")
    return _dt.date.fromisoformat(s)


def today_local() -> str:
    """Run dates use the user's local calendar date, not UTC."""
    return _dt.date.today().isoformat()


def utc_now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat()


def ranking_inputs(run: Path) -> dict:
    """Content hashes of the files a ranking is computed from."""
    out = {n: sha256_file(run / n) for n in ("sources.json", "scores.json")}
    if (run / "search.json").exists():
        out["search.json"] = sha256_file(run / "search.json")
    out["config/rubric.json"] = sha256_file(CONFIG / "rubric.json")
    return out
