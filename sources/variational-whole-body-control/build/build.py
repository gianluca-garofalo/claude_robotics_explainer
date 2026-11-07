"""Assemble the restructured document from src/part*.html.

Source conventions
  <section id="sec-x"> <h2>SECNUM Title</h2>     numbered section (h2)
  <h3 id="sec-y">SECNUM Title</h3>               numbered subsection
  SEC(sec-y)                                     -> "4.2"
  ... id="eq-EQDEF(label)" ... \\tag{EQDEF(label)} -> sequential equation number
  EQ(label)                                      -> <a class="eqref" href="#eq-N">(N)</a>
  FIGSVG(n)                                      -> inline SVG of original figure n
"""
import re, sys, glob, os, html

HERE = os.path.dirname(os.path.abspath(__file__))
rd = lambda p: open(os.path.join(HERE, p), encoding='utf-8').read()

parts = sorted(glob.glob(os.path.join(HERE, 'src', 'part*.html')))
body = '\n'.join(open(p, encoding='utf-8').read() for p in parts)
errors = []

# ---- figures -------------------------------------------------------------
def fig(m):
    return rd(f'fig{m.group(1)}.svg')
body = re.sub(r'FIGSVG\((\d)\)', fig, body)
body = body.replace('REFSLIST', rd('refs_fragment.html'))
body = re.sub(r'&ndash;(?=SEC\(|EQ\(|\d)', '&ndash;&#8288;', body)   # no line break inside a range

# ---- sections --------------------------------------------------------------
tok = re.compile(
    r'<div class="part-label(?: first)?">(?P<part>.*?)</div>'
    r'|<section id="(?P<sid>[\w-]+)">\s*<h2>(?P<h2>.*?)</h2>'
    r'|<h3 id="(?P<hid>[\w-]+)">(?P<h3>.*?)</h3>', re.S)
secnum, toc, n2, n3 = {}, [], 0, 0
def num_heading(m):
    global n2, n3
    if m.group('part') is not None:
        toc.append(('part', None, m.group('part')))
        return m.group(0)
    if m.group('sid') is not None:
        sid, title = m.group('sid'), m.group('h2')
        if title.startswith('SECNUM '):
            n2 += 1; n3 = 0
            secnum[sid] = str(n2)
            title = f'{n2}. ' + title[len('SECNUM '):]
        else:
            secnum[sid] = re.sub(r'^Appendix ([A-Z]).*$', r'\1', title)
        toc.append(('h2', sid, title))
        return m.group(0).replace(m.group('h2'), title, 1)
    hid, title = m.group('hid'), m.group('h3')
    if title.startswith('SECNUM '):
        n3 += 1
        secnum[hid] = f'{n2}.{n3}'
        title = f'{n2}.{n3} ' + title[len('SECNUM '):]
    toc.append(('h3', hid, title))
    return f'<h3 id="{hid}">{title}</h3>'
body = tok.sub(num_heading, body)

def secref(m):
    k = m.group(1)
    if k not in secnum:
        errors.append(f'undefined SEC({k})'); return '??'
    return secnum[k]
body = re.sub(r'SEC\(([\w-]+)\)', secref, body)

# ---- equations -------------------------------------------------------------
eqnum, count = {}, {}
for m in re.finditer(r'EQDEF\(([\w:-]+)\)', body):
    k = m.group(1)
    count[k] = count.get(k, 0) + 1
    if k not in eqnum:
        eqnum[k] = len(eqnum) + 1
for k, c in count.items():
    if c != 2:
        errors.append(f'EQDEF({k}) appears {c} times (expected 2: anchor + tag)')
body = re.sub(r'EQDEF\(([\w:-]+)\)', lambda m: str(eqnum[m.group(1)]), body)
def eqref(m):
    k = m.group(1)
    if k not in eqnum:
        errors.append(f'undefined EQ({k})'); return '(??)'
    n = eqnum[k]
    return f'<a class="eqref" href="#eq-{n}">({n})</a>'
body = re.sub(r'EQ\(([\w:-]+)\)', eqref, body)
used = set(re.findall(r'href="#eq-(\d+)"', body))
for k, n in eqnum.items():
    if str(n) not in used:
        print(f'note: equation ({n}) [{k}] is never referenced')

# ---- table of contents -------------------------------------------------------
out = ['<nav class="toc" id="toc" aria-label="Contents">', '  <div class="toc-title">Contents</div>', '  <ol>',
       '    <li><a href="#abstract">Abstract</a></li>']
open_sub = False; open_li = False
def close():
    global open_sub, open_li
    if open_sub: out.append('      </ol>'); open_sub = False
    if open_li: out.append('    </li>'); open_li = False
for kind, ident, title in toc:
    if kind == 'part':
        close(); out.append(f'    <li class="toc-part">{title}</li>')
    elif kind == 'h2':
        close(); out.append(f'    <li><a href="#{ident}">{title}</a>'); open_li = True
    else:
        if not open_sub: out.append('      <ol>'); open_sub = True
        out.append(f'        <li><a href="#{ident}">{title}</a></li>')
close()
out += ['  </ol>', '</nav>']
nav = '\n'.join(out)

doc = (rd('head.html') + '\n\n' + rd('controls.html') + '\n\n<!-- Table of Contents (sidebar) -->\n' + nav
       + '\n\n<article>\n\n' + body + '\n</article>\n' + rd('tail.html'))

# ---- checks ------------------------------------------------------------------
for t in ('SECNUM', 'SEC(', 'EQDEF(', 'EQ(', 'FIGSVG('):
    i = doc.find(t)
    if i >= 0:
        errors.append(f'leftover token {t!r} near: {doc[max(0,i-80):i+40]!r}')
ids = set(re.findall(r'\sid="([^"]+)"', doc))
for h in sorted(set(re.findall(r'href="#([^"]+)"', doc))):
    if h not in ids:
        errors.append(f'dangling link #{h}')
dup = [i for i in set(re.findall(r'\sid="([^"]+)"', doc)) if len(re.findall(r'\sid="%s"' % re.escape(i), doc)) > 1]
if dup:
    print('note: duplicate ids (svg-internal ids are expected):', sorted(dup)[:20])

outpath = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, 'out.html')
open(outpath, 'w', encoding='utf-8').write(doc)
print(f'sections: {len(secnum)}, equations: {len(eqnum)}, bytes: {len(doc)} -> {outpath}')
if errors:
    print('ERRORS:'); [print('  ' + e) for e in errors]; sys.exit(1)
