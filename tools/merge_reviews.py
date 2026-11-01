#!/usr/bin/env python3
"""Merge reviewer reports into one ranked summary (deterministic).

Usage:
  python3 tools/merge_reviews.py runs/<run>                 # explainer reviews: review/*.json -> review/summary.*
  python3 tools/merge_reviews.py runs/<run> --set video     # video design review: review/video/ -> review/video/summary.*
  python3 tools/merge_reviews.py runs/<run> --set final_cut # final-cut review of the assembled video: review/final_cut/
  python3 tools/merge_reviews.py runs/<plan run> --set series_plan   # red team of a series plan: review/series_plan/

Reads review/<reviewer>.json (one per reviewer subagent), review/verify/<finding-id>.json (verdicts of the
finding-verifier subagents on blocker and major findings) and, if present, review/resolutions.json (how the
writer handled each finding: {"resolutions": [{"finding", "status": "fixed"|"wontfix", "note"}]}) and, for the
explainer, review/symbol_ledger.json (the presentation-reviewer's symbol ledger: its changes of meaning are listed in
the summary for the writer).
Writes review/summary.json and review/summary.md, findings sorted by severity, then verdict, then id.
A blocker or major finding is open until it is refuted by verification or resolved by the writer.
Exit status 1 if an input file is invalid; 0 otherwise (the open count is printed).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import rel, resolve_run, sha256_file, utc_now, write_json  # noqa: E402
import validate as V  # noqa: E402

SEV_ORDER = {"blocker": 0, "major": 1, "minor": 2, "nit": 3}
VERDICT_ORDER = {"confirmed": 0, "uncertain": 1, "unverified": 2, "refuted": 3}
SKIP = V.NOT_REVIEWS


def scenes_sha256(run: Path) -> str:
    """One hash over the scene sources and the video plan: what a video design review looked at."""
    import hashlib
    h = hashlib.sha256()
    files = sorted((run / "video" / "scenes").glob("*.py")) + [run / "video" / "plan.json"]
    for f in files:
        if f.exists():
            h.update(f.name.encode() + b"\0" + f.read_bytes() + b"\0")
    return h.hexdigest()


def cell(s) -> str:
    return str(s).replace("|", "\\|").replace("\n", " ").strip()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run")
    ap.add_argument("--set", choices=["explainer", "video", "final_cut", "series_plan"], default="explainer")
    a = ap.parse_args()
    run = resolve_run(a.run)
    rv = run / "review" if a.set == "explainer" else run / "review" / a.set
    reports, bad = [], False
    for p in sorted(rv.glob("*.json")):
        if p.name in SKIP:
            continue
        rep = V.validate_file("review", p, run)
        if rep.errors:
            rep.print()
            bad = True
            continue
        reports.append(json.loads(p.read_text(encoding="utf-8")))
    verdicts = {}
    for vp in sorted((rv / "verify").glob("*.json")):
        rep = V.validate_file("verdict", vp, run)
        if rep.errors:
            rep.print()
            bad = True
            continue
        v = json.loads(vp.read_text(encoding="utf-8"))
        verdicts[v["finding"]] = v
    ledger = None
    lp = rv / "symbol_ledger.json"
    if a.set == "explainer" and lp.exists():
        rep = V.validate_file("symbol_ledger", lp, run)
        if rep.errors:
            rep.print()
            bad = True
        else:
            ledger = json.loads(lp.read_text(encoding="utf-8"))
    res = {}
    rp = rv / "resolutions.json"
    if rp.exists():
        res = {r["finding"]: r for r in json.loads(rp.read_text(encoding="utf-8")).get("resolutions", [])}
    if bad:
        return 1
    if not reports:
        print("error: no reviewer reports in review/", file=sys.stderr)
        return 1

    findings = []
    for r in reports:
        for f in r["findings"]:
            v = verdicts.get(f["id"])
            verdict = v["verdict"] if v else "unverified"
            status = res.get(f["id"], {}).get("status", "open")
            if verdict == "refuted":
                status = "refuted"
            findings.append(dict(f, reviewer=r["reviewer"], verdict=verdict,
                                 verdict_reason=v["reason"] if v else "", status=status,
                                 resolution_note=res.get(f["id"], {}).get("note", "")))
    findings.sort(key=lambda f: (SEV_ORDER[f["severity"]], VERDICT_ORDER.get(f["verdict"], 9), f["id"]))
    unverified_serious = [f["id"] for f in findings if f["severity"] in ("blocker", "major") and f["verdict"] == "unverified"]
    open_serious = [f for f in findings if f["severity"] in ("blocker", "major") and f["status"] == "open"]
    html = run / "explainer.html"
    extra = {}
    if a.set == "final_cut":                 # tied to the video it watched; independent unless a reviewer says not
        sys.path.insert(0, str(Path(__file__).resolve().parent / "video"))
        import plan as P
        vid = P.final_video(run)
        extra = {"video_sha256": sha256_file(vid) if vid.exists() else None,
                 "independent": all(r.get("independent", True) is not False for r in reports),
                 "reviewed_by": sorted({r.get("reviewed_by", r["reviewer"]) for r in reports})}
    summary = {"schema_version": 1, "merged_at": utc_now(), "set": a.set,
               "explainer_sha256": sha256_file(html) if html.exists() else None,
               "scenes_sha256": scenes_sha256(run) if a.set == "video" else None, **extra,
               "reviewers": [{"reviewer": r["reviewer"], "findings": len(r["findings"]), "summary": r["summary"]}
                             for r in reports],
               "open_blocker_major": [f["id"] for f in open_serious], "unverified_blocker_major": unverified_serious,
               "findings": findings}
    if ledger is not None:
        changed = [sym for sym in ledger["symbols"] if any(u["change"] in ("announced", "unannounced")
                                                           for u in sym["uses"][1:])]
        summary["symbol_ledger"] = {"symbols": len(ledger["symbols"]),
                                    "changes": [dict(u, symbol=sym["symbol"], finding=sym.get("finding"))
                                                for sym in changed for u in sym["uses"]]}
    write_json(rv / "summary.json", summary)

    md = [f"# Review summary: {run.name}", "",
          f"Merged {summary['merged_at']} by `tools/merge_reviews.py` from {len(reports)} reviewer report(s). "
          "Blocker and major findings are checked by an independent finding-verifier before anyone acts on them; "
          "minor findings and nits are listed as reported.", ""]
    if a.set == "final_cut" and not extra["independent"]:
        md += ["**NOT INDEPENDENT:** the session could not start reviewer subagents, so the video was reviewed by the "
               f"session that made it ({', '.join(extra['reviewed_by'])}). The gate marks the review as not independent.",
               ""]
    md += ["| Reviewer | Findings | Summary |", "|---|---|---|"]
    md += [f"| {r['reviewer']} | {len(r['findings'])} | {cell(r['summary'])} |" for r in reports]
    md += ["", f"**Open blocker/major findings: {len(open_serious)}**"
           + (f" ({', '.join(f['id'] for f in open_serious)})" if open_serious else "") + ".", ""]
    if unverified_serious:
        md += [f"Not yet verified: {', '.join(unverified_serious)} (run the finding-verifier).", ""]
    md += ["## Findings", "", "| ID | Severity | Verdict | Status | Location | Issue | Suggested fix |", "|---|---|---|---|---|---|---|"]
    for f in findings:
        loc = f"{f['time_s']:.1f} s, {f['location']}" if isinstance(f.get("time_s"), (int, float)) else f["location"]
        md.append(f"| {f['id']} | {f['severity']} | {f['verdict']} | {f['status']} | {cell(loc)} | "
                  f"{cell(f['issue'])} | {cell(f['suggested_fix'])} |")
    if ledger is not None:
        sl = summary["symbol_ledger"]
        md += ["", "## Symbol ledger", "",
               f"{sl['symbols']} symbol(s) tracked by the presentation-reviewer (`review/symbol_ledger.json`); "
               f"{len({c['symbol'] for c in sl['changes']})} change meaning between sections"
               + (":" if sl["changes"] else "."), ""]
        if sl["changes"]:
            md += ["| Symbol | Section | Location | Meaning there | Built from | Use | Finding |",
                   "|---|---|---|---|---|---|---|"]
            md += [f"| {cell(c['symbol'])} | {cell(c['section'])} | {cell(c['location'])} | {cell(c['meaning'])} | "
                   f"{cell(c.get('defined_from') or '')} | {c['change']} | {c['finding'] or ''} |"
                   for c in sl["changes"]]
    md += ["", "## Evidence", ""]
    for f in findings:
        md.append(f"- **{f['id']}** ({f['reviewer']}, confidence {f['confidence']}): {cell(f['evidence'])}"
                  + (f" Verifier: {cell(f['verdict_reason'])}" if f["verdict_reason"] else "")
                  + (f" Resolution: {cell(f['resolution_note'])}" if f["resolution_note"] else ""))
    md += ["", "## Checks the reviewers ran", ""]
    for r in reports:
        for c in r.get("checks_run", []):
            md.append(f"- {r['reviewer']}: `{cell(c['command'])}` -> {cell(c['result'])}")
    (rv / "summary.md").write_text("\n".join(md).rstrip() + "\n", encoding="utf-8")
    print(f"wrote {rel(rv / 'summary.md')}: {len(findings)} finding(s), {len(open_serious)} open blocker/major, "
          f"{len(unverified_serious)} not yet verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
