#!/usr/bin/env python3
"""The hand-over package of a finished video for the owner's own upload: runs/<run>/deliver/ with SHA256SUMS.

Usage:
  python3 tools/deliver.py runs/<run> [--out DIR]   # needs a passed release gate for the current final video
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent / "video"))
from _common import CONFIG, REPO, load_json, read_json, rel, resolve_run, sha256_file, utc_now  # noqa: E402
import plan as P  # noqa: E402
import review_package as RP  # noqa: E402

CATEGORIES = {"1": "Film & Animation", "10": "Music", "22": "People & Blogs", "24": "Entertainment",
              "25": "News & Politics", "26": "Howto & Style", "27": "Education", "28": "Science & Technology"}
LICENCES = {"youtube": "Standard YouTube License", "creativeCommon": "Creative Commons - Attribution"}
SERIES = REPO / "series"                       # tests point it elsewhere


class NotReady(Exception):
    pass


def release_record(run: Path, video: Path) -> dict:
    """review/gates.json of a passed release gate for this very video, or NotReady with what to do."""
    gp = run / "review" / "gates.json"
    if not video.exists():
        raise NotReady(f"{rel(video)} missing: render and assemble the video first")
    if not gp.exists():
        raise NotReady("no review/gates.json: run tools/gate.py --stage final, the final-cut review and "
                       "tools/gate.py --stage release first")
    g = read_json(gp)
    if g.get("stage") != "release":
        raise NotReady(f"the last gate run was --stage {g.get('stage')}: run the final-cut review and "
                       "tools/gate.py --stage release first")
    if g.get("passed") is not True:
        raise NotReady("the release gate did not pass: fix what review/gates.md lists, then run it again")
    if g.get("video_sha256") != sha256_file(video):
        raise NotReady("the release gate passed for another version of the video: run the final gates, the "
                       "final-cut review and the release gate on the current one")
    return g


def description_for_studio(desc: str, marker: str) -> str:
    """The composed description without the trailing "Run:" marker (it only serves automated uploads)."""
    lines = desc.rstrip("\n").split("\n")
    if lines and lines[-1].strip() == marker:
        lines.pop()
        while lines and not lines[-1].strip():
            lines.pop()
    return "\n".join(lines)


def plan_committed(folder: Path) -> bool | None:
    """True when the series folder is committed unchanged, False when it is new or changed here, None without git."""
    try:
        r = subprocess.run(["git", "-C", str(REPO), "status", "--porcelain", "--", rel(folder)], capture_output=True,
                           text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return None if r.returncode != 0 else r.stdout.strip() == ""


def voice_text(run: Path) -> tuple[str, str]:
    """(service, model) of the narration from video/voice/manifest.json ('', '' without one)."""
    m = read_json(run / "video" / "voice" / "manifest.json", {})
    return str(m.get("service") or ""), str(m.get("voice_model") or "")


def music_section(run: Path) -> list[str]:
    """The upload sheet's "Music" section: what is in the mix, its licence, and what to do about a claim."""
    final = run / "video" / "final"
    asm = read_json(final / "assembly.json")
    info = (asm.get("audio") or {}).get("music") or {}
    meas = (asm.get("audio") or {}).get("measured") or {}
    out = ["## Music", ""]
    if not info.get("used"):
        out += ["None: the narration only.", ""]
    else:
        st = read_json(final / "music.json", {})
        out += [f"- Original, generated for this video by `{st.get('generator', info.get('generator'))}` "
                f"{st.get('tool_version', '')} (preset `{st.get('preset')}`, seed {st.get('seed')}); no samples, no "
                "third-party recording, nothing to attribute or license. Provenance: `video/final/music.json` "
                f"(sha256 `{str(st.get('sha256', ''))[:16]}...`).",
                "- Content ID: no claim is expected (nothing in the mix is registered). If one appears anyway, "
                "dispute it as original content and cite the generator stamp above; for a licensed track (not used "
                "here) you would attach its saved licence instead.",
                f"- Mix: the bed {abs(info.get('bed_in_gaps_lu', 0))} LU under the narration in pauses and "
                f"{abs(info.get('bed_under_voice_lu', 0))} LU under it while it speaks; "
                f"{len(info.get('stings', []))} motif sting(s) "
                f"({', '.join(s['kind'] + ' at ' + str(round(s['t'], 1)) + ' s' for s in info.get('stings', []))}).",
                ""]
    if meas:
        out += [f"Loudness of the final file: {meas.get('integrated_lufs')} LUFS integrated, true peak "
                f"{meas.get('true_peak_dbtp')} dBTP (measured after AAC encoding).", ""]
    return out


def sheet(run: Path, meta: dict, files: dict[str, Path], gates: dict, plan: tuple[str, bool | None] | None) -> str:
    channel = load_json(CONFIG / "channel.json")
    topic = P.topic(run)
    series = P.is_series(run)
    sn, st = meta["snippet"], meta["status"]
    asm = read_json(run / "video" / "final" / "assembly.json")
    chapters = read_json(run / "video" / "final" / "chapters.json", {"chapters": [], "valid": False})
    dur = float(asm["duration"])
    service, model = voice_text(run)
    synthetic = bool(st.get("containsSyntheticMedia"))
    voice = (f"{service}{' (' + model + ')' if model else ''}" if service else "unknown")
    kids = "Yes, it is made for kids" if st.get("selfDeclaredMadeForKids") else "No, it is not made for kids"
    pl = (topic.get("playlist") or {}) if series else {}
    ctx = read_json(run / "video" / "series_context.json", {})
    what = (f"episode {topic['episode']} of {topic.get('episodes_total', '?')} of \"{topic['series_title']}\""
            if series else "single video")
    out = [f"# Upload sheet: {sn['title']}", "",
           f"{channel['channel_name']} · run `{run.name}` · {what} · {int(dur) // 60}:{int(dur) % 60:02d} · "
           f"{len(chapters.get('chapters', []))} chapters · made {utc_now()[:10]}", "",
           "The final gates and the final-cut review passed for this exact video file (sha256 "
           f"`{gates['video_sha256'][:16]}...`, listed in SHA256SUMS). Nothing has been uploaded: watch the video, "
           "then upload it yourself with the steps below.", "",
           "## Files", "", "| File | What it is |", "|---|---|",
           f"| `{files['video'].name}` | the video, {files['video'].stat().st_size / 1e6:.1f} MB |",
           f"| `{files['captions'].name}` | the captions (the narration, timed) |",
           f"| `{files['thumbnail'].name}` | the custom thumbnail |",
           "| `final_cut_review.md` | what the final-cut review watched and found, and how each finding was "
           "resolved |",
           "| `youtube.json` | the same metadata as this sheet, as data |", "",
           "## Title", "", "```text", sn["title"], "```", "",
           "## Description", "",
           "Paste it whole. It starts with the episode line and carries the chapter list YouTube turns into chapters."
           if series else "Paste it whole. Its chapter list is what YouTube turns into chapters.", "",
           "```text", description_for_studio(sn["description"], meta.get("marker", f"Run: {run.name}")), "```", "",
           "## Tags", "", "```text", ", ".join(sn.get("tags", [])), "```", "",
           "## Chapters", ""]
    if chapters.get("valid"):
        out += ["Already in the description (YouTube needs the first at 0:00, at least three, each at least 10 s; "
                "these were checked):", "", "```text", *[c["label"] for c in chapters["chapters"]], "```", ""]
    else:
        out += ["None: the video has fewer than three chapters, so YouTube shows none.", ""]
    out += music_section(run)
    out += ["## Settings", "",
            f"- Audience: {kids}",
            f"- Altered or synthetic content: **{'Yes' if synthetic else 'No'}** (the narration voice: {voice}"
            + ("; a synthetic voice reads the script" if synthetic else "; your own recorded voice") + ")",
            f"- Category: {CATEGORIES.get(str(sn.get('categoryId')), 'id ' + str(sn.get('categoryId')))}",
            f"- Video language and caption language: {sn.get('defaultLanguage', 'en')}",
            f"- License: {LICENCES.get(st.get('license', 'youtube'), st.get('license', 'youtube'))}; "
            f"allow embedding: {'yes' if st.get('embeddable', True) else 'no'}; show how many viewers like this "
            f"video: {'yes' if st.get('publicStatsViewable', True) else 'no'}",
            "- Visibility: Private while you check it on YouTube, then Public (or Schedule)"]
    if series:
        out += [f"- Playlist: \"{pl.get('title') or topic['series_title']}\" (create it the first time, "
                f"{pl.get('privacy', 'public')}, with the description below)", "",
                "Playlist description (once, when you create the playlist):",
                "", "```text", pl.get("description", ""), "```"]
        missing = [k for k in (ctx.get("prerequisites") or {}).get("must", [])
                   if not (ctx.get("published") or {}).get(k)]
        if missing:
            names = ", ".join(f"\"{(ctx.get('short_titles') or {}).get(k, k)}\"" for k in missing)
            out += ["", f"This episode builds on {names}. The description has no link to "
                    f"{'it' if len(missing) == 1 else 'them'} (no published video ID was known when the episode "
                    "started); you may add a line such as `Builds on: <title>: <link>` after the episode line."]
    if plan:
        slug_s, committed = plan
        out += ["", "## Series plan", "",
                f"`series/{slug_s}/` in this folder is a copy of the plan this episode was made from (series.json, "
                "PLAN.md). " + (
                    "It is already in your repository, unchanged: nothing to do." if committed else
                    "It was made or changed in this session and exists nowhere else: copy the folder into your "
                    f"repository as `series/{slug_s}/`, commit and push it, so the next session makes the next episode "
                    "from the same plan instead of planning again." if committed is False else
                    f"If your repository has no `series/{slug_s}/` yet, copy it there, commit and push it, so the next "
                    "session uses the same plan.")]
    out += ["", "## YouTube Studio checklist", "",
            f"- [ ] Watch `{files['video'].name}` from start to end (sound on); compare a few captions with the "
            "narration",
            f"- [ ] Create > Upload videos: `{files['video'].name}`; while it processes paste the title, the "
            "description and the tags",
            f"- [ ] Thumbnail: upload `{files['thumbnail'].name}`"]
    if series:
        out.append(f"- [ ] Playlists: add it to \"{pl.get('title') or topic['series_title']}\"")
    out += [f"- [ ] Audience: {kids}",
            ("- [ ] Altered or synthetic content (Details > Show more): tick **Yes**, the box YouTube asks for "
             "realistic altered or synthetic content: an AI voice narrates (voice policy: AI narration is always "
             "disclosed; the description says so too)" if synthetic else
             "- [ ] Altered or synthetic content (Details > Show more): No (your own voice)"),
            "- [ ] Show more > Category, language and license as in Settings",
            f"- [ ] Subtitles: Add language ({sn.get('defaultLanguage', 'en')}), Upload file > With timing > "
            f"`{files['captions'].name}`",
            "- [ ] Chapters: once processing is done, open the video page: the progress bar shows the chapters of "
            "the list above at the same times" if chapters.get("valid") else
            "- [ ] Chapters: none for this video (fewer than three)"]
    steps = [s for s in RP.studio_steps(run, series) if s.startswith("- [ ]")]
    out += steps
    out += ["- [ ] Visibility: Private first; watch it once on YouTube (captions, chapters, thumbnail), then Public "
            "or Schedule",
            "- [ ] Keep these files until the video is public: the cloud session's copies are temporary", ""]
    return "\n".join(out)


def build(run: Path, out: Path) -> list[Path]:
    video = P.final_video(run)
    gates = release_record(run, video)
    final = run / "video" / "final"
    yp = final / "youtube.json"
    if not yp.exists():
        raise NotReady(f"{rel(yp)} missing: run tools/video/metadata.py")
    meta = read_json(yp)
    files = {"video": video, "captions": final / f"{P.topic(run)['slug']}.srt", "thumbnail": final / "thumbnail.jpg"}
    missing = [rel(p) for p in files.values() if not p.exists()]
    if missing:
        raise NotReady(f"missing: {', '.join(missing)}")
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    written = []
    for p in files.values():
        written.append(Path(shutil.copy2(p, out / p.name)))
    written.append(Path(shutil.copy2(yp, out / "youtube.json")))
    fc = run / "review" / "final_cut" / "summary.md"
    (out / "final_cut_review.md").write_text(
        fc.read_text(encoding="utf-8") if fc.exists() else
        "# Final-cut review\n\nNot run: config/pipeline.json makes it optional and none was recorded.\n",
        encoding="utf-8")
    written.append(out / "final_cut_review.md")
    plan = None
    if P.is_series(run):
        slug_s = P.topic(run)["series"]
        folder = SERIES / slug_s
        if (folder / "series.json").exists():
            (out / "series" / slug_s).mkdir(parents=True)
            for name in ("series.json", "PLAN.md"):
                if (folder / name).exists():
                    written.append(Path(shutil.copy2(folder / name, out / "series" / slug_s / name)))
            plan = (slug_s, plan_committed(folder))
    (out / "upload_sheet.md").write_text(sheet(run, meta, {k: out / p.name for k, p in files.items()}, gates, plan),
                                         encoding="utf-8")
    written.insert(0, out / "upload_sheet.md")
    (out / "SHA256SUMS").write_text("".join(f"{sha256_file(p)}  {p.relative_to(out).as_posix()}\n" for p in written),
                                    encoding="utf-8")
    return written + [out / "SHA256SUMS"]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run")
    ap.add_argument("--out", help="folder to write (default runs/<run>/deliver/)")
    a = ap.parse_args()
    run = resolve_run(a.run)
    out = Path(a.out).resolve() if a.out else run / "deliver"
    try:
        written = build(run, out)
    except NotReady as exc:
        print(f"error: not ready to hand over: {exc}", file=sys.stderr)
        return 1
    for p in written:
        print(f"{rel(p)}\t{p.stat().st_size / 1e6:.1f} MB")
    print(f"deliver: {len(written)} files in {rel(out)}; nothing was uploaded")
    return 0


if __name__ == "__main__":
    sys.exit(main())
