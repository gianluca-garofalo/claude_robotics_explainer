#!/usr/bin/env python3
"""Merge a run's reviewer reports, every round, into one ranked review/summary.json and summary.md.

Usage:
  python3 tools/merge_reviews.py runs/<run> [--set explainer|video|final_cut|series_plan]   # review/ or review/<set>/
  python3 tools/merge_reviews.py runs/<run> --set SET --workflow-args     # the args of the review-fanout workflow
  python3 tools/merge_reviews.py runs/<run> --set SET --pending REVIEWER  # check one reviewer's report (JSON)
  A later round is <reviewer>.round2.json (round3, ...) beside the earlier report, its finding ids new; exit 1 on an
  invalid report, a finding id in two reports, or a resolution or verdict whose finding no report holds.
  --pending checks the reviewer's newest round with tools/validate.py and lists its blocker and major findings without
  a verdict, per report; exit 1 when the report is missing or fails. A report counts as independent only with
  "independent": true (reviewer-contract.md).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import md_cell as cell, read_json, rel, resolve_run, sha256_file, utc_now, write_json  # noqa: E402
import validate as V  # noqa: E402

SETS = ("explainer", "video", "final_cut", "series_plan")
SEV_ORDER = {"blocker": 0, "major": 1, "minor": 2, "nit": 3}
VERDICT_ORDER = {"confirmed": 0, "uncertain": 1, "unverified": 2, "refuted": 3}
SERIOUS = ("blocker", "major")
SKIP = V.NOT_REVIEWS
ROUND_RE = re.compile(r"^(?P<name>.+?)(?:\.round(?P<n>\d+))?\.json$")


def review_sets() -> dict[str, tuple[str, ...]]:
    """The reviewers of each set: tools/gate.py's REVIEWERS (the explainer) and VIDEO_REVIEWERS, and the series red
    team, which no gate lists (tools/series.py write reads its summary)."""
    import gate                                  # only here: the gate imports this module
    return {"explainer": gate.REVIEWERS, **gate.VIDEO_REVIEWERS, "series_plan": ("series-red-team",)}


def review_dir(run: Path, rset: str) -> Path:
    return run / "review" if rset == "explainer" else run / "review" / rset


def scenes_sha256(run: Path) -> str:
    """One hash over the scene sources and the video plan: what a video design review looked at."""
    h = hashlib.sha256()
    for f in sorted((run / "video" / "scenes").glob("*.py")) + [run / "video" / "plan.json"]:
        if f.exists():
            h.update(f.name.encode() + b"\0" + f.read_bytes() + b"\0")
    return h.hexdigest()


def report_files(rv: Path) -> list[tuple[Path, int]]:
    """The reports in rv with their round number, each reviewer's rounds in order."""
    found = [(p, ROUND_RE.match(p.name)) for p in rv.glob("*.json") if p.name not in SKIP]
    return [(p, int(m["n"] or 1)) for p, m in sorted(found, key=lambda x: (x[1]["name"] + ".json", int(x[1]["n"] or 1)))]


def independence_errors(data: dict, name: str) -> list[str]:
    """Every report says who made it (reviewer-contract.md, Report): a missing field is not independence."""
    if isinstance(data.get("independent"), bool) and str(data.get("reviewed_by") or "").strip():
        return []
    return [f'$.independent and $.reviewed_by are required: "independent": true and "reviewed_by": "{name} subagent" '
            'from a reviewer subagent, false and "main session (no subagents)" from the session that made the work '
            '(reviewer-contract.md, Report)']


def pending(run: Path, rset: str, name: str) -> dict:
    """One reviewer's newest report checked (tools/validate.py, the independence fields, its symbol ledger) and its
    blocker and major findings without a verdict, every round, grouped by report."""
    rv = review_dir(run, rset)
    rounds = [p for p, _ in report_files(rv) if ROUND_RE.match(p.name)["name"] == name]
    out = {"reviewer": name, "report": rel(rounds[-1] if rounds else rv / f"{name}.json"), "errors": [], "verify": []}
    if not rounds:
        out["errors"].append(f"no report: write {out['report']} and its .md (reviewer-contract.md)")
        return out
    rep = V.validate_file("review", rounds[-1], run)
    out["errors"] += rep.errors
    if not rep.errors:
        data = read_json(rounds[-1])
        if data.get("reviewer") != name:
            out["errors"].append(f"$.reviewer must be {name!r} (the report's file name)")
        out["errors"] += independence_errors(data, name)
    lp = rv / "symbol_ledger.json"
    try:                                         # the ledger names its writer; an unreadable one fails the merge
        ledger_by = read_json(lp).get("reviewer") if rset == "explainer" and lp.exists() else None
    except (ValueError, AttributeError):
        ledger_by = None
    if ledger_by == name:
        lrep = V.validate_file("symbol_ledger", lp, run)
        V.ledger_findings(run, lrep)
        out["errors"] += [f"{rel(lp)}: {e}" for e in lrep.errors]
    verdicts = {p.stem for p in (rv / "verify").glob("*.json")}
    for p in rounds:
        try:
            findings = read_json(p).get("findings", [])
        except (ValueError, AttributeError):
            continue
        ids = [f.get("id") for f in findings if isinstance(f, dict) and f.get("severity") in SERIOUS
               and isinstance(f.get("id"), str) and f["id"] not in verdicts]
        if ids:
            out["verify"].append({"report": rel(p), "findings": ids})
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run")
    ap.add_argument("--set", choices=SETS, default="explainer")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--workflow-args", action="store_true",
                      help="print the args of the review-fanout workflow: run, set and the set's reviewers")
    mode.add_argument("--pending", metavar="REVIEWER", help="check this reviewer's newest report; print JSON")
    a = ap.parse_args()
    run = resolve_run(a.run)
    if a.workflow_args:
        print(json.dumps({"run": rel(run), "set": a.set, "reviewers": list(review_sets()[a.set])}))
        return 0
    if a.pending:
        out = pending(run, a.set, a.pending)
        print(json.dumps(out))
        return 1 if out["errors"] else 0
    rv = review_dir(run, a.set)
    reports, bad = [], False
    for p, rnd in report_files(rv):
        rep = V.validate_file("review", p, run)
        if rep.errors:
            rep.print()
            bad = True
            continue
        reports.append(dict(read_json(p), _round=rnd, _file=p.name))
    verdicts = {}
    for vp in sorted((rv / "verify").glob("*.json")):
        rep = V.validate_file("verdict", vp, run)
        if rep.errors:
            rep.print()
            bad = True
            continue
        v = read_json(vp)
        verdicts[v["finding"]] = v
    ledger = None
    lp = rv / "symbol_ledger.json"
    if a.set == "explainer" and lp.exists():
        rep = V.validate_file("symbol_ledger", lp, run)
        if rep.errors:
            rep.print()
            bad = True
        else:
            ledger = read_json(lp)
    rp = rv / "resolutions.json"
    res = {r["finding"]: r for r in read_json(rp, {}).get("resolutions", [])}
    if bad:
        return 1
    if not reports:
        print("error: no reviewer reports in review/", file=sys.stderr)
        return 1
    where, errors = {}, []
    for r in reports:
        for f in r["findings"]:
            if f["id"] in where:
                errors.append(f"finding {f['id']} is in {where[f['id']]} and in {r['_file']}: a later round numbers its "
                              "findings after the earlier rounds'")
            where[f["id"]] = r["_file"]
    for what, ids in ((rel(rp), res), (rel(rv / "verify"), verdicts)):
        orphans = sorted(set(ids) - set(where))
        if orphans:
            errors.append(f"{what} names {', '.join(orphans)}, which no report holds: a later round goes in "
                          "<reviewer>.round2.json and leaves the earlier report as it was (restore it: its findings "
                          "are in summary.json)")
    if errors:
        for e in errors:
            print(f"error: {e}", file=sys.stderr)
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
    unverified_serious = [f["id"] for f in findings if f["severity"] in SERIOUS and f["verdict"] == "unverified"]
    open_serious = [f for f in findings if f["severity"] in SERIOUS and f["status"] == "open"]
    html = run / "explainer.html"
    extra = {}
    if a.set == "final_cut":                 # tied to the video it watched
        sys.path.insert(0, str(Path(__file__).resolve().parent / "video"))
        import plan as P
        vid = P.final_video(run)
        extra = {"video_sha256": sha256_file(vid) if vid.exists() else None}
    not_indep = [r for r in reports if r.get("independent") is not True]     # not stated is not independent
    summary = {"schema_version": 1, "merged_at": utc_now(), "set": a.set,
               "explainer_sha256": sha256_file(html) if html.exists() else None,
               "scenes_sha256": scenes_sha256(run) if a.set == "video" else None, **extra,
               "independent": not not_indep,
               "reviewed_by": sorted({str(r.get("reviewed_by") or f"{r['reviewer']} (not stated)") for r in reports}),
               "reviewers": [dict({"reviewer": r["reviewer"], "findings": len(r["findings"]), "summary": r["summary"],
                                   "independent": r.get("independent") is True},
                                  **({"round": r["_round"]} if r["_round"] > 1 else {})) for r in reports],
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
    if not_indep:
        md += ["**NOT INDEPENDENT:** " + ", ".join(sorted({r["_file"] for r in not_indep})) + " do not say "
               '`"independent": true`: reviewed by the session that made the work, or not stated (reviewed by: '
               + ", ".join(summary["reviewed_by"]) + ")."
               + (" The release gate marks the final-cut review as not independent." if a.set == "final_cut" else ""),
               ""]
    md += ["| Reviewer | Findings | Summary |", "|---|---|---|"]
    for r in reports:
        label = r["reviewer"] + (f" (round {r['_round']})" if r["_round"] > 1 else "")
        md.append(f"| {label} | {len(r['findings'])} | {cell(r['summary'])} |")
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
