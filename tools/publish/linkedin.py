#!/usr/bin/env python3
"""Optional LinkedIn post after publication (the workflow's publish job; never run by an agent).

Usage (LINKEDIN_ACCESS_TOKEN, LINKEDIN_AUTHOR_URN, LINKEDIN_VERSION in the environment; without them it skips):
  python3 tools/publish/linkedin.py post runs/<run> --video-url URL [--explainer-url URL] [--ledger L] [--dry-run]
  LINKEDIN_BACKEND=fake LINKEDIN_FAKE_STATE=file.json: records the post locally (tests)
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
from _common import CONFIG, load_json, read_json, resolve_run  # noqa: E402
import plan as P  # noqa: E402
from review_package import links_on  # noqa: E402

ENDPOINT = "https://api.linkedin.com/rest/posts"


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
        entry = read_json(a.ledger).get("runs", {}).get(run.name, {})
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
        posts = read_json(state, [])
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
