"""Unit tests for the self-contained video rule (tools/video/check_selfcontained.py), the equation-number setting,
the links setting and the source credits of the metadata, and the series "fresh" start (python3 -m unittest)."""
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

import check_selfcontained as SC  # noqa: E402
import metadata  # noqa: E402

FIX = REPO / "tests" / "fixtures" / "selfcontained"


def run_cli(*args):
    return subprocess.run([sys.executable, str(REPO / "tools" / "video" / "check_selfcontained.py"), *args],
                          capture_output=True, text=True)


def settings(**kw):
    st = SC.settings()
    st.update(kw)
    return st


def items(texts, source="screen", kind="plain"):
    return [{"source": source, "where": f"{source} {i}", "text": t, "kind": kind, "order": (0, 2, float(i))}
            for i, t in enumerate(texts)]


class Fixture(unittest.TestCase):
    """The before fixture shows every kind of reference; the same scene, fixed, passes."""

    def test_before_fails_with_every_kind_of_reference(self):
        r = run_cli("--layout", str(FIX / "before.layout.json"), "--srt", str(FIX / "before.srt"))
        self.assertEqual(r.returncode, 1)
        out = r.stdout
        for needle in ("file name 'sec5_6_symbolic_checks.py'", "folder path 'code/'", "material outside the video "
                       "'explainer'", "numbered reference 'Eq. 3'", "numbered reference 'Section 6.5'", "URL",
                       "equation label '\\qquad(18)'", "equation label '(19)'", "equation label '\\tag{3}'",
                       "equation label command '\\label'", "circled number", "equation reference 'equation 2'",
                       "link 'linked in the description'", "the video's description",
                       "cross-episode equation number 'equation 4 of episode 2'", "numbered reference 'figure 2'",
                       "(\\star)"):
            self.assertIn(needle, out, needle)
        for allowed in ("Two-link", "y(0)", "\\frac{\\kappa q^2}{2}", "'last episode'"):
            self.assertNotIn(allowed, "\n".join(ln for ln in out.splitlines() if ln.startswith("ERROR")), allowed)

    def test_after_passes(self):
        r = run_cli("--layout", str(FIX / "after.layout.json"), "--srt", str(FIX / "after.srt"))
        self.assertEqual(r.returncode, 0, r.stdout)


class Rules(unittest.TestCase):
    def found(self, texts, **kw):
        return SC.check_items(items(texts), settings(**kw))

    def test_robotics_link_and_math_words_are_allowed(self):
        ok = ["a two-link arm", "the link length l1", "each link of the arm", "the Hamilton–Jacobi equation",
              "a cross section", "we figure out the push", "the third equation in this list", "W(1) and y(0)",
              "subscripts and superscripts", "q₀ = (1.0, −0.95) rad", "this episode"]
        self.assertEqual(self.found(ok), [])

    def test_references_fail(self):
        bad = {"see the code": "material outside the video", "link below": "link", "Fig. 3": "numbered reference",
               "Table 2": "numbered reference", "§6.5": "section sign", "www.example.org": "URL",
               "run hilltop.py": "file name", "in the pinned comment": "the video's description",
               "Theorem 2 says": "numbered reference"}
        for text, rule in bad.items():
            with self.subTest(text=text):
                self.assertIn(rule, [f["rule"] for f in self.found([text])])

    def test_link_counts_only_with_an_outward_cue(self):
        ordinary = ["That link is what we'll need next.", "the missing link between energy and time",
                    "These two ideas are linked.", "linking the torque to the acceleration", "a weak link in the chain",
                    "the link below the elbow", "the link hangs below the joint", "The masses are linked by a spring.",
                    "Follow the link's tip as it swings."]
        self.assertEqual(self.found(ordinary), [])
        outward = ["Follow the link to try it.", "the link below", "the link in the description",
                   "It's linked in the notes.", "Links are in the description.", "Click on the link above.",
                   "I've linked the full derivation below.", "There's a link to it in the show notes."]
        for text in outward:
            with self.subTest(text=text):
                self.assertIn("link", [f["rule"] for f in self.found([text])])

    def test_other_episodes_by_title_and_meaning_are_not_flagged(self):
        ok = ["In the episode on Gauss's principle we saw the forces balance.", "Previously, the window was one step.",
              "Next time: the same idea with a speed limit.", "This series takes one idea per episode.",
              "The episode on the boundary term has the full story.", "In the last episode this was a stage cost.",
              "the next episode", "a Fourier series", "the second equation of this episode"]
        for eq in (False, True):
            self.assertEqual(self.found(ok, equation_numbers=eq), [])

    def test_hard_prerequisites_fail(self):
        for text in ("You must have watched the first episode.", "Watch the episode on the boundary term first.",
                     "This won't make sense unless you saw part one.", "Make sure you've seen the hilltop episode.",
                     "Go back and watch the previous video."):
            with self.subTest(text=text):
                self.assertEqual([f["rule"] for f in self.found([text])], ["hard prerequisite"])

    def test_cross_episode_equation_numbers_fail_whatever_the_setting(self):
        bad = ["equation 4 of episode 2", "Eq. (4) in the previous episode", "episode 2's equation 4",
               "result 3 from the episode on Gauss's principle", "(4) from part two"]
        for eq in (False, True):
            for text in bad:
                with self.subTest(text=text, equation_numbers=eq):
                    self.assertEqual([f["rule"] for f in self.found([text], equation_numbers=eq)],
                                     ["cross-episode equation number"])

    def test_math_tags(self):
        st = settings(equation_numbers=False)
        for tex in (r"x=1\qquad(4)", r"\tag{2} x=1", r"\text{(ii)}", r"x=1\quad(\ast)", r"\eqref{a}", "(7)"):
            with self.subTest(tex=tex):
                self.assertTrue(SC.check_items(items([tex], kind="math"), st), tex)
        for tex in (r"f(2)=4", r"V(q_0)", r"(a+b)^2", r"\big(q,-V'(q)\big)"):
            with self.subTest(tex=tex):
                self.assertEqual(SC.check_items(items([tex], kind="math"), st), [], tex)


class Publication(unittest.TestCase):
    """A video never names the publication it covers or its authors; the description credits them."""
    RULE = "publication or its authors"

    def found(self, texts):
        return [f["match"] for f in SC.check_items(items(texts), settings()) if f["rule"] == self.RULE]

    def test_news_video_fails_wherever_it_names_the_publication(self):
        found = [f for f in SC.check(FIX / "news-before", "final") if f["rule"] == self.RULE]
        self.assertEqual({f["source"] for f in found}, {"narration", "captions", "screen", "chapter"})
        self.assertEqual({f["match"].lower() for f in found},
                         {"authors", "the paper", "preprint", "arxiv", "the study"})
        self.assertTrue(all(f.get("detail") for f in found))

    def test_the_same_video_on_its_own_terms_passes(self):
        self.assertEqual(SC.check(FIX / "news-after", "final"), [])

    def test_a_reference_fails_the_check(self):
        r = run_cli("--srt", str(FIX / "news-before" / "video" / "renders" / "news.srt"))
        self.assertEqual(r.returncode, 1)
        self.assertIn("publication or its authors 'The paper'", r.stdout)

    def test_references_fail(self):
        for text in ("This paper shows it", "in their study", "an article in a journal", "a recent publication",
                     "Lee et al. showed", "the researchers found", "a pre-print", "the paper's main result",
                     "its co-authors"):
            with self.subTest(text=text):
                self.assertTrue(self.found([text]))

    def test_ordinary_words_pass(self):
        ok = ["a sheet of paper", "the paper cup", "a paper-thin margin", "tricks that paper over the gap",
              "a planner that studies the contacts", "the study of motion", "an article of clothing",
              "a journal bearing", "Researchers have long assumed it", "we study the pendulum", "the authority"]
        self.assertEqual(SC.check_items(items(ok), settings()), [])


class EquationNumbers(unittest.TestCase):
    """config/video.json equation_numbers: false rejects every label; true allows the video's own sequence only."""

    def episode(self, labels, narration=()):
        its = [{"source": "screen", "where": f"S t={t}", "text": rf"x_{i}=0\qquad({n})", "kind": "math",
                "order": (0, 2, float(t))} for i, (n, t) in enumerate(labels)]
        its += [{"source": "narration", "where": f"block {i}", "text": t, "kind": "plain", "order": (0, 1, i)}
                for i, t in enumerate(narration)]
        return its

    def test_off_rejects_even_the_videos_own_numbering(self):
        found = SC.check_items(self.episode([(1, 1.0), (2, 5.0)]), settings(equation_numbers=False))
        self.assertEqual(len(found), 2)

    def test_on_allows_the_own_sequence_and_references_to_it(self):
        st = settings(equation_numbers=True)
        self.assertEqual(SC.check_items(self.episode([(1, 1.0), (2, 5.0), (1, 9.0)], ["as equation 2 shows"]), st), [])

    def test_on_still_rejects_document_tags(self):
        st = settings(equation_numbers=True)
        found = SC.check_items(self.episode([(13, 1.0)], ["recall equation 5"]), st)
        self.assertEqual(sorted(f["rule"] for f in found), ["equation label", "equation reference"])
        jump = SC.check_items(self.episode([(1, 1.0), (3, 5.0)]), st)
        self.assertEqual([f["label"] for f in jump], ["3"])


class Chapters(unittest.TestCase):
    def test_explainer_heading_is_not_a_chapter_title(self):
        tmp = Path(tempfile.mkdtemp(prefix="sc-chapter-"))
        try:
            (tmp / "video" / "scenes").mkdir(parents=True)
            (tmp / "explainer.html").write_text('<h3 id="sec-boundary">6.4 Role of the boundary term</h3>')
            plan = {"scenes": [{"file": "a.py", "class": "A", "section": "sec-boundary",
                                "chapter": "Role of the boundary term"}]}
            (tmp / "video" / "plan.json").write_text(json.dumps(plan))
            found = SC.check(tmp, "draft")
            self.assertEqual([f["rule"] for f in found], ["explainer heading as chapter"])
            plan["scenes"][0]["chapter"] = "What the boundary term does"
            (tmp / "video" / "plan.json").write_text(json.dumps(plan))
            self.assertEqual(SC.check(tmp, "draft"), [])
        finally:
            shutil.rmtree(tmp)


class Links(unittest.TestCase):
    def test_links_are_opt_in_per_run(self):
        ch = {"links": {"include": False}}
        old = os.environ.pop("INCLUDE_LINKS", None)
        try:
            self.assertFalse(metadata.links_included(ch))
            self.assertTrue(metadata.links_included(ch, "on"))
            os.environ["INCLUDE_LINKS"] = "on"
            self.assertTrue(metadata.links_included(ch))
            self.assertFalse(metadata.links_included({"links": {"include": True}}, "off"))
            os.environ["INCLUDE_LINKS"] = ""
            self.assertTrue(metadata.links_included({"links": {"include": True}}))
        finally:
            os.environ.pop("INCLUDE_LINKS", None)
            if old is not None:
                os.environ["INCLUDE_LINKS"] = old


class Credits(unittest.TestCase):
    """The description's primary sources name their authors: the source's own record, else the run's references.json."""

    def setUp(self):
        self.run = Path(tempfile.mkdtemp(prefix="sc-credits-"))

    def tearDown(self):
        shutil.rmtree(self.run, ignore_errors=True)

    def references(self, *entries):
        refs = [dict({"key": f"ref{i}", "type": "preprint", "year": 2026,
                      "verification": {"status": "verified", "checked_against": ["record"]}}, **e)
                for i, e in enumerate(entries)]
        (self.run / "references.json").write_text(json.dumps({"schema_version": 1, "references": refs}))

    def test_authors_from_the_record_or_the_same_work_in_the_references(self):
        self.references({"authors": ["J. Doe", "R. Roe"], "title": "Planning a million robots", "arxiv": "2611.01234"},
                        {"authors": ["K. Lee"], "title": "Contact-implicit planning", "doi": "10.1000/xyz.12"},
                        {"authors": ["M. Kim"], "title": "Learned dynamics with certificates",
                         "url": "https://example.org/kim"})
        sources = [{"url": "https://example.org/own", "title": "Own record", "authors": ["A. Author"]},
                   {"url": "https://arxiv.org/abs/2611.01234v2", "title": "A title that differs"},
                   {"url": "https://doi.org/10.1000/XYZ.12", "title": "Another title"},
                   {"url": "https://example.org/kim/", "title": "Kim's page"},
                   {"url": "https://example.org/other", "title": "Learned Dynamics, with Certificates"},
                   {"url": "https://example.org/none", "title": "No record names its authors"}]
        self.assertEqual([s["authors"] for s in metadata.with_authors(self.run, sources)],
                         [["A. Author"], ["J. Doe", "R. Roe"], ["K. Lee"], ["M. Kim"], ["M. Kim"], []])

    def test_description_names_the_authors(self):
        shutil.copy(REPO / "tests" / "fixtures" / "run" / "sources.json", self.run / "sources.json")
        self.references({"authors": ["J. Doe", "R. Roe", "K. Lee"], "title": "Fixture paper A",
                         "url": "https://example.org/fixture/paper-a"})
        (self.run / "selection.json").write_text(json.dumps({"topic_id": "T1", "slug": "fixture-descent-certificate"}))
        (self.run / "video").mkdir()
        (self.run / "video" / "plan.json").write_text(json.dumps({"title": "A title", "summary": "A summary.",
                                                                 "tags": ["control"]}))
        desc = metadata.build(self.run, "", False)["snippet"]["description"].splitlines()
        self.assertIn("- Fixture paper A, by J. Doe, R. Roe, and K. Lee (Example Proceedings): "
                      "https://example.org/fixture/paper-a", desc)
        self.assertIn("- Fictional classic MPC paper (Example Proceedings): "
                      "https://example.org/fixture/classic-mpc-paper", desc)              # no record names its authors

    def test_author_lists(self):
        s = {"title": "T", "publisher": "Example Lab", "url": "https://example.org/t"}
        lines = {n: metadata.source_line(dict(s, authors=[f"A{i}" for i in range(1, n + 1)])) for n in (1, 2, 3, 12)}
        self.assertEqual(lines[1], "- T, by A1 (Example Lab): https://example.org/t")
        self.assertIn(", by A1 and A2 (", lines[2])
        self.assertIn(", by A1, A2, and A3 (", lines[3])
        self.assertIn(", by A1, A2, A3, et al. (", lines[12])
        self.assertEqual(metadata.source_line(dict(s, authors=["Example Lab"])),
                         "- T (Example Lab): https://example.org/t")                   # the publisher is no author


class FreshStart(unittest.TestCase):
    def test_fresh_copies_no_kept_scenes(self):
        sys.path.insert(0, str(REPO / "tests"))
        from series_fixture import make_series, scenes_beyond_helpers
        tmp = Path(tempfile.mkdtemp(prefix="series-fresh-"))
        try:
            d = make_series(tmp)
            kept = d / "episodes" / "ep02" / "scenes" / "kept.py"
            kept.parent.mkdir(parents=True)
            kept.write_text("from manim import *\n\n\nclass Kept(Scene):\n    pass\n")
            before = kept.read_bytes()
            r = subprocess.run([sys.executable, "tools/series.py", "start", str(d), "--episode", "2",
                                "--root", str(tmp / "runs"), "--date", "2026-11-12", "--fresh"], cwd=REPO,
                               capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            run = Path(r.stdout.strip())
            self.assertEqual(scenes_beyond_helpers(run), [])                   # the helpers only, never kept.py
            self.assertTrue((run / "video" / "scenes" / "common.py").is_file())
            self.assertFalse((run / "video" / "plan.json").exists())
            self.assertFalse(list((run / "video").glob("voiceover_*.md")))
            self.assertNotIn("kept.py", (run / "video" / "episode.md").read_text())   # the brief offers no kept scene
            ep = json.loads((run / "episode.json").read_text())
            self.assertTrue(ep["fresh"])
            self.assertEqual(ep["scenes_from_plan"], [])
            self.assertEqual(kept.read_bytes(), before)                       # the kept assets are untouched
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
