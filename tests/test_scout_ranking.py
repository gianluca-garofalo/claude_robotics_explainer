"""Tests for the scout and ranking rules found in a live test: read levels, claim roles, subject sources, provisional
claims, unknown recency, run windows, coverage, network status, stale search data, hook scope (python3 -m unittest)."""
import copy
import json
import os
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

import rank_topics  # noqa: E402
import validate  # noqa: E402

FIX = REPO / "tests" / "fixtures"
PY = sys.executable


def run_tool(*args, env=None):
    return subprocess.run([PY, *args], cwd=REPO, capture_output=True, text=True, env=env)


class RunFolder(unittest.TestCase):
    """A fresh run (outside runs/) with the fixture sources and scores."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="scout-test-"))
        r = run_tool("tools/run.py", "new", *testenv.COVERAGE_ARGS, "--root", str(self.tmp), "--date", "2026-10-30")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.run_dir = Path(r.stdout.strip())
        for f in ("sources.json", "scores.json"):
            shutil.copy(FIX / "run" / f, self.run_dir / f)
        self.sources = json.loads((self.run_dir / "sources.json").read_text())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def save(self, sources):
        (self.run_dir / "sources.json").write_text(json.dumps(sources, indent=1))

    def rows(self):
        rubric = json.loads((testenv.CONFIG / "rubric.json").read_text())
        scores = json.loads((self.run_dir / "scores.json").read_text())
        rows, _ = rank_topics.compute(self.run_dir, json.loads((self.run_dir / "sources.json").read_text()), scores,
                                      rubric)
        return {r["id"]: r for r in rows}

    def errors(self):
        rep = validate.validate_file("sources", self.run_dir / "sources.json", self.run_dir)
        return rep.errors, rep.warnings


class NewRun(RunFolder):
    def test_new_run_has_ledger_and_coverage(self):
        self.assertEqual(json.loads((self.run_dir / "published.json").read_text())["runs"], {})
        items = json.loads((self.run_dir / "covered.json").read_text())["items"]
        sources = {i["source"] for i in items}
        self.assertEqual(sources, {"source document"})                    # the fixture source; no series plan
        self.assertTrue(any("Hamilton" in i["title"] for i in items))     # a section of the fixture source
        window = json.loads((testenv.CONFIG / "scout.json").read_text())["window_days"]
        self.assertEqual(json.loads((self.run_dir / "run.json").read_text())["window_days"], window)

    def test_coverage_lists_series_plans(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("ra_coverage", REPO / "tools" / "coverage.py")
        coverage = importlib.util.module_from_spec(spec)                 # not the coverage.py package
        spec.loader.exec_module(coverage)
        sys.path.insert(0, str(REPO / "tests"))
        from series_fixture import make_series
        make_series(self.tmp)
        items = coverage.build(self.run_dir, series_root=self.tmp / "series", sources_root=testenv.SOURCES)["items"]
        planned = [i for i in items if i["source"] == "series"]
        self.assertEqual(planned[0]["status"], "series")
        self.assertEqual(len(planned), 3)                                  # the series and its two episodes
        self.assertTrue(all(i["where"].endswith("series.json") for i in planned))

    def test_window_override_is_recorded(self):
        r = run_tool("tools/run.py", "new", *testenv.COVERAGE_ARGS, "--root", str(self.tmp), "--date", "2026-10-30", "--window-days", "30")
        rj = json.loads((Path(r.stdout.strip()) / "run.json").read_text())
        self.assertEqual((rj["window_days"], rj["window_source"]), (30, "--window-days"))


class Gates(RunFolder):
    def test_limitations_never_gate(self):
        row = self.rows()["T1"]
        self.assertTrue(any(c.get("role") == "limitation" and c["status"] == "unverified" for c in row["claims"]))
        self.assertTrue(row["eligible"], row["gate_reasons"])

    def test_prior_work_does_not_satisfy_the_gate(self):
        s = copy.deepcopy(self.sources)
        t2 = next(c for c in s["candidates"] if c["id"] == "T2")
        for x in t2["sources"]:
            x["relation"] = "prior_work"
        self.save(s)
        row = self.rows()["T2"]
        self.assertFalse(row["eligible"])
        self.assertIn("only prior work", "; ".join(row["gate_reasons"]))
        self.assertIsNone(row["scores"]["recency"])

    def test_provisional_claims_pass_and_are_flagged(self):
        s = copy.deepcopy(self.sources)
        t1 = s["candidates"][0]
        t1["sources"][0]["read"] = "search_abstract"
        t1["central_claims"][0]["status"] = "provisional"
        self.save(s)
        errs, _ = self.errors()
        self.assertEqual(errs, [])
        row = self.rows()["T1"]
        self.assertTrue(row["eligible"])
        self.assertEqual(row["provisional"], 1)

    def test_unknown_recency_is_renormalised_not_zero(self):
        s = copy.deepcopy(self.sources)
        for x in s["candidates"][0]["sources"]:
            if x.get("relation") == "subject":
                x["published"] = None
        self.save(s)
        row = self.rows()["T1"]
        self.assertIsNone(row["scores"]["recency"])
        self.assertIn("recency", row["unknown"])
        self.assertGreater(row["total"], 70)

    def test_covered_topic_is_excluded(self):
        s = copy.deepcopy(self.sources)
        s["candidates"][1]["coverage"] = {"status": "covered", "by": ["sources: whole-body control"]}
        self.save(s)
        row = self.rows()["T2"]
        self.assertFalse(row["eligible"])
        self.assertIn("already covered", "; ".join(row["gate_reasons"]))


class Validation(RunFolder):
    def test_read_levels_limit_claim_status(self):
        s = copy.deepcopy(self.sources)
        s["candidates"][0]["sources"][0]["read"] = "search_abstract"          # claim still says verified
        self.save(s)
        errs, _ = self.errors()
        self.assertTrue(any("'verified' but no supporting source" in e for e in errs))
        s["candidates"][0]["sources"][0]["read"] = "snippet"
        s["candidates"][0]["central_claims"][0]["status"] = "provisional"
        self.save(s)
        errs, _ = self.errors()
        self.assertTrue(any("snippet is not enough" in e for e in errs))

    def test_primary_source_needs_a_relation(self):
        s = copy.deepcopy(self.sources)
        del s["candidates"][0]["sources"][0]["relation"]
        self.save(s)
        self.assertTrue(any("relation is required" in e for e in self.errors()[0]))

    def test_window_is_enforced_from_subject_dates(self):
        s = copy.deepcopy(self.sources)
        s["candidates"][1]["sources"][0]["published"] = "2026-09-01"
        self.save(s)
        self.assertTrue(any("older than the run's 14-day window" in e for e in self.errors()[0]))

    def test_window_must_match_the_run(self):
        s = copy.deepcopy(self.sources)
        s["window_days"] = 30
        self.save(s)
        self.assertTrue(any("differs from the run's window" in e for e in self.errors()[0]))

    def test_coverage_required_with_covered_json(self):
        s = copy.deepcopy(self.sources)
        del s["candidates"][0]["coverage"]
        self.save(s)
        self.assertTrue(any("coverage must say" in e for e in self.errors()[0]))

    def test_hook_checks_runs_outside_runs_folder(self):
        bad = {"schema_version": 1}
        self.save(bad)
        event = {"tool_name": "Write", "tool_input": {"file_path": str(self.run_dir / "sources.json")},
                 "cwd": str(REPO)}
        r = subprocess.run([PY, "tools/hooks/after_edit.py"], cwd=REPO, input=json.dumps(event), text=True,
                           capture_output=True, env=dict(os.environ, CLAUDE_PROJECT_DIR=str(REPO)))
        self.assertEqual(r.returncode, 2)
        self.assertIn("$.candidates is required", r.stderr)


class Report(RunFolder):
    def test_network_status_and_real_path_in_ranking(self):
        s = copy.deepcopy(self.sources)
        s["unreadable"].append({"url": "https://arxiv.org/abs/0000.00001", "reason": "host refused",
                                "cause": "network_policy"})
        self.save(s)
        r = run_tool("tools/rank_topics.py", str(self.run_dir))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        md = (self.run_dir / "ranking.md").read_text()
        self.assertIn("## Sources unreadable from this network", md)
        self.assertIn("arxiv.org", md.split("## Sources unreadable from this network")[1][:400])
        self.assertIn(f"/approve-topic {self.run_dir}", md)
        self.assertNotIn("/approve-topic runs/", md)

    def test_stale_search_data_is_ignored(self):
        env = dict(os.environ, SEARCH_BACKEND="fake", SEARCH_FAKE_DATA=str(FIX / "search_fake.json"))
        self.assertEqual(run_tool("tools/search_demand.py", str(self.run_dir), env=env).returncode, 0)
        data = json.loads((self.run_dir / "search.json").read_text())
        self.assertTrue(data["topics"]["T1"]["trends"]["coverage"].startswith("partial"))
        self.assertTrue(data["topics"]["T2"]["youtube"]["errors"])
        s = copy.deepcopy(self.sources)
        s["candidates"][0]["summary"] += " Edited after the search."
        self.save(s)
        run_tool("tools/rank_topics.py", str(self.run_dir))
        md = (self.run_dir / "ranking.md").read_text()
        self.assertIn("Search data is stale", md)
        rk = json.loads((self.run_dir / "ranking.json").read_text())
        self.assertIn("search_demand", rk["ranking"][0]["unknown"])
        st = run_tool("tools/run.py", "status", str(self.run_dir)).stdout
        self.assertIn("search.json was collected for an earlier sources.json", st)

    def test_human_approval_of_a_ranking_with_search_data(self):
        env = dict(os.environ, SEARCH_BACKEND="fake", SEARCH_FAKE_DATA=str(FIX / "search_fake.json"))
        self.assertEqual(run_tool("tools/search_demand.py", str(self.run_dir), env=env).returncode, 0)
        self.assertEqual(run_tool("tools/rank_topics.py", str(self.run_dir)).returncode, 0)
        sys.path.insert(0, str(REPO / "tools" / "human"))
        import approve_topic
        self.assertEqual(approve_topic.record(str(self.run_dir), "T1", via="test")["topic_id"], "T1")
        (self.run_dir / "search.json").write_text("{}")
        with self.assertRaises(approve_topic.ApprovalError):
            approve_topic.record(str(self.run_dir), "T1", via="test")


if __name__ == "__main__":
    unittest.main()
