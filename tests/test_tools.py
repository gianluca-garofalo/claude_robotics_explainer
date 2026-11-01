"""Unit tests for the deterministic tools (standard library unittest; run: python3 -m unittest discover -s tests)."""
import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
sys.path.insert(0, str(REPO / "tools" / "hooks"))

import block_publish  # noqa: E402
import build_explainer  # noqa: E402
import lint_html  # noqa: E402
import rank_topics  # noqa: E402
import validate  # noqa: E402

FIX = REPO / "tests" / "fixtures" / "run"


class BlockPublish(unittest.TestCase):
    BLOCK = ["git push origin main", "git -C . push", "FOO=1 git push", "sh -c 'git push origin'",
             "bash -c \"cd x && git -c a=b push\"", "gh release create v1", "gh pr create --fill",
             "gh api -X POST repos/x/y/issues", "gh api repos/a/b -f title=x", "npm publish",
             "python3 -m twine upload dist/x", "youtube-upload --title x a.mp4", "python3 upload_video.py --file a.mp4",
             "curl -F file=@a.mp4 https://example.org", "curl -X POST https://example.org", "curl -d '{}' https://x",
             "curl -T a.mp4 https://x", "wget --post-file=a https://x", "scp a.mp4 host:/srv/",
             "rsync -av runs/ host:/srv/", "docker push img", "aws s3 cp a s3://b/", "git status && git push",
             "timeout 30 git push", "ffmpeg -re -i a.mp4 -f flv rtmp://live.example.org/app/key",
             "curl https://www.googleapis.com/upload/youtube/v3/videos",
             "gh issue edit 12 --add-label approve-publish", "gh issue -R me/repo edit 12 --add-label approve-publish",
             "gh api -X POST repos/me/repo/actions/runs/1/pending_deployments", "gh variable set PUBLISH_ENABLED",
             "gh run rerun 123", "gh -R me/repo workflow run pipeline.yml"]
    ALLOW = ["gh pr view 12", "gh api repos/x/y", "curl -fsSL https://arxiv.org/abs/1234", "wget https://arxiv.org/pdf/1",
             "ffmpeg -i a.mp4 b.mp4", "grep -n 'git push' CLAUDE.md", "echo git push", "rsync -av runs/ backup/",
             "git log --grep push", "git commit -m 'push it'", "node tools/check_html.js x.html", "ls -la",
             "gh run view 123", "gh issue view 12 -R me/repo"]

    def test_blocked(self):
        for c in self.BLOCK:
            with self.subTest(c=c):
                self.assertIsNotNone(block_publish.check(c))

    def test_allowed(self):
        for c in self.ALLOW:
            with self.subTest(c=c):
                self.assertIsNone(block_publish.check(c))


class Recency(unittest.TestCase):
    def test_bands(self):
        crit = json.loads((REPO / "config" / "rubric.json").read_text())["criteria"]["recency"]
        for days, want in [(0, 5), (7, 5), (8, 4), (14, 4), (30, 3), (90, 2), (365, 1), (366, 0), (None, None)]:
            self.assertEqual(rank_topics.recency_score(days, crit), want, days)


class SplitMath(unittest.TestCase):
    def test_balanced(self):
        segs, unclosed = lint_html.split_math("a $x^2$ and $$\\frac{a}{b}$$ end")
        self.assertIsNone(unclosed)
        self.assertEqual([k for k, _ in segs], ["text", "inline", "text", "display", "text"])

    def test_unclosed_dollar(self):
        _, unclosed = lint_html.split_math("costs $5 per unit")
        self.assertEqual(unclosed, "$5 per unit")

    def test_brace_protects_delimiter(self):
        segs, unclosed = lint_html.split_math("$\\text{a$b}$")
        self.assertIsNone(unclosed)
        self.assertEqual(segs[0][0], "inline")


class Validators(unittest.TestCase):
    def setUp(self):
        self.src = json.loads((FIX / "sources.json").read_text())

    def check(self, data):
        rep = validate.Report("t")
        validate.validate_sources(data, rep, {"max_candidates": 8, "min_candidates": 1})
        return rep

    def test_fixture_valid(self):
        self.assertEqual(self.check(self.src).errors, [])

    def test_news_cannot_be_primary(self):
        d = copy.deepcopy(self.src)
        d["candidates"][0]["sources"][1]["primary"] = True
        self.assertTrue(any("cannot be a primary source" in e for e in self.check(d).errors))

    def test_verified_needs_primary_read(self):
        d = copy.deepcopy(self.src)
        d["candidates"][0]["sources"][0]["read"] = "snippet"
        self.assertTrue(any("is 'verified' but" in e for e in self.check(d).errors))

    def test_generated_records_in_review_are_not_reports(self):
        """review/gates.json (tools/gate.py) and the other generated records are skipped by the run validator."""
        for name in ("gates.json", "summary.json", "resolutions.json", "frames.json"):
            self.assertIsNone(validate.kind_for(Path("runs/x/review") / name), name)
        self.assertIsNone(validate.kind_for(Path("runs/x/review/final_cut/frames.json")))
        self.assertEqual(validate.kind_for(Path("runs/x/review/final_cut/final-cut-reviewer.json")), "review")

    def test_doi_needs_provenance(self):
        refs = json.loads((FIX / "references.json").read_text())
        del refs["references"][0]["verification"]["doi_seen_in"]
        rep = validate.Report("t")
        validate.validate_references(refs, rep)
        self.assertTrue(any("never invent or infer a DOI" in e for e in rep.errors))


class Citations(unittest.TestCase):
    def ref(self, authors, typ="article"):
        return {"key": "x2020", "authors": authors, "year": 2020, "type": typ}

    def test_author_year(self):
        self.assertIn(">Keerthi &amp; Gilbert, 1988<", build_explainer.cite(
            {"key": "k", "authors": ["S.S. Keerthi", "E.G. Gilbert"], "year": 1988, "type": "article"}, False))
        self.assertIn(">Mayne et al. (2000)<", build_explainer.cite(
            {"key": "m", "authors": ["D.Q. Mayne", "J.B. Rawlings", "C.V. Rao"], "year": 2000, "type": "article"}, True))
        self.assertIn(">van der Schaft, 2020<", build_explainer.cite(self.ref(["A.J. van der Schaft"]), False))
        self.assertIn(">Example Robotics Lab, 2020<", build_explainer.cite(self.ref(["Example Robotics Lab"], "web"), False))


class ShellScripts(unittest.TestCase):
    """Every shell script runs as ./script from any shell: exec bit, bash shebang, and the run-under-bash guard."""
    GUARD = '[ -n "${BASH_VERSION:-}" ] || exec bash "$0" "$@"'

    def scripts(self):
        skip = {"node_modules", ".venv", "runs", "__pycache__"}
        return [p for p in REPO.rglob("*.sh") if not any(x in skip for x in p.relative_to(REPO).parts)]

    def test_exec_bit_shebang_and_guard(self):
        found = self.scripts()
        self.assertGreaterEqual(len(found), 4)
        for p in found:
            with self.subTest(script=str(p.relative_to(REPO))):
                lines = p.read_text().splitlines()
                self.assertTrue(p.stat().st_mode & 0o111, "exec bit")
                self.assertEqual(lines[0], "#!/usr/bin/env bash")
                self.assertTrue(lines[1].startswith(self.GUARD))

    def test_same_behaviour_from_every_shell(self):
        import shutil as sh
        for script, arg in (("setup.sh", "--help"), ("tools/render_video.sh", "--help")):
            outs = {}
            for shell in ("./", "sh", "zsh", "bash"):
                if shell != "./" and not sh.which(shell):
                    continue
                cmd = [f"./{script}", arg] if shell == "./" else [shell, script, arg]
                r = subprocess.run(cmd, cwd=REPO, capture_output=True, text=True)
                outs[shell] = (r.returncode, r.stdout)
            with self.subTest(script=script):
                self.assertEqual(len(set(outs.values())), 1, {k: v[0] for k, v in outs.items()})
                self.assertEqual(outs["./"][0], 0)


class SetupOnMacOS(unittest.TestCase):
    """setup.sh --check on a simulated Darwin (uname answers Darwin, cairo headers missing) names Homebrew."""

    def test_check_prints_the_homebrew_command(self):
        import os
        with tempfile.TemporaryDirectory() as shim:
            for name, body in (("uname", "echo Darwin"), ("pkg-config", "exit 1")):
                f = Path(shim) / name
                f.write_text(f"#!/bin/sh\n{body}\n")
                f.chmod(0o755)
            env = dict(os.environ, PATH=shim + os.pathsep + os.environ.get("PATH", ""))
            r = subprocess.run(["./setup.sh", "--check"], cwd=REPO, env=env, capture_output=True, text=True)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("cairo + pango headers              MISSING", r.stdout)
        self.assertIn("brew install python@3.13 pkg-config cairo pango fontconfig ffmpeg sox node", r.stdout)
        self.assertIn("brew install --cask mactex-no-gui font-dejavu", r.stdout)
        self.assertIn("Then: ./setup.sh", r.stdout)


class SetupAsRoot(unittest.TestCase):
    """setup.sh --with-system-deps in a cloud environment's setup script: root, no terminal. apt runs without sudo
    and without questions (DEBIAN_FRONTEND=noninteractive, -y); a Node.js already there is not replaced. As a normal
    user it goes through sudo. --system-deps-only stops after the packages (shims stand in for apt-get and sudo)."""

    def run_setup(self, uid: str, node: bool):
        import os
        with tempfile.TemporaryDirectory() as shim:
            log = Path(shim) / "calls.log"
            for name, body in (("id", f'[ "$1" = -u ] && echo {uid} || /usr/bin/id "$@"'),
                               ("apt-get", f'echo "DEBIAN_FRONTEND=${{DEBIAN_FRONTEND:-}} $*" >> "{log}"'),
                               ("sudo", f'echo "sudo $*" >> "{log}"; exec "$@"'),
                               ("node", "exit 0" if node else "exit 1"), ("npm", "exit 0" if node else "exit 1"),
                               ("uname", "echo Linux")):
                f = Path(shim) / name
                f.write_text(f"#!/bin/sh\n{body}\n")
                f.chmod(0o755)
            env = dict(os.environ, PATH=shim + os.pathsep + os.environ.get("PATH", ""))
            r = subprocess.run(["./setup.sh", "--system-deps-only"], cwd=REPO, env=env, capture_output=True,
                               text=True, stdin=subprocess.DEVNULL, timeout=60)
            return r, (log.read_text() if log.exists() else "")

    def test_root_needs_no_sudo_and_no_answers(self):
        r, calls = self.run_setup("0", node=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("System packages installed.", r.stdout)
        self.assertNotIn("sudo", calls)
        self.assertIn("DEBIAN_FRONTEND=noninteractive update", calls)
        self.assertIn("DEBIAN_FRONTEND=noninteractive install -y -o Dpkg::Options::=--force-confdef "
                      "-o Dpkg::Options::=--force-confold build-essential", calls)   # no conffile prompt either
        self.assertNotIn(" nodejs npm ", calls)                         # the image's own Node.js stays

    def test_a_user_goes_through_sudo(self):
        r, calls = self.run_setup("1000", node=False)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("sudo env DEBIAN_FRONTEND=noninteractive apt-get install -y", calls)
        self.assertIn(" nodejs npm ", calls)


class CodeChecksOnASource(unittest.TestCase):
    """tools/run_code_checks.py on sources/<name> runs in a temporary copy: the scripts' side files, overwritten
    figures and caches never reach the source, which stays byte-identical except code/logs/ (or entirely, with
    --logs DIR); a run folder still runs in place."""
    SCRIPT = ("import pathlib\n"
              "pathlib.Path('fig.svg').write_text('<svg>regenerated</svg>')\n"
              "pathlib.Path('side_output.json').write_text('{}')\n"
              "pathlib.Path('cache').mkdir(exist_ok=True)\n"
              "(pathlib.Path('cache') / 'x.npz').write_bytes(b'0')\n"
              "print('RESULT 42')\n")

    def make(self, root: Path, kind: str) -> Path:
        d = root / kind / "demo"
        (d / "code").mkdir(parents=True)
        (d / "data").mkdir()
        (d / "data" / "a.csv").write_text("x\n1\n")
        (d / "explainer.html").write_text("<!doctype html><title>demo</title>\n")
        (d / "code" / "make_fig.py").write_text(self.SCRIPT)
        (d / "code" / "fig.svg").write_text("<svg>as published</svg>")
        (d / "code" / "README.md").write_text("make_fig.py prints the result and draws fig.svg\n")
        (d / "code" / "checks.toml").write_text('[[check]]\nscript = "make_fig.py"\nexpect = ["RESULT 42"]\n'
                                                'produces = ["fig.svg", "side_output.json"]\n')
        return d

    @staticmethod
    def snapshot(d: Path) -> dict:
        return {p.relative_to(d).as_posix(): p.read_bytes() for p in sorted(d.rglob("*")) if p.is_file()}

    def check(self, d: Path, *extra) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(REPO / "tools" / "run_code_checks.py"), str(d), *extra],
                              capture_output=True, text=True)

    def test_source_stays_identical_except_logs(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = self.make(Path(tmp), "sources")
            before = self.snapshot(d)
            r = self.check(d)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("temporary copy", r.stdout)
            after = self.snapshot(d)
            changed = sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))
            self.assertEqual([k for k in changed if not k.startswith("code/logs/")], [])
            self.assertIn("code/logs/summary.json", changed)
            summary = json.loads((d / "code" / "logs" / "summary.json").read_text())
            self.assertEqual(summary["ran_in"], "temporary copy")
            self.assertTrue(summary["checks"][0]["ok"])
            self.assertNotIn("code-checks-", summary["checks"][0]["log"])   # names the source's log, not the copy

    def test_logs_elsewhere_keep_the_source_byte_identical(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = self.make(Path(tmp), "sources")
            before = self.snapshot(d)
            r = self.check(d, "--logs", str(Path(tmp) / "scratch-logs"))
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertEqual(self.snapshot(d), before)
            self.assertTrue((Path(tmp) / "scratch-logs" / "summary.json").exists())

    def test_a_failing_check_in_the_copy_is_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = self.make(Path(tmp), "sources")
            (d / "code" / "checks.toml").write_text('[[check]]\nscript = "make_fig.py"\nproduces = ["missing.svg"]\n')
            r = self.check(d)
            self.assertEqual(r.returncode, 1)
            self.assertIn("missing files ['missing.svg']", r.stdout)

    def test_a_run_folder_runs_in_place(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = self.make(Path(tmp), "runs")
            r = self.check(d)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertEqual((d / "code" / "fig.svg").read_text(), "<svg>regenerated</svg>")
            self.assertTrue((d / "code" / "side_output.json").exists())


class DocShellBlocks(unittest.TestCase):
    """Command blocks in the documents paste into zsh as well as bash (tools/lint_project.py --docs)."""

    def lint(self, text):
        with tempfile.TemporaryDirectory() as tmp:
            md = Path(tmp) / "doc.md"
            md.write_text(text)
            return subprocess.run([sys.executable, str(REPO / "tools" / "lint_project.py"), "--docs", str(md)],
                                  capture_output=True, text=True)

    def test_zsh_hazards_fail_and_the_fixed_block_passes(self):
        bad = ("```bash\n# set up\n./setup.sh --check   # what is missing\npython3 tools/run.py status runs/<run>\n"
               "pip install manim[jupyter]\n```\n")
        r = self.lint(bad)
        self.assertEqual(r.returncode, 1, r.stdout)
        for needle in ("comment line", "trailing comment", "placeholder", "unquoted 'manim[jupyter]'"):
            self.assertIn(needle, r.stdout)
        good = ("```bash\n./setup.sh --check\npython3 tools/run.py status runs/2026-10-30-example\n"
                "pip install 'manim[jupyter]'\nchmod +x setup.sh tools/*.sh tools/ci/*.sh\n```\n")
        r = self.lint(good)
        self.assertEqual(r.returncode, 0, r.stdout)

    def test_project_documents_are_clean(self):
        docs = [str(p) for p in (REPO / "README.md", REPO / "SETUP-AUTOMATION.md", REPO / "CONTRIBUTING.md",
                                 REPO / "CLOUD-SESSION.md")]
        r = subprocess.run([sys.executable, str(REPO / "tools" / "lint_project.py"), "--docs", *docs],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout)


class HooksFailClosed(unittest.TestCase):
    """The safety hooks block on anything unexpected, never let it through."""
    HOOKS = REPO / "tools" / "hooks"

    def run_hook(self, name, stdin):
        return subprocess.run([sys.executable, str(self.HOOKS / name)], input=stdin, capture_output=True, text=True)

    def test_unreadable_input_blocks(self):
        for name in ("block_publish.py", "reviewer_write_guard.py"):
            with self.subTest(hook=name):
                self.assertEqual(self.run_hook(name, "not json").returncode, 2)

    def test_too_old_python_blocks(self):
        code = ("import runpy, sys; sys.version_info = (3, 6, 15, 'final', 0); sys.argv = ['hook']; "
                f"runpy.run_path({str(self.HOOKS / 'block_publish.py')!r}, run_name='__main__')")
        r = subprocess.run([sys.executable, "-c", code], input="{}", capture_output=True, text=True)
        self.assertEqual(r.returncode, 2)
        self.assertIn("too old", r.stderr)

    def test_hook_syntax_parses_on_old_pythons(self):
        import ast
        for p in sorted(self.HOOKS.glob("*.py")):
            with self.subTest(hook=p.name):
                ast.parse(p.read_text(), feature_version=(3, 7))      # macOS ships python3 3.9


if __name__ == "__main__":
    unittest.main()
