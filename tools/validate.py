#!/usr/bin/env python3
"""Validate the JSON artifacts of a run against the project's schemas and source policy.

Usage:
  python3 tools/validate.py runs/<run>                 # every artifact that exists in the run
  python3 tools/validate.py --kind sources FILE         # one file: sources | scores | references | review | verdict |
                                                        #   approval | symbol_ledger

Exit status: 0 = no errors (warnings allowed), 1 = errors. Standard library only.
The schemas are documented in .claude/skills/*/SKILL.md and README.md; this file is the executable version.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import CONFIG, SLUG_RE, load_json, parse_date, rel  # noqa: E402

SOURCE_KINDS_PRIMARY = {"paper", "preprint", "official_post", "code", "dataset"}
SOURCE_KINDS_SECONDARY = {"news", "press_release", "video", "social", "other"}
READ_LEVELS = {"full", "abstract", "search_abstract", "snippet", "unreadable"}   # defined in source-policy.md
CLAIM_STATUS = {"verified", "provisional", "unverified", "disputed"}
CLAIM_ROLES = {"central", "limitation", "context"}
SOURCE_RELATIONS = {"subject", "prior_work", "context"}
UNREADABLE_CAUSES = {"network_policy", "paywall", "login", "http_error", "timeout", "not_found", "other"}
COVERAGE = {"new", "partly_covered", "covered"}
STOP = set("a an and the of for in on to with by from at as is are be via its it this that new using how why what "
           "robot robots robotics control learning".split())


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z][a-z0-9-]{2,}", (text or "").lower()) if w not in STOP}
REF_TYPES = {"article", "inproceedings", "book", "chapter", "thesis", "preprint", "web", "press", "video",
             "software", "dataset", "report"}
REF_STATUS = {"verified", "secondary_only", "unverified"}
SEVERITIES = {"blocker", "major", "minor", "nit"}
CONFIDENCE = {"high", "medium", "low"}
VERDICTS = {"confirmed", "refuted", "uncertain"}
NOT_REVIEWS = {"summary.json", "check_html.json", "resolutions.json", "lint_html.json", "frames.json", "gates.json",
               "symbol_ledger.json"}           # pipeline records at the top of review/, not reviewer reports; the
                                               # reviewers' own scripts and tool outputs live in review/checks/
REVIEW_SETS = ("video", "final_cut", "series_plan")         # review/<set>/ hold reports in the same format
ID_PREFIX = {"technical-correctness-reviewer": "TC", "reference-verifier": "REF", "presentation-reviewer": "PRES",
             "claims-red-team": "RT", "linear-reader": "LR", "video-design-reviewer": "VD",
             "final-cut-reviewer": "FC", "series-red-team": "SRT"}   # each reviewer's finding ids: PREFIX-n
LEDGER_CHANGES = {"none", "announced", "unannounced"}         # how a later use of a symbol relates to the first
DOI_RE = re.compile(r"^10\.\d{4,9}/\S+$")
ARXIV_RE = re.compile(r"^(\d{4}\.\d{4,5}|[a-z\-]+(\.[A-Z]{2})?/\d{7})(v\d+)?$")
REF_KEY_RE = re.compile(r"^[a-z][a-z0-9]*$")


class Report:
    def __init__(self, label: str):
        self.label = label
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def err(self, msg: str) -> None:
        self.errors.append(msg)

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)

    def print(self) -> None:
        status = "FAIL" if self.errors else "ok"
        print(f"[{status}] {self.label}: {len(self.errors)} error(s), {len(self.warnings)} warning(s)")
        for e in self.errors:
            print(f"  ERROR   {e}")
        for w in self.warnings:
            print(f"  warning {w}")


def _str(x, maxlen: int | None = None) -> bool:
    return isinstance(x, str) and x.strip() != "" and (maxlen is None or len(x) <= maxlen)


def _date(rep: Report, where: str, value, allow_null: bool = False):
    if value is None and allow_null:
        return None
    try:
        return parse_date(value)
    except (ValueError, TypeError) as exc:
        rep.err(f"{where}: {exc}")
        return None


# --------------------------------------------------------------------------- sources.json
def validate_sources(data, rep: Report, scout_cfg: dict | None = None, run_dir: Path | None = None) -> None:
    scout_cfg = scout_cfg or {}
    if not isinstance(data, dict):
        rep.err("top level must be an object")
        return
    if data.get("schema_version") != 1:
        rep.err("schema_version must be 1")
    run_date = _date(rep, "run_date", data.get("run_date"))
    window = data.get("window_days")
    if not isinstance(window, int) or window <= 0:
        rep.err("window_days must be a positive integer")
        window = None
    run_json = (run_dir / "run.json") if run_dir else None
    if run_json is not None and run_json.exists() and window is not None:
        want = json.loads(run_json.read_text(encoding="utf-8")).get("window_days")
        if want and want != window:
            rep.err(f"window_days {window} differs from the run's window ({want} days in run.json, set by "
                    "tools/run.py new --window-days); the run's window is the one that counts")
    queries = data.get("queries")
    if not isinstance(queries, list) or not queries or not all(_str(q) for q in queries):
        rep.err("queries must list every search query actually run (non-empty strings)")
    unreadable = data.get("unreadable", [])
    if not isinstance(unreadable, list):
        rep.err("unreadable must be a list of {url, reason}")
    else:
        for i, u in enumerate(unreadable):
            if not (isinstance(u, dict) and _str(u.get("url")) and _str(u.get("reason"))):
                rep.err(f"unreadable[{i}] needs url and reason")
            elif u.get("cause") is None:
                rep.warn(f"unreadable[{i}]: add a cause ({', '.join(sorted(UNREADABLE_CAUSES))}) so the ranking can "
                         "tell a blocked network from a problem with the topic")
            elif u["cause"] not in UNREADABLE_CAUSES:
                rep.err(f"unreadable[{i}].cause must be one of {sorted(UNREADABLE_CAUSES)}")
    covered = []
    cov_p = (run_dir / "covered.json") if run_dir else None
    if cov_p is not None and cov_p.exists():
        covered = json.loads(cov_p.read_text(encoding="utf-8")).get("items", [])
    cands = data.get("candidates")
    if not isinstance(cands, list) or not cands:
        rep.err("candidates must be a non-empty list")
        return
    max_c = scout_cfg.get("max_candidates", 12)
    min_c = scout_cfg.get("min_candidates", 1)
    if len(cands) > max_c:
        rep.err(f"{len(cands)} candidates; config/scout.json allows at most {max_c}")
    if len(cands) < min_c:
        rep.warn(f"only {len(cands)} candidate(s); config/scout.json asks for at least {min_c}")

    seen_tid, seen_slug, seen_sid, url_owner = set(), set(), set(), {}
    for ci, c in enumerate(cands):
        where = f"candidates[{ci}]"
        if not isinstance(c, dict):
            rep.err(f"{where} must be an object")
            continue
        tid = c.get("id")
        if not (isinstance(tid, str) and re.match(r"^T\d+$", tid)):
            rep.err(f"{where}.id must look like T1, T2, ...")
        elif tid in seen_tid:
            rep.err(f"duplicate candidate id {tid}")
        seen_tid.add(tid)
        where = f"{tid or where}"
        if not _str(c.get("title"), 160):
            rep.err(f"{where}.title must be a non-empty string of at most 160 characters")
        slug = c.get("slug")
        if not (isinstance(slug, str) and SLUG_RE.match(slug) and len(slug) <= 60):
            rep.err(f"{where}.slug must be kebab-case, at most 60 characters")
        elif slug in seen_slug:
            rep.err(f"duplicate slug {slug}")
        seen_slug.add(slug)
        summary = c.get("summary", "")
        if not _str(summary):
            rep.err(f"{where}.summary is required (two or three sentences in our own words)")
        elif len(summary) > 900:
            rep.err(f"{where}.summary has {len(summary)} characters; keep it under 700 and in our own words")
        elif len(summary) > 700:
            rep.warn(f"{where}.summary has {len(summary)} characters; aim for under 700")
        queries = c.get("search_queries", [])
        if not (isinstance(queries, list) and len(queries) <= 4 and
                all(isinstance(q, str) and 2 <= len(q.strip()) <= 80 for q in queries)):
            rep.err(f"{where}.search_queries must be a list of at most 4 phrases (2-80 characters) a viewer would type")
        hooks = c.get("visual_hooks", [])
        if not isinstance(hooks, list) or not all(_str(h) for h in hooks):
            rep.err(f"{where}.visual_hooks must be a list of strings")

        sources = c.get("sources")
        if not isinstance(sources, list) or not sources:
            rep.err(f"{where}.sources must be a non-empty list")
            sources = []
        sid_info = {}
        newest_subject = None
        for si, s in enumerate(sources):
            sw = f"{where}.sources[{si}]"
            if not isinstance(s, dict):
                rep.err(f"{sw} must be an object")
                continue
            sid = s.get("id")
            if not (isinstance(sid, str) and re.match(r"^S\d+$", sid)):
                rep.err(f"{sw}.id must look like S1, S2, ...")
            elif sid in seen_sid:
                rep.err(f"duplicate source id {sid} (source ids are unique across the file)")
            seen_sid.add(sid)
            sw = f"{where}/{sid or si}"
            url = s.get("url")
            if not (isinstance(url, str) and re.match(r"^https?://[^\s]+$", url)):
                rep.err(f"{sw}.url must be an http(s) URL")
            else:
                if url.startswith("http://"):
                    rep.warn(f"{sw}.url uses http; prefer https")
                if url in url_owner and url_owner[url] != tid:
                    rep.warn(f"{sw}: URL also used by {url_owner[url]}")
                url_owner.setdefault(url, tid)
            for f in ("title", "publisher"):
                if not _str(s.get(f)):
                    rep.err(f"{sw}.{f} is required")
            kind = s.get("kind")
            if kind not in SOURCE_KINDS_PRIMARY | SOURCE_KINDS_SECONDARY:
                rep.err(f"{sw}.kind must be one of {sorted(SOURCE_KINDS_PRIMARY | SOURCE_KINDS_SECONDARY)}")
            primary = s.get("primary")
            if not isinstance(primary, bool):
                rep.err(f"{sw}.primary must be true or false")
            elif primary and kind in SOURCE_KINDS_SECONDARY:
                rep.err(f"{sw}: kind '{kind}' cannot be a primary source (primary = paper, preprint, official_post, code, dataset)")
            read = s.get("read")
            if read not in READ_LEVELS:
                rep.err(f"{sw}.read must be one of {sorted(READ_LEVELS)} (what was actually read)")
            relation = s.get("relation")
            if relation is None and primary is True:
                rep.err(f"{sw}.relation is required for a primary source: 'subject' (the source presents this "
                        "candidate's work), 'prior_work' (earlier work, e.g. for novelty) or 'context'")
            elif relation is not None and relation not in SOURCE_RELATIONS:
                rep.err(f"{sw}.relation must be one of {sorted(SOURCE_RELATIONS)}")
            via = s.get("via")
            if via is not None and not (isinstance(via, str) and re.match(r"^https?://\S+$", via)):
                rep.err(f"{sw}.via must be the http(s) URL where the text was actually read (a metadata endpoint, "
                        "index or the authors' page) when it was not the source's own URL")
            pub = _date(rep, f"{sw}.published", s.get("published"), allow_null=True)
            acc = _date(rep, f"{sw}.accessed", s.get("accessed"))
            if run_date and pub and pub > run_date:
                rep.err(f"{sw}.published {pub} is after the run date {run_date}")
            if run_date and acc and not (run_date <= acc <= run_date + dt.timedelta(days=7)):
                rep.warn(f"{sw}.accessed {acc} is not within a week after the run date")
            subject = primary is True and (relation or "subject") == "subject"
            sid_info[sid] = (primary is True, read, subject)
            if subject and pub and (newest_subject is None or pub > newest_subject):
                newest_subject = pub
        if not any(info[2] for info in sid_info.values()):
            rep.warn(f"{where}: no primary source about the candidate itself (relation 'subject'); prior work does not "
                     "count, so the ranking gate will exclude it from recommendation")
        elif newest_subject is None:
            rep.warn(f"{where}: no subject primary source has a publication date (recency will be unknown)")
        elif run_date and window and (run_date - newest_subject).days > window:
            rep.err(f"{where}: its newest subject primary source ({newest_subject}) is older than the run's "
                    f"{window}-day window; drop the candidate, or start the run with a wider window "
                    "(tools/run.py new --window-days N)")
        cov = c.get("coverage")
        if covered:
            if not isinstance(cov, dict) or cov.get("status") not in COVERAGE:
                rep.err(f"{where}.coverage must say whether the channel already covers it: "
                        f'{{"status": "new"|"partly_covered"|"covered", "by": [...], "note": "..."}} (covered.json)')
            else:
                mine = _words(f"{c.get('title', '')} {slug or ''}")
                close = [it["title"] for it in covered if len(mine & set(it.get("keywords", []))) >= 3]
                if close and cov["status"] == "new":
                    rep.warn(f"{where}: shares keywords with already covered '{close[0][:70]}'; check coverage")
        elif cov is not None and (not isinstance(cov, dict) or cov.get("status") not in COVERAGE):
            rep.err(f"{where}.coverage.status must be one of {sorted(COVERAGE)}")

        claims = c.get("central_claims")
        if not isinstance(claims, list) or not claims:
            rep.err(f"{where}.central_claims must list the claims the topic rests on")
            claims = []
        for k, cl in enumerate(claims):
            cw = f"{where}.central_claims[{k}]"
            if not isinstance(cl, dict) or not _str(cl.get("claim")):
                rep.err(f"{cw} needs a claim")
                continue
            st = cl.get("status")
            if st not in CLAIM_STATUS:
                rep.err(f"{cw}.status must be one of {sorted(CLAIM_STATUS)}")
            role = cl.get("role")
            if role is None:
                rep.warn(f"{cw}: add a role (central, limitation or context); without one it counts as central")
            elif role not in CLAIM_ROLES:
                rep.err(f"{cw}.role must be one of {sorted(CLAIM_ROLES)}")
            sup = cl.get("support", [])
            if not isinstance(sup, list):
                rep.err(f"{cw}.support must be a list of source ids")
                sup = []
            for x in sup:
                if x not in sid_info:
                    rep.err(f"{cw}.support cites {x}, which is not a source of {where}")
            levels = {sid_info[x][1] for x in sup if x in sid_info and sid_info[x][0]}
            if st == "verified" and not levels & {"full", "abstract"}:
                rep.err(f"{cw} is 'verified' but no supporting source is primary and read in full or abstract")
            if st == "provisional":
                if not levels & {"search_abstract", "full", "abstract"}:
                    rep.err(f"{cw} is 'provisional' but no supporting primary source was read even at "
                            "search_abstract level (a snippet is not enough)")
                elif levels & {"full", "abstract"}:
                    rep.warn(f"{cw} is 'provisional' although a supporting primary source was read in full or "
                             "abstract: mark it verified if the source states it")
            if st in ("unverified", "disputed") and (role or "central") == "central":
                rep.warn(f"{cw} is {st} and central: {cl.get('claim')[:90]}")


# --------------------------------------------------------------------------- scores.json
def validate_scores(data, rep: Report, sources: dict | None, rubric: dict) -> None:
    if not isinstance(data, dict) or data.get("schema_version") != 1:
        rep.err("scores.json must be an object with schema_version 1")
        return
    topics = data.get("topics")
    if not isinstance(topics, list) or not topics:
        rep.err("topics must be a non-empty list")
        return
    judged = [k for k, v in rubric["criteria"].items() if not v.get("computed")]
    computed = [k for k, v in rubric["criteria"].items() if v.get("computed")]
    penalties = list(rubric.get("penalty", {}))
    must_cite = {"novelty", "hype_risk"}
    cand_sources = {}
    if sources:
        for c in sources.get("candidates", []):
            cand_sources[c.get("id")] = {s.get("id") for s in c.get("sources", []) if isinstance(s, dict)}
    seen = set()
    for i, t in enumerate(topics):
        tid = t.get("id") if isinstance(t, dict) else None
        where = tid or f"topics[{i}]"
        if not isinstance(t, dict) or not isinstance(tid, str):
            rep.err(f"{where} must be an object with an id")
            continue
        if tid in seen:
            rep.err(f"duplicate topic {tid}")
        seen.add(tid)
        if sources is not None and tid not in cand_sources:
            rep.err(f"{tid} is not a candidate in sources.json")
        sc = t.get("scores")
        if not isinstance(sc, dict):
            rep.err(f"{where}.scores must be an object")
            continue
        for k in computed:
            if k in sc:
                rep.err(f"{where}.scores.{k} must not be judged: it is computed from "
                        f"{'search data (tools/search_demand.py)' if rubric['criteria'][k].get('source') == 'search' else 'source dates'}")
        for k in judged + penalties:
            v = sc.get(k)
            if not isinstance(v, dict):
                rep.err(f"{where}.scores.{k} is missing")
                continue
            s = v.get("score")
            if not (isinstance(s, int) and not isinstance(s, bool) and 0 <= s <= 5):
                rep.err(f"{where}.scores.{k}.score must be an integer 0-5")
            if not (_str(v.get("why")) and len(v["why"]) >= 20):
                rep.err(f"{where}.scores.{k}.why must justify the score (at least one sentence)")
            cites = v.get("sources", [])
            if not isinstance(cites, list):
                rep.err(f"{where}.scores.{k}.sources must be a list of source ids")
                cites = []
            if k in must_cite and not cites:
                rep.err(f"{where}.scores.{k} must cite at least one source id")
            for x in cites:
                if tid in cand_sources and x not in cand_sources[tid]:
                    rep.err(f"{where}.scores.{k} cites {x}, which is not a source of {tid}")
        unknown = set(sc) - set(judged) - set(penalties) - set(computed)
        if unknown:
            rep.err(f"{where}.scores has unknown criteria {sorted(unknown)} (see config/rubric.json)")
        for f in ("proposed_angle", "animation_idea"):
            if not _str(t.get(f)):
                rep.err(f"{where}.{f} is required (one or two sentences)")
    missing = set(cand_sources) - seen
    if missing:
        rep.err(f"candidates without scores: {sorted(missing)}")


# --------------------------------------------------------------------------- references.json
def validate_references(data, rep: Report) -> None:
    if not isinstance(data, dict) or data.get("schema_version") != 1:
        rep.err("references.json must be an object with schema_version 1")
        return
    refs = data.get("references")
    if not isinstance(refs, list):
        rep.err("references must be a list")
        return
    keys = set()
    for i, r in enumerate(refs):
        key = r.get("key") if isinstance(r, dict) else None
        where = key or f"references[{i}]"
        if not isinstance(r, dict):
            rep.err(f"{where} must be an object")
            continue
        if not (isinstance(key, str) and REF_KEY_RE.match(key)):
            rep.err(f"{where}.key must be lowercase letters and digits, e.g. keerthi1988")
        elif key in keys:
            rep.err(f"duplicate reference key {key}")
        keys.add(key)
        if r.get("type") not in REF_TYPES:
            rep.err(f"{where}.type must be one of {sorted(REF_TYPES)}")
        authors = r.get("authors")
        if not (isinstance(authors, list) and authors and all(_str(a) for a in authors)):
            rep.err(f"{where}.authors must be a non-empty list (an organisation is fine for web pages)")
        if not _str(r.get("title")):
            rep.err(f"{where}.title is required")
        year = r.get("year")
        if not ((isinstance(year, int) and 1600 <= year <= 2100) or year == "n.d."):
            rep.err(f"{where}.year must be an integer year or 'n.d.'")
        ver = r.get("verification")
        if not isinstance(ver, dict) or ver.get("status") not in REF_STATUS:
            rep.err(f"{where}.verification.status must be one of {sorted(REF_STATUS)}")
            ver = {}
        status = ver.get("status")
        checked = ver.get("checked_against", [])
        if status in ("verified", "secondary_only") and not (isinstance(checked, list) and checked):
            rep.err(f"{where}.verification.checked_against must list the records actually seen")
        if status == "unverified":
            rep.warn(f"{where} is unverified (the strict build and lint refuse it)")
        doi = r.get("doi")
        if doi is not None:
            if not (isinstance(doi, str) and DOI_RE.match(doi)):
                rep.err(f"{where}.doi is malformed: {doi!r}")
            if not _str(ver.get("doi_seen_in")):
                rep.err(f"{where}.doi given without verification.doi_seen_in: never invent or infer a DOI")
        arx = r.get("arxiv")
        if arx is not None and not (isinstance(arx, str) and ARXIV_RE.match(arx)):
            rep.err(f"{where}.arxiv is malformed: {arx!r}")
        url = r.get("url")
        if url is not None and not (isinstance(url, str) and re.match(r"^https?://\S+$", url)):
            rep.err(f"{where}.url must be an http(s) URL")
        if r.get("type") in ("web", "press", "video", "software", "dataset") and not url:
            rep.err(f"{where}: a {r.get('type')} reference needs a url")
        if url and r.get("type") in ("web", "press", "video") and not r.get("accessed"):
            rep.err(f"{where}: web sources need an accessed date")
        if r.get("accessed") is not None:
            _date(rep, f"{where}.accessed", r.get("accessed"))


# --------------------------------------------------------------------------- review/*.json
def validate_review(data, rep: Report) -> None:
    if not isinstance(data, dict) or ("reviewer" not in data and "findings" not in data):
        rep.err("not a reviewer report: only reports and the pipeline's records sit at the top of review/; "
                "tool outputs and a reviewer's own files go in review/checks/ (named tc_*, ref_*, pres_*, rt_*, lr_*)")
        return
    if data.get("schema_version") != 1:
        rep.err("review file must be an object with schema_version 1")
        return
    if not _str(data.get("reviewer")):
        rep.err("reviewer is required")
    if not _str(data.get("summary")):
        rep.err("summary is required (two or three sentences)")
    checks = data.get("checks_run", [])
    if not isinstance(checks, list) or not all(isinstance(c, dict) and _str(c.get("command")) and _str(c.get("result"))
                                               for c in checks):
        rep.err("checks_run must be a list of {command, result} (evidence, not assertions)")
    findings = data.get("findings")
    if not isinstance(findings, list):
        rep.err("findings must be a list (empty if nothing was found)")
        return
    ids = set()
    for i, f in enumerate(findings):
        fid = f.get("id") if isinstance(f, dict) else None
        where = fid or f"findings[{i}]"
        if not isinstance(f, dict) or not (isinstance(fid, str) and re.match(r"^[A-Z]{2,4}-\d+$", fid)):
            rep.err(f"{where}: id must look like TC-1, REF-2, PRES-3, RT-4, LR-5")
            continue
        want = ID_PREFIX.get(data.get("reviewer"))
        if want and fid.split("-")[0] != want:
            rep.err(f"{where}: {data['reviewer']} findings use {want}-n ids")
        if fid in ids:
            rep.err(f"duplicate finding id {fid}")
        ids.add(fid)
        if f.get("severity") not in SEVERITIES:
            rep.err(f"{where}.severity must be one of {sorted(SEVERITIES)}")
        if f.get("confidence") not in CONFIDENCE:
            rep.err(f"{where}.confidence must be one of {sorted(CONFIDENCE)}")
        for k in ("location", "issue", "evidence", "suggested_fix"):
            if not _str(f.get(k)):
                rep.err(f"{where}.{k} is required")
        if fid.startswith("FC-") and not (isinstance(f.get("time_s"), (int, float)) and f["time_s"] >= 0):
            rep.err(f"{where}: a final-cut finding needs time_s, the time in the final video in seconds")


def validate_symbol_ledger(data, rep: Report) -> None:
    """review/symbol_ledger.json, written by the presentation-reviewer: every symbol's meaning per section, and how
    each later use relates to the first (format in .claude/skills/explainer-review/reviewer-contract.md)."""
    if not isinstance(data, dict) or data.get("schema_version") != 1:
        rep.err("symbol_ledger.json must be an object with schema_version 1")
        return
    if not _str(data.get("reviewer")):
        rep.err("reviewer is required")
    symbols = data.get("symbols")
    if not isinstance(symbols, list) or not symbols:
        rep.err("symbols must be a non-empty list (every symbol and named object of the explainer)")
        return
    for i, sym in enumerate(symbols):
        name = sym.get("symbol") if isinstance(sym, dict) else None
        where = f"symbols[{i}]" + (f" ({name})" if _str(name) else "")
        if not isinstance(sym, dict) or not _str(name):
            rep.err(f"{where}: symbol is required")
            continue
        uses = sym.get("uses")
        if not isinstance(uses, list) or not uses:
            rep.err(f"{where}: uses must be a non-empty list, in document order")
            continue
        for j, u in enumerate(uses):
            uw = f"{where}.uses[{j}]"
            if not isinstance(u, dict):
                rep.err(f"{uw} must be an object")
                continue
            for k in ("section", "location", "meaning"):
                if not _str(u.get(k)):
                    rep.err(f"{uw}.{k} is required")
            if u.get("defined_from") is not None and not _str(u.get("defined_from")):
                rep.err(f"{uw}.defined_from must be a non-empty string when given")
            change = u.get("change")
            if j == 0 and change != "first":
                rep.err(f"{uw}.change must be 'first' (the first use defines the symbol)")
            elif j > 0 and change not in LEDGER_CHANGES:
                rep.err(f"{uw}.change must be one of {sorted(LEDGER_CHANGES)}")
        silent = [u for u in uses[1:] if isinstance(u, dict) and u.get("change") == "unannounced"]
        finding = sym.get("finding")
        if silent and not (_str(finding) and re.match(r"^(PRES|LR)-\d+$", finding)):
            rep.err(f"{where}: an unannounced change of meaning must name its finding (finding: PRES-n or LR-n)")
        elif finding is not None and not (_str(finding) and re.match(r"^[A-Z]{2,4}-\d+$", finding)):
            rep.err(f"{where}: finding must be a finding id such as PRES-3")


def ledger_findings(run: Path, rep: Report) -> None:
    """Every finding the ledger names must exist in the presentation-reviewer's or the linear-reader's report."""
    lp = run / "review" / "symbol_ledger.json"
    try:
        ledger = _load(lp)
    except (FileNotFoundError, json.JSONDecodeError):
        return
    ids = set()
    for name in ("presentation-reviewer", "linear-reader"):
        try:
            ids |= {f.get("id") for f in _load(run / "review" / f"{name}.json").get("findings", [])
                    if isinstance(f, dict)}
        except (FileNotFoundError, json.JSONDecodeError, AttributeError):
            continue
    for sym in ledger.get("symbols", []) if isinstance(ledger, dict) else []:
        fid = sym.get("finding") if isinstance(sym, dict) else None
        if _str(fid) and fid not in ids:
            rep.err(f"symbol {sym.get('symbol')!r}: finding {fid} is not in presentation-reviewer.json or "
                    "linear-reader.json")


def validate_verdict(data, rep: Report) -> None:
    """review/verify/<finding-id>.json, written by the finding-verifier subagent."""
    if not isinstance(data, dict) or data.get("schema_version") != 1:
        rep.err("verdict file must be an object with schema_version 1")
        return
    if not (_str(data.get("finding")) and re.match(r"^[A-Z]{2,4}-\d+$", data["finding"])):
        rep.err("finding must be the id of the finding checked, e.g. TC-3")
    if data.get("verdict") not in VERDICTS:
        rep.err(f"verdict must be one of {sorted(VERDICTS)}")
    if not _str(data.get("reason")):
        rep.err("reason is required (what was re-checked and what it showed)")
    checks = data.get("checks_run", [])
    if not isinstance(checks, list) or not all(isinstance(c, dict) and _str(c.get("command")) and _str(c.get("result"))
                                               for c in checks):
        rep.err("checks_run must be a list of {command, result}")


def validate_approval(data, rep: Report) -> None:
    need = ("topic_id", "title", "slug", "approved_at", "via", "ranking_sha256")
    if not isinstance(data, dict) or data.get("schema_version") != 1:
        rep.err("approval.json must be an object with schema_version 1")
        return
    for k in need:
        if not _str(data.get(k)):
            rep.err(f"approval.json: {k} is missing")


# --------------------------------------------------------------------------- driver
def _load(path: Path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def validate_file(kind: str, path: Path, run_dir: Path | None = None) -> Report:
    rep = Report(f"{kind}: {rel(path)}")
    try:
        data = _load(path)
    except FileNotFoundError:
        rep.err("file not found")
        return rep
    except json.JSONDecodeError as exc:
        rep.err(f"invalid JSON: {exc}")
        return rep
    if kind == "sources":
        scout = load_json(CONFIG / "scout.json")
        validate_sources(data, rep, scout, run_dir or path.parent)
    elif kind == "scores":
        rubric = load_json(CONFIG / "rubric.json")
        src = None
        sp = (run_dir or path.parent) / "sources.json"
        if sp.exists():
            try:
                src = _load(sp)
            except json.JSONDecodeError:
                rep.err("sources.json next to scores.json is not valid JSON")
        validate_scores(data, rep, src, rubric)
    elif kind == "references":
        validate_references(data, rep)
    elif kind == "review":
        validate_review(data, rep)
    elif kind == "verdict":
        validate_verdict(data, rep)
    elif kind == "approval":
        validate_approval(data, rep)
    elif kind == "symbol_ledger":
        validate_symbol_ledger(data, rep)
    else:
        rep.err(f"unknown kind {kind}")
    return rep


def kind_for(path: Path) -> str | None:
    name = path.name
    if name in ("sources.json", "scores.json", "references.json", "approval.json"):
        return name.split(".")[0]
    if name == "symbol_ledger.json" and path.parent.name == "review":
        return "symbol_ledger"
    if path.parent.name == "verify" and name.endswith(".json") and (
            path.parent.parent.name == "review" or path.parent.parent.parent.name == "review"):
        return "verdict"
    if name.endswith(".json") and name not in NOT_REVIEWS and (
            path.parent.name == "review" or (path.parent.name in REVIEW_SETS and path.parent.parent.name == "review")):
        return "review"
    return None


def validate_run(run: Path) -> list[Report]:
    reports = []
    for name in ("sources.json", "scores.json", "references.json", "approval.json"):
        p = run / name
        if p.exists():
            reports.append(validate_file(name.split(".")[0], p, run))
    rv = run / "review"
    if rv.is_dir():
        files = sorted(rv.glob("*.json")) + sorted((rv / "verify").glob("*.json"))
        for sub in REVIEW_SETS:
            files += sorted((rv / sub).glob("*.json")) + sorted((rv / sub / "verify").glob("*.json"))
        for p in files:
            k = kind_for(p)
            if k:
                reports.append(validate_file(k, p, run))
        if (rv / "symbol_ledger.json").exists():            # across files: the ledger's findings exist
            xr = Report(f"symbol ledger findings: {rel(rv / 'symbol_ledger.json')}")
            ledger_findings(run, xr)
            if xr.errors:
                reports.append(xr)
    return reports


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("target", help="run directory, or a file with --kind")
    ap.add_argument("--kind", choices=["sources", "scores", "references", "review", "verdict", "approval",
                                       "symbol_ledger"])
    args = ap.parse_args()
    target = Path(args.target)
    if args.kind:
        reports = [validate_file(args.kind, target)]
    elif target.is_dir():
        reports = validate_run(target)
        if not reports:
            print(f"nothing to validate in {rel(target)}")
    else:
        k = kind_for(target)
        if not k:
            print("error: pass --kind for this file", file=sys.stderr)
            return 1
        reports = [validate_file(k, target)]
    for r in reports:
        r.print()
    return 1 if any(r.errors for r in reports) else 0


if __name__ == "__main__":
    sys.exit(main())
