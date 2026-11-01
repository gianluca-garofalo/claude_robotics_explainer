#!/usr/bin/env python3
"""Reader features of the explainer pages: a dark-mode switch, equation links that the Back button undoes, a
collapsible table of contents (a drawer on phones), and on phones equation numbers that stay on screen, figure labels
that keep a readable size and numbers in tables that do not break; added by tools/build_explainer.py. Small inline
CSS and JavaScript only, no dependency; with JavaScript off the page stays light, the table of contents stays visible
and every link still jumps.

  python3 tools/html_features.py reinject PAGE.html            # dry run: which blocks would be replaced
  python3 tools/html_features.py reinject PAGE.html --write    # replace them in place
  python3 tools/html_features.py reinject PAGE.html -o OUT.html

reinject swaps the injected CSS and scripts of an existing page for the current ones and leaves every other byte
(text, equations, figures, the page's own CSS) as it is. It finds the blocks by their markers, or, in pages made
before the markers, by their first lines.

Colours: the light set is the house style; the dark set is the channel's video palette (background #0f172a, a lighter
surface for cards and the sidebar, text #e2e8f0, secondary #94a3b8, borders #334155, and the semantic colours
#2dd4bf, #fbbf24, #818cf8, #ef4444 with lighter tints where text needs WCAG AA contrast). Print is always light.
"""
from __future__ import annotations

import colorsys
import re

DARK_VARS = {
    "--bg": "#0f172a", "--bg-secondary": "#1e293b", "--text": "#e2e8f0", "--text-secondary": "#94a3b8",
    "--heading": "#f1f5f9", "--accent": "#818cf8", "--accent-light": "#1e2446", "--accent-dim": "#1e2446",
    "--border": "#334155", "--code-bg": "#1e293b", "--code-text": "#e2e8f0", "--table-header-bg": "#1e293b",
    "--row-stripe": "#131d33", "--sidebar-bg": "#131d33", "--definition-bg": "#0d2b2c", "--definition-border": "#2dd4bf",
    "--definition-strong": "#5eead4", "--insight-bg": "#2b2410", "--insight-border": "#fbbf24",
    "--insight-strong": "#fcd34d", "--blockquote-bg": "#1e293b", "--danger": "#f87171",
    "--fig-ink": "#e2e8f0", "--fig-muted": "#94a3b8", "--fig-faint": "#334155", "--fig-bg": "#0f172a",
    "--highlight": "#3b3417", "--fig-mix": "65%", "--fig-keep": "0%",
}
LIGHT_EXTRA = {"--accent": "#2563eb",            # links: #3b82f6 gave 3.7:1 on white (WCAG AA needs 4.5:1)
               "--fig-ink": "#1e293b", "--fig-muted": "#64748b", "--fig-faint": "#e2e8f0", "--fig-bg": "#ffffff",
               "--highlight": "#fef3c7", "--fig-mix": "100%", "--fig-keep": "100%"}


def _vars(d: dict) -> str:
    return " ".join(f"{k}: {v};" for k, v in d.items())


CSS = """
  /* Reader features (tools/html_features.py): dark mode, equation links, collapsible contents */
  :root { %(light)s }
  :root[data-theme="dark"] { %(dark)s color-scheme: dark; }
  :root[data-theme="dark"] .algorithm { box-shadow: 0 0 0 1px var(--border); }
  :root[data-theme="dark"] img { opacity: 0.92; }
  figure svg { color: var(--fig-ink); }
  figure svg:not([fill]) { fill: var(--fig-ink); }
  .reader-controls { position: fixed; top: 0.6rem; right: 0.7rem; z-index: 120; display: flex; gap: 0.4rem; }
  .reader-controls button, .toc-toggle {
    font: inherit; font-size: 1.05rem; line-height: 1; min-width: 2.4rem; min-height: 2.4rem; padding: 0.35rem;
    color: var(--text); background: var(--bg-secondary); border: 1px solid var(--border); border-radius: 8px;
    cursor: pointer; }
  .reader-controls button:focus-visible, .toc-toggle:focus-visible, nav.toc a:focus-visible, a.eqref:focus-visible {
    outline: 3px solid var(--accent); outline-offset: 2px; }
  .toc-toggle { position: fixed; top: 0.6rem; left: 0.7rem; z-index: 130; display: none; }
  html.js .toc-toggle { display: inline-block; }
  html.js nav.toc { padding-top: 3.4rem; }
  html.js.toc-collapsed nav.toc { display: none; }
  html.js.toc-collapsed article { margin-left: auto; margin-right: auto; }
  nav.toc a.current { color: var(--accent); font-weight: 700; }
  .toc-backdrop { display: none; }
  a.eqref { white-space: nowrap; }
  .eq-anchor { display: block; position: relative; height: 0; scroll-margin-top: 4.5rem; }
  [id] { scroll-margin-top: 4rem; }
  .eq-anchor:target + .katex-display, .eq-anchor:target + p .katex-display, .equation-block:target {
    animation: eq-flash 2.4s ease-out; border-radius: 6px; }
  @keyframes eq-flash { 0%%, 30%% { background: var(--highlight); } 100%% { background: transparent; } }
  .eq-back { position: fixed; bottom: 1rem; right: 1rem; z-index: 120; padding: 0.5rem 0.8rem; font-size: 0.9rem;
    color: var(--text); background: var(--bg-secondary); border: 1px solid var(--border); border-radius: 999px;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.18); cursor: pointer; }
  .eq-back[hidden] { display: none; }
  @media (max-width: 800px) {
    html.js nav.toc { position: fixed; top: 0; left: 0; bottom: 0; width: min(85vw, 320px); height: 100%%;
      transform: translateX(-105%%); transition: transform 0.25s ease; border-right: 1px solid var(--border);
      border-bottom: none; z-index: 125; visibility: hidden; }
    html.js.toc-open nav.toc { transform: none; visibility: visible; }
    html.js.toc-collapsed nav.toc { display: block; }
    html.js .toc-backdrop { position: fixed; inset: 0; z-index: 124; background: rgba(2, 6, 23, 0.55); }
    html.js.toc-open .toc-backdrop { display: block; }
    html.js article { padding-top: 3.4rem; }
    /* nothing wider than the screen: long formulas, tables and code scroll in their own box */
    .katex-display, .equation-block, table, pre { max-width: 100%% !important; overflow-x: auto !important;
      overflow-y: hidden !important; position: relative; }
    table { display: block; }
    .katex-display > .katex > .katex-html > .tag { position: static; display: inline-block; padding-left: 1em; }
    /* a numbered formula scrolls inside its display and its number stays on screen, on the line below it */
    .katex-display:has(.tag) { overflow: visible !important; padding-bottom: 1.6em; }
    .katex-display:has(.tag) > .katex { overflow-x: auto; overflow-y: hidden; }
    .katex-display:has(.tag) > .katex > .katex-html { position: static !important; }
    .katex-display:has(.tag) > .katex > .katex-html > .tag { position: absolute !important; right: 0; bottom: 0;
      padding-left: 0 !important; }
    .katex-display:has(.tag) > .katex > .katex-html > .tag > .strut { display: none; }   /* only the number's height */
    .katex .katex-mathml { position: absolute; clip: rect(1px, 1px, 1px, 1px); width: 1px; height: 1px; overflow: hidden; }
    img, svg, video { max-width: 100%%; height: auto; }
  }
  .nb { white-space: nowrap; }      /* a number in a table cell never breaks across lines (the body script) */
  /* the body script marks a numbered formula too wide for its number beside it: the number goes on the line below,
     and a table that no longer fits its column scrolls in its own box instead of widening the page */
  .katex-display.tag-below { position: relative !important; overflow: visible !important; padding-bottom: 1.6em; }
  .katex-display.tag-below > .katex { overflow-x: auto; overflow-y: hidden; }
  .katex-display.tag-below > .katex > .katex-html { position: static !important; }
  .katex-display.tag-below > .katex > .katex-html > .tag { position: absolute !important; right: 0; bottom: 0;
    padding-left: 0 !important; }
  .katex-display.tag-below > .katex > .katex-html > .tag > .strut { display: none; }
  table.tbl-scroll { display: block; overflow-x: auto; }
  figure.fig-scroll { overflow-x: auto; overflow-y: hidden; }   /* labels kept at 9 px or more: the figure scrolls */
  @media (max-width: 380px) { html { font-size: 15px; } }   /* long inline formulas still fit a 360 px phone */
  @media (prefers-reduced-motion: reduce) {
    html { scroll-behavior: auto; }
    html.js nav.toc { transition: none; }
    .eq-anchor:target + .katex-display, .eq-anchor:target + p .katex-display, .equation-block:target {
      animation: none; background: var(--highlight); }
  }
  @media print {
    :root, :root[data-theme="dark"] { %(light_print)s color-scheme: light; }
    .reader-controls, .toc-toggle, .toc-backdrop, .eq-back { display: none !important; }
  }
"""

HEAD_SCRIPT = """<script>
/* Theme before first paint (no flash): the stored choice, else the system setting; light without JavaScript. */
(function () {
  var t = null;
  try { t = localStorage.getItem('ra-theme'); } catch (e) {}
  if (t !== 'dark' && t !== 'light') {
    t = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  }
  document.documentElement.setAttribute('data-theme', t);
  document.documentElement.classList.add('js');
  try { if (localStorage.getItem('ra-toc') === 'collapsed' && window.innerWidth > 800) {
    document.documentElement.classList.add('toc-collapsed'); } } catch (e) {}
})();
</script>"""

CONTROLS = """<button type="button" class="toc-toggle" aria-controls="toc" aria-expanded="true" aria-label="Contents">&#9776;</button>
<div class="toc-backdrop" hidden></div>
<div class="reader-controls"><button type="button" class="theme-toggle" aria-pressed="false" aria-label="Dark mode" title="Dark mode">&#9790;</button></div>
<button type="button" class="eq-back" hidden>&#8617; back to text</button>"""

BODY_SCRIPT = """<script>
(function () {
  var root = document.documentElement, store = function (k, v) { try { localStorage.setItem(k, v); } catch (e) {} };
  var themeBtn = document.querySelector('.theme-toggle');
  function paintTheme() {
    var dark = root.getAttribute('data-theme') === 'dark';
    themeBtn.setAttribute('aria-pressed', dark ? 'true' : 'false');
    themeBtn.innerHTML = dark ? '&#9728;' : '&#9790;';
    themeBtn.title = dark ? 'Light mode' : 'Dark mode';
  }
  themeBtn.addEventListener('click', function () {
    var next = root.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
    root.setAttribute('data-theme', next); store('ra-theme', next); paintTheme();
  });
  paintTheme();

  var nav = document.getElementById('toc'), btn = document.querySelector('.toc-toggle'),
      backdrop = document.querySelector('.toc-backdrop'), narrow = window.matchMedia('(max-width: 800px)');
  function links() { return nav ? nav.querySelectorAll('a') : []; }
  function setOpen(open, refocus) {
    root.classList.toggle('toc-open', open);
    btn.setAttribute('aria-expanded', open ? 'true' : 'false');
    if (backdrop) backdrop.hidden = !open;
    if (open) { var l = links(); if (l.length) l[0].focus(); } else if (refocus) btn.focus();
  }
  function syncState() {
    if (narrow.matches) { root.classList.remove('toc-collapsed'); setOpen(false, false); }
    else { root.classList.remove('toc-open'); if (backdrop) backdrop.hidden = true;
      btn.setAttribute('aria-expanded', root.classList.contains('toc-collapsed') ? 'false' : 'true'); }
  }
  if (nav && btn) {
    btn.addEventListener('click', function () {
      if (narrow.matches) { setOpen(!root.classList.contains('toc-open'), true); return; }
      var collapsed = root.classList.toggle('toc-collapsed');
      btn.setAttribute('aria-expanded', collapsed ? 'false' : 'true');
      store('ra-toc', collapsed ? 'collapsed' : 'open');
    });
    if (backdrop) backdrop.addEventListener('click', function () { setOpen(false, true); });
    nav.addEventListener('click', function (e) { if (e.target.closest('a') && narrow.matches) setOpen(false, false); });
    document.addEventListener('keydown', function (e) {
      if (!root.classList.contains('toc-open')) return;
      if (e.key === 'Escape') { setOpen(false, true); return; }
      if (e.key !== 'Tab') return;
      var ring = [btn].concat([].slice.call(links())), i = ring.indexOf(document.activeElement);
      e.preventDefault();                                   // focus stays in the drawer while it is open
      ring[(i < 0 ? 0 : i + (e.shiftKey ? ring.length - 1 : 1)) % ring.length].focus();
    });
    (narrow.addEventListener ? narrow.addEventListener('change', syncState) : narrow.addListener(syncState));
    syncState();
    if ('IntersectionObserver' in window) {
      var byId = {}; links().forEach(function (a) { byId[a.getAttribute('href').slice(1)] = a; });
      var current = null, io = new IntersectionObserver(function (entries) {
        entries.forEach(function (en) {
          if (!en.isIntersecting) return;
          var a = byId[en.target.id]; if (!a || a === current) return;
          if (current) { current.classList.remove('current'); current.removeAttribute('aria-current'); }
          current = a; a.classList.add('current'); a.setAttribute('aria-current', 'true');
        });
      }, { rootMargin: '0px 0px -75% 0px' });
      Object.keys(byId).forEach(function (id) { var el = document.getElementById(id); if (el) io.observe(el); });
    }
  }

  var back = document.querySelector('.eq-back'), jumpY = null;
  document.addEventListener('click', function (e) {
    var a = e.target.closest && e.target.closest('a[href^="#"]');
    if (!a) return;
    /* remember the reading position in the current history entry: Back restores it exactly */
    try { var st = history.state && typeof history.state === 'object' ? history.state : {};
      st.raY = window.scrollY; history.replaceState(st, ''); } catch (err) {}
    if (a.classList.contains('eqref') && back) setTimeout(function () { jumpY = window.scrollY; back.hidden = false; }, 450);
  });
  window.addEventListener('popstate', function (e) {
    if (e.state && typeof e.state.raY === 'number') {
      var y = e.state.raY;
      window.scrollTo({ top: y, behavior: 'instant' });
      setTimeout(function () { if (Math.abs(window.scrollY - y) > 2) window.scrollTo({ top: y, behavior: 'instant' }); }, 60);
    }
  });
  if (back) {
    back.addEventListener('click', function () { back.hidden = true; jumpY = null; history.back(); });
    window.addEventListener('scroll', function () {
      if (jumpY !== null && Math.abs(window.scrollY - jumpY) > 1.5 * window.innerHeight) { back.hidden = true; jumpY = null; }
    }, { passive: true });
    window.addEventListener('popstate', function () { back.hidden = true; jumpY = null; });
  }

  /* After KaTeX has rendered (deferred scripts run before DOMContentLoaded): numbers in table cells never break
     across lines, a figure keeps its labels at MIN_LABEL px or more (scrolling sideways if it must), a numbered
     formula too wide for its number puts the number on the line below, and a table too wide for its column scrolls. */
  var MIN_LABEL = 9, NUM = /[−+-]?[0-9]+(?:[.,][0-9]+)+(?:[eE][−+-]?[0-9]+)?|[0-9]{4,}/g;
  function keepNumbers() {
    [].forEach.call(document.querySelectorAll('td, th'), function (cell) {
      var tw = document.createTreeWalker(cell, NodeFilter.SHOW_TEXT), found = [], n;
      while ((n = tw.nextNode())) {
        if (n.nodeValue.indexOf('$') >= 0 || n.parentElement.closest('.katex, .nb, code, pre')) continue;
        NUM.lastIndex = 0;
        if (NUM.test(n.nodeValue)) found.push(n);
      }
      found.forEach(function (t) {
        var s = t.nodeValue, frag = document.createDocumentFragment(), last = 0, m;
        NUM.lastIndex = 0;
        while ((m = NUM.exec(s))) {
          if (m.index > last) frag.appendChild(document.createTextNode(s.slice(last, m.index)));
          var sp = document.createElement('span'); sp.className = 'nb'; sp.textContent = m[0]; frag.appendChild(sp);
          last = m.index + m[0].length;
        }
        if (last < s.length) frag.appendChild(document.createTextNode(s.slice(last)));
        t.parentNode.replaceChild(frag, t);
      });
    });
  }
  function fitFigures() {
    [].forEach.call(document.querySelectorAll('figure svg'), function (svg) {
      if (svg.parentElement.closest('svg')) return;
      var fig = svg.closest('figure'), vb = svg.viewBox && svg.viewBox.baseVal, small = Infinity;
      svg.style.minWidth = ''; fig.classList.remove('fig-scroll');
      if (!vb || !vb.width) return;
      [].forEach.call(svg.querySelectorAll('text'), function (t) {
        var px = parseFloat(getComputedStyle(t).fontSize); if (px > 0 && px < small) small = px; });
      if (small === Infinity) return;
      var wa = (svg.getAttribute('width') || '').trim(),
          natural = /^[0-9]+([.][0-9]+)?(px)?$/.test(wa) ? parseFloat(wa) : vb.width,
          need = Math.min(natural, Math.ceil(vb.width * MIN_LABEL / small));
      if (svg.getBoundingClientRect().width < need - 0.5) {
        svg.style.minWidth = need + 'px'; fig.classList.add('fig-scroll');
      }
    });
  }
  function fitTags() {                 /* wider screens: a number that would touch its formula goes below it */
    [].forEach.call(document.querySelectorAll('.katex-display'), function (d) {
      var tag = d.querySelector('.katex-html > .tag'), right = -Infinity, left;
      d.classList.remove('tag-below');
      if (!tag || narrow.matches) return;
      left = tag.getBoundingClientRect().left + (parseFloat(getComputedStyle(tag).paddingLeft) || 0);
      [].forEach.call(d.querySelectorAll('.katex-html > .base'), function (b) {
        right = Math.max(right, b.getBoundingClientRect().right); });
      if (right > left - 4) d.classList.add('tag-below');
    });
  }
  function fitTables() {
    [].forEach.call(document.querySelectorAll('table'), function (t) {
      t.classList.remove('tbl-scroll');
      if (t.getBoundingClientRect().width > t.parentElement.clientWidth + 1) t.classList.add('tbl-scroll');
    });
  }
  function fitAll() { fitTags(); fitTables(); fitFigures(); }
  function afterRender() { keepNumbers(); fitAll(); }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', afterRender); else afterRender();
  window.addEventListener('load', fitAll);                   /* the math fonts change the widths once they arrive */
  if (document.fonts && document.fonts.ready) document.fonts.ready.then(fitAll);
  var resized = null;
  window.addEventListener('resize', function () { clearTimeout(resized); resized = setTimeout(fitAll, 150); });
})();
</script>"""


def css() -> str:
    light_print = _vars({"--bg": "#ffffff", "--bg-secondary": "#f7f8fa", "--text": "#1e293b",
                         "--text-secondary": "#64748b", "--heading": "#0f172a", "--accent": "#2563eb",
                         "--accent-light": "#eff6ff", "--accent-dim": "#eff6ff", "--border": "#e2e8f0",
                         "--code-bg": "#f1f5f9", "--code-text": "#0f172a", "--table-header-bg": "#f1f5f9",
                         "--row-stripe": "#f8fafc", "--sidebar-bg": "#f8fafc", "--definition-bg": "#f0fdf4",
                         "--definition-border": "#22c55e", "--definition-strong": "#15803d", "--insight-bg": "#fffbeb",
                         "--insight-border": "#f59e0b", "--insight-strong": "#b45309", "--blockquote-bg": "#f8fafc",
                         "--danger": "#b91c1c", **LIGHT_EXTRA})
    return CSS % {"light": _vars(LIGHT_EXTRA), "dark": _vars(DARK_VARS), "light_print": light_print}


# --------------------------------------------------------------------------- SVG figures in both themes
NAMED = {"black": "ink", "white": "bg", "gray": "muted", "grey": "muted", "darkgray": "muted", "darkgrey": "muted",
         "dimgray": "muted", "dimgrey": "muted", "lightgray": "faint", "lightgrey": "faint", "silver": "faint",
         "gainsboro": "faint"}
ROLE = {"ink": "var(--fig-ink)", "muted": "var(--fig-muted)", "faint": "var(--fig-faint)", "bg": "var(--fig-bg)"}


def _rgb(c: str):
    c = c.strip().lower()
    m = re.fullmatch(r"#([0-9a-f]{3}|[0-9a-f]{6})", c)
    if m:
        h = m.group(1)
        h = "".join(ch * 2 for ch in h) if len(h) == 3 else h
        return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
    r_ = re.fullmatch(r"rgb\((\d+),\s*(\d+),\s*(\d+)\)", c)
    return tuple(int(x) for x in r_.groups()) if r_ else None


def _lum(rgb) -> float:
    return (0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2]) / 255


def _neutral(col: str) -> str | None:
    """'ink', 'muted', 'faint' or 'bg' for a neutral colour, else None (a colour keeps its meaning). Neutral: a named
    grey, equal channels, or the low-chroma greys of UI palettes (slate, zinc, ...: channel spread up to 48); in the
    pale range a small spread can be a tint (a shaded region), told apart from a light grey by its saturation."""
    c = col.strip().lower()
    if c in NAMED:
        return NAMED[c]
    rgb = _rgb(c)
    if rgb is None:
        return None
    spread = max(rgb) - min(rgb)
    if spread > 12:
        if _lum(rgb) > 0.85:
            if colorsys.rgb_to_hls(*(x / 255 for x in rgb))[2] > 0.5:
                return None                            # a pale tint: #f0fdf4, #eff6ff (slate-200 #e2e8f0 is grey)
        elif spread > 48:
            return None
    v = sum(rgb) / 3
    return "ink" if v < 80 else "muted" if v < 185 else "faint" if v < 245 else "bg"


def themed(val: str) -> str | None:
    """The theme-aware value of a fill or stroke colour, or None to leave it alone. The light theme keeps the exact
    colour (--fig-keep and --fig-mix are 100 %); in the dark theme neutrals take the theme's ink, muted, faint or
    background, a colour keeps its hue and is lightened (more contrast on the dark background), and a pale tint becomes
    a dark tint of the same hue."""
    v = val.strip()
    role = _neutral(v)
    if role:
        return f"color-mix(in srgb, {v} var(--fig-keep), {ROLE[role]})"
    rgb = _rgb(v)
    if rgb is None:
        return None
    if _lum(rgb) > 0.85:
        h, _, sat = colorsys.rgb_to_hls(*(x / 255 for x in rgb))
        dark = "#" + "".join(f"{round(x * 255):02x}" for x in colorsys.hls_to_rgb(h, 0.14, min(sat, 0.45)))
        return f"color-mix(in srgb, {v} var(--fig-keep), {dark})"
    return f"color-mix(in srgb, {v} var(--fig-mix), #ffffff)"


# The style attribute itself, never the tail of another attribute (font-style="italic" is not a style attribute), and
# the colour properties inside it, never the tail of another property (background-color, flood-color).
STYLE_ATTR = re.compile(r'(?<=\s)style="([^"]*)"')
STYLE_DECL = re.compile(r"(?<![\w-])(fill|stroke|color|stop-color)\s*:\s*([#\w(), ]+?)(?=;|$)")


def theme_svg(svg: str) -> str:
    """Strokes, fills and text of an inline SVG follow the theme (themed(): the light theme keeps every colour exactly,
    the dark theme maps neutrals to its ink and background and keeps the hue of colours). The original value stays in
    front as the fallback for browsers without color-mix(). No blanket invert: it would break the semantic colours."""
    def style_decl(m):
        prop, val = m.group(1), m.group(2)
        new = themed(val)
        return f"{prop}: {val}; {prop}: {new}" if new else m.group(0)

    def fix_style(m):
        return 'style="' + STYLE_DECL.sub(style_decl, m.group(1)) + '"'

    def per_tag(m):
        tag, extra = m.group(0), []

        def fix_attr(a):                # the attribute stays: it is the fallback without color-mix()
            new = themed(a.group(2))
            if new:
                extra.append(f"{a.group(1)}: {new}")
            return a.group(0)
        tag = re.sub(r'\s(fill|stroke)="([^"]+)"', fix_attr, tag)
        tag = STYLE_ATTR.sub(fix_style, tag)
        if extra:                       # presentation attributes yield to the element's own style declarations
            if STYLE_ATTR.search(tag):
                tag = STYLE_ATTR.sub(lambda s_: 'style="' + "; ".join(extra + [s_.group(1)]) + '"', tag, count=1)
            else:
                end = -2 if tag.endswith("/>") else -1
                tag = tag[:end].rstrip() + f' style="{"; ".join(extra)}"' + tag[end:]
        return tag
    return re.sub(r"<(?!/)[a-zA-Z][^<>]*?/?>", per_tag, svg)


MARK = {"css": ("/* reader-features:css */", "/* /reader-features:css */"),
        "head": ("<!-- reader-features:head -->", "<!-- /reader-features:head -->"),
        "controls": ("<!-- reader-features:controls -->", "<!-- /reader-features:controls -->"),
        "body": ("<!-- reader-features:body -->", "<!-- /reader-features:body -->")}
# the same blocks in pages injected before the markers existed
LEGACY = {"css": re.compile(r"(?<=\n)  /\* Reader features \(tools/html_features\.py\).*?\n(?=\n</style>)", re.S),
          "head": re.compile(r"<script>\n/\* Theme before first paint.*?</script>", re.S),
          "controls": re.compile(r'<button type="button" class="toc-toggle".*?back to text</button>', re.S),
          "body": re.compile(r"<script>\n\(function \(\) \{\n  var root = document\.documentElement, store.*?</script>",
                             re.S)}


def blocks() -> dict:
    """The four injected blocks, each between its markers."""
    raw = {"css": css(), "head": HEAD_SCRIPT, "controls": CONTROLS, "body": BODY_SCRIPT}
    return {k: f"{MARK[k][0]}\n{v.strip(chr(10))}\n{MARK[k][1]}" for k, v in raw.items()}


def inject(html: str) -> str:
    """Add the feature CSS, the head script, the controls and the body script to a page with <nav class="toc">."""
    b = blocks()
    html = html.replace("</style>", b["css"] + "\n</style>", 1)
    html = html.replace("</head>", b["head"] + "\n</head>", 1)
    html = re.sub(r'<nav class="toc"(?![^>]*\bid=)', '<nav class="toc" id="toc" aria-label="Contents"', html, count=1)
    m = re.search(r"<body[^>]*>", html)
    if m:
        html = html[:m.end()] + "\n" + b["controls"] + html[m.end():]
    html = html.replace("</body>", b["body"] + "\n</body>", 1)
    return html


def find_blocks(html: str) -> dict:
    """{block: (start, end, "marked" | "legacy")} of the injected blocks of a page; ValueError if one is missing or
    appears twice."""
    found = {}
    for k, (start, end) in MARK.items():
        hits, kind = list(re.finditer(re.escape(start) + r".*?" + re.escape(end), html, re.S)), "marked"
        if not hits:
            hits, kind = list(LEGACY[k].finditer(html)), "legacy"
        if len(hits) != 1:
            raise ValueError(f"the reader-features {k} block appears {len(hits)} times (expected once): is this a page "
                             "made by tools/build_explainer.py?")
        found[k] = (hits[0].start(), hits[0].end(), kind)
    return found


def reinject(html: str) -> tuple[str, dict]:
    """The page with its injected CSS and scripts replaced by the current ones; every other byte is kept. Returns
    (html, {block: "marked" | "legacy"})."""
    new, found = blocks(), find_blocks(html)
    out, last = [], 0
    for k, (a, b, kind) in sorted(found.items(), key=lambda kv: kv[1][0]):
        out += [html[last:a], new[k]]
        last = b
    out.append(html[last:])
    return "".join(out), {k: v[2] for k, v in found.items()}


def outside_blocks(html: str) -> str:
    """The page without its injected blocks: what reinject must leave unchanged."""
    found = find_blocks(html)
    out, last = [], 0
    for a, b, _ in sorted(found.values()):
        out.append(html[last:a])
        last = b
    return "".join(out + [html[last:]])


def main(argv=None) -> int:
    import argparse
    import sys
    from pathlib import Path
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("reinject", help="replace the injected CSS and scripts of a page with the current ones")
    r.add_argument("page")
    r.add_argument("--write", action="store_true", help="replace them in the page itself")
    r.add_argument("-o", "--out", help="write the result to this file instead")
    a = ap.parse_args(argv)
    path = Path(a.page)
    html = path.read_text(encoding="utf-8")
    try:
        new, how = reinject(html)
    except ValueError as exc:
        print(f"error: {a.page}: {exc}", file=sys.stderr)
        return 1
    if outside_blocks(new) != outside_blocks(html):          # never touch the content
        print(f"error: {a.page}: the page outside the injected blocks would change; nothing written", file=sys.stderr)
        return 1
    print(f"{a.page}: blocks " + ", ".join(f"{k} ({v})" for k, v in how.items())
          + f"; {len(html)} -> {len(new)} characters" + ("; already current" if new == html else ""))
    if a.out:
        Path(a.out).write_text(new, encoding="utf-8")
        print(f"wrote {a.out}")
    elif a.write:
        if new != html:
            path.write_text(new, encoding="utf-8")
            print(f"wrote {a.page}")
    else:
        print("dry run: nothing written (add --write, or -o OUT.html)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
