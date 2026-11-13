"""The tools inside Claude Code's sandbox: check_html.js finds a browser that starts there."""
import json
import os
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

CHECK_HTML = REPO / "tools" / "check_html.js"
# Playwright's chromium, stubbed: its own build aborts as a full Chromium does in the sandbox; a browser named by
# executablePath starts unless its path says "broken". Prints the browsers tried and the outcome.
STUB = """
const { launchChromium } = require(process.argv[1]);
const tried = [];
const chromium = { async launch(o = {}) {
  tried.push(o.executablePath || 'pinned');
  if (!o.executablePath) throw new Error('process_singleton_posix.cc: socket: Operation not permitted');
  if (o.executablePath.includes('broken')) throw new Error('crashed');
  return { version: () => '1.0' };
} };
const done = r => console.log(JSON.stringify({ tried, ...r }));
launchChromium(chromium, JSON.parse(process.argv[2])).then(() => done({ ok: true }), e => done({ error: e.message }));
"""


@unittest.skipUnless(shutil.which("node"), "needs node")
class BrowserFallback(unittest.TestCase):
    """Playwright's own Chromium does not start, for any reason: the next browser that starts runs ($CHROMIUM_PATH,
    the preinstalled headless shells, newest first, then the full Chromium); when none starts, the first error."""

    def node(self, script, *args, **env):
        base = {k: v for k, v in os.environ.items() if k != "CHROMIUM_PATH"}
        r = subprocess.run(["node", "-e", script, str(CHECK_HTML), *args], capture_output=True, text=True,
                           env=dict(base, **env), timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout.strip().splitlines()

    def launch(self, candidates):
        *log, last = self.node(STUB, json.dumps(candidates))
        return json.loads(last), "\n".join(log)

    def test_the_first_browser_that_starts_runs(self):
        res, log = self.launch(["/c/broken-shell", "/c/shell", "/c/chromium"])
        self.assertEqual(res, {"tried": ["pinned", "/c/broken-shell", "/c/shell"], "ok": True})
        self.assertIn("/c/shell", log)                      # says which browser ran

    def test_none_starts_reports_the_first_error(self):
        res, _ = self.launch(["/c/broken-a", "/c/broken-b"])
        self.assertEqual(res["tried"], ["pinned", "/c/broken-a", "/c/broken-b"])
        self.assertIn("process_singleton", res["error"])

    def test_headless_shells_newest_first_then_the_full_chromium(self):
        script = "console.log(JSON.stringify(require(process.argv[1]).browserCandidates(process.argv[2])))"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shell = {n: root / f"chromium_headless_shell-{n}/chrome-headless-shell-linux64/chrome-headless-shell"
                     for n in (999, 1250)}
            own, full = root / "own" / "chrome", root / "chromium"
            for p in (*shell.values(), own, full):
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text("")
            (root / "chromium_headless_shell-1300").mkdir()          # no executable inside: skipped
            got = self.node(script, str(root), CHROMIUM_PATH=str(own))
            self.assertEqual(json.loads(got[-1]), [str(p) for p in (own, shell[1250], shell[999], full)])
            got = self.node(script, str(root), CHROMIUM_PATH=str(root / "missing"))
            self.assertEqual(json.loads(got[-1]), [str(p) for p in (shell[1250], shell[999], full)])


if __name__ == "__main__":
    unittest.main()
