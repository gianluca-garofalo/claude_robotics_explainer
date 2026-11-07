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
sys.path.insert(0, str(Path(__file__).resolve().parent))
import testenv  # noqa: E402
testenv.activate()                  # fixture config and sources, before any tool is imported
sys.path.insert(0, str(REPO / "tools"))
sys.path.insert(0, str(REPO / "tools" / "video"))
sys.path.insert(0, str(REPO / "tests"))

import series as S  # noqa: E402
from series_fixture import make_series  # noqa: E402


def series_cli(*args, cwd=REPO, env=None):
    return subprocess.run([sys.executable, str(REPO / "tools" / "series.py"), *args], cwd=cwd, capture_output=True,
                          text=True, env=env)


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

    def test_idea_rules(self):
        cases = {
            "ideas is required": lambda d: d["episodes"][0].pop("ideas"),
            "a later episode": lambda d: d["episodes"][0]["ideas"][0].update(uses=["hj-certificate"]),
            "no episode declares": lambda d: d["episodes"][0]["ideas"][0].update(uses=["nowhere"]),
            "only a concept": lambda d: d["episodes"][0]["ideas"][5].update(pretraining=True),
            "unique in the series": lambda d: d["episodes"][1]["ideas"].append(
                {"id": "descent", "kind": "claim", "text": "again"}),
            "never lower it": lambda d: d["episodes"][0]["ideas"][5].update(seconds=30),
            "kind must be": lambda d: d["episodes"][0]["ideas"][5].update(kind="theorem"),
        }
        for needle, edit in cases.items():
            with self.subTest(rule=needle):
                self.assertTrue(any(needle in e for e in self.errors(edit)), self.errors(edit))

    def test_story_order_chains_and_outline(self):
        def chain(d):
            d["episodes"][0]["ideas"].append({"id": "chained", "kind": "claim", "follows": "feasible", "text": "x"})
        self.assertTrue(any("a chain is a derivation" in e for e in self.errors(chain)))

        def three(d):
            d["episodes"][0]["ideas"].append({"id": "third", "kind": "claim", "follows": "descent", "text": "x"})
        self.assertTrue(any("3 consequences follow 'descent'" in e for e in self.errors(three)))

        def circle(d):
            d["episodes"][0]["ideas"][1]["uses"] = ["remaining-action"]           # remaining-action uses it too
        self.assertTrue(any("in a circle" in e for e in self.errors(circle)))
        d = copy.deepcopy(self.data)
        d["episodes"][0]["ideas"][5]["uses"].append("exact-step")              # declared after the descent
        self.assertTrue(any("declared later" in w for w in S.validate_v2(d)[1]))
        d = copy.deepcopy(self.data)
        d["episodes"][0]["outline"] = d["episodes"][0]["outline"][:3]          # beats that squeeze the ideas
        self.assertTrue(any("squeezes" in w for w in S.validate_v2(d)[1]))
        d["episodes"][0]["outline"].append({"beat": "more", "min": 9.0})
        self.assertTrue(any("plans more" in w for w in S.validate_v2(d)[1]))

    def test_recap_ideas_come_from_its_episodes(self):
        def ok(d):
            d["episodes"][1]["recap"][0]["ideas"] = ["descent", "certificate-pair"]
        self.assertEqual(self.errors(ok), [])

        def stale(d):
            d["episodes"][1]["recap"][0]["ideas"] = ["descent", "only-one-push"]
        self.assertTrue(any("only-one-push" in e and "do not teach" in e for e in self.errors(stale)))

    def test_an_overpacked_episode_fails_and_says_what_to_move_where(self):
        def third_star(d):
            d["episodes"][0]["ideas"] += [
                {"id": "recursion", "kind": "star", "uses": ["remaining-action"], "text": "the recursion"},
                {"id": "monotone", "kind": "claim", "uses": ["recursion"], "text": "longer windows never cost more"}]
            d["episodes"][1]["ideas"][7]["uses"].append("recursion")          # the next episode builds on it
        errs = self.errors(third_star)
        over = [e for e in errs if "episode 1" in e and "over-packed" in e]
        self.assertEqual(len(over), 1, errs)
        moved = over[0].split("to episode 2,")[1].split("(then")[0]
        self.assertIn("recursion", moved)
        self.assertIn("monotone", moved)                                     # what builds on it moves with it
        self.assertNotIn("descent", moved)

        def many_claims(d):
            d["episodes"][0]["ideas"] += [{"id": f"aside-{k}", "kind": "claim", "uses": ["descent"],
                                           "text": f"aside {k}"} for k in range(5)]
        over = [e for e in self.errors(many_claims) if "over-packed" in e]
        self.assertTrue(over and "aside-4" in over[0], over)
        d = copy.deepcopy(self.data)
        many_claims(d)
        sug = S.IB.suggest_moves(d["episodes"], 1, S.IB.settings())
        self.assertEqual(sug["to"], 2)
        self.assertTrue(sug["fits"])
        self.assertFalse(S.IB.overpacked([i for i in d["episodes"][0]["ideas"] if i["id"] not in sug["move"]],
                                         S.IB.settings()))

    def test_an_overpacked_episode_may_leave_material_to_the_explainer(self):
        d = copy.deepcopy(self.data)
        d["episodes"][0]["ideas"] += [{"id": f"aside-{k}", "kind": "claim", "uses": ["descent"], "text": f"aside {k}"}
                                      for k in range(3)]
        d["episodes"][1]["ideas"][0]["uses"] = ["aside-0"]                     # a later episode builds on this one
        cfg = S.IB.settings()
        cut = S.IB.suggest_cut(d["episodes"], 1, cfg)
        self.assertTrue(cut["fits"])
        ep1 = {i["id"]: i for i in d["episodes"][0]["ideas"]}
        for x in cut["cut"]:
            self.assertNotEqual(ep1[x]["kind"], "star")
            self.assertFalse(ep1[x].get("example"))
        self.assertNotIn("aside-0", cut["cut"])
        self.assertNotIn("remaining-action", cut["cut"])                        # the hilltop builds on it
        over = [e for e in S.validate_v2(d)[0] if "over-packed" in e]
        self.assertTrue(over and "leave to the explainer" in over[0], over)
        self.assertTrue(any(ep1[x]["kind"] == "claim" and not ep1[x].get("follows") for x in cut["cut"]))

    def test_a_lone_consequence_is_not_the_cut_when_a_claim_group_exists(self):
        d = copy.deepcopy(self.data)
        ep = d["episodes"][0]
        ep["ideas"] += [{"id": "aside", "kind": "claim", "uses": ["descent"], "text": "a claim of its own"},
                        {"id": "so-what", "kind": "claim", "follows": "aside", "text": "its consequence"},
                        {"id": "lone", "kind": "claim", "follows": "certificate-pair", "text": "a consequence"}]
        ep["ideas"][0]["seconds"] = 60                                          # just over the cap
        cfg = S.IB.settings()
        self.assertTrue(S.IB.overpacked(ep["ideas"], cfg))
        cut = S.IB.suggest_cut(d["episodes"], 1, cfg)
        ideas = {i["id"]: i for i in ep["ideas"]}
        self.assertNotIn("lone", cut["cut"])                                    # a cheap "so what" is not the cut
        self.assertTrue(any(ideas[x]["kind"] == "claim" and not ideas[x].get("follows") for x in cut["cut"]))

    def test_length_follows_from_the_ideas(self):
        d = copy.deepcopy(self.data)
        d["episodes"][0]["length_min"] = 7
        self.assertTrue(any("length_min 7" in w for w in S.validate_v2(d)[1]))
        cfg = S.IB.settings()
        fewer = S.IB.estimate(d["episodes"][0]["ideas"][:6], cfg)
        more = S.IB.estimate(d["episodes"][0]["ideas"], cfg)
        self.assertLess(fewer["hi_s"], more["lo_s"])                         # every idea costs time

    def test_a_slow_reading_of_the_derivations_cannot_slip_past_the_cap(self):
        cfg = S.IB.settings()
        f = 1 + cfg["slow_extra"]
        self.assertAlmostEqual(S.IB.idea_seconds({"id": "a", "kind": "star", "text": "x"}, cfg)[0], 75 * f)
        self.assertAlmostEqual(S.IB.idea_seconds({"id": "b", "kind": "claim", "follows": "a", "text": "y"}, cfg)[0],
                               10 * f)                                        # argued in a slow block
        self.assertEqual(S.IB.idea_seconds({"id": "c", "kind": "concept", "text": "z"}, cfg), (35.0, 35.0))  # base rate
        self.assertFalse([e for e in self.errors(lambda d: d["episodes"][0]["ideas"][5].update(seconds=80))
                          if "never lower" in e])                            # seconds are written at the ordinary pace
        ideas = copy.deepcopy(self.data["episodes"][0]["ideas"])
        ideas.append({"id": "one-more", "kind": "claim", "uses": ["descent"], "text": "one more result"})
        self.assertFalse(S.IB.overpacked(ideas, dict(cfg, slow_extra=0.0)))   # it would fit at the ordinary pace
        self.assertTrue(S.IB.overpacked(ideas, cfg))                          # but not read as the house reads it

    def test_validate_cli_prints_the_budget_and_fails_an_overpacked_plan(self):
        r = series_cli("validate", str(make_series(self.tmp / "ok", approve=False)))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("budget", r.stdout)

        def over(d):
            d["episodes"][0]["ideas"].append({"id": "recursion", "kind": "star", "text": "the recursion"})
        r = series_cli("validate", str(make_series(self.tmp / "over", approve=False, edit=over)))
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("recursion", r.stdout)

    def test_plan_hash_ignores_the_explainer_bytes(self):
        d = copy.deepcopy(self.data)
        d["explainer_sha256"] = "0" * 64
        self.assertEqual(S.plan_hash(d), S.plan_hash(self.data))
        d["episodes"][1]["teaser"] = "changed"
        self.assertNotEqual(S.plan_hash(d), S.plan_hash(self.data))


class Approval(unittest.TestCase):
    """Plan approval, under both settings of config/pipeline.json series.plan_approval (each test names the setting
    it runs with, in a variant of the fixture configuration): "required" refuses an unapproved or changed plan,
    "optional" starts it with an informational note; --require-approval asks for the approval whatever the setting."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="series-approval-"))
        self.env = {name: testenv.env(testenv.variant(self.tmp / name, {"pipeline": {"series": {"plan_approval": name}}}))
                    for name in ("optional", "required")}

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def start(self, d, *extra, setting="optional"):
        return series_cli("start", str(d), "--episode", "2", "--root", str(self.tmp / "runs"), "--date", "2026-11-14",
                          *extra, env=self.env[setting])

    def test_unapproved_plan_is_refused_when_required(self):
        d = make_series(self.tmp, approve=False)
        for setting, extra in (("required", ()), ("optional", ("--require-approval",))):
            with self.subTest(setting=setting, extra=extra):
                r = self.start(d, *extra, setting=setting)
                self.assertEqual(r.returncode, 1)
                self.assertIn("not approved", r.stderr)
                self.assertIn("approve_series.py", r.stderr)

    def test_changed_after_approval_is_refused_when_required(self):
        d = make_series(self.tmp)
        data = json.loads((d / "series.json").read_text())
        data["episodes"][1]["hook"] += " Changed."
        (d / "series.json").write_text(json.dumps(data))
        r = self.start(d, setting="required")
        self.assertEqual(r.returncode, 1)
        self.assertIn("changed since", r.stderr)

    def test_optional_setting_starts_an_unapproved_plan_with_a_note(self):
        r = self.start(make_series(self.tmp, approve=False), setting="optional")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("note: plan approval is optional", r.stderr)
        self.assertNotIn("warning", r.stderr.lower())
        self.assertNotIn("approve_series.py", r.stderr)                    # no nag
        ep = json.loads((Path(r.stdout.strip()) / "episode.json").read_text())
        self.assertEqual((ep["plan_approval"]["required"], ep["plan_approval"]["approved"]), (False, False))

    def test_approval_state_under_both_settings(self):
        sp = make_series(self.tmp, approve=False) / "series.json"
        data = json.loads(sp.read_text())
        saved = S.approval_setting
        try:
            for setting in ("optional", "required"):
                S.approval_setting = lambda setting=setting: setting
                st = S.approval_state(sp, data)
                self.assertEqual((st["required"], st["approved"]), (setting == "required", False))
                self.assertIn("none needed" if setting == "optional" else "approve_series.py", st["detail"])
                self.assertTrue(S.approval_state(sp, data, require=True)["required"])     # never the other way round
        finally:
            S.approval_setting = saved

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
        r = series_cli("from-source", testenv.SOURCE, "--root", str(self.tmp))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual([ln.split("\t")[0].rsplit("/", 1)[-1] for ln in r.stdout.splitlines()],
                         ["fixture-series", "fixture-second"])
        r = series_cli("from-source", "tests/fixtures/nothing-here", "--root", str(self.tmp))
        self.assertEqual(r.returncode, 1)
        self.assertIn("/plan-series tests/fixtures/nothing-here", r.stderr)

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
        src = self.tmp / "bare"
        src.mkdir(parents=True)
        shutil.copy(testenv.SOURCE_DIR / "explainer.html", src / "explainer.html")
        data = json.loads((make_series(self.tmp) / "series.json").read_text())
        errs, warns = S.validate_v2(dict(data, source="bare"), repo=self.tmp)
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
        plan_ep = json.loads((self.d / "series.json").read_text())["episodes"][1]
        brief = (run / "video" / "episode.md").read_text()
        for value in (plan_ep["title"], plan_ep["hook"], plan_ep["recap"][0]["title"]):   # the brief is the plan's
            self.assertIn(value, brief)
        for idea in plan_ep["ideas"]:                                  # and so is the idea budget
            self.assertIn(idea["id"], brief)
        self.assertEqual([i["id"] for i in ep["ideas"]], [i["id"] for i in plan_ep["ideas"]])
        self.assertTrue((run / "video" / "data" / "hilltop_samples.csv").exists())   # data/ of the source


class Write(unittest.TestCase):
    def test_write_validates_and_keeps_an_approved_plan(self):
        tmp = Path(tempfile.mkdtemp(prefix="series-write-"))
        try:
            src = make_series(tmp / "src", approve=False) / "series.json"
            required = testenv.env(testenv.variant(tmp / "required", {"pipeline": {"series": {"plan_approval":
                                                                                            "required"}}}))
            r = series_cli("write", str(src), "--root", str(tmp / "req"), env=required)
            self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
            self.assertIn("approve_series.py", r.stdout)                 # required: the owner's step is named
            optional = testenv.env(testenv.variant(tmp / "optional", {"pipeline": {"series": {"plan_approval":
                                                                                            "optional"}}}))
            r = series_cli("write", str(src), "--root", str(tmp / "out"), env=optional)
            self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
            out = tmp / "out" / "series" / "fixture-series"
            self.assertIn("Plan approval is optional", r.stdout)       # optional: no approval step
            self.assertNotIn("approve_series.py", r.stdout)
            data = json.loads((out / "series.json").read_text())
            data["plan_approval"] = {"status": "approved", "plan_sha256": S.plan_hash(data)}
            (out / "series.json").write_text(json.dumps(data))
            r2 = series_cli("write", str(src), "--root", str(tmp / "out"), env=optional)
            self.assertEqual(r2.returncode, 1)
            self.assertIn("approved plan", r2.stderr)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class PlanSections(unittest.TestCase):
    def test_sections_are_sources_and_roles_are_checked(self):
        import plan as P
        tmp = Path(tempfile.mkdtemp(prefix="plan-roles-"))
        try:
            shutil.copy(testenv.SOURCE_DIR / "explainer.html", tmp / "explainer.html")
            (tmp / "video" / "scenes").mkdir(parents=True)
            (tmp / "video" / "scenes" / "a.py").write_text("class A(RAScene):\n    pass\nclass B(RAScene):\n    pass\n")
            (tmp / "episode.json").write_text(json.dumps({"slug": "x", "sections": ["5"]}))
            plan = {"schema_version": 1, "title": "T", "summary": "S.", "tags": [],
                    "scenes": [{"file": "a.py", "class": "A", "section": "sec-speedlimit", "chapter": "One",
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
