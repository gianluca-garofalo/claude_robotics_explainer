#!/usr/bin/env python3
"""Turn judged rubric scores into a ranked, cited ranking.md (deterministic).

Usage:
  python3 tools/rank_topics.py runs/<run>             # writes ranking.md and ranking.json in the run
  python3 tools/rank_topics.py runs/<run> --check     # validate inputs and print the table only

Inputs:  run.json (run date), sources.json (scout), scores.json (ranker's judged scores with justifications),
         search.json (tools/search_demand.py, optional), config/rubric.json (weights, recency bands, gates; humans
         edit it, agents do not).
Recency is computed here from the newest primary-source date; search demand and supply gap come from search.json;
every other criterion is judged by the virality-ranker skill and only aggregated here. A computed criterion without
data is unknown ("?"), never zero: the total renormalises the weights of the known criteria for that topic.
The output is a heuristic, not a prediction.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import CONFIG, load_json, parse_date, ranking_inputs, rel, resolve_run, sha256_file, write_json  # noqa: E402
import validate as V  # noqa: E402

LABELS = {"recency": "Rec", "search_demand": "Search", "supply_gap": "Gap", "novelty": "Nov",
          "visual_potential": "Vis", "audience_fit": "Aud", "teachability": "Teach", "hype_risk": "Hype (-)"}


def recency_score(days: int | None, crit: dict) -> int | None:
    """Score from the age of the newest subject primary source; None (unknown, never 0) when no such date exists."""
    if days is None:
        return None
    for limit, score in crit["bands_days"]:
        if days <= limit:
            return int(score)
    return int(crit.get("older", 0))


def search_data(run: Path) -> tuple[dict | None, bool]:
    """search.json if it was collected for the current sources.json (by hash); (None, True) when it is stale."""
    p = run / "search.json"
    if not p.exists():
        return None, False
    data = load_json(p)
    want = data.get("sources_sha256")
    if want is not None and want != sha256_file(run / "sources.json"):
        return None, True
    return data, False


def cell(text) -> str:
    return str(text).replace("|", "\\|").replace("\n", " ").strip()


def compute(run: Path, sources: dict, scores: dict, rubric: dict) -> tuple[list[dict], str]:
    run_json = run / "run.json"
    run_date_s = load_json(run_json)["run_date"] if run_json.exists() else sources["run_date"]
    run_date = parse_date(run_date_s)
    crits = rubric["criteria"]
    pen = rubric.get("penalty", {})
    gates = rubric.get("gates", {})
    wsum = sum(c["weight"] for c in crits.values())
    if abs(wsum - 1.0) > 1e-9:
        raise SystemExit(f"error: criterion weights in config/rubric.json sum to {wsum}, not 1")
    by_id = {t["id"]: t for t in scores["topics"]}
    search, stale = search_data(run)
    rows = []
    for c in sources["candidates"]:
        tid = c["id"]
        t = by_id[tid]
        prim = [s for s in c["sources"] if s.get("primary") is True]
        subject = [s for s in prim if s.get("relation", "subject") == "subject"]     # prior work never counts
        dated = [parse_date(s["published"]) for s in subject if s.get("published")]
        newest = max(dated) if dated else None
        days = (run_date - newest).days if newest else None
        s = {}
        why = {}
        cites = {}
        for k, cfg in crits.items():
            if cfg.get("computed") and cfg.get("source", "dates") == "search":
                ev = (search or {}).get("topics", {}).get(tid)
                s[k] = ev["scores"].get(k) if ev else None
                why[k] = (ev["why"].get(k, "") if ev else "unknown: search.json is stale (sources.json changed after "
                          "the lookups; rerun tools/search_demand.py)" if stale else
                          "unknown: search data not collected (tools/search_demand.py)")
                cites[k] = ["search.json"] if ev else []
            elif cfg.get("computed"):
                s[k] = recency_score(days, cfg)
                why[k] = (f"Newest primary source about the topic published {newest.isoformat()} ({days} days before "
                          "the run date)." if newest else
                          "unknown: no dated primary source about the topic (weight renormalised).")
                cites[k] = [x["id"] for x in subject if x.get("published") == (newest.isoformat() if newest else None)]
            else:
                s[k] = t["scores"][k]["score"]
                why[k] = t["scores"][k]["why"]
                cites[k] = t["scores"][k].get("sources", [])
        for k in pen:
            s[k] = t["scores"][k]["score"]
            why[k] = t["scores"][k]["why"]
            cites[k] = t["scores"][k].get("sources", [])
        known = [k for k in crits if s[k] is not None]
        base = sum(crits[k]["weight"] * s[k] for k in known) / (5.0 * sum(crits[k]["weight"] for k in known))
        penalty = sum(pen[k]["weight"] * s[k] for k in pen) / 5.0
        total = round(100.0 * max(0.0, base - penalty), 1)
        roles = set(gates.get("claim_roles_counted", ["central"]))
        counted = [cl for cl in c["central_claims"] if cl.get("role", "central") in roles]
        unverified = [cl for cl in counted if cl.get("status") in ("unverified", "disputed")]
        provisional = [cl for cl in counted if cl.get("status") == "provisional"]
        reasons = []
        if gates.get("require_primary_source") and not subject:
            reasons.append("no primary source about the topic itself" + (" (only prior work)" if prim else ""))
        cov = c.get("coverage") or {}
        if cov.get("status") == "covered":
            reasons.append("already covered by the channel: " + ", ".join(cov.get("by", [])[:2]))
        if "hype_risk" in s and s["hype_risk"] > gates.get("max_hype_risk_for_recommendation", 5):
            reasons.append(f"hype risk {s['hype_risk']} > {gates['max_hype_risk_for_recommendation']}")
        if len(unverified) > gates.get("max_unverified_central_claims", 99):
            reasons.append(f"{len(unverified)} unverified or disputed central claim(s)")
        max_prov = gates.get("max_provisional_central_claims")
        if max_prov is not None and len(provisional) > max_prov:
            reasons.append(f"{len(provisional)} central claim(s) only provisionally checked")
        rows.append(dict(id=tid, title=c["title"], slug=c["slug"], summary=c["summary"], scores=s, why=why,
                         unknown=[k for k in crits if s[k] is None], search=(search or {}).get("topics", {}).get(tid),
                         provisional=len(provisional), coverage=cov,
                         cites=cites, total=total, eligible=not reasons, gate_reasons=reasons,
                         newest_primary=newest.isoformat() if newest else None, days=days,
                         claims=c["central_claims"], sources=c["sources"], hooks=c.get("visual_hooks", []),
                         angle=t.get("proposed_angle", ""), animation=t.get("animation_idea", "")))
    tb = rubric.get("tie_breakers", [])
    rows.sort(key=lambda r: (not r["eligible"], -r["total"], *[-(r["scores"].get(k) or 0) for k in tb], r["id"]))
    for i, r in enumerate(rows, 1):
        r["rank"] = i
    return rows, run_date_s


def render(run: Path, rows: list[dict], run_date: str, rubric: dict, sources: dict) -> str:
    crits = rubric["criteria"]
    pen = rubric.get("penalty", {})
    order = list(crits) + list(pen)
    name = run.name
    out = [f"# Topic ranking: {name}", "",
           f"Run date {run_date} · search window {sources.get('window_days')} days · rubric v{rubric['version']} "
           f"(`config/rubric.json`) · generated by `tools/rank_topics.py` from `sources.json` and `scores.json`.", "",
           f"> **{rubric['disclaimer']}** Scores are judgments with written reasons; read the reasons, not only the totals.", "",
           "## How the score is computed", "",
           f"`{rubric['formula']}`", "",
           "| Criterion | Weight | Meaning |", "|---|---|---|"]
    for k, c in crits.items():
        tag = f" (computed from {c.get('source', 'dates')})" if c.get("computed") else ""
        out.append(f"| {k}{tag} | {c['weight']:.2f} | {cell(c['description'])} |")
    for k, c in pen.items():
        out.append(f"| {k} (penalty) | -{c['weight']:.2f} | {cell(c['description'])} |")
    g = rubric.get("gates", {})
    mp = g.get("max_provisional_central_claims")
    out += ["", "Gates (a topic that fails one is listed but not recommended): a primary source about the topic itself "
            f"(relation `subject`; prior work does not count) = {g.get('require_primary_source')}; "
            f"hype risk at most {g.get('max_hype_risk_for_recommendation')}; unverified or disputed claims with role "
            f"{', '.join(g.get('claim_roles_counted', ['central']))} at most {g.get('max_unverified_central_claims')} "
            "(limitations and context never gate); provisionally checked central claims "
            f"{'allowed, flagged for re-verification before writing' if mp is None else f'at most {mp}'}; "
            "topics the channel already covers are excluded.", ""]
    path = rel(run)
    blocked = [u for u in sources.get("unreadable", []) if u.get("cause") == "network_policy"]
    if blocked:
        hosts = sorted({re.sub(r"^https?://([^/]+).*$", r"\1", u["url"]) for u in blocked})
        out += ["## Sources unreadable from this network", "",
                f"**{len(blocked)} source(s) could not be fetched because this session's network policy blocks "
                f"{', '.join(hosts)}.** This is a limitation of the run, not of the topics. Claims were checked at "
                "the best level reachable (source-policy.md, fallbacks): an abstract read through a metadata "
                "endpoint or index counts as `abstract`; a search tool's summary of the canonical page counts as "
                "`search_abstract`, and claims resting on it are `provisional`, to be re-verified where these hosts "
                "are reachable (allow them in the environment's network settings, or in CI) before writing.", ""]
        prov = sum(r.get("provisional", 0) for r in rows)
        out += [f"In this run {prov} central claim(s) are provisional" + (" (listed per topic below)." if prov else
                ": every central claim was checked at abstract level or better despite the blocked hosts."), ""]
        out += [f"- {cell(u['url'])}: {cell(u['reason'])}" for u in blocked]
        out.append("")
    srch, stale = search_data(run)
    if stale:
        out += ["**Search data is stale:** `search.json` was collected for an earlier `sources.json` (hashes differ), "
                "so search demand and supply gap are treated as unknown. Rerun `tools/search_demand.py`.", ""]
    elif srch:
        out += [f"Search data (`search.json`, {srch['collected_at']}): "
                + "; ".join(f"{k} {v}" for k, v in srch.get("sources_status", {}).items())
                + f"; YouTube quota used {srch.get('youtube_quota_units', 0)} units. A source that failed is "
                "unknown, never zero.", ""]
    else:
        out += ["Search data not collected (`tools/search_demand.py`): search demand and supply gap are unknown for "
                "every topic and the totals use the other criteria.", ""]
    other = [u for u in sources.get("unreadable", []) if u.get("cause") != "network_policy"]
    if other:
        out += ["Sources that could not be read for other reasons (not silently dropped):", ""]
        out += [f"- {cell(u['url'])}: {cell(u['reason'])}" for u in other]
        out.append("")
    out += ["## Ranking", "", "| # | Topic | Total | " + " | ".join(LABELS.get(k, k) for k in order) + " | Gate |",
            "|---|---|---|" + "---|" * len(order) + "---|"]
    for r in rows:
        gate = "eligible" if r["eligible"] else "excluded: " + "; ".join(r["gate_reasons"])
        if r["eligible"] and r.get("provisional"):
            gate += f" (provisional: {r['provisional']} central claim(s) to re-verify)"
        if (r.get("coverage") or {}).get("status") == "partly_covered":
            gate += " (partly covered: " + ", ".join(r["coverage"].get("by", [])[:1]) + ")"
        out.append(f"| {r['rank']} | {r['id']} {cell(r['title'])} | {r['total']:.1f} | "
                   + " | ".join("?" if r["scores"][k] is None else str(r["scores"][k]) for k in order)
                   + f" | {cell(gate)} |")
    out += ["", "## Recommendation", ""]
    best = next((r for r in rows if r["eligible"]), None)
    if best:
        out += [f"**{best['id']}: {best['title']}** (total {best['total']:.1f}).", "",
                f"- Proposed angle: {best['angle']}", f"- Animation idea: {best['animation']}", ""]
    else:
        out += ["No topic passes the gates. Scout again, widen the window, or approve an excluded topic "
                "explicitly and address its gate reasons in the explainer.", ""]
    out += ["**Next step:** in automatic mode `tools/auto_select.py` approves the best eligible topic and logs why "
            f"(`config/pipeline.json`); in human mode type `/approve-topic {path} <topic-id>`. Nothing is "
            "written, rendered or published before that.", "", "## Topics in detail", ""]
    for r in rows:
        out += [f"### {r['rank']}. {r['id']} · {r['title']}", "", r["summary"], ""]
        cov = r.get("coverage") or {}
        if cov:
            out += [f"Coverage: {cov.get('status')}" + (f" ({', '.join(cov.get('by', []))})" if cov.get("by") else "")
                    + (f": {cov['note'].rstrip('.')}" if cov.get("note") else "") + ".", ""]
        if not r["eligible"]:
            out += [f"**Excluded from recommendation:** {'; '.join(r['gate_reasons'])}.", ""]
        out += ["| Criterion | Score | Why | Sources |", "|---|---|---|---|"]
        for k in order:
            sign = " (penalty)" if k in pen else ""
            val = "? (unknown, weight renormalised)" if r["scores"][k] is None else r["scores"][k]
            out.append(f"| {k}{sign} | {val} | {cell(r['why'][k])} | {', '.join(r['cites'][k]) or '-'} |")
        ev = r.get("search")
        if ev:
            out += ["", f"Search queries: {', '.join(repr(q) for q in ev['queries'])}."]
            for q in ev.get("autocomplete", {}).get("queries", []):
                out.append(f"- Suggestions for '{cell(q['query'])}': {cell(', '.join(q['matching'][:5])) or 'none matching'}")
            for v in ev.get("youtube", {}).get("top", []):
                out.append(f"- Competing video: {cell(v['title'])} ({cell(v['channel'])}, {v['published']}, "
                           f"{v['views']:,} views)")
        out += ["", "Claims (status, role; only central claims count for the gate):", ""]
        for cl in r["claims"]:
            mark = "verified" if cl.get("status") == "verified" else cl.get("status", "?").upper()
            role = cl.get("role", "central")
            out.append(f"- [{mark}, {role}] {cl['claim']} ({', '.join(cl.get('support', [])) or 'no source'})")
        if r["hooks"]:
            out += ["", "Visual hooks: " + "; ".join(r["hooks"])]
        out += ["", "Sources:", ""]
        for s in r["sources"]:
            rel_ = s.get("relation", "subject" if s.get("primary") else "context")
            kind = f"{s['kind']}, {'primary' if s.get('primary') else 'secondary'}, {rel_}"
            via = f" via {s['via']}" if s.get("via") else ""
            out.append(f"- {s['id']} ({kind}; published {s.get('published') or 'unknown'}; read: {s['read']}{via}): "
                       f"[{cell(s['title'])}]({s['url']}), {cell(s['publisher'])}")
        out.append("")
    return "\n".join(out).rstrip() + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run")
    ap.add_argument("--check", action="store_true", help="validate and print the table; write nothing")
    args = ap.parse_args()
    run = resolve_run(args.run)
    rubric = load_json(CONFIG / "rubric.json")
    reps = [V.validate_file("sources", run / "sources.json", run), V.validate_file("scores", run / "scores.json", run)]
    for rp in reps:
        rp.print()
    if any(rp.errors for rp in reps):
        print("error: fix the inputs above before ranking", file=sys.stderr)
        return 1
    sources = load_json(run / "sources.json")
    scores = load_json(run / "scores.json")
    rows, run_date = compute(run, sources, scores, rubric)
    md = render(run, rows, run_date, rubric, sources)
    if args.check:
        print("\n".join(md.split("## Ranking", 1)[1].split("## Recommendation")[0].strip().splitlines()))
        return 0
    (run / "ranking.md").write_text(md, encoding="utf-8")
    write_json(run / "ranking.json", {
        "schema_version": 1, "run_date": run_date, "rubric_version": rubric["version"],
        "inputs_sha256": ranking_inputs(run),
        "ranking": [{k: r[k] for k in ("rank", "id", "title", "slug", "total", "eligible", "gate_reasons", "scores",
                                         "unknown", "newest_primary", "days")} for r in rows]})
    print(f"wrote {rel(run / 'ranking.md')} and ranking.json ({len(rows)} topics)")
    for r in rows:
        print(f"  {r['rank']}. {r['id']} {r['total']:5.1f} {'eligible' if r['eligible'] else 'EXCLUDED'}  {r['title']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
