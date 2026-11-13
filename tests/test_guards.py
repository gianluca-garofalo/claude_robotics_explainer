"""The guards the sandbox and the hooks rely on: the news scout's write guard, the skills link, the sandbox lint."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
import testenv  # noqa: E402
testenv.activate()                  # fixture config and sources, before any tool is imported
sys.path.insert(0, str(REPO / "tools"))
import lint_project  # noqa: E402

GUARD = REPO / ".agents" / "skills" / "robotics-news-scout" / "write_guard.py"


class ScoutWriteGuard(unittest.TestCase):
    """The news-scout subagent writes only <run>/sources.json (a folder with run.json); anything else is blocked."""

    def guard(self, payload) -> int:
        stdin = payload if isinstance(payload, str) else json.dumps(payload)
        return subprocess.run([sys.executable, str(GUARD)], input=stdin, capture_output=True, text=True).returncode

    def write(self, path, cwd) -> int:
        return self.guard({"tool_name": "Write", "tool_input": {"file_path": str(path)}, "cwd": str(cwd)})

    def test_only_the_runs_sources_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run = root / "runs" / "2026-11-12-scouting"
            run.mkdir(parents=True)
            (run / "run.json").write_text("{}")
            (root / "elsewhere").mkdir()
            cases = {run / "sources.json": 0, run / "notes.md": 2, run / "scores.json": 2,
                     root / "elsewhere" / "sources.json": 2, root / ".claude" / "settings.json": 2}
            for path, code in cases.items():
                with self.subTest(path=str(path.relative_to(root))):
                    self.assertEqual(self.write(path, root), code)
            self.assertEqual(self.write("runs/2026-11-12-scouting/sources.json", root), 0)   # relative to cwd
            (run / "link.json").symlink_to(root / "elsewhere" / "sources.json")
            self.assertEqual(self.write(run / "link.json", root), 2)

    def test_fails_closed(self):
        self.assertEqual(self.guard("not json"), 2)
        self.assertEqual(self.guard({"tool_name": "Write", "tool_input": {}}), 2)

    def test_parses_on_old_pythons(self):
        import ast
        ast.parse(GUARD.read_text(), feature_version=(3, 7))      # macOS ships python3 3.9


class SkillsLink(unittest.TestCase):
    """.claude/skills must be the link to ../.agents/skills: a folder, a file or nothing in its place is reported."""

    def test_each_broken_form(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / ".agents" / "skills"
            target.mkdir(parents=True)
            (Path(tmp) / ".claude").mkdir()
            link = Path(tmp) / ".claude" / "skills"
            self.assertEqual(lint_project.skills_link_problem(link, target), "is missing")
            link.write_text("../.agents/skills")                 # a checkout without symbolic links
            self.assertIn("is a file", lint_project.skills_link_problem(link, target))
            link.unlink()
            link.mkdir()                                          # an archive tool copied the folder
            self.assertIn("is a folder", lint_project.skills_link_problem(link, target))
            link.rmdir()
            link.symlink_to("../.agents/skills")
            self.assertIsNone(lint_project.skills_link_problem(link, target))


class SandboxLint(unittest.TestCase):
    """The project's sandbox block: on, no unsandboxed retry, allow rules still decide, every Bash host explicit."""
    GOOD = {"enabled": True, "allowUnsandboxedCommands": False, "autoAllowBashIfSandboxed": False,
            "excludedCommands": ["python3 tools/example.py write *", "node tools/example.js *", "git fetch",
                                 "git fetch origin"],
            "network": {"allowedDomains": ["arxiv.org"], "deniedDomains": ["code.example.org"]}}
    ALLOW = ["WebFetch(domain:arxiv.org)", "WebFetch(domain:code.example.org)"]

    def errors(self, sb, allow=None):
        out = lint_project.Out()
        lint_project.lint_sandbox("settings.json", sb, {"allow": self.ALLOW if allow is None else allow}, out)
        return out.errors

    def test_good_block_passes(self):
        self.assertEqual(self.errors(self.GOOD), [])

    def test_each_weakening_is_reported(self):
        bad = {
            "off": dict(self.GOOD, enabled=False),
            "retry allowed": dict(self.GOOD, allowUnsandboxedCommands=True),
            "auto-allow": dict(self.GOOD, autoAllowBashIfSandboxed=True),
            "interpreter excluded": dict(self.GOOD, excludedCommands=["python3 *"]),
            "shell excluded": dict(self.GOOD, excludedCommands=["bash -c *"]),
            # a fetch leaves the sandbox only for the configured remote: no URL, option (--upload-pack) or wildcard
            "fetch anything": dict(self.GOOD, excludedCommands=["git fetch *"]),
            "fetch a URL": dict(self.GOOD, excludedCommands=["git fetch https://code.example.org/x.git"]),
            "fetch an option": dict(self.GOOD, excludedCommands=["git fetch --upload-pack=x origin"]),
            "git excluded": dict(self.GOOD, excludedCommands=["git *"]),
            "push excluded": dict(self.GOOD, excludedCommands=["git push origin"]),
        }
        for name, sb in bad.items():
            with self.subTest(case=name):
                self.assertTrue(self.errors(sb))
        self.assertTrue(self.errors(self.GOOD, self.ALLOW + ["WebFetch(domain:unlisted.example.org)"]))


if __name__ == "__main__":
    unittest.main()
