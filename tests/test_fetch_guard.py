"""The reviewers' fetch guard (tools/hooks/reviewer_fetch_guard.py): a fetch from a host no WebFetch allow rule covers,
a broken URL, unreadable settings, curl and wget are refused at once (exit 2), so no reviewer waits on a permission
prompt or a dead host; the reviewers and the verifier that read the web carry it, the news scout does not."""
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
import testenv  # noqa: E402
testenv.activate()                  # fixture config and sources, before any tool is imported

GUARD = REPO / "tools" / "hooks" / "reviewer_fetch_guard.py"
AGENTS = REPO / ".claude" / "agents"
GUARDED = ("reference-verifier", "finding-verifier", "claims-red-team")


class FetchGuard(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.settings = self.write("settings.json", ["Bash(python3 tools/*)", "WebSearch", "WebFetch(domain:arxiv.org)",
                                                     "WebFetch(domain:*.ieee.org)"])

    def write(self, name, allow):
        path = self.tmp / name
        path.write_text(json.dumps({"permissions": {"allow": allow}}), encoding="utf-8")
        return path

    def guard(self, payload, *settings):
        stdin = payload if isinstance(payload, str) else json.dumps(payload)
        return subprocess.run([sys.executable, str(GUARD), *map(str, settings or (self.settings,))], input=stdin,
                              capture_output=True, text=True)

    def fetch(self, url, *settings):
        return self.guard({"tool_name": "WebFetch", "tool_input": {"url": url, "prompt": "the title"}}, *settings)

    def test_allowed_and_wildcard_hosts_pass(self):
        for url in ("https://arxiv.org/abs/2401.00001", "http://ArXiv.org.:443/abs/1",
                    "https://ieeexplore.ieee.org/document/1", "https://a.b.ieee.org/x"):
            with self.subTest(url=url):
                r = self.fetch(url)
                self.assertEqual(r.returncode, 0, r.stderr)

    def test_other_hosts_are_refused_and_named(self):
        for url, host in (("https://rd.springer.com/article/10.1007/x", "rd.springer.com"),
                          ("https://ieee.org/", "ieee.org"),                    # *. covers subdomains only
                          ("https://arxiv.org.example.com/abs/1", "arxiv.org.example.com"),
                          ("https://example.com/?next=https://arxiv.org/", "example.com"),
                          ("https://example.com\\@arxiv.org/", "example.com")):   # a URL parser's \ is a /
            with self.subTest(url=url):
                r = self.fetch(url)
                self.assertEqual(r.returncode, 2)
                self.assertIn(host, r.stderr)

    def test_broken_urls_and_input_are_refused(self):
        for url in ("not a url", "arxiv.org/abs/1", "https://", "http://[::1", "file:///etc/hosts", ""):
            with self.subTest(url=url):
                self.assertEqual(self.fetch(url).returncode, 2)
        self.assertEqual(self.guard("not json").returncode, 2)
        self.assertEqual(self.guard({"tool_name": "WebFetch", "tool_input": {}}).returncode, 2)

    def test_unreadable_settings_fail_closed(self):
        broken = self.tmp / "broken.json"
        broken.write_text("{", encoding="utf-8")
        for settings in (self.tmp / "missing.json", broken):
            with self.subTest(settings=settings.name):
                self.assertEqual(self.fetch("https://arxiv.org/abs/1", settings).returncode, 2)

    def test_rules_of_every_settings_file_count(self):
        user = self.write("user.json", ["WebFetch(domain:link.springer.com)", "WebFetch(domain:proceedings.*)"])
        for url, code in (("https://link.springer.com/x", 0), ("https://proceedings.org/x", 0),
                          ("https://proceedings.evil.org/x", 2), ("https://rd.springer.com/x", 2)):
            with self.subTest(url=url):
                self.assertEqual(self.fetch(url, self.settings, user).returncode, code)
        anything = self.write("ci.json", ["WebFetch"])                   # a bare WebFetch rule: every host
        self.assertEqual(self.fetch("https://rd.springer.com/x", self.settings, anything).returncode, 0)

    def test_curl_and_wget_are_refused(self):
        for cmd, code in (("curl -sL https://arxiv.org/abs/1", 2), ("cd runs && wget https://doi.org/10.1/x", 2),
                          ("timeout 9 /usr/bin/curl https://example.org", 2), ("grep -n curl notes.md", 0),
                          ("python3 tools/validate.py runs/x", 0)):
            with self.subTest(cmd=cmd):
                self.assertEqual(self.guard({"tool_name": "Bash", "tool_input": {"command": cmd}}).returncode, code)


class GuardedAgents(unittest.TestCase):
    def test_the_web_reading_reviewers_carry_it(self):
        for name in GUARDED + ("news-scout",):
            fm = yaml.safe_load((AGENTS / f"{name}.md").read_text(encoding="utf-8").split("---")[1])
            groups = [g for g in fm["hooks"]["PreToolUse"] if "reviewer_fetch_guard.py" in json.dumps(g)]
            with self.subTest(agent=name):
                if name == "news-scout":                                  # it reads lab pages on any host
                    self.assertEqual(groups, [])
                else:
                    self.assertEqual(len(groups), 1)
                    self.assertEqual(set(re.split(r"\s*[|,]\s*", groups[0]["matcher"])), {"WebFetch", "Bash"})


if __name__ == "__main__":
    unittest.main()
