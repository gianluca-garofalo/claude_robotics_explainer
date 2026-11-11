"""The channel's ledger: runs/ledger/*.json merged with a Pages ledger, and what reads it (run.py new, coverage,
auto_select, series.py list, next and start, validate)."""
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
import testenv  # noqa: E402
testenv.activate()                  # fixture config and sources, before any tool is imported
sys.path.insert(0, str(REPO / "tools"))
sys.path.insert(0, str(REPO / "tests"))

import series as S  # noqa: E402
from _common import read_ledger  # noqa: E402
from series_fixture import make_series  # noqa: E402

FIX = REPO / "tests" / "fixtures" / "run"
PY = sys.executable


def tool(*args, env=None):
    return subprocess.run([PY, *args], cwd=REPO, capture_output=True, text=True, env=env)


class Ledger(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="ledger-"))
        self.runs = self.tmp / "runs"
        (self.runs / "ledger").mkdir(parents=True)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def write(self, run: str, **fields) -> None:
        """runs/ledger/<run>.json as tools/deliver.py writes it, with these fields."""
        entry = {"schema_version": 1, "run": run, "status": "delivered", "delivered_at": "2026-11-07T19:30:00+00:00",
                 "run_date": run[:10], "title": "A video", "slug": "a-video", "primary_urls": [], **fields}
        (self.runs / "ledger" / f"{run}.json").write_text(json.dumps(entry))

    def test_merged_with_a_pages_ledger(self):
        self.write("2026-11-07-a", slug="a", series="fixture-series", episode=1)
        self.write("2026-11-08-b", slug="b")
        pages = self.tmp / "ledger.json"
        pages.write_text(json.dumps({"schema_version": 1, "series": {"fixture-series": {"playlist_id": "PL1"}},
                                     "runs": {"2026-11-07-a": {"status": "published", "video_id": "v1"},
                                              "2026-11-09-c": {"status": "staged", "slug": "c"}}}))
        runs = read_ledger(pages, self.runs)["runs"]
        self.assertEqual(sorted(runs), ["2026-11-07-a", "2026-11-08-b", "2026-11-09-c"])
        self.assertEqual((runs["2026-11-07-a"]["status"], runs["2026-11-07-a"]["episode"]), ("published", 1))
        self.assertEqual(runs["2026-11-08-b"]["status"], "delivered")
        self.assertEqual(read_ledger(pages, self.runs)["series"]["fixture-series"]["playlist_id"], "PL1")
        self.assertEqual(read_ledger(runs=self.tmp / "elsewhere")["runs"], {})

    def test_a_new_run_knows_a_delivered_topic_and_does_not_select_it(self):
        self.write("2026-11-07-fixture-descent-certificate", slug="fixture-descent-certificate", topic_id="T1",
                   primary_urls=["https://example.org/fixture/paper-a"])
        cfg = testenv.variant(self.tmp, {})
        pipeline = json.loads((cfg / "pipeline.json").read_text())
        del pipeline["auto_selection"]["skip_ledger_statuses"]                # the tool's default applies
        (cfg / "pipeline.json").write_text(json.dumps(pipeline))
        env = testenv.env(cfg)
        r = tool("tools/run.py", "new", *testenv.COVERAGE_ARGS, "--root", str(self.runs), "--date", "2026-11-11",
                 env=env)
        self.assertEqual(r.returncode, 0, r.stderr)
        run = Path(r.stdout.strip())
        published = json.loads((run / "published.json").read_text())["runs"]
        self.assertEqual(published["2026-11-07-fixture-descent-certificate"]["status"], "delivered")
        covered = json.loads((run / "covered.json").read_text())["items"]
        self.assertTrue([i for i in covered if i["source"] == "ledger" and i["status"] == "delivered"])
        for f in ("sources.json", "scores.json"):
            shutil.copy(FIX / f, run / f)
        self.assertEqual(tool("tools/rank_topics.py", str(run), env=env).returncode, 0)
        r = tool("tools/auto_select.py", str(run), env=env)
        self.assertEqual(r.returncode, 0, r.stderr)
        selection = json.loads((run / "selection.json").read_text())
        self.assertEqual(selection["topic_id"], "T2")                      # T1 ranks first but was delivered
        self.assertTrue(any("already delivered" in why for s in selection["skipped"] for why in s["reasons"]))

    def test_series_list_next_and_start_count_delivered_episodes(self):
        d = make_series(self.tmp)
        self.write("2026-11-07-fixture-series-ep01-x", slug="fixture-series-ep01-x", topic_id="EP01",
                   series="fixture-series", episode=1)
        root = ("--root", str(self.runs))
        self.assertEqual(tool("tools/series.py", "next", str(d), *root).stdout.strip(), "2")
        listing = tool("tools/series.py", "list", str(d), *root).stdout.splitlines()
        self.assertIn("[delivered]", next(ln for ln in listing if ln.strip().startswith("1.")))
        r = tool("tools/series.py", "start", str(d), "--episode", "next", *root, "--date", "2026-11-11")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads((Path(r.stdout.strip()) / "episode.json").read_text())["episode"], 2)
        pages = self.tmp / "ledger.json"
        pages.write_text(json.dumps({"schema_version": 1, "runs": {"2026-11-12-ep02": {
            "status": "published", "series": "fixture-series", "episode": 2, "video_id": "v2"}}}))
        self.assertEqual(tool("tools/series.py", "next", str(d), *root, "--ledger", str(pages)).returncode, 1)
        r = tool("tools/series.py", "start", str(d), "--episode", "2", *root, "--ledger", str(pages), "--date",
                 "2026-11-13")
        self.assertEqual(r.returncode, 1)                                   # published: never made twice
        r = tool("tools/series.py", "start", str(d), "--episode", "1", *root, "--date", "2026-11-13")
        self.assertEqual(r.returncode, 0, r.stderr)                         # delivered: an explicit number may remake it

    def test_an_episode_has_its_most_advanced_status(self):
        led = {"runs": {"a": {"series": "s", "episode": 1, "status": "delivered"},
                        "b": {"series": "s", "episode": 1, "status": "rejected"},
                        "c": {"series": "s", "episode": 2, "status": "published"},
                        "d": {"series": "s", "episode": 2, "status": "delivered"},
                        "e": {"series": "s", "episode": 3, "status": "rejected"}}}
        self.assertEqual(S.episode_status({"slug": "s"}, led, self.runs), {1: "delivered", 2: "published",
                                                                           3: "rejected"})

    def test_validate_checks_every_entry(self):
        self.write("2026-11-07-a")
        self.assertEqual(tool("tools/validate.py", str(self.runs / "ledger")).returncode, 0)
        self.write("2026-11-08-b", status="uploaded")
        r = tool("tools/validate.py", str(self.runs / "ledger"))
        self.assertEqual(r.returncode, 1)
        self.assertEqual([ln for ln in r.stdout.splitlines() if "FAIL" in ln and "2026-11-08-b" in ln][:1],
                         [ln for ln in r.stdout.splitlines() if "FAIL" in ln])           # only the bad entry fails


if __name__ == "__main__":
    unittest.main()
