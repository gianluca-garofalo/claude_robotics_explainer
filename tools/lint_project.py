#!/usr/bin/env python3
"""Lint the Claude Code configuration against the documented formats, and the repository for publish hygiene.

Usage:
  python3 tools/lint_project.py            # config + automation + hygiene
  python3 tools/lint_project.py --config   # only .claude/ (skills, agents, rules, workflows, settings.json)
  python3 tools/lint_project.py --automation   # only ci/*.json and .github/ (the publishing boundary)
  python3 tools/lint_project.py --hygiene  # only the repository scan

Config: frontmatter keys must be ones the Claude Code docs list (unknown keys are silently ignored by Claude Code,
so a typo would go unnoticed), required keys present, names valid, description within the 1,536-character listing
cap, SKILL.md under 500 lines, linked files present, hook scripts present, workflow meta a plain literal, settings
strict JSON with known hook events. Project policy: no `model` field anywhere (defaults apply), side-effect skills
set `disable-model-invocation: true`.
Automation: the CI settings Claude runs with (ci/*.json) deny publishing, approval and edits to tools, config and
workflows, use only relative path rules (they are installed as user settings), and keep the sandbox strict; in the
GitHub workflows, jobs that run Claude hold no publishing secret, no write permission and no environment, carry turn
and budget caps, scrub credentials from subprocesses and do not persist the checkout token; jobs that use YouTube or
LinkedIn secrets run in an environment; steps that execute code written during the run (code checks, renders) hold
no secret; no `${{ }}` expression is pasted into a shell script; scheduled workflows that run Claude have the
PIPELINE_ENABLED kill switch.
Hygiene: no absolute local paths, e-mail addresses, secrets or model identifiers in tracked text files; files over
5 MB reported; shell scripts executable, with the bash shebang and the run-under-bash guard; shell code blocks in
the Markdown documents safe to paste into zsh as well as bash (no comment lines or trailing comments, which
interactive zsh runs as words; no <placeholders>, which are redirections; no unquoted [ ] * ? that match no file,
which zsh refuses; zsh -n and bash -n clean where the shells are installed). Requires PyYAML (in requirements.txt).
Exit status 1 on errors.

  python3 tools/lint_project.py --docs FILE.md ...   # only the shell-block check, on any Markdown files
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    print("error: PyYAML is required (pip install pyyaml, or use .venv/bin/python)", file=sys.stderr)
    sys.exit(3)

REPO = Path(__file__).resolve().parent.parent
CLAUDE = REPO / ".claude"

# Field lists from code.claude.com/docs/en/skills (frontmatter reference) and /sub-agents (frontmatter reference).
SKILL_KEYS = {"name", "description", "when_to_use", "argument-hint", "arguments", "disable-model-invocation",
              "user-invocable", "allowed-tools", "disallowed-tools", "model", "effort", "context", "agent",
              "background", "hooks", "paths", "shell", "metadata", "license", "compatibility"}
AGENT_KEYS = {"name", "description", "tools", "disallowedTools", "model", "permissionMode", "maxTurns",
              "autoCompactWindow", "skills", "mcpServers", "hooks", "memory", "background", "effort", "isolation",
              "color", "initialPrompt", "omitClaudeMd", "experimental"}
RULE_KEYS = {"paths"}
AGENT_COLORS = {"red", "blue", "green", "yellow", "purple", "orange", "pink", "cyan"}
TOOLS = {"Read", "Grep", "Glob", "Bash", "Edit", "Write", "NotebookEdit", "WebFetch", "WebSearch", "TodoWrite",
         "Skill", "Agent", "LSP", "PowerShell", "Monitor", "TaskStop", "SendMessage", "ToolSearch", "EnterWorktree",
         "ExitWorktree", "Artifact"}
HOOK_EVENTS = {"SessionStart", "Setup", "InstructionsLoaded", "UserPromptSubmit", "UserPromptExpansion",
               "MessageDisplay", "PreToolUse", "PermissionRequest", "PostToolUse", "PostToolUseFailure",
               "PostToolBatch", "PermissionDenied", "Notification", "SubagentStart", "SubagentStop", "TaskCreated",
               "TaskCompleted", "Stop", "StopFailure", "TeammateIdle", "ConfigChange", "CwdChanged",
               "DirectoryAdded", "FileChanged", "WorktreeCreate", "WorktreeRemove", "PreCompact", "PostCompact",
               "SessionEnd", "Elicitation", "ElicitationResult", "PreModelSwitch", "PostModelSwitch"}
HANDLER_KEYS = {"type", "command", "args", "timeout", "if", "statusMessage", "async", "asyncRewake", "shell",
                "onFailure", "once", "url", "headers", "allowedEnvVars", "prompt", "model", "server", "tool", "input"}
HANDLER_TYPES = {"command", "http", "mcp_tool", "prompt", "agent"}
SETTINGS_KEYS_USED = {"$schema", "permissions", "hooks", "env"}
SIDE_EFFECT_SKILLS = {"produce-explainer", "approve-topic", "produce-episode", "produce-from-source", "plan-series"}

TEXT_SUFFIXES = {".md", ".py", ".js", ".json", ".toml", ".txt", ".sh", ".html", ".css", ".yml", ".yaml", ".cfg", ""}
SKIP_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__", "media", "runs"}
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


def rel(p: Path) -> str:
    return p.relative_to(REPO).as_posix()


def frontmatter(path: Path, out: Out):
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        out.err(rel(path), "frontmatter must start on the first line with ---")
        return None, text
    end = text.find("\n---", 4)
    if end == -1:
        out.err(rel(path), "frontmatter is not closed with ---")
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


def check_hooks(where: str, hooks, out: Out):
    if not isinstance(hooks, dict):
        out.err(where, "hooks must map event names to matcher groups")
        return
    for event, groups in hooks.items():
        if event not in HOOK_EVENTS:
            out.err(where, f"unknown hook event {event!r}")
        if not isinstance(groups, list):
            out.err(where, f"hooks.{event} must be a list of matcher groups")
            continue
        for g in groups:
            if not isinstance(g, dict) or not isinstance(g.get("hooks"), list):
                out.err(where, f"hooks.{event}: each group needs a 'hooks' list")
                continue
            for h in g["hooks"]:
                if not isinstance(h, dict) or h.get("type") not in HANDLER_TYPES:
                    out.err(where, f"hooks.{event}: handler type must be one of {sorted(HANDLER_TYPES)}")
                    continue
                unknown = set(h) - HANDLER_KEYS
                if unknown:
                    out.err(where, f"hooks.{event}: unknown handler field(s) {sorted(unknown)}")
                if h["type"] == "command":
                    for token in [h.get("command", "")] + list(h.get("args", [])):
                        m = re.search(r"\$\{CLAUDE_PROJECT_DIR\}/([^\s\"']+)", str(token))
                        if m and not (REPO / m.group(1)).exists():
                            out.err(where, f"hook script {m.group(1)} does not exist")


def lint_skills(out: Out, names: set):
    for d in sorted((CLAUDE / "skills").iterdir()):
        if not d.is_dir():
            continue
        p = d / "SKILL.md"
        if not p.exists():
            out.err(rel(d), "skill folder without SKILL.md")
            continue
        fm, body = frontmatter(p, out)
        if fm is None:
            continue
        where = rel(p)
        for k in sorted(set(fm) - SKILL_KEYS):
            out.err(where, f"unknown frontmatter field {k!r} (Claude Code would ignore it silently)")
        if "model" in fm:
            out.err(where, "project policy: no model field (let Claude Code defaults apply)")
        desc = str(fm.get("description", ""))
        if not desc:
            out.err(where, "description is required here (it is how Claude decides when to use the skill)")
        if len(desc) + len(str(fm.get("when_to_use", ""))) > 1536:
            out.err(where, "description + when_to_use exceed 1,536 characters (truncated in the skill listing)")
        if "<" in desc or ">" in desc:
            out.warn(where, "angle brackets in description are shown as &lt; &gt;")
        name = fm.get("name", d.name)
        if not re.match(r"^[a-z0-9]+(-[a-z0-9]+)*$", str(name)):
            out.err(where, f"name {name!r} should be lowercase words joined by hyphens")
        if fm.get("name") and fm["name"] != d.name:
            out.warn(where, f"name {fm['name']!r} differs from the folder name {d.name!r}")
        if d.name.lower() in ("synced",) or d.name.startswith("anthropic-skills"):
            out.err(where, "reserved skill folder name")
        if d.name in SIDE_EFFECT_SKILLS and fm.get("disable-model-invocation") is not True:
            out.err(where, "side-effect or human-only skill must set disable-model-invocation: true")
        if fm.get("context") == "fork" and fm.get("agent") and fm["agent"] not in names | {"Explore", "Plan", "general-purpose"}:
            out.err(where, f"agent {fm['agent']!r} is not defined")
        if "hooks" in fm:
            check_hooks(where, fm["hooks"], out)
        lines = p.read_text(encoding="utf-8").count("\n")
        if lines > 500:
            out.err(where, f"{lines} lines; keep SKILL.md under 500 and move detail to supporting files")
        for link in re.findall(r"\]\(([^)#\s]+)\)", body):
            if not re.match(r"^[a-z]+://", link) and not (d / link).exists():
                out.err(where, f"linked file {link} does not exist")
        for path in re.findall(r"`((?:tools|templates|config|sources|series|\.claude)/[\w./-]+)`", body):
            if "<" not in path and not (REPO / path).exists():
                out.err(where, f"mentions {path}, which does not exist")


def lint_agents(out: Out) -> set:
    names = set()
    for p in sorted((CLAUDE / "agents").glob("*.md")):
        fm, body = frontmatter(p, out)
        if fm is None:
            continue
        where = rel(p)
        for k in sorted(set(fm) - AGENT_KEYS):
            out.err(where, f"unknown frontmatter field {k!r} (Claude Code would ignore it silently)")
        for k in ("name", "description"):
            if not fm.get(k):
                out.err(where, f"{k} is required (without it Claude Code skips the file)")
        name = str(fm.get("name", ""))
        if ":" in name or name.startswith("-") or len(name) > 256:
            out.err(where, "name must not contain ':' or start with '-' and must be at most 256 characters")
        if name in names:
            out.err(where, f"duplicate agent name {name}")
        names.add(name)
        if "model" in fm:
            out.err(where, "project policy: no model field (let Claude Code defaults apply)")
        if fm.get("color") and fm["color"] not in AGENT_COLORS:
            out.err(where, f"color must be one of {sorted(AGENT_COLORS)}")
        tools = fm.get("tools")
        if tools is not None:
            items = tools if isinstance(tools, list) else [t.strip() for t in str(tools).split(",")]
            for t in items:
                base = re.sub(r"\(.*\)$", "", t)
                if base not in TOOLS and not base.startswith("mcp__"):
                    out.err(where, f"unknown tool {t!r}")
        if "maxTurns" in fm and not (isinstance(fm["maxTurns"], int) and fm["maxTurns"] > 0):
            out.err(where, "maxTurns must be a positive integer")
        if "hooks" in fm:
            check_hooks(where, fm["hooks"], out)
        if not body.strip():
            out.err(where, "empty system prompt")
    return names


def lint_rules(out: Out):
    for p in sorted((CLAUDE / "rules").rglob("*.md")):
        fm, _ = frontmatter(p, out)
        if fm is None:
            continue
        for k in sorted(set(fm) - RULE_KEYS):
            out.err(rel(p), f"unknown rule field {k!r} (only 'paths' is read)")
        paths = fm.get("paths")
        if paths is not None and not (isinstance(paths, list) and all(isinstance(x, str) for x in paths)):
            out.err(rel(p), "paths must be a list of glob strings")


def lint_workflows(out: Out):
    for p in sorted((CLAUDE / "workflows").glob("*.js")):
        src = p.read_text(encoding="utf-8")
        where = rel(p)
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
            for t in re.findall(r"phase\s*:\s*'([^']+)'|phase\('([^']+)'\)", src):
                t = t[0] or t[1]
                if titles and t not in titles:
                    out.warn(where, f"phase {t!r} is not listed in meta.phases")
        for bad in (r"Date\.now\(", r"Math\.random\(", r"new Date\(\)", r"\bimport\("):
            if re.search(bad, src):
                out.err(where, f"{bad} is not allowed in workflow scripts (breaks resume)")
        if re.search(r"\bmodel\s*:", src):
            out.err(where, "project policy: no model overrides in workflow agents")
        node = shutil.which("node")
        if node:
            with tempfile.TemporaryDirectory() as td:
                body = "export {};\n(async () => {\n" + src.replace("export const meta", "const meta", 1) + "\n})\n"
                f = Path(td) / "wf.mjs"
                f.write_text(body, encoding="utf-8")
                r = subprocess.run([node, "--check", str(f)], capture_output=True, text=True)
                if r.returncode != 0:
                    out.err(where, "JavaScript syntax error: " + (r.stderr.strip().splitlines() or ["?"])[-1])
        else:
            out.warn(where, "node not found: workflow syntax not checked")


def lint_settings(out: Out):
    p = CLAUDE / "settings.json"
    where = rel(p)
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        out.err(where, f"not strict JSON: {exc}")
        return
    for k in set(data) - SETTINGS_KEYS_USED:
        out.warn(where, f"top-level key {k!r} is not one this project uses; check it against the settings reference")
    perms = data.get("permissions", {})
    for kind in ("allow", "ask", "deny"):
        for rule in perms.get(kind, []):
            if not re.match(r"^(\*|[A-Za-z][A-Za-z0-9_*]*)(\(.+\))?$", rule):
                out.err(where, f"permissions.{kind}: malformed rule {rule!r}")
                continue
            tool = rule.split("(")[0]
            if tool not in TOOLS and not tool.startswith("mcp__") and tool != "*":
                out.err(where, f"permissions.{kind}: unknown tool in {rule!r}")
            if re.match(r"^(Write|NotebookEdit|Glob)\(", rule):
                out.err(where, f"{rule!r} never matches: use Edit(...) or Read(...) path rules")
    check_hooks(where, data.get("hooks", {}), out)
    deny = " ".join(perms.get("deny", []))
    for must in ("git push", "gh release", "approval.json"):
        if must not in deny:
            out.err(where, f"project policy: deny rules must cover {must!r}")


CI_KEYS = {"$schema", "permissions", "env", "sandbox"}
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
        for k in sorted(set(data) - CI_KEYS):
            out.err(where, f"unexpected top-level key {k!r}")
        perms = data.get("permissions", {})
        if perms.get("defaultMode") != "dontAsk":
            out.err(where, "permissions.defaultMode must be dontAsk (nobody answers prompts in CI)")
        for kind in ("allow", "ask", "deny"):
            for rule in perms.get(kind, []):
                tool = rule.split("(")[0]
                if tool not in TOOLS and not tool.startswith("mcp__"):
                    out.err(where, f"permissions.{kind}: unknown tool in {rule!r}")
                if re.match(r"^(Edit|Read)\(/[^/]", rule):
                    out.err(where, f"{rule!r}: these settings are installed as user settings, where /path means "
                                   "~/.claude/path; use a relative pattern")
        deny = " ".join(perms.get("deny", []))
        for must in CI_MUST_DENY:
            if must not in deny:
                out.err(where, f"deny rules must cover {must!r}")
        if any(r.startswith("Bash(gh") or r.startswith("Bash(git push") or r.startswith("Bash(curl")
               for r in perms.get("allow", [])):
            out.err(where, "allow rules must not open gh, git push or curl")
        sb = data.get("sandbox")
        if sb is not None:
            if sb.get("enabled") is not True or sb.get("allowUnsandboxedCommands") is not False:
                out.err(where, "sandbox: enabled must be true and allowUnsandboxedCommands false")
            if sb.get("network", {}).get("allowedDomains"):
                out.warn(where, "sandbox: Bash may reach " + ", ".join(sb["network"]["allowedDomains"]))
            denied = {v.get("name") for v in sb.get("credentials", {}).get("envVars", []) if v.get("mode") == "deny"}
            if "GITHUB_TOKEN" not in denied:
                out.err(where, "sandbox.credentials must deny GITHUB_TOKEN")


def _strings(node):
    if isinstance(node, dict):
        for v in node.values():
            yield from _strings(v)
    elif isinstance(node, list):
        for v in node:
            yield from _strings(v)
    elif isinstance(node, str):
        yield node


def _step_lists(wf: dict):
    for job in (wf.get("jobs") or {}).values():
        if isinstance(job, dict):
            yield job.get("steps") or []
    runs = wf.get("runs")
    if isinstance(runs, dict):
        yield runs.get("steps") or []


def _run_blocks(wf: dict):
    for steps in _step_lists(wf):
        for st in steps:
            if isinstance(st, dict) and isinstance(st.get("run"), str):
                yield st["run"]


def lint_actions(out: Out):
    gh = REPO / ".github"
    files = sorted(gh.glob("workflows/*.yml")) + sorted(gh.glob("actions/*/action.yml"))
    for p in files:
        where = rel(p)
        text = p.read_text(encoding="utf-8")
        try:
            wf = yaml.safe_load(text)
        except yaml.YAMLError as exc:
            out.err(where, f"YAML does not parse: {exc}")
            continue
        for block in _run_blocks(wf):
            if "${{" in block:
                out.err(where, "a run script contains ${{ ... }}: pass the value through env instead "
                               "(expression injection)")
        if p.name == "action.yml":
            continue
        on = wf.get("on", wf.get(True, {}))
        if "permissions" not in wf:
            out.err(where, "top-level permissions missing: start from permissions: {} and grant per job")
        if isinstance(on, dict) and "schedule" in on and CLAUDE_ACTION in text and "PIPELINE_ENABLED" not in text:
            out.err(where, "scheduled workflow that runs Claude without the PIPELINE_ENABLED kill switch")
        for name, job in (wf.get("jobs") or {}).items():
            jw = f"{where} jobs.{name}"
            strings = list(_strings(job))
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
                args = str(w.get("claude_args", ""))
                for flag in ("--max-turns", "--max-budget-usd", "--permission-mode dontAsk"):
                    if flag not in args:
                        out.err(jw, f"step {st.get('name', '?')!r}: claude_args needs {flag}")
                if re.search(r"--model\b|--dangerously|bypassPermissions", args):
                    out.err(jw, f"step {st.get('name', '?')!r}: no model override or permission bypass")
                if not w.get("settings"):
                    out.err(jw, f"step {st.get('name', '?')!r}: pass the CI settings (ci/*.json)")


SH_GUARD = '[ -n "${BASH_VERSION:-}" ] || exec bash "$0" "$@"'    # sh or zsh hand the script over to bash
SHELL_LANGS = {"bash", "sh", "shell", "zsh", "console"}


def shell_blocks(path: Path):
    """The fenced shell code blocks of a Markdown file: [(line number of the first command, [lines])]."""
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
    """Shell words of one line with their unquoted characters: [(word, unquoted part)]."""
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
    """Shell code blocks in the documents must paste into zsh (macOS's default shell) as well as into bash."""
    if files is None:
        files = [p for p in sorted(REPO.rglob("*.md"))
                 if not any(part in SKIP_DIRS for part in p.relative_to(REPO).parts)]
    shells = [sh for sh in ("zsh", "bash") if shutil.which(sh)]
    for path in files:
        path = Path(path).resolve()
        r = rel(path) if path.is_relative_to(REPO) else path.name
        for first, lines in shell_blocks(path):
            for n, line in enumerate(lines, first):
                ws = _words(line)
                if line.lstrip().startswith("#"):
                    out.err(f"{r}:{n}", "comment line in a shell block: interactive zsh runs it as a command; "
                                        "explain the command in the text instead")
                    continue
                for w, bare in ws:
                    if bare.startswith("#"):
                        out.err(f"{r}:{n}", "trailing comment in a shell block: interactive zsh passes it to the "
                                            "command as arguments; move it to the text")
                        break
                    if re.search(r"<[\w .-]+>", bare):
                        out.err(f"{r}:{n}", f"placeholder {w!r}: the shell reads <...> as a redirection; "
                                            "write a real value")
                    elif re.search(r"[][*?]", bare) and w not in ("[", "]", "[[", "]]"):
                        roots = {REPO, path.parent}                 # the commands run in the project folder
                        if not any(any(root.glob(w.strip("'\""))) for root in roots):
                            out.err(f"{r}:{n}", f"unquoted {w!r}: zsh stops with 'no matches found'; quote it")
            for sh in shells:
                res = subprocess.run([sh, "-n"], input="\n".join(lines) + "\n", capture_output=True, text=True)
                if res.returncode:
                    out.err(f"{r}:{first}", f"{sh} -n: {(res.stderr.strip().splitlines() or ['syntax error'])[0]}")


def lint_hygiene(out: Out):
    for p in sorted(REPO.rglob("*")):
        if not p.is_file() or any(part in SKIP_DIRS for part in p.relative_to(REPO).parts):
            continue
        r = rel(p)
        size = p.stat().st_size
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
    if a.docs:
        lint_doc_blocks(out, a.docs)
        a.config = a.automation = a.hygiene = False
    both = not (a.config or a.hygiene or a.automation or a.docs)
    if a.config or both:
        names = lint_agents(out)
        lint_skills(out, names)
        lint_rules(out)
        lint_workflows(out)
        lint_settings(out)
    if a.automation or both:
        lint_ci_settings(out)
        lint_actions(out)
    if a.hygiene or both:
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
