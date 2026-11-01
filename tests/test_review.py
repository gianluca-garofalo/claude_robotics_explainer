"""Unit tests for the explainer review wiring: the five reviewers (the linear-reader with LR- ids), the reader-flow
severity row, the symbol ledger (schema, cross-check, summary) and the reading-order text (tools/explainer_text.py).
The prompts themselves are judged by hand: tests/fixtures/review/reader_flow_eval.md."""
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
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
    """The linear-reader is an agent, a reviewer the gate requires, part of the skill and the workflow, with LR- ids."""

    def test_agent_definition(self):
        text = (REPO / ".claude" / "agents" / "linear-reader.md").read_text(encoding="utf-8")
        fm = text.split("---")[1]
        self.assertIn("name: linear-reader", fm)
        self.assertIn("reviewer_write_guard.py", fm)              # writes only under review/
        self.assertNotRegex(fm, r"tools:.*\bEdit\b")
        self.assertNotIn("model:", fm)
        for phrase in ("front to back", "never fill a gap", "LR-", "linear-reader.json", "explainer_text.py"):
            self.assertIn(phrase, text)

    def test_wired_everywhere(self):
        self.assertIn("linear-reader", gate.REVIEWERS)
        self.assertEqual(len(gate.REVIEWERS), 5)
        self.assertEqual(validate.ID_PREFIX["linear-reader"], "LR")
        skill = (REPO / ".claude" / "skills" / "explainer-review" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("`linear-reader` (`LR-`", skill)
        workflow = (REPO / ".claude" / "workflows" / "review-fanout.js").read_text(encoding="utf-8")
        listed = re.search(r"const REVIEWERS = \[(.*?)\]", workflow, re.S).group(1)
        self.assertEqual(re.findall(r"'([\w-]+)'", listed), list(gate.REVIEWERS))
        self.assertIn("`LR-`", (REPO / ".claude" / "agents" / "finding-verifier.md").read_text(encoding="utf-8"))
        self.assertTrue((FIX / "linear-reader.json").exists())    # the dry runs pass the gate with it

    def test_reader_flow_agents_state_the_major_cases(self):
        """Run 1 of the manual eval under-rated an example without its claim and grouped four places in one minor
        finding: both reader-flow agents now say so explicitly."""
        for name in ("presentation-reviewer", "linear-reader"):
            text = " ".join((REPO / ".claude" / "agents" / f"{name}.md").read_text(encoding="utf-8").split())
            self.assertRegex(text, r"does not say which earlier claim it checks.{0,40}`major`|`major`.{0,200}does "
                                   r"not say which earlier claim it checks", name)
            self.assertIn("without an announcement", text, name)
            self.assertIn("never fold several such places into one `minor` finding", text.replace("Never", "never"),
                          name)
        lr = " ".join((REPO / ".claude" / "agents" / "linear-reader.md").read_text(encoding="utf-8").split())
        self.assertIn("switches from one function to another in the same role", lr)

    def test_contract_ids_and_reader_flow_severity(self):
        text = CONTRACT.read_text(encoding="utf-8")
        self.assertIn("`LR-n` linear", text)
        major = re.findall(r"^\| `major` \| (.*) \|$", text, re.M)
        self.assertTrue(any("cannot follow a derivation or argument" in r and "unannounced change of meaning" in r
                            and "missing link" in r for r in major), major)
        minor = re.search(r"^\| `minor` \| (.*) \|$", text, re.M).group(1)
        self.assertIn("plain wording", minor)


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
            self.assertNotIn("presentation_check.json", validate.NOT_REVIEWS)
        finally:
            shutil.rmtree(run.parent)

    def test_every_reviewer_is_told_where_its_files_go(self):
        for name, prefix in (("technical-correctness-reviewer", "tc_"), ("reference-verifier", "ref_"),
                             ("presentation-reviewer", "pres_"), ("claims-red-team", "rt_"),
                             ("linear-reader", "lr_"), ("finding-verifier", "verify_")):
            text = (REPO / ".claude" / "agents" / f"{name}.md").read_text(encoding="utf-8")
            self.assertIn(f"review/checks/{prefix}", text, name)
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


class EvalNote(unittest.TestCase):
    def test_note_lists_the_three_findings(self):
        text = (REPO / "tests" / "fixtures" / "review" / "reader_flow_eval.md").read_text(encoding="utf-8")
        self.assertIn("0860176d796b62ad8115567b619f7c4fe09771cffad725acd060b75cb4dd6183", text)
        for case, where in (("(a)", "Section 5.2"), ("(b)", "Section 6.3"), ("(c)", "Section 6.2")):
            self.assertIn(f"**{case}", text)
            self.assertIn(where, text)


if __name__ == "__main__":
    unittest.main()
