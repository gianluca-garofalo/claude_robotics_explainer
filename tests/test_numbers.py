"""Unit tests for the number-format house rule: fmt() (templates/manim/reading_model.py) and
tools/video/check_numbers.py (python3 -m unittest)."""
import subprocess
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
sys.path.insert(0, str(REPO / "tools" / "video"))
sys.path.insert(0, str(REPO / "templates" / "manim"))

import check_numbers as CN  # noqa: E402
from reading_model import fmt  # noqa: E402

FIX = REPO / "tests" / "fixtures" / "numbers"


def run_cli(*args):
    return subprocess.run([sys.executable, str(REPO / "tools" / "video" / "check_numbers.py"), *args],
                          capture_output=True, text=True)


class Format(unittest.TestCase):
    def test_house_format(self):
        cases = {(0.500000,): "0.5", (1.27712,): "1.28", (3.0,): "3", (-0.95,): "−0.95", (1.2e-5,): "1.2×10⁻⁵",
                 (1277.4,): "1277", (0.0012345,): "0.00123"}
        for args, want in cases.items():
            with self.subTest(args=args):
                self.assertEqual(fmt(*args), want)

    def test_fixed_decimals_for_readouts_and_exact_values(self):
        self.assertEqual(fmt(0.2, decimals=2), "0.20")
        self.assertEqual(fmt(-0.001, decimals=2), "0.00")            # never "−0.00"
        self.assertEqual(fmt(0, exact=True), "0")
        self.assertEqual(fmt(1 / 3, exact=True), "⅓")
        self.assertEqual(fmt(0.5, exact=True), "0.5")
        self.assertEqual(fmt(1.2, unit="s"), "1.2 s")

    def test_fmt_output_passes_the_check(self):
        cfg, fd = CN.settings(), CN.Findings()
        for x in (0.500000, 1.27712, -0.95, 1.2e-5, 0.0012345):
            CN.check_static(f"x = {fmt(x)}", "text", "screen", "screen", "test", cfg, fd)
        self.assertEqual(fd.items, [])


class Fixture(unittest.TestCase):
    """The before fixture holds every kind of number problem; the same scene, fixed, passes."""

    def test_before_fails_with_every_rule(self):
        r = run_cli("--layout", str(FIX / "before.layout.json"), "--srt", str(FIX / "before.srt"))
        self.assertEqual(r.returncode, 1)
        for needle in ("digits '0.500000'", "trailing-zero '0.50'", "exact-zero '0.000000'", "minus '-0.95",
                       "sci '1e-12'", "unit-space '0.5s'", "precision '0.5 → 0.75 → 1'", "precision 'c'",
                       "precision '1.28 / 1.277'", "spoken 'point five zero zero zero zero zero'",
                       "digits '1.277'"):
            self.assertIn(needle, r.stdout, needle)

    def test_after_passes(self):
        r = run_cli("--layout", str(FIX / "after.layout.json"), "--srt", str(FIX / "after.srt"))
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("0 warning(s)", r.stdout)

    def test_live_readouts_may_keep_fixed_decimals(self):
        cfg, fd = CN.settings(), CN.Findings()
        CN.check_static("∫ L dt = 0.00", "text", "readout", "screen", "t", cfg, fd, live=True)
        CN.check_static("c = 0.50", "text", "readout", "screen", "t", cfg, fd, live=True)
        self.assertEqual(fd.items, [])

    def test_math_items_ignore_exponents_and_fraction_shorthand(self):
        cfg, fd = CN.settings(), CN.Findings()
        CN.check_static(r"V(q)=\tfrac12\sqrt{m\kappa}\,q^2,\quad q_0=1.6", "math", "screen", "screen", "t", cfg, fd)
        self.assertEqual(fd.items, [])

    def test_signed_zero_is_an_error_even_in_a_live_readout(self):
        cfg, fd = CN.settings(), CN.Findings()
        CN.check_static("lowest value = −H = −0.00", "text", "readout", "screen", "t", cfg, fd, live=True)
        CN.check_static("lowest value = −H = +0.00", "text", "readout", "screen", "t2", cfg, fd, live=True)
        self.assertEqual([f["rule"] for f in fd.items], ["signed-zero", "signed-zero"])
        fd = CN.Findings()
        CN.check_static("x − 0.5 and t−0 and −H = +0.14", "text", "readout", "screen", "t", cfg, fd, live=True)
        self.assertEqual(fd.items, [])

    def test_fmt_never_signs_a_zero(self):
        self.assertEqual(fmt(-1e-17, decimals=2), "0.00")
        self.assertEqual(fmt(-1e-17, decimals=2, sign=True), "0.00")
        self.assertEqual(fmt(0.14, decimals=2, sign=True), "+0.14")
        self.assertEqual(fmt(-1.5, decimals=2, sign=True), "\u22121.50")
        self.assertEqual(fmt(0.0, sign=True), "0")

    def test_math_items_ignore_layout_lengths(self):
        """Table cells set with \\makebox[5.0em] or spaced with \\hspace{1.5cm}: the lengths are not on screen."""
        cfg, fd = CN.settings(), CN.Findings()
        CN.check_static(r"\makebox[2.4em][r]{$0.5$}\quad \makebox[5.0em][r]{$-0.88$}\hspace{1.5cm}\kern-0.3em x",
                        "math", "screen", "screen", "t", cfg, fd)
        self.assertEqual(fd.items, [])
        self.assertEqual([n["raw"] for n in CN.numbers_in(r"\makebox[5.0em]{$2.50$}", "math")], ["2.50"])


if __name__ == "__main__":
    unittest.main()
