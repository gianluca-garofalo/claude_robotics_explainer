"""The only test that reads sources/: every real source document passes tools/check_source.py (python3 -m unittest).

It asserts properties only (no error in check_source's sense: the page lints, no external script, every manifest
script exists), never wording, section numbers, counts or hashes, and it skips when sources/ holds no source.
Warnings (a script the document names but code/ lacks, stale section tags) are printed by check_source and by the
CI step, not failed here. Every other test uses tests/fixtures/sources (tests/test_hermetic.py enforces it).
"""
import subprocess
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
import testenv  # noqa: E402
testenv.activate()                  # fixture config and sources, before any tool is imported

REAL_SOURCES = REPO / "sources"


class RealSourcesSmoke(unittest.TestCase):
    def test_every_real_source_passes_check_source(self):
        folders = sorted(p for p in REAL_SOURCES.iterdir() if p.is_dir() and not p.name.startswith((".", "_"))) \
            if REAL_SOURCES.is_dir() else []
        if not folders:
            self.skipTest("sources/ holds no source document")
        for folder in folders:
            with self.subTest(source=folder.name):
                r = subprocess.run([sys.executable, str(REPO / "tools" / "check_source.py"), str(folder)], cwd=REPO,
                                   capture_output=True, text=True, timeout=300)
                self.assertEqual(r.returncode, 0, r.stdout[-4000:] + r.stderr[-1000:])


if __name__ == "__main__":
    unittest.main()
