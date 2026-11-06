"""Unit tests for tools/check_source.py on copies of the fixture source (python3 -m unittest)."""
import json
import shutil
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

import check_source as CS  # noqa: E402

KATEX_JS = '<script defer src="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.js"></script>'
VIEWER = "<script type='text/javascript' src='https://viewer.example.org/inject.js'></script>"


def run(*args):
    return subprocess.run([sys.executable, str(REPO / "tools" / "check_source.py"), *map(str, args)],
                          capture_output=True, text=True)


class CheckSource(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="check-source-"))
        self.src = self.tmp / "sources" / "demo"
        shutil.copytree(testenv.SOURCE_DIR, self.src)
        self.page = self.src / "explainer.html"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def edit(self, path, old, new):
        text = path.read_text(encoding="utf-8")
        self.assertIn(old, text)
        path.write_text(text.replace(old, new, 1), encoding="utf-8")

    def test_the_fixture_source_is_clean(self):
        r = run(self.src, "--json", self.tmp / "out.json")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("check_source: ok (0 error(s), 0 warning(s))", r.stdout)
        rep = json.loads((self.tmp / "out.json").read_text())["sources"][0]
        self.assertEqual((rep["scripts_named"], rep["scripts_missing"]), (3, []))

    def test_an_external_script_is_an_error_and_strip_removes_only_it(self):
        self.edit(self.page, "<head>", "<head>" + VIEWER)
        self.edit(self.page, "</body>", "<script src=\"https://cdn.jsdelivr.net/npm/other@1.0.0/x.js\"></script>\n"
                                        "</body>")
        before = self.page.read_text(encoding="utf-8")
        r = run(self.src)
        self.assertEqual(r.returncode, 1)
        self.assertIn("[external-script]", r.stdout)
        self.assertIn("viewer.example.org", r.stdout)
        self.assertIn("--strip-external-scripts --write", r.stdout)
        r = run(self.src, "--strip-external-scripts")                    # a dry run changes nothing
        self.assertIn("would remove explainer.html:", r.stdout)
        self.assertEqual(self.page.read_text(encoding="utf-8"), before)
        r = run(self.src, "--strip-external-scripts", "--write")
        after = self.page.read_text(encoding="utf-8")
        self.assertNotIn("viewer.example.org", after)
        self.assertIn("<head>\n", after)                                   # the tag only, not its line
        self.assertEqual(after.count("cdn.jsdelivr.net/npm/katex@0.16.9"), before.count("cdn.jsdelivr.net/npm/katex@0.16.9"))
        self.assertIn("npm/other@1.0.0", after)                            # the KaTeX CDN's host is left alone
        self.assertEqual(r.returncode, 1)                                   # ... and lint still reports it
        self.assertIn("[lint-external-resource]", r.stdout)

    def test_a_tag_alone_on_its_line_takes_the_line(self):
        html = f"<head>\n{VIEWER}\n{KATEX_JS}\n</head>"
        out, n = CS.strip_scripts(html)
        self.assertEqual((out, n), (f"<head>\n{KATEX_JS}\n</head>", 1))

    def test_scripts_named_in_the_explainer(self):
        self.edit(self.page, "<code>hilltop_values.py</code>", "<code>hilltop_values.py</code>, "
                  "<code>checks/missing_check.py</code>")
        self.edit(self.page, "<code>speed_limit.py</code>", "<code>speed_limit.py</code>, <code>gone.py</code>")
        r = run(self.src, "--json", self.tmp / "out.json")
        self.assertEqual(r.returncode, 0, r.stdout)                        # a warning: the pipeline still runs
        rep = json.loads((self.tmp / "out.json").read_text())["sources"][0]
        self.assertEqual(rep["scripts_missing"], ["checks/missing_check.py", "gone.py"])
        self.assertIn("names checks/missing_check.py (section 5.1)", r.stdout)

    def test_basenames_after_a_path_resolve_in_its_folder(self):
        code = self.src / "code"
        (code / "other").mkdir()
        (code / "other" / "speed_limit.py").write_text("print('elsewhere')\n")
        blocks = [{"text": "steps/window_steps.py, speed_limit.py", "section": "5.1", "hrefs": []},
                  {"text": "run window_steps.py by hand", "section": "2.2", "hrefs": []}]
        found, missing = CS.script_refs(blocks, code)
        self.assertEqual(sorted(found), ["steps/speed_limit.py", "steps/window_steps.py"])
        self.assertEqual(missing, {})

    def test_manifest_coverage(self):
        (self.src / "code" / "helper.py").write_text("X = 1\n")
        r = run(self.src)
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("code/helper.py is not in checks.toml", r.stdout)
        self.edit(self.src / "code" / "checks.toml", 'script = "steps/speed_limit.py"', 'script = "steps/nowhere.py"')
        r = run(self.src)
        self.assertEqual(r.returncode, 1)
        self.assertIn("[manifest-script-missing]", r.stdout)

    def test_section_tags_after_a_renumbering(self):
        self.edit(self.src / "code" / "checks.toml", 'sections = ["3.1", "3.2"]', 'sections = ["9.9"]')
        self.edit(self.src / "code" / "README.md", "| 2.2, 3.3 |", "| 7.7 |")
        self.edit(self.src / "code" / "checks.toml", 'sections = ["4"]', 'sections = ["1.1"]')
        r = run(self.src)
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("checks.toml: hilltop_values.py is tagged 9.9, which the explainer does not have", r.stdout)
        self.assertIn("code/README.md: the row of steps/window_steps.py names 7.7", r.stdout)
        self.assertIn("checks.toml: steps/speed_limit.py is tagged 1.1, but the explainer's verification table ties "
                      "it to section(s) 4", r.stdout)                      # the row names Section 4
        self.assertEqual(run(self.src, "--strict").returncode, 1)

    def test_no_explainer_and_no_code(self):
        shutil.rmtree(self.src / "code")
        r = run(self.src)
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("[no-companion-code]", r.stdout)
        self.page.unlink()
        r = run(self.src)
        self.assertEqual(r.returncode, 1)
        self.assertIn("[no-explainer]", r.stdout)

    def test_all(self):
        empty = self.tmp / "empty"
        empty.mkdir()
        r = run("--all", "--sources-dir", empty)
        self.assertEqual(r.returncode, 0)
        self.assertIn("no source folders", r.stdout)
        shutil.copytree(self.src, self.tmp / "sources" / "broken")
        self.edit(self.tmp / "sources" / "broken" / "explainer.html", "<head>", "<head>" + VIEWER)
        r = run("--all", "--sources-dir", self.tmp / "sources")
        self.assertEqual(r.returncode, 1)
        self.assertIn("check_source: ok (0 error(s), 0 warning(s))", r.stdout)     # demo
        self.assertIn("check_source: FAIL (1 error(s)", r.stdout)                 # broken


if __name__ == "__main__":
    unittest.main()
