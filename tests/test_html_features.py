"""Unit tests for the reader features of the explainer pages (tools/html_features.py, tools/build_explainer.py) and,
when Playwright, Chromium and a local KaTeX are available, the browser check (tools/check_html_features.js)
(python3 -m unittest)."""
import json
import os
import re
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
sys.path.insert(0, str(REPO / "tools" / "video"))

import html_features as HF  # noqa: E402
import lint_html  # noqa: E402
from check_design import contrast, hex_rgb  # noqa: E402

SOURCE = testenv.SOURCE_DIR / "explainer.html"           # the fixture source document, never the owner's


def light_vars() -> dict:
    css = (REPO / "templates" / "explainer" / "explainer.css").read_text(encoding="utf-8")
    root = css[css.index(":root {"):css.index("}", css.index(":root {"))]
    v = dict(re.findall(r"(--[\w-]+):\s*(#[0-9a-fA-F]{6})", root))
    v.update(HF.LIGHT_EXTRA)
    return v


class Contrast(unittest.TestCase):
    """WCAG 2.x contrast of text in both themes: body text, links, boxes, code, tables, citations, contents."""
    PAIRS = [("--text", "--bg"), ("--text-secondary", "--bg"), ("--heading", "--bg"), ("--accent", "--bg"),
             ("--definition-strong", "--definition-bg"), ("--text", "--definition-bg"),
             ("--insight-strong", "--insight-bg"), ("--text", "--insight-bg"), ("--code-text", "--code-bg"),
             ("--text", "--table-header-bg"), ("--text", "--row-stripe"), ("--text-secondary", "--sidebar-bg"),
             ("--accent", "--sidebar-bg"), ("--danger", "--bg"), ("--text", "--blockquote-bg"),
             ("--fig-ink", "--fig-bg"), ("--fig-muted", "--fig-bg")]

    def test_both_themes_meet_aa(self):
        light, dark = light_vars(), dict(light_vars(), **HF.DARK_VARS)
        for name, vs in (("light", light), ("dark", dark)):
            for fg, bg in self.PAIRS:
                with self.subTest(theme=name, pair=(fg, bg)):
                    self.assertGreaterEqual(contrast(hex_rgb(vs[fg]), hex_rgb(vs[bg])), 4.5, (vs[fg], vs[bg]))


class SvgTheme(unittest.TestCase):
    def test_light_keeps_colours_dark_maps_neutrals_and_keeps_hues(self):
        out = HF.theme_svg('<svg><rect fill="#ffffff"/><path style="fill: #000000; stroke: #1f77b4"/>'
                           '<line stroke="gray" style="stroke: #2dd4bf"/><text fill="#ef4444">x</text>'
                           '<text fill="#0f172a">q</text></svg>')
        self.assertIn('<rect fill="#ffffff" style="fill: color-mix(in srgb, #ffffff var(--fig-keep), var(--fig-bg))"',
                      out)                                             # the attribute stays as the fallback
        self.assertIn("fill: #000000; fill: color-mix(in srgb, #000000 var(--fig-keep), var(--fig-ink))", out)
        self.assertIn("stroke: #1f77b4; stroke: color-mix(in srgb, #1f77b4 var(--fig-mix), #ffffff)", out)
        self.assertIn("var(--fig-muted)); stroke: #2dd4bf; stroke: color-mix(in srgb, #2dd4bf", out)  # own style wins
        self.assertIn("fill: color-mix(in srgb, #ef4444 var(--fig-mix), #ffffff)", out)       # the hue stays
        self.assertIn("color-mix(in srgb, #0f172a var(--fig-keep), var(--fig-ink))", out)    # a slate grey is ink
        tint = HF.theme_svg('<rect fill="#f0fdf4"/>')                  # a pale green region: dark green in dark
        dark = re.search(r"color-mix\(in srgb, #f0fdf4 var\(--fig-keep\), (#[0-9a-f]{6})\)", tint).group(1)
        r, g, b = hex_rgb(dark)
        self.assertTrue(g > r and g > b and max(r, g, b) < 0.3, dark)
        self.assertNotIn("invert(", HF.css())

    def test_font_style_is_not_a_style_attribute(self):
        """A text label with a themed fill and font-style="italic": the colour goes to the style attribute, never
        into font-style (the defect of the earlier pattern: font-style="fill: color-mix(...); italic")."""
        fill = "fill: color-mix(in srgb, #64748b var(--fig-keep), var(--fig-muted))"
        out = HF.theme_svg('<svg><text x="5" fill="#64748b" font-style="italic">q</text>'
                           '<g font-size="11.5" fill="#64748b" font-style="italic"><text>a</text></g>'
                           '<text fill="#64748b" font-style="italic" style="font-weight: bold">v</text></svg>')
        self.assertIn(f'<text x="5" fill="#64748b" font-style="italic" style="{fill}">q</text>', out)
        self.assertIn(f'<g font-size="11.5" fill="#64748b" font-style="italic" style="{fill}">', out)
        self.assertIn(f'font-style="italic" style="{fill}; font-weight: bold">v</text>', out)
        self.assertEqual(re.findall(r'font-style="([^"]*)"', out), ["italic"] * 3)
        self.assertEqual(lint_html.lint_svg_attributes(out), [])

    def test_only_colour_properties_are_themed(self):
        out = HF.theme_svg('<rect style="background-color: #ffffff; fill: #000000"/>'
                           '<stop style="stop-color: #ffffff"/>')
        self.assertIn('style="background-color: #ffffff; fill: #000000; fill: color-mix(', out)   # no color: added
        self.assertIn("stop-color: #ffffff; stop-color: color-mix(in srgb, #ffffff var(--fig-keep), var(--fig-bg))",
                      out)

    def test_lint_flags_declarations_in_an_attribute(self):
        bad = ('<g fill="#64748b" font-style="fill: color-mix(in srgb, #64748b var(--fig-keep), var(--fig-muted)); '
               'italic">')
        found = lint_html.lint_svg_attributes("<svg>\n" + bad + "</g></svg>")
        self.assertEqual([(i["code"], i["line"]) for i in found], [("svg-attribute", 2)])
        self.assertIn("font-style", found[0]["message"])

    def test_light_theme_is_exact(self):
        light = dict(light_vars())
        self.assertEqual((light["--fig-keep"], light["--fig-mix"]), ("100%", "100%"))
        self.assertEqual(HF.DARK_VARS["--fig-keep"], "0%")

    def test_neutrals_take_the_theme_role_and_colours_keep_their_hue(self):
        for col, role in (("#0f172a", "ink"), ("#64748b", "muted"), ("#94a3b8", "muted"), ("#e2e8f0", "faint"),
                          ("#ffffff", "bg"), ("#f8fafc", "bg"), ("black", "ink"), ("#7f7f7f", "muted")):
            self.assertEqual(HF.themed(col), f"color-mix(in srgb, {col} var(--fig-keep), var(--fig-{role}))", col)
        for col in ("#1f77b4", "#8c564b", "#15803d", "#3b82f6", "#eff6ff", "#f0fdf4", "#fffbeb", "#dbeafe",
                    "#fef3c7"):
            self.assertNotRegex(HF.themed(col), r"var\(--fig-(ink|muted|faint|bg)\)", col)   # they keep their hue

    def test_dark_colours_meet_contrast_on_the_dark_background(self):
        def mix(c, p):
            r, g, b = (int(c[i:i + 2], 16) for i in (1, 3, 5))
            return "#%02x%02x%02x" % tuple(round(p * x + (1 - p) * 255) for x in (r, g, b))
        p = int(HF.DARK_VARS["--fig-mix"].rstrip("%")) / 100
        for c in ("#1e40af", "#92400e", "#15803d", "#b45309", "#1d4ed8", "#3b82f6", "#d62728", "#2ca02c"):
            with self.subTest(colour=c):
                self.assertGreaterEqual(contrast(hex_rgb(mix(c, p)), hex_rgb(HF.DARK_VARS["--fig-bg"])), 4.5)


class Builder(unittest.TestCase):
    def test_fixture_build_links_equations_and_has_the_features(self):
        tmp = Path(tempfile.mkdtemp(prefix="build-features-"))
        try:
            run = tmp / "run"
            shutil.copytree(REPO / "tests" / "fixtures" / "run", run)
            (run / "code" / "figures").mkdir(parents=True, exist_ok=True)       # normally drawn by the run's script
            (run / "code" / "figures" / "concept.svg").write_text(
                '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"><path d="M0 0L10 10" stroke="#000"/></svg>')
            r = subprocess.run([sys.executable, "tools/build_explainer.py", str(run)], cwd=REPO, capture_output=True,
                               text=True)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            html = (run / "explainer.html").read_text()
            anchors = re.findall(r'<span class="eq-anchor" id="eq-([\w-]+)"', html)
            self.assertTrue(anchors)
            refs = re.findall(r'<a class="eqref" href="#eq-([\w-]+)">\((\d+)\)</a>', html)
            self.assertTrue(refs)
            self.assertTrue(all(name in anchors for name, _ in refs))
            self.assertNotIn("[[eq:", html)
            self.assertIn('data-theme', html.split("</head>")[0])           # theme set before first paint
            for needle in ('class="theme-toggle"', 'aria-pressed', 'class="toc-toggle"', 'aria-controls="toc"',
                           '<nav class="toc" id="toc"', "prefers-reduced-motion", ":root[data-theme=\"dark\"]"):
                self.assertIn(needle, html)
            lint = subprocess.run([sys.executable, "tools/lint_html.py", str(run / "explainer.html"), "--strict"],
                                  cwd=REPO, capture_output=True, text=True)
            self.assertEqual(lint.returncode, 0, lint.stdout)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_a_matplotlib_figure_builds_and_lints(self):
        """A figure saved by plain plt.savefig(path, format="svg") builds under --strict: the build drops its RDF
        <metadata> (tags the lint does not know), and the page is the one its drawing alone gives."""
        svg = (REPO / "tests" / "fixtures" / "figures" / "matplotlib.svg").read_text(encoding="utf-8")
        drawing = svg[:svg.index("<metadata>")] + svg[svg.index("</metadata>") + len("</metadata>"):]
        pages = []
        with tempfile.TemporaryDirectory() as tmp:
            for i, figure in enumerate((svg, drawing)):
                run = Path(tmp) / f"run{i}"
                shutil.copytree(REPO / "tests" / "fixtures" / "run", run)
                (run / "code" / "figures").mkdir(parents=True, exist_ok=True)
                (run / "code" / "figures" / "concept.svg").write_text(figure, encoding="utf-8")
                r = subprocess.run([sys.executable, "tools/build_explainer.py", str(run), "--strict"], cwd=REPO,
                                   capture_output=True, text=True)
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)          # built, and the strict lint passes
                pages.append((run / "explainer.html").read_text(encoding="utf-8"))
        self.assertEqual(pages[0].split(), pages[1].split())


LEGACY_PAGE_TAIL = "\n<p>Text $a=b$ stays.</p>\n</article>\n"


def legacy_page() -> str:
    """A page injected the way pages were before the markers: the same four blocks, unmarked."""
    head = ('<!DOCTYPE html><html><head><meta charset="UTF-8"><style>\n  body { color: #111; }\n</style>\n</head>\n'
            '<body>\n<nav class="toc"><a href="#sec-a">1 A</a></nav>\n<article><section id="sec-a"><h2>1. A</h2>'
            + LEGACY_PAGE_TAIL + "</body>\n</html>\n")
    html = head.replace("</style>", HF.css() + "\n</style>", 1).replace("</head>", HF.HEAD_SCRIPT + "\n</head>", 1)
    html = re.sub(r"(<body[^>]*>)", r"\1\n" + HF.CONTROLS.replace("\\", "\\\\"), html, count=1)
    return html.replace("</body>", HF.BODY_SCRIPT + "\n</body>", 1)


class Reinject(unittest.TestCase):
    """reinject swaps the injected CSS and scripts for the current ones and keeps every other byte."""

    def test_legacy_page_gets_marked_blocks_and_keeps_its_content(self):
        old = legacy_page()
        new, how = HF.reinject(old)
        self.assertEqual(how, {"css": "legacy", "head": "legacy", "controls": "legacy", "body": "legacy"})
        for start, end in HF.MARK.values():
            self.assertEqual((new.count(start), new.count(end)), (1, 1))
        self.assertEqual(HF.outside_blocks(new), HF.outside_blocks(old))
        self.assertIn(LEGACY_PAGE_TAIL, new)
        again, how = HF.reinject(new)
        self.assertEqual((again, set(how.values())), (new, {"marked"}))      # current: nothing changes

    def test_old_blocks_are_replaced_by_the_current_ones(self):
        old = legacy_page().replace("/* Reader features (tools/html_features.py)",
                                    "/* Reader features (tools/html_features.py) .stale-css-sentinel {}", 1)
        old = old.replace("})();\n</script>", "})();\n/* stale-body-sentinel */\n</script>", 1)
        new, how = HF.reinject(old)
        self.assertEqual(set(how.values()), {"legacy"})
        self.assertNotIn("stale-css-sentinel", new)
        self.assertNotIn("stale-body-sentinel", new)
        for block in HF.blocks().values():
            self.assertIn(block, new)
        fresh = HF.inject("<html><head><style>\n</style>\n</head>\n<body>\n<nav class=\"toc\"></nav>\n</body></html>")
        self.assertEqual({v[2] for v in HF.find_blocks(fresh).values()}, {"marked"})   # new pages carry the markers

    def test_a_page_without_the_features_is_refused(self):
        with self.assertRaises(ValueError):
            HF.reinject("<html><head><style></style></head><body><p>x</p></body></html>")
        doubled = legacy_page().replace("</body>", HF.BODY_SCRIPT + "\n</body>")
        with self.assertRaises(ValueError):
            HF.reinject(doubled)

    def test_command_line(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            page = tmp / "page.html"
            page.write_text(legacy_page(), encoding="utf-8")
            cli = [sys.executable, str(REPO / "tools" / "html_features.py"), "reinject", str(page)]
            r = subprocess.run(cli, capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("dry run: nothing written", r.stdout)
            self.assertEqual(page.read_text(encoding="utf-8"), legacy_page())
            r = subprocess.run(cli + ["-o", str(tmp / "out.html")], capture_output=True, text=True)
            self.assertIn("reader-features:css", (tmp / "out.html").read_text(encoding="utf-8"))
            self.assertEqual(page.read_text(encoding="utf-8"), legacy_page())
            r = subprocess.run(cli + ["--write"], capture_output=True, text=True)
            self.assertEqual(page.read_text(encoding="utf-8"), (tmp / "out.html").read_text(encoding="utf-8"))
            self.assertIn("already current", subprocess.run(cli, capture_output=True, text=True).stdout)
            (tmp / "plain.html").write_text("<html><body>x</body></html>", encoding="utf-8")
            r = subprocess.run(cli[:-1] + [str(tmp / "plain.html")], capture_output=True, text=True)
            self.assertEqual(r.returncode, 1)
        finally:
            shutil.rmtree(tmp)

    def test_label_size_agrees_with_the_check(self):
        """The page scales figure labels up to the size check_html.js measures against: the two numbers must agree."""
        page = re.search(r"\bMIN_LABEL = (\d+(?:\.\d+)?)", HF.BODY_SCRIPT)
        check = re.search(r"\bMIN_LABEL_PX = (\d+(?:\.\d+)?)",
                          (REPO / "tools" / "check_html.js").read_text(encoding="utf-8"))
        self.assertTrue(page and check)
        self.assertEqual(float(page.group(1)), float(check.group(1)))


KATEX = os.environ.get("KATEX_DIST") or str(REPO / "node_modules" / "katex" / "dist")


@unittest.skipUnless(shutil.which("node") and Path(KATEX, "katex.min.js").exists(),
                     "needs node, Playwright with Chromium and a local KaTeX ($KATEX_DIST)")
class Browser(unittest.TestCase):
    checked = None                      # check_html_features.js on the fixture source, run once for the tests below

    def features(self) -> str:
        """The output of check_html_features.js on the fixture source with the current blocks (reinject)."""
        if Browser.checked is None:
            tmp = Path(tempfile.mkdtemp())
            try:
                page = tmp / "explainer.html"
                r = subprocess.run([sys.executable, "tools/html_features.py", "reinject", str(SOURCE), "-o", str(page)],
                                   cwd=REPO, capture_output=True, text=True)
                self.assertEqual(r.returncode, 0, r.stderr)
                Browser.checked = subprocess.run(["node", "tools/check_html_features.js", str(page), "--katex-dist",
                                                  KATEX], cwd=REPO, capture_output=True, text=True, timeout=900)
            finally:
                shutil.rmtree(tmp, ignore_errors=True)
        r = Browser.checked
        if r.returncode == 3:
            self.skipTest(r.stderr.strip()[:200])
        self.assertEqual(r.returncode, 0, r.stdout[-3000:])
        return r.stdout

    def test_reader_features_in_a_browser(self):
        out = self.features()
        for needle in ("Back returns to the reading position", "phone: Tab stays inside the open drawer",
                       "no horizontal overflow at 360 px (dark)", "KaTeX renders without errors"):
            self.assertIn("ok    " + needle, out)

    def test_equation_preview_in_a_browser(self):
        """Pointing at an equation reference, or reaching it with Tab, shows that equation beside the link; Esc hides
        it; at 390 px in dark mode it stays on screen and readable; a tap still jumps. reinject brings it to a page
        injected earlier."""
        out = self.features()
        for needle in ("pointing at a reference shows its equation", "moving the pointer away hides it",
                       "Tab to a reference shows it, Esc hides it", "at 390 px, dark", "a tap jumps to the equation"):
            self.assertRegex(out, r"(?m)^ok +equation preview\b.*" + re.escape(needle))

    def test_phone_reading_measurements(self):
        """check_html.js measures equation numbers off screen, figure labels and numbers broken in table cells; the
        reader features bring all three to zero (a page without them shows each problem)."""
        css = (REPO / "templates" / "explainer" / "explainer.css").read_text(encoding="utf-8")
        long_sum = "+".join(f"a_{{{i}}}" for i in range(1, 41))
        body = ('<nav class="toc"><a href="#sec-a">1. A</a></nav><article><section id="sec-a"><h2>1. A</h2>'
                '<div class="equation-block"><span class="eq-anchor" id="eq-1"></span>'
                f'$${long_sum}=b \\tag{{1}}$$</div>'
                '<figure><svg width="680" height="200" viewBox="0 0 680 200"><rect width="680" height="200" fill="#ffffff"/>'
                '<text x="10" y="100" font-size="11">a label</text></svg><figcaption>Figure 1. A figure.</figcaption>'
                '</figure><table><tr><th>Case</th><th>Value</th></tr><tr><td>A long description of the case that takes '
                'the room of the row</td><td style="width: 2em">0.516832</td></tr></table></section></article>')
        page = ('<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8">'
                '<meta name="viewport" content="width=device-width, initial-scale=1.0">'
                '<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.css">'
                '<script defer src="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.js"></script>'
                '<script defer src="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/contrib/auto-render.min.js" '
                'onload="renderMathInElement(document.body, {delimiters: [{left: \'$$\', right: \'$$\', display: true}]})">'
                '</script><style>\n' + css + '\n  figure svg { max-width: 100%; height: auto; }\n</style></head><body>'
                + body + '</body></html>')
        tmp = Path(tempfile.mkdtemp())
        try:
            results = {}
            for name, html in (("plain", page), ("features", HF.inject(page))):
                (tmp / f"{name}.html").write_text(html, encoding="utf-8")
                r = subprocess.run(["node", "tools/check_html.js", str(tmp / f"{name}.html"), "--katex-dist", KATEX,
                                    "--json", str(tmp / f"{name}.json")], cwd=REPO, capture_output=True, text=True,
                                   timeout=600)
                if r.returncode == 3:
                    self.skipTest(r.stderr.strip()[:200])
                rep = json.loads((tmp / f"{name}.json").read_text(encoding="utf-8"))["widths"]
                results[name] = (len(rep["390"]["tagsHidden"]), min(f["minPx"] for f in rep["390"]["figureText"]),
                                 len(rep["1400"]["brokenNumbers"]) + len(rep["390"]["brokenNumbers"]))
            hidden, label, broken = results["plain"]
            self.assertEqual(hidden, 1)
            self.assertLess(label, 9)
            self.assertGreater(broken, 0)
            self.assertEqual(results["features"][0], 0)
            self.assertGreaterEqual(results["features"][1], 9)
            self.assertEqual(results["features"][2], 0)
        finally:
            shutil.rmtree(tmp)


if __name__ == "__main__":
    unittest.main()
