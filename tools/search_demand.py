#!/usr/bin/env python3
"""Search demand and supply gap of each candidate topic, from search data, with the evidence written down.

Usage:
  python3 tools/search_demand.py runs/<run>            # after the scout, before tools/rank_topics.py; writes search.json
  SEARCH_BACKEND=fake SEARCH_FAKE_DATA=file.json ...    # recorded responses (tests); nothing leaves the machine

Queries: each candidate's "search_queries" in sources.json (the phrases a viewer would type, chosen by the scout),
else words from its title; at most max_queries_per_topic (config/search.json). Sources, each optional and isolated:
  autocomplete  YouTube search suggestions (suggestqueries.google.com, ds=yt): unofficial, no key, no quota
  youtube       YouTube Data API v3 search.list (100 quota units per call) + videos.list (1 unit): views and dates of
                recent relevant videos; needs $YOUTUBE_API_KEY; capped at max_api_queries_per_run
  trends        Google Trends through the unofficial pytrends client if it is installed (requirements-search.txt):
                all of a topic's queries in one comparison; the score uses the mean of their means
Every query of every source is tried; a source that answers only some queries is "partial (k/n)" and the failed
queries are listed with their reasons. search.json records the hash of the sources.json it was made from, so a later
edit of sources.json makes it stale (tools/rank_topics.py then treats the search criteria as unknown).
Scores, 0-5, written to search.json and used by tools/rank_topics.py (computed, never judged):
  search_demand = weighted mean of the sources that answered: views (median views of the recent relevant videos,
                  1.25 * (log10 v - 2)), autocomplete (matching suggestions, 1 point each up to 5), trends (mean
                  interest / 20); weights in config/search.json, renormalised over the sources that answered
  supply_gap    = 5 - 0.6 * competition - 0.4 * strongest competitor, from YouTube only (competition =
                  2.2 * log10(1 + recent relevant videos), strongest = 1.25 * (log10 max views - 2))
A source that fails is recorded as unavailable with the reason; a criterion with no source is unknown (null), never
zero, and the ranking renormalises the weights. Search measures the long tail of views from search; viral spikes
come mostly from suggested and browse traffic, which no lookup here sees.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import os
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import CONFIG, load_json, rel, resolve_run, sha256_file, utc_now, write_json  # noqa: E402

STOP = set("a an and the of for in on to with by from at as is are be via its it this that new using how why what "
           "fictional robot robots robotics".split())
STOP_KEEP = {"robot", "robots", "robotics"}          # dropped only when other words remain


def content_words(q: str) -> list[str]:
    words = [w for w in re.findall(r"[a-z0-9][a-z0-9+-]*", q.lower())]
    core = [w for w in words if w not in STOP]
    return core or [w for w in words if w in STOP_KEEP] or words


def default_queries(cand: dict, n: int) -> list[str]:
    qs = [q.strip() for q in cand.get("search_queries", []) if isinstance(q, str) and q.strip()]
    if not qs:
        title = re.sub(r"\([^)]*\)", " ", cand.get("title", ""))
        qs = [" ".join(content_words(title)[:5])]
    return qs[:n]


def relevant(title: str, q: str, share: float) -> bool:
    need = content_words(q)
    t = title.lower()
    hits = sum(1 for w in need if w in t)
    return bool(need) and hits >= math.ceil(share * len(need))


def clamp(x: float, lo: float = 0.0, hi: float = 5.0) -> float:
    return max(lo, min(hi, x))


# --------------------------------------------------------------------------- backends
class Live:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.key = os.environ.get("YOUTUBE_API_KEY", "")
        self.quota = 0

    def _get(self, url: str) -> bytes:
        req = urllib.request.Request(url, headers={"User-Agent": "remaining-action-pipeline/1"})
        with urllib.request.urlopen(req, timeout=self.cfg.get("timeout_s", 15)) as r:
            return r.read()

    def autocomplete(self, q: str) -> list[str]:
        url = ("https://suggestqueries.google.com/complete/search?client=firefox&ds=yt&hl="
               f"{self.cfg.get('language', 'en')}&q={urllib.parse.quote(q)}")
        data = json.loads(self._get(url).decode("utf-8", "replace"))
        return [s for s in data[1] if isinstance(s, str)]

    def youtube(self, q: str) -> list[dict]:
        if not self.key:
            raise LookupError("skipped: no YOUTUBE_API_KEY")
        after = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=self.cfg["published_within_days"]))
        params = {"part": "snippet", "type": "video", "maxResults": 25, "order": "relevance", "q": q, "key": self.key,
                  "publishedAfter": after.strftime("%Y-%m-%dT%H:%M:%SZ"), "relevanceLanguage": self.cfg.get("language", "en"),
                  "regionCode": self.cfg.get("region", "US")}
        found = json.loads(self._get("https://www.googleapis.com/youtube/v3/search?" + urllib.parse.urlencode(params)))
        self.quota += 100
        items = [{"id": i["id"]["videoId"], "title": i["snippet"]["title"], "channel": i["snippet"]["channelTitle"],
                  "published": i["snippet"]["publishedAt"][:10]} for i in found.get("items", []) if "videoId" in i["id"]]
        if items:
            stats = json.loads(self._get("https://www.googleapis.com/youtube/v3/videos?" + urllib.parse.urlencode(
                {"part": "statistics", "id": ",".join(i["id"] for i in items), "key": self.key})))
            self.quota += 1
            views = {v["id"]: int(v.get("statistics", {}).get("viewCount", 0)) for v in stats.get("items", [])}
            for i in items:
                i["views"] = views.get(i["id"], 0)
        return items

    def trends(self, queries: list[str]) -> dict:
        """{query: {"mean", "points", "recent_half_mean"}} for up to five queries compared in one request."""
        try:
            from pytrends.request import TrendReq
        except ImportError:
            raise LookupError("unavailable: pytrends is not installed (optional, requirements-search.txt)")
        t = self.cfg.get("trends", {})
        client = TrendReq(hl="en-US", tz=0, timeout=(5, self.cfg.get("timeout_s", 15)))
        client.build_payload(list(queries)[:5], timeframe=t.get("timeframe", "today 12-m"), gprop=t.get("gprop", "youtube"))
        df = client.interest_over_time()
        out = {}
        for q in list(queries)[:5]:
            if df is None or df.empty or q not in df:
                continue
            series = [float(x) for x in df[q].tolist()]
            half = len(series) // 2
            out[q] = {"mean": round(sum(series) / len(series), 1), "points": len(series),
                      "recent_half_mean": round(sum(series[half:]) / max(len(series) - half, 1), 1)}
        return out


class Fake(Live):
    """Recorded responses: {"autocomplete": {q: [...]}, "youtube": {q: [...]}, "trends": {q: {...}}}; a missing
    entry raises, like a failed lookup."""

    def __init__(self, cfg: dict):
        super().__init__(cfg)
        self.data = json.loads(Path(os.environ["SEARCH_FAKE_DATA"]).read_text(encoding="utf-8"))
        self.key = "fake"

    def _pick(self, kind: str, q: str):
        src = self.data.get(kind)
        if src is None or q not in src:
            raise LookupError(f"unavailable: no recorded {kind} answer")
        return src[q]

    def autocomplete(self, q):
        return self._pick("autocomplete", q)

    def youtube(self, q):
        items = self._pick("youtube", q)
        self.quota += 101
        return items

    def trends(self, queries):
        out = {q: self.data["trends"][q] for q in queries if q in self.data.get("trends", {})}
        if not out:
            raise LookupError("unavailable: no recorded trends answer")
        return out


# --------------------------------------------------------------------------- scoring
def score_topic(evidence: dict, cfg: dict, run_date: str | None = None) -> tuple[dict, dict]:
    w = cfg["demand_weights"]
    parts, why = {}, []
    ac = evidence.get("autocomplete", {})
    if ac.get("status") == "ok":
        matched = [len(x["matching"]) for x in ac["queries"]]
        parts["autocomplete"] = clamp(max(matched, default=0))
        why.append(f"{max(matched, default=0)} matching YouTube search suggestion(s)")
    yt = evidence.get("youtube", {})
    rel_videos = yt.get("relevant", [])
    if yt.get("status") == "ok":
        views = sorted(v["views"] for v in rel_videos)
        med = views[len(views) // 2] if views else 0
        parts["views"] = clamp(1.25 * (math.log10(med) - 2)) if med > 0 else 0.0
        why.append(f"median {med:,} views over {len(views)} relevant video(s) of the last "
                   f"{cfg['published_within_days']} days")
    tr = evidence.get("trends", {})
    if tr.get("status") == "ok":
        parts["trends"] = clamp(tr["mean"] / 20.0)
        why.append(f"Google Trends (YouTube search) mean interest {tr['mean']} over "
                   f"{len(tr.get('per_query', {})) or 1} query(ies)")
    scores, reasons = {}, {}
    if parts:
        total_w = sum(w[k] for k in parts)
        scores["search_demand"] = round(sum(w[k] * v for k, v in parts.items()) / total_w, 1)
        reasons["search_demand"] = "; ".join(why) + f" (sub-scores {', '.join(f'{k} {v:.1f}' for k, v in parts.items())})."
    else:
        scores["search_demand"] = None
        reasons["search_demand"] = "unknown: no search source answered (" + "; ".join(
            f"{k}: {evidence.get(k, {}).get('status', 'not tried')}" for k in ("autocomplete", "youtube", "trends")) + ")"
    if yt.get("status") == "ok":
        day = dt.date.fromisoformat(run_date) if run_date else dt.date.today()
        cutoff = (day - dt.timedelta(days=cfg["recent_days"])).isoformat()
        recent = [v for v in rel_videos if v["published"] >= cutoff]
        competition = clamp(2.2 * math.log10(1 + len(recent)))
        top = max((v["views"] for v in recent), default=0)
        strongest = clamp(1.25 * (math.log10(top) - 2)) if top > 0 else 0.0
        scores["supply_gap"] = round(clamp(5 - 0.6 * competition - 0.4 * strongest), 1)
        reasons["supply_gap"] = (f"{len(recent)} relevant video(s) in the last {cfg['recent_days']} days "
                                 f"(competition {competition:.1f}); strongest has {top:,} views ({strongest:.1f}).")
    else:
        scores["supply_gap"] = None
        reasons["supply_gap"] = f"unknown: YouTube data {yt.get('status', 'not tried')}"
    return scores, reasons


def _status(msg: str) -> str:
    return msg if msg.startswith(("unavailable", "skipped")) else f"unavailable: {msg}"


def _summary(answered: int, errors: list[dict], total: int) -> str:
    """'ok', 'partial (k/n queries answered)' or the reason none answered."""
    if answered == total:
        return "ok"
    if answered:
        return f"partial ({answered}/{total} queries answered)"
    return _status(errors[0]["reason"]) if errors else "unavailable"


def collect(run: Path, backend, cfg: dict) -> dict:
    sources = load_json(run / "sources.json")
    run_date = load_json(run / "run.json").get("run_date") if (run / "run.json").exists() else sources.get("run_date")
    status: dict[str, dict] = {"autocomplete": {}, "youtube": {}, "trends": {}}
    out = {"schema_version": 1, "run": run.name, "collected_at": utc_now(), "config_version": cfg.get("version"),
           "sources_sha256": sha256_file(run / "sources.json"), "topics": {}}
    api_calls = 0
    for cand in sources["candidates"]:
        queries = default_queries(cand, cfg["max_queries_per_topic"])
        ev = {"queries": queries}
        # autocomplete: every query; failures per query are kept
        acq, errs = [], []
        for q in queries:
            try:
                sug = backend.autocomplete(q)
                words = content_words(q)
                acq.append({"query": q, "suggestions": sug[:10],
                            "matching": [x for x in sug if all(w in x.lower() for w in words)][:10]})
            except Exception as exc:                  # noqa: BLE001 - recorded, never fatal
                errs.append({"query": q, "reason": _status(str(exc)[:200])})
        st = _summary(len(acq), errs, len(queries))
        ev["autocomplete"] = {"status": "ok" if acq else st, "coverage": st, "queries": acq, "errors": errs}
        # YouTube Data API: every query until the per-run cap
        vids, errs, answered = {}, [], 0
        for q in queries:
            if api_calls >= cfg["max_api_queries_per_run"]:
                errs.append({"query": q, "reason": f"skipped: quota cap of {cfg['max_api_queries_per_run']} search "
                                                   "calls per run reached"})
                continue
            try:
                items = backend.youtube(q)
                api_calls += 1
                answered += 1
                for it in items:
                    if relevant(it["title"], q, cfg["relevance_word_share"]):
                        vids[it["id"]] = it
            except Exception as exc:                  # noqa: BLE001
                reason = _status(str(exc)[:200])
                errs.append({"query": q, "reason": reason})
                if reason.startswith("skipped: no YOUTUBE_API_KEY"):
                    errs += [{"query": x, "reason": reason} for x in queries[queries.index(q) + 1:]]
                    break
        st = _summary(answered, errs, len(queries))
        if answered:
            top = sorted(vids.values(), key=lambda v: -v["views"])
            ev["youtube"] = {"status": "ok", "coverage": st, "errors": errs, "relevant": top[:25],
                             "top": [{k: v[k] for k in ("title", "channel", "published", "views")} for v in top[:3]]}
        else:
            ev["youtube"] = {"status": st, "coverage": st, "errors": errs}
        # Google Trends: all queries in one comparison (values are relative within it); mean of the queries' means
        if cfg.get("trends", {}).get("enabled", True):
            try:
                per = backend.trends(queries)
                answered_q = {q: v for q, v in per.items() if isinstance(v, dict) and "mean" in v}
                missing = [{"query": q, "reason": "unavailable: no data returned"} for q in queries if q not in answered_q]
                if answered_q:
                    ev["trends"] = {"status": "ok", "coverage": _summary(len(answered_q), missing, len(queries)),
                                    "mean": round(sum(v["mean"] for v in answered_q.values()) / len(answered_q), 1),
                                    "per_query": answered_q, "errors": missing}
                else:
                    ev["trends"] = {"status": "unavailable: no data returned", "errors": missing}
            except Exception as exc:                  # noqa: BLE001 - unofficial client: isolated, non-fatal
                ev["trends"] = {"status": _status(str(exc)[:200])}
        else:
            ev["trends"] = {"status": "skipped: disabled in config/search.json"}
        for k in status:
            key = ev[k].get("coverage", ev[k]["status"])
            status[k][key] = status[k].get(key, 0) + 1
        ev["scores"], ev["why"] = score_topic(ev, cfg, run_date)
        if "relevant" in ev["youtube"]:
            ev["youtube"]["relevant_count"] = len(ev["youtube"].pop("relevant"))
        out["topics"][cand["id"]] = ev
    n = len(out["topics"])
    out["sources_status"] = {k: "; ".join(f"{st} ({c}/{n} topics)" for st, c in v.items()) for k, v in status.items()}
    out["youtube_quota_units"] = backend.quota
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run")
    a = ap.parse_args()
    run = resolve_run(a.run)
    cfg = load_json(CONFIG / "search.json")
    backend = Fake(cfg) if os.environ.get("SEARCH_BACKEND") == "fake" else Live(cfg)
    data = collect(run, backend, cfg)
    write_json(run / "search.json", data)
    known = sum(1 for t in data["topics"].values() if t["scores"]["search_demand"] is not None)
    print(f"wrote {rel(run / 'search.json')}: {len(data['topics'])} topic(s), search demand known for {known}; "
          f"sources {', '.join(f'{k} {v}' for k, v in data['sources_status'].items())}; "
          f"YouTube quota {data['youtube_quota_units']} units")
    return 0


if __name__ == "__main__":
    sys.exit(main())
