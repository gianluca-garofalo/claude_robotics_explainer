#!/usr/bin/env python3
"""End-to-end dry run of the automated pipeline after the agent's part, YouTube and LinkedIn stubbed, news and
series mode; skips itself (exit 0, says why) without ffmpeg, Manim or Node with Playwright.

Usage:
  python3 tests/automation_dry_run.py [--keep]
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
import testenv  # noqa: E402
testenv.activate()                  # fixture config and sources, before any tool is imported
FIX = REPO / "tests" / "fixtures" / "run"
PY = sys.executable
RESULTS: list[tuple[str, str, str]] = []


def step(name, cmd, env=None, expect=0, check=None):
    r = subprocess.run(cmd, cwd=REPO, capture_output=True, text=True, env=env)
    ok = r.returncode == expect
    detail = (r.stdout.strip().splitlines() or [""])[-1][:110]
    if ok and check:
        res = check(r)
        ok, detail = (res, detail) if isinstance(res, bool) else res
    RESULTS.append((name, "ok" if ok else "FAIL", detail))
    if not ok:
        print(f"--- {name} (exit {r.returncode}, expected {expect})\n{r.stdout[-2500:]}\n{r.stderr[-2500:]}")
    return r


def report(tmp, keep):
    w = max(len(n) for n, _, _ in RESULTS)
    print()
    for n, st, d in RESULTS:
        print(f"{st:5} {n:<{w}}  {d}")
    fails = [n for n, st, _ in RESULTS if st == "FAIL"]
    print(f"\nautomation dry run: {'FAIL' if fails else 'ok'} ({len(RESULTS) - len(fails)} ok, {len(fails)} failed)")
    if keep:
        print(f"kept: {tmp}")
    return 1 if fails else 0


KEYS = ("AZURE_SUBSCRIPTION_KEY", "AZURE_SERVICE_REGION")      # the only text-to-speech keys a voice reads (azure)


def keyless_voice(manim: str) -> tuple[str, str]:
    """(service, why): Piper, the configured voice, when its model is here; else silent, chosen explicitly (there is
    no fallback voice: the final gates then run with --allow-silent)."""
    mpy = str(Path(manim).parent / "python")
    py = mpy if Path(mpy).exists() else PY
    piper = subprocess.run([py, str(REPO / "templates/manim/voice.py"), "check", "piper"], capture_output=True,
                           text=True)
    if piper.returncode == 0:
        return "piper", ""
    return "silent", "Piper's voice model is not here (./setup.sh downloads it), so this dry run is explicitly silent"


CHANNEL = json.loads((testenv.CONFIG / "channel.json").read_text(encoding="utf-8"))     # the fixture preferences
PIPELINE = json.loads((testenv.CONFIG / "pipeline.json").read_text(encoding="utf-8"))


def final_cut(run: Path, label: str) -> None:
    """Frames of the assembled video, the (fixture) final-cut and linear-viewer reports, the release gate: an open
    blocker is refused."""
    step(f"final-cut frames and contact sheets{label}", [PY, "tools/video/final_frames.py", str(run)],
         check=lambda r: (any((run / "review/final_cut").glob("sheet-*.jpg")) and
                          (run / "review/final_cut/frames.json").exists(), r.stdout.strip()[-110:]))
    rep = json.loads((FIX / "review/final_cut/final-cut-reviewer.json").read_text())
    blocked = dict(rep, findings=rep["findings"] + [dict(rep["findings"][0], id="FC-2", severity="blocker",
                                                         issue="fixture: a label hides the readout")])
    (run / "review/final_cut/final-cut-reviewer.json").write_text(json.dumps(blocked, indent=1))
    shutil.copy(FIX / "review/final_cut/linear-viewer.json", run / "review/final_cut/linear-viewer.json")
    step(f"final-cut review with an open blocker merged{label}", [PY, "tools/merge_reviews.py", str(run), "--set",
                                                                  "final_cut"])
    step(f"release gate refuses an open blocker (the run goes back){label}",
         [PY, "tools/gate.py", str(run), "--stage", "release"], expect=1)
    shutil.copy(FIX / "review/final_cut/final-cut-reviewer.json", run / "review/final_cut/final-cut-reviewer.json")
    step(f"final-cut review merged (fixture report, no blocker){label}",
         [PY, "tools/merge_reviews.py", str(run), "--set", "final_cut"])
    step(f"release gate: final gates for this video, final-cut review clean{label}",
         [PY, "tools/gate.py", str(run), "--stage", "release"],
         check=lambda r: ("final-cut review" in (run / "review/gates.md").read_text(), r.stdout.strip()[-110:]))


CONTEXT_SCENE = '''"""Series context (dry run): the builds-on frame under the spoken context."""
from manim import *  # noqa: F401,F403
from common import *  # noqa: F401,F403


class SeriesContext(RAScene):
    def construct(self):
        frame = builds_on()
        with self.voiceover(text="This is episode two of two. It builds on the first episode, on why predictive "
                                 "control is stable."):
            self.play(FadeIn(frame, shift=UP * 0.1), run_time=0.8)
        self.read()
        self.play(FadeOut(frame), run_time=0.6)
'''

OUTRO_SCENE = '''"""Outro (dry run): the takeaway card and the channel name, the end-screen area empty; a finale, so no teaser."""
from manim import *  # noqa: F401,F403
from common import *  # noqa: F401,F403


class Outro(RAScene):
    def construct(self):
        layout = outro(takeaway_card(font_size=44))
        with self.voiceover(text="The cost still to pay generates the one push that arrives. It solves the "
                                 "Hamilton-Jacobi equation at zero energy, and it falls at exactly the rate of the "
                                 "cost. A boundary term is certified wherever that energy is at least zero."):
            self.play(FadeIn(layout[0]), FadeIn(layout[-1]), run_time=1.0)
        self.read()
        self.wait(2.0)
'''


def series_flow(tmp: Path, env: dict, site: Path, manim: str, voice: str) -> None:
    """Series mode, schema 2, on the fixture series (tests/series_fixture.py: two episodes made from the source
    document): an unapproved plan and a plan edited after its approval are refused; episode 2 of the approved plan
    starts fresh (the source's explainer, code and data and its series context; no scenes), gets a series context and
    an outro written here around the template scene (standing in for the body, to keep the dry run short) and runs to
    a published video in its playlist."""
    sys.path.insert(0, str(REPO / "tests"))
    import series_fixture
    unapproved = series_fixture.make_series(tmp / "unapproved", approve=False)
    step("series: approval required: an unapproved plan is refused",
         [PY, "tools/series.py", "start", str(unapproved), "--episode", "1", "--root", str(tmp / "refused"), "--date",
          "2026-11-09", "--by", "dry run", "--require-approval"], expect=1,
         check=lambda r: ("approve_series.py" in r.stderr, r.stderr.strip()[-110:]))
    optional = testenv.env(testenv.variant(tmp / "optional-config", {"pipeline": {"series": {"plan_approval":
                                                                                           "optional"}}}))
    step("series: approval optional: the unapproved plan starts, with a note",
         [PY, "tools/series.py", "start", str(unapproved), "--episode", "1", "--root", str(tmp / "optional"), "--date",
          "2026-11-09", "--by", "dry run"], env=dict(optional, **{k: v for k, v in env.items()
                                                                  if k not in testenv.environ()}),
         check=lambda r: ("note: plan approval is optional" in r.stderr and "approve_series.py" not in r.stderr and
                          (Path(r.stdout.strip()) / "episode.json").exists(), r.stderr.strip()[-110:]))
    changed = series_fixture.make_series(tmp / "changed")
    data = json.loads((changed / "series.json").read_text(encoding="utf-8"))
    data["episodes"][1]["target_viewer"] += " (edited after the approval)"
    (changed / "series.json").write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    step("series: approval required: a plan edited after its approval is refused (the owner approves it again)",
         [PY, "tools/series.py", "start", str(changed), "--episode", "1", "--root", str(tmp / "refused"), "--date",
          "2026-11-09", "--by", "dry run", "--require-approval"], expect=1,
         check=lambda r: ("plan changed since the owner approved it" in r.stderr and "approve_series.py" in r.stderr,
                          r.stderr.strip()[-110:]))
    approved = series_fixture.make_series(tmp / "approved")

    def started(r):
        run_ = Path(r.stdout.strip())
        ctx = json.loads((run_ / "video/series_context.json").read_text())
        ep = json.loads((run_ / "episode.json").read_text())
        return (ctx["episode"] == 2 and ctx["context"]["frame"]["heading"] == "Episode 2 of 2" and
                series_fixture.scenes_beyond_helpers(run_) == [] and ep["scenes_from_plan"] == [] and
                (run_ / "video/data/hilltop_samples.csv").exists() and (run_ / "code/checks.toml").exists(),
                "series context (episode 2 of 2), the source's code and data, no scenes")
    r = step("series: start episode 2 of the approved plan (fresh)",
             [PY, "tools/series.py", "start", str(approved), "--episode", "2", "--root", str(tmp / "runs"), "--date",
              "2026-11-09", "--ledger", str(site / "ledger.json"), "--by", "dry run"], check=started)
    if r.returncode != 0:
        return
    run = Path(r.stdout.strip())
    slug = json.loads((approved / "series.json").read_text(encoding="utf-8"))["explainer_slug"]
    plan_guard = ("series plan (owner approval optional)" if PIPELINE["series"]["plan_approval"] == "optional"
                  else "series plan approved by the owner")
    scenes = run / "video" / "scenes"
    # the body is stood in for by the template scene, before the series context and the outro (keeps it short)
    shutil.copy(REPO / "templates" / "manim" / "scene_template.py", scenes / "scene_template.py")
    (scenes / "context.py").write_text(CONTEXT_SCENE, encoding="utf-8")
    (scenes / "outro.py").write_text(OUTRO_SCENE, encoding="utf-8")
    plan = {"schema_version": 1, "title": "The hilltop: Hamilton–Jacobi and the stable manifold",
            "summary": "Fixture episode for the automated pipeline test: only one push brings a ball to rest on a "
                       "hilltop, and the cost still to pay finds it.",
            "tags": ["Hamilton-Jacobi equation", "stable manifold", "model predictive control", "test fixture"],
            "scenes": [
                {"file": "scene_template.py", "class": "TemplateScene", "section": "sec-hj",
                 "chapter": "The idea in one scene", "role": "hook"},
                {"file": "context.py", "class": "SeriesContext", "chapter": "The idea in one scene", "role": "context"},
                {"file": "outro.py", "class": "Outro", "chapter": "What it leaves us", "role": "outro"}],
            "thumbnail": {"scene": "TemplateScene", "time": 7.0, "text": "Only H = 0 arrives"}}
    (run / "video" / "plan.json").write_text(json.dumps(plan, indent=2, ensure_ascii=False), encoding="utf-8")
    draft_and_review(run, env, " (series)")
    step("series: code checks of the episode's companion scripts (the fixture source's)",
         [PY, "tools/run_code_checks.py", str(run)])
    step("series: gates before rendering (the plan, explainer unchanged, design, reading, review)",
         [PY, "tools/gate.py", str(run), "--stage", "pre-render"],
         check=lambda r: (f"| {plan_guard} | pass |" in (run / "review/gates.md").read_text(),
                          r.stdout.strip()[-80:]))
    step(f"series: narration ({voice}, no keys)", [PY, "tools/video/synthesize_voice.py", str(run), "--service", voice],
         env=env)
    for sc in plan["scenes"]:
        step(f"series: final render of {sc['class']}", ["bash", "tools/render_video.sh", str(run), "--quality", "l",
                                                        "--scene", f"{sc['file']}:{sc['class']}"],
             env=dict(env, VOICE_SERVICE="recorded"))
    for name, cmd in (("assemble (scenes only: the hook opens, the outro ends)",
                       ["tools/video/assemble.py", str(run), "--quality", "l"]),
                      ("thumbnail", ["tools/video/thumbnail.py", str(run)])):
        step(f"series: {name}", [PY, *cmd], env=env)
    step("series: metadata with links on for this run (the pipeline's links input)",
         [PY, "tools/video/metadata.py", str(run)], env=dict(env, INCLUDE_LINKS="on"))
    m = json.loads((run / "video/final/youtube.json").read_text())
    RESULTS.append(("series: the description starts 'Episode 2 of 2 · <series>' and links the explainer, the video "
                    "does not", "ok" if (m["snippet"]["description"].startswith(
                        "Episode 2 of 2 · Fixture: two episodes of predictive control") and
                        f"/explainers/{slug}/#" in m["explainer_url"] and
                        m["explainer_url"] in m["snippet"]["description"] and m["links"]["included"])
                    else "FAIL", m["explainer_url"]))
    step("series: final design, reading and series checks", ["bash", "-c",
         f'"{PY}" tools/video/check_design.py "{run}" --stage final --no-frames && '
         f'"{PY}" tools/video/check_reading.py "{run}" --stage final && '
         f'"{PY}" tools/video/check_series.py "{run}" --stage final'])
    step("series: final gates (narration present)", [PY, "tools/gate.py", str(run), "--stage", "final",
                                                     "--require-links", "--video-quality", "l", "--min-duration", "10",
                                                     *(["--allow-silent"] if voice == "silent" else [])])
    step("series: hand-over package refused before the release gate", [PY, "tools/deliver.py", str(run)], expect=1,
         check=lambda r: ("not ready to hand over" in r.stderr and not (run / "deliver").exists() and
                          not (run.parent / "ledger").exists(), r.stderr.strip()[-110:]))
    final_cut(run, " (series)")
    step("series: hand-over package for the owner's own upload (the session's path)", [PY, "tools/deliver.py", str(run)],
         check=lambda r: delivered(run))
    step("series: the delivered episode counts (next and list read the runs folder)",
         [PY, "tools/series.py", "list", str(approved), "--root", str(tmp / "runs")],
         check=lambda r: ("[delivered]" in next(ln for ln in r.stdout.splitlines() if ln.strip().startswith("2.")),
                          r.stdout.strip().splitlines()[-1][:110]))
    r = step("series: private upload (fake YouTube)", [PY, "tools/publish/youtube.py", "stage", str(run), "--ledger",
                                                        str(site / "ledger.json")], env=env)
    vid = json.loads(r.stdout)["video_id"] if r.returncode == 0 else "none"
    step("series: publish (fake YouTube)", [PY, "tools/publish/youtube.py", "publish", "--video-id", vid,
                                            "--mode", "public"], env=env)
    r = step("series: added to the series playlist (created once)",
             [PY, "tools/publish/youtube.py", "playlist", str(run), "--video-id", vid, "--ledger",
              str(site / "ledger.json")], env=env,
             check=lambda r: (json.loads(r.stdout).get("added") is True and json.loads(r.stdout).get("created") is True,
                              r.stdout.strip()[:110]))
    pid = json.loads(r.stdout).get("playlist_id", "") if r.returncode == 0 else ""
    step("series: explainer published once for the whole series", [PY, "tools/publish/site.py", "promote", str(site),
                                                                    str(run), "--token", "abc123", "--video-id", vid],
         check=lambda r: ((site / "explainers" / slug / "index.html").exists(), r.stdout.strip()))
    step("series: ledger records the episode and the playlist", [PY, "tools/publish/site.py", "mark", str(site),
                                                                  str(run), "--status", "published", "--playlist", pid])
    step("series: playlist again: no duplicate", [PY, "tools/publish/youtube.py", "playlist", str(run), "--video-id",
                                                   vid, "--ledger", str(site / "ledger.json")], env=env,
         check=lambda r: (json.loads(r.stdout).get("added") is False, r.stdout.strip()[:110]))
    step("series: the next episode is 1, the one not yet published",
         [PY, "tools/series.py", "next", str(approved), "--ledger", str(site / "ledger.json"), "--root",
          str(tmp / "runs")],
         check=lambda r: (r.stdout.strip() == "1", r.stdout.strip()))


def delivered(run: Path) -> tuple[bool, str]:
    """deliver/: the video, captions and thumbnail as made, the upload sheet (episode line, chapters, the synthetic
    content answer from the narration manifest, the end screen, no upload marker), the final-cut summary, the plan,
    and a copy of the episode's ledger entry, runs/ledger/<run>.json."""
    d = run / "deliver"
    ep = json.loads((run / "episode.json").read_text())
    slug = ep["slug"]
    names = sorted(p.relative_to(d).as_posix() for p in d.rglob("*") if p.is_file())
    want = sorted([f"{slug}.mp4", f"{slug}.srt", "thumbnail.jpg", "upload_sheet.md", "final_cut_review.md",
                   "youtube.json", f"ledger-{run.name}.json", "SHA256SUMS"])
    entry = run.parent / "ledger" / f"{run.name}.json"
    sheet = (d / "upload_sheet.md").read_text()
    meta = json.loads((run / "video/final/youtube.json").read_text())
    synthetic = "**Yes**" if meta["status"]["containsSyntheticMedia"] else "**No**"
    chapters = json.loads((run / "video/final/chapters.json").read_text())
    ok = (names == want and
          (d / f"{slug}.mp4").read_bytes() == (run / "video/final" / f"{slug}.mp4").read_bytes() and
          "Episode 2 of 2 · Fixture: two episodes of predictive control" in sheet and "## Chapters" in sheet and
          (all(c["label"] in sheet for c in chapters["chapters"]) if chapters["valid"] else "fewer than three" in sheet)
          and f"Altered or synthetic content: {synthetic}" in sheet and "End screen from" in sheet and
          f"Run: {run.name}" not in sheet and "final-cut" in (d / "final_cut_review.md").read_text().lower() and
          entry.exists() and entry.read_bytes() == (d / f"ledger-{run.name}.json").read_bytes() and
          json.loads(entry.read_text())["status"] == "delivered")
    return ok, f"{len(names)} files; synthetic content {synthetic.strip('*')}"


def draft_and_review(run: Path, env: dict, label: str) -> None:
    """Draft renders with layout logs, design and reading-time checks, and the (fixture) video design and linear-viewer
    reviews."""
    step(f"draft renders with layout logs{label}", ["bash", "tools/render_video.sh", str(run), "--check"], env=env,
         check=lambda r: (all((run / "video/checks" / f"{s['class']}.layout.json").exists()
                              for s in json.loads((run / "video/plan.json").read_text())["scenes"]), "layout logged"))
    step(f"design check of the drafts (frames, contact sheet){label}",
         [PY, "tools/video/check_design.py", str(run), "--stage", "draft"],
         check=lambda r: (any((run / "review/design/draft").glob("*-sheet.jpg")), r.stdout.strip()[-110:]))
    step(f"reading-time check of the drafts{label}", [PY, "tools/video/check_reading.py", str(run), "--stage", "draft"])
    (run / "review" / "video").mkdir(parents=True, exist_ok=True)
    for name in ("video-design-reviewer.json", "linear-viewer.json"):
        shutil.copy(FIX / "review" / "video" / name, run / "review/video" / name)
    step(f"video design review and linear viewer merged (fixture reports){label}",
         [PY, "tools/merge_reviews.py", str(run), "--set", "video"],
         check=lambda r: (json.loads((run / "review/video/summary.json").read_text())["scenes_sha256"] is not None,
                          r.stdout.strip()[:110]))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--keep", action="store_true")
    a = ap.parse_args()
    manim = os.environ.get("MANIM") or (str(REPO / ".venv/bin/manim") if (REPO / ".venv/bin/manim").exists()
                                        else shutil.which("manim"))
    missing = [n for n, ok in (("ffmpeg", shutil.which("ffmpeg")), ("manim", manim), ("node", shutil.which("node")))
               if not ok]
    if missing:
        print(f"automation dry run skipped: {', '.join(missing)} not found")
        return 0
    tmp = Path(tempfile.mkdtemp(prefix="explainer-automation-"))
    voice, why = keyless_voice(manim)
    env = {k: v for k, v in os.environ.items() if k not in KEYS and k != "VOICE_SERVICE"}   # no text-to-speech keys
    env = dict(env, CLAUDE_PROJECT_DIR=str(tmp), MANIM=manim, YOUTUBE_BACKEND="fake",
               YOUTUBE_FAKE_STATE=str(tmp / "youtube.json"), LINKEDIN_BACKEND="fake",
               LINKEDIN_FAKE_STATE=str(tmp / "linkedin.json"), SITE_BASE_URL="https://example.org/remaining-action")
    try:
        r = step("new run", [PY, "tools/run.py", "new", *testenv.COVERAGE_ARGS, "--root", str(tmp / "runs"), "--date", "2026-10-30"])
        run = Path(r.stdout.strip())
        for f in ("sources.json", "scores.json"):
            shutil.copy(FIX / f, run / f)
        senv = dict(env, SEARCH_BACKEND="fake", SEARCH_FAKE_DATA=str(REPO / "tests/fixtures/search_fake.json"))
        step("search demand (recorded answers; failed lookups stay unknown)", [PY, "tools/search_demand.py", str(run)],
             env=senv, check=lambda r: (json.loads((run / "search.json").read_text())["topics"]["T2"]["scores"]
                                        ["supply_gap"] is None, r.stdout.strip()[:110]))
        step("rank (with search demand and supply gap)", [PY, "tools/rank_topics.py", str(run)],
             check=lambda r: ("?" in (run / "ranking.md").read_text() and "1. T1" in r.stdout, r.stdout.strip()[:110]))
        step("automatic topic approval (logged)", [PY, "tools/auto_select.py", str(run)],
             check=lambda r: ("selected T1" in r.stdout and (run / "selection.md").exists(), r.stdout.strip()[:110]))
        r = step("finalize", [PY, "tools/run.py", "finalize", str(run)])
        run = Path(r.stdout.strip())
        shutil.copytree(FIX / "draft", run / "draft", dirs_exist_ok=True)
        shutil.copytree(FIX / "code", run / "code", dirs_exist_ok=True)
        shutil.copy(FIX / "references.json", run / "references.json")
        step("code checks", [PY, "tools/run_code_checks.py", str(run)])
        step("build --strict", [PY, "tools/build_explainer.py", str(run), "--strict"])
        cmd = ["node", "tools/check_html.js", str(run / "explainer.html"), "--json", str(run / "review" / "check_html.json")]
        if os.environ.get("KATEX_DIST") or (REPO / "node_modules" / "katex").exists():
            cmd.append("--offline")
        r = step("render check", cmd)
        if r.returncode == 3:
            RESULTS.pop()
            print("automation dry run skipped: Playwright or Chromium not available")
            return 0
        shutil.copytree(FIX / "review", run / "review", dirs_exist_ok=True)
        step("merge reviews", [PY, "tools/merge_reviews.py", str(run)])

        scenes = run / "video" / "scenes"
        for f in ("common.py", "voice.py", "reading_model.py", "scene_template.py"):
            shutil.copy(REPO / "templates" / "manim" / f, scenes / f)
        shutil.copy(FIX / "video" / "plan.json", run / "video" / "plan.json")
        step("render matrix", [PY, "tools/ci/scene_matrix.py", str(run)],
             check=lambda r: (json.loads(r.stdout)[0]["class"] == "TemplateScene", r.stdout.strip()))
        draft_and_review(run, env, "")
        step("gates: pre-render", [PY, "tools/gate.py", str(run), "--stage", "pre-render"])

        step(f"narration synthesized once without any key, scene code parsed not run ({voice}"
             f"{': ' + why if why else ''})",
             [PY, "tools/video/synthesize_voice.py", str(run), *([] if voice == "piper" else ["--service", voice])],
             env=env,
             check=lambda r: (len(json.loads((run / "video/voice/manifest.json").read_text())["blocks"]) == 3 and
                              len(list((run / "video/voice").glob("*.timings.json"))) == 3 and
                              json.loads((run / "video/voice/manifest.json").read_text())["service"] == voice,
                              r.stdout.strip()[:110]))
        fenv = dict(env, VOICE_SERVICE="recorded")
        step("final scene render from the prepared narration (-ql here, 1080p60 in CI)",
             ["bash", "tools/render_video.sh", str(run), "--quality", "l", "--scene", "scene_template.py:TemplateScene"],
             env=fenv, check=lambda r: ((run / "video/renders/TemplateScene.layout.json").exists(), "with layout log"))
        step("design and reading-time checks of the final renders (before assembly)",
             ["bash", "-c", f'"{PY}" tools/video/check_design.py "{run}" --stage final --no-frames && '
                            f'"{PY}" tools/video/check_reading.py "{run}" --stage final'])
        step("assemble (scenes only, no channel card; captions, chapters)",
             [PY, "tools/video/assemble.py", str(run), "--quality", "l"])
        step("thumbnail", [PY, "tools/video/thumbnail.py", str(run)])
        step("thumbnail legible at 168 x 94", [PY, "tools/video/check_design.py", str(run), "--stage", "final",
                                               "--no-frames"],
             check=lambda r: (json.loads((run / "review/design/final/check_design.json").read_text())["thumbnail"]
                              ["elements"][0]["cap_px_small"] >= 7, r.stdout.strip()[:110]))

        def meta_ok(r):
            m = json.loads((run / "video/final/youtube.json").read_text())
            return ("Run: " in m["snippet"]["description"] and CHANNEL["youtube"]["default_tags"][0] in m["snippet"]["tags"]
                    and m["status"]["containsSyntheticMedia"] is True
                    and m["status"]["privacyStatus"] == CHANNEL["youtube"]["review_privacy"]
                    and "Narration: AI voice (" in m["snippet"]["description"], r.stdout.strip()[:110])
        silent = ["--allow-silent"] if voice == "silent" else []
        nolinks = {k: v for k, v in env.items() if k != "SITE_BASE_URL"}     # links off: no site URL needed at all
        step("metadata (links off by default: no site URL needed; synthetic voice declared from the manifest)",
             [PY, "tools/video/metadata.py", str(run)], env=nolinks,
             check=(lambda r: (meta_ok(r)[0] and "/explainers/" not in json.loads(
                 (run / "video/final/youtube.json").read_text())["snippet"]["description"], meta_ok(r)[1]))
             if voice != "silent" else None)
        step("gates: final with --require-links and links off (self-contained video; voice and timings named)",
             [PY, "tools/gate.py", str(run), "--stage", "final", "--require-links", "--video-quality", "l",
              "--min-duration", "10", *silent], env=nolinks,
             check=lambda r: (f"| narration voice | pass | {voice}" in (run / "review/gates.md").read_text() and
                              "self-contained video (final)" in (run / "review/gates.md").read_text(),
                              next((ln for ln in r.stdout.splitlines() if "narration voice" in ln), "")[:110]))
        step("links on without a site URL: metadata refuses", [PY, "tools/video/metadata.py", str(run)],
             env=dict(nolinks, INCLUDE_LINKS="on"), expect=1)
        bad = json.loads((run / "video/final/youtube.json").read_text())
        bad["status"]["privacyStatus"] = "public"
        (run / "video/final/youtube.json").write_text(json.dumps(bad))
        step("gates refuse a public upload", [PY, "tools/gate.py", str(run), "--stage", "final", "--require-links",
                                              "--video-quality", "l", "--min-duration", "10", *silent], expect=1)
        step("metadata again", [PY, "tools/video/metadata.py", str(run)], env=nolinks)
        step("gates: final again (the record the release gate reads)",
             [PY, "tools/gate.py", str(run), "--stage", "final", "--require-links", "--video-quality", "l",
              "--min-duration", "10", *silent], env=nolinks)
        final_cut(run, "")

        site = tmp / "site"
        step("site init", [PY, "tools/publish/site.py", "init", str(site)])
        r = step("stage: private upload (fake YouTube)",
                 [PY, "tools/publish/youtube.py", "stage", str(run), "--ledger", str(site / "ledger.json")], env=env)
        vid = json.loads(r.stdout)["video_id"] if r.returncode == 0 else "none"
        step("stage again: reuses the upload (idempotent)",
             [PY, "tools/publish/youtube.py", "stage", str(run), "--ledger", str(site / "ledger.json")], env=env,
             check=lambda r: (json.loads(r.stdout)["reused"] and
                              sum(c.startswith("videos.insert") for c in json.loads((tmp / "youtube.json").read_text())["calls"]) == 1,
                              f"one videos.insert in total, quota used {json.loads((tmp / 'youtube.json').read_text())['quota']}"))
        step("preview on the site", [PY, "tools/publish/site.py", "preview", str(site), str(run), "--token", "0ff1ce"])
        r = step("staging re-run: the new preview replaces the old one",
                 [PY, "tools/publish/site.py", "preview", str(site), str(run), "--token", "abc123"],
                 check=lambda r: ([d.name for d in (site / "preview").iterdir()] == [f"{run.name}-abc123"],
                                  r.stdout.strip()))
        step("ledger: staged", [PY, "tools/publish/site.py", "mark", str(site), str(run), "--status", "staged",
                                "--video-id", vid])
        step("review package", [PY, "tools/review_package.py", str(run), "--video-id", vid, "--preview-url",
                                f"https://example.org/remaining-action/{r.stdout.strip()}", "--workflow-url",
                                "https://example.org/actions/runs/1", "--token", "abc123", "--source-run-id", "1"],
             check=lambda r: ("pipeline-meta" in (run / "review/package.md").read_text() and
                              f"- Narration: {voice}" in (run / "review/package.md").read_text(),
                              r.stdout.strip()))
        shutil.copy(run / "review/package.md", tmp / "package-api.md")
        step("review package, manual YouTube mode (no upload)",
             [PY, "tools/review_package.py", str(run), "--video-id", "", "--preview-url",
              "https://example.org/remaining-action/preview/x/", "--workflow-url", "https://example.org/actions/runs/1",
              "--token", "abc123", "--source-run-id", "1"],
             check=lambda r: ("run-final" in (run / "review/package.md").read_text() and
                              "youtu.be" not in (run / "review/package.md").read_text(), "points to the artifact"))
        shutil.copy(tmp / "package-api.md", run / "review/package.md")
        step("publish (fake YouTube): video public", [PY, "tools/publish/youtube.py", "publish", "--video-id", vid,
                                                       "--mode", "public"], env=env,
             check=lambda r: (json.loads(r.stdout)["privacy"] == "public", r.stdout.strip()))
        step("promote the explainer", [PY, "tools/publish/site.py", "promote", str(site), str(run), "--token", "abc123",
                                       "--video-id", vid],
             check=lambda r: ((site / "explainers/fixture-descent-certificate/index.html").exists() and
                              not (site / "preview" / f"{run.name}-abc123").exists() and
                              'noindex' not in (site / "explainers/fixture-descent-certificate/index.html").read_text() and
                              f"youtu.be/{vid}" in (site / "explainers/fixture-descent-certificate/index.html").read_text(),
                              "explainer, code/ and code.zip published; preview removed"))
        step("LinkedIn post (fake)", [PY, "tools/publish/linkedin.py", "post", str(run), "--video-url",
                                      f"https://youtu.be/{vid}", "--explainer-url",
                                      "https://example.org/remaining-action/explainers/fixture-descent-certificate/"],
             env=env)
        step("publish again: no change", [PY, "tools/publish/youtube.py", "publish", "--video-id", vid], env=env,
             check=lambda r: (json.loads(r.stdout)["changed"] is False, r.stdout.strip()))
        lenv = dict(env, YOUTUBE_FAKE_STATE=str(tmp / "youtube_locked.json"), YOUTUBE_FAKE_LOCKED="1")
        r2 = step("unaudited API project: upload", [PY, "tools/publish/youtube.py", "stage", str(run)], env=lenv)
        vid2 = json.loads(r2.stdout)["video_id"] if r2.returncode == 0 else "none"
        step("unaudited API project: publish is refused with the reason", [PY, "tools/publish/youtube.py", "publish",
                                                                           "--video-id", vid2, "--mode", "public"],
             env=lenv, expect=1, check=lambda r: ("audit" in r.stderr, r.stderr.strip()[:110]))
        step("wrong channel is refused", [PY, "tools/publish/youtube.py", "whoami"],
             env=dict(env, YOUTUBE_FAKE_STATE=str(tmp / "other.json"), YOUTUBE_FAKE_CHANNEL="Someone Else"), expect=1)

        r = step("second run", [PY, "tools/run.py", "new", *testenv.COVERAGE_ARGS, "--root", str(tmp / "runs"), "--date", "2026-11-06"])
        run2 = Path(r.stdout.strip())
        for f in ("sources.json", "scores.json"):
            shutil.copy(FIX / f, run2 / f)
        shutil.copy(site / "ledger.json", run2 / "published.json")
        step("rank (second run)", [PY, "tools/rank_topics.py", str(run2)])
        step("selection skips the published topic", [PY, "tools/auto_select.py", str(run2)],
             check=lambda r: ("selected T2" in r.stdout and "already published" in (run2 / "selection.md").read_text(),
                              r.stdout.strip()[:110]))
        step("finalize (second run)", [PY, "tools/run.py", "finalize", str(run2)])
        run2 = tmp / "runs" / "2026-11-06-fixture-contact-benchmark"
        shutil.copytree(FIX / "video", run2 / "video", dirs_exist_ok=True)
        step("rejection is archived with the reason", [PY, "tools/publish/site.py", "mark", str(site), str(run2),
                                                       "--status", "rejected", "--reason", "fixture: narration too fast",
                                                       "--by", "reviewer"],
             check=lambda r: ((site / "archive" / f"{run2.name}.json").exists(), r.stdout.strip()))
        series_flow(tmp, env, site, manim, voice)
        led = json.loads((site / "ledger.json").read_text())
        led["runs"] = {k: v for k, v in led["runs"].items() if not v.get("series")}
        RESULTS.append(("ledger records published and rejected runs",
                        "ok" if {e["status"] for e in led["runs"].values()} == {"published", "rejected"} else "FAIL",
                        ", ".join(f"{k}: {v['status']}" for k, v in led["runs"].items())))
        return report(tmp, a.keep)
    finally:
        if not a.keep:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
