#!/usr/bin/env python3
"""Write the single review message the human receives (the body of the review issue), deterministically.

Usage:
  python3 tools/review_package.py runs/<run> --video-id ID --preview-url URL --workflow-url URL
                                  [--approval-mode environment|label] [--token T] [--source-run-id N]

An empty --video-id means manual YouTube mode (repository variable YOUTUBE_UPLOAD=manual, used until the API
project passes Google's audit): the reviewer watches the MP4 from the run-final artifact instead of a private upload.

Collects: links to the private video and to the explainer preview, why the topic was chosen (selection.md), every
gate result (review/gates.json), the review findings by severity and what was done about them (review/summary.json),
the claims that are unverified or disputed (sources.json), the upload status (publish/stage.json), the final-cut review
(review/final_cut/summary.json), the YouTube Studio steps the API cannot do (end screen, cards, official series), and
the checklist.
Writes review/package.md. A hidden comment carries the run metadata the label-based approval workflow needs.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent / "video"))
from _common import CONFIG, load_json, rel, resolve_run  # noqa: E402
import plan as P  # noqa: E402

SEV = ["blocker", "major", "minor", "nit"]


def cell(s) -> str:
    return str(s).replace("|", "/").replace("\n", " ").strip()


def links_on(run) -> bool:
    """The run's links decision, recorded by tools/video/metadata.py in youtube.json."""
    yp = run / "video" / "final" / "youtube.json"
    if not yp.exists():
        return False
    m = json.loads(yp.read_text(encoding="utf-8"))
    return bool(m.get("links", {}).get("included", bool(m.get("explainer_url"))))


def voice_lines(run) -> list[str]:
    """The narration source: the service (and Piper voice model) and how its word timings were obtained."""
    man = run / "video" / "voice" / "manifest.json"
    if not man.exists():
        return []
    m = json.loads(man.read_text(encoding="utf-8"))
    model = f" {m['voice_model']}" if m.get("voice_model") else ""
    return [f"- Narration: {m.get('service')}{model} (word timings {m.get('timings', 'unknown')})"]


def studio_steps(run, series: bool) -> list[str]:
    """The manual YouTube Studio steps the API cannot do (end screen, cards, official series), with exact times."""
    asm_p = run / "video" / "final" / "assembly.json"
    if not asm_p.exists():
        return []
    asm = json.loads(asm_p.read_text(encoding="utf-8"))
    dur = asm["duration"]

    def mmss(t):
        return f"{int(t) // 60}:{int(t) % 60:02d}"
    outro = next((sg for sg in asm["segments"] if sg.get("role") == "outro"), None)
    t0 = max(dur - 20, outro["start"] if outro else dur - 20)
    out = ["", "### YouTube Studio steps after publishing (no API for these)", "",
           f"- [ ] End screen from {mmss(t0)} to {mmss(dur)}: "
           + ("the series playlist, or the next episode once it is public, " if series else "a related video, ")
           + "plus Subscribe, in the empty right part of the frame"]
    ctx_p = run / "video" / "series_context.json"
    if series and ctx_p.exists():
        ctx = json.loads(ctx_p.read_text(encoding="utf-8"))
        for sg in asm["segments"]:
            if sg.get("role") == "recap":
                out.append(f"- [ ] Optional card at {mmss(sg['start'])}: the full episode this recap restates "
                           f"({sg.get('chapter', 'recap')})")
        out.append(f"- [ ] Once per series: playlist settings, \"Set as official series for this playlist\" "
                   f"({ctx['series_title']})")
        if ctx.get("episode", 1) > 1:
            out.append("- [ ] Previous episode: point its end screen at this video now that it exists")
    return out


def final_cut_lines(run) -> list[str]:
    p = run / "review" / "final_cut" / "summary.json"
    if not p.exists():
        return ["", "### Final-cut review", "", "- not run (tools/video/final_frames.py, then the final-cut-review skill)"]
    s = json.loads(p.read_text(encoding="utf-8"))
    counts = {k: sum(f["severity"] == k for f in s["findings"]) for k in SEV}
    out = ["", "### Final-cut review (someone watched the assembled video)", "",
           ("- Independent reviewer subagent; blocker and major findings checked by a verifier. "
            if s.get("independent", True) else
            "- **NOT INDEPENDENT**: the session could not start a reviewer subagent, so the session that made the video "
            "reviewed it. ") + ", ".join(f"{counts[k]} {k}" for k in SEV) + "."]
    if s["findings"]:
        out += ["", "| ID | Time | Severity | Verdict | Status | Issue |", "|---|---|---|---|---|---|"]
        out += [f"| {f['id']} | {f.get('time_s', '')} s | {f['severity']} | {f['verdict']} | {f['status']} | "
                f"{cell(f['issue'])} |" for f in s["findings"]]
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run")
    ap.add_argument("--video-id", default="", help="empty in manual YouTube mode")
    ap.add_argument("--preview-url", required=True)
    ap.add_argument("--workflow-url", required=True)
    ap.add_argument("--approval-mode", default="environment", choices=["environment", "label"])
    ap.add_argument("--token", default="")
    ap.add_argument("--source-run-id", default="")
    a = ap.parse_args()
    run = resolve_run(a.run)
    channel = load_json(CONFIG / "channel.json")
    plan, topic = P.load(run), P.topic(run)
    gates = json.loads((run / "review" / "gates.json").read_text(encoding="utf-8"))
    sp_ = run / "review" / "summary.json"
    summary = json.loads(sp_.read_text(encoding="utf-8")) if sp_.exists() else {"findings": []}
    stage = json.loads((run / "publish" / "stage.json").read_text(encoding="utf-8")) \
        if (run / "publish" / "stage.json").exists() else {}
    asm = json.loads((run / "video" / "final" / "assembly.json").read_text(encoding="utf-8"))
    chapters = json.loads((run / "video" / "final" / "chapters.json").read_text(encoding="utf-8"))
    sp = run / "sources.json"
    sources = json.loads(sp.read_text(encoding="utf-8")) if sp.exists() else {"candidates": []}
    cand = next((c for c in sources["candidates"] if c["id"] == topic["topic_id"]), {"central_claims": [], "sources": []})
    series = P.is_series(run)
    preview = a.preview_url.rstrip("/") + "/"
    v = a.video_id
    slug = topic["slug"]
    if v:
        watch = (f"- **Watch the {stage.get('privacy', 'private')} video:** https://youtu.be/{v} (signed in as the "
                 f"channel owner) · YouTube Studio: https://studio.youtube.com/video/{v}/edit")
    else:
        watch = (f"- **Watch the video:** download the `run-final` artifact from {a.workflow_url} and open "
                 f"`video/final/{slug}.mp4` (manual YouTube mode: nothing was uploaded)")
    out = [f"## Review: {plan['title']}", "",
           f"{channel['channel_name']} · run `{run.name}` · "
           + (f"series episode {topic['episode']} of {topic['series']} (chosen by {topic.get('chosen_by', '?')})"
              if series else f"topic {topic['topic_id']} selected "
              f"{'automatically' if topic.get('mode') == 'auto' else 'by you'} (rank {topic['rank']}, total {topic['total']})")
           + " · "
           f"gates: {'all passed' if gates['passed'] else 'FAILED'} ({sum(c['ok'] for c in gates['checks'])}/"
           f"{len(gates['checks'])}) · video {asm['duration']:.0f} s, {len(chapters.get('chapters', []))} chapters", "",
           watch,
           *voice_lines(run),
           f"- **Read the explainer preview** (for you; the video never points to it"
           f"{', the description links it' if links_on(run) else ' and neither does the description'}): {preview} "
           f"(not indexed) · code: {preview}code/ · "
           f"review summary: {preview}review/summary.md", "", "### How to decide", ""]
    if a.approval_mode == "environment":
        out += [f"- **Approve**: open {a.workflow_url}, click *Review deployments*, tick `publish`, *Approve and deploy*. "
                + ("The video goes public (or is scheduled), the explainer moves to its permanent address and this "
                   "issue closes." if v else "The explainer moves to its permanent address; a comment here then lists "
                   "the files to upload to YouTube by hand."),
                "- **Reject**: same place, *Reject*, and write the reason in the comment box. The run is archived with "
                "your reason and the video stays private.",
                "- Doing nothing for 30 days expires the request; the run is then archived as not approved."]
    else:
        out += ["- **Approve**: add the label `approve-publish` to this issue.",
                "- **Reject**: write the reason as a comment, then add the label `reject-publish`."]
    out += ["", "### Checklist", "",
            "- [ ] Watched the whole video: narration matches the captions, nothing is cut off or overlapping, "
            "numbers read well (the final-cut review below watched it first)",
            "- [ ] The video stands on its own: it never mentions the explainer, code, files or links, shows no "
            "equation numbers, and needs no other video (gate \"self-contained video\")",
            "- [ ] Thumbnail: legible at full size and at 168 x 94, nothing busy behind the title",
            "- [ ] Title and description are accurate (no clickbait); "
            + ("the explainer and code links work (links are on for this run)" if links_on(run)
               else "the description has no explainer, code or site links (links are off for this run)"),
            "- [ ] What the video says about the news matches the primary sources (see the claims below)",
            "- [ ] Equations and numbers on screen match the explainer",
            "- [ ] The explainer reads well, also on a phone",
            "- [ ] The made-for-kids and synthetic-media declarations fit this video",
            "- [ ] The design and reading-time warnings below are acceptable (labels readable, nothing gone too fast)",
            "",
            "### Why this topic", "", (run / "selection.md").read_text(encoding="utf-8").split("\n", 2)[-1].strip()
            if (run / "selection.md").exists() else
            (f"Series mode: episode {topic['episode']} of \"{topic['series_title']}\", sections "
             f"{', '.join(topic['sections'])} of the series' explainer (unchanged). Chosen by {topic.get('chosen_by')}; "
             "nothing was scouted, ranked or written." if series else "Approved by you with /approve-topic."), "",
            "### Gates", "", "| Gate | Result | Detail |", "|---|---|---|"]
    out += [f"| {c['name']} | {'pass' if c['ok'] else 'FAIL'} | {cell(c['detail'])} |" for c in gates["checks"]]
    counts = {s: sum(f["severity"] == s for f in summary["findings"]) for s in SEV}
    out += ["", "### Review findings", "",
            ("Series mode: the explainer was reviewed when it was first published; this run reviewed the video. "
             if series else "Five independent reviewers, one of them reading strictly front to back; blocker and "
             "major findings were checked by a verifier before any fix. ") + ", ".join(f"{counts[s]} {s}" for s in SEV) + ".", ""]
    if summary["findings"]:
        out += ["| ID | Severity | Verdict | Status | Location | Issue |", "|---|---|---|---|---|---|"]
        out += [f"| {f['id']} | {f['severity']} | {f['verdict']} | {f['status']} | {cell(f['location'])} | "
                f"{cell(f['issue'])} |" for f in summary["findings"]]
    vs_p = run / "review" / "video" / "summary.json"
    vsum = json.loads(vs_p.read_text(encoding="utf-8")) if vs_p.exists() else {"findings": []}
    out += ["", "### Video design", ""]
    for phase in ("draft", "final"):
        for tool in ("check_design", "check_reading"):
            rp = run / "review" / "design" / phase / f"{tool}.json"
            if rp.exists():
                r = json.loads(rp.read_text(encoding="utf-8"))
                out.append(f"- {tool.replace('_', ' ')} ({phase} renders): {r['summary']['errors']} error(s), "
                           f"{r['summary']['warnings']} warning(s)")
    vc = {s: sum(f["severity"] == s for f in vsum["findings"]) for s in SEV}
    out.append("- video-design-reviewer: " + ", ".join(f"{vc[s]} {s}" for s in SEV)
               + " (blockers gate the run; the rest is for your judgement)")
    if vsum["findings"]:
        out += ["", "| ID | Severity | Verdict | Status | Location | Issue |", "|---|---|---|---|---|---|"]
        out += [f"| {f['id']} | {f['severity']} | {f['verdict']} | {f['status']} | {cell(f['location'])} | "
                f"{cell(f['issue'])} |" for f in vsum["findings"]]
    out += final_cut_lines(run)
    out += studio_steps(run, series)
    claims = [c for c in cand["central_claims"] if c.get("status") != "verified"]
    if not series:
        out += ["", "### Unverified or disputed claims about the news", ""]
        out += [f"- [{c['status']}] {c['claim']}" for c in claims] or ["- none: every central claim is backed by a "
                                                                       "primary source"]
    out += ["", "### Upload", ""]
    if v:
        out += [f"- Video `{v}` on {stage.get('channel', '?')}, {stage.get('privacy', '?')}"
                + (" (reused: this run had already uploaded it)" if stage.get("reused") else ""),
                f"- Thumbnail set: {stage.get('thumbnail_set')} · captions uploaded: {stage.get('captions_set')}"]
        out += [f"- Warning: {w}" for w in stage.get("warnings", [])]
    else:
        out += ["- Manual YouTube mode (YOUTUBE_UPLOAD=manual): no upload. After approval, upload "
                f"`video/final/{slug}.mp4` with `thumbnail.jpg`, `{slug}.srt` and the title, description and tags in "
                "`youtube.json` (all in the run-final artifact)."]
    meta = {"run": run.name, "video_id": v, "token": a.token, "source_run_id": a.source_run_id, "slug": topic["slug"]}
    out += ["", f"<!-- pipeline-meta {json.dumps(meta)} -->"]
    path = run / "review" / "package.md"
    path.write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"wrote {rel(path)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
