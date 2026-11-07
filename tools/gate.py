#!/usr/bin/env python3
"""Hard gates of a run, recorded in review/gates.json and gates.md; exit 1 when one fails.

Usage:
  python3 tools/gate.py runs/<run> --stage pre-render   # explainer, code, review, references, plan, narration, drafts
  python3 tools/gate.py runs/<run> --stage final        # the above, then video, captions, thumbnail, metadata
  python3 tools/gate.py runs/<run> --stage release      # the final gates passed for this video; final-cut review
  options: --require-links; tests only: --allow-silent, --video-quality l|m|h|k, --video-fps N, --min-duration S
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tomllib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent / "video"))
from _common import CONFIG, REPO, load_json, read_json, rel, resolve_run, sha256_file, utc_now, write_json  # noqa: E402
import lint_html  # noqa: E402
import plan as P  # noqa: E402
import voice_script as VS  # noqa: E402

REVIEWERS = ("technical-correctness-reviewer", "reference-verifier", "presentation-reviewer", "claims-red-team",
             "linear-reader")
PRESETS = {"l": (854, 480, 15), "m": (1280, 720, 30), "h": (1920, 1080, 60), "k": (3840, 2160, 60)}
MEDIA_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".mp4", ".mov", ".webm", ".svg"}
AUDIO_SUFFIXES = {".mp3", ".wav", ".m4a", ".flac", ".ogg", ".aac", ".opus"}


class Gates:
    def __init__(self):
        self.checks: list[dict] = []

    def add(self, name: str, ok: bool, detail: str):
        self.checks.append({"name": name, "ok": bool(ok), "detail": detail})

    def guard(self, name: str, fn):
        try:
            ok, detail = fn()
        except FileNotFoundError as exc:
            ok, detail = False, f"missing: {exc.filename or exc}"
        except (KeyError, ValueError, json.JSONDecodeError) as exc:
            ok, detail = False, f"unreadable input: {exc}"
        self.add(name, ok, detail)


def _json_or_empty(p: Path) -> dict:
    try:
        return read_json(p)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def open_serious(findings: list, unverified: list) -> tuple[list, list, list]:
    """Open blockers, open confirmed majors, and the blockers among `unverified`."""
    open_ = [f for f in findings if f.get("status", "open") == "open" and f.get("verdict") != "refuted"]
    blockers = {f["id"] for f in findings if f["severity"] == "blocker"}
    return ([f["id"] for f in open_ if f["severity"] == "blocker"],
            [f["id"] for f in open_ if f["severity"] == "major" and f.get("verdict") == "confirmed"],
            [i for i in unverified if i in blockers])


def video_checks(run: Path, g: Gates, stage: str) -> None:
    """The video checks' reports for `stage` (draft or final renders), tied to the logs and files they read."""
    folder = run / "video" / ("checks" if stage == "draft" else "renders")
    reports = run / "review" / "design" / stage
    names = [s["class"] for s in P.load(run)["scenes"]]
    video_cfg = _json_or_empty(CONFIG / "video.json")

    def stale(have, strict: bool = True) -> list[str]:
        """Scenes whose layout log is not the one the report read (strict: a missing log too)."""
        out = []
        for n in names:
            lp = folder / f"{n}.layout.json"
            now = sha256_file(lp) if lp.exists() else None
            if have(n) != now or (strict and now is None):
                out.append(n)
        return out

    def layout_report(tool, have):
        def check():
            r = read_json(reports / f"{tool}.json")
            st = stale(lambda n: have(r, n))
            ok = r.get("passed") is True and not st
            return ok, (f"{r['summary']['warnings']} warning(s), no error" if ok else
                        f"{r['summary']['errors']} error(s) (review/design/{stage}/{tool}.md)" if not st else
                        f"not run on the current {stage} renders of {st}")
        return check
    g.guard(f"video design ({stage} renders)",
            layout_report("check_design", lambda r, n: (r.get("scenes", {}).get(n, {}) or {}).get("layout_sha256")))
    g.guard(f"reading time ({stage} renders)",
            layout_report("check_reading", lambda r, n: (r.get("layout_sha256") or {}).get(n)))

    def self_contained():
        import check_selfcontained as SC
        found = SC.check(run, stage)
        return (not found), ("no reference to the explainer, code, files or links; no equation labels; on screen, in "
                             "narration, captions and chapters" if not found else
                             f"{len(found)} finding(s): " + "; ".join(SC.describe(f) for f in found[:3])
                             + (" ..." if len(found) > 3 else "") + " (check_selfcontained.py)")
    g.guard(f"self-contained video ({stage})", self_contained)

    def numbers():
        import check_numbers as CN
        fd = CN.Findings()
        CN.check_run(run, stage, CN.settings(), fd)
        errs = [f for f in fd.items if f["severity"] == "error"]
        warns = [f for f in fd.items if f["severity"] == "warning"]
        return (not errs), (f"{len(warns)} warning(s), no error" if not errs else f"{len(errs)} error(s): " + "; ".join(
            f"{f['where']} {f['rule']} '{f['match']}'" for f in errs[:3]) + " (check_numbers.py)")
    g.guard(f"number format ({stage})", numbers)

    def structure():
        import check_series as CS
        items, info = CS.check(run, stage, CS.settings())
        return True, (f"{len(items)} warning(s)" + (": " + "; ".join(f"{x['check']}: {x['detail']}" for x in items[:2])
                                                    if items else "") + (" ..." if len(items) > 2 else "")
                      + " (check_series.py; warnings only)")
    g.guard(f"opening, ending and series beats ({stage})", structure)

    def measured(tool, section, not_run, stale_of, what, detail_of):
        """A report that blocks only when config/video.json <section>.errors_block_gate is true."""
        def check():
            p = reports / f"{tool}.json"
            block = bool(video_cfg.get(section, {}).get("errors_block_gate", False))
            if not p.exists():
                return not block, f"not run (tools/video/{tool}.py {rel(run)} --stage {stage}; {not_run})"
            r = read_json(p)
            st = stale_of(r)
            errs, warns = r["summary"]["errors"], r["summary"]["warnings"]
            detail = (f"{errs} error(s), {warns} warning(s); {detail_of(r)} (review/design/{stage}/{tool}.md"
                      + ("" if block else f"; reported, not blocking: {section}.errors_block_gate") + ")")
            if st:
                detail = f"not run on the current {what} {st[:3]}; " + detail
            return (not block) or (not errs and not st), detail
        return check

    def by_layout(r):
        return stale(lambda n: (r.get("layout_sha256") or {}).get(n), strict=False)

    def by_scene_files(r):
        now = {f.name: sha256_file(f) for f in sorted((run / "video" / "scenes").glob("*.py"))
               if f.name not in ("common.py", "voice.py", "reading_model.py")}
        had = r.get("scene_sha256") or {}
        return sorted(n for n in set(now) | set(had) if had.get(n) != now.get(n))

    def engagement_detail(r):
        st = r.get("stats", {})
        return (f"moving {st.get('moving_share', '-')}, longest frozen narration "
                f"{st.get('longest_frozen_narrated_s', '-')} s, FadeIn/transforms {st.get('fade_in')}/"
                f"{st.get('transforms')}")

    def script_detail(r):
        st = (r.get("stats") or {}).get("whole", {})
        au = (r.get("stats") or {}).get("audio") or {}
        return (f"pause marks {st.get('pause_punct_per_100', '-')}, contractions "
                f"{st.get('contractions_per_100', '-')}, connectives {st.get('connectives_per_100', '-')} per 100 words"
                + (f"; {au.get('wpm')} wpm, {au.get('mid_pauses')} mid-sentence pause(s)" if au else ""))

    def pacing_detail(r):
        st = r.get("stats", {})
        return (f"longest stretch without a pause {st.get('longest_stretch_s', '-')} s, pauses "
                f"{st.get('pause_share', '-')} of the body, declared ideas {st.get('declared') or 'none'}")
    g.guard(f"engagement: motion, transforms, narration, text ({stage})",
            measured("check_engagement", "engagement", "warnings only", by_layout, f"{stage} renders of",
                     engagement_detail))
    g.guard(f"spoken script: pauses, rhythm, contractions, stock phrases ({stage})",
            measured("check_script", "script", "report only", by_scene_files, "scene files", script_detail))
    g.guard(f"pacing: ideas per minute, pauses, holds (rules P1-P20; {stage})",
            measured("check_pacing", "pacing", "reported, not blocking unless pacing.errors_block_gate", by_layout,
                     f"{stage} renders of", pacing_detail))


def scene_urls(run: Path) -> list[str]:
    """Scene files that hold a URL or load an image from outside code/figures/ and data/."""
    bad = []
    for p in sorted((run / "video" / "scenes").glob("*.py")):
        helper = REPO / "templates" / "manim" / p.name
        if helper.is_file() and helper.read_bytes() == p.read_bytes():   # voice.py's SSML namespaces fetch nothing
            continue
        src = p.read_text(encoding="utf-8")
        if re.search(r"https?://", src):
            bad.append(f"{p.name}: URL in scene code")
        for m in re.finditer(r"(ImageMobject|SVGMobject)\(\s*['\"]([^'\"]+)", src):
            if not re.match(r"^(\.\./)*(code/figures|data)/", m.group(2)):
                bad.append(f"{p.name}: {m.group(1)} loads {m.group(2)}")
    return bad


def pre_render(run: Path, g: Gates, cfg: dict):
    html = run / "explainer.html"
    html_sha = sha256_file(html) if html.exists() else None
    series = P.is_series(run)

    def explainer_gate(name, fn):              # a series reuses its published, reviewed explainer unchanged
        if not series:
            g.guard(name, fn)

    def episode():
        e = read_json(run / "episode.json")
        same = e.get("explainer_sha256") == html_sha
        return same, (f"episode {e['episode']} of {e['series']}: {e['title']}" + ("" if same else
                      "; explainer.html differs from the series' explainer (it must be copied unchanged)"))

    def topic():
        mode = load_json(CONFIG / "pipeline.json").get("topic_approval", "auto")
        name = "selection.json" if mode == "auto" else "approval.json"
        t = read_json(run / name)
        ok = t.get("ranking_sha256") == sha256_file(run / "ranking.md")
        return ok, f"{name}: {t['topic_id']} {t['title']}" + ("" if ok else " (ranking changed after the selection)")
    g.guard("topic approved" if not series else "series episode chosen (explainer unchanged)",
            topic if not series else episode)

    def plan_approved():
        import series as S
        e = read_json(run / "episode.json")
        sp = REPO / "series" / e["series"] / "series.json"
        if sp.exists():                                   # re-check against the plan in this checkout
            st = S.approval_state(sp, read_json(sp), require=bool((e.get("plan_approval") or {}).get("required")))
            same = S.plan_hash(read_json(sp)) == e.get("plan_sha256")
            ok = (st["approved"] or not st["required"]) and same
            return ok, st["detail"] + ("" if same else "; the plan changed since this episode was started")
        pa = e.get("plan_approval") or {}
        return bool(pa.get("approved") or not pa.get("required", True)), pa.get("detail", "no record")
    if series:
        import series as S
        required = S.approval_setting() == "required" or bool((_json_or_empty(run / "episode.json").get("plan_approval")
                                                                or {}).get("required"))
        g.guard("series plan approved by the owner" if required else "series plan (owner approval optional)",
                plan_approved)

    def lint():
        errs = [i for i in lint_html.lint(html, run, strict=True) if i["level"] == "error"]
        return not errs, "strict lint clean" if not errs else "; ".join(e["message"] for e in errs[:3])
    explainer_gate("explainer strict lint", lint)

    def render_check():
        r = read_json(run / "review" / "check_html.json")
        same = r.get("sha256") == html_sha
        return r.get("pass") is True and same, ("passed" if r.get("pass") else f"{len(r.get('errors', []))} error(s)") \
            + ("" if same else "; the check was run on a different explainer.html")
    explainer_gate("render check (KaTeX, anchors, TOC, 390 px)", render_check)

    def code_checks():
        s = read_json(run / "code" / "logs" / "summary.json")
        bad = [c["script"] for c in s["checks"] if not c.get("ok")]
        stale = [c["script"] for c in s["checks"] if c.get("sha256") != sha256_file(run / "code" / c["script"])]
        if s.get("manifest_sha256") != sha256_file(run / "code" / "checks.toml"):
            stale.append("checks.toml")
        listed = tomllib.loads((run / "code" / "checks.toml").read_text(encoding="utf-8")).get("check", [])
        unrun = [c.get("script") for c in listed if c.get("script") not in {x["script"] for x in s["checks"]}]
        ok = not bad and not stale and not unrun and bool(s["checks"])
        return ok, (f"{len(s['checks'])} script(s) passed" if ok else
                    f"failing: {bad}; changed since the run: {stale}" + (f"; not run: {unrun}" if unrun else ""))
    g.guard("companion code checks", code_checks)

    def figures():
        man = tomllib.loads((run / "code" / "checks.toml").read_text(encoding="utf-8"))
        produced = {f for c in man.get("check", []) for f in c.get("produces", [])}
        figs = [f"figures/{p.name}" for p in sorted((run / "code" / "figures").glob("*")) if p.is_file()]
        orphans = [f for f in figs if f not in produced]
        return not orphans, f"{len(figs)} figure(s), each produced by a listed script" if not orphans else \
            f"figures not produced by any script in checks.toml: {orphans}"
    explainer_gate("figure provenance (original figures only)", figures)

    def review_complete():
        missing = [r for r in REVIEWERS if not (run / "review" / f"{r}.json").exists()]
        s = read_json(run / "review" / "summary.json")
        current = s.get("explainer_sha256") == html_sha
        ok = not missing and current
        return ok, (f"{len(REVIEWERS)} reviewer reports merged against the final explainer" if ok else
                    f"missing reports: {missing}" if missing else "summary.json was merged for another explainer.html")
    explainer_gate("independent review complete", review_complete)

    def blockers():
        s = read_json(run / "review" / "summary.json")
        blk, maj, _ = open_serious(s["findings"], [])
        unverified = s.get("unverified_blocker_major", [])
        ok = len(blk) <= cfg.get("max_open_blocker", 0) and len(maj) <= cfg.get("max_open_confirmed_major", 0) \
            and not unverified
        return ok, (f"open blockers {blk or 'none'}, open confirmed majors {maj or 'none'}, "
                    f"serious findings never verified {unverified or 'none'}")
    explainer_gate("review findings (blocker/major)", blockers)

    def references():
        refs = read_json(run / "references.json")["references"]
        allowed = set(cfg.get("allowed_reference_status", ["verified", "secondary_only"]))
        bad = [r["key"] for r in refs if r.get("verification", {}).get("status") not in allowed]
        has_report = (run / "review" / "reference-verifier.json").exists()
        ok = not bad and (has_report or not cfg.get("require_reference_verifier_report", True))
        return ok, (f"{len(refs)} reference(s) verified or marked secondary-only; reference-verifier report present"
                    if ok else f"not verified: {bad}" if bad else "reference-verifier report missing")
    explainer_gate("reference verification", references)

    def attribution():
        text = html.read_text(encoding="utf-8")
        ok = 'id="attribution"' in text and 'id="sec-references"' in text
        return ok, "attribution statement and references present" if ok else "attribution or references missing"
    explainer_gate("attribution", attribution)

    def media():
        """Images and footage in scenes and data fail; audio there needs the music generator's stamp beside it."""
        import music as MU
        bad = []
        for sub in ("scenes", "data"):
            d = run / "video" / sub
            for p in (d.rglob("*") if d.exists() else []):
                if not p.is_file():
                    continue
                if p.suffix.lower() in MEDIA_SUFFIXES:
                    bad.append(rel(p))
                elif p.suffix.lower() in AUDIO_SUFFIXES:
                    st = _json_or_empty(p.with_name(p.name + ".json")) or _json_or_empty(p.with_suffix(".json"))
                    if st.get("generator") != MU.GENERATOR or st.get("sha256") != sha256_file(p):
                        bad.append(f"{rel(p)} (audio without a generator stamp)")
        bad += scene_urls(run)
        return not bad, ("only our renders, data, recordings and generated sound" if not bad else
                         f"unlicensed third-party media risk: {bad[:5]}")
    g.guard("no unlicensed third-party media in the video", media)

    def video_plan():
        issues = P.problems(run)
        return not issues, "plan.json valid" if not issues else "; ".join(issues[:4])
    g.guard("video plan", video_plan)

    def narration():
        n, bad = 0, []
        for p in sorted((run / "video" / "scenes").glob("*.py")):
            if p.name in ("common.py", "voice.py"):
                continue
            for key, text in VS.blocks(p):
                n += 1
                if key is None:
                    bad.append(f"{p.name}: {text}")
        ok = n > 0 and not bad
        return ok, (f"{n} voiceover block(s), all literal text (CI synthesizes them without running the scenes)"
                    if ok else "; ".join(bad[:3]) or "no voiceover block: the video would have no narration")
    g.guard("narration script", narration)

    def drafts():
        r = read_json(run / "video" / "checks" / "check.json")
        names = {v["file"] for v in r.get("videos", [])}
        need = {f"{s['class']}_ql.mp4" for s in P.load(run)["scenes"]}
        ok = r.get("pass") is True and need <= names
        return ok, "every planned scene rendered at -ql" if ok else f"draft renders missing or failing: {sorted(need - names)}"
    g.guard("draft renders of every scene", drafts)
    video_checks(run, g, "draft")

    def design_review():
        import merge_reviews
        s = read_json(run / "review" / "video" / "summary.json")
        current = s.get("scenes_sha256") == merge_reviews.scenes_sha256(run)
        has = any(r["reviewer"] == "video-design-reviewer" for r in s.get("reviewers", []))
        open_blk, _, unverified = open_serious(s.get("findings", []), s.get("unverified_blocker_major", []))
        ok = has and current and not open_blk and not unverified
        return ok, ("video-design-reviewer report merged for the current scenes; open blockers none" if ok else
                    "no video-design-reviewer report" if not has else
                    "reviewed scenes or plan changed since (merge_reviews.py --set video)" if not current else
                    f"open blockers {open_blk or 'none'}, blockers never verified {unverified or 'none'}")
    g.guard("video design review (blockers)", design_review)


def final(run: Path, g: Gates, cfg: dict, channel: dict, require_links: bool, allow_silent: bool,
          overrides: dict | None = None):
    vid_cfg = dict(channel.get("video", {}), **{k: v for k, v in (overrides or {}).items() if v is not None})
    asm_p = run / "video" / "final" / "assembly.json"

    def video():
        asm = read_json(asm_p)
        w, h, fps = PRESETS[vid_cfg.get("quality", "h")]
        fps = vid_cfg.get("fps") or fps
        path = P.final_video(run)
        out = subprocess.run([sys.executable, str(Path(__file__).parent / "check_video.py"), str(path), "--quality",
                              vid_cfg.get("quality", "h"), "--fps", str(fps),
                              "--min-duration", str(vid_cfg.get("min_duration_s", 45)),
                              "--max-duration", str(vid_cfg.get("max_duration_s", 1200)), "--json",
                              str(run / "video" / "final" / "check.json")], capture_output=True, text=True)
        kinds = [s["kind"] for s in asm["segments"]]
        hook_first = bool(kinds) and all(k == "scene" for k in kinds)
        ok = out.returncode == 0 and hook_first
        return ok, (f"{w}x{h} at {fps} fps, {asm['duration']:.0f} s, opens with the hook (no channel card)" if ok else
                    (out.stdout.strip().splitlines() or ["check failed"])[-1]
                    + ("" if hook_first else "; a card segment before or after the scenes (assemble again)"))
    g.guard("final video (size, frame rate, length, no channel card)", video)

    def narration():
        # measured on the narration stem: under a music bed a silent narration would pass on the mix
        stem = run / "video" / "final" / "narration.wav"
        asm = read_json(asm_p)
        music = ((asm.get("audio") or {}).get("music") or {}).get("used", False)
        src = stem if stem.exists() else (None if music else P.final_video(run))
        if src is None:
            return False, "music in the mix but no narration stem (video/final/narration.wav): assemble again"
        p = subprocess.run(["ffmpeg", "-v", "info", "-i", str(src), "-map", "0:a:0", "-af", "volumedetect", "-f", "null",
                            "-"], capture_output=True, text=True)
        m = re.search(r"max_volume:\s*(-?[\d.]+|-inf) dB", p.stderr)
        level = float(m.group(1)) if m and m.group(1) != "-inf" else -200.0
        ok = level > -50 or allow_silent
        what = "narration stem" if src == stem else "audio (no stem: an older assembly without music)"
        return ok, f"{what} peak {level:.1f} dB" + ("" if level > -50 else " (silent: a draft voice reached the final"
                                                    + (", allowed for this test)" if allow_silent else ")"))
    g.guard("narration present", narration)

    def music_provenance():
        import music as MU
        asm = read_json(asm_p)
        info = (asm.get("audio") or {}).get("music") or {"used": False}
        final_dir = run / "video" / "final"
        if not info.get("used"):
            stray = [n for n in ("music.wav", "stings.wav", "music.json") if (final_dir / n).exists()]
            return not stray, ("no music in the mix (narration only)" if not stray else
                               f"no music recorded in assembly.json, yet {stray} exist: assemble again")
        if info.get("source") != "generated":
            return False, f"music source {info.get('source')!r}: only original, generated music is allowed (route A)"
        errs = MU.verify(final_dir)
        stamp = _json_or_empty(final_dir / "music.json")
        if stamp.get("sha256") != info.get("sha256"):
            errs.append("assembly.json mixed another music.wav than the stamped one")
        return not errs, ("original, generated: " + f"{stamp.get('generator')} {stamp.get('tool_version')}, preset "
                          f"{stamp.get('preset')}, seed {stamp.get('seed')}, sha256 {str(stamp.get('sha256'))[:12]}..."
                          if not errs else "; ".join(errs))
    g.guard("music provenance (original sound only)", music_provenance)

    def music_under_voice():
        asm = read_json(asm_p)
        info = (asm.get("audio") or {}).get("music") or {"used": False}
        if not info.get("used"):
            return True, "no music in the mix"
        limit = float(info.get("under_voice_limit_db", (channel.get("music") or {}).get("music_under_voice_max_lu",
                                                                                         -12.0)))
        v = info.get("under_voice_max_db")
        if v is None:
            return allow_silent, ("not measured (an assembly older than the measurement, or a silent voice): "
                                  "assemble again" + ("; not enforced (--allow-silent, tests only)" if allow_silent
                                                      else ""))
        return v <= limit, (f"loudest music while the voice speaks: {v:+.1f} dB relative to the voice (at most "
                            f"{limit:+g}); stings at {[s['t'] for s in info.get('stings', [])]} s")
    g.guard("music under the narration", music_under_voice)

    def loudness():
        import assemble as AS
        asm = read_json(asm_p)
        a = asm.get("audio") or {}
        target = float(channel.get("video", {}).get("loudness_lufs", -14))
        ceiling = float((channel.get("music") or {}).get("true_peak_dbtp", -1.0))
        m = AS.loudness(P.final_video(run))
        ok = (abs(m["integrated_lufs"] - target) <= 1.0 and m["true_peak_dbtp"] <= ceiling + 0.05) or allow_silent
        return ok, (f"{m['integrated_lufs']:.1f} LUFS integrated (target {target:g} ± 1), true peak "
                    f"{m['true_peak_dbtp']:.1f} dBTP (ceiling {ceiling:g}, after AAC encoding), LRA {m['lra_lu']:.1f} LU"
                    + ("" if a else "; assembly.json has no audio record (an older assembly)")
                    + ("; not enforced (--allow-silent, tests only)" if allow_silent else ""))
    g.guard("loudness and true peak", loudness)

    def voice_source():
        man = run / "video" / "voice" / "manifest.json"
        if not man.exists():
            return True, "no narration manifest (rendered with a live speech service)"
        m = read_json(man)
        blocks = ", ".join(f"{k} {v}" for k, v in (m.get("sources") or {}).items()) or m.get("service", "?")
        model = f" ({m['voice_model']})" if m.get("voice_model") else ""
        return True, f"{m.get('service')}{model}; blocks: {blocks}; word timings {m.get('timings', 'unknown')}"
    g.guard("narration voice", voice_source)

    def captions():
        srt = P.final_video(run).with_suffix(".srt")
        asm = read_json(asm_p)
        text = srt.read_text(encoding="utf-8")
        times = re.findall(r"(\d\d):(\d\d):(\d\d),(\d{3}) --> (\d\d):(\d\d):(\d\d),(\d{3})", text)
        secs = [(int(a) * 3600 + int(b) * 60 + int(c) + int(d) / 1000, int(e) * 3600 + int(f) * 60 + int(g_) + int(h) / 1000)
                for a, b, c, d, e, f, g_, h in times]
        ordered = all(s0 <= s1 for (s0, _), (s1, _) in zip(secs, secs[1:])) and all(a < b for a, b in secs)
        inside = all(b <= asm["duration"] + 0.5 for _, b in secs)
        ok = bool(secs) and ordered and inside
        return ok, f"{len(secs)} cues, ordered, inside the video" if ok else "captions empty, unordered or past the end"
    g.guard("captions", captions)

    def chapters():
        c = read_json(run / "video" / "final" / "chapters.json")
        ok = c.get("valid") or not cfg.get("require_chapters", False)
        return ok, (f"{len(c['chapters'])} chapters" + ("" if c.get("valid") else
                    " (fewer than 3: none in the description; not required)"))
    g.guard("chapters", chapters)

    def thumbnail():
        from PIL import Image
        p = run / "video" / "final" / "thumbnail.jpg"
        size = p.stat().st_size
        with Image.open(p) as im:
            dims, fmt = im.size, im.format
        ok = dims == (1280, 720) and fmt in ("JPEG", "PNG") and size < cfg.get("max_thumbnail_bytes", 2_000_000)
        return ok, f"{dims[0]}x{dims[1]} {fmt}, {size / 1e3:.0f} kB"
    g.guard("thumbnail", thumbnail)
    video_checks(run, g, "final")

    def metadata():
        m = read_json(run / "video" / "final" / "youtube.json")
        s, st = m["snippet"], m["status"]
        errs = []
        if not (0 < len(s["title"]) <= 100):
            errs.append("title length")
        if len(s["description"].encode("utf-8")) > 5000:
            errs.append("description over 5,000 bytes")
        if re.search(r"[<>]", s["title"] + s["description"] + "".join(s["tags"])):
            errs.append("angle brackets")
        if len(",".join(f'"{t}"' if " " in t else t for t in s["tags"])) > 500:
            errs.append("tags over 500 characters")
        if m["marker"] not in s["description"]:
            errs.append("run marker missing")
        if st["privacyStatus"] not in ("private", "unlisted"):
            errs.append("upload privacy must be private or unlisted (review first)")
        links = m.get("links", {"included": bool(m.get("explainer_url"))})
        if links.get("included"):
            if require_links and not m.get("explainer_url"):
                errs.append("links are on for this run but there is no explainer link (set SITE_BASE_URL)")
            elif m.get("explainer_url") and m["explainer_url"] not in s["description"]:
                errs.append("the explainer link is missing from the description")
        else:
            site = os.environ.get("SITE_BASE_URL", "").rstrip("/")
            if "/explainers/" in s["description"] or (site and site in s["description"]) or m.get("explainer_url") \
                    or re.search(r"(?im)^(explainer|code) .*https?://", s["description"]):
                errs.append("links are off for this run, but the description links the explainer, code or site")
        state = "links in the description" if links.get("included") else "no links (links off)"
        return not errs, f"title, description, tags and privacy valid; {state}" if not errs else "; ".join(errs)
    g.guard("YouTube metadata", metadata)


def release(run: Path, g: Gates, cfg: dict):
    vid = P.final_video(run)
    vsha = sha256_file(vid) if vid.exists() else None

    def final_passed():
        r = read_json(run / "review" / "gates.json")
        ok = r.get("final_passed", r.get("stage") == "final" and r.get("passed")) is True and \
            r.get("video_sha256") == vsha
        return ok, ("final gates passed for this video" if ok else
                    "run tools/gate.py --stage final on this video first" if r.get("video_sha256") != vsha else
                    "the final gates did not pass")
    g.guard("final gates passed for this video", final_passed)

    def final_cut():
        need = load_json(CONFIG / "pipeline.json").get("series", {}).get("final_cut_review", "required") == "required"
        p = run / "review" / "final_cut" / "summary.json"
        if not p.exists():
            return (not need), ("no final-cut review (tools/video/final_frames.py, then the final-cut-review skill)"
                                + ("" if need else "; optional in config/pipeline.json"))
        s = read_json(p)
        blk, maj, unverified = open_serious(s["findings"], s.get("unverified_blocker_major", []))
        fresh = s.get("video_sha256") == vsha
        indep = s.get("independent", True)
        ok = fresh and not blk and len(maj) <= cfg.get("max_open_confirmed_major", 0) and not unverified
        detail = ("NOT INDEPENDENT (reviewed by the session that made the video); " if not indep else "independent; ")
        detail += (f"{len(s['findings'])} finding(s), open blockers {blk or 'none'}, open confirmed majors "
                   f"{maj or 'none'}, blockers never verified {unverified or 'none'}" if fresh else
                   "the review watched another version of the video: review the current one")
        return ok, detail
    g.guard("final-cut review (the assembled video, watched)", final_cut)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run")
    ap.add_argument("--stage", choices=["pre-render", "final", "release"], required=True)
    ap.add_argument("--require-links", action="store_true",
                    help="with links on, the description must carry them (with links off it never may)")
    ap.add_argument("--allow-silent", action="store_true", help="tests only")
    ap.add_argument("--video-quality", choices=sorted(PRESETS), help="override config/channel.json (tests, drafts)")
    ap.add_argument("--video-fps", type=int, help="override the frame rate of the quality preset")
    ap.add_argument("--min-duration", type=float, help="override config/channel.json (tests)")
    a = ap.parse_args()
    run = resolve_run(a.run)
    cfg = load_json(CONFIG / "pipeline.json").get("gates", {})
    channel = load_json(CONFIG / "channel.json")
    g = Gates()
    if a.stage == "release":
        release(run, g, cfg)
    else:
        pre_render(run, g, cfg)
    if a.stage == "final":
        final(run, g, cfg, channel, a.require_links, a.allow_silent,
              {"quality": a.video_quality, "fps": a.video_fps, "min_duration_s": a.min_duration})
    passed = all(c["ok"] for c in g.checks)
    vid = P.final_video(run) if a.stage != "pre-render" else None
    record = {"schema_version": 1, "stage": a.stage, "checked_at": utc_now(), "passed": passed, "checks": g.checks}
    if vid is not None and vid.exists():
        record["video_sha256"] = sha256_file(vid)
    if a.stage == "final":
        record["final_passed"] = passed
    if a.stage == "release":                 # keep the final result next to the release checks
        try:
            prev = read_json(run / "review" / "gates.json")
            record["final_passed"] = prev.get("final_passed", prev.get("stage") == "final" and prev.get("passed"))
            record["final_checks"] = prev.get("checks", []) if prev.get("stage") == "final" else prev.get("final_checks", [])
        except (FileNotFoundError, json.JSONDecodeError):
            pass
    write_json(run / "review" / "gates.json", record)
    md = [f"# Gates ({a.stage}): {'PASSED' if passed else 'FAILED'}", "", "| Gate | Result | Detail |", "|---|---|---|"]
    md += [f"| {c['name']} | {'pass' if c['ok'] else 'FAIL'} | {c['detail'].replace('|', '/')} |" for c in g.checks]
    (run / "review" / "gates.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    for c in g.checks:
        print(f"{'pass' if c['ok'] else 'FAIL'}  {c['name']}: {c['detail']}")
    print(f"gates ({a.stage}): {'PASSED' if passed else 'FAILED'}; {rel(run / 'review' / 'gates.md')}")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
