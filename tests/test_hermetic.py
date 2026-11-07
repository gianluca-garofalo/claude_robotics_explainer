"""The tests depend only on fixtures (python3 -m unittest): a guard so that coupling to what the owner may change
cannot creep back.

Rules (AGENTS.md, Changing the pipeline):
- no test file reads the real sources/ or series/ (by path, including sources/<name> and series/<slug>) or the live
  config/ (a source's name or a series slug on its own is not flagged: it may be an ordinary word); tests use tests/fixtures/ (testenv.SOURCES, testenv.CONFIG, the fixture series);
- every test module and dry run calls testenv.activate() before it imports a tool, so every tool, in the process and
  in its subprocesses, reads tests/fixtures/config;
- the only exception is tests/test_sources_smoke.py, which runs tools/check_source.py on each real source.
"""
import json
import re
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
import testenv  # noqa: E402
testenv.activate()                  # fixture config and sources, before any tool is imported

TESTS = REPO / "tests"
EXEMPT = {"test_sources_smoke.py", "testenv.py", "test_hermetic.py"}


def real_names() -> set[str]:
    """Names that only exist in the owner's data: source folders, series slugs (also the plans removed on 2026-11-01,
    kept as the plan-series example) and the pilot series of 2026-10-30."""
    names = {"variational-wbc"}
    for folder in ("sources", "series"):
        root = REPO / folder
        if root.is_dir():
            names |= {p.name for p in root.iterdir() if p.is_dir() and not p.name.startswith((".", "_"))}
    for p in (REPO / ".claude" / "skills" / "plan-series" / "example").glob("*.json"):
        names.add(json.loads(p.read_text(encoding="utf-8")).get("slug", ""))
    return {n for n in names if n}


class Hermetic(unittest.TestCase):
    def files(self):
        return [p for p in sorted(TESTS.glob("*.py")) if p.name not in EXEMPT]

    def test_no_test_reads_real_sources_series_or_config(self):
        patterns = {
            "the real sources/": re.compile(r"(?<![\w/-])sources/|REPO\s*/\s*[\"']sources[\"']"),
            "the real series/": re.compile(r"REPO\s*/\s*[\"']series[\"']"),
            "the live config/": re.compile(r"REPO\s*/\s*[\"']config[\"']"),
        }
        names = real_names()
        problems = []
        for p in self.files():
            text = p.read_text(encoding="utf-8")
            for what, rx in patterns.items():
                for m in rx.finditer(text):
                    line = text.count("\n", 0, m.start()) + 1
                    problems.append(f"{p.name}:{line} reads {what} ({m.group(0)!r}): use tests/fixtures/ (testenv)")
            for n in sorted(names):         # only as a path: a slug may also be an ordinary word or a site name
                for m in re.finditer(rf"(?<![\w-])(?:sources|series)/{re.escape(n)}(?![\w-])", text):
                    line = text.count("\n", 0, m.start()) + 1
                    problems.append(f"{p.name}:{line} names {m.group(0)!r}, which exists only in the owner's data")
        for p in sorted((TESTS / "fixtures" / "series").glob("*.json")):
            source = json.loads(p.read_text(encoding="utf-8")).get("source", "")
            if not source.startswith("tests/fixtures/"):
                problems.append(f"fixtures/series/{p.name}: source {source!r} is not a fixture source")
        self.assertEqual(problems, [])

    def test_every_test_module_activates_the_fixtures_first(self):
        for p in self.files():
            if not (p.name.startswith("test_") or p.name.endswith("dry_run.py")):
                continue
            text = p.read_text(encoding="utf-8")
            with self.subTest(file=p.name):
                self.assertIn("testenv.activate()", text)
                first_tool = re.search(r"REPO\s*/\s*[\"']tools[\"']", text)
                self.assertLess(text.index("testenv.activate()"), first_tool.start() if first_tool else len(text))

    def test_the_fixtures_are_complete(self):
        self.assertEqual(sorted(p.name for p in testenv.CONFIG.glob("*.json")),
                         sorted(p.name for p in (REPO / "config").glob("*.json")))   # same files, frozen values
        self.assertTrue((testenv.SOURCE_DIR / "explainer.html").is_file())
        self.assertTrue((testenv.SOURCE_DIR / "code" / "checks.toml").is_file())
        self.assertFalse(testenv.NO_SERIES.exists())


if __name__ == "__main__":
    unittest.main()
