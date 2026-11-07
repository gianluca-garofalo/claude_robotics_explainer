#!/usr/bin/env python3
"""Validate a run's JSON files against schemas/*.json, then the uniqueness, cross-file, date and policy rules.

Usage:
  python3 tools/validate.py runs/<run>         # every file that exists in the run
  python3 tools/validate.py --kind KIND FILE   # KIND: sources scores references review verdict approval symbol_ledger
Exit status 1 on errors (warnings allowed).
"""
from __future__ import annotations

import argparse
import datetime as dt
import functools
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import CONFIG, REPO, load_json, parse_date, rel  # noqa: E402

try:
    from jsonschema import Draft202012Validator, validators
    from referencing import Registry, Resource
except ImportError:                  # hooks import this module under any python3: schema_errors says what is missing
    Draft202012Validator = None

KINDS = ("sources", "scores", "references", "review", "verdict", "approval", "symbol_ledger")
NOT_REVIEWS = {"summary.json", "check_html.json", "resolutions.json", "lint_html.json", "frames.json", "gates.json",
               "symbol_ledger.json"}           # pipeline records at the top of review/; tool outputs go in review/checks/
REVIEW_SETS = ("video", "final_cut", "series_plan")         # review/<set>/ hold reports in the same format
ID_PREFIX = {"technical-correctness-reviewer": "TC", "reference-verifier": "REF", "presentation-reviewer": "PRES",
             "claims-red-team": "RT", "linear-reader": "LR", "video-design-reviewer": "VD",
             "final-cut-reviewer": "FC", "series-red-team": "SRT"}   # each reviewer's finding ids: PREFIX-n
STOP = set("a an and the of for in on to with by from at as is are be via its it this that new using how why what "
           "robot robots robotics control learning".split())
NOUNS = {"object": "an object", "array": "a list", "string": "a string", "integer": "an integer", "number": "a number",
         "boolean": "true or false", "null": "null"}


@dataclass
class Report:
    label: str
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def err(self, msg: str) -> None:
        self.errors.append(msg)

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)

    def print(self) -> None:
        print(f"[{'FAIL' if self.errors else 'ok'}] {self.label}: {len(self.errors)} error(s), "
              f"{len(self.warnings)} warning(s)")
        for line in [f"  ERROR   {e}" for e in self.errors] + [f"  warning {w}" for w in self.warnings]:
            print(line)


@functools.cache
def schema(name: str) -> dict:
    return json.loads((REPO / "schemas" / f"{name}.json").read_text(encoding="utf-8"))


@functools.cache
def _validator(name: str):
    registry = Registry().with_resources((p.name, Resource.from_contents(schema(p.stem)))
                                         for p in (REPO / "schemas").glob("*.json"))
    # JSON Schema counts 1.0 as an integer; the project's files never did (nor true)
    types = Draft202012Validator.TYPE_CHECKER.redefine("integer", lambda _, x: type(x) is int)
    return validators.extend(Draft202012Validator, type_checker=types)(
        schema(name), registry=registry, format_checker=Draft202012Validator.FORMAT_CHECKER)


def schema_errors(name: str, data) -> list[str]:
    """data checked against schemas/<name>.json: '<JSON path> <problem> (<description>)' per error."""
    if Draft202012Validator is None:
        return ["jsonschema is not installed: pip install -r requirements-tools.txt"]
    errors = _validator(name).iter_errors(data)
    return [_message(e) for e in sorted(errors, key=lambda e: [(type(p) is str, p) for p in e.absolute_path])]


def _message(e) -> str:
    rule, want, path, sch = e.validator, e.validator_value, e.json_path, e.schema
    if rule == "required":
        name = next(p for p in want if e.message.startswith(f"{p!r} "))
        path, sch, problem = f"{path}.{name}", sch.get("properties", {}).get(name, {}), "is required"
    elif rule == "type":
        problem = "must be " + " or ".join(NOUNS[t] for t in ([want] if isinstance(want, str) else want))
    elif rule == "enum":
        problem = f"must be one of {sorted(v for v in want if v is not None)}"
    elif rule == "const":
        problem = f"must be {want!r}" if isinstance(want, str) else f"must be {json.dumps(want)}"
    elif rule == "pattern":
        problem = "must not be blank" if want == r"\S" else f"must match {want}"
    elif rule == "format":
        problem = "must be an ISO date (YYYY-MM-DD)" if want == "date" else f"must be a valid {want}"
    elif rule in ("minItems", "minLength", "maxItems", "maxLength"):
        low, unit = rule.startswith("min"), "items" if rule.endswith("Items") else "characters"
        problem = ("must not be empty" if low and want == 1 else
                   f"has {len(e.instance)} {unit}; {'at least' if low else 'at most'} {want}")
    elif rule in ("minimum", "maximum"):
        problem = f"must be {'at least' if rule == 'minimum' else 'at most'} {want}"
    else:
        problem = "is not allowed" if rule == "not" else "is not valid"
    note = sch.get("description") if isinstance(sch, dict) else None
    return f"{path} {problem}" + (f" ({note})" if note else "")


def _day(value) -> dt.date | None:
    try:
        return parse_date(value)
    except (TypeError, ValueError):
        return None


def _items(seq) -> list[tuple[int, dict]]:
    return [(i, x) for i, x in enumerate(seq) if isinstance(x, dict)] if isinstance(seq, list) else []


def _at(*parts) -> str:
    return "$" + "".join(f"[{p}]" if isinstance(p, int) else f".{p}" for p in parts)


def _unique(rep: Report, seen: set, value, where: str, what: str, note: str = "") -> None:
    if isinstance(value, str):
        if value in seen:
            rep.err(f"{where}: duplicate {what} {value}{note}")
        seen.add(value)


# --------------------------------------------------------------------------- rules beyond the schemas
def validate_sources(data, rep: Report, scout_cfg: dict | None = None, run_dir: Path | None = None) -> None:
    rep.errors += schema_errors("sources", data)
    if not isinstance(data, dict):
        return
    scout_cfg, run_date, window = scout_cfg or {}, _day(data.get("run_date")), data.get("window_days")
    window = window if type(window) is int and window > 0 else None
    want = _load(run_dir / "run.json").get("window_days") if run_dir and (run_dir / "run.json").exists() else None
    if window and want and want != window:
        rep.err(f"$.window_days {window} differs from the run's window ({want} days in run.json, set by "
                "tools/run.py new --window-days); the run's window is the one that counts")
    causes = ", ".join(c for c in schema("sources")["$defs"]["unreadable"]["properties"]["cause"]["enum"] if c)
    for i, u in _items(data.get("unreadable")):
        if u.get("cause") is None:
            rep.warn(f"{_at('unreadable', i)}: add a cause ({causes}) so the ranking can tell a blocked network from "
                     "a problem with the topic")
    covered = (_load(run_dir / "covered.json").get("items", []) if run_dir and (run_dir / "covered.json").exists()
               else [])
    cands, most, least = data.get("candidates"), scout_cfg.get("max_candidates", 12), scout_cfg.get("min_candidates", 1)
    if not isinstance(cands, list) or not cands:
        return
    if len(cands) > most:
        rep.err(f"$.candidates: {len(cands)} candidates; config/scout.json allows at most {most}")
    if len(cands) < least:
        rep.warn(f"$.candidates: only {len(cands)} candidate(s); config/scout.json asks for at least {least}")
    tids, slugs, sids, url_owner = set(), set(), set(), {}
    for ci, c in _items(cands):
        at, tid, slug, summary = _at("candidates", ci), c.get("id"), c.get("slug"), c.get("summary")
        _unique(rep, tids, tid, f"{at}.id", "candidate id")
        _unique(rep, slugs, slug, f"{at}.slug", "slug")
        if isinstance(summary, str) and 700 < len(summary) <= 900:
            rep.warn(f"{at}.summary has {len(summary)} characters; aim for under 700")
        info, newest = {}, None                  # source id -> (primary, read, subject)
        for si, s in _items(c.get("sources")):
            sw, sid, url = f"{at}.sources[{si}]", s.get("id"), s.get("url")
            pub, acc, primary = _day(s.get("published")), _day(s.get("accessed")), s.get("primary") is True
            _unique(rep, sids, sid, f"{sw}.id", "source id", " (source ids are unique across the file)")
            if isinstance(url, str) and url.startswith("http://"):
                rep.warn(f"{sw}.url uses http; prefer https")
            if isinstance(url, str) and url_owner.setdefault(url, tid) != tid:
                rep.warn(f"{sw}: URL also used by {url_owner[url]}")
            if run_date and pub and pub > run_date:
                rep.err(f"{sw}.published {pub} is after the run date {run_date}")
            if run_date and acc and not run_date <= acc <= run_date + dt.timedelta(days=7):
                rep.warn(f"{sw}.accessed {acc} is not within a week after the run date")
            subject = primary and (s.get("relation") or "subject") == "subject"
            info[sid if isinstance(sid, str) else si] = (primary, str(s.get("read")), subject)
            if subject and pub and (newest is None or pub > newest):
                newest = pub
        if not any(v[2] for v in info.values()):
            rep.warn(f"{at}: no primary source about the candidate itself (relation 'subject'); prior work does not "
                     "count, so the ranking gate will exclude it from recommendation")
        elif newest is None:
            rep.warn(f"{at}: no subject primary source has a publication date (recency will be unknown)")
        elif run_date and window and (run_date - newest).days > window:
            rep.err(f"{at}: its newest subject primary source ({newest}) is older than the run's {window}-day window; "
                    "drop the candidate, or start the run with a wider window (tools/run.py new --window-days N)")
        cov = c.get("coverage")
        if covered and not isinstance(cov, dict):
            rep.err(f"{at}.coverage must say whether the channel already covers it: "
                    f'{{"status": "new"|"partly_covered"|"covered", "by": [...], "note": "..."}} (covered.json)')
        elif covered and cov.get("status") == "new":
            mine = set(re.findall(r"[a-z][a-z0-9-]{2,}", f"{c.get('title', '')} {slug or ''}".lower())) - STOP
            close = [it["title"] for it in covered if len(mine & set(it.get("keywords", []))) >= 3]
            if close:
                rep.warn(f"{at}: shares keywords with already covered '{close[0][:70]}'; check coverage")
        for k, cl in _items(c.get("central_claims")):
            cw, st, role, sup = f"{at}.central_claims[{k}]", cl.get("status"), cl.get("role"), cl.get("support")
            sup = sup if isinstance(sup, list) else []
            if role is None:
                rep.warn(f"{cw}: add a role (central, limitation or context); without one it counts as central")
            for x in sup:
                if not (isinstance(x, str) and x in info):
                    rep.err(f"{cw}.support cites {x}, which is not a source of {tid or at}")
            levels = {info[x][1] for x in sup if isinstance(x, str) and x in info and info[x][0]}
            if st == "verified" and not levels & {"full", "abstract"}:
                rep.err(f"{cw} is 'verified' but no supporting source is primary and read in full or abstract")
            if st == "provisional" and not levels & {"search_abstract", "full", "abstract"}:
                rep.err(f"{cw} is 'provisional' but no supporting primary source was read even at search_abstract "
                        "level (a snippet is not enough)")
            elif st == "provisional" and levels & {"full", "abstract"}:
                rep.warn(f"{cw} is 'provisional' although a supporting primary source was read in full or abstract: "
                         "mark it verified if the source states it")
            if st in ("unverified", "disputed") and (role or "central") == "central":
                rep.warn(f"{cw} is {st} and central: {str(cl.get('claim'))[:90]}")


def validate_scores(data, rep: Report, sources: dict | None, rubric: dict) -> None:
    rep.errors += schema_errors("scores", data)
    crit = rubric["criteria"]
    judged = [k for k, v in crit.items() if not v.get("computed")] + list(rubric.get("penalty", {}))
    computed = [k for k, v in crit.items() if v.get("computed")]
    cand = {c["id"]: [s.get("id") for _, s in _items(c.get("sources"))]
            for _, c in _items(sources.get("candidates") if isinstance(sources, dict) else None)
            if isinstance(c.get("id"), str)}
    seen = set()
    for i, t in _items(data.get("topics") if isinstance(data, dict) else None):
        at, tid, sc = _at("topics", i), t.get("id"), t.get("scores")
        if not isinstance(tid, str):
            continue
        _unique(rep, seen, tid, f"{at}.id", "topic")
        if sources is not None and tid not in cand:
            rep.err(f"{at}.id: {tid} is not a candidate in sources.json")
        if not isinstance(sc, dict):
            continue
        for k in (k for k in computed if k in sc):
            rep.err(f"{at}.scores.{k} must not be judged: it is computed from " + (
                "search data (tools/search_demand.py)" if crit[k].get("source") == "search" else "source dates"))
        if set(sc) - set(judged) - set(computed):
            rep.err(f"{at}.scores has unknown criteria {sorted(set(sc) - set(judged) - set(computed))} "
                    "(see config/rubric.json)")
        for k in judged:
            cites = sc[k].get("sources", []) if isinstance(sc.get(k), dict) else []
            cites = cites if isinstance(cites, list) else []
            if k not in sc:
                rep.err(f"{at}.scores.{k} is missing")
            elif k in ("novelty", "hype_risk") and isinstance(sc[k], dict) and not cites:
                rep.err(f"{at}.scores.{k} must cite at least one source id")
            for x in (x for x in cites if tid in cand and x not in cand[tid]):
                rep.err(f"{at}.scores.{k} cites {x}, which is not a source of {tid}")
    if set(cand) - seen:
        rep.err(f"$.topics: candidates without scores: {sorted(set(cand) - seen)}")


def validate_references(data, rep: Report) -> None:
    rep.errors += schema_errors("references", data)
    keys = set()
    for i, r in _items(data.get("references") if isinstance(data, dict) else None):
        _unique(rep, keys, r.get("key"), f"{_at('references', i)}.key", "reference key")
        if isinstance(r.get("verification"), dict) and r["verification"].get("status") == "unverified":
            rep.warn(f"{_at('references', i)} is unverified (the strict build and lint refuse it)")


def validate_review(data, rep: Report) -> None:
    if not isinstance(data, dict) or ("reviewer" not in data and "findings" not in data):
        rep.err("not a reviewer report: only reports and the pipeline's records sit at the top of review/; "
                "tool outputs and a reviewer's own files go in review/checks/ (named tc_*, ref_*, pres_*, rt_*, lr_*)")
        return
    rep.errors += schema_errors("review", data)
    reviewer, ids = data.get("reviewer"), set()
    want = ID_PREFIX.get(reviewer) if isinstance(reviewer, str) else None
    for i, f in _items(data.get("findings")):
        fid = f.get("id")
        if want and isinstance(fid, str) and fid.split("-")[0] != want:
            rep.err(f"{_at('findings', i)}.id: {reviewer} findings use {want}-n ids")
        _unique(rep, ids, fid, f"{_at('findings', i)}.id", "finding id")


def validate_symbol_ledger(data, rep: Report) -> None:
    rep.errors += schema_errors("symbol_ledger", data)


def ledger_findings(run: Path, rep: Report) -> None:
    """Every finding the ledger names must exist in the presentation-reviewer's or the linear-reader's report."""
    try:
        ledger = _load(run / "review" / "symbol_ledger.json")
    except (FileNotFoundError, json.JSONDecodeError):
        return
    ids = set()
    for name in ("presentation-reviewer", "linear-reader"):
        for rp in sorted((run / "review").glob(f"{name}.json")) + sorted((run / "review").glob(f"{name}.round*.json")):
            try:
                ids |= {f.get("id") for _, f in _items(_load(rp).get("findings"))}
            except (json.JSONDecodeError, AttributeError):
                continue
    for i, sym in _items(ledger.get("symbols") if isinstance(ledger, dict) else None):
        fid = sym.get("finding")
        if isinstance(fid, str) and fid.strip() and fid not in ids:
            rep.err(f"{_at('symbols', i, 'finding')} ({sym.get('symbol')}): {fid} is not in presentation-reviewer.json "
                    "or linear-reader.json")


# --------------------------------------------------------------------------- driver
def _load(path: Path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def validate_file(kind: str, path: Path, run_dir: Path | None = None) -> Report:
    rep, run_dir = Report(f"{kind}: {rel(path)}"), run_dir or path.parent
    try:
        data = _load(path)
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        rep.err("file not found" if isinstance(exc, FileNotFoundError) else f"invalid JSON: {exc}")
        return rep
    if kind == "sources":
        validate_sources(data, rep, load_json(CONFIG / "scout.json"), run_dir)
    elif kind == "scores":
        try:
            src = _load(run_dir / "sources.json") if (run_dir / "sources.json").exists() else None
        except json.JSONDecodeError:
            src = None
            rep.err("sources.json next to scores.json is not valid JSON")
        validate_scores(data, rep, src, load_json(CONFIG / "rubric.json"))
    elif kind in ("references", "review", "symbol_ledger"):
        {"references": validate_references, "review": validate_review,
         "symbol_ledger": validate_symbol_ledger}[kind](data, rep)
    elif kind in KINDS:
        rep.errors += schema_errors(kind, data)
    else:
        rep.err(f"unknown kind {kind}")
    return rep


def kind_for(path: Path) -> str | None:
    name, parent = path.name, path.parent
    if name in ("sources.json", "scores.json", "references.json", "approval.json"):
        return name.split(".")[0]
    if name == "symbol_ledger.json" and parent.name == "review":
        return "symbol_ledger"
    if parent.name == "verify" and name.endswith(".json") and "review" in (parent.parent.name, parent.parent.parent.name):
        return "verdict"
    if name.endswith(".json") and name not in NOT_REVIEWS and (
            parent.name == "review" or (parent.name in REVIEW_SETS and parent.parent.name == "review")):
        return "review"
    return None


def validate_run(run: Path) -> list[Report]:
    reports = [validate_file(n.split(".")[0], run / n, run) for n in ("sources.json", "scores.json",
                                                                      "references.json", "approval.json")
               if (run / n).exists()]
    rv = run / "review"
    if rv.is_dir():
        files = []
        for d in (rv, *(rv / sub for sub in REVIEW_SETS)):
            files += sorted(d.glob("*.json")) + sorted((d / "verify").glob("*.json"))
        reports += [validate_file(k, p, run) for p in files if (k := kind_for(p))]
        if (rv / "symbol_ledger.json").exists():
            xr = Report(f"symbol ledger findings: {rel(rv / 'symbol_ledger.json')}")
            ledger_findings(run, xr)
            reports += [xr] if xr.errors else []
    return reports


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("target", help="run directory, or a file with --kind")
    ap.add_argument("--kind", choices=KINDS)
    args = ap.parse_args()
    target = Path(args.target)
    if args.kind or not target.is_dir():
        kind = args.kind or kind_for(target)
        if not kind:
            print("error: pass --kind for this file", file=sys.stderr)
            return 1
        reports = [validate_file(kind, target)]
    else:
        reports = validate_run(target)
        if not reports:
            print(f"nothing to validate in {rel(target)}")
    for r in reports:
        r.print()
    return 1 if any(r.errors for r in reports) else 0


if __name__ == "__main__":
    sys.exit(main())
