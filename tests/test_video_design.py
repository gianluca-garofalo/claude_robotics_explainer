"""Unit tests for the video design and reading-time checks, search demand and series mode (python3 -m unittest)."""
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
sys.path.insert(0, str(REPO / "tools" / "video"))
sys.path.insert(0, str(REPO / "templates" / "manim"))

import check_design as CD  # noqa: E402
import check_reading as CR  # noqa: E402
import reading_model as RM  # noqa: E402
import search_demand as SD  # noqa: E402
import series as S  # noqa: E402

FIX = REPO / "tests" / "fixtures"
SOURCE = testenv.SOURCE_DIR                    # the fixture source document, never the owner's


def sha256(path: Path) -> str:
    from _common import sha256_file
    return sha256_file(path)


def design_findings(layout: Path) -> list[dict]:
    d, palette = CD.load_config()
    log_all = json.loads(layout.read_text(encoding="utf-8"))
    rep = CD.Report()
    for name, log in log_all["scenes"].items():
        CD.scene_checks(name, log, log_all["frame"], d, palette, rep)
    return rep.items


class Colour(unittest.TestCase):
    def test_wcag_contrast(self):
        self.assertAlmostEqual(CD.contrast(CD.hex_rgb("#000000"), CD.hex_rgb("#ffffff")), 21.0, places=6)
        self.assertAlmostEqual(CD.contrast(CD.hex_rgb("#777777"), CD.hex_rgb("#ffffff")), 4.48, places=2)

    def test_greys_keep_their_difference_under_every_simulation(self):
        dist, _ = CD.cvd_distance("#606060", "#a0a0a0")
        self.assertAlmostEqual(dist, CD.Color("#606060").delta_e("#a0a0a0", method="2000", space="lab-d65"), places=2)

    def test_former_green_red_collapse_for_deuteranopes(self):
        dist, kind = CD.cvd_distance("#22c55e", "#f87171")
        self.assertLess(dist, 5)
        self.assertEqual(kind, "deuteranopia")

    def test_house_palette_stays_distinguishable(self):
        palette = json.loads((testenv.CONFIG / "video.json").read_text())["palette"]["semantic"]
        cols = sorted(palette)
        for i, a in enumerate(cols):
            for b in cols[i + 1:]:
                with self.subTest(a=a, b=b):
                    self.assertGreaterEqual(CD.cvd_distance(a, b)[0], 12)

    def test_semantic_colours_readable_on_background(self):
        """Every semantic colour of the palette keeps 4.5:1 against palette.background."""
        pal = json.loads((testenv.CONFIG / "video.json").read_text())["palette"]
        bg = CD.hex_rgb(pal["background"])
        for c in pal["semantic"]:
            with self.subTest(colour=c):
                self.assertGreaterEqual(CD.contrast(CD.hex_rgb(c), bg), 4.5)


class Geometry(unittest.TestCase):
    def test_segment_inside_box(self):
        self.assertAlmostEqual(CD.clip_len((-1, 0.5), (2, 0.5), [0, 0, 1, 1]), 1.0)
        self.assertEqual(CD.clip_len((-1, 2), (2, 2), [0, 0, 1, 1]), 0.0)


class KnownOverlaps(unittest.TestCase):
    """The proof-of-concept renders have a label on a curve (Hilltop) and a header on an inequality (ArmWindow)."""

    def test_hilltop_label_on_the_hill(self):
        f = design_findings(FIX / "design" / "hilltop.layout.json")
        hits = [x for x in f if x["check"] == "overlap" and "U(q)" in x["detail"] and x["severity"] == "error"]
        self.assertEqual(len(hits), 1, f)
        self.assertIn("strong stroke", hits[0]["detail"])

    def test_arm_window_header_on_the_inequality(self):
        f = design_findings(FIX / "design" / "arm_window.layout.json")
        hits = [x for x in f if x["check"] == "overlap" and x["severity"] == "error"]
        self.assertEqual(len(hits), 1, hits)
        self.assertIn(r"|\tau_2|/30", hits[0]["detail"])
        self.assertIn("V_N(z_{k+1})", hits[0]["detail"])

    def test_arm_window_series_copy_has_no_overlap(self):
        # the same moment rendered after the inequality was moved (arm_window_fixed.layout.json)
        f = design_findings(FIX / "design" / "arm_window_fixed.layout.json")
        self.assertEqual([x for x in f if x["check"] == "overlap" and x["severity"] == "error"], [])

    def test_no_other_overlap_errors_in_hilltop(self):
        f = design_findings(FIX / "design" / "hilltop.layout.json")
        self.assertEqual(sum(x["check"] == "overlap" and x["severity"] == "error" for x in f), 1)

    def test_old_palette_flagged_and_safe_area(self):
        f = design_findings(FIX / "design" / "arm_window.layout.json")
        self.assertTrue(any(x["check"] == "safe-area" and "Two-link arm" in x["detail"] and x["severity"] == "error"
                            for x in f))
        self.assertTrue(any(x["check"] == "palette" and x["severity"] == "error" for x in f))


class Reading(unittest.TestCase):
    def setUp(self):
        self.cfg = RM.load(REPO)

    def test_words_and_terms(self):
        self.assertEqual(RM.words("H > 0: rolls over the top"), 6)
        self.assertEqual(RM.equation_terms(r"V_N(z_{k+1})-V_N(z_k)+h\,\ell(z_k,u_k)\le 0")[0], 4)
        self.assertEqual(RM.equation_terms(r"\text{sum} = V(q_0)=1.28"), (3.0, 1))

    def test_required_seconds(self):
        self.assertAlmostEqual(RM.required_seconds("text", "one two three four five", False, self.cfg), 2.1)
        self.assertAlmostEqual(RM.required_seconds("math", "q", False, self.cfg), 1.0)
        eq = r"V_N(z_{k+1})-V_N(z_k)+h\,\ell(z_k,u_k)\le 0"
        self.assertAlmostEqual(RM.required_seconds("math", eq, False, self.cfg), 3.4)
        self.assertAlmostEqual(RM.required_seconds("math", eq, True, self.cfg), 4.76)

    def test_hilltop_caption_too_short(self):
        log_all = json.loads((FIX / "design" / "hilltop.timeline.json").read_text())
        findings, stats = [], {}
        cfg = dict(RM.DEFAULTS, **self.cfg)
        design = json.loads((testenv.CONFIG / "video.json").read_text())["design"]
        CR.scene_reading("Hilltop", log_all["scenes"]["Hilltop"], cfg, findings, stats, log_all["frame"], design)
        short = [f for f in findings if f["check"] == "display-time"]
        self.assertTrue(any("knife-edge" in f["detail"] and f["severity"] == "error" for f in short), short)
        self.assertGreater(stats["Hilltop"]["appearances_checked"], 10)

    def test_intervals(self):
        ev = [[0.0, 0, 0, 0, 1, 1, 0], [1.0, 1, 0, 0, 1, 1, 1], [2.5, 0, 0, 0, 1, 1, 0], [3.0, 1, 0, 0, 1, 1, 1]]
        self.assertEqual(CR.intervals(ev, 4.0), [(1.0, 2.5), (3.0, 4.0)])


class Search(unittest.TestCase):
    CFG = {"demand_weights": {"views": 0.5, "autocomplete": 0.3, "trends": 0.2}, "published_within_days": 730,
           "recent_days": 365}

    def test_nothing_answered_is_unknown_not_zero(self):
        ev = {"autocomplete": {"status": "unavailable: offline"}, "youtube": {"status": "skipped: no YOUTUBE_API_KEY"},
              "trends": {"status": "unavailable: no client"}}
        scores, why = SD.score_topic(ev, self.CFG, "2026-10-30")
        self.assertIsNone(scores["search_demand"])
        self.assertIsNone(scores["supply_gap"])
        self.assertIn("unknown", why["search_demand"])

    def test_weights_renormalise_over_answers(self):
        ev = {"autocomplete": {"status": "ok", "queries": [{"matching": ["a", "b", "c"]}]},
              "youtube": {"status": "unavailable"}, "trends": {"status": "unavailable"}}
        scores, _ = SD.score_topic(ev, self.CFG, "2026-10-30")
        self.assertEqual(scores["search_demand"], 3.0)
        self.assertIsNone(scores["supply_gap"])

    def test_relevance_and_queries(self):
        self.assertTrue(SD.relevant("MPC stability with a Lyapunov function", "mpc lyapunov function", 0.6))
        self.assertFalse(SD.relevant("Cooking with robots", "mpc lyapunov function", 0.6))
        self.assertEqual(SD.default_queries({"title": "A new robot (fictional) for contact planning"}, 2),
                         ["contact planning"])

    def test_ranking_with_recorded_search_data(self):
        tmp = Path(tempfile.mkdtemp(prefix="search-test-"))
        try:
            env = dict(os.environ, SEARCH_BACKEND="fake", SEARCH_FAKE_DATA=str(FIX / "search_fake.json"))
            r = subprocess.run([sys.executable, "tools/run.py", "new", *testenv.COVERAGE_ARGS, "--root", str(tmp), "--date", "2026-10-30"],
                               cwd=REPO, capture_output=True, text=True, check=True)
            run = Path(r.stdout.strip())
            for f in ("sources.json", "scores.json"):
                shutil.copy(FIX / "run" / f, run / f)
            subprocess.run([sys.executable, "tools/search_demand.py", str(run)], cwd=REPO, env=env, check=True,
                           capture_output=True)
            data = json.loads((run / "search.json").read_text())
            self.assertIsNotNone(data["topics"]["T1"]["scores"]["supply_gap"])
            self.assertIsNone(data["topics"]["T2"]["scores"]["supply_gap"])
            subprocess.run([sys.executable, "tools/rank_topics.py", str(run)], cwd=REPO, check=True, capture_output=True)
            md = (run / "ranking.md").read_text()
            self.assertIn("? (unknown, weight renormalised)", md)
            self.assertIn("Competing video", md)
            rk = json.loads((run / "ranking.json").read_text())
            self.assertEqual(rk["ranking"][0]["id"], "T1")
            self.assertIn("search.json", rk["inputs_sha256"])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class Series(unittest.TestCase):
    def test_section_ids(self):
        ids = S.section_ids(SOURCE / "explainer.html")
        self.assertEqual(ids["3"], "sec-hj")
        self.assertEqual(ids["3.3"], "sec-scalar")

    def test_start_copies_the_source_and_scenes_kept_for_an_episode(self):
        """explainer.html, code/ and data/ come from the source; scenes kept in series/<slug>/episodes/epNN/ (an
        episode made again after a fix) are copied with their plan; an episode without kept scenes gets none."""
        sys.path.insert(0, str(REPO / "tests"))
        from series_fixture import make_series, scenes_beyond_helpers
        tmp = Path(tempfile.mkdtemp(prefix="series-start-"))
        try:
            d = make_series(tmp)
            kept = d / "episodes" / "ep02"
            (kept / "scenes").mkdir(parents=True)
            (kept / "scenes" / "fixed.py").write_text("from manim import *\nfrom common import *\n\n\n"
                                                      "class Fixed(RAScene):\n    pass\n")
            (kept / "plan.json").write_text(json.dumps({"scenes": [{"file": "fixed.py", "class": "Fixed"}]}))
            for ep in ("2", "1"):
                r = subprocess.run([sys.executable, "tools/series.py", "start", str(d), "--episode", ep,
                                    "--root", str(tmp / "runs"), "--date", "2026-11-10"], cwd=REPO,
                                   capture_output=True, text=True)
                self.assertEqual(r.returncode, 0, r.stderr)
            ep2 = next((tmp / "runs").glob("*-ep02-*"))
            self.assertEqual(sha256(ep2 / "explainer.html"), sha256(SOURCE / "explainer.html"))
            self.assertTrue((ep2 / "code" / "checks.toml").exists())
            self.assertTrue((ep2 / "video" / "data" / "hilltop_samples.csv").exists())  # data/ of the source
            self.assertTrue((ep2 / "video" / "scenes" / "fixed.py").exists())
            self.assertTrue((ep2 / "video" / "plan.json").exists())
            self.assertEqual(json.loads((ep2 / "episode.json").read_text())["scenes_from_plan"],
                             [{"file": "fixed.py", "class": "Fixed"}])
            self.assertIn("episodes/ep02", (ep2 / "video" / "episode.md").read_text())
            ep1 = next((tmp / "runs").glob("*-ep01-*"))
            self.assertEqual(scenes_beyond_helpers(ep1), [])                   # episode 1 kept no scenes
            self.assertNotIn("fixed.py", (ep1 / "video" / "episode.md").read_text())
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_slug_ends_at_a_word_without_a_stop_word(self):
        self.assertEqual(S.slugify("The hilltop: Hamilton–Jacobi and the stable manifold", 32),
                         "the-hilltop-hamilton-jacobi")
        self.assertEqual(S.slugify("One step is enough (with the right boundary term)", 32), "one-step-is-enough")
        self.assertEqual(S.slugify("Gauss's principle: multipliers are forces", 32), "gauss-s-principle-multipliers")
        self.assertEqual(S.slugify("Supercalifragilisticexpialidocious", 10), "supercalif")
        self.assertEqual(S.slugify("***", 10), "episode")

    def test_a_plan_from_the_source_validates_and_starts_at_episode_one(self):
        """A schema-2 plan made from a source (the fixture source and plan: real plans are made by /plan-series and
        are not part of the tests) validates against the source, carries no copied assets and starts with episode 1;
        its approval state follows the setting, and require=True always asks for the approval."""
        sys.path.insert(0, str(REPO / "tests"))
        from series_fixture import make_series
        tmp = Path(tempfile.mkdtemp(prefix="series-source-"))
        try:
            for approve in (True, False):
                sp = make_series(tmp / str(approve), approve=approve) / "series.json"
                s = json.loads(sp.read_text())
                self.assertEqual(s["source"], testenv.SOURCE)
                self.assertEqual(s["explainer_sha256"], sha256(SOURCE / "explainer.html"))
                self.assertEqual(S.validate_v2(s), ([], []))
                self.assertFalse(any(k in e for e in s["episodes"]
                                     for k in ("assets_from", "scenes", "voiceover_draft")))
                st = S.approval_state(sp, s)
                self.assertEqual(st["approved"], approve)
                self.assertEqual(st["required"], S.approval_setting() == "required")
                req = S.approval_state(sp, s, require=True)
                self.assertTrue(req["required"])
                if not approve:
                    self.assertRegex(req["detail"], r"\./tools/human/approve_series\.py \S*series/fixture-series")
                self.assertEqual(S.pick_next(s, None, sp, tmp / "runs")["number"], 1)   # the plan's release order
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

def _text(i, top, bbox, content="label", axis=False, order=None):
    return {"id": i, "kind": "text", "content": content, "bbox": bbox, "font_size": 28.0, "color": "#e2e8f0",
            "opacity": 1.0, "order": i if order is None else order, "top": top, "live": False, "axis": axis, "lines": 1}


def _axis(i, top, p, q):
    return {"id": i, "order": i, "top": top, "live": False, "axis": True, "bbox": [min(p[0], q[0]), min(p[1], q[1]),
            max(p[0], q[0]), max(p[1], q[1])], "stroke_width": 2.0, "stroke_opacity": 1.0, "stroke_color": "#334155",
            "fill_opacity": 0.0, "fill_color": "#334155", "points": [list(p), list(q)]}


def spacing(texts, paths=()):
    d, palette = CD.load_config()
    rep = CD.Report()
    log = {"snapshots": [{"t": 1.0, "settled": True, "label": "play", "texts": texts, "paths": list(paths),
                          "elements": 2}], "timeline": [], "duration": 2.0}
    CD.scene_checks("S", log, {"width": 14.222, "height": 8.0, "background": "#0f172a"}, d, palette, rep)
    return [f for f in rep.items if f["check"] == "spacing"]


class Spacing(unittest.TestCase):
    """Texts of different groups, or a text beside an axis line, need a visible gap (config/video.json design)."""

    def test_gap_between_groups(self):
        near = spacing([_text(1, 0, [0, 0, 2, 0.3]), _text(2, 1, [0, 0.4, 2, 0.7])])       # 0.10 apart
        self.assertEqual([f["severity"] for f in near], ["warning"])
        touching = spacing([_text(1, 0, [0, 0, 2, 0.3]), _text(2, 1, [0, 0.33, 2, 0.6])])  # 0.03 apart
        self.assertEqual([f["severity"] for f in touching], ["error"])
        clear = spacing([_text(1, 0, [0, 0, 2, 0.3]), _text(2, 1, [0, 0.5, 2, 0.8])])      # 0.20 apart
        self.assertEqual(clear, [])

    def test_one_group_may_sit_close(self):
        self.assertEqual(spacing([_text(1, 0, [0, 0, 2, 0.3]), _text(2, 0, [0, 0.36, 2, 0.6])]), [])

    def test_axis_line_beside_text_but_not_at_its_tip(self):
        beside = spacing([_text(1, 0, [1.0, 0.1, 2.0, 0.4])], [_axis(2, 1, (0, 0), (4, 0))])
        self.assertEqual([f["severity"] for f in beside], ["warning"])
        tip = spacing([_text(1, 0, [4.1, -0.1, 4.3, 0.15], content="q")], [_axis(2, 1, (0, 0), (4, 0))])
        self.assertEqual(tip, [])


class RecallLoad(unittest.TestCase):
    """Callbacks to equations no longer on screen are design warnings, never errors."""

    def scene(self, name, duration, math=(), narration=()):
        tl = [{"id": i, "kind": "math", "content": c, "live": False, "axis": False,
               "events": [[a, 1, 0, 0, 1, 1, 1.0], [b, 0, 0, 0, 1, 1, 1.0]]} for i, (c, a, b) in enumerate(math)]
        vo = [{"start": t, "duration": 3.0, "words": len(x.split()), "text": x} for t, x in narration]
        return name, {"duration": duration, "timeline": tl, "voiceovers": vo}

    def test_callbacks_and_their_count(self):
        hj = r"H\big(q,-V'(q)\big)=0"
        logs = [self.scene("A", 40, [(hj, 5, 30)], [(10, "That is the Hamilton-Jacobi equation.")]),
                self.scene("B", 100, [], [(70, "Remember the Hamilton-Jacobi equation."),
                                          (80, "The Hamilton-Jacobi equation again.")])]
        found = CR.recall_load(logs, {"window_s": 60, "max_callbacks": 3})
        self.assertEqual(len(found), 2)
        self.assertTrue(all(f["severity"] == "warning" and f["check"] == "recall-load" for f in found))
        shown = [self.scene("A", 40, [(hj, 5, 30)], [(10, "That is the Hamilton-Jacobi equation.")]),
                 self.scene("B", 100, [(hj, 60, 99)], [(70, "The Hamilton-Jacobi equation again.")])]
        self.assertEqual(CR.recall_load(shown, {"window_s": 60}), [])            # shown again: no recall needed
        many = [self.scene("A", 40, [(hj, 5, 30)], [(10, "That is the Hamilton-Jacobi equation.")]),
                self.scene("B", 400, [], [(100 + 60 * k, "Recall the Hamilton-Jacobi equation.") for k in range(4)])]
        found = CR.recall_load(many, {"window_s": 60, "max_callbacks": 3})
        self.assertEqual(len(found), 5)
        self.assertEqual(found[-1]["scene"], "(episode)")
        self.assertIn("split the episode", found[-1]["detail"])


class ThumbnailBehindTitle(unittest.TestCase):
    """The thumbnail check fails when frame text lies under the title or the area behind it is busy."""

    def make(self, busy, text_under):
        from PIL import Image, ImageDraw
        tmp = Path(tempfile.mkdtemp(prefix="thumb-test-"))
        (tmp / "video" / "final").mkdir(parents=True)
        (tmp / "video" / "renders").mkdir(parents=True)
        img = Image.new("RGB", (1280, 720), (15, 23, 42))
        d = ImageDraw.Draw(img)
        if busy:
            for k in range(0, 640, 6):
                d.line((k, 250, k + 3, 470), fill=(70, 80, 100), width=2)
        for x in range(72, 600, 28):                                         # the title's ink: glyph-like strokes
            d.rectangle((x, 300, x + 12, 400), fill=(226, 232, 240))
        img.save(tmp / "video" / "final" / "thumbnail.jpg", quality=92)
        meta = {"size": [1280, 720], "frame": {"scene": "S", "scene_time": 2.0},
                "elements": [{"role": "title", "text": "Only one", "font_px": 92, "bbox": [64, 290, 610, 410],
                              "color": "#e2e8f0"}]}
        (tmp / "video" / "final" / "thumbnail.json").write_text(json.dumps(meta))
        texts = [_text(1, 0, [-5.5, 0.2, -3.0, 0.6], content="H = +0.2")] if text_under else \
            [_text(1, 0, [3.0, 2.5, 5.0, 2.9], content="far away")]
        log = {"frame": {"width": 14.222, "height": 8.0}, "scenes": {"S": {"snapshots": [
            {"t": 1.0, "settled": True, "texts": texts, "paths": []}], "timeline": [], "duration": 3.0}}}
        (tmp / "video" / "renders" / "S.layout.json").write_text(json.dumps(log))
        return tmp

    def findings(self, tmp):
        d, _ = CD.load_config()
        rep = CD.Report()
        CD.thumbnail_check(tmp, d, rep, tmp / "out")
        return [f["detail"] for f in rep.items if f["severity"] == "error"]

    def test_calm_background_passes(self):
        tmp = self.make(busy=False, text_under=False)
        try:
            self.assertEqual(self.findings(tmp), [])
        finally:
            shutil.rmtree(tmp)

    def test_text_under_the_title_fails(self):
        tmp = self.make(busy=False, text_under=True)
        try:
            self.assertTrue(any("frame text behind the title" in f for f in self.findings(tmp)))
        finally:
            shutil.rmtree(tmp)

    def test_busy_background_fails(self):
        tmp = self.make(busy=True, text_under=False)
        try:
            self.assertTrue(any("busy background behind the title" in f for f in self.findings(tmp)))
        finally:
            shutil.rmtree(tmp)


def _manim():
    m = os.environ.get("MANIM") or str(REPO / ".venv" / "bin" / "manim")
    return m if Path(m).exists() else shutil.which("manim")


@unittest.skipUnless(_manim() and shutil.which("ffmpeg"), "needs Manim with manim-voiceover ($MANIM or .venv) and ffmpeg")
class LiveReadoutPlacement(unittest.TestCase):
    """A readout added with self.add() is placed before its first frame (the probe used to log it at the origin)."""

    def test_added_readout_is_logged_where_it_is_shown(self):
        tmp = Path(tempfile.mkdtemp(prefix="readout-test-"))
        try:
            scenes = tmp / "video" / "scenes"
            scenes.mkdir(parents=True)
            for f in ("common.py", "voice.py", "reading_model.py"):
                shutil.copy(REPO / "templates" / "manim" / f, scenes / f)
            (scenes / "t.py").write_text(
                "from manim import *\nfrom common import *\n\n"
                "class T(RAScene):\n    def construct(self):\n"
                "        self.add(Text('centre', font_size=28))\n"
                "        k = ValueTracker(1.0)\n"
                "        live = readout(lambda: f'k = {k.get_value():.2f}', font_size=28)\n"
                "        live.add_updater(lambda m: m.move_to([4.0, 2.0, 0]))\n"
                "        self.add(live)\n"
                "        self.wait(2.5)\n", encoding="utf-8")
            env = dict(os.environ, MANIM=_manim(), VOICE_SERVICE="silent")
            r = subprocess.run(["bash", str(REPO / "tools" / "render_video.sh"), str(tmp), "--check", "--voice", "silent",
                                "--scene", "t.py:T"], capture_output=True, text=True, env=env, cwd=REPO)
            self.assertEqual(r.returncode, 0, r.stdout[-1500:] + r.stderr[-1500:])
            findings = design_findings(tmp / "video" / "checks" / "T.layout.json")
            self.assertEqual([f for f in findings if f["check"] == "overlap"], [])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


@unittest.skipUnless(_manim() and shutil.which("ffmpeg") and shutil.which("latex"),
                     "needs Manim with manim-voiceover ($MANIM or .venv), LaTeX and ffmpeg")
class EquationBuiltFromPieces(unittest.TestCase):
    """An equation on screen only as its pieces is logged as one math text, so a stroke through it is found."""

    def test_render(self):
        tmp = Path(tempfile.mkdtemp(prefix="pieces-test-"))
        try:
            scenes = tmp / "video" / "scenes"
            scenes.mkdir(parents=True)
            for f in ("common.py", "voice.py", "reading_model.py"):
                shutil.copy(REPO / "templates" / "manim" / f, scenes / f)
            (scenes / "t.py").write_text(
                "from manim import *\nfrom common import *\n\n"
                "class T(RAScene):\n    def construct(self):\n"
                "        chain = MathTex('V_N', r'\\le', 'V_{N-1}', r'\\le', 'V_0', font_size=40).move_to([0, 1, 0])\n"
                "        self.play(LaggedStart(*[FadeIn(x) for x in chain], lag_ratio=0.2), run_time=1.0)\n"
                "        src = Square(0.3, color=INK).move_to([-4, -2, 0])\n"
                "        eq = MathTex('a', '+', 'b', font_size=40).move_to([3, -2, 0])\n"
                "        self.add(src)\n"
                "        self.play(TransformFromCopy(src, eq[0]), FadeIn(eq[1]), FadeIn(eq[2]), run_time=0.6)\n"
                "        self.play(Create(Line([-3, 0.6, 0], [3, 1.4, 0], color=INK, stroke_width=6)), run_time=0.5)\n"
                "        self.wait(2.0)\n", encoding="utf-8")
            env = dict(os.environ, MANIM=_manim(), VOICE_SERVICE="silent")
            r = subprocess.run(["bash", str(REPO / "tools" / "render_video.sh"), str(tmp), "--check", "--voice", "silent",
                                "--scene", "t.py:T"], capture_output=True, text=True, env=env, cwd=REPO)
            self.assertEqual(r.returncode, 0, r.stdout[-1500:] + r.stderr[-1500:])
            layout = tmp / "video" / "checks" / "T.layout.json"
            log = json.loads(layout.read_text())["scenes"]["T"]
            last = [x for x in log["snapshots"] if x["settled"]][-1]
            maths = {x["content"]: x for x in last["texts"] if x["kind"] == "math"}
            self.assertIn("a + b", maths)
            chain = next(x for c, x in maths.items() if c.startswith("V_N"))
            self.assertLess(chain["bbox"][0], -1.0)                       # the whole chain, not one piece
            findings = design_findings(layout)
            self.assertTrue([f for f in findings if f["check"] == "overlap" and "crossed" in f["detail"]
                             and "V_N" in f["detail"]], [f["detail"] for f in findings])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


@unittest.skipUnless(_manim() and shutil.which("ffmpeg"), "needs Manim with manim-voiceover ($MANIM or .venv) and ffmpeg")
class AttachAndLegendTable(unittest.TestCase):
    """common.py attach() reaches the layout log, and legend_table() aligns its columns by construction."""

    def test_render(self):
        tmp = Path(tempfile.mkdtemp(prefix="legend-test-"))
        try:
            scenes = tmp / "video" / "scenes"
            scenes.mkdir(parents=True)
            for f in ("common.py", "voice.py", "reading_model.py"):
                shutil.copy(REPO / "templates" / "manim" / f, scenes / f)
            (scenes / "t.py").write_text(
                "from manim import *\nfrom common import *\n\n"
                "class T(RAScene):\n    def construct(self):\n"
                "        curve = Line([-5, 2, 0], [-1, 2, 0], color=INK, stroke_width=4)\n"
                "        name = attach(Text('curve', font_size=26), curve, direction=UP, buff=0.08)\n"
                "        alts = [Text('arrives as t', font_size=24, color=c) for c in (RED, GREEN, BLUE)]\n"
                "        t = legend_table([[Dot(radius=0.08, color=c), MathTex(h, font_size=30, color=c),\n"
                "                           Text(w, font_size=24, color=c)]\n"
                "                          for c, h, w in ((RED, 'H=+0.2', 'too hard'), (GREEN, 'H=0', 'exactly'),\n"
                "                                          (BLUE, 'H=-0.2', 'too softly'))],\n"
                "                         min_widths={2: max(a.width for a in alts)}).move_to([2.5, -1.5, 0])\n"
                "        self.add(curve, name, VGroup(*[VGroup(*r[:2]) for r in t.cells]), t.column(2))\n"
                "        self.wait(1.0)\n"
                "        self.remove(t.column(2))\n"
                "        self.add(VGroup(*[t.place(a, i, 2) for i, a in enumerate(alts)]))\n"
                "        self.wait(1.0)\n", encoding="utf-8")
            env = dict(os.environ, MANIM=_manim(), VOICE_SERVICE="silent")
            r = subprocess.run(["bash", str(REPO / "tools" / "render_video.sh"), str(tmp), "--check", "--voice", "silent",
                                "--scene", "t.py:T"], capture_output=True, text=True, env=env, cwd=REPO)
            self.assertEqual(r.returncode, 0, r.stdout[-1500:] + r.stderr[-1500:])
            log = json.loads((tmp / "video" / "checks" / "T.layout.json").read_text())["scenes"]["T"]
            snaps = [x for x in log["snapshots"] if x["settled"]]
            name = next(x for x in snaps[0]["texts"] if x["content"] == "curve")
            self.assertTrue(name["attached"])
            self.assertTrue(name["attached_to"])
            for snap, words in ((snaps[0], ("too hard", "exactly", "too softly")), (snaps[-1], ("arrives as t",))):
                lefts = {round(x["bbox"][0], 2) for x in snap["texts"] if x["content"] in words}
                self.assertEqual(len(lefts), 1, (words, lefts))            # one column, one left edge
                lefts_h = {round(x["bbox"][0], 2) for x in snap["texts"] if x["content"].startswith("H=")}
                self.assertEqual(len(lefts_h), 1, lefts_h)
            findings = design_findings(tmp / "video" / "checks" / "T.layout.json")
            self.assertEqual([f for f in findings if f["check"] in ("alignment", "spacing")], [], findings)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


def _shape(i, top, bbox, fill=0.0):
    return {"id": i, "order": i, "top": top, "live": False, "axis": False, "bbox": bbox, "stroke_width": 3.0,
            "stroke_opacity": 1.0, "stroke_color": "#818cf8", "fill_opacity": fill, "fill_color": "#818cf8",
            "points": [[bbox[0], bbox[1]], [bbox[2], bbox[3]]]}


def scene_findings(snapshots, timeline=(), duration=10.0, check=None):
    d, palette = CD.load_config()
    rep = CD.Report()
    log = {"snapshots": list(snapshots), "timeline": list(timeline), "duration": duration}
    CD.scene_checks("S", log, {"width": 14.222, "height": 8.0, "background": "#0f172a"}, d, palette, rep)
    return [f for f in rep.items if check is None or f["check"] == check]


def _settled(t, texts, paths=()):
    return {"t": t, "settled": True, "label": "play", "texts": list(texts), "paths": list(paths), "elements": 3}


def _curve(i, top, points, width=4.0, color="#94a3b8"):
    xs, ys = [q[0] for q in points], [q[1] for q in points]
    return {"id": i, "order": i, "top": top, "live": False, "axis": False, "bbox": [min(xs), min(ys), max(xs), max(ys)],
            "stroke_width": width, "stroke_opacity": 1.0, "stroke_color": color, "fill_opacity": 0.0,
            "fill_color": color, "points": [list(q) for q in points]}


def _sized(i, top, bbox, size=28.0, content="label"):
    return dict(_text(i, top, bbox, content), font_size=size)


class LayoutRegression(unittest.TestCase):
    """The Hilltop legend: a tag touching the hill curve, staggered tags, a left panel ending far above the plot."""

    def test_the_defective_frame_produces_all_three_findings(self):
        found = design_findings(FIX / "design" / "hilltop_legend_before.layout.json")
        near = [f for f in found if f["check"] == "spacing" and "from a line" in f["detail"]]
        self.assertEqual(len(near), 1, found)
        self.assertEqual(near[0]["severity"], "error")
        self.assertIn("too hard", near[0]["detail"])
        align = [f for f in found if f["check"] == "alignment"]
        self.assertEqual(len(align), 1)
        self.assertIn("'exactly' is 0.53 units off", align[0]["detail"])
        panels = [f for f in found if f["check"] == "panels"]
        self.assertEqual(len(panels), 1)
        self.assertIn("left one ends 1.53 units higher", panels[0]["detail"])

    def test_the_fixed_frame_produces_none(self):
        self.assertEqual(design_findings(FIX / "design" / "hilltop_legend_after.layout.json"), [])


class TextNearStrokes(unittest.TestCase):
    """Any strong stroke closer than min_gap_warn to a text: not only strokes that cross it."""

    def label(self):
        return _text(1, 1, [0.0, 0.0, 1.0, 0.3], "too hard")

    def test_a_curve_ending_at_the_text_edge(self):
        for y, sev in ((0.32, "error"), (0.40, "warning")):
            f = scene_findings([_settled(1.0, [self.label()], [_curve(2, 0, [(-2.0, 1.5), (0.5, y)])])], check="spacing")
            self.assertEqual([x["severity"] for x in f], [sev], (y, f))
        clear = _curve(2, 0, [(-2.0, 1.5), (0.5, 0.6)])
        self.assertEqual(scene_findings([_settled(1.0, [self.label()], [clear])], check="spacing"), [])

    def test_attached_label_is_exempt_from_its_own_object_only(self):
        near = _curve(2, 0, [(-2.0, 1.5), (0.5, 0.35)])
        own = dict(self.label(), attached=True, attached_to=[2])
        self.assertEqual(scene_findings([_settled(1.0, [own], [near])], check="spacing"), [])
        other = dict(self.label(), attached=True, attached_to=[9])
        self.assertEqual(len(scene_findings([_settled(1.0, [other], [near])], check="spacing")), 1)
        anything = dict(self.label(), attached=True, attached_to=None)
        self.assertEqual(scene_findings([_settled(1.0, [anything], [near])], check="spacing"), [])

    def test_faint_grid_strokes_do_not_count(self):
        grid = _curve(2, 0, [(-2.0, 0.35), (3.0, 0.35)], width=2.0, color="#334155")
        self.assertEqual(scene_findings([_settled(1.0, [self.label()], [grid])], check="spacing"), [])

    def test_a_crossing_is_reported_once_as_an_overlap(self):
        through = _curve(2, 0, [(-1.0, 0.15), (2.0, 0.15)])
        f = scene_findings([_settled(1.0, [self.label()], [through])])
        self.assertEqual([x["check"] for x in f if x["check"] in ("overlap", "spacing")], ["overlap"])


class AlmostAligned(unittest.TestCase):
    def column(self, lefts, size=24.0):
        return [_sized(i + 1, 5, [x, -0.5 * i, x + 1.2, -0.5 * i + 0.3], size, f"tag {i}") for i, x in enumerate(lefts)]

    def test_drift_within_align_max_warns(self):
        f = scene_findings([_settled(1.0, self.column([-1.74, -1.70, -1.62]))], check="alignment")
        self.assertEqual(len(f), 1)
        self.assertIn("almost aligned", f[0]["detail"])

    def test_one_staggered_member_warns(self):
        f = scene_findings([_settled(1.0, self.column([-1.74, -2.25, -1.73]))], check="alignment")
        self.assertEqual(len(f), 1)
        self.assertRegex(f[0]["detail"], r"'tag 1' is 0\.5[12] units off")

    def test_aligned_indented_or_mixed_columns_pass(self):
        for lefts in ([-1.74, -1.74, -1.75], [-2.0, -2.0, -1.0]):          # aligned; a deliberate 1-unit indent
            self.assertEqual(scene_findings([_settled(1.0, self.column(lefts))], check="alignment"), [], lefts)
        mixed = [_sized(1, 5, [-1.74, 0.0, -0.5, 0.4], 36.0, "Heading")] + self.column([-1.6, -1.74])
        self.assertEqual(scene_findings([_settled(1.0, mixed)], check="alignment"), [])

    def test_a_row_almost_on_one_line_warns(self):
        row = [_sized(i + 1, 5, [2.0 * i, y, 2.0 * i + 1.5, y + 0.3], 24.0, f"cell {i}")
               for i, y in enumerate((0.0, 0.1, 0.05))]
        self.assertEqual(len(scene_findings([_settled(1.0, row)], check="alignment")), 1)


class PanelBalance(unittest.TestCase):
    def frame(self, left_text_boxes, role=None):
        plot = _shape(9, 9, [1.0, -3.0, 6.0, 2.0])
        texts = [_text(i + 1, i + 1, b, f"line {i}") for i, b in enumerate(left_text_boxes)]
        d, palette = CD.load_config()
        rep = CD.Report()
        CD.scene_checks("S", {"snapshots": [_settled(1.0, texts, [plot])], "timeline": [], "duration": 5.0},
                        {"width": 14.222, "height": 8.0, "background": "#0f172a"}, d, palette, rep, role=role)
        return [f for f in rep.items if f["check"] == "panels"]

    def test_one_side_ending_much_higher_warns_and_the_outro_is_exempt(self):
        top_aligned = [[-6.0, 1.4 - 0.6 * i, -1.0, 1.8 - 0.6 * i] for i in range(3)]
        f = self.frame(top_aligned)
        self.assertTrue(any("ends" in x["detail"] and "higher" in x["detail"] for x in f), f)
        self.assertEqual(self.frame(top_aligned, role="outro"), [])

    def test_a_short_column_centred_beside_a_tall_plot_passes(self):
        centred = [[-6.0, 0.1 - 0.6 * i, -1.0, 0.5 - 0.6 * i] for i in range(3)]
        self.assertEqual(self.frame(centred), [])

    def test_a_panel_with_a_large_hole_warns(self):
        boxes = [[-6.0, 1.6, -1.0, 2.0], [-6.0, -3.0, -1.0, -2.6], [-6.0, -0.7, -5.4, -0.3]]
        self.assertTrue(any("empty in one block" in x["detail"] for x in self.frame(boxes)))


class SpaceUsage(unittest.TestCase):
    """Warnings for frames that use the safe area badly (config/video.json design space_*)."""

    def test_content_crowded_on_one_side(self):
        snap = _settled(1.0, [_text(1, 0, [-6.2, 1.0, -3.0, 1.4])], [_shape(2, 1, [-6.2, -3.0, -2.0, 0.8])])
        details = " ".join(f["detail"] for f in scene_findings([snap], check="space"))
        self.assertIn("left part of the frame", details)
        self.assertIn("large empty block", details)

    def test_small_picture(self):
        snap = _settled(1.0, [], [_shape(1, 0, [-1.0, -0.8, 1.0, 0.8])])
        details = " ".join(f["detail"] for f in scene_findings([snap], check="space"))
        self.assertIn("scale the picture up", details)

    def test_balanced_frame_is_clean(self):
        snap = _settled(1.0, [_text(1, 0, [-3.0, 2.8, 3.0, 3.3])],
                        [_shape(2, 1, [-5.8, -3.2, -0.3, 2.4]), _shape(3, 2, [0.3, -3.2, 5.8, 2.4])])
        self.assertEqual(scene_findings([snap], check="space"), [])


class Motion(unittest.TestCase):
    """Checks during animations, from the probe's timeline: transient overlaps and jittering readouts."""

    @staticmethod
    def item(i, events, live=False, content="label"):
        return {"id": i, "kind": "text", "content": content, "font_size": 28.0, "lines": 1, "live": live,
                "axis": False, "events": events}

    def test_transient_overlap_while_moving(self):
        still = self.item(1, [[0.0, 1, 0.0, 0.0, 2.0, 0.4, 1.0]], content="fixed label")
        passing = self.item(2, [[0.0, 1, 4.0, 0.0, 6.0, 0.4, 1.0], [1.0, 1, 1.0, 0.1, 3.0, 0.5, 1.0],
                                [1.5, 1, 4.0, 0.1, 6.0, 0.5, 1.0]], content="moving label")
        found = scene_findings([_settled(0.0, []), _settled(3.0, [])], [still, passing], check="motion")
        self.assertEqual([f["severity"] for f in found], ["warning"])
        self.assertIn("overlap for 0.50 s", found[0]["detail"])

    def test_long_transient_overlap_is_an_error(self):
        still = self.item(1, [[0.0, 1, 0.0, 0.0, 2.0, 0.4, 1.0]])
        passing = self.item(2, [[0.0, 1, 4.0, 0.0, 6.0, 0.4, 1.0], [1.0, 1, 1.0, 0.1, 3.0, 0.5, 1.0],
                                [3.0, 1, 4.0, 0.1, 6.0, 0.5, 1.0]])
        found = scene_findings([_settled(0.0, []), _settled(4.0, [])], [still, passing], check="motion")
        self.assertEqual([f["severity"] for f in found], ["error"])

    def test_overlap_that_stays_is_left_to_the_settled_check(self):
        still = self.item(1, [[0.0, 1, 0.0, 0.0, 2.0, 0.4, 1.0]])
        arriving = self.item(2, [[0.0, 1, 4.0, 0.0, 6.0, 0.4, 1.0], [1.0, 1, 1.0, 0.1, 3.0, 0.5, 1.0]])
        self.assertEqual(scene_findings([_settled(2.0, [])], [still, arriving], check="motion"), [])

    def test_readout_width_jitter(self):
        jumpy = self.item(1, [[0.0, 1, 0.0, 0.0, 1.2, 0.4, 1.0], [0.5, 1, 0.0, 0.0, 1.6, 0.4, 1.0],
                              [1.0, 1, 0.0, 0.0, 1.3, 0.4, 1.0]], live=True, content="x = 1.3")
        steady = self.item(2, [[0.0, 1, 3.0, 0.0, 4.4, 0.4, 1.0], [0.5, 1, 3.0, 0.0, 4.45, 0.4, 1.0]], live=True)
        found = scene_findings([_settled(2.0, [])], [jumpy, steady], check="motion")
        self.assertEqual(len(found), 1)
        self.assertIn("changes width by 0.40", found[0]["detail"])


class ThumbnailFont(unittest.TestCase):
    """Without DejaVu Sans the thumbnail still renders, with another sans and a clear warning."""

    def test_missing_dejavu_falls_back_with_a_warning(self):
        try:
            from PIL import ImageFont
        except ImportError:
            self.skipTest("Pillow not installed")
        import contextlib
        import io
        import thumbnail as T
        real = ImageFont.truetype

        def no_dejavu(name, *a, **k):
            if "dejavu" in str(name).lower():
                raise OSError("cannot open resource")
            return real(name, *a, **k)
        err = io.StringIO()
        T._warned.clear()
        ImageFont.truetype = no_dejavu
        try:
            with contextlib.redirect_stderr(err):
                f = T.font(40)
        finally:
            ImageFont.truetype = real
        self.assertTrue(hasattr(f, "getbbox"))
        self.assertIn("not found", err.getvalue())
        self.assertIn("font-dejavu", err.getvalue())


if __name__ == "__main__":
    unittest.main()
