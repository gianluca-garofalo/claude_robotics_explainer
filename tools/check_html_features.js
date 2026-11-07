#!/usr/bin/env node
/*
 * Browser check of the reader features of an explainer page (dark mode, equation links with Back, contents drawer).
 *
 *   node tools/check_html_features.js PAGE.html [--katex-dist DIR] [--shots DIR] [--json OUT.json]
 */
'use strict';
const fs = require('fs');
const path = require('path');
const { findKatex, launchChromium } = require('./check_html.js');

const args = process.argv.slice(2);
const opt = (name) => { const i = args.indexOf(name); return i >= 0 ? args[i + 1] : null; };
const file = args.find((a, i) => !a.startsWith('--') && (i === 0 || !args[i - 1].startsWith('--')));
if (!file || !fs.existsSync(file)) { console.error('usage: node tools/check_html_features.js PAGE.html'); process.exit(3); }
const kdir = (findKatex(opt('--katex-dist')) || {}).dir;
if (!kdir) { console.error('no local KaTeX (--katex-dist DIR)'); process.exit(3); }
let chromium;
try { ({ chromium } = require('playwright')); } catch (e) { console.error('playwright is not installed'); process.exit(3); }

const url = 'file://' + path.resolve(file);
const results = [];
const check = (name, ok, detail) => { results.push({ name, ok: !!ok, detail: detail || '' }); };

async function route(ctx) {
  await ctx.route('**/*', r => {
    const u = r.request().url();
    if (u.startsWith('file://')) return r.continue();
    const m = u.match(/katex@0\.16\.9\/dist\/(.+?)(\?|$)/);
    if (m && fs.existsSync(path.join(kdir, m[1]))) {
      const ct = m[1].endsWith('.css') ? 'text/css' : m[1].endsWith('.js') ? 'application/javascript' : 'font/woff2';
      return r.fulfill({ status: 200, contentType: ct, body: fs.readFileSync(path.join(kdir, m[1])) });
    }
    return r.abort();
  });
}

async function open(browser, opts) {
  const ctx = await browser.newContext(opts);
  await route(ctx);
  const page = await ctx.newPage();
  await page.goto(url, { waitUntil: 'load' });
  await page.waitForFunction(() => document.querySelectorAll('.katex').length > 0, null, { timeout: 30000 })
    .catch(() => {});
  await page.waitForTimeout(300);
  return { ctx, page };
}

(async () => {
  let browser;
  try { browser = await launchChromium(chromium); } catch (e) { console.error('could not start Chromium: ' + e.message); process.exit(3); }
  const shots = opt('--shots');

  // 1. JavaScript off: contents visible, light, every anchor present
  {
    const { ctx, page } = await open(browser, { javaScriptEnabled: false, viewport: { width: 390, height: 800 } });
    const r = await page.evaluate(() => {
      const nav = document.querySelector('nav.toc');
      const st = nav ? getComputedStyle(nav) : null;
      return { nav: !!nav && st.display !== 'none' && st.visibility !== 'hidden' && nav.getBoundingClientRect().width > 100,
               theme: document.documentElement.getAttribute('data-theme'), anchors: document.querySelectorAll('.eq-anchor').length };
    });
    check('no JavaScript: contents visible, light theme, anchors present', r.nav && !r.theme && r.anchors > 0, JSON.stringify(r));
    await ctx.close();
  }

  // 2. desktop, light system setting: KaTeX, ids, links, theme toggle and persistence, eqref + Back, collapse
  {
    const { ctx, page } = await open(browser, { viewport: { width: 1400, height: 900 }, colorScheme: 'light' });
    const r = await page.evaluate(() => {
      const ids = [...document.querySelectorAll('[id]')].map(e => e.id);
      const dup = ids.filter((x, i) => ids.indexOf(x) !== i);
      const dangling = [...document.querySelectorAll('a[href^="#"]')].map(a => a.getAttribute('href').slice(1))
        .filter(id => id && !document.getElementById(decodeURIComponent(id)));
      return { katexErrors: document.querySelectorAll('.katex-error').length, katex: document.querySelectorAll('.katex').length,
               dup: [...new Set(dup)].slice(0, 5), dangling: [...new Set(dangling)].slice(0, 5),
               eqrefs: document.querySelectorAll('a.eqref').length, theme: document.documentElement.getAttribute('data-theme') };
    });
    check('KaTeX renders without errors', r.katex > 0 && r.katexErrors === 0, `${r.katex} formulas, ${r.katexErrors} errors`);
    check('no duplicate ids, every #link resolves', !r.dup.length && !r.dangling.length,
          `duplicates ${r.dup.join(', ') || 'none'}; dangling ${r.dangling.join(', ') || 'none'}`);
    check('theme follows a light system setting', r.theme === 'light', r.theme);
    await page.click('.theme-toggle');
    const t1 = await page.evaluate(() => [document.documentElement.getAttribute('data-theme'),
      document.querySelector('.theme-toggle').getAttribute('aria-pressed')]);
    await page.reload({ waitUntil: 'load' });
    await page.waitForTimeout(300);
    const t2 = await page.evaluate(() => document.documentElement.getAttribute('data-theme'));
    check('theme toggle flips the theme (aria-pressed) and the choice survives a reload',
          t1[0] === 'dark' && t1[1] === 'true' && t2 === 'dark', `${t1} then ${t2}`);
    if (shots) {
      fs.mkdirSync(shots, { recursive: true });
      const fig = await page.$('figure svg');
      if (fig) { await fig.scrollIntoViewIfNeeded(); await fig.screenshot({ path: path.join(shots, 'figure-dark.png') }); }
    }
    await page.click('.theme-toggle');                              // back to light for the remaining checks
    if (shots) {
      const fig = await page.$('figure svg');
      if (fig) await fig.screenshot({ path: path.join(shots, 'figure-light.png') });
    }
    if (r.eqrefs) {
      const handle = await page.evaluateHandle(() => {
        const refs = [...document.querySelectorAll('a.eqref')];
        return refs.find(a => { const t = document.getElementById(a.getAttribute('href').slice(1));
          return t && Math.abs(t.getBoundingClientRect().top - a.getBoundingClientRect().top) > 1.5 * innerHeight; }) || refs[0];
      });
      await handle.evaluate(a => a.scrollIntoView({ block: 'center', behavior: 'instant' }));
      await page.waitForTimeout(600);
      const y0 = await page.evaluate(() => scrollY);
      await handle.click();
      await page.waitForTimeout(1200);
      const after = await handle.evaluate(a => { const t = document.getElementById(a.getAttribute('href').slice(1));
        return { y: scrollY, top: t.getBoundingClientRect().top, h: innerHeight, back: !document.querySelector('.eq-back').hidden }; });
      await page.goBack();
      await page.waitForTimeout(1200);
      const y2 = await page.evaluate(() => scrollY);
      check('an equation reference jumps to its equation', Math.abs(after.y - y0) > 10 && after.top >= -5 && after.top < after.h / 2,
            `scrollY ${Math.round(y0)} -> ${Math.round(after.y)}, target at ${Math.round(after.top)} px`);
      check('the floating back-to-text link appears after the jump', after.back, '');
      check('Back returns to the reading position', Math.abs(y2 - y0) < 10, `scrollY back at ${Math.round(y2)} (was ${Math.round(y0)})`);
    } else {
      check('equation references present', false, 'no a.eqref on the page');
    }
    const w0 = await page.evaluate(() => document.querySelector('article').getBoundingClientRect().left);
    await page.click('.toc-toggle');
    await page.waitForTimeout(200);
    const c1 = await page.evaluate(() => ({ nav: getComputedStyle(document.querySelector('nav.toc')).display,
      left: document.querySelector('article').getBoundingClientRect().left,
      exp: document.querySelector('.toc-toggle').getAttribute('aria-expanded') }));
    await page.reload({ waitUntil: 'load' });
    await page.waitForTimeout(300);
    const c2 = await page.evaluate(() => getComputedStyle(document.querySelector('nav.toc')).display);
    check('desktop: the button collapses the sidebar (aria-expanded) and the state survives a reload',
          c1.nav === 'none' && c1.left < w0 && c1.exp === 'false' && c2 === 'none', `${JSON.stringify(c1)} then ${c2}`);
    await page.click('.toc-toggle');
    await ctx.close();
  }

  // 3. phone, dark system setting: theme default, drawer behaviour
  {
    const { ctx, page } = await open(browser, { viewport: { width: 390, height: 844 }, colorScheme: 'dark' });
    check('theme follows a dark system setting', (await page.evaluate(() => document.documentElement.getAttribute('data-theme'))) === 'dark', '');
    const hidden = await page.evaluate(() => { const b = document.querySelector('nav.toc').getBoundingClientRect();
      return b.right <= 1 || getComputedStyle(document.querySelector('nav.toc')).visibility === 'hidden'; });
    await page.click('.toc-toggle');
    await page.waitForTimeout(400);
    const o = await page.evaluate(() => ({ open: document.documentElement.classList.contains('toc-open'),
      exp: document.querySelector('.toc-toggle').getAttribute('aria-expanded'),
      focusIn: document.querySelector('nav.toc').contains(document.activeElement),
      visible: document.querySelector('nav.toc').getBoundingClientRect().left >= -1 }));
    let inside = true;
    for (let i = 0; i < 60; i++) {
      await page.keyboard.press('Tab');
      const ok = await page.evaluate(() => document.querySelector('nav.toc').contains(document.activeElement)
        || document.activeElement === document.querySelector('.toc-toggle'));
      if (!ok) { inside = false; break; }
    }
    await page.keyboard.press('Escape');
    await page.waitForTimeout(300);
    const e = await page.evaluate(() => ({ open: document.documentElement.classList.contains('toc-open'),
      focus: document.activeElement === document.querySelector('.toc-toggle') }));
    await page.click('.toc-toggle');
    await page.waitForTimeout(300);
    await page.click('nav.toc a >> nth=3');
    await page.waitForTimeout(500);
    const l = await page.evaluate(() => document.documentElement.classList.contains('toc-open'));
    check('phone: the drawer is closed at first and opens from the menu button (aria-expanded, focus inside)',
          hidden && o.open && o.exp === 'true' && o.focusIn && o.visible, JSON.stringify({ hidden, ...o }));
    check('phone: Tab stays inside the open drawer', inside, '');
    check('phone: Esc closes the drawer and returns focus to the button', !e.open && e.focus, JSON.stringify(e));
    check('phone: a link closes the drawer', !l, '');
    await ctx.close();
  }

  // 4. no horizontal overflow at 360 and 390 px, light and dark
  for (const w of [360, 390]) {
    for (const scheme of ['light', 'dark']) {
      const { ctx, page } = await open(browser, { viewport: { width: w, height: 800 }, colorScheme: scheme });
      const sw = await page.evaluate(() => document.documentElement.scrollWidth);
      check(`no horizontal overflow at ${w} px (${scheme})`, sw <= w + 1, `scrollWidth ${sw}`);
      await ctx.close();
    }
  }
  await browser.close();
  const failed = results.filter(r => !r.ok);
  for (const r of results) console.log(`${r.ok ? 'ok  ' : 'FAIL'}  ${r.name}${r.detail ? ' (' + r.detail + ')' : ''}`);
  const out = opt('--json');
  if (out) fs.writeFileSync(out, JSON.stringify({ file, passed: !failed.length, results }, null, 1));
  console.log(`check_html_features: ${failed.length ? 'FAIL' : 'ok'} (${results.length - failed.length}/${results.length}) ${file}`);
  process.exit(failed.length ? 1 : 0);
})();
