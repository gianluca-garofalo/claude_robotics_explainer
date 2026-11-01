"""Unit tests for the automation tools: topic selection, video plan, chapters, metadata (python3 -m unittest)."""
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

import assemble  # noqa: E402
import auto_select  # noqa: E402
import metadata  # noqa: E402
import plan as P  # noqa: E402

FIX = REPO / "tests" / "fixtures" / "run"


def seg(kind, start, duration, section=None):
    return {"kind": kind, "start": start, "duration": duration, "section": section}


class Chapters(unittest.TestCase):
    TITLES = {"a": "First idea", "b": "Second idea", "c": "Third idea"}

    def test_intro_folds_into_first_chapter(self):
        segs = [seg("intro", 0, 3), seg("scene", 3, 37, "a"), seg("scene", 40, 50, "b"), seg("scene", 90, 60, "c"),
                seg("outro", 150, 6)]
        ch = assemble.chapters(segs, self.TITLES, 156)
        self.assertEqual([c["label"] for c in ch], ["0:00 First idea", "0:40 Second idea", "1:30 Third idea"])

    def test_short_chapter_is_merged(self):
        segs = [seg("intro", 0, 3), seg("scene", 3, 37, "a"), seg("scene", 40, 5, "b"), seg("scene", 45, 60, "c")]
        ch = assemble.chapters(segs, self.TITLES, 105)
        self.assertEqual([c["title"] for c in ch], ["First idea", "Third idea"])

    def test_same_section_is_one_chapter(self):
        segs = [seg("scene", 0, 30, "a"), seg("scene", 30, 30, "a"), seg("scene", 60, 30, "b")]
        self.assertEqual(len(assemble.chapters(segs, self.TITLES, 90)), 2)

    def test_short_last_chapter_folds_back(self):
        segs = [seg("scene", 0, 40, "a"), seg("scene", 40, 40, "b"), seg("scene", 80, 4, "c")]
        self.assertEqual([c["title"] for c in assemble.chapters(segs, self.TITLES, 84)], ["First idea", "Second idea"])

    def test_scenes_without_a_source_section(self):
        """Context and outro scenes may omit "section": their chapter is the plan's own title."""
        segs = [dict(seg("scene", 0, 30, "a"), chapter="Only one push works"),
                {"kind": "scene", "start": 30, "duration": 40, "chapter": "Recap: why it is stable"},
                {"kind": "scene", "start": 70, "duration": 20, "section": None, "chapter": "Three facts"}]
        self.assertEqual([c["title"] for c in assemble.chapters(segs, self.TITLES, 90)],
                         ["Only one push works", "Recap: why it is stable", "Three facts"])

    def test_timestamps(self):
        self.assertEqual(assemble.fmt_chapter(59.9), "0:59")
        self.assertEqual(assemble.fmt_chapter(3725), "1:02:05")
        self.assertEqual(assemble.fmt_srt(3.0), "00:00:03,000")


class Metadata(unittest.TestCase):
    def test_tags_length_counts_quotes(self):
        self.assertEqual(metadata.tags_length(["a b", "c"]), len('"a b",c'))

    def test_synthetic_media_auto(self):
        ch = {"youtube": {"contains_synthetic_media": "auto"}, "voice": {"service": "azure"}}
        old = os.environ.pop("VOICE_SERVICE", None)
        try:
            self.assertTrue(metadata.synthetic_flag(ch))
            os.environ["VOICE_SERVICE"] = "recorded"
            self.assertFalse(metadata.synthetic_flag(ch))
            ch["youtube"]["contains_synthetic_media"] = True
            self.assertTrue(metadata.synthetic_flag(ch))
        finally:
            os.environ.pop("VOICE_SERVICE", None)
            if old is not None:
                os.environ["VOICE_SERVICE"] = old


class Plan(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="plan-test-"))
        (self.tmp / "video" / "scenes").mkdir(parents=True)
        (self.tmp / "video" / "scenes" / "idea.py").write_text("class Idea(VoiceoverScene):\n    pass\n")
        self.plan = {"schema_version": 1, "title": "A title", "summary": "A summary.", "tags": ["control"],
                     "scenes": [{"file": "idea.py", "class": "Idea", "section": "sec-idea", "chapter": "The idea"}],
                     "thumbnail": {"scene": "Idea", "time": 2.0, "text": "Four words at most"}}

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_valid(self):
        self.assertEqual(P.problems(self.tmp, self.plan), [])

    def test_rejects_unsafe_names(self):
        for f, c in (("../idea.py", "Idea"), ('idea.py"; echo x', "Idea"), ("idea.py", "Idea; rm"), ("idea.sh", "Idea")):
            with self.subTest(f=f, c=c):
                plan = dict(self.plan, scenes=[{"file": f, "class": c, "section": "sec-idea", "chapter": "The idea"}])
                self.assertTrue(any("plain file name" in p for p in P.problems(self.tmp, plan)))

    def test_rejects_clickbait_length_and_brackets(self):
        self.assertTrue(P.problems(self.tmp, dict(self.plan, title="x" * 91)))
        self.assertTrue(P.problems(self.tmp, dict(self.plan, summary="see <script>")))
        self.assertTrue(P.problems(self.tmp, dict(self.plan, tags=["a,b"])))

    def test_section_must_be_a_heading_of_the_explainer(self):
        (self.tmp / "explainer.html").write_text('<h2 id="sec-idea">1. Idea</h2><h3 id="sec-sub">1.1 Sub</h3>'
                                                 '<h2 id="sec-other">2. Other</h2>', encoding="utf-8")
        self.assertEqual(P.problems(self.tmp, self.plan), [])
        plan = dict(self.plan, scenes=[{"file": "idea.py", "class": "Idea", "section": "sec-typo", "chapter": "The idea"}])
        self.assertTrue(any("not a heading id" in p for p in P.problems(self.tmp, plan)))

    def test_series_sections_are_sources_not_a_mapping(self):
        (self.tmp / "explainer.html").write_text('<h2 id="sec-idea">1. Idea</h2><h3 id="sec-sub">1.1 Sub</h3>'
                                                 '<h2 id="sec-other">2. Other</h2>', encoding="utf-8")
        (self.tmp / "episode.json").write_text(json.dumps({"mode": "series", "sections": ["1"], "slug": "s"}))
        other = dict(self.plan, scenes=[{"file": "idea.py", "class": "Idea", "section": "sec-other", "chapter": "The idea"}])
        self.assertEqual(P.problems(self.tmp, other), [])                   # any heading of the explainer is a source
        outro = dict(self.plan, scenes=[{"file": "idea.py", "class": "Idea", "chapter": "The idea", "role": "outro"}])
        self.assertEqual(P.problems(self.tmp, outro), [])                   # outro and context scenes may omit it

    def test_thumbnail_must_name_a_listed_scene(self):
        plan = dict(self.plan, thumbnail={"scene": "Other", "time": 1, "text": "x"})
        self.assertTrue(any("thumbnail" in p for p in P.problems(self.tmp, plan)))


class Selection(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="select-test-"))
        r = subprocess.run([sys.executable, "tools/run.py", "new", *testenv.COVERAGE_ARGS, "--root", str(cls.tmp / "runs"), "--date",
                            "2026-10-30"], cwd=REPO, capture_output=True, text=True, check=True)
        cls.run_dir = Path(r.stdout.strip())
        for f in ("sources.json", "scores.json"):
            shutil.copy(FIX / f, cls.run_dir / f)
        subprocess.run([sys.executable, "tools/rank_topics.py", str(cls.run_dir)], cwd=REPO, capture_output=True,
                       check=True)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def ledger(self, entries):
        p = self.tmp / "ledger.json"
        p.write_text(json.dumps({"schema_version": 1, "runs": entries}))
        return p

    def test_best_eligible_topic(self):
        chosen, _ = auto_select.select(self.run_dir, None)
        self.assertEqual(chosen["id"], "T1")

    def test_skips_rejected_and_staged_topics(self):
        for status in ("published", "staged", "rejected"):
            with self.subTest(status=status):
                led = self.ledger({"r1": {"status": status, "slug": "fixture-descent-certificate"}})
                chosen, skipped = auto_select.select(self.run_dir, led)
                self.assertEqual(chosen["id"], "T2")
                self.assertTrue(any(f"already {status}" in r for s in skipped for r in s["reasons"]))

    def test_same_primary_source_counts_as_covered(self):
        led = self.ledger({"r1": {"status": "published", "slug": "another-slug",
                                  "primary_urls": ["https://example.org/fixture/paper-a"]}})
        chosen, _ = auto_select.select(self.run_dir, led)
        self.assertEqual(chosen["id"], "T2")

    def test_ineligible_topic_is_never_chosen(self):
        led = self.ledger({"r1": {"status": "published", "slug": "fixture-descent-certificate"},
                           "r2": {"status": "published", "slug": "fixture-contact-benchmark"}})
        chosen, skipped = auto_select.select(self.run_dir, led)
        self.assertIsNone(chosen)
        self.assertTrue(any("rubric gates" in r for s in skipped if s["id"] == "T3" for r in s["reasons"]))

    def test_stale_ranking_is_refused(self):
        tmp = Path(tempfile.mkdtemp(prefix="select-stale-"))
        try:
            run = tmp / self.run_dir.name
            shutil.copytree(self.run_dir, run)
            scores = json.loads((run / "scores.json").read_text())
            (run / "scores.json").write_text(json.dumps(scores, indent=1))
            with self.assertRaises(SystemExit):
                auto_select.select(run, None)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
