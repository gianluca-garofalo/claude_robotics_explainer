#!/usr/bin/env node
/*
 * Render check of an explainer page in Chromium at each width (KaTeX, links, ids, contents, figures, overflow, tags).
 *
 *   node tools/check_html.js runs/<run>/explainer.html [--json report.json] [--screenshots DIR]
 *                            [--offline] [--katex-dist DIR] [--widths 1400,390]
 */
'use strict';
const fs = require('fs');
const path = require('path');

const KATEX_PREFIX = 'https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/';
const MIN_LABEL_PX = 9;           // tools/html_features.py scales figure labels up to this
const REPO = path.resolve(__dirname, '..');
const PREINSTALLED_CHROMIUM = '/opt/pw-browsers/chromium';    // cloud images

function parseArgs(argv) {
  const a = { file: null, json: null, shots: null, offline: !!process.env.CHECK_HTML_OFFLINE, katex: null, widths: [1400, 390] };
  for (let i = 0; i < argv.length; i++) {
    const x = argv[i];
    if (x === '--json') a.json = argv[++i];
    else if (x === '--screenshots') a.shots = argv[++i];
    else if (x === '--offline') a.offline = true;
    else if (x === '--katex-dist') a.katex = argv[++i];
    else if (x === '--widths') a.widths = argv[++i].split(',').map(Number);
    else if (x === '-h' || x === '--help') { console.log(fs.readFileSync(__filename, 'utf8').split('*/')[0]); process.exit(0); }
    else if (!a.file) a.file = x;
    else { console.error(`unknown argument ${x}`); process.exit(3); }
  }
  if (!a.file) { console.error('usage: node tools/check_html.js FILE.html [--json out] [--screenshots dir] [--offline]'); process.exit(3); }
  return a;
}

function findKatex(explicit) {
  const cands = [explicit, process.env.KATEX_DIST, path.join(REPO, 'node_modules', 'katex', 'dist')];
  try { cands.push(path.join(path.dirname(require.resolve('katex/package.json')), 'dist')); } catch (e) { /* not installed */ }
  for (const c of cands) {
    if (c && fs.existsSync(path.join(c, 'katex.min.js'))) {
      let version = null;
      try { version = JSON.parse(fs.readFileSync(path.join(c, '..', 'package.json'), 'utf8')).version; } catch (e) { /* unknown */ }
      return { dir: c, version };
    }
  }
  return null;
}

// Playwright's pinned Chromium, else $CHROMIUM_PATH or the preinstalled one when the pinned build is not installed.
async function launchChromium(chromium) {
  try { return await chromium.launch(); } catch (e) {
    const alt = process.env.CHROMIUM_PATH || (fs.existsSync(PREINSTALLED_CHROMIUM) ? PREINSTALLED_CHROMIUM : null);
    if (!alt || !e.message.includes("Executable doesn't exist")) throw e;
    const browser = await chromium.launch({ executablePath: alt });
    console.log(`browser: ${alt} (Chromium ${browser.version()}; Playwright's pinned build is not installed)`);
    return browser;
  }
}

// Runs inside the page.
function inspect(opts) {
  const res = {};
  const norm = s => s.replace(/\s+/g, ' ').trim();
  res.katex = document.querySelectorAll('.katex').length;
  res.katexErrors = [...document.querySelectorAll('.katex-error')].map(e => (e.getAttribute('title') || e.textContent).slice(0, 160));
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  const raw = [];
  while (walker.nextNode()) {
    const n = walker.currentNode;
    if (n.textContent.includes('$') && !n.parentElement.closest('.katex, script, style, code, pre, svg, textarea')) raw.push(norm(n.textContent).slice(0, 90));
  }
  res.rawDollar = raw.slice(0, 15);
  const tags = [...document.querySelectorAll('.katex-display .tag')].map(t => t.innerText.trim());
  res.ntags = tags.length;
  const nums = tags.map(t => parseInt(t.replace(/[()]/g, ''), 10));
  res.tagFirstBad = nums.findIndex((x, i) => x !== i + 1);
  res.tagSample = tags.length ? tags.slice(0, 3).join(' ') + (tags.length > 3 ? ' ... ' + tags.slice(-2).join(' ') : '') : '';
  res.tagOverlap = [...document.querySelectorAll('.katex-display')].map(d => {
    const tag = d.querySelector('.tag'); if (!tag) return null;
    const t = tag.getBoundingClientRect(); const pl = parseFloat(getComputedStyle(tag).paddingLeft) || 0;
    const hit = [...d.querySelectorAll('.katex-html > .base')].map(e => e.getBoundingClientRect())
      .some(r => r.right > t.left + pl - 4 && r.bottom > t.top && r.top < t.bottom && r.width > 0);
    return hit ? tag.innerText.trim() : null;
  }).filter(x => x);
  const ids = [...document.querySelectorAll('[id]')].map(e => e.id);
  const idset = new Set(ids);
  res.duplicateIds = [...new Set(ids.filter((x, i) => ids.indexOf(x) !== i))].slice(0, 15);
  res.badLinks = [...new Set([...document.querySelectorAll('a[href^="#"]')].map(a => a.getAttribute('href').slice(1)).filter(h => h && !idset.has(h)))].slice(0, 15);
  const cited = new Set([...document.querySelectorAll('a[href^="#ref-"]')].map(a => a.getAttribute('href').slice(1)));
  res.uncitedRefs = [...document.querySelectorAll('li[id^="ref-"]')].map(e => e.id).filter(x => !cited.has(x));
  // textContent: on a phone the contents are a closed drawer (hidden), and innerText of hidden text is empty
  const toc = [...document.querySelectorAll('nav.toc a[href^="#"]')].map(a => [a.getAttribute('href').slice(1), norm(a.textContent)]);
  res.tocEntries = toc.length;
  res.tocMismatch = toc.filter(([id, txt]) => {
    const el = document.getElementById(id); if (!el) return true;
    const h = el.tagName === 'SECTION' ? el.querySelector('h2') : (/^H[1-6]$/.test(el.tagName) ? el : null);
    return h ? norm(h.textContent) !== txt : false;
  }).map(([id, txt]) => `${txt} -> #${id}`).slice(0, 10);
  const heads = [...document.querySelectorAll('article section[id] > h2, article h3[id]')].map(h => h.parentElement.tagName === 'SECTION' && h.tagName === 'H2' ? h.parentElement.id : h.id);
  const tocIds = new Set(toc.map(t => t[0]));
  res.headingsNotInToc = heads.filter(id => !tocIds.has(id)).slice(0, 10);
  res.figures = [...document.querySelectorAll('figure')].map((f, i) => {
    const g = f.querySelector('svg, img'); const b = g ? g.getBoundingClientRect() : null;
    return { i: i + 1, caption: !!f.querySelector('figcaption'), size: b ? `${Math.round(b.width)}x${Math.round(b.height)}` : 'none', empty: !b || b.width < 10 || b.height < 10 };
  });
  const cw = document.documentElement.clientWidth;
  res.scrollWidth = document.documentElement.scrollWidth; res.clientWidth = cw;
  const scrollers = '.equation-block, table, .katex-display, pre, td, nav.toc';
  // an element is only a problem if it is visible past the viewport: skip parts clipped by an ancestor
  // (KaTeX's hidden MathML and stretchy-glyph tails) and the insides of an <svg> (the <svg> itself is checked)
  const clipped = e => {
    for (let x = e.parentElement; x && x.tagName !== 'ARTICLE'; x = x.parentElement) {
      if (getComputedStyle(x).overflowX !== 'visible' && x.getBoundingClientRect().right <= cw + 1) return true;
    }
    return false;
  };
  res.wide = [...document.querySelectorAll('article *')].filter(e => {
    const r = e.getBoundingClientRect();
    if (!(r.width > 0 && r.right > cw + 1) || e.closest(scrollers)) return false;
    if (e.ownerSVGElement) return false;
    return !clipped(e);
  }).map(e => e.tagName.toLowerCase() + (e.id ? '#' + e.id : '') + (e.className && typeof e.className === 'string' ? '.' + e.className.split(' ')[0] : '')).slice(0, 10);
  res.headingIds = [...document.querySelectorAll('article section[id]')].map(s => s.id);

  // An equation number is off screen outside the part of its scrolling box (or of the page) seen without scrolling.
  const visible = el => {
    let l = 0, r = cw;
    for (let x = el.parentElement; x; x = x.parentElement) {
      if (x === document.documentElement || x === document.body) break;
      if (getComputedStyle(x).overflowX !== 'visible') {
        const b = x.getBoundingClientRect(); l = Math.max(l, b.left); r = Math.min(r, b.right);
      }
    }
    return [l, r];
  };
  const tagEls = [...document.querySelectorAll('.katex-display .tag')];
  res.tagsHidden = tagEls.filter(t => {
    const b = t.getBoundingClientRect(); const [l, r] = visible(t);
    return b.width === 0 || b.left < l - 1 || b.right > r + 1;
  }).map(t => t.innerText.trim());
  // Figure labels: the computed font size of each <text> (user units) times the figure's rendered scale.
  res.figureText = [...document.querySelectorAll('figure svg')].filter(s => !s.parentElement.closest('svg')).map((s, i) => {
    const vb = s.viewBox && s.viewBox.baseVal && s.viewBox.baseVal.width ? s.viewBox.baseVal.width : null;
    const k = vb ? s.getBoundingClientRect().width / vb : 1;
    const px = [...s.querySelectorAll('text')].map(t => parseFloat(getComputedStyle(t).fontSize) * k).filter(x => x > 0);
    return { fig: i + 1, minPx: px.length ? Math.round(Math.min(...px) * 10) / 10 : null, labels: px.length };
  }).filter(f => f.minPx !== null);
  // Numbers in table cells that wrap onto two lines ("0.516" / "8").
  const broken = [];
  for (const cell of document.querySelectorAll('td, th')) {
    const tw = document.createTreeWalker(cell, NodeFilter.SHOW_TEXT);
    while (tw.nextNode()) {
      const n = tw.currentNode;
      if (n.parentElement.closest('.katex')) continue;
      for (const m of n.textContent.matchAll(/[\u2212-]?\d+(?:[.,]\d+)+|\d{4,}/g)) {
        const rg = document.createRange(); rg.setStart(n, m.index); rg.setEnd(n, m.index + m[0].length);
        if (new Set([...rg.getClientRects()].map(x => Math.round(x.top))).size > 1) {
          const sec = cell.closest('section[id]');
          broken.push(`${m[0]} (${sec ? sec.id : 'page'})`);
        }
      }
    }
  }
  res.brokenNumbers = broken;
  return res;
}

async function main() {
  const a = parseArgs(process.argv.slice(2));
  const file = path.resolve(a.file);
  if (!fs.existsSync(file)) { console.error(`not found: ${a.file}`); process.exit(3); }
  let chromium;
  try { ({ chromium } = require('playwright')); } catch (e) {
    console.error('playwright is not installed: run `npm install` and `npx playwright install chromium` (see setup.sh)');
    process.exit(3);
  }
  const kx = findKatex(a.katex);
  if (a.offline && !kx) { console.error('--offline needs a local KaTeX 0.16.9 (npm install, or --katex-dist DIR)'); process.exit(3); }
  if (kx && kx.version && kx.version !== '0.16.9') console.warn(`warning: local KaTeX is ${kx.version}, the documents pin 0.16.9`);

  let browser;
  try { browser = await launchChromium(chromium); } catch (e) {
    console.error('could not start Chromium: run `npx playwright install chromium` (' + e.message.split('\n')[0] + ')');
    process.exit(3);
  }
  const sha256 = require('crypto').createHash('sha256').update(fs.readFileSync(file)).digest('hex');
  const report = { file: path.relative(process.cwd(), file), sha256, katex: kx ? `local ${kx.version || '?'}` : 'cdn', widths: {}, errors: [], warnings: [] };
  const fail = (w, msg) => report.errors.push(`[${w}px] ${msg}`);
  const widest = Math.max(...a.widths);
  if (a.shots) fs.mkdirSync(a.shots, { recursive: true });

  for (const w of a.widths) {
    const page = await browser.newPage({ viewport: { width: w, height: 900 } });
    const consoleErrors = [];
    const external = [];
    page.on('console', m => { if (m.type() === 'error') consoleErrors.push(m.text().slice(0, 200)); });
    page.on('pageerror', e => consoleErrors.push('pageerror: ' + e.message.slice(0, 200)));
    await page.route('**/*', route => {
      const url = route.request().url();
      if (url.startsWith('file:') || url.startsWith('data:') || url.startsWith('about:')) return route.continue();
      if (url.startsWith(KATEX_PREFIX)) {
        if (kx) {
          const local = path.join(kx.dir, url.slice(KATEX_PREFIX.length).split(/[?#]/)[0]);
          if (fs.existsSync(local)) return route.fulfill({ path: local });
          return route.fulfill({ status: 404, body: 'not in local KaTeX copy' });
        }
        return a.offline ? route.abort() : route.continue();
      }
      external.push(url);
      return route.abort();
    });
    await page.goto('file://' + file, { waitUntil: 'load', timeout: 60000 });
    await page.waitForFunction(() => document.querySelectorAll('.katex').length > 0 || !document.body.innerText.includes('$'),
      null, { timeout: 20000 }).catch(() => {});
    await page.evaluate(() => document.fonts ? document.fonts.ready : null);
    await page.waitForTimeout(400);
    const r = await page.evaluate(inspect, {});
    r.consoleErrors = consoleErrors; r.external = [...new Set(external)];
    report.widths[w] = r;

    if (r.katexErrors.length) fail(w, `${r.katexErrors.length} KaTeX error(s): ${r.katexErrors.slice(0, 3).join(' | ')}`);
    if (r.rawDollar.length) fail(w, `raw "$" left in text (${r.rawDollar.length}): ${r.rawDollar.slice(0, 3).join(' | ')}`);
    if (r.katex === 0 && r.rawDollar.length) fail(w, 'KaTeX did not render (is the CDN reachable, or is a local copy installed?)');
    if (r.consoleErrors.length) fail(w, `console errors: ${r.consoleErrors.slice(0, 3).join(' | ')}`);
    if (r.external.length) fail(w, `external requests (explainers must be self-contained): ${r.external.slice(0, 3).join(' ')}`);
    if (r.badLinks.length) fail(w, `links without target: ${r.badLinks.join(', ')}`);
    if (r.duplicateIds.length) fail(w, `duplicate ids: ${r.duplicateIds.join(', ')}`);
    if (r.tocMismatch.length) fail(w, `TOC entries that do not match their heading: ${r.tocMismatch.join(' | ')}`);
    if (r.headingsNotInToc.length) fail(w, `headings missing from the TOC: ${r.headingsNotInToc.join(', ')}`);
    if (r.tagOverlap.length) fail(w, `equation tags overlapping the formula: ${r.tagOverlap.join(' ')}`);
    const badFigs = r.figures.filter(f => !f.caption || f.empty);
    if (badFigs.length) fail(w, `figures without caption or with an empty graphic: ${badFigs.map(f => f.i).join(', ')}`);
    if (w === widest && r.tagFirstBad !== -1) fail(w, `equation tags not sequential (first problem at position ${r.tagFirstBad + 1}; ${r.tagSample})`);
    if (w <= 500 && r.scrollWidth > r.clientWidth + 1) fail(w, `horizontal page overflow: scrollWidth ${r.scrollWidth} > ${r.clientWidth}`);
    if (w <= 500 && r.wide.length) fail(w, `elements wider than the viewport: ${r.wide.join(', ')}`);
    if (w === widest && r.uncitedRefs.length) report.warnings.push(`references never cited: ${r.uncitedRefs.join(', ')}`);
    if (w <= 500 && r.tagsHidden.length) report.warnings.push(`[${w}px] ${r.tagsHidden.length} of ${r.ntags} equation ` +
      `numbers are off screen (in a formula that scrolls sideways): ${r.tagsHidden.slice(0, 8).join(' ')}`);
    const small = r.figureText.filter(f => f.minPx < MIN_LABEL_PX);
    if (small.length) report.warnings.push(`[${w}px] figure labels below ${MIN_LABEL_PX} px: ` +
      small.map(f => `figure ${f.fig} (${f.minPx} px)`).join(', '));
    if (r.brokenNumbers.length) report.warnings.push(`[${w}px] ${r.brokenNumbers.length} number(s) broken across lines ` +
      `in table cells: ${r.brokenNumbers.slice(0, 5).join(', ')}`);

    console.log(`${w}px: katex=${r.katex} katexErrors=${r.katexErrors.length} rawDollar=${r.rawDollar.length} tags=${r.ntags}` +
      ` (${r.tagSample || 'none'}) overlaps=${r.tagOverlap.length} badLinks=${r.badLinks.length} toc=${r.tocEntries}` +
      ` figures=${r.figures.length} scrollWidth=${r.scrollWidth}/${r.clientWidth} external=${r.external.length}` +
      ` consoleErrors=${r.consoleErrors.length} tagsOffScreen=${r.tagsHidden.length}/${r.ntags}` +
      ` minLabelPx=${r.figureText.length ? Math.min(...r.figureText.map(f => f.minPx)) : '-'}` +
      ` brokenNumbers=${r.brokenNumbers.length}`);

    if (a.shots) {
      const tag = w >= 1000 ? 'desk' : `w${w}`;
      await page.screenshot({ path: path.join(a.shots, `${tag}_top.png`) });
      const ids = w >= 1000 ? r.headingIds : r.headingIds.slice(0, 4);
      for (const id of ids.slice(0, 24)) {
        await page.evaluate(id => { document.documentElement.style.scrollBehavior = 'auto'; document.getElementById(id).scrollIntoView(); }, id);
        await page.waitForTimeout(80);
        await page.screenshot({ path: path.join(a.shots, `${tag}_${id}.png`) });
      }
    }
    await page.close();
  }
  await browser.close();
  report.pass = report.errors.length === 0;
  if (a.json) { fs.mkdirSync(path.dirname(path.resolve(a.json)), { recursive: true }); fs.writeFileSync(a.json, JSON.stringify(report, null, 2) + '\n'); }
  for (const e of report.errors) console.log('ERROR   ' + e);
  for (const wmsg of report.warnings) console.log('warning ' + wmsg);
  console.log(`check_html: ${report.pass ? 'PASS' : 'FAIL'} (${report.errors.length} error(s), ${report.warnings.length} warning(s); KaTeX ${report.katex}) ${report.file}`);
  process.exit(report.pass ? 0 : 1);
}

module.exports = { findKatex, launchChromium };
if (require.main === module) main().catch(e => { console.error('check_html crashed: ' + (e && e.stack || e)); process.exit(3); });
