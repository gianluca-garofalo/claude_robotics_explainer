"""The schema-2 fixture series (tests/fixtures/series/fixture-series.json) for the tests and the dry runs."""
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
import testenv  # noqa: E402
testenv.activate()                  # fixture config and sources, before any tool is imported
sys.path.insert(0, str(REPO / "tools"))

import series as S  # noqa: E402
from _common import sha256_file  # noqa: E402


def make_series(root: Path, approve: bool = True, edit=None) -> Path:
    """Write <root>/series/fixture-series/series.json, approved unless approve=False; returns its folder."""
    data = json.loads((REPO / "tests" / "fixtures" / "series" / "fixture-series.json").read_text(encoding="utf-8"))
    data["explainer_sha256"] = sha256_file(REPO / data["source"] / "explainer.html")
    if edit:
        edit(data)
    if approve:
        data["plan_approval"] = {"status": "approved", "by": "owner", "date": "2026-10-31",
                                 "via": "tests/series_fixture.py (fixture)", "plan_sha256": S.plan_hash(data)}
    d = Path(root) / "series" / data["slug"]
    d.mkdir(parents=True, exist_ok=True)
    (d / "series.json").write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return d


def scenes_beyond_helpers(run: Path) -> list[str]:
    """Files in <run>/video/scenes/ besides unchanged copies of the templates/manim helpers."""
    tpl = REPO / "templates" / "manim"
    helpers = {p.name: p.read_bytes() for p in tpl.glob("*.py") if p.name != "scene_template.py"}
    return sorted(p.name for p in (run / "video" / "scenes").glob("*.py") if helpers.get(p.name) != p.read_bytes())
