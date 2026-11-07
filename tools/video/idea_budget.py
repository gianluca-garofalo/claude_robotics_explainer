#!/usr/bin/env python3
"""The idea budget: the runtime a video's or an episode's declared ideas need (rule P18).

Usage:
  python3 tools/video/idea_budget.py runs/<run>             # the ideas the run's video is budgeted on
  python3 tools/video/idea_budget.py series/<slug> <n>      # episode n of a series plan
"""
from __future__ import annotations

import argparse
import copy
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from _common import CONFIG, REPO, die, load_json, rel  # noqa: E402

ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
KINDS = ("concept", "claim", "star")
PLAN_DEFAULTS = {
    "key_idea_s": [75, 90], "concept_s": 35, "pretraining_concept_s": 20, "consequence_s": 10, "term_s": 10,
    "consolidation_s": {"star": 10, "claim": 2, "concept": 1, "prompt": 12, "summary": 6},
    "prompt_every_s": 240, "pause_share": 0.07,
    "overhead_s": {"hook": 40, "context": 6, "roadmap": 12, "end_recap": 20, "outro": 18},
    "max_stars": 2, "max_examples": 1, "max_side": 1, "max_pretraining": 5, "max_consequences_per_idea": 2,
    "episode_max_min": 12.0, "length_slack_min": 0.5,
    "slow_extra": 0.08, "slow_roles": ["star", "key", "consequence"],
}


def settings() -> dict:
    """pacing.plan of config/video.json over the defaults."""
    cfg = copy.deepcopy(PLAN_DEFAULTS)
    for k, v in ((load_json(CONFIG / "video.json").get("pacing") or {}).get("plan") or {}).items():
        if k.startswith("_"):
            continue
        if isinstance(v, dict) and isinstance(cfg.get(k), dict):
            cfg[k].update(v)
        else:
            cfg[k] = v
    return cfg


def role(idea: dict) -> str:
    """star, key (a claim of its own), consequence, term (names an earlier idea), pretraining or concept."""
    k = idea.get("kind")
    if k == "star":
        return "star"
    if k == "claim":
        return "consequence" if idea.get("follows") else "key"
    if idea.get("names"):
        return "term"
    return "pretraining" if idea.get("pretraining") else "concept"


def role_seconds(idea: dict, cfg: dict) -> tuple[float, float]:
    """(least, most) seconds of an idea's role at the ordinary pace; "seconds" may ask for more, never less."""
    r = role(idea)
    if r in ("star", "key"):
        lo, hi = (float(x) for x in cfg["key_idea_s"])
    else:
        lo = hi = float(cfg["consequence_s"] if r == "consequence" else cfg["term_s"] if r == "term" else
                        cfg["pretraining_concept_s"] if r == "pretraining" else cfg["concept_s"])
    s = idea.get("seconds")
    if isinstance(s, (int, float)) and not isinstance(s, bool) and s > lo:
        lo, hi = float(s), max(hi, float(s))
    return lo, hi


def idea_seconds(idea: dict, cfg: dict) -> tuple[float, float]:
    """(least, most) seconds an idea needs: its role's, and slow_extra more for the roles read in slow blocks."""
    lo, hi = role_seconds(idea, cfg)
    if role(idea) in (cfg.get("slow_roles") or ()):
        f = 1.0 + float(cfg.get("slow_extra") or 0.0)
        lo, hi = lo * f, hi * f
    return lo, hi


def estimate(ideas: list[dict], cfg: dict, recap_s: float = 0.0) -> dict:
    """{"lo_s", "hi_s", "ideas_s", "consolidation_s", "overhead_s", "counts": {role: n}} of a list of ideas."""
    counts = {"star": 0, "key": 0, "consequence": 0, "term": 0, "pretraining": 0, "concept": 0}
    lo = hi = 0.0
    for i in ideas:
        a, b = idea_seconds(i, cfg)
        lo, hi = lo + a, hi + b
        counts[role(i)] += 1
    c = cfg["consolidation_s"]
    results = counts["star"] + counts["key"]
    fixed = (counts["star"] * c["star"] + counts["key"] * c["claim"]
             + (counts["concept"] + counts["pretraining"] + counts["term"]) * c["concept"] + results * c["summary"])

    def consolidation(x: float) -> float:
        prompts = max(1, round(x / float(cfg["prompt_every_s"])))
        return fixed + prompts * c["prompt"] + float(cfg["pause_share"]) * x
    o = cfg["overhead_s"]
    overhead = float(o["hook"] + o["context"] + o["roadmap"] + o["end_recap"] + o["outro"]) + float(recap_s or 0)
    return {"lo_s": round(overhead + lo + consolidation(lo), 1), "hi_s": round(overhead + hi + consolidation(hi), 1),
            "ideas_s": [lo, hi], "consolidation_s": [round(consolidation(lo), 1), round(consolidation(hi), 1)],
            "overhead_s": overhead, "counts": counts}


def budgeted(ideas: list[dict]) -> list[dict]:
    """The ideas a video's budget counts: concepts, claims and stars, but not a claim that is a step ("of")."""
    return [i for i in ideas if i.get("kind") in KINDS and not (i.get("kind") == "claim" and i.get("of"))]


def planned_ideas(run: Path) -> list[dict]:
    """The series plan's ideas of a run's episode (episode.json), [] for a standalone run."""
    ep = run / "episode.json"
    return [i for i in json.loads(ep.read_text(encoding="utf-8")).get("ideas") or [] if isinstance(i, dict)] \
        if ep.exists() else []


def recap_seconds(ep: dict) -> float:
    return float(sum(r.get("seconds") or 0 for r in ep.get("recap") or [] if isinstance(r, dict)))


def _refs(idea: dict) -> list[str]:
    out = [x for x in idea.get("uses") or [] if isinstance(x, str)]
    for k in ("follows", "names"):
        if isinstance(idea.get(k), str):
            out.append(idea[k])
    return out


def overpacked(ideas: list[dict], cfg: dict, recap_s: float = 0.0) -> list[str]:
    """Why an episode with these ideas is over-packed ([] when it is not)."""
    out = []
    n = {k: sum(1 for i in ideas if test(i)) for k, test in (
        ("stars", lambda i: i.get("kind") == "star"), ("examples", lambda i: i.get("kind") == "claim" and i.get("example")),
        ("side", lambda i: i.get("kind") == "claim" and i.get("side")),
        ("pretraining", lambda i: i.get("kind") == "concept" and i.get("pretraining")))}
    for key, limit, what in (("stars", "max_stars", "starred results"), ("examples", "max_examples", "example results"),
                             ("side", "max_side", "side results"), ("pretraining", "max_pretraining",
                                                                    "pretraining concepts")):
        if n[key] > int(cfg[limit]):
            out.append(f"{n[key]} {what} (at most {cfg[limit]})")
    est = estimate(ideas, cfg, recap_s)
    if est["lo_s"] > 60.0 * float(cfg["episode_max_min"]):
        out.append(f"its ideas need {est['lo_s'] / 60:.1f}-{est['hi_s'] / 60:.1f} min (at most "
                   f"{float(cfg['episode_max_min']):g})")
    return out


def suggest_moves(episodes: list[dict], number: int, cfg: dict) -> dict | None:
    """What to move from an over-packed episode to a neighbour, with what builds on it and what only it needs."""
    by_num = {e.get("number"): e for e in episodes if isinstance(e, dict)}
    ep = by_num.get(number)
    if not ep or not isinstance(ep.get("ideas"), list):
        return None
    dest = number + 1 if number + 1 in by_num else number - 1 if number - 1 in by_num else None
    if dest is None:
        return None
    ideas = [i for i in ep["ideas"] if isinstance(i, dict) and isinstance(i.get("id"), str)]
    order = {i["id"]: k for k, i in enumerate(ideas)}
    by_id = {i["id"]: i for i in ideas}
    wanted = {r for i in by_num[dest].get("ideas") or [] if isinstance(i, dict) for r in _refs(i)}
    recap = recap_seconds(ep)
    staying = dict(by_id)

    def needed_by(ids: set[str]) -> set[str]:          # the ideas these build on, in this episode, transitively
        out, todo = set(), list(ids)
        while todo:
            for r in _refs(by_id.get(todo.pop(), {})):
                if r in by_id and r not in out:
                    out.add(r)
                    todo.append(r)
        return out

    def group(x: str) -> set[str]:                     # x, what builds on it here, and what only they needed
        g, changed = {x}, True
        while changed:
            changed = False
            for i in staying.values():                 # what builds on the group cannot stay before it
                if i["id"] not in g and any(r in g for r in _refs(i)):
                    g.add(i["id"])
                    changed = True
            for y in list(staying):                    # a prerequisite only the group uses goes with it
                users = [i["id"] for i in staying.values() if y in _refs(i)]
                if y not in g and users and all(u in g for u in users) and by_id[y].get("kind") != "star":
                    g.add(y)
                    changed = True
        if dest < number and any(r in staying and r not in g for y in g for r in _refs(by_id[y])):
            return set()                               # moving back: it cannot leave its prerequisites behind
        return g

    def rank(x: str) -> tuple:
        return (x not in wanted and not (group(x) & wanted), -order[x])
    moved: list[str] = []

    def move(x: str) -> bool:
        g = group(x)
        if not g:
            return False
        for y in sorted(g, key=lambda y: order[y]):
            staying.pop(y, None)
            moved.append(y)
        return True
    while len([x for x in staying if by_id[x].get("kind") == "star"]) > int(cfg["max_stars"]):
        left = [x for x in staying if by_id[x].get("kind") == "star"]
        free = [x for x in left if not any(x in needed_by({y}) for y in left if y != x)] or left
        if not any(move(x) for x in sorted(free, key=rank)):
            break
    for limit, test in (("max_examples", "example"), ("max_side", "side")):
        while sum(1 for i in staying.values() if i.get("kind") == "claim" and i.get(test)) > int(cfg[limit]):
            extra = [x for x, i in staying.items() if i.get("kind") == "claim" and i.get(test)]
            if not any(move(x) for x in sorted(extra, key=rank)):
                break

    def over() -> bool:
        return estimate(list(staying.values()), cfg, recap)["lo_s"] > 60.0 * float(cfg["episode_max_min"])
    while over():
        core = {x for x in staying if by_id[x].get("kind") == "star"}
        core |= needed_by(core)
        cands = [x for x in staying if x not in core]
        if not cands or not any(move(x) for x in sorted(cands, key=rank)):
            break
    if not moved:
        return None
    there = [i for i in by_num[dest].get("ideas") or [] if isinstance(i, dict)] + [by_id[x] for x in moved]
    left = list(staying.values())
    return {"to": dest, "move": moved, "fits": not overpacked(left, cfg, recap),
            "left": estimate(left, cfg, recap), "there": estimate(there, cfg, recap_seconds(by_num[dest])),
            "there_over": overpacked(there, cfg, recap_seconds(by_num[dest]))}


def suggest_cut(episodes: list[dict], number: int, cfg: dict) -> dict | None:
    """What an over-packed episode could leave to the explainer: the smallest groups nothing kept or later needs."""
    by_num = {e.get("number"): e for e in episodes if isinstance(e, dict)}
    ep = by_num.get(number)
    if not ep or not isinstance(ep.get("ideas"), list):
        return None
    ideas = [i for i in ep["ideas"] if isinstance(i, dict) and isinstance(i.get("id"), str)]
    by_id = {i["id"]: i for i in ideas}
    later = set()
    for e in episodes:
        if isinstance(e, dict) and isinstance(e.get("number"), int) and e["number"] > number:
            for i in e.get("ideas") or []:
                if isinstance(i, dict):
                    later.update(_refs(i))
            for rc in e.get("recap") or []:
                if isinstance(rc, dict) and isinstance(rc.get("ideas"), list):
                    later.update(x for x in rc["ideas"] if isinstance(x, str))
    staying = dict(by_id)
    recap = recap_seconds(ep)

    def needed_by(ids: set[str]) -> set[str]:
        out, todo = set(), list(ids)
        while todo:
            for r in _refs(by_id.get(todo.pop(), {})):
                if r in by_id and r not in out:
                    out.add(r)
                    todo.append(r)
        return out

    def group(x: str) -> set[str]:
        g, changed = {x}, True
        while changed:
            changed = False
            for i in staying.values():
                if i["id"] not in g and any(r in g for r in _refs(i)):
                    g.add(i["id"])
                    changed = True
            for y in list(staying):
                users = [i["id"] for i in staying.values() if y in _refs(i)]
                if y not in g and users and all(u in g for u in users) and by_id[y].get("kind") != "star" \
                        and y not in later:
                    g.add(y)
                    changed = True
        return g

    def ok(g: set[str]) -> bool:
        stars = {x for x in staying if by_id[x].get("kind") == "star"}
        return not any(by_id[y].get("kind") == "star" or by_id[y].get("example") or y in later for y in g) and \
            not (g & needed_by(stars - g))

    def saving(g: set[str]) -> float:
        return sum(idea_seconds(by_id[y], cfg)[0] for y in g)

    def over(ids, key="lo_s") -> bool:
        return estimate([by_id[y] for y in ids], cfg, recap)[key] > 60.0 * float(cfg["episode_max_min"])
    order = [i["id"] for i in ideas]
    cut: list[str] = []
    while over(staying):
        groups = [g for g in (group(x) for x in staying) if ok(g)]
        if not groups:
            break
        pool = [g for g in groups if not all(role(by_id[y]) == "consequence" for y in g)] or groups
        fits = [g for g in pool if not over(set(staying) - g, "hi_s")] or \
            [g for g in pool if not over(set(staying) - g)]
        best = min(fits, key=lambda g: (len(g), -saving(g), min(order.index(y) for y in g))) if fits else \
            max(pool, key=saving)
        for y in [i["id"] for i in ideas if i["id"] in best]:
            staying.pop(y, None)
            cut.append(y)
    if not cut:
        return None
    left = list(staying.values())
    return {"cut": cut, "fits": not overpacked(left, cfg, recap), "left": estimate(left, cfg, recap)}


def check_series(episodes: list[dict], cfg: dict) -> tuple[list[str], list[str], dict]:
    """(errors, warnings, {episode number: estimate}) of the ideas of a series plan's episodes."""
    errs, warns, est = [], [], {}
    where: dict[str, int] = {}
    for e in episodes:
        if not isinstance(e, dict):
            continue
        for i in e.get("ideas") or [] if isinstance(e.get("ideas"), list) else []:
            if isinstance(i, dict) and isinstance(i.get("id"), str):
                if i["id"] in where:
                    errs.append(f"idea {i['id']!r} is declared in episode {where[i['id']]} and again in episode "
                                f"{e.get('number')} (ids are unique in the series)")
                else:
                    where[i["id"]] = e.get("number")
    every = {i["id"]: i for e in episodes if isinstance(e, dict)
             for i in (e.get("ideas") if isinstance(e.get("ideas"), list) else []) if isinstance(i, dict)
             and isinstance(i.get("id"), str)}
    for e in episodes:
        if not isinstance(e, dict):
            continue
        n, w = e.get("number"), f"episode {e.get('number')}"
        ideas = e.get("ideas")
        if not isinstance(ideas, list) or not ideas:
            errs.append(f"{w}: ideas is required: every concept, claim and starred result the episode teaches, with "
                        "its id, kind and text (tools/video/idea_budget.py); the episode's length follows from them")
            continue
        ok = []
        for k, i in enumerate(ideas):
            iw = f"{w} ideas[{k}]"
            if not isinstance(i, dict):
                errs.append(f"{iw} must be an object")
                continue
            if not (isinstance(i.get("id"), str) and ID_RE.match(i["id"])):
                errs.append(f"{iw}: id must be a short kebab-case name (unique in the series)")
                continue
            iw = f"{w} idea {i['id']!r}"
            if i.get("kind") not in KINDS:
                errs.append(f"{iw}: kind must be one of {', '.join(KINDS)}")
                continue
            if not (isinstance(i.get("text"), str) and i["text"].strip()) or len(i.get("text", "")) > 240:
                errs.append(f"{iw}: text must say the idea in one line (1-240 characters)")
            if i.get("pretraining") and i["kind"] != "concept":
                errs.append(f"{iw}: only a concept can be part of the pretraining segment")
            if (i.get("example") or i.get("side")) and i["kind"] != "claim":
                errs.append(f"{iw}: only a claim can be an example or a side result")
            if i.get("follows") is not None and i["kind"] != "claim":
                errs.append(f"{iw}: only a claim follows from another idea")
            if i.get("names") is not None and (i["kind"] != "concept" or i.get("pretraining")):
                errs.append(f"{iw}: only a concept outside the pretraining segment names another idea")
            s = i.get("seconds")
            if s is not None and not (isinstance(s, (int, float)) and not isinstance(s, bool)
                                      and s >= role_seconds(dict(i, seconds=None), cfg)[0]):
                errs.append(f"{iw}: seconds may raise the budget of a {role(i)} "
                            f"({role_seconds(dict(i, seconds=None), cfg)[0]:g} s), never lower it")
            uses = i.get("uses", [])
            if not isinstance(uses, list) or not all(isinstance(x, str) for x in uses):
                errs.append(f"{iw}: uses must be a list of idea ids")
                uses = []
            pre = e.get("prerequisites") or {}
            listed = {x for x in (pre.get("must") or []) + (pre.get("helpful") or []) if isinstance(x, int)}
            for r in uses + [i[k] for k in ("follows", "names") if isinstance(i.get(k), str)]:
                if r not in where:
                    errs.append(f"{iw} builds on {r!r}, which no episode declares")
                elif isinstance(n, int) and isinstance(where[r], int) and where[r] > n:
                    errs.append(f"{iw} builds on {r!r} of episode {where[r]}, a later episode: move one of them")
                elif r == i["id"]:
                    errs.append(f"{iw} builds on itself")
                elif isinstance(n, int) and isinstance(where[r], int) and where[r] < n and where[r] not in listed:
                    warns.append(f"{iw} builds on {r!r} of episode {where[r]}, which is not among its prerequisites "
                                 "(a must one, with a recap, when it is a premise)")
            root = every.get(i["follows"]) if isinstance(i.get("follows"), str) else None
            if isinstance(i.get("follows"), str) and (root is None or root.get("kind") not in ("claim", "star")):
                errs.append(f"{iw}: follows names the claim or starred result it follows from")
            elif root is not None and role(root) == "consequence":
                errs.append(f"{iw} follows {i['follows']!r}, itself a consequence: a chain is a derivation; point it "
                            f"at the root ({root['follows']!r}), or give the step its own budget or seconds")
            ok.append(i)
        per = {}
        for i in ok:
            if role(i) == "consequence":
                per[i["follows"]] = per.get(i["follows"], 0) + 1
        for src, k in per.items():
            if k > int(cfg["max_consequences_per_idea"]):
                errs.append(f"{w}: {k} consequences follow {src!r} (at most {cfg['max_consequences_per_idea']}): "
                            "a consequence is said in a sentence or two; give the others their own budget")
        pos = {i["id"]: k for k, i in enumerate(ok)}                     # story order inside the episode
        for i in ok:
            for r in _refs(i):
                if r in pos and pos[r] > pos[i["id"]]:
                    warns.append(f"{w} idea {i['id']!r} builds on {r!r}, declared later in the episode: declare "
                                 "ideas in story order (an idea assumed first and shown later is two ideas: declare "
                                 "the assumption separately)")
        cycle = _cycle(ok)
        if cycle:
            errs.append(f"{w}: ideas build on each other in a circle: {' -> '.join(cycle)}")
        for j, rc in enumerate(e.get("recap") or []):
            if not isinstance(rc, dict) or rc.get("ideas") is None:
                continue
            frm = {r for r in rc.get("from") or [] if isinstance(r, int)}
            if not isinstance(rc["ideas"], list):
                errs.append(f"{w} recap[{j}]: ideas must be a list of idea ids")
                continue
            for r in rc["ideas"]:
                if where.get(r) not in frm:
                    errs.append(f"{w} recap[{j}] restates {r!r}, which episode(s) "
                                f"{', '.join(map(str, sorted(frm))) or '-'} do not teach"
                                + (f" (episode {where[r]} does)" if r in where else ""))
        if not any(i.get("kind") == "star" for i in ok):
            warns.append(f"{w}: no starred result: mark the result its takeaway states as \"star\"")
        recap = recap_seconds(e)
        est[n] = estimate(ok, cfg, recap)
        lo, hi = est[n]["lo_s"] / 60, est[n]["hi_s"] / 60
        why = overpacked(ok, cfg, recap)
        if why:
            sug = suggest_moves(episodes, n, cfg) if isinstance(n, int) else None
            stars = [i["id"] for i in ok if i.get("kind") == "star"]
            steps = [x for x in stars if any(x in _refs(i) for i in ok if i.get("kind") == "star" and i["id"] != x)]
            msg = f"{w} is over-packed: {'; '.join(why)}. Move material to a neighbouring episode"
            if sug:
                msg += (f": to episode {sug['to']}, {', '.join(sug['move'])} (then episode {n} needs "
                        f"{sug['left']['lo_s'] / 60:.1f}-{sug['left']['hi_s'] / 60:.1f} min and episode {sug['to']} "
                        f"{sug['there']['lo_s'] / 60:.1f}-{sug['there']['hi_s'] / 60:.1f} min"
                        + (f", over-packed in turn: {'; '.join(sug['there_over'])}" if sug["there_over"] else "")
                        + ")" + ("" if sug["fits"] else "; more must go, or the episode splits in two"))
            cut = suggest_cut(episodes, n, cfg) if isinstance(n, int) else None
            if cut:
                msg += (f"; or leave to the explainer: {', '.join(cut['cut'])} (nothing later builds on them; then "
                        f"episode {n} needs {cut['left']['lo_s'] / 60:.1f}-{cut['left']['hi_s'] / 60:.1f} min"
                        + ("" if cut["fits"] else ", still over-packed") + ")")
            if len(stars) > int(cfg["max_stars"]) and steps:
                msg += (f". A starred result that is only a stepping stone to another one here may be a claim instead: "
                        f"{', '.join(steps)}")
            errs.append(msg)
        if not why and round(hi, 1) > float(cfg["episode_max_min"]):
            warns.append(f"{w}: its ideas may need up to {hi:.1f} min (more than {float(cfg['episode_max_min']):g}): "
                         "consider moving one more idea to a neighbouring episode")
        L = e.get("length_min")
        slack = float(cfg["length_slack_min"])
        if isinstance(L, (int, float)) and not why and not lo - slack <= L <= hi + slack:
            warns.append(f"{w}: length_min {L:g} but its ideas need {lo:.1f}-{hi:.1f} min: set length_min from the "
                         "ideas (cut an idea rather than squeeze it; never raise the speaking rate)")
        beats = [b.get("min") for b in e.get("outline") or [] if isinstance(b, dict)]
        if beats and all(isinstance(m, (int, float)) for m in beats) and not why:
            total = float(sum(beats))
            if total < lo - slack:
                warns.append(f"{w}: the outline's beats add up to {total:.1f} min against the {lo:.1f}-{hi:.1f} its "
                             "ideas need: the outline squeezes its ideas; give the beats their time")
            elif total > hi + slack:
                warns.append(f"{w}: the outline's beats add up to {total:.1f} min against the {lo:.1f}-{hi:.1f} its "
                             "ideas need: the outline plans more than its declared ideas; declare what it teaches "
                             "or cut a beat")
    return errs, warns, est


def _cycle(ideas: list[dict]) -> list[str]:
    """A circle of ideas that build on each other ([a, b, a]), or []."""
    refs = {i["id"]: [r for r in _refs(i) if r != i["id"]] for i in ideas}
    state: dict[str, int] = {}

    def visit(x, path):
        state[x] = 1
        for r in refs.get(x, []):
            if r not in refs:
                continue
            if state.get(r) == 1:
                return path[path.index(r):] + [r] if r in path else [x, r, x]
            if not state.get(r):
                found = visit(r, path + [r])
                if found:
                    return found
        state[x] = 2
        return []
    for x in refs:
        if not state.get(x):
            found = visit(x, [x])
            if found:
                return found
    return []


def table(episodes: list[dict], est: dict, cfg: dict) -> list[str]:
    """One line per episode: its counts, what its ideas need and its length_min."""
    out = [f"{'ep':>3} {'stars':>5} {'claims':>6} {'conseq':>6} {'concepts':>8}  {'needs (min)':>11}  "
           f"{'length_min':>10}"]
    for e in episodes:
        if not isinstance(e, dict) or e.get("number") not in est:
            continue
        x = est[e["number"]]
        c = x["counts"]
        flag = " OVER" if x["lo_s"] > 60 * float(cfg["episode_max_min"]) else ""
        out.append(f"{e['number']:>3} {c['star']:>5} {c['key']:>6} {c['consequence']:>6} "
                   f"{c['concept'] + c['pretraining'] + c['term']:>8}  {x['lo_s'] / 60:>5.1f}-{x['hi_s'] / 60:<5.1f}  "
                   f"{e.get('length_min', '-')!s:>10}{flag}")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("folder", help="runs/<run>, or series/<slug> with an episode number")
    ap.add_argument("episode", nargs="?", type=int)
    a = ap.parse_args()
    folder = next((p for p in (Path(a.folder), REPO / a.folder) if p.is_dir()), None)
    if folder is None:
        die(f"not a folder: {a.folder}")
    recap = 0.0
    if (folder / "series.json").exists():
        if a.episode is None:
            die("give the episode number: idea_budget.py series/<slug> <n>")
        ep = next((e for e in load_json(folder / "series.json").get("episodes") or []
                   if isinstance(e, dict) and e.get("number") == a.episode), None)
        if ep is None:
            die(f"{rel(folder)}: no episode {a.episode}")
        ideas = [i for i in ep.get("ideas") or [] if isinstance(i, dict)]
        recap, source = recap_seconds(ep), f"episode {a.episode} of {rel(folder / 'series.json')}"
    elif (folder / "video" / "plan.json").exists() or (folder / "episode.json").exists():
        ideas, source = planned_ideas(folder), "the series plan (episode.json)"
        if not ideas:
            plan = folder / "video" / "plan.json"
            ideas = budgeted(load_json(plan).get("ideas") or []) if plan.exists() else []
            source = rel(plan)
    else:
        die(f"{a.folder}: neither a run with video/plan.json nor a series with series.json")
    if not ideas:
        die(f"no declared ideas in {source}")
    cfg = settings()
    est = estimate(ideas, cfg, recap)
    c = est["counts"]
    print(f"{len(ideas)} ideas from {source} (stars {c['star']}, key claims {c['key']}, consequences "
          f"{c['consequence']}, concepts {c['concept'] + c['pretraining'] + c['term']})")
    print(f"they need {est['lo_s'] / 60:.1f}-{est['hi_s'] / 60:.1f} min: ideas {est['ideas_s'][0] / 60:.1f}-"
          f"{est['ideas_s'][1] / 60:.1f}, consolidation {est['consolidation_s'][0] / 60:.1f}-"
          f"{est['consolidation_s'][1] / 60:.1f}, fixed beats and recaps {est['overhead_s'] / 60:.1f}")
    for why in overpacked(ideas, cfg, recap):
        print(f"over-packed: {why}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
