"""A schema-2 series for the tests and the dry runs: tests/fixtures/series/fixture-series.json (two episodes adapted
from the curator's plan), with the source explainer's current hash and, unless approve=False, the owner's approval (in series.json)."""
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

import series as S  # noqa: E402
from _common import sha256_file  # noqa: E402


def make_series(root: Path, approve: bool = True, edit=None) -> Path:
    """Write <root>/series/fixture-series/series.json (and plan_approval.json); returns the series folder."""
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
