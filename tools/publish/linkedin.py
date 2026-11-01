#!/usr/bin/env python3
"""Optional LinkedIn post after publication (publish job only; Claude never runs it).

Usage:
  python3 tools/publish/linkedin.py post runs/<run> --video-url URL [--explainer-url URL] [--ledger site/ledger.json]
  python3 tools/publish/linkedin.py post ... --dry-run          # print the request, send nothing

Environment: LINKEDIN_ACCESS_TOKEN (member token with w_member_social, from the "Share on LinkedIn" product),
LINKEDIN_AUTHOR_URN (urn:li:person:<id>), LINKEDIN_VERSION (YYYYMM, a version LinkedIn currently supports).
Member tokens expire after about 60 days and standard apps get no refresh token: renew it by hand (SETUP-AUTOMATION.md).
An expired or missing token makes this step report and skip, never fail the publication.
LINKEDIN_BACKEND=fake with LINKEDIN_FAKE_STATE=file.json records the post locally (tests).
Idempotency: a run whose ledger entry already has a LinkedIn post is skipped.
Links follow the run's own decision (video/final/youtube.json "links", from links.include or the pipeline's "links"
input): with links off the post shares the video only (linkedin.commentary_template_video), never the explainer.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "video"))
from _common import CONFIG, load_json, resolve_run  # noqa: E402
import plan as P  # noqa: E402

ENDPOINT = "https://api.linkedin.com/rest/posts"


def links_on(run: Path) -> bool:
    yp = run / "video" / "final" / "youtube.json"
    m = json.loads(yp.read_text(encoding="utf-8")) if yp.exists() else {}
    return bool(m.get("links", {}).get("included", bool(m.get("explainer_url"))))


def payload(run: Path, video_url: str, explainer_url: str, author: str) -> dict:
    channel = load_json(CONFIG / "channel.json")
    plan = P.load(run)
    with_links = links_on(run) and bool(explainer_url)
    key = "commentary_template" if with_links else "commentary_template_video"
    template = channel["linkedin"].get(key) or "New on Remaining Action: {title}. {summary} Video: {video_url}"
    text = template.format(title=plan["title"], summary=plan["summary"], explainer_url=explainer_url,
                           video_url=video_url)
    return {"author": author, "commentary": text[:2900], "visibility": "PUBLIC",
            "distribution": {"feedDistribution": "MAIN_FEED", "targetEntities": [], "thirdPartyDistributionChannels": []},
            "content": {"article": {"source": explainer_url if with_links else video_url, "title": plan["title"][:200],
                                    "description": plan["summary"][:250]}},
            "lifecycleState": "PUBLISHED", "isReshareDisabledByAuthor": False}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("post")
    p.add_argument("run")
    p.add_argument("--video-url", required=True)
    p.add_argument("--explainer-url", default="")
    p.add_argument("--ledger")
    p.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    run = resolve_run(a.run)
    if a.ledger and Path(a.ledger).exists():
        entry = json.loads(Path(a.ledger).read_text()).get("runs", {}).get(run.name, {})
        if entry.get("linkedin_post"):
            print(json.dumps({"skipped": "already posted", "post": entry["linkedin_post"]}))
            return 0
    token, author = os.environ.get("LINKEDIN_ACCESS_TOKEN"), os.environ.get("LINKEDIN_AUTHOR_URN", "")
    body = payload(run, a.video_url, a.explainer_url, author or "urn:li:person:UNSET")
    if a.dry_run:
        print(json.dumps({"dry_run": True, "endpoint": ENDPOINT, "body": body}, indent=2))
        return 0
    if os.environ.get("LINKEDIN_BACKEND") == "fake":
        state = Path(os.environ.get("LINKEDIN_FAKE_STATE", "linkedin_fake_state.json"))
        posts = json.loads(state.read_text()) if state.exists() else []
        posts.append(body)
        state.write_text(json.dumps(posts, indent=2))
        print(json.dumps({"post": f"urn:li:share:fake{len(posts)}"}))
        return 0
    if not token or not author.startswith("urn:li:person:") or not os.environ.get("LINKEDIN_VERSION"):
        print(json.dumps({"skipped": "LinkedIn not configured (token, author URN or version missing)"}))
        return 0
    req = urllib.request.Request(ENDPOINT, data=json.dumps(body).encode(), method="POST", headers={
        "Authorization": f"Bearer {token}", "Content-Type": "application/json",
        "LinkedIn-Version": os.environ["LINKEDIN_VERSION"], "X-Restli-Protocol-Version": "2.0.0"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            print(json.dumps({"post": r.headers.get("x-restli-id", ""), "status": r.status}))
    except urllib.error.HTTPError as exc:
        reason = "token expired or revoked: renew it (SETUP-AUTOMATION.md)" if exc.code == 401 else exc.read()[:300].decode(errors="replace")
        print(json.dumps({"skipped": f"LinkedIn returned {exc.code}: {reason}"}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
