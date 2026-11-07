#!/usr/bin/env python3
"""Build runs/<run>/draft/ (parts, meta.json, references.json, code/figures/*.svg) into explainer.html, then lint it.

Usage:
  python3 tools/build_explainer.py runs/<run> [--strict] [--out FILE]
"""
from __future__ import annotations

import argparse
import html
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import TEMPLATES, rel, resolve_run  # noqa: E402
import lint_html  # noqa: E402
import html_features as HF  # noqa: E402
import validate as V  # noqa: E402

ORG_TYPES = {"web", "press", "video", "software", "dataset", "report"}


class BuildError(Exception):
    pass


def esc(s) -> str:
    return html.escape(str(s), quote=False)


# --------------------------------------------------------------------------- references and citations
def surname(name: str) -> str:
    name = name.strip()
    if "," in name:
        return name.split(",")[0].strip()
    parts = name.split()
    particles = {"van", "von", "de", "der", "den", "da", "di", "du", "del", "la", "le"}
    i = len(parts) - 1
    while i > 0 and parts[i - 1].lower() in particles:
        i -= 1
    return " ".join(parts[i:])


def cite_names(r: dict, textual: bool) -> str:
    if r.get("cite_as"):
        return esc(r["cite_as"])
    authors = r["authors"]
    if len(authors) == 1 and r["type"] in ORG_TYPES:
        return esc(authors[0])
    s = [esc(surname(a)) for a in authors]
    if len(s) == 1:
        return s[0]
    if len(s) == 2:
        return f"{s[0]} and {s[1]}" if textual else f"{s[0]} &amp; {s[1]}"
    return f"{s[0]} et al."


def cite(r: dict, textual: bool) -> str:
    names, year = cite_names(r, textual), r["year"]
    text = f"{names} ({year})" if textual else f"{names}, {year}"
    return f'<a href="#ref-{r["key"]}">{text}</a>'


def author_list(authors: list[str]) -> str:
    a = [esc(x) for x in authors]
    if len(a) > 10:
        return ", ".join(a[:3]) + ", et al."
    if len(a) == 1:
        return a[0]
    if len(a) == 2:
        return f"{a[0]} and {a[1]}"
    return ", ".join(a[:-1]) + ", and " + a[-1]


def format_ref(r: dict) -> str:
    t = r["type"]
    parts = [author_list(r["authors"])]
    title = esc(r["title"])
    venue = esc(r.get("venue", "")) if r.get("venue") else ""
    if t in ("book", "thesis"):
        s = f"<em>{title}</em>"
        extra = [esc(x) for x in (r.get("publisher"),) if x]
    else:
        s = f"&ldquo;{title},&rdquo;"
        extra = []
        if t == "article":
            if venue:
                extra.append(f"<em>{venue}</em>")
        elif t in ("inproceedings", "chapter"):
            if venue:
                extra.append(f"in <em>{venue}</em>")
            if r.get("publisher"):
                extra.append(esc(r["publisher"]))
        elif t == "preprint":
            extra.append("preprint")
        elif venue or r.get("publisher"):
            extra.append(f"<em>{venue or esc(r['publisher'])}</em>")
    for k, label in (("volume", "vol. "), ("number", "no. "), ("pages", "pp. ")):
        if r.get(k):
            extra.append(f"{label}{esc(r[k]).replace('-', '&ndash;')}")
    extra.append(esc(r["year"]))
    body = f"{parts[0]}, {s} " + ", ".join(extra) + "."
    ids = []
    if r.get("doi"):
        d = esc(r["doi"])
        ids.append(f'doi:<a href="https://doi.org/{d}">{d}</a>')
    if r.get("arxiv"):
        x = esc(r["arxiv"])
        ids.append(f'arXiv:<a href="https://arxiv.org/abs/{x}">{x}</a>')
    if r.get("url") and not r.get("doi") and not r.get("arxiv"):
        u = esc(r["url"])
        shown = re.sub(r"^https?://(www\.)?", "", r["url"]).rstrip("/")
        shown = esc(shown if len(shown) <= 60 else shown[:57] + "...")
        ids.append(f'<a href="{u}">{shown}</a>')
    if ids:
        body += " " + "; ".join(ids) + "."
    if r.get("accessed"):
        body += f" Accessed {esc(r['accessed'])}."
    if r.get("note"):
        body += f" ({esc(r['note'])})"
    status = r.get("verification", {}).get("status")
    if status == "secondary_only":
        body += " &#9675;"
    elif status == "unverified":
        body += ' <span class="unverified">[unverified]</span>'
    return f'<li id="ref-{r["key"]}">{body}</li>'


# --------------------------------------------------------------------------- SVG figures
def load_svg(run: Path, name: str) -> str:
    p = run / "code" / "figures" / f"{name}.svg"
    if not p.exists():
        raise BuildError(f"<!--SVG:{name}--> but {rel(p)} does not exist (produce it with a script in code/)")
    s = p.read_text(encoding="utf-8")
    s = re.sub(r"<\?xml.*?\?>", "", s, flags=re.S)
    s = re.sub(r"<!DOCTYPE.*?>", "", s, flags=re.S)
    s = re.sub(r"<!--.*?-->", "", s, flags=re.S).strip()
    s = HF.theme_svg(s)
    prefix = re.sub(r"[^\w-]", "-", name)
    s = re.sub(r'\bid="([^"]+)"', lambda m: f'id="{prefix}-{m.group(1)}"', s)
    s = re.sub(r"url\(#([^)]+)\)", lambda m: f"url(#{prefix}-{m.group(1)})", s)
    s = re.sub(r'((?:xlink:)?href)="#([^"]+)"', lambda m: f'{m.group(1)}="#{prefix}-{m.group(2)}"', s)
    m = re.search(r"<svg\b[^>]*>", s)
    if not m:
        raise BuildError(f"{rel(p)} has no <svg> element")
    tag = m.group(0)
    new = tag
    if "style=" not in tag:
        width = None
        vb = re.search(r'viewBox="[\d.\-]+\s+[\d.\-]+\s+([\d.]+)', tag)
        w = re.search(r'\swidth="([\d.]+)(pt|px)?"', tag)
        if w:
            width = float(w.group(1)) * (4 / 3 if w.group(2) == "pt" else 1)
        elif vb:
            width = float(vb.group(1))
        new = re.sub(r'\s(width|height)="[^"]*"', "", new)
        mw = f"max-width:{int(round(width))}px;" if width else ""
        new = new[:-1] + f' style="width:100%;{mw}height:auto"' + ">"
    if "role=" not in new:
        new = new[:-1] + ' role="img"' + ">"
    if "aria-label=" not in new:
        print(f"warning: {rel(p)} has no aria-label; add a one-line description of the figure", file=sys.stderr)
    return s.replace(tag, new, 1)


# --------------------------------------------------------------------------- assembly
# The drafts are rewritten as text (markers, regular expressions): every byte the build does not number stays as written.
def build(run: Path, strict: bool = False) -> tuple[str, dict]:
    draft = run / "draft"
    meta_p = draft / "meta.json"
    if not meta_p.exists():
        raise BuildError(f"{rel(meta_p)} is missing")
    meta = json.loads(meta_p.read_text(encoding="utf-8"))
    for k in ("title", "subtitle", "date"):
        if not meta.get(k):
            raise BuildError(f"draft/meta.json needs '{k}'")
    parts = sorted(p for p in draft.glob("*.html") if not p.name.startswith("_"))
    if not parts:
        raise BuildError("no draft/*.html parts")
    body = "\n\n".join(p.read_text(encoding="utf-8").strip() for p in parts)
    if 'id="sec-references"' in body:
        raise BuildError("drafts must not contain the References section: the build appends it from references.json")

    refs_p = run / "references.json"
    refs = []
    if refs_p.exists():
        rep = V.validate_file("references", refs_p, run)
        if rep.errors:
            rep.print()
            raise BuildError("references.json has errors")
        refs = json.loads(refs_p.read_text(encoding="utf-8"))["references"]
    by_key = {r["key"]: r for r in refs}

    def cite_repl(m):
        key = m.group(2)
        if key not in by_key:
            raise BuildError(f"[[{m.group(1)}:{key}]] cites an unknown reference key")
        return cite(by_key[key], textual=m.group(1) == "citet")
    body = re.sub(r"\[\[(cite|citet):([\w]+)\]\]", cite_repl, body)

    body = re.sub(r"<!--SVG:([\w-]+)-->", lambda m: load_svg(run, m.group(1)), body)

    attribution = (TEMPLATES / "explainer" / "attribution.html").read_text(encoding="utf-8").strip()
    items = "\n".join("  " + format_ref(by_key[k]) for k in sorted(by_key))
    body += ("\n\n<section id=\"sec-references\">\n<h2>References</h2>\n" + attribution +
             "\n<ol class=\"references\">\n" + items + "\n</ol>\n</section>")

    tok = re.compile(r'<div class="part-label[^"]*">(.*?)</div>|<section id="([^"]+)"([^>]*)>\s*<h2>(.*?)</h2>'
                     r'|<h3 id="([^"]+)">(.*?)</h3>', re.S)
    sec_num, toc, out, last, h2n, h3n = {}, [], [], 0, 0, 0
    for m in tok.finditer(body):
        out.append(body[last:m.start()])
        if m.group(1) is not None:
            toc.append(("part", None, m.group(1)))
            out.append(m.group(0))
        elif m.group(2) is not None:
            h2n += 1
            h3n = 0
            sid, attrs, title = m.group(2), m.group(3), m.group(4).strip()
            if sid in sec_num:
                raise BuildError(f"duplicate section id {sid}")
            sec_num[sid] = f"{h2n}"
            toc.append((2, sid, f"{h2n}. {title}"))
            out.append(f'<section id="{sid}"{attrs}>\n<h2>{h2n}. {title}</h2>')
        else:
            if h2n == 0:
                raise BuildError(f"<h3 id=\"{m.group(5)}\"> before the first section")
            h3n += 1
            sid, title = m.group(5), m.group(6).strip()
            if sid in sec_num:
                raise BuildError(f"duplicate section id {sid}")
            sec_num[sid] = f"{h2n}.{h3n}"
            toc.append((3, sid, f"{h2n}.{h3n} {title}"))
            out.append(f'<h3 id="{sid}">{h2n}.{h3n} {title}</h3>')
        last = m.end()
    out.append(body[last:])
    body = "".join(out)

    # link targets: an anchor before each display with \tag{[[eq:name]]}, an id on the figure defining [[figdef:name]]
    def anchor_display(m):
        names = re.findall(r"\\tag\{\[\[eq:([\w-]+)\]\]\}", m.group(0))
        return "".join(f'<span class="eq-anchor" id="eq-{n}" aria-hidden="true"></span>' for n in names) + m.group(0)
    body = re.sub(r"\$\$.*?\$\$", anchor_display, body, flags=re.S)

    def figure_id(m):
        name = re.search(r"\[\[figdef:([\w-]+)\]\]", m.group(0))
        if name and " id=" not in m.group(1):
            return f'<figure id="fig-{name.group(1)}"{m.group(1)}>' + m.group(2)
        return m.group(0)
    body = re.sub(r"<figure((?:\s[^>]*)?)>(.*?</figure>)", figure_id, body, flags=re.S)

    eq_num, fig_num = {}, {}
    for i, name in enumerate(re.findall(r"\\tag\{\[\[eq:([\w-]+)\]\]\}", body), 1):
        if name in eq_num:
            raise BuildError(f"duplicate equation label {name}")
        eq_num[name] = i
    for i, name in enumerate(re.findall(r"\[\[figdef:([\w-]+)\]\]", body), 1):
        if name in fig_num:
            raise BuildError(f"duplicate figure label {name}")
        fig_num[name] = i

    def number(kind, name):
        table = {"eq": eq_num, "fig": fig_num, "figdef": fig_num, "sec": sec_num}[kind]
        if name not in table:
            raise BuildError(f"unresolved reference [[{kind}:{name}]]")
        return str(table[name])

    def link(m):                         # outside math: a link the Back button undoes ("(3)" links as a whole)
        lp, kind, name, rp = m.group(1) or "", m.group(2), m.group(3), m.group(4) or ""
        n = number(kind, name)
        if kind == "figdef":
            return lp + n + rp
        href, cls = {"eq": (f"#eq-{name}", "eqref"), "fig": (f"#fig-{name}", "figref"), "sec": (f"#{name}", "secref")}[kind]
        if lp and rp:
            return f'<a class="{cls}" href="{href}">({n})</a>'
        return f'{lp}<a class="{cls}" href="{href}">{n}</a>{rp}'
    pieces = re.split(r"(\$\$.*?\$\$|\$[^$\n]*?\$)", body, flags=re.S)
    for k, piece in enumerate(pieces):
        if k % 2:                        # inside math: the number only (\tag{...} becomes the equation's tag)
            pieces[k] = re.sub(r"\[\[(eq|fig|figdef|sec):([\w-]+)\]\]", lambda m: number(m.group(1), m.group(2)), piece)
        else:
            pieces[k] = re.sub(r"(\()?\[\[(eq|fig|figdef|sec):([\w-]+)\]\](\))?", link, piece)
    body = "".join(pieces)
    left = re.search(r"\[\[[^\]]*\]\]|<!--SVG:", body)
    if left:
        i = left.start()
        raise BuildError("leftover marker near: " + body[max(0, i - 60):i + 60].replace("\n", " "))

    nav = ['<!-- Table of Contents (sidebar) -->', '<nav class="toc">', '  <div class="toc-title">Contents</div>',
           '  <ol>', '    <li><a href="#abstract">Abstract</a></li>']
    open_sub = False
    for i, (kind, sid, title) in enumerate(toc):
        if kind in ("part", 2) and open_sub:
            nav.append("      </ol>\n    </li>")
            open_sub = False
        if kind == "part":
            nav.append(f'    <li class="toc-part">{title}</li>')
        elif kind == 2:
            has_sub = i + 1 < len(toc) and toc[i + 1][0] == 3
            if has_sub:
                nav.append(f'    <li><a href="#{sid}">{title}</a>\n      <ol>')
                open_sub = True
            else:
                nav.append(f'    <li><a href="#{sid}">{title}</a></li>')
        else:
            nav.append(f'        <li><a href="#{sid}">{title}</a></li>')
    if open_sub:
        nav.append("      </ol>\n    </li>")
    nav += ["  </ol>", "</nav>"]

    css = (TEMPLATES / "explainer" / "explainer.css").read_text(encoding="utf-8").rstrip()
    skel = (TEMPLATES / "explainer" / "skeleton.html").read_text(encoding="utf-8")
    html_title = meta.get("html_title") or re.sub(r"<[^>]+>", "", meta["title"])
    fields = {"lang": meta.get("lang", "en"), "html_title": esc(html.unescape(html_title)), "css": css,
              "toc": "\n".join(nav), "title": meta["title"], "subtitle": meta["subtitle"], "date": meta["date"],
              "year": str(meta["date"])[:4], "body": body}
    doc = re.sub(r"\{\{(\w+)\}\}", lambda m: fields[m.group(1)], skel)
    doc = HF.inject(doc)
    stats = {"parts": len(parts), "sections": h2n, "equations": len(eq_num), "figures": len(fig_num),
             "references": len(refs),
             "uncited": sorted(set(by_key) - set(re.findall(r'href="#ref-(\w+)"', body.split('id="sec-references"')[0])))}
    return doc, stats


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run")
    ap.add_argument("--out", help="output file (default: <run>/explainer.html)")
    ap.add_argument("--strict", action="store_true", help="lint in strict mode (final build before review)")
    a = ap.parse_args()
    run = resolve_run(a.run)
    try:
        doc, st = build(run, a.strict)
    except BuildError as exc:
        print(f"build error: {exc}", file=sys.stderr)
        return 1
    out = Path(a.out) if a.out else run / "explainer.html"
    out.write_text(doc, encoding="utf-8")
    print(f"wrote {rel(out)}: {st['parts']} parts, {st['sections']} sections, {st['equations']} equations, "
          f"{st['figures']} figures, {st['references']} references")
    if st["uncited"]:
        print(f"warning: references never cited: {', '.join(st['uncited'])}")
    issues = lint_html.lint(out, run, strict=a.strict)
    errors = [i for i in issues if i["level"] == "error"]
    for i in issues:
        print(f"  {i['level']:7} [{i['code']}] {i['message']}" + (f" (line {i['line']})" if i["line"] else ""))
    print(f"lint: {'FAIL' if errors else 'ok'} ({len(errors)} error(s))")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
