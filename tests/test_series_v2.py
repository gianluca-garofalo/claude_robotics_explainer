"""Unit tests for series plans (schema 2): validation, the owner's plan approval, start, plan sections as sources
(python3 -m unittest)."""
import copy
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
sys.path.insert(0, str(REPO / "tools" / "video"))
sys.path.insert(0, str(REPO / "tests"))

import series as S  # noqa: E402
from series_fixture import make_series  # noqa: E402


def series_cli(*args, cwd=REPO):
    return subprocess.run([sys.executable, str(REPO / "tools" / "series.py"), *args], cwd=cwd, capture_output=True,
                          text=True)


class Validate(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="series-v2-"))
        self.data = json.loads((make_series(self.tmp) / "series.json").read_text())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def errors(self, edit):
        d = copy.deepcopy(self.data)
        edit(d)
        return S.validate_v2(d)[0]

    def test_fixture_is_valid(self):
        self.assertEqual(S.validate_v2(self.data), ([], []))

    def test_rules(self):
        cases = {
            "kind must be 'finale'": lambda d: d["episodes"][1].update(kind="middle"),
            "must be an earlier episode": lambda d: d["episodes"][0]["prerequisites"].update(must=[2]),
            "has no recap": lambda d: d["episodes"][1].update(recap=[]),
            "the finale has no teaser": lambda d: d["episodes"][1].update(teaser="In the next episode, more."),
            "teaser is required": lambda d: d["episodes"][0].update(teaser=None),
            "equation label": lambda d: d["episodes"][0]["takeaway"].update(tex=[r"V_N\le 0\tag{3}"]),
            "not in the explainer": lambda d: d["episodes"][0]["material"].update(section_ids=["sec-nowhere"]),
            "does not follow": lambda d: d["episodes"][1]["prerequisites"].update(
                helpful=[{"series": "other-series", "episode": 1}]),
            "listed twice": lambda d: d["episodes"][1]["prerequisites"].update(helpful=[1]),
            "hard prerequisite": lambda d: d["episodes"][1]["series_context"].update(
                spoken="You must have watched the first episode."),
        }
        for needle, edit in cases.items():
            with self.subTest(rule=needle):
                self.assertTrue(any(needle in e for e in self.errors(edit)), self.errors(edit))

    def test_plan_hash_ignores_the_explainer_bytes(self):
        d = copy.deepcopy(self.data)
        d["explainer_sha256"] = "0" * 64
        self.assertEqual(S.plan_hash(d), S.plan_hash(self.data))
        d["episodes"][1]["teaser"] = "changed"
        self.assertNotEqual(S.plan_hash(d), S.plan_hash(self.data))


class Approval(unittest.TestCase):
    """Plan approval: required (the owner approves each plan; --require-approval asks for it whatever the setting) or
    optional (the owner's setting since 2026-11-01: an unapproved plan starts with an informational note)."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="series-approval-"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def start(self, d, *extra):
        return series_cli("start", str(d), "--episode", "2", "--root", str(self.tmp / "runs"), "--date", "2026-11-14",
                          *extra)

    def test_unapproved_plan_is_refused_when_required(self):
        r = self.start(make_series(self.tmp, approve=False), "--require-approval")
        self.assertEqual(r.returncode, 1)
        self.assertIn("not approved", r.stderr)
        self.assertIn("approve_series.py", r.stderr)

    def test_changed_after_approval_is_refused_when_required(self):
        d = make_series(self.tmp)
        data = json.loads((d / "series.json").read_text())
        data["episodes"][1]["hook"] += " Changed."
        (d / "series.json").write_text(json.dumps(data))
        r = self.start(d, "--require-approval")
        self.assertEqual(r.returncode, 1)
        self.assertIn("changed since", r.stderr)

    def test_optional_setting_starts_an_unapproved_plan_with_a_note(self):
        self.assertEqual(S.approval_setting(), "optional")                # config/pipeline.json, the owner's choice
        r = self.start(make_series(self.tmp, approve=False))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("note: plan approval is optional", r.stderr)
        self.assertNotIn("warning", r.stderr.lower())
        self.assertNotIn("approve_series.py", r.stderr)                    # no nag
        ep = json.loads((Path(r.stdout.strip()) / "episode.json").read_text())
        self.assertEqual((ep["plan_approval"]["required"], ep["plan_approval"]["approved"]), (False, False))
        st = S.approval_state(self.tmp / "series" / "fixture-series" / "series.json",
                              json.loads((self.tmp / "series" / "fixture-series" / "series.json").read_text()))
        self.assertIn("none needed", st["detail"])

    def test_a_plan_without_schema_2_is_refused(self):
        d = make_series(self.tmp, edit=lambda s: s.update(schema_version=1))
        r = self.start(d)
        self.assertEqual(r.returncode, 1)
        self.assertIn("schema_version must be 2", r.stderr)

    def test_human_tool_needs_a_terminal_and_claude_is_blocked(self):
        d = make_series(self.tmp, approve=False)
        r = subprocess.run([sys.executable, str(REPO / "tools" / "human" / "approve_series.py"), str(d)],
                           input="fixture-series\n", capture_output=True, text=True)
        self.assertEqual(r.returncode, 2)
        self.assertNotIn("plan_approval", json.loads((d / "series.json").read_text()))
        ev = {"tool_name": "Bash", "tool_input": {"command": f"python3 tools/human/approve_series.py {d}"}}
        h = subprocess.run([sys.executable, str(REPO / "tools" / "hooks" / "block_publish.py")], input=json.dumps(ev),
                           capture_output=True, text=True)
        self.assertEqual(h.returncode, 2)


class FromSourceAndNext(unittest.TestCase):
    """from-source finds the series made from a source in release order; next skips episodes whose hand-over package
    exists in the runs folder; a source without companion code gets an empty code/ for the episode's own scripts."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="series-source-"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_from_source_and_release_order(self):
        make_series(self.tmp)
        second = make_series(self.tmp, edit=lambda d: d.update(slug="fixture-second", related_series={
            "follows": ["fixture-series"], "followed_by": []}))
        self.assertEqual(second.name, "fixture-second")
        r = series_cli("from-source", "sources/variational-whole-body-control", "--root", str(self.tmp))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual([ln.split("\t")[0].rsplit("/", 1)[-1] for ln in r.stdout.splitlines()],
                         ["fixture-series", "fixture-second"])
        r = series_cli("from-source", "sources/nothing-here", "--root", str(self.tmp))
        self.assertEqual(r.returncode, 1)
        self.assertIn("/plan-series sources/nothing-here", r.stderr)

    def test_next_skips_delivered_episodes(self):
        d = make_series(self.tmp)
        runs = self.tmp / "runs"
        self.assertEqual(series_cli("next", str(d), "--root", str(runs)).stdout.strip(), "1")
        r = series_cli("start", str(d), "--episode", "next", "--root", str(runs), "--date", "2026-11-14")
        run = Path(r.stdout.strip())
        self.assertIn("ep01", run.name)
        self.assertEqual(series_cli("next", str(d), "--root", str(runs)).stdout.strip(), "1")   # started, not delivered
        (run / "deliver").mkdir()
        (run / "deliver" / "upload_sheet.md").write_text("# Upload sheet\n")
        self.assertEqual(series_cli("next", str(d), "--root", str(runs)).stdout.strip(), "2")
        r = series_cli("start", str(d), "--episode", "1", "--root", str(runs), "--date", "2026-11-15")
        self.assertEqual(r.returncode, 0, r.stderr)                          # an explicit number may be made again

    def test_a_source_without_code(self):
        src = self.tmp / "sources" / "bare"
        src.mkdir(parents=True)
        shutil.copy(REPO / "sources" / "variational-whole-body-control" / "explainer.html", src / "explainer.html")
        data = json.loads((make_series(self.tmp) / "series.json").read_text())
        errs, warns = S.validate_v2(dict(data, source="sources/bare"), repo=self.tmp)
        self.assertEqual(errs, [])
        self.assertTrue(any("no companion code" in w for w in warns), warns)


class Start(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="series-start-v2-"))
        self.d = make_series(self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_start_writes_the_series_context_and_the_brief(self):
        r = series_cli("start", str(self.d), "--episode", "2", "--root", str(self.tmp / "runs"), "--date", "2026-11-14")
        self.assertEqual(r.returncode, 0, r.stderr)
        run = Path(r.stdout.strip())
        ctx = json.loads((run / "video" / "series_context.json").read_text())
        self.assertEqual((ctx["episode"], ctx["episodes_total"], ctx["kind"]), (2, 2, "finale"))
        self.assertEqual(ctx["prerequisites"]["must"], ["1"])
        self.assertEqual(ctx["short_titles"]["1"], "Why MPC is stable")
        self.assertTrue(ctx["recaps"][0]["card"])
        self.assertIsNone(ctx["teaser"])
        ep = json.loads((run / "episode.json").read_text())
        self.assertEqual((ep["schema_version"], ep["episodes_total"], ep["plan_approval"]["approved"]), (2, 2, True))
        self.assertTrue(ep["section_ids"])
        brief = (run / "video" / "episode.md").read_text()
        for needle in ("Hook first", "builds_on()", "recap_tag()", "never \"you must have watched\"", "15-20 s"):
            self.assertIn(needle, brief)
        self.assertIn("Existing scenes: none: write them", brief)                   # a fresh start: no kept scenes
        self.assertTrue((run / "video" / "data" / "arm_A.npz").exists())             # data/ of the source

    def test_fresh_copies_no_scenes(self):
        r = series_cli("start", str(self.d), "--episode", "2", "--root", str(self.tmp / "runs"), "--date", "2026-11-14",
                       "--fresh")
        self.assertEqual(r.returncode, 0, r.stderr)
        run = Path(r.stdout.strip())
        self.assertEqual(sorted(p.name for p in (run / "video" / "scenes").glob("*.py")),
                         ["common.py", "reading_model.py", "voice.py"])
        self.assertIn("Existing scenes: none: write them", (run / "video" / "episode.md").read_text())


class Write(unittest.TestCase):
    def test_write_validates_and_keeps_an_approved_plan(self):
        tmp = Path(tempfile.mkdtemp(prefix="series-write-"))
        try:
            src = make_series(tmp / "src", approve=False) / "series.json"
            r = series_cli("write", str(src), "--root", str(tmp / "out"))
            self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
            out = tmp / "out" / "series" / "fixture-series"
            self.assertIn("Plan approval is optional", r.stdout)       # the owner's setting: no approval step
            self.assertNotIn("approve_series.py", r.stdout)
            data = json.loads((out / "series.json").read_text())
            data["plan_approval"] = {"status": "approved", "plan_sha256": S.plan_hash(data)}
            (out / "series.json").write_text(json.dumps(data))
            r2 = series_cli("write", str(src), "--root", str(tmp / "out"))
            self.assertEqual(r2.returncode, 1)
            self.assertIn("approved plan", r2.stderr)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class PlanSections(unittest.TestCase):
    def test_sections_are_sources_and_roles_are_checked(self):
        import plan as P
        tmp = Path(tempfile.mkdtemp(prefix="plan-roles-"))
        try:
            shutil.copy(REPO / "sources" / "variational-whole-body-control" / "explainer.html",
                        tmp / "explainer.html")
            (tmp / "video" / "scenes").mkdir(parents=True)
            (tmp / "video" / "scenes" / "a.py").write_text("class A(RAScene):\n    pass\nclass B(RAScene):\n    pass\n")
            (tmp / "episode.json").write_text(json.dumps({"slug": "x", "sections": ["5"]}))
            plan = {"schema_version": 1, "title": "T", "summary": "S.", "tags": [],
                    "scenes": [{"file": "a.py", "class": "A", "section": "sec-hierarchy", "chapter": "One",
                                "role": "hook"},
                               {"file": "a.py", "class": "B", "section": "sec-hj", "chapter": "Recap: two",
                                "role": "recap"}],
                    "thumbnail": {"scene": "A", "time": 1.0, "text": "T"}}
            issues = P.problems(tmp, plan)
            self.assertFalse([i for i in issues if "outside this episode" in i])         # sources, not a mapping
            self.assertTrue([i for i in issues if "recap_of" in i])
            plan["scenes"][1]["recap_of"] = 1
            plan["scenes"][0]["role"] = "intro"
            self.assertTrue([i for i in P.problems(tmp, plan) if "role 'intro'" in i])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
