#!/usr/bin/env python3
"""PreToolUse hook (Bash): block publishing, uploading and approval commands in any spelling; exit 2 says why.

Standard library only. It reads the command text: an upload made from inside a script is not caught.
"""
import sys
from pathlib import Path
if sys.version_info < (3, 7):          # fail closed: an old python3 must never let a blocked action through
    sys.stderr.write("Remaining Action hook: python3 %d.%d is too old (3.7 or later is needed); blocked to stay safe. "
                     "Put a newer Python first in PATH.\n" % sys.version_info[:2])
    sys.exit(2)
import json
import os
import re
import shlex
import sys

WRAPPERS = {"sudo", "env", "nice", "nohup", "time", "timeout", "command", "builtin", "stdbuf", "xargs", "exec",
            "npx", "uvx", "pipx"}
SHELLS = {"sh", "bash", "zsh", "dash", "ksh", "fish"}
UPLOAD_BINARIES = {"youtube-upload", "youtubeuploader", "youtube_uploader", "ytupload", "tiktok-uploader",
                   "vimeo-upload"}
STREAM_RE = re.compile(r"^(rtmps?|srt|rtsp)://", re.I)
UPLOAD_HOST_RE = re.compile(r"(googleapis\.com/upload|youtube\.com|api\.vimeo\.com|open\.tiktokapis\.com|"
                            r"graph\.facebook\.com|api\.twitter\.com|api\.x\.com|api\.linkedin\.com|zenodo\.org/api|"
                            r"api\.github\.com|uploads\.github\.com|upload\.pypi\.org)", re.I)
GIT_OPTS_WITH_VALUE = {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path", "--config-env"}
SEND_FLAGS = {"-T", "--upload-file", "-F", "--form", "--form-string", "--json", "--post-data", "--post-file",
              "--body-data", "--body-file"}
GH_WRITES = {"pr create", "pr merge", "pr ready", "pr comment", "pr review", "pr edit", "repo create", "repo edit",
             "repo delete", "repo rename", "repo fork", "gist create", "gist edit", "workflow run", "workflow enable",
             "workflow disable", "issue create", "issue comment", "issue edit", "issue close", "issue reopen",
             "issue delete", "label create", "run rerun", "run cancel", "secret set", "secret delete",
             "variable set", "variable delete"}


def simple_commands(cmd: str):
    lex = shlex.shlex(cmd.replace("\n", " ; "), posix=True, punctuation_chars=";&|()")
    lex.whitespace_split = True
    lex.commenters = ""
    try:
        toks = list(lex)
    except ValueError:
        toks = cmd.split()
    cur = []
    for w in toks:
        if w and set(w) <= set(";&|()"):
            if cur:
                yield cur
            cur = []
        else:
            cur.append(w)
    if cur:
        yield cur


def strip_prefix(argv):
    i = 0
    while i < len(argv):
        w = argv[i]
        if re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", w):
            i += 1
            continue
        base = os.path.basename(w)
        if base not in WRAPPERS:
            break
        i += 1
        if base == "timeout" and i < len(argv) and re.match(r"^[0-9.]+[smhd]?$", argv[i]):
            i += 1
        if base in ("pipx", "uvx") and i < len(argv) and argv[i] == "run":
            i += 1
        while i < len(argv) and argv[i].startswith("-") and base in ("sudo", "env", "nice", "stdbuf", "xargs", "npx"):
            i += 1
    return argv[i:]


def git_subcommand(args):
    i = 0
    while i < len(args):
        a = args[i]
        if a in GIT_OPTS_WITH_VALUE:
            i += 2
        elif a.startswith("-"):
            i += 1
        else:
            return a
    return None


def http_sends_data(prog, args):
    joined = " ".join(args)
    if {a.split("=", 1)[0] if a.startswith("--") else a for a in args} & SEND_FLAGS:
        return True
    if any(re.match(r"^(-d|--data(-[a-z]+)?)(=.*)?$", a) or re.match(r"^-d[^a-z-]", a) for a in args):
        return True
    if re.search(r"(?:^|\s)(?:-X\s*|--request[ =]|--method[ =])(POST|PUT|PATCH|DELETE)\b", joined, re.I):
        return True
    return prog in ("http", "https", "xh") and bool(args) and args[0].upper() in ("POST", "PUT", "PATCH", "DELETE")


READ_ONLY = {"cat", "head", "tail", "less", "more", "ls", "grep", "rg", "wc", "stat", "file", "jq", "sha256sum",
             "shasum", "diff", "cmp"}


def reason_for(argv, depth=0):
    argv = strip_prefix(argv)
    if not argv:
        return None
    prog = os.path.basename(argv[0])
    args = argv[1:]
    if any("approve_series.py" in a or "approve_topic.py" in a or "record_approval.py" in a for a in argv):
        return "approving a topic or a series plan is the user's decision (they run the approval tool themselves)"
    if any("plan_approval.json" in a or a.endswith("/approval.json") or a == "approval.json" for a in argv) \
            and prog not in READ_ONLY:
        return "approval files (approval.json, plan_approval.json) are written only by the user's approval tools"
    if prog in SHELLS and "-c" in args:
        k = args.index("-c") + 1
        return check(args[k] if k < len(args) else "", depth + 1)
    if prog == "eval":
        return check(" ".join(args), depth + 1)
    if prog == "git":
        sub = git_subcommand(args)
        if sub in ("push", "send-email", "request-pull"):
            return f"git {sub} publishes commits"
    if prog == "gh":
        pos, skip = [], False
        for a in args:                           # positional words, without the values of -R/--repo/--hostname
            if skip:
                skip = False
            elif a in ("-R", "--repo", "--hostname"):
                skip = True
            elif not a.startswith("-"):
                pos.append(a)
        pair = " ".join(pos[:2])
        if pos[:1] == ["release"] or pair in GH_WRITES:
            return f"gh {pair} changes or publishes on GitHub"
        if pos[:1] == ["api"] and (re.search(r"(-X|--method)[ =]?(POST|PUT|PATCH|DELETE)", " ".join(args), re.I)
                                   or set(args) & {"-f", "-F", "--field", "--raw-field", "--input"}):
            return "gh api with a write method or fields"
    if prog in ("npm", "pnpm", "yarn", "cargo", "poetry", "uv", "flit", "hatch") and "publish" in args:
        return f"{prog} publish uploads a package"
    if prog == "twine" and "upload" in args:
        return "twine upload publishes a package"
    if prog.startswith("python") and "-m" in args:
        k = args.index("-m") + 1
        if k < len(args) and args[k] == "twine" and "upload" in args:
            return "twine upload publishes a package"
    if prog in UPLOAD_BINARIES or any("upload_video.py" in a for a in argv):
        return f"{prog} uploads a video"
    if prog in ("docker", "podman") and args[:1] == ["push"]:
        return f"{prog} push uploads an image"
    if prog == "aws" and args[:1] == ["s3"] and len(args) > 1 and args[1] in ("cp", "sync", "mv") and \
            args[-1].startswith("s3://"):
        return "aws s3 upload"
    if prog in ("gsutil", "gcloud") and args and args[-1].startswith("gs://") and \
            any(a in ("cp", "rsync", "mv") for a in args):
        return f"{prog} upload to a bucket"
    if prog == "rclone" and args[:1] and args[0] in ("copy", "sync", "move", "copyto", "moveto"):
        return "rclone copies to a remote"
    if prog in ("scp", "rsync", "sftp"):
        tail = [a for a in args if not a.startswith("-")]
        if tail and (re.match(r"^[^/\s]+:", tail[-1]) or tail[-1].startswith("rsync://")):
            return f"{prog} copies files to a remote host"
    if prog in ("curl", "wget", "http", "https", "xh"):
        if http_sends_data(prog, args):
            return f"{prog} sends data (an upload or write request)"
        if any(UPLOAD_HOST_RE.search(a) for a in args if "://" in a):
            return f"{prog} targets an upload or social media API"
    if prog in ("ffmpeg", "obs", "gst-launch-1.0", "streamlink") and any(STREAM_RE.match(a) for a in args):
        return "live streaming to a remote server"
    return None


def check(cmd: str, depth: int = 0):
    if depth > 3 or not cmd:
        return None
    if re.search(r">\s*\S*(plan_approval|/approval)\.json", cmd) or re.search(r">\s*approval\.json", cmd):
        return "approval files (approval.json, plan_approval.json) are written only by the user's approval tools"
    for argv in simple_commands(cmd):
        r = reason_for(argv, depth)
        if r:
            return r
    return None


def main() -> int:
    try:
        event = json.load(sys.stdin)
    except json.JSONDecodeError:                  # fail closed: an unreadable event blocks the call
        print("Remaining Action hook: could not read the hook input; blocked to stay safe", file=sys.stderr)
        return 2
    if event.get("tool_name") != "Bash":
        return 0
    r = check((event.get("tool_input") or {}).get("command", ""))
    if r:
        print(f"Blocked by project policy: {r}. Nothing is published, pushed or uploaded from Claude Code in this "
              "project, and the approval that publishes a video (labels, deployment reviews, repository variables) "
              "is the user's alone. Publication happens only in the GitHub workflow after the user approves the "
              "video (see AGENTS.md). Prepare the files and tell the user what is ready instead.", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001 - fail closed: a crash blocks the action and says why
        sys.stderr.write(f"Remaining Action hook {Path(__file__).name} failed ({type(exc).__name__}: {exc}); "
                         "blocked to stay safe\n")
        sys.exit(2)
