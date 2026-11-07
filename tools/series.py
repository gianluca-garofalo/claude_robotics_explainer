#!/usr/bin/env python3
"""Video series planned from a source explainer (series/<slug>/series.json), made one episode per run.

Usage:
  python3 tools/series.py plan <explainer run | sources/<name>> [--root runs] [--date D]   # a run for /plan-series
  python3 tools/series.py validate <series.json | series/<slug> | proposal.json>   # also prints the idea budget
  python3 tools/series.py write <proposal.json> [--plan PLAN.md] [--replace] [--allow-open-findings] [--root DIR]
  python3 tools/series.py approval|rehash series/<slug>
  python3 tools/series.py from-source sources/<name>                    # the source's series, in release order
  python3 tools/series.py list|next series/<slug> [--ledger site/ledger.json] [--root runs]
  python3 tools/series.py start series/<slug> --episode N|next [--ledger L] [--root runs] [--date D] [--by WHO]
                                [--fresh] [--require-approval]   # --fresh: no kept scenes
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent / "video"))
from _common import (CONFIG, REPO, SLUG_RE, TEMPLATES, die, load_json, parse_date, read_json, rel,  # noqa: E402
                     sha256_file, today_local, utc_now, write_json)
import idea_budget as IB  # noqa: E402

CLASS_RE = re.compile(r"^class ([A-Za-z_][A-Za-z0-9_]*)\([A-Za-z0-9_.]*Scene\):", re.M)
DONE = {"published", "staged"}          # in the ledger: start refuses the episode again
NEXT_DONE = DONE | {"delivered"}         # also skipped by `next`: its hand-over package exists in runs/
STOP_WORDS = {"a", "an", "and", "as", "at", "by", "for", "in", "is", "of", "on", "or", "the", "to", "with"}
VOLATILE = {"explainer_sha256", "created_at", "_proposal_notes", "provenance", "plan_approval"}   # not part of the plan
HELPERS = ("common.py", "voice.py", "reading_model.py")


def slugify(text: str, n: int = 40) -> str:
    """Lower-case words joined by hyphens, cut at a word boundary within n characters, without a trailing stop word."""
    words = [w for w in re.sub(r"[^a-z0-9]+", "-", re.sub(r"[*`_]", "", text).lower()).split("-") if w]
    out: list[str] = []
    for w in words:
        if len("-".join(out + [w])) > n:
            break
        out.append(w)
    while len(out) > 1 and out[-1] in STOP_WORDS:
        out.pop()
    return "-".join(out) or (words[0][:n] if words else "episode")


def _headings(explainer: Path) -> dict:
    import lint_html
    c = lint_html.Collector()
    c.feed(explainer.read_text(encoding="utf-8"))
    c.close()
    return c.headings


def section_ids(explainer: Path) -> dict[str, str]:
    """'6' -> 'sec-hj', '6.3' -> 'sec-scalar', from the numbered headings of the explainer."""
    out = {}
    for sid, (_, text, _) in _headings(explainer).items():
        m = re.match(r"^(\d+(?:\.\d+)*)\.?\s", text)
        if m and sid:
            out.setdefault(m.group(1), sid)
    return out


def heading_ids(explainer: Path) -> set[str]:
    return {sid for sid in _headings(explainer) if sid}


def source_slug(src: Path) -> str:
    """The source's name, without the date of a run folder."""
    return re.sub(r"^\d{4}-\d{2}-\d{2}-", "", src.name)


def load_series(arg: str) -> tuple[Path, dict]:
    """A series folder's series.json, or a plan file; relative to here or to the repository."""
    for base in (Path(arg), REPO / arg):
        p = base if base.is_file() else base / "series.json"
        if p.exists():
            return p, read_json(p)
    die(f"{arg}: no series.json (a series is planned with /plan-series: tools/series.py plan, then write)")
    raise SystemExit  # for type checkers


def assets(sp: Path, ep: dict) -> Path | None:
    """series/<series>/episodes/epNN/ when its scenes/ holds the scenes kept for the episode, else None."""
    d = sp.parent / "episodes" / f"ep{ep['number']:02d}"
    return d if (d / "scenes").is_dir() and any((d / "scenes").glob("*.py")) else None


def scene_list(sp: Path, ep: dict) -> list[dict]:
    """File and class of every kept Scene, in their plan.json order."""
    d = assets(sp, ep)
    if d is None:
        return []
    order = [x["file"] for x in read_json(d / "plan.json", {}).get("scenes", [])]
    out = []
    for f in sorted((d / "scenes").glob("*.py"), key=lambda f: (order.index(f.name) if f.name in order else 99, f.name)):
        out += [{"file": f.name, "class": c} for c in CLASS_RE.findall(f.read_text(encoding="utf-8"))]
    return out


def delivered(slug: str, runs: Path | None = None) -> set[int]:
    """Episodes of a series whose hand-over package (deliver/upload_sheet.md) is in a run folder."""
    out = set()
    for ep in sorted((runs or REPO / "runs").glob("*/episode.json")):
        try:
            e = read_json(ep)
        except (OSError, ValueError):
            continue
        if e.get("series") == slug and e.get("episode") is not None and \
                (ep.parent / "deliver" / "upload_sheet.md").exists():
            out.add(int(e["episode"]))
    return out


def episode_status(series: dict, ledger: Path | None, runs: Path | None = None) -> dict[int, str]:
    st = {n: "delivered" for n in delivered(series["slug"], runs)}
    if ledger and ledger.exists():
        for e in read_json(ledger).get("runs", {}).values():
            if e.get("series") == series["slug"] and e.get("episode") is not None:
                st[int(e["episode"])] = e.get("status", "")
    return st


def blocked_by(ep: dict, ledger: Path | None, runs: Path | None = None) -> list[str]:
    """Must prerequisites in other series that are not published, staged or delivered yet."""
    out = []
    for r in (ep.get("prerequisites") or {}).get("must", []):
        if isinstance(r, dict) and \
                episode_status({"slug": r["series"]}, ledger, runs).get(r["episode"]) not in NEXT_DONE:
            out.append(f"{r['series']}:{r['episode']}")
    return out


def _first_open(series: dict, ledger: Path | None, runs: Path | None) -> dict | None:
    """The first episode in the plan's release order that is not done."""
    st = episode_status(series, ledger, runs)
    order = (series.get("release") or {}).get("order") or [e["number"] for e in series["episodes"]]
    by = {e["number"]: e for e in series["episodes"]}
    return next((by[n] for n in order if n in by and st.get(n) not in NEXT_DONE), None)


def pick_next(series: dict, ledger: Path | None, sp: Path | None = None, runs: Path | None = None) -> dict | None:
    nxt = _first_open(series, ledger, runs)
    return nxt if nxt is None or not blocked_by(nxt, ledger, runs) else None


def next_reason(series: dict, ledger: Path | None, runs: Path | None = None) -> str:
    nxt = _first_open(series, ledger, runs)
    if nxt is None:
        return "every episode is published, in review or delivered"
    return (f"the next episode in the release order, {nxt['number']} ({nxt.get('short_title', nxt['title'])}), builds "
            f"on {', '.join(blocked_by(nxt, ledger, runs))}, which is not published, in review or delivered yet")


def cmd_list(a) -> int:
    p_, s = load_series(a.series)
    st = episode_status(s, Path(a.ledger) if a.ledger else None, Path(a.root) if a.root else None)
    print(f"{s['title']} ({s['slug']}), from {s['source']}; plan: {approval_state(p_, s)['detail']}")
    for e in s["episodes"]:
        kept = assets(p_, e)
        scenes = (", ".join(f"{x['file']}:{x['class']}" for x in scene_list(p_, e)) + f"; kept in {rel(kept)}"
                  if kept else "no scenes yet")
        pre = e.get("prerequisites") or {}
        print(f"  {e['number']:2d}. {e['short_title']} ({e['kind']})  [{st.get(e['number'], 'not started')}]  "
              f"builds on {', '.join(map(ref_key, pre.get('must', []))) or 'nothing'}  ({scenes})")
    return 0


def cmd_next(a) -> int:
    sp, s = load_series(a.series)
    ledger = Path(a.ledger) if a.ledger else None
    runs = Path(a.root) if a.root else None
    e = pick_next(s, ledger, sp, runs)
    if e is None:
        print(next_reason(s, ledger, runs), file=sys.stderr)
        return 1
    print(e["number"])
    return 0


def from_source(source: str, root: Path | None = None) -> list[tuple[Path, dict]]:
    """The series made from a source folder, in release order (a series comes after those it follows)."""
    want = source.strip().rstrip("/")
    found = {}
    for p in sorted((root or REPO).glob("series/*/series.json")):
        try:
            d = read_json(p)
        except (OSError, ValueError):
            continue
        if str(d.get("source", "")).rstrip("/") == want:
            found[d.get("slug", p.parent.name)] = (p.parent, d)
    order: list[str] = []

    def visit(slug, seen=()):
        if slug in order or slug not in found or slug in seen:
            return
        for other in (found[slug][1].get("related_series") or {}).get("follows", []):
            visit(other, seen + (slug,))
        order.append(slug)
    for slug in sorted(found):
        visit(slug)
    return [found[k] for k in order]


def cmd_from_source(a) -> int:
    hits = from_source(a.source, Path(a.root) if a.root else None)
    if not hits:
        print(f"no series made from {a.source} yet: plan them with /plan-series {a.source}", file=sys.stderr)
        return 1
    for sp, d in hits:
        print(f"{rel(sp)}\t{d.get('title', '')}\t{len(d.get('episodes', []))} episode(s)")
    return 0


def plan_hash(data: dict) -> str:
    """Hash of what the owner approves: the plan without its VOLATILE fields."""
    keep = {k: v for k, v in data.items() if k not in VOLATILE}
    return hashlib.sha256(json.dumps(keep, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def approval_setting() -> str:
    return str(load_json(CONFIG / "pipeline.json").get("series", {}).get("plan_approval", "required"))


def approval_state(sp: Path, data: dict, require: bool = False) -> dict:
    """{"required", "approved", "detail", "approved_at"}; require=True asks for the approval whatever the setting."""
    required = require or approval_setting() == "required"
    rec = data.get("plan_approval") or {}
    optional = "plan approval is optional (config/pipeline.json series.plan_approval: optional)"
    if rec.get("status") != "approved":
        return {"required": required, "approved": False, "approved_at": None,
                "detail": f"not approved: the owner runs `./tools/human/approve_series.py {rel(sp.parent)}` in a terminal"
                if required else f"{optional}: none recorded, none needed"}
    if rec.get("plan_sha256") != plan_hash(data):
        return {"required": required, "approved": False, "approved_at": rec.get("date"),
                "detail": "the plan changed since the owner approved it (series.json edited after the approval): "
                          f"the owner approves it again with `./tools/human/approve_series.py {rel(sp.parent)}` in a "
                          "terminal" if required else
                          f"{optional}: the approval recorded earlier no longer matches the plan, and none is needed"}
    return {"required": required, "approved": True, "approved_at": rec.get("date"),
            "detail": f"approved by the {rec.get('by', 'owner')} on {rec.get('date', '?')} ({rec.get('via', '')})"}


def ref_key(r) -> str:
    """'3' for episode 3 of this series, 'mpc-mechanics:2' for episode 2 of another series."""
    return f"{r['series']}:{r['episode']}" if isinstance(r, dict) else str(r)


def validate_v2(data: dict, repo: Path = REPO) -> tuple[list[str], list[str]]:
    """(errors, warnings) of a schema-2 series plan."""
    import check_selfcontained as SC
    errs, warns = [], []
    if data.get("schema_version") != 2:
        return [f"schema_version must be 2 (got {data.get('schema_version')!r})"], []
    if not (isinstance(data.get("slug"), str) and SLUG_RE.match(data["slug"])):
        errs.append("slug must be kebab-case")
    if not (isinstance(data.get("title"), str) and 0 < len(data["title"]) <= 100):
        errs.append("title must be 1-100 characters")
    src = repo / str(data.get("source", ""))
    ids: set[str] = set()
    if not (src / "explainer.html").exists():
        errs.append(f"source {data.get('source')!r} has no explainer.html")
    else:
        if not (src / "code").is_dir():
            warns.append(f"source {data.get('source')!r} has no companion code (code/): every number an episode shows "
                         "must then come from scripts written in that episode's run code/, never from memory")
        ids = heading_ids(src / "explainer.html")
        if data.get("explainer_sha256") != sha256_file(src / "explainer.html"):
            errs.append("explainer_sha256 differs from the source's explainer.html: re-plan if its content changed, "
                        "or run `python3 tools/series.py rehash` after a template-only rebuild")
    ps = data.get("plan_sentence")
    if not (isinstance(ps, str) and ps.strip()):
        errs.append("plan_sentence is required (said in episode 1, in the playlist description)")
    elif len(ps.split()) > 60:
        warns.append(f"plan_sentence has {len(ps.split())} words (at most about 50 read well)")
    pd = data.get("playlist_description")
    if not (isinstance(pd, str) and pd.strip()) or len(pd.encode("utf-8")) > 5000:
        errs.append("playlist_description must be 1-5000 bytes (YouTube's limit)")
    elif re.search(r"https?://", pd):
        warns.append("playlist_description holds a link (the series stands on its own)")
    follows = set((data.get("related_series") or {}).get("follows", []))
    eps = data.get("episodes")
    if not isinstance(eps, list) or not eps:
        return errs + ["episodes must be a non-empty list"], warns
    n_total = len(eps)
    short = {e.get("number"): e.get("short_title") for e in eps if isinstance(e, dict)}
    st = SC.settings()

    def viewer_text(where, text, math=False):
        if isinstance(text, str):
            for f in (SC.scan_math(text, st) if math else SC.scan_plain(text, st)):
                errs.append(f"{where}: {f['rule']} '{f['match']}' (videos are self-contained)")

    for i, e in enumerate(eps):
        n = i + 1
        w = f"episode {n}"
        if not isinstance(e, dict) or e.get("number") != n:
            errs.append(f"episodes[{i}]: number must be {n} (episodes are numbered 1..N in order)")
            continue
        want = "first" if n == 1 else "finale" if n == n_total and n_total > 1 else "middle"
        if e.get("kind") != want:
            errs.append(f"{w}: kind must be {want!r} (first, middle, finale by position)")
        if not (isinstance(e.get("title"), str) and 0 < len(e["title"]) <= 90):
            errs.append(f"{w}: title must be 1-90 characters")
        st_ = e.get("short_title")
        if not (isinstance(st_, str) and st_.strip()) or len(st_) > 40:
            errs.append(f"{w}: short_title must be 1-40 characters (shown on the builds-on frame)")
        elif len(st_) > 28 or len(st_.split()) > 4:
            warns.append(f"{w}: short_title {st_!r} is long (at most 4 words, 28 characters read at a glance)")
        if not (isinstance(e.get("hook"), str) and e["hook"].strip()):
            errs.append(f"{w}: hook is required (the first seconds: a full moving picture, spoken by 3 s, its question by 15 s)")
        if not isinstance(e.get("length_min"), (int, float)) or not 1 <= e["length_min"] <= 30:
            errs.append(f"{w}: length_min must be 1-30")
        tk = e.get("takeaway") or {}
        if not (isinstance(tk.get("sentence"), str) and tk["sentence"].strip()):
            errs.append(f"{w}: takeaway.sentence is required")
        elif len(tk["sentence"].split()) > 40:
            warns.append(f"{w}: takeaway sentence has {len(tk['sentence'].split())} words (about 30 at most)")
        tex = tk.get("tex", [])
        if not isinstance(tex, list) or not all(isinstance(t, str) for t in tex) or len(tex) > 3:
            errs.append(f"{w}: takeaway.tex must be a list of at most 3 LaTeX strings (the takeaway card)")
        else:
            for t in tex:
                viewer_text(f"{w} takeaway.tex", t, math=True)
        pre = e.get("prerequisites") or {}
        must, helpful = pre.get("must", []), pre.get("helpful", [])
        keys = set()
        for kind_, lst in (("must", must), ("helpful", helpful)):
            if not isinstance(lst, list):
                errs.append(f"{w}: prerequisites.{kind_} must be a list")
                continue
            for r in lst:
                if isinstance(r, int):
                    if not 1 <= r < n:                # backward only, so the prerequisites cannot form a cycle
                        errs.append(f"{w}: prerequisite {r} must be an earlier episode (backward only, no cycles)")
                elif isinstance(r, dict) and isinstance(r.get("series"), str) and isinstance(r.get("episode"), int):
                    if r["series"] not in follows:
                        errs.append(f"{w}: prerequisite {ref_key(r)} is in a series this one does not follow "
                                    "(related_series.follows lists series released earlier)")
                    other = repo / "series" / r["series"] / "series.json"
                    if other.exists() and r["episode"] not in [x.get("number") for x in
                                                               read_json(other).get("episodes", [])]:
                        errs.append(f"{w}: prerequisite {ref_key(r)} names an episode that series does not have")
                else:
                    errs.append(f"{w}: prerequisite {r!r} must be an episode number or {{series, episode}}")
                if ref_key(r) in keys:
                    errs.append(f"{w}: prerequisite {ref_key(r)} is listed twice (must and helpful are disjoint)")
                keys.add(ref_key(r))
        recaps = e.get("recap") or []
        covered = set()
        if not isinstance(recaps, list):
            errs.append(f"{w}: recap must be a list")
            recaps = []
        for j, rc in enumerate(recaps):
            rw = f"{w} recap[{j}]"
            if not isinstance(rc, dict):
                errs.append(f"{rw} must be an object")
                continue
            if not (isinstance(rc.get("title"), str) and rc["title"].startswith("Recap")):
                errs.append(f"{rw}: title must start with 'Recap' (it is also the chapter title)")
            covered |= {ref_key(r) for r in rc.get("from", [])}
            secs = rc.get("seconds")
            if isinstance(secs, (int, float)) and not 15 <= secs <= 75:
                warns.append(f"{rw}: {secs} s (recaps of about 20-60 s keep returning viewers)")
            for t in rc.get("card", []) or []:
                viewer_text(f"{rw} card", t, math=True)
            if not (isinstance(rc.get("restates"), str) and rc["restates"].strip()):
                errs.append(f"{rw}: restates is required (what the recap says, by meaning)")
            else:
                viewer_text(f"{rw} restates", rc["restates"])
        for r in must:
            if ref_key(r) not in covered:
                errs.append(f"{w}: must prerequisite {ref_key(r)} has no recap (recap everything the episode uses)")
        total_recap = sum(rc.get("seconds") or 0 for rc in recaps if isinstance(rc, dict))
        limit = 90 if want == "finale" and len(must) > 2 else 60
        if len(recaps) > 2 or total_recap > limit:
            warns.append(f"{w}: {len(recaps)} recap block(s), {total_recap} s in all (about two and {limit} s at "
                         "most keep returning viewers; merge recaps or split the episode)")
        teaser = e.get("teaser")
        if want == "finale" and teaser:
            errs.append(f"{w}: the finale has no teaser (teaser must be empty)")
        if want != "finale" and n_total > 1 and not (isinstance(teaser, str) and teaser.strip()):
            errs.append(f"{w}: teaser is required ('In the next episode, ...')")
        viewer_text(f"{w} teaser", teaser)
        viewer_text(f"{w} hook", e.get("hook"))
        sc = e.get("series_context") or {}
        if n_total > 1:
            if not (isinstance(sc.get("spoken"), str) and sc["spoken"].strip()):
                warns.append(f"{w}: series_context.spoken is missing (the spoken series context after the hook)")
            else:
                viewer_text(f"{w} series_context", sc["spoken"])
            at = sc.get("at_s")
            if isinstance(at, (int, float)) and not 25 <= at <= 90:
                warns.append(f"{w}: series context at {at} s (the first natural break, about 30-90 s)")
            fr = sc.get("frame") or {}
            if fr.get("heading") and fr["heading"] != f"Episode {n} of {n_total}":
                warns.append(f"{w}: builds-on heading {fr['heading']!r} should read 'Episode {n} of {n_total}'")
            want_titles = [short.get(r) if isinstance(r, int) else ref_key(r) for r in must]
            if fr.get("builds_on") is not None and isinstance(must, list) and \
                    sorted(fr["builds_on"]) != sorted(t for t in want_titles if t) and all(isinstance(r, int) for r in must):
                warns.append(f"{w}: builds_on {fr['builds_on']} differs from the must prerequisites' short titles "
                             f"{want_titles}")
        mat = e.get("material") or {}
        sec = mat.get("section_ids", e.get("section_ids", []))
        if not isinstance(sec, list) or not sec:
            errs.append(f"{w}: material.section_ids must list the explainer sections it draws on (sources)")
        elif ids:
            bad = [x for x in sec if x not in ids]
            if bad:
                errs.append(f"{w}: material.section_ids not in the explainer: {bad}")
        for sc_ in mat.get("scripts", []) or []:
            if (src / "code").exists() and not (src / "code" / sc_).exists():
                warns.append(f"{w}: script {sc_} is not in the series source's code/: sync it before producing")
    e2, w2, _ = IB.check_series(eps, IB.settings())     # the idea budget: an over-packed episode fails here
    return errs + e2, warns + w2


def budget(data: dict) -> list[str]:
    """The idea budget of every episode, as lines for the planner."""
    eps = [e for e in data.get("episodes") or [] if isinstance(e, dict)]
    cfg = IB.settings()
    _, _, est = IB.check_series(eps, cfg)
    if not est:
        return []
    return ["budget: what each episode's ideas need (pacing.plan of config/video.json: 75-90 s per key idea, "
            f"{100 * float(cfg.get('slow_extra') or 0):g} % more for the slow reading of the derivations, concepts, "
            f"consequences, consolidation and the fixed beats; at most {float(cfg['episode_max_min']):g} min)"] + \
        ["  " + line for line in IB.table(eps, est, cfg)]


def check_plan(data: dict) -> tuple[list[str], list[str]]:
    """validate_v2, printing the idea budget, the warnings and the errors."""
    errs, warns = validate_v2(data)
    for line in budget(data):
        print(line)
    for w_ in warns:
        print(f"warning {w_}")
    for e_ in errs:
        print(f"ERROR   {e_}")
    return errs, warns


def cmd_validate(a) -> int:
    p, data = load_series(a.series)
    errs, warns = check_plan(data)
    print(f"validate: {'FAIL' if errs else 'ok'} ({len(errs)} error(s), {len(warns)} warning(s)) {rel(p)}")
    return 1 if errs else 0


def cmd_approval(a) -> int:
    p, data = load_series(a.series)
    st = approval_state(p, data)
    print(f"{rel(p.parent)}: {st['detail']} (config/pipeline.json series.plan_approval: {approval_setting()})")
    return 0 if st["approved"] or not st["required"] else 1


def cmd_rehash(a) -> int:
    """Record the source explainer's new byte hash after a template-only rebuild (the approval stays valid)."""
    p, data = load_series(a.series)
    src = REPO / data["source"] / "explainer.html"
    old = data.get("explainer_sha256")
    data["explainer_sha256"] = sha256_file(src)
    write_json(p, data)
    print(f"{rel(p)}: explainer_sha256 {str(old)[:12]} -> {data['explainer_sha256'][:12]}")
    return 0


def cmd_write(a) -> int:
    src = Path(a.proposal)
    data = read_json(src)
    errs, _ = check_plan(data)
    if errs:
        die(f"{src}: not written ({len(errs)} error(s))")
    plan_run = next((d for d in src.resolve().parents if (d / "series_plan").is_dir() and (d / "review").is_dir()),
                    None)
    red = plan_run / "review" / "series_plan" / "summary.json" if plan_run else None
    if red is not None and not a.allow_open_findings:
        if not red.exists():
            die("the red team has not reviewed this plan (review/series_plan/summary.json; see /plan-series)")
        summ = read_json(red)
        if summ.get("open_blocker_major") or summ.get("unverified_blocker_major"):
            die(f"open or unverified red-team findings: {summ.get('open_blocker_major') or summ.get('unverified_blocker_major')}")
    out_dir = (Path(a.root) if a.root else REPO) / "series" / data["slug"]
    out = out_dir / "series.json"
    if out.exists():
        old = read_json(out)
        if old.get("schema_version") == 2 and approval_state(out, old)["approved"] and not a.replace:
            die(f"{rel(out)} holds an approved plan: pass --replace to supersede it (the owner approves again)")
        keep = out_dir / "superseded"
        keep.mkdir(parents=True, exist_ok=True)
        shutil.copy(out, keep / f"{utc_now().replace(':', '').replace('-', '')[:15]}-series.json")
    data = {k: v for k, v in data.items() if k != "_proposal_notes"}
    data["provenance"] = {"proposal": rel(src), "plan_run": rel(plan_run) if plan_run else None,
                          "red_team": rel(red) if red is not None and red.exists() else None, "written_at": utc_now()}
    write_json(out, data)
    if a.plan:
        shutil.copy(a.plan, out_dir / "PLAN.md")
    print(f"wrote {rel(out)}: {len(data['episodes'])} episode(s); plan hash {plan_hash(data)[:12]}. "
          + (f"The owner approves it once: ./tools/human/approve_series.py {rel(out_dir)}"
             if approval_setting() == "required" else
             "Plan approval is optional (config/pipeline.json series.plan_approval): episodes can start from it."))
    return 0


def cmd_plan(a) -> int:
    """A planning run: the explainer, code and data to read, series_plan/ for proposals, review/series_plan/."""
    src = Path(a.source).resolve()
    if not (src / "explainer.html").exists():
        die(f"{a.source}: no explainer.html")
    date = a.date or today_local()
    parse_date(date)
    root = Path(a.root) if a.root else REPO / "runs"
    run = root / f"{date}-series-plan-{slugify(source_slug(src), 40)}"
    if run.exists():
        die(f"{rel(run)} exists: resume it, or remove it")
    (run / "series_plan").mkdir(parents=True)
    (run / "review" / "series_plan").mkdir(parents=True)
    shutil.copy(src / "explainer.html", run / "explainer.html")
    for sub in ("code", "data"):
        if (src / sub).exists():
            shutil.copytree(src / sub, run / sub, ignore=shutil.ignore_patterns("__pycache__"))
    has_code = (src / "code").is_dir()
    write_json(run / "plan_source.json", {"schema_version": 1, "source": rel(src),
                                          "explainer_sha256": sha256_file(src / "explainer.html"),
                                          "companion_code": has_code, "data": (src / "data").is_dir(),
                                          "existing_series": sorted(rel(p.parent) for p in (REPO / "series").glob("*/series.json")),
                                          "created_at": utc_now()})
    if not has_code:
        print(f"warning: {rel(src)} has no companion code (code/): every number an episode shows must come from a "
              "script the episode writes in its run's code/ (or a closed form of the explainer), never from memory",
              file=sys.stderr)
    print(rel(run))
    return 0


HOUSE_RULES = [
    "## House rules for the video (they take precedence)", "",
    "- Hook first: narration starts at 0 s with the question or object the title promises. No channel card: the "
    "channel name appears only on the outro and the thumbnail.",
    "- Series context at the first natural break, about 30-90 s in: one or two spoken sentences (where this episode "
    "sits, what it builds on, a welcome for viewers joining here), over the 4-6 s builds-on frame "
    "(`builds_on()`: \"Episode n of N\" and the titles of the episodes it builds on). No map.",
    "- Recap everything the episode uses from earlier episodes, in scenes marked `recap_tag()` (plan.json role "
    "\"recap\", recap_of, a chapter \"Recap: ...\"), showing the earlier episode's takeaway card (`takeaway_card(k)`), "
    "with a soft pointer by title (\"the episode on ... has the full story\"), never \"you must have watched\".",
    "- Other episodes may be named in the body by title or meaning only when the result is shown in this video; "
    "never by equation number (\"equation 4 of episode 2\").",
    "- Outro, 15-20 s (plan.json role \"outro\"): this episode's takeaway card and the channel name (`outro()`), the "
    "right 40 % of the frame left empty for YouTube's end-screen elements, and a spoken \"In the next episode, "
    "<topic>\" (no teaser in the finale).",
    "- Self-contained: no mention of the explainer, its code, files, data, links or the description; no section, "
    "figure or equation numbers. `tools/video/check_selfcontained.py` enforces it; `tools/video/check_series.py` "
    "warns about the series beats.",
    "- No equation labels or tags (config/video.json `equation_numbers`): show an equation again, or name it by its "
    "meaning. Numbers through `fmt()` (config/video.json \"numbers\"; `tools/video/check_numbers.py`).",
    "- Chapters are the video's own titles (`plan.json` \"chapter\"), written for viewers.",
    "- Choose less, and different, material than the explainer: the episode tells its own story with what it needs; "
    "it does not walk the sections.",
]


def series_context(sp: Path, s: dict, ep: dict, ledger: Path | None) -> dict:
    """video/series_context.json: what the episode's series beats show (read by common.py at render time)."""
    n, total = ep["number"], len(s["episodes"])
    by_num = {e["number"]: e for e in s["episodes"]}
    others: dict[str, dict] = {}

    def episode_of(r):
        if isinstance(r, int):
            return by_num.get(r)
        if r["series"] not in others:
            others[r["series"]] = read_json(REPO / "series" / r["series"] / "series.json", {"episodes": []})
        return next((e for e in others[r["series"]]["episodes"] if e.get("number") == r["episode"]), None)

    pre = ep.get("prerequisites") or {"must": [], "helpful": []}
    refs = list(pre.get("must", [])) + list(pre.get("helpful", []))
    short, takeaways = {}, {str(n): ep.get("takeaway")}
    for r in refs:
        e = episode_of(r)
        short[ref_key(r)] = (e or {}).get("short_title", ref_key(r))
        takeaways[ref_key(r)] = (e or {}).get("takeaway")
    published, playlist = {}, None
    if ledger and ledger.exists():
        led = read_json(ledger)
        for e in led.get("runs", {}).values():
            if e.get("status") == "published" and e.get("video_id") and e.get("episode") is not None:
                key = str(e["episode"]) if e.get("series") == s["slug"] else f"{e.get('series')}:{e['episode']}"
                published[key] = e["video_id"]
        playlist = led.get("series", {}).get(s["slug"], {}).get("playlist_id")
    nxt = by_num.get(n + 1)
    return {"schema_version": 1, "series": s["slug"], "series_title": s["title"], "episode": n, "episodes_total": total,
            "kind": ep["kind"], "title": ep["title"], "short_title": ep["short_title"],
            "prerequisites": {"must": [ref_key(r) for r in pre.get("must", [])],
                              "helpful": [ref_key(r) for r in pre.get("helpful", [])]},
            "short_titles": short, "takeaways": takeaways,
            "recaps": [{"title": rc.get("title"), "from": [ref_key(r) for r in rc.get("from", [])],
                        "seconds": rc.get("seconds"),
                        "card": rc.get("card") or [t for r in rc.get("from", [])
                                                   for t in ((takeaways.get(ref_key(r)) or {}).get("tex") or [])],
                        "restates": rc.get("restates")} for rc in ep.get("recap") or []],
            "context": ep.get("series_context"), "teaser": ep.get("teaser") or None,
            "next": {"number": nxt["number"], "short_title": nxt["short_title"]} if nxt else None,
            "published": published, "playlist_id": playlist, "plan_sha256": plan_hash(s)}


def brief(sp: Path, s: dict, ep: dict, kept: Path | None, fresh: bool, source_code: bool = True) -> str:
    """video/episode.md: the episode's brief from the plan, then the house rules."""
    pre = ep.get("prerequisites") or {}
    mat = ep.get("material") or {}
    state = "plan approved" if approval_state(sp, s)["approved"] else "the plan as written; approval optional"
    lines = [f"# Episode {ep['number']} of {len(s['episodes'])}: {ep['title']}", "",
             f"Series: {s['title']} (`{rel(sp)}`, {state}). Explainer: `explainer.html` (copied unchanged from "
             f"`{s['source']}`). Kind: {ep['kind']}. Target length: {ep.get('length_min', '?')} min.", "",
             f"- Hook (a full moving picture from frame 0, spoken by 3 s, its question by 15 s): {ep.get('hook', '')}",
             f"- Story beat: {ep.get('story_beat', '')}",
             f"- Takeaway: {(ep.get('takeaway') or {}).get('sentence', '')} (card: `takeaway_card()`)",
             f"- Builds on (recap each): {', '.join(map(ref_key, pre.get('must', []))) or 'nothing'}; helpful: "
             f"{', '.join(map(ref_key, pre.get('helpful', []))) or 'none'}",
             f"- Series context (about {(ep.get('series_context') or {}).get('at_s', 30)} s): "
             f"{(ep.get('series_context') or {}).get('spoken', '')}",
             f"- Teaser: {ep.get('teaser') or 'none (finale)'}",
             f"- Material (sources, not a mapping): sections {', '.join(mat.get('section_ids', []))}; scripts "
             f"{', '.join(mat.get('scripts', [])) or 'see code/'}; {mat.get('notes', '')}",
             f"- Viewer: {ep.get('target_viewer', '')}",
             "- Code: " + ("the source's companion code is in `code/` (copied unchanged); numbers come from its scripts and "
                           "logs" if source_code else "the source has no companion code: write the scripts that print "
                           "every number of this episode in `code/` (listed in `code/checks.toml`); never a number from "
                           "memory"),
             f"- Existing scenes: {'none: write them' if fresh else ', '.join(x['file'] + ':' + x['class'] for x in scene_list(sp, ep)) or 'none: write them'}"
             + (f" (kept in `{rel(kept)}`: start from these)" if kept else ""),
             "", "## Recaps", ""]
    for rc in ep.get("recap") or []:
        lines.append(f"- {rc.get('title')} ({rc.get('seconds', '?')} s, from {', '.join(map(ref_key, rc.get('from', [])))}): "
                     f"{rc.get('restates', '')}")
    lines += ["", "## Outline", ""]
    lines += [f"- {b.get('beat')} ({b.get('min', '?')} min)" for b in ep.get("outline") or []]
    ideas = [i for i in ep.get("ideas") or [] if isinstance(i, dict)]
    if ideas:
        cfg = IB.settings()
        est = IB.estimate(ideas, cfg, IB.recap_seconds(ep))
        lines += ["", "## Ideas (the budget: declare each in `video/plan.json` \"ideas\" where it lands)", "",
                  f"The ideas need {est['lo_s'] / 60:.1f}-{est['hi_s'] / 60:.1f} min with consolidation and the fixed "
                  "beats (tools/video/idea_budget.py). Teach these and no more: a new starred result or claim goes "
                  "back to the series plan, never into the video.", ""]
        for i in ideas:
            lo, hi = IB.idea_seconds(i, cfg)
            extra = [f"uses {', '.join(i['uses'])}"] if i.get("uses") else []
            extra += [f"follows {i['follows']}"] if i.get("follows") else []
            extra += [x for x in ("pretraining", "example", "side") if i.get(x)]
            lines.append(f"- `{i.get('id')}` ({i.get('kind')}, {lo:g}" + (f"-{hi:g}" if hi != lo else "") + " s"
                         + (f"; {'; '.join(extra)}" if extra else "") + f"): {i.get('text', '')}")
    lines += [""] + HOUSE_RULES
    return "\n".join(lines).rstrip() + "\n"


def cmd_start(a) -> int:
    sp, s = load_series(a.series)
    errs, _ = validate_v2(s)
    if errs:
        die(f"{rel(sp)} does not validate: {errs[0]} (python3 tools/series.py validate {a.series})")
    appr = approval_state(sp, s, require=a.require_approval)
    if appr["required"] and not appr["approved"]:
        die(f"series plan {rel(sp.parent)}: {appr['detail']} (plan approval is required: config/pipeline.json "
            "series.plan_approval, or --require-approval)")
    if not appr["approved"]:
        print(f"note: {appr['detail']}", file=sys.stderr)
    for other in (s.get("related_series") or {}).get("follows", []):
        if not (REPO / "series" / other / "series.json").exists():
            die(f"{rel(sp)} follows series {other!r}, which is not in series/: its recaps and links need it")
    src = REPO / s["source"]
    ledger = Path(a.ledger) if a.ledger else None
    runs = Path(a.root) if a.root else None
    if a.episode == "next":
        ep = pick_next(s, ledger, sp, runs)
        if ep is None:
            die(next_reason(s, ledger, runs))
    else:
        ep = next((e for e in s["episodes"] if str(e["number"]) == str(a.episode)), None)
        if ep is None:
            die(f"episode {a.episode} is not in {rel(sp)}")
        status = episode_status(s, ledger).get(ep["number"])
        if status in DONE:
            die(f"episode {ep['number']} is already {status} (ledger)")
    date = a.date or today_local()
    parse_date(date)
    slug = f"{s['slug']}-ep{ep['number']:02d}-{slugify(ep['title'], 32)}"
    run = (runs or REPO / "runs") / f"{date}-{slug}"
    if run.exists():
        die(f"{rel(run)} exists: resume it, or remove it")
    (run / "review").mkdir(parents=True)
    shutil.copy(src / "explainer.html", run / "explainer.html")
    if (src / "code").is_dir():
        shutil.copytree(src / "code", run / "code", ignore=shutil.ignore_patterns("__pycache__"))
    else:                                                 # no companion code: the episode writes its own scripts
        (run / "code").mkdir()
        shutil.copy(TEMPLATES / "run" / "checks.toml", run / "code" / "checks.toml")
        shutil.copy(TEMPLATES / "run" / "code_README.md", run / "code" / "README.md")
        print(f"note: {s['source']} has no code/: write the scripts that print this episode's numbers in "
              f"{rel(run / 'code')} and list them in its checks.toml; never take a number from memory", file=sys.stderr)
    scenes = run / "video" / "scenes"
    scenes.mkdir(parents=True)
    for helper in HELPERS:
        shutil.copy(TEMPLATES / "manim" / helper, scenes / helper)
    kept = None if a.fresh else assets(sp, ep)
    if kept is not None:                                  # an episode made again after a fix starts from its scenes
        for f in sorted((kept / "scenes").glob("*.py")):
            shutil.copy(f, scenes / f.name)
        for name in ("plan.json", "storyboard.md"):
            if (kept / name).exists():
                shutil.copy(kept / name, run / "video" / name)
    if (src / "data").exists():
        shutil.copytree(src / "data", run / "video" / "data", ignore=shutil.ignore_patterns("__pycache__"))
    for d in ("checks", "renders", "final"):
        (run / "video" / d).mkdir(parents=True, exist_ok=True)
    ctx = series_context(sp, s, ep, ledger)
    for k in ctx["prerequisites"]["must"]:
        if k not in ctx["published"] and ledger is not None:
            print(f"note: episode {k}, which this one builds on, is not published yet (its recap keeps this episode "
                  "watchable alone)", file=sys.stderr)
    write_json(run / "video" / "series_context.json", ctx)
    (run / "video" / "episode.md").write_text(brief(sp, s, ep, kept, a.fresh, (src / "code").is_dir()),
                                              encoding="utf-8")
    write_json(run / "run.json", {"schema_version": 1, "run_date": date, "focus": s["title"], "mode": "series",
                                  "window_days": 0})
    mat = ep.get("material") or {}
    pl = dict(s.get("playlist") or {"title": s["title"][:150], "privacy": "public"})
    pl["description"] = s.get("playlist_description") or pl.get("description", "")
    write_json(run / "episode.json", {
        "schema_version": 2, "mode": "series", "series": s["slug"], "series_title": s["title"],
        "episode": ep["number"], "episodes_total": len(s["episodes"]), "kind": ep["kind"],
        "short_title": ep["short_title"], "topic_id": f"EP{ep['number']:02d}", "title": ep["title"], "slug": slug,
        "explainer_slug": s["explainer_slug"], "explainer_sha256": s["explainer_sha256"], "source": s["source"],
        "sections": ep.get("sections", []), "section_ids": mat.get("section_ids", ep.get("section_ids", [])),
        "prerequisites": ctx["prerequisites"], "playlist": pl, "plan_sha256": plan_hash(s),
        "plan_approval": {"required": appr["required"], "approved": appr["approved"], "detail": appr["detail"]},
        "ideas": ep.get("ideas") or [],
        "scenes_from_plan": [] if a.fresh else scene_list(sp, ep), "fresh": a.fresh, "chosen_by": a.by,
        "selected_at": utc_now(), "rule": "tools/series.py start"})
    print(rel(run))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    pl = sub.add_parser("plan", help="create a planning run for /plan-series")
    pl.add_argument("source")
    pl.add_argument("--root")
    pl.add_argument("--date")
    for name in ("validate", "approval", "rehash"):
        sub.add_parser(name).add_argument("series")
    w = sub.add_parser("write", help="validate a proposal and store it as series/<slug>/series.json")
    w.add_argument("proposal")
    w.add_argument("--plan", help="PLAN.md to keep next to it")
    w.add_argument("--replace", action="store_true", help="supersede an approved plan (the owner approves again)")
    w.add_argument("--allow-open-findings", action="store_true", help="write despite open red-team findings")
    w.add_argument("--root", help="folder that holds series/ (default: the repository; tests)")
    for name in ("list", "next"):
        p = sub.add_parser(name)
        p.add_argument("series")
        p.add_argument("--ledger")
        p.add_argument("--root", help="folder of the run folders (default runs/): episodes delivered there count")
    st = sub.add_parser("start")
    st.add_argument("series")
    st.add_argument("--episode", required=True, help="episode number, or 'next'")
    st.add_argument("--ledger")
    st.add_argument("--root")
    st.add_argument("--date")
    st.add_argument("--by", default="local", help="who chose the episode (for the log)")
    st.add_argument("--fresh", action="store_true", help="copy no kept scenes (series/<slug>/episodes/epNN/); they "
                    "stay on disk untouched")
    st.add_argument("--require-approval", action="store_true", help="refuse a plan the owner has not approved, "
                    "whatever config/pipeline.json says")
    fs = sub.add_parser("from-source", help="the series made from a source folder, in release order")
    fs.add_argument("source")
    fs.add_argument("--root", help="folder that holds series/ (default: the repository; tests)")
    a = ap.parse_args()
    return {"plan": cmd_plan, "validate": cmd_validate, "approval": cmd_approval,
            "rehash": cmd_rehash, "write": cmd_write, "list": cmd_list, "next": cmd_next,
            "start": cmd_start, "from-source": cmd_from_source}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
