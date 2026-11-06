"""Unit tests for tools/deliver.py, the hand-over package of a finished video (python3 -m unittest)."""
import hashlib
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
SLUG = "the-hilltop"
RUN_NAME = "2026-11-14-the-hilltop"


def fake_run(root: Path, synthetic: bool = True, release: bool = True) -> Path:
    """A minimal finished series episode: final files, metadata, assembly, chapters, final-cut summary, gates."""
    run = root / "runs" / RUN_NAME
    final = run / "video" / "final"
    final.mkdir(parents=True)
    (run / "review" / "final_cut").mkdir(parents=True)
    (run / "video" / "voice").mkdir(parents=True)
    (run / "episode.json").write_text(json.dumps({
        "schema_version": 2, "mode": "series", "series": "fixture-series", "series_title": "Fixture series",
        "episode": 2, "episodes_total": 2, "title": "The hilltop", "slug": SLUG, "topic_id": "EP02",
        "playlist": {"title": "Fixture series", "privacy": "public", "description": "Two episodes, one idea."}}))
    (run / "video" / "series_context.json").write_text(json.dumps({
        "series_title": "Fixture series", "episode": 2, "prerequisites": {"must": ["1"]},
        "short_titles": {"1": "One step"}, "published": {}}))
    (final / f"{SLUG}.mp4").write_bytes(b"\x00\x00\x00\x18ftypmp42 fixture video")
    (final / f"{SLUG}.srt").write_text("1\n00:00:00,000 --> 00:00:02,000\nOnly one push arrives.\n")
    (final / "thumbnail.jpg").write_bytes(b"\xff\xd8\xff fixture thumbnail")
    chapters = [{"start": 0, "title": "Only one push", "label": "0:00 Only one push"},
                {"start": 30, "title": "The cost still to pay", "label": "0:30 The cost still to pay"},
                {"start": 75, "title": "What it leaves us", "label": "1:15 What it leaves us"}]
    (final / "chapters.json").write_text(json.dumps({"schema_version": 1, "chapters": chapters, "valid": True}))
    (final / "assembly.json").write_text(json.dumps({"duration": 95.0, "segments": [
        {"role": "hook", "start": 0.0}, {"role": "recap", "start": 30.0, "chapter": "Recap: one step"},
        {"role": "outro", "start": 78.0}]}))
    desc = ("Episode 2 of 2 · Fixture series\n\nOnly one push brings the ball to rest.\n\nChapters:\n"
            + "\n".join(c["label"] for c in chapters) + f"\n\nRemaining Action\n\nRun: {RUN_NAME}")
    (final / "youtube.json").write_text(json.dumps({
        "schema_version": 1, "run": RUN_NAME, "marker": f"Run: {RUN_NAME}", "slug": SLUG,
        "snippet": {"title": "The hilltop: only one push arrives", "description": desc,
                    "tags": ["stable manifold", "Remaining Action"], "categoryId": "28", "defaultLanguage": "en"},
        "status": {"privacyStatus": "private", "selfDeclaredMadeForKids": False,
                   "containsSyntheticMedia": synthetic, "license": "youtube"}}))
    (run / "video" / "voice" / "manifest.json").write_text(json.dumps(
        {"service": "piper" if synthetic else "recorded", "voice_model": "fixture-voice" if synthetic else ""}))
    (run / "review" / "final_cut" / "summary.md").write_text("# Final-cut review\n\n0 blocker, 0 major.\n")
    vsha = hashlib.sha256((final / f"{SLUG}.mp4").read_bytes()).hexdigest()
    (run / "review" / "gates.json").write_text(json.dumps(
        {"stage": "release" if release else "final", "passed": True, "video_sha256": vsha, "checks": []}))
    return run


def deliver(run: Path, *extra) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(REPO / "tools" / "deliver.py"), str(run), *extra],
                          capture_output=True, text=True)


class Deliver(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="deliver-"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_refused_without_a_release_gate_for_this_video(self):
        run = fake_run(self.tmp, release=False)
        r = deliver(run)
        self.assertEqual(r.returncode, 1)
        self.assertIn("--stage release", r.stderr)
        self.assertFalse((run / "deliver").exists())
        gp = run / "review" / "gates.json"
        gp.write_text(json.dumps(dict(json.loads(gp.read_text()), stage="release", video_sha256="0" * 64)))
        r = deliver(run)
        self.assertEqual(r.returncode, 1)
        self.assertIn("another version of the video", r.stderr)
        gp.write_text(json.dumps(dict(json.loads(gp.read_text()), passed=False)))
        self.assertEqual(deliver(run).returncode, 1)

    def test_package_and_upload_sheet(self):
        run = fake_run(self.tmp)
        r = deliver(run)
        self.assertEqual(r.returncode, 0, r.stderr)
        d = run / "deliver"
        self.assertEqual(sorted(p.name for p in d.iterdir()),
                         sorted([f"{SLUG}.mp4", f"{SLUG}.srt", "thumbnail.jpg", "upload_sheet.md",
                                 "final_cut_review.md", "youtube.json", "SHA256SUMS"]))
        self.assertEqual((d / f"{SLUG}.mp4").read_bytes(), (run / "video/final" / f"{SLUG}.mp4").read_bytes())
        sheet = (d / "upload_sheet.md").read_text()
        # what the sheet carries from the metadata, the manifest, the assembly and the series context
        for needle in ("The hilltop: only one push arrives", "Episode 2 of 2 · Fixture series",
                       "0:30 The cost still to pay", "stable manifold, Remaining Action",
                       "Altered or synthetic content: **Yes**", "piper (fixture-voice)", "Science & Technology",
                       "No, it is not made for kids", '"Fixture series"', "Two episodes, one idea.", f"`{SLUG}.srt`",
                       "`thumbnail.jpg`", "End screen from 1:18 to 1:35", "card at 0:30", '"One step"'):
            self.assertIn(needle, sheet)
        self.assertNotIn(f"Run: {RUN_NAME}", sheet)          # the upload marker only serves automated uploads
        sums = dict(reversed(line.split("  ")) for line in (d / "SHA256SUMS").read_text().splitlines())
        self.assertEqual(sums[f"{SLUG}.mp4"], hashlib.sha256((d / f"{SLUG}.mp4").read_bytes()).hexdigest())
        self.assertIn("0 blocker", (d / "final_cut_review.md").read_text())

    def test_own_voice_is_not_declared_synthetic(self):
        run = fake_run(self.tmp, synthetic=False)
        self.assertEqual(deliver(run).returncode, 0)
        sheet = (run / "deliver" / "upload_sheet.md").read_text()
        self.assertIn("Altered or synthetic content: **No**", sheet)

    def test_the_series_plan_travels_with_the_episode(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("ra_deliver", REPO / "tools" / "deliver.py")
        D = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(D)
        plans = self.tmp / "series"
        (plans / "fixture-series").mkdir(parents=True)
        (plans / "fixture-series" / "series.json").write_text('{"slug": "fixture-series"}\n')
        (plans / "fixture-series" / "PLAN.md").write_text("# Plan\n")
        D.SERIES = plans
        run = fake_run(self.tmp)
        D.build(run, run / "deliver")
        d = run / "deliver"
        self.assertEqual((d / "series/fixture-series/series.json").read_text(), '{"slug": "fixture-series"}\n')
        self.assertTrue((d / "series/fixture-series/PLAN.md").exists())
        self.assertIn("series/fixture-series/series.json", (d / "SHA256SUMS").read_text())
        sheet = (d / "upload_sheet.md").read_text()
        self.assertIn("## Series plan", sheet)

    def test_delivered_episode_counts_for_next(self):
        sys.path.insert(0, str(REPO / "tools"))
        import series as S
        run = fake_run(self.tmp)
        self.assertEqual(S.delivered("fixture-series", self.tmp / "runs"), set())
        self.assertEqual(deliver(run).returncode, 0)
        self.assertEqual(S.delivered("fixture-series", self.tmp / "runs"), {2})


if __name__ == "__main__":
    unittest.main()
