#!/usr/bin/env python3
"""Lint the agent configuration, the automation's publishing boundary and the repository's hygiene.

Usage:
  python3 tools/lint_project.py                      # all of it
  python3 tools/lint_project.py --config             # schemas/, .agents/skills and .claude/
  python3 tools/lint_project.py --automation         # ci/*.json and .github/
  python3 tools/lint_project.py --hygiene            # the files git does not ignore, and the documents' shell blocks
  python3 tools/lint_project.py --docs FILE.md ...   # only the shell-block check, on these files
Exit status 1 on errors.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import REPO  # noqa: E402  (moves python3 into the .venv when there is one)

try:
    import jsonschema
    import yaml
except ImportError as exc:  # pragma: no cover
    print(f"error: {exc.name} is required: pip install -r requirements-tools.txt, or use .venv/bin/python",
          file=sys.stderr)
    sys.exit(3)
from validate import schema_errors  # noqa: E402

CLAUDE = REPO / ".claude"
SKILLS = REPO / ".agents" / "skills"           # .claude/skills links here
TOOLS = {"Read", "Grep", "Glob", "Bash", "Edit", "Write", "NotebookEdit", "WebFetch", "WebSearch", "TodoWrite",
         "Skill", "Agent", "LSP", "PowerShell", "Monitor", "TaskStop", "SendMessage", "ToolSearch", "EnterWorktree",
         "ExitWorktree", "Artifact", "Workflow"}
SETTINGS_KEYS_USED = {"$schema", "permissions", "hooks", "env", "sandbox"}
SIDE_EFFECT_SKILLS = {"produce-explainer", "approve-topic", "produce-episode", "produce-from-source", "plan-series"}
SKILLS_LINK_FIX = "rm -rf .claude/skills && ln -s ../.agents/skills .claude/skills"
# The owner's folders (AGENTS.md, Rules): an Edit deny rule each, which the sandbox also applies to Bash.
OWNER_DIRS = ("config", "series", "sources", "tools/hooks", "tools/human", "tools/publish", "tools/ci", ".github", "ci")
# Run files that only the pipeline's tools write: deny them as bare names. Claude Code applies a bare name at any depth
# to its file tools, but gives the sandbox only <project>/<name>; a **/ glob becomes an OS-level deny on macOS that
# also stops the tool that writes the file.
TOOL_WRITTEN = ("selection.json", "episode.json", "search.json", "covered.json", "published.json")
# What may leave the sandbox: a repository tool and its subcommand (writes the sandbox denies, or a browser).
SANDBOX_EXCLUDABLE = re.compile(r"^(python3 tools/[\w/-]+\.py|node tools/[\w/-]+\.js)( [a-z][\w-]*)? \*$")
# Claude steps of the workflow that read the web; every other one runs with --disallowedTools "WebFetch WebSearch".
WEB_SKILLS = {"robotics-news-scout", "didactic-html-writer", "explainer-review"}

TEXT_SUFFIXES = {".md", ".py", ".js", ".json", ".toml", ".txt", ".sh", ".html", ".css", ".yml", ".yaml", ".cfg", ""}
SKIP_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__", "media", "runs", ".cache"}   # without git only
HYGIENE = [
    ("absolute-path", re.compile(r"(/home/[a-z_][\w-]*/|/Users/[A-Za-z][\w.-]*/|/root/|/private/var/folders/|[A-Z]:\\\\Users\\\\)")),
    ("email", re.compile(r"\b[A-Za-z0-9._%+-]+@(?:[A-Za-z0-9-]+\.)+(?:com|org|net|edu|gov|mil|int|io|ai|dev|app|"
                         r"info|biz|me|co|[a-z]{2})\b")),
    ("secret", re.compile(r"(sk-ant-[A-Za-z0-9_-]{10,}|sk-[A-Za-z0-9]{32,}|AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{30,}|"
                          r"github_pat_[A-Za-z0-9_]{30,}|xox[abprs]-[A-Za-z0-9-]{10,}|-----BEGIN [A-Z ]*PRIVATE KEY-----)")),
    ("model-id", re.compile(r"\bclaude-(?:\d|opus|sonnet|haiku|fable|instant)[\w.-]*|\b(?:Opus|Sonnet|Haiku|Fable) \d", re.I)),
]
EMAIL_OK = re.compile(r"@(example\.(org|com|net)|users\.noreply\.github\.com)$")


class Out:
    def __init__(self):
        self.errors, self.warnings = [], []

    def err(self, where, msg):
        self.errors.append(f"{where}: {msg}")

    def warn(self, where, msg):
        self.warnings.append(f"{where}: {msg}")

    def schema(self, where, name, data):
        for msg in schema_errors(name, data):
            self.err(where, msg)


def rel(p: Path) -> str:
    return p.relative_to(REPO).as_posix()


def repo_files() -> list[Path]:
    """The files git does not ignore, tracked or not; without git, a walk that skips SKIP_DIRS."""
    try:
        out = subprocess.run(["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"], cwd=REPO,
                             capture_output=True, check=True).stdout.decode()
        files = [REPO / f for f in out.split("\0") if f]
    except (OSError, subprocess.CalledProcessError):
        files = []
        for d, dirs, names in os.walk(REPO):
            dirs[:] = [x for x in dirs if x not in SKIP_DIRS]
            files += [Path(d) / n for n in names]
    return sorted({p for p in files if p.is_file()})


def frontmatter(path: Path, out: Out):
    text = path.read_text(encoding="utf-8")
    end = text.find("\n---", 4)
    if not text.startswith("---\n") or end == -1:
        out.err(rel(path), "frontmatter is not closed with ---" if text.startswith("---\n") else
                "frontmatter must start on the first line with ---")
        return None, text
    try:
        data = yaml.safe_load(text[4:end]) or {}
    except yaml.YAMLError as exc:
        out.err(rel(path), f"frontmatter YAML does not parse: {exc}")
        return None, text
    if not isinstance(data, dict):
        out.err(rel(path), "frontmatter must be a mapping")
        return None, text
    return data, text[end + 4:]


def _strings(node):
    if isinstance(node, dict):
        for v in node.values():
            yield from _strings(v)
    elif isinstance(node, list):
        for v in node:
            yield from _strings(v)
    elif isinstance(node, str):
        yield node


def hook_scripts(where: str, hooks, out: Out):
    for s in _strings(hooks):
        for m in re.finditer(r"\$\{CLAUDE_PROJECT_DIR\}/([^\s\"']+)", s):
            if not (REPO / m.group(1)).exists():
                out.err(where, f"hook script {m.group(1)} does not exist")


def lint_skills(out: Out, agents: set):
    for d in sorted(p for p in SKILLS.iterdir() if p.is_dir()):
        p = d / "SKILL.md"
        if not p.exists():
            out.err(rel(d), "skill folder without SKILL.md")
            continue
        fm, body = frontmatter(p, out)
        if fm is None:
            continue
        where = rel(p)
        out.schema(where, "skill", {"name": d.name, **fm})
        if len(str(fm.get("description", ""))) + len(str(fm.get("when_to_use", ""))) > 1536:
            out.err(where, "description + when_to_use exceed 1,536 characters (truncated in the skill listing)")
        if re.search(r"[<>]", str(fm.get("description", ""))):
            out.warn(where, "angle brackets in description are shown as &lt; &gt;")
        if fm.get("name") and fm["name"] != d.name:
            out.warn(where, f"name {fm['name']!r} differs from the folder name {d.name!r}")
        if d.name.lower() == "synced" or d.name.startswith("anthropic-skills"):
            out.err(where, "reserved skill folder name")
        if d.name in SIDE_EFFECT_SKILLS and fm.get("disable-model-invocation") is not True:
            out.err(where, "side-effect or human-only skill must set disable-model-invocation: true")
        if fm.get("context") == "fork" and fm.get("agent") and fm["agent"] not in agents | {"Explore", "Plan",
                                                                                            "general-purpose"}:
            out.err(where, f"agent {fm['agent']!r} is not defined")
        hook_scripts(where, fm.get("hooks"), out)
        lines = p.read_text(encoding="utf-8").count("\n")
        if lines > 500:
            out.err(where, f"{lines} lines; keep SKILL.md under 500 and move detail to supporting files")
        for link in re.findall(r"\]\(([^)#\s]+)\)", body):
            if not re.match(r"^[a-z]+://", link) and not (d / link).exists():
                out.err(where, f"linked file {link} does not exist")
        for path in re.findall(r"`((?:tools|templates|config|sources|series|\.claude|\.agents)/[\w./-]+)`", body):
            if "<" not in path and not (REPO / path).exists():
                out.err(where, f"mentions {path}, which does not exist")


def lint_agents(out: Out) -> set:
    names = set()
    for p in sorted((CLAUDE / "agents").glob("*.md")):
        fm, body = frontmatter(p, out)
        if fm is None:
            continue
        where = rel(p)
        out.schema(where, "agent", fm)
        name = str(fm.get("name", ""))
        if name in names:
            out.err(where, f"duplicate agent name {name}")
        names.add(name)
        tools = fm.get("tools")
        for t in [] if tools is None else tools if isinstance(tools, list) else [x.strip() for x in str(tools).split(",")]:
            base = re.sub(r"\(.*\)$", "", str(t))
            if base not in TOOLS and not base.startswith("mcp__"):
                out.err(where, f"unknown tool {t!r}")
        hook_scripts(where, fm.get("hooks"), out)
        if not body.strip():
            out.err(where, "empty system prompt")
    return names


def lint_rules(out: Out):
    for p in sorted((CLAUDE / "rules").rglob("*.md")):
        fm, _ = frontmatter(p, out)
        if fm is not None:
            out.schema(rel(p), "rule", fm)


def lint_workflows(out: Out):
    node = shutil.which("node")
    for p in sorted((CLAUDE / "workflows").glob("*.js")):
        src, where = p.read_text(encoding="utf-8"), rel(p)
        if not src.lstrip().startswith("export const meta = {"):
            out.err(where, "the first statement must be `export const meta = {...}`")
        m = re.search(r"export const meta = (\{.*?\n\})", src, re.S)
        if not m:
            out.err(where, "could not find the meta object literal")
        else:
            meta = m.group(1)
            for k in ("name", "description"):
                if not re.search(rf"\b{k}\s*:\s*'[^']+'", meta):
                    out.err(where, f"meta.{k} must be a string literal")
            if re.search(r"\$\{|\.\.\.|\w\(", meta):
                out.err(where, "meta must be a plain literal (no interpolation, spreads or calls)")
            titles = re.findall(r"title:\s*'([^']+)'", meta)
            for a, b in re.findall(r"phase\s*:\s*'([^']+)'|phase\('([^']+)'\)", src):
                if titles and (a or b) not in titles:
                    out.warn(where, f"phase {a or b!r} is not listed in meta.phases")
        for bad in (r"Date\.now\(", r"Math\.random\(", r"new Date\(\)", r"\bimport\("):
            if re.search(bad, src):
                out.err(where, f"{bad} is not allowed in workflow scripts (breaks resume)")
        if re.search(r"\bmodel\s*:", src):
            out.err(where, "project policy: no model overrides in workflow agents")
        if not node:
            out.warn(where, "node not found: workflow syntax not checked")
            continue
        with tempfile.TemporaryDirectory() as td:          # the body runs inside an async function at load time
            f = Path(td) / "wf.mjs"
            f.write_text("export {};\n(async () => {\n" + src.replace("export const meta", "const meta", 1) + "\n})\n",
                         encoding="utf-8")
            r = subprocess.run([node, "--check", str(f)], capture_output=True, text=True)
            if r.returncode != 0:
                out.err(where, "JavaScript syntax error: " + (r.stderr.strip().splitlines() or ["?"])[-1])


def lint_schemas(out: Out):
    for p in sorted((REPO / "schemas").glob("*.json")):
        try:
            jsonschema.Draft202012Validator.check_schema(json.loads(p.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, jsonschema.SchemaError) as exc:
            out.err(rel(p), f"not a draft 2020-12 schema: {str(exc).splitlines()[0]}")


def check_rules(where: str, perms: dict, out: Out, known: set = TOOLS):
    for kind in ("allow", "ask", "deny"):
        for rule in perms.get(kind, []) if isinstance(perms.get(kind), list) else []:
            tool = str(rule).split("(")[0]
            if tool not in known and not tool.startswith("mcp__"):
                out.err(where, f"permissions.{kind}: unknown tool in {rule!r}")


def lint_settings(out: Out):
    p = CLAUDE / "settings.json"
    where = rel(p)
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        out.err(where, f"not strict JSON: {exc}")
        return
    out.schema(where, "settings", data)
    for k in sorted(set(data) - SETTINGS_KEYS_USED):
        out.warn(where, f"top-level key {k!r} is not one this project uses; check it against the settings reference")
    perms = data.get("permissions") if isinstance(data.get("permissions"), dict) else {}
    check_rules(where, perms, out, TOOLS | {"*"})
    for rule in (r for k in ("allow", "ask", "deny") for r in perms.get(k, []) if isinstance(r, str)):
        if re.match(r"^(Write|NotebookEdit|Glob)\(", rule):
            out.err(where, f"{rule!r} never matches: use Edit(...) or Read(...) path rules")
    hook_scripts(where, data.get("hooks"), out)
    deny_rules = [str(r) for r in perms.get("deny", [])]
    deny = " ".join(deny_rules)
    for must in ("git push", "gh release", "approval.json"):
        if must not in deny:
            out.err(where, f"project policy: deny rules must cover {must!r}")
    for d in OWNER_DIRS:
        if f"Edit(/{d}/**)" not in deny_rules:
            out.err(where, f"deny rules must include Edit(/{d}/**): {d}/ is the owner's (AGENTS.md, Rules)")
    for name in TOOL_WRITTEN:
        if f"Edit({name})" not in deny_rules:
            out.err(where, f"deny rules must include Edit({name}): only a tool writes it")
        for rule in deny_rules:
            if rule.startswith("Edit(") and rule.endswith(f"/{name})"):
                out.err(where, f"{rule}: write Edit({name}); with the sandbox on, a path pattern also stops the tool "
                               f"that writes {name} on macOS")
    lint_sandbox(where, data.get("sandbox"), perms, out)


def lint_sandbox(where: str, sb, perms: dict, out: Out):
    """The project's sandbox: on, no unsandboxed retry, the allow rules still decide, every Bash host explicit."""
    if not isinstance(sb, dict) or sb.get("enabled") is not True:
        out.err(where, "sandbox.enabled must be true: the deny rules and the network allowlist then hold for Bash too")
        return
    if sb.get("allowUnsandboxedCommands") is not False:
        out.err(where, "sandbox.allowUnsandboxedCommands must be false: no retry outside the sandbox")
    if sb.get("autoAllowBashIfSandboxed") is not False:
        out.err(where, "sandbox.autoAllowBashIfSandboxed must be false: on Linux the sandbox cannot hold a **/ rule "
                       "such as Edit(**/approval.json), so the allow rules keep deciding which commands run")
    for cmd in sb.get("excludedCommands") or []:
        if not SANDBOX_EXCLUDABLE.match(str(cmd)):
            out.err(where, f"sandbox.excludedCommands {cmd!r}: only `python3 tools/<x>.py [subcommand] *` or "
                           "`node tools/<x>.js *` may run outside the sandbox")
    net = sb.get("network") if isinstance(sb.get("network"), dict) else {}
    allowed, denied = set(net.get("allowedDomains") or []), set(net.get("deniedDomains") or [])
    if not allowed:
        out.err(where, "sandbox.network.allowedDomains must list the hosts Bash needs")
    for rule in perms.get("allow", []):
        m = re.match(r"^WebFetch\(domain:(.+)\)$", str(rule))
        if m and m.group(1) not in allowed | denied:
            out.err(where, f"{rule}: Claude Code also adds this host to the hosts Bash may reach; list it in "
                           "sandbox.network.allowedDomains (Bash needs it) or deniedDomains (only WebFetch does)")
    for host in sorted(allowed & denied):
        out.err(where, f"sandbox.network: {host} is both allowed and denied")


def skills_link_problem(link: Path, target: Path) -> str | None:
    """None when `link` is a symbolic link that resolves to `target`, else what is wrong with it."""
    if link.is_symlink():
        if link.resolve() == target.resolve():
            return None
        return f"links to {os.readlink(link)}, not to ../.agents/skills"
    if link.is_dir():
        return "is a folder, not a symbolic link (a zip download or a copy replaced the link)"
    if link.exists():
        return "is a file, not a symbolic link (a checkout without symbolic links, as on Windows without WSL)"
    return "is missing"


def lint_skills_link(out: Out):
    problem = skills_link_problem(CLAUDE / "skills", SKILLS)
    if problem:
        out.err(".claude/skills", f"{problem}: Claude Code finds the skills through it. Fix: {SKILLS_LINK_FIX}")


CI_MUST_DENY = ("git push", "Bash(gh *)", "Bash(curl *)", "tools/publish", "auto_select", "approval.json",
                "selection.json", "episode.json", "Edit(tools/**)", "Edit(config/**)", "Edit(series/**)", ".github/**")
CLAUDE_ACTION = "anthropics/claude-code-action"
CLAUDE_SECRETS = {"ANTHROPIC_API_KEY", "CLAUDE_CODE_OAUTH_TOKEN"}
PUBLISH_SECRET = re.compile(r"secrets\.(YOUTUBE_(CLIENT|REFRESH)|LINKEDIN_)")   # the read-only YOUTUBE_API_KEY is data
RUNS_RUN_CODE = re.compile(r"render_video\.sh|run_code_checks\.py")   # they execute code/ and video/scenes/


def lint_ci_settings(out: Out):
    files = sorted((REPO / "ci").glob("*.json"))
    if not files:
        out.err("ci/", "no CI settings for Claude (ci/claude-ci-settings.json)")
    for p in files:
        where = rel(p)
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            out.err(where, f"not strict JSON: {exc}")
            continue
        out.schema(where, "ci_settings", data)
        perms = data.get("permissions") if isinstance(data.get("permissions"), dict) else {}
        check_rules(where, perms, out)
        for rule in (r for k in ("allow", "ask", "deny") for r in perms.get(k, []) if isinstance(r, str)):
            if re.match(r"^(Edit|Read)\(/[^/]", rule):
                out.err(where, f"{rule!r}: these settings are installed as user settings, where /path means "
                               "~/.claude/path; use a relative pattern")
        deny = " ".join(map(str, perms.get("deny", [])))
        for must in CI_MUST_DENY:
            if must not in deny:
                out.err(where, f"deny rules must cover {must!r}")
        if any(str(r).startswith(("Bash(gh", "Bash(git push", "Bash(curl")) for r in perms.get("allow", [])):
            out.err(where, "allow rules must not open gh, git push or curl")
        sb = data.get("sandbox") if isinstance(data.get("sandbox"), dict) else None
        if sb is not None:
            if (sb.get("network") or {}).get("allowedDomains"):
                out.warn(where, "sandbox: Bash may reach " + ", ".join(sb["network"]["allowedDomains"]))
            if (sb.get("network") or {}).get("strictAllowlist") is not True:
                out.err(where, "sandbox.network.strictAllowlist must be true: otherwise the project's allowedDomains "
                               "and WebFetch(domain:...) rules add their hosts to the ones Bash may reach in CI")
            if not any(v.get("name") == "GITHUB_TOKEN" and v.get("mode") == "deny"
                       for v in (sb.get("credentials") or {}).get("envVars", []) if isinstance(v, dict)):
                out.err(where, "sandbox.credentials must deny GITHUB_TOKEN")


def _run_blocks(wf: dict):
    jobs = [j for j in (wf.get("jobs") or {}).values() if isinstance(j, dict)]
    runs = wf.get("runs") if isinstance(wf.get("runs"), dict) else {}
    for steps in [j.get("steps") or [] for j in jobs] + [runs.get("steps") or []]:
        yield from (st["run"] for st in steps if isinstance(st, dict) and isinstance(st.get("run"), str))


def lint_actions(out: Out):
    gh = REPO / ".github"
    for p in sorted(gh.glob("workflows/*.yml")) + sorted(gh.glob("actions/*/action.yml")):
        where, text = rel(p), p.read_text(encoding="utf-8")
        try:
            wf = yaml.safe_load(text)
        except yaml.YAMLError as exc:
            out.err(where, f"YAML does not parse: {exc}")
            continue
        if any("${{" in block for block in _run_blocks(wf)):
            out.err(where, "a run script contains ${{ ... }}: pass the value through env instead (expression injection)")
        if p.name == "action.yml":
            continue
        on = wf.get("on", wf.get(True, {}))
        if "permissions" not in wf:
            out.err(where, "top-level permissions missing: start from permissions: {} and grant per job")
        if isinstance(on, dict) and "schedule" in on and CLAUDE_ACTION in text and "PIPELINE_ENABLED" not in text:
            out.err(where, "scheduled workflow that runs Claude without the PIPELINE_ENABLED kill switch")
        for name, job in (wf.get("jobs") or {}).items():
            jw, strings = f"{where} jobs.{name}", list(_strings(job))
            steps = job.get("steps", []) if isinstance(job, dict) else []
            claude = [st for st in steps if str(st.get("uses", "")).startswith(CLAUDE_ACTION)]
            if any(PUBLISH_SECRET.search(x) for x in strings) and "environment" not in job:
                out.err(jw, "uses YouTube or LinkedIn secrets outside an environment")
            job_env = " ".join(_strings(job.get("env") or {})) if isinstance(job, dict) else ""
            for st in steps:
                if isinstance(st.get("run"), str) and RUNS_RUN_CODE.search(st["run"]):
                    held = set(re.findall(r"secrets\.([A-Z0-9_]+)", job_env + " " +
                                          " ".join(_strings(st.get("env") or {})))) - {"GITHUB_TOKEN"}
                    if held:
                        out.err(jw, f"step {st.get('name', '?')!r} runs code written during the run while "
                                    f"holding {sorted(held)}")
            if not claude:
                continue
            if "environment" in job:
                out.err(jw, "runs Claude inside an environment (its secrets would be exposed)")
            perms = job.get("permissions")
            if not isinstance(perms, dict) or any(v != "read" for v in perms.values()):
                out.err(jw, "runs Claude: permissions must be explicit and read-only")
            secrets = {m for x in strings for m in re.findall(r"secrets\.([A-Z0-9_]+)", x)}
            if secrets - CLAUDE_SECRETS:
                out.err(jw, f"runs Claude: holds secrets {sorted(secrets - CLAUDE_SECRETS)}")
            if str((job.get("env") or {}).get("CLAUDE_CODE_SUBPROCESS_ENV_SCRUB")) != "1":
                out.err(jw, "runs Claude: set CLAUDE_CODE_SUBPROCESS_ENV_SCRUB: \"1\"")
            for st in steps:
                if str(st.get("uses", "")).startswith("actions/checkout") and \
                        (st.get("with") or {}).get("persist-credentials") is not False:
                    out.err(jw, "runs Claude: every checkout needs persist-credentials: false")
            for st in claude:
                w = st.get("with") or {}
                args, name = str(w.get("claude_args", "")), st.get("name", "?")
                for flag in ("--max-turns", "--max-budget-usd", "--permission-mode dontAsk"):
                    if flag not in args:
                        out.err(jw, f"step {name!r}: claude_args needs {flag}")
                if re.search(r"--model\b|--dangerously|bypassPermissions", args):
                    out.err(jw, f"step {name!r}: no model override or permission bypass")
                if not w.get("settings"):
                    out.err(jw, f"step {name!r}: pass the CI settings (ci/*.json)")
                elif f"--settings {w['settings']}" not in args:
                    out.err(jw, f"step {name!r}: claude_args needs --settings {w['settings']} as well: the settings "
                                "input installs them as user settings, below the project's .claude/settings.json")
                skill = re.match(r"^\s*/([\w-]+)", str(w.get("prompt", "")))
                no_web = re.search(r"--disallowedTools[ =]\"?[^\"]*\bWebFetch\b[^\"]*\bWebSearch\b|"
                                   r"--disallowedTools[ =]\"?[^\"]*\bWebSearch\b[^\"]*\bWebFetch\b", args)
                if not (skill and skill.group(1) in WEB_SKILLS) and not no_web:
                    out.err(jw, f"step {name!r}: needs no web: add --disallowedTools \"WebFetch WebSearch\" to "
                                "claude_args (or add its skill to WEB_SKILLS in tools/lint_project.py)")


SH_GUARD = '[ -n "${BASH_VERSION:-}" ] || exec bash "$0" "$@"'    # sh or zsh hand the script over to bash
SHELL_LANGS = {"bash", "sh", "shell", "zsh", "console"}


def shell_blocks(path: Path):
    """[(line number of the first command, [lines])] for the fenced shell blocks of a Markdown file."""
    blocks, lines, i = [], path.read_text(encoding="utf-8").splitlines(), 0
    while i < len(lines):
        m = re.match(r"^\s*(`{3,}|~{3,})\s*([\w+-]*)", lines[i])
        if not m:
            i += 1
            continue
        fence, j = m.group(1), i + 1
        while j < len(lines) and not lines[j].strip().startswith(fence):
            j += 1
        if m.group(2).lower() in SHELL_LANGS:
            body = lines[i + 1:j]
            indent = min((len(x) - len(x.lstrip()) for x in body if x.strip()), default=0)
            blocks.append((i + 2, [x[indent:] for x in body]))
        i = j + 1
    return blocks


def _words(line: str):
    """[(shell word, its unquoted characters)] of one line."""
    out, word, bare, q, k = [], "", "", None, 0
    while k < len(line):
        c = line[k]
        if q:
            word += c
            if c == q:
                q = None
            elif c == "\\" and q == '"' and k + 1 < len(line):
                word += line[k + 1]
                k += 1
        elif c in "'\"":
            q, word = c, word + c
        elif c == "\\" and k + 1 < len(line):
            word += line[k:k + 2]
            k += 1
        elif c.isspace():
            if word:
                out.append((word, bare))
            word, bare = "", ""
        else:
            word, bare = word + c, bare + c
        k += 1
    if word:
        out.append((word, bare))
    return out


def lint_doc_blocks(out: Out, files=None):
    """The documents' shell blocks paste into zsh (macOS's default shell) as well as into bash."""
    files = files if files is not None else [p for p in repo_files() if p.suffix == ".md"]
    shells = [sh for sh in ("zsh", "bash") if shutil.which(sh)]
    for path in files:
        path = Path(path).resolve()
        r = rel(path) if path.is_relative_to(REPO) else path.name
        for first, lines in shell_blocks(path):
            for n, line in enumerate(lines, first):
                if line.lstrip().startswith("#"):
                    out.err(f"{r}:{n}", "comment line in a shell block: interactive zsh runs it as a command; "
                                        "explain the command in the text instead")
                    continue
                for w, bare in _words(line):
                    if bare.startswith("#"):
                        out.err(f"{r}:{n}", "trailing comment in a shell block: interactive zsh passes it to the "
                                            "command as arguments; move it to the text")
                        break
                    if re.search(r"<[\w .-]+>", bare):
                        out.err(f"{r}:{n}", f"placeholder {w!r}: the shell reads <...> as a redirection; "
                                            "write a real value")
                    elif re.search(r"[][*?]", bare) and w not in ("[", "]", "[[", "]]"):
                        if not any(any(root.glob(w.strip("'\""))) for root in (REPO, path.parent)):
                            out.err(f"{r}:{n}", f"unquoted {w!r}: zsh stops with 'no matches found'; quote it")
            for sh in shells:
                res = subprocess.run([sh, "-n"], input="\n".join(lines) + "\n", capture_output=True, text=True)
                if res.returncode:
                    out.err(f"{r}:{first}", f"{sh} -n: {(res.stderr.strip().splitlines() or ['syntax error'])[0]}")


def lint_hygiene(out: Out):
    for p in repo_files():
        r, size = rel(p), p.stat().st_size
        if size > 5e6:
            out.warn(r, f"{size / 1e6:.1f} MB: consider Git LFS or a release asset")
        if p.suffix.lower() not in TEXT_SUFFIXES or size > 3e6 and p.suffix != ".html":
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if p.suffix == ".sh":
            lines = (text.splitlines() + ["", ""])[:2]
            if not p.stat().st_mode & 0o111:
                out.err(r, "shell script without the exec bit: chmod +x (the docs run it as ./" + p.name + ")")
            if lines[0] != "#!/usr/bin/env bash":
                out.err(r, "first line must be #!/usr/bin/env bash")
            if lines[1] != SH_GUARD and not lines[1].startswith(SH_GUARD + " "):
                out.err(r, f"second line must be the run-under-bash guard: {SH_GUARD}")
        if r == "tools/lint_project.py":
            continue
        for code, rx in HYGIENE:
            for m in rx.finditer(text):
                hit = m.group(0)
                if code == "email" and (EMAIL_OK.search(hit) or re.match(r"^[\w.-]+@\d", hit)
                                        or re.search(r"@(media|import|keyframes|font-face)", hit)):
                    continue
                line = text.count("\n", 0, m.start()) + 1
                out.err(f"{r}:{line}", f"{code}: {hit[:60]!r}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", action="store_true")
    ap.add_argument("--automation", action="store_true")
    ap.add_argument("--hygiene", action="store_true")
    ap.add_argument("--docs", nargs="+", metavar="FILE.md", help="only the shell-block check, on these files")
    a = ap.parse_args()
    out = Out()
    every = not (a.config or a.automation or a.hygiene or a.docs)
    if a.docs:
        lint_doc_blocks(out, a.docs)
        a.config = a.automation = a.hygiene = False
    if a.config or every:
        lint_schemas(out)
        lint_skills(out, lint_agents(out))
        lint_rules(out)
        lint_workflows(out)
        lint_settings(out)
        lint_skills_link(out)
    if a.automation or every:
        lint_ci_settings(out)
        lint_actions(out)
    if a.hygiene or every:
        lint_hygiene(out)
        lint_doc_blocks(out)
    for e in out.errors:
        print(f"ERROR   {e}")
    for w in out.warnings:
        print(f"warning {w}")
    print(f"lint_project: {'FAIL' if out.errors else 'ok'} ({len(out.errors)} error(s), {len(out.warnings)} warning(s))")
    return 1 if out.errors else 0


if __name__ == "__main__":
    sys.exit(main())
