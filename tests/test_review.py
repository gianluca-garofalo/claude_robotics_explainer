"""Unit tests for the explainer review wiring: the reviewers the gate requires (the linear-reader with LR- ids), the
symbol ledger (schema, cross-check, summary) and the reading-order text (tools/explainer_text.py); and the
linear-viewer of both video reviews (LV- ids, its reports in the gates).
The prompts themselves are judged by hand: tests/fixtures/review/reader_flow_eval.md."""
import json
import re
import shutil
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
sys.path.insert(0, str(REPO / "tools"))

import explainer_text  # noqa: E402
import gate  # noqa: E402
import validate  # noqa: E402

CONTRACT = REPO / ".claude" / "skills" / "explainer-review" / "reviewer-contract.md"
FIX = REPO / "tests" / "fixtures" / "run" / "review"


def report(reviewer, *findings):
    return {"schema_version": 1, "reviewer": reviewer, "summary": "Test report.",
            "checks_run": [{"command": "test", "result": "test"}],
            "findings": [{"id": fid, "severity": sev, "location": "Section 6.2", "issue": "An unannounced switch.",
                          "evidence": "Quoted.", "suggested_fix": "Announce it.", "confidence": "high"}
                         for fid, sev in findings]}


def ledger(*symbols):
    return {"schema_version": 1, "reviewer": "presentation-reviewer", "symbols": list(symbols)}


P_SWITCH = {"symbol": "p", "finding": "PRES-1", "uses": [
    {"section": "5.2", "location": "equation (14)", "meaning": "momentum field", "defined_from": "W",
     "change": "first"},
    {"section": "6.2", "location": "dictionary", "meaning": "momentum field", "defined_from": "V",
     "change": "unannounced"}]}


class FiveReviewers(unittest.TestCase):
    """Every reviewer the gate requires is an agent, part of the skill and the workflow, with its own finding ids; the
    linear-reader writes only under review/. Structure only: the prompts' wording is judged by hand
    (tests/fixtures/review/reader_flow_eval.md)."""

    def test_agent_definition(self):
        text = (REPO / ".claude" / "agents" / "linear-reader.md").read_text(encoding="utf-8")
        fm = yaml.safe_load(text.split("---")[1])
        self.assertEqual(fm["name"], "linear-reader")
        self.assertIn("reviewer_write_guard.py", json.dumps(fm.get("hooks")))   # writes only under review/
        self.assertNotRegex(str(fm.get("tools", "")), r"\bEdit\b")
        self.assertNotIn("model", fm)
        for name in ("linear-reader.json", "explainer_text.py"):              # its report, the tool it reads with
            self.assertIn(name, text)

    def test_wired_everywhere(self):
        self.assertIn("linear-reader", gate.REVIEWERS)
        skill = (REPO / ".claude" / "skills" / "explainer-review" / "SKILL.md").read_text(encoding="utf-8")
        for r in gate.REVIEWERS:
            with self.subTest(reviewer=r):
                self.assertTrue((REPO / ".claude" / "agents" / f"{r}.md").is_file())
                self.assertIn(r, validate.ID_PREFIX)
                self.assertIn(r, skill)
        workflow = (REPO / ".claude" / "workflows" / "review-fanout.js").read_text(encoding="utf-8")
        listed = re.search(r"const REVIEWERS = \[(.*?)\]", workflow, re.S).group(1)
        self.assertEqual(re.findall(r"'([\w-]+)'", listed), list(gate.REVIEWERS))
        self.assertIn("LR-", (REPO / ".claude" / "agents" / "finding-verifier.md").read_text(encoding="utf-8"))


class Ids(unittest.TestCase):
    def check(self, data):
        rep = validate.Report("test")
        validate.validate_review(data, rep)
        return rep.errors

    def test_lr_ids_accepted(self):
        self.assertEqual(self.check(report("linear-reader", ("LR-1", "major"), ("LR-2", "minor"))), [])

    def test_each_reviewer_keeps_its_prefix(self):
        self.assertTrue(any("LR-n" in e for e in self.check(report("linear-reader", ("PRES-1", "major")))))
        self.assertTrue(any("PRES-n" in e for e in self.check(report("presentation-reviewer", ("LR-1", "major")))))
        self.assertEqual(self.check(report("another-reviewer", ("XY-1", "minor"))), [])   # unknown: any PREFIX-n


class MergeAndGate(unittest.TestCase):
    """An LR- major is verified, stays open until fixed or resolved, and the summary lists the ledger's changes."""

    def setUp(self):
        self.run = Path(tempfile.mkdtemp()) / "2026-11-01-test"
        (self.run / "review" / "verify").mkdir(parents=True)
        self.write("linear-reader.json", report("linear-reader", ("LR-1", "major"), ("LR-2", "minor")))
        self.write("presentation-reviewer.json", report("presentation-reviewer", ("PRES-1", "major")))

    def tearDown(self):
        shutil.rmtree(self.run.parent)

    def write(self, name, data):
        (self.run / "review" / name).write_text(json.dumps(data), encoding="utf-8")

    def merge(self):
        r = subprocess.run([sys.executable, str(REPO / "tools" / "merge_reviews.py"), str(self.run)],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return json.loads((self.run / "review" / "summary.json").read_text(encoding="utf-8"))

    def test_lr_major_flow(self):
        s = self.merge()
        self.assertIn("LR-1", s["unverified_blocker_major"])
        self.assertIn("LR-1", s["open_blocker_major"])
        self.assertNotIn("LR-2", s["open_blocker_major"])              # minor: listed, never blocking
        self.write("verify/LR-1.json", {"schema_version": 1, "finding": "LR-1", "verdict": "confirmed",
                                        "reason": "Read up to 6.2: no sentence links p to V.", "checks_run": []})
        s = self.merge()
        self.assertEqual(s["unverified_blocker_major"], ["PRES-1"])
        self.assertIn("LR-1", s["open_blocker_major"])
        self.write("resolutions.json", {"resolutions": [{"finding": "LR-1", "status": "fixed",
                                                         "note": "Bridging sentence added at the start of 6.2."}]})
        self.assertNotIn("LR-1", self.merge()["open_blocker_major"])

    def merge_fails(self):
        r = subprocess.run([sys.executable, str(REPO / "tools" / "merge_reviews.py"), str(self.run)],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        return r.stderr

    def test_a_later_round_keeps_the_earlier_findings(self):
        self.write("resolutions.json", {"resolutions": [{"finding": "LR-1", "status": "fixed", "note": "Bridged."}]})
        self.write("linear-reader.round2.json", report("linear-reader", ("LR-3", "minor")))
        s = self.merge()
        self.assertEqual({f["id"]: f["status"] for f in s["findings"] if f["id"].startswith("LR-")},
                         {"LR-1": "fixed", "LR-2": "open", "LR-3": "open"})
        self.assertEqual([r.get("round", 1) for r in s["reviewers"] if r["reviewer"] == "linear-reader"], [1, 2])
        self.write("linear-reader.round2.json", report("linear-reader", ("LR-2", "minor")))
        self.assertIn("LR-2 is in linear-reader.json and in linear-reader.round2.json", self.merge_fails())
        (self.run / "review" / "linear-reader.round2.json").unlink()
        self.write("linear-reader.json", report("linear-reader", ("LR-2", "minor")))     # round 1 rewritten
        self.assertIn("LR-1, which no report holds", self.merge_fails())

    def test_ledger_in_summary(self):
        self.write("symbol_ledger.json", ledger(P_SWITCH, {"symbol": "H", "uses": [
            {"section": "5.2", "location": "equation (14)", "meaning": "Hamiltonian", "change": "first"}]}))
        s = self.merge()
        self.assertEqual(s["symbol_ledger"]["symbols"], 2)
        self.assertEqual([c["change"] for c in s["symbol_ledger"]["changes"]], ["first", "unannounced"])
        md = (self.run / "review" / "summary.md").read_text(encoding="utf-8")
        self.assertIn("## Symbol ledger", md)
        self.assertIn("| p | 6.2 | dictionary | momentum field | V | unannounced | PRES-1 |", md)
        self.assertNotIn("symbol_ledger", [r["reviewer"] for r in s["reviewers"]])   # a record, not a report

    def test_invalid_ledger_stops_the_merge(self):
        self.write("symbol_ledger.json", ledger(dict(P_SWITCH, finding=None)))
        r = subprocess.run([sys.executable, str(REPO / "tools" / "merge_reviews.py"), str(self.run)],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 1)
        self.assertIn("must name its finding", r.stdout)

    def test_gate_needs_the_linear_reader(self):
        self.assertEqual([r for r in gate.REVIEWERS if not (FIX / f"{r}.json").exists()], [])


def viewer_report(*findings):
    """A linear-viewer report: each finding with its time."""
    r = report("linear-viewer", *findings)
    for f in r["findings"]:
        f["time_s"] = 12.5
    return r


def verdict(fid, value):
    return {"schema_version": 1, "finding": fid, "verdict": value, "reason": "Watched up to 12.5 s.", "checks_run": []}


class LinearViewer(unittest.TestCase):
    """The linear-reader's video counterpart: an agent with LV- ids, each finding timed, that writes only under review/,
    run by the design review and the final-cut review and expected in both video review sets. Structure only."""

    def test_agent_definition(self):
        text = (REPO / ".claude" / "agents" / "linear-viewer.md").read_text(encoding="utf-8")
        fm = yaml.safe_load(text.split("---")[1])
        self.assertEqual(fm["name"], "linear-viewer")
        self.assertIn("reviewer_write_guard.py", json.dumps(fm.get("hooks")))   # writes only under review/
        self.assertNotRegex(str(fm.get("tools", "")), r"\bEdit\b")
        self.assertNotIn("model", fm)
        for name in ("linear-viewer.json", "voice_script.py", "frames.json", "review/checks/"):   # report, inputs
            self.assertIn(name, text)

    def test_wired_into_both_video_reviews(self):
        self.assertEqual(validate.ID_PREFIX["linear-viewer"], "LV")
        self.assertIn("LV-", (REPO / ".claude" / "agents" / "finding-verifier.md").read_text(encoding="utf-8"))
        for rset, skill in (("video", "manim-video-producer"), ("final_cut", "final-cut-review")):
            with self.subTest(set=rset):
                self.assertIn("linear-viewer", gate.VIDEO_REVIEWERS[rset])
                self.assertIn("`linear-viewer`", (REPO / ".claude" / "skills" / skill / "SKILL.md").read_text(
                    encoding="utf-8"))
                for r in gate.VIDEO_REVIEWERS[rset]:          # each: an agent, its ids, a valid fixture report
                    self.assertTrue((REPO / ".claude" / "agents" / f"{r}.md").is_file(), r)
                    self.assertIn(r, validate.ID_PREFIX)
                    self.assertEqual(validate.validate_file("review", FIX / rset / f"{r}.json").errors, [], r)

    def test_ids_and_times(self):
        def errors(data):
            rep = validate.Report("test")
            validate.validate_review(data, rep)
            return rep.errors
        self.assertEqual(errors(viewer_report(("LV-1", "major"), ("LV-2", "minor"))), [])
        self.assertTrue(any("LV-n" in e for e in errors(viewer_report(("VD-1", "major")))))
        self.assertTrue(any("time_s is required" in e for e in errors(report("linear-viewer", ("LV-1", "minor")))))


class VideoReviewGates(unittest.TestCase):
    """The pre-render and release gates need every reviewer of their set (gate.VIDEO_REVIEWERS); an open confirmed
    linear-viewer major blocks both, a design reviewer's major does not block the drafts."""

    def setUp(self):
        self.run = Path(tempfile.mkdtemp()) / "2026-11-01-test"
        (self.run / "video" / "final").mkdir(parents=True)
        (self.run / "video" / "plan.json").write_text('{"scenes": []}', encoding="utf-8")
        (self.run / "video" / "final" / "test.mp4").write_bytes(b"stands in for the assembled video")
        (self.run / "selection.json").write_text('{"slug": "test"}', encoding="utf-8")
        for rset, names in gate.VIDEO_REVIEWERS.items():
            (self.run / "review" / rset / "verify").mkdir(parents=True)
            for r in names:
                shutil.copy(FIX / rset / f"{r}.json", self.run / "review" / rset / f"{r}.json")

    def tearDown(self):
        shutil.rmtree(self.run.parent)

    def write(self, rset, name, data):
        (self.run / "review" / rset / name).write_text(json.dumps(data), encoding="utf-8")

    def row(self, rset):
        """Merge the set, then its gate's review row: pre-render for review/video/, release for review/final_cut/."""
        r = subprocess.run([sys.executable, str(REPO / "tools" / "merge_reviews.py"), str(self.run), "--set", rset],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        g = gate.Gates()
        (gate.pre_render if rset == "video" else gate.release)(self.run, g, {})
        return next(c for c in g.checks if c["name"].startswith("video review" if rset == "video" else "final-cut"))

    def test_each_set_needs_the_linear_viewer(self):
        for rset in gate.VIDEO_REVIEWERS:
            with self.subTest(set=rset):
                row = self.row(rset)
                self.assertTrue(row["ok"], row["detail"])
                (self.run / "review" / rset / "linear-viewer.json").unlink()
                row = self.row(rset)
                self.assertFalse(row["ok"])
                self.assertIn("no linear-viewer report", row["detail"])

    def test_an_open_lv_major_blocks_both_gates(self):
        for rset in gate.VIDEO_REVIEWERS:
            with self.subTest(set=rset):
                self.write(rset, "linear-viewer.json", viewer_report(("LV-1", "minor"), ("LV-2", "major")))
                self.write(rset, "verify/LV-2.json", verdict("LV-2", "confirmed"))
                row = self.row(rset)
                self.assertFalse(row["ok"])
                self.assertIn("LV-2", row["detail"])
                self.write(rset, "resolutions.json", {"resolutions": [{"finding": "LV-2", "status": "fixed",
                                                                       "note": "The term is explained first now."}]})
                self.assertTrue(self.row(rset)["ok"])

    def test_a_design_major_does_not_block_the_drafts(self):
        self.write("video", "video-design-reviewer.json", report("video-design-reviewer", ("VD-1", "major")))
        self.write("video", "verify/VD-1.json", verdict("VD-1", "confirmed"))
        self.assertTrue(self.row("video")["ok"])


class WorkingFiles(unittest.TestCase):
    """Reviewers' scripts and tool outputs live in review/checks/, which validate and merge never read; a tool output
    left at the top of review/ fails validation with a message that says where it belongs."""

    def test_checks_folder_is_ignored_and_strays_are_explained(self):
        run = Path(tempfile.mkdtemp()) / "2026-11-01-test"
        try:
            (run / "review" / "checks").mkdir(parents=True)
            (run / "review" / "linear-reader.json").write_text(json.dumps(report("linear-reader", ("LR-1", "minor"))),
                                                               encoding="utf-8")
            tool = {"file": "explainer.html", "results": [{"name": "theme toggle", "ok": True}], "pass": True}
            (run / "review" / "checks" / "pres_features.json").write_text(json.dumps(tool), encoding="utf-8")
            (run / "review" / "checks" / "tc_riccati.py").write_text("print(1)\n", encoding="utf-8")
            self.assertEqual([e for r in validate.validate_run(run) for e in r.errors], [])
            r = subprocess.run([sys.executable, str(REPO / "tools" / "merge_reviews.py"), str(run)],
                               capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            s = json.loads((run / "review" / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual([x["reviewer"] for x in s["reviewers"]], ["linear-reader"])
            (run / "review" / "features_check.json").write_text(json.dumps(tool), encoding="utf-8")   # a stray
            errs = [e for r in validate.validate_run(run) for e in r.errors]
            self.assertTrue(any("not a reviewer report" in e and "review/checks/" in e for e in errs), errs)
        finally:
            shutil.rmtree(run.parent)

    def test_every_reviewer_is_told_where_its_files_go(self):
        """review/checks/ is the folder validate and merge skip: every reviewer must know it, or its tool outputs fail
        the run's validation."""
        for name in (*gate.REVIEWERS, "finding-verifier"):
            text = (REPO / ".claude" / "agents" / f"{name}.md").read_text(encoding="utf-8")
            self.assertIn("review/checks/", text, name)
        self.assertIn("review/checks/", CONTRACT.read_text(encoding="utf-8"))


class SymbolLedger(unittest.TestCase):
    def errors(self, data):
        rep = validate.Report("test")
        validate.validate_symbol_ledger(data, rep)
        return rep.errors

    def test_fixture_and_switch_are_valid(self):
        self.assertEqual(validate.validate_file("symbol_ledger", FIX / "symbol_ledger.json").errors, [])
        self.assertEqual(self.errors(ledger(P_SWITCH)), [])
        self.assertEqual(validate.kind_for(FIX / "symbol_ledger.json"), "symbol_ledger")

    def test_rules(self):
        silent = dict(P_SWITCH)
        silent.pop("finding")
        self.assertTrue(any("must name its finding" in e for e in self.errors(ledger(silent))))
        first = json.loads(json.dumps(P_SWITCH))
        first["uses"][0]["change"] = "none"
        self.assertTrue(any("'first'" in e for e in self.errors(ledger(first))))
        odd = json.loads(json.dumps(P_SWITCH))
        odd["uses"][1]["change"] = "silent"
        self.assertTrue(any("change must be one of" in e for e in self.errors(ledger(odd))))
        self.assertTrue(self.errors(ledger()))                      # every symbol of the explainer: not empty

    def test_run_check_names_existing_findings(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            (tmp / "review").mkdir()
            (tmp / "review" / "symbol_ledger.json").write_text(json.dumps(ledger(P_SWITCH)), encoding="utf-8")
            (tmp / "review" / "presentation-reviewer.json").write_text(
                json.dumps(report("presentation-reviewer", ("PRES-2", "major"))), encoding="utf-8")
            errs = [e for r in validate.validate_run(tmp) for e in r.errors]
            self.assertTrue(any("PRES-1 is not in" in e for e in errs), errs)
            (tmp / "review" / "presentation-reviewer.json").write_text(
                json.dumps(report("presentation-reviewer", ("PRES-1", "major"))), encoding="utf-8")
            self.assertEqual([e for r in validate.validate_run(tmp) for e in r.errors], [])
        finally:
            shutil.rmtree(tmp)


PAGE = """<!doctype html><html><head><title>T</title><style>p{}</style><script>var x = 1;</script></head><body>
<button class="toc-toggle">Contents</button><nav class="toc"><a href="#sec-a">1 A</a></nav>
<h1>Title</h1><div class="abstract">The abstract says $V$ is the value.</div>
<section id="sec-a"><h2>1. First</h2><p>Define $p:=-\\nabla W$.</p>
<h3 id="sec-a1">1.1 Detail</h3><p>Text   with
  spaces.</p><div class="equation-block">$$ a=b \\tag{1} $$</div>
<figure><svg aria-label="A saddle"><text>hidden</text></svg><figcaption>Figure 1. The saddle.</figcaption></figure>
<h4>Case A</h4><p>Case text.</p></section>
<section id="sec-b"><h2>2. Second</h2><table><tr><th>Symbol</th><th>Meaning</th></tr><tr><td>$p$</td>
<td>$-\\nabla V$</td></tr></table><h3 id="sec-b1">2.1 More</h3><p>Uses $p=-\\nabla V$.</p></section></body></html>"""


class ReadingOrder(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        (self.tmp / "explainer.html").write_text(PAGE, encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def text(self, *args):
        r = subprocess.run([sys.executable, str(REPO / "tools" / "explainer_text.py"), str(self.tmp / "explainer.html"),
                            *args], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout

    def test_blocks(self):
        blocks = explainer_text.read(self.tmp / "explainer.html")
        texts = [b["text"] for b in blocks]
        self.assertIn("Text with spaces.", texts)                   # whitespace collapsed
        self.assertIn("$$ a=b \\tag{1} $$", texts)                  # math as written, with its tag
        self.assertIn("[figure: A saddle]", texts)                  # an SVG is one line; its text is not read
        self.assertIn("Symbol | Meaning", texts)
        self.assertFalse(any("var x" in t or "Contents" in t or t == "1 A" for t in texts))   # script, button, nav
        case = next(b for b in blocks if b["text"] == "Case A")
        self.assertEqual((case["sec"], case["sec_id"]), ("1.1", "sec-a1"))   # an unnumbered heading stays in 1.1

    def test_outline_section_until_grep(self):
        outline = self.text("--outline")
        self.assertIn("1.1 Detail  [sec-a1,", outline)
        self.assertIn("2. Second  [sec-b,", outline)
        one = self.text("--section", "1.1")
        self.assertIn("Text with spaces.", one)
        self.assertNotIn("Define $p", one)
        self.assertNotIn("Second", one)
        self.assertIn("Case text.", self.text("--section", "sec-a1"))
        before = self.text("--until", "2")
        self.assertIn("Define $p:=-\\nabla W$.", before)
        self.assertNotIn("nabla V", before)
        self.assertEqual(self.text("--until", "2", "--grep", r"nabla V").strip(), "")
        self.assertIn("[2.1] Uses $p=-\\nabla V$.", self.text("--grep", r"nabla V"))
        self.assertIn("More", self.text("--from", "2.1"))


if __name__ == "__main__":
    unittest.main()
