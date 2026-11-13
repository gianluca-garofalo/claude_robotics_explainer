#!/usr/bin/env python3
"""PreToolUse hook (WebFetch|Bash) of the reviewers that read the web: refuses at once (exit 2) a fetch from a host no
WebFetch allow rule covers, and curl or wget, so no reviewer waits on a permission prompt or a dead host.

Usage: reviewer_fetch_guard.py [SETTINGS.json ...]; default: the project's settings, local settings and user settings.
"""
import sys
if sys.version_info < (3, 7):          # fail closed: an old python3 must never let a blocked action through
    sys.stderr.write("Remaining Action hook: python3 %d.%d is too old (3.7 or later is needed); blocked to stay safe. "
                     "Put a newer Python first in PATH.\n" % sys.version_info[:2])
    sys.exit(2)
import json
import os
import re
from pathlib import Path
from urllib.parse import urlsplit

REPO = Path(__file__).resolve().parents[2]
FETCHERS = {"curl", "wget"}            # ask rules in the settings: they wait on a prompt, even in auto mode
INSTEAD = ("record the source as not reachable (not verified), or use a reachable record such as arXiv or Crossref "
           "metadata by DOI (https://api.crossref.org/works/<doi>).")


def settings_files():
    if sys.argv[1:]:
        return [Path(p) for p in sys.argv[1:]]
    user = Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude") / "settings.json"
    return [REPO / ".claude" / "settings.json"] + [p for p in (REPO / ".claude" / "settings.local.json", user)
                                                   if p.is_file()]


def allowed_hosts(files):
    """The host patterns of the WebFetch allow rules; a bare WebFetch rule allows every host (*)."""
    out = []
    for f in files:
        for rule in (json.loads(f.read_text(encoding="utf-8")).get("permissions") or {}).get("allow") or []:
            m = re.fullmatch(r"WebFetch(?:\(domain:(.+)\))?", str(rule).strip())
            if m:
                out.append((m.group(1) or "*").lower().rstrip("."))
    return out


def covered(host, pattern):
    """Claude Code's domain match: a leading *. covers subdomains at any depth, a bare * all, another * one label."""
    if pattern == "*":
        return True
    deep = pattern.startswith("*.")
    core = r"[^.]*".join(re.escape(part) for part in (pattern[2:] if deep else pattern).split("*"))
    return re.fullmatch((r".+\." if deep else "") + core, host) is not None


def refusal(event):
    tool, ti = event.get("tool_name"), event.get("tool_input") or {}
    if tool == "Bash":
        from block_publish import simple_commands, strip_prefix   # the publish guard's shell parser, beside this file
        progs = {os.path.basename(a[0]) for a in map(strip_prefix, simple_commands(ti.get("command") or "")) if a}
        if progs & FETCHERS:
            return ("curl and wget wait on a permission prompt here: read web pages with WebFetch, on the allowed "
                    "hosts. For a source on another host, " + INSTEAD)
        return None
    if tool != "WebFetch":
        return None
    url = str(ti.get("url") or "").strip().replace("\\", "/")     # as WebFetch's URL parser reads a backslash
    try:
        parts = urlsplit(url)
        host = (parts.hostname or "").rstrip(".") if parts.scheme in ("http", "https") else ""
    except ValueError:
        host = ""
    if not host:
        return f"Not fetched: {url!r} is not an http(s) URL with a host."
    try:
        patterns = allowed_hosts(settings_files())
    except (OSError, ValueError) as exc:          # fail closed: without the allow rules nothing is fetched
        return (f"Not fetched: the WebFetch allow rules could not be read ({exc}), so every fetch is refused: "
                "record the source as not reachable (not verified) and go on.")
    if any(covered(host, p) for p in patterns):
        return None
    return (f"Not fetched: {host} is not among the hosts WebFetch may reach here ({', '.join(patterns) or 'none'}). "
            f"Try no other URL on {host}; " + INSTEAD)


def main() -> int:
    try:
        event = json.load(sys.stdin)
    except json.JSONDecodeError:                  # fail closed: an unreadable event blocks the call
        print("Remaining Action hook: could not read the hook input; blocked to stay safe", file=sys.stderr)
        return 2
    reason = refusal(event)
    if reason:
        print(reason, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001 - fail closed: a crash blocks the action and says why
        sys.stderr.write(f"Remaining Action hook {Path(__file__).name} failed ({type(exc).__name__}: {exc}); "
                         "blocked to stay safe\n")
        sys.exit(2)
