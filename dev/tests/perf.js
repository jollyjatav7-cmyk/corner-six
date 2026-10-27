// Stress: 120 finished matches with ~300 events each. Time the first render, a tap, the stats page, and the
// "my records" baseline. Usage: node perf.js <base_url>
const { chromium } = require(process.env.PLAYWRIGHT || '/opt/node-tools/node_modules/playwright');
const [base] = process.argv.slice(2);
(async () => {
  const b = await chromium.launch();
  const ctx = await b.newContext({ viewport: { width: 390, height: 763 }, isMobile: true, hasTouch: true, serviceWorkers: 'block' });
  const page = await ctx.newPage();
  const errs = []; page.on('pageerror', e => errs.push(e.message));
  await page.goto(base + '/index.html');
  const bytes = await page.evaluate(() => {
    const codes = ['ar', 'ar', 'ar', 'db', 'dc', 'do', 'dx', 'dg', 'eb', 'ec', 'eo', 'po', 'pl', 'pl', 'lb', 'lp', 'lh', 'lx', 'sb', 'sp', 'sh', 'sx', 'ck', 'ar', 'po', 'd', 's'];
    const st = {};
    let seed = 7; const rnd = () => (seed = (seed * 16807) % 2147483647) / 2147483647;
    for (let m = 0; m < 120; m++){
      const ev = [];
      for (let k = 0; k < 300; k++){ const p = k < 150 ? 1 : 2; ev.push({ t: (p - 1) * 2700 + Math.floor(rnd() * 2820), p, i: rnd() < 0.5 ? 0 : 1, c: codes[Math.floor(rnd() * codes.length)] }); }
      if (m % 7 === 0) ev.push({ t: 1000, p: 1, i: 0, c: 'sz' });
      st['x' + m] = { id: 'x' + m, c: 1, u: 1 + m, d: '2026-10-' + String(1 + m % 27).padStart(2, '0'), lg: ['日职联', '英超', '德甲'][m % 3], h: '主' + m, a: '客' + m, st: 2, keep: 1,
        tm: { p: 2, b: 5640, r: 0, at: 0, ht: 0 }, pe: { 1: 2820, 2: 5640 }, obs: { p: 1, t: 0 }, stop: { p: 2, t: 5640 }, man: {}, note: '', ev };
    }
    const s = JSON.stringify(st);
    localStorage.setItem('corner-six-matches', s);
    return s.length;
  });
  console.log('stored bytes', bytes);
  let t0 = Date.now();
  await page.reload();
  await page.waitForSelector('.pad[data-i="0"] [data-k="ar"]');
  console.log('reload+render ms', Date.now() - t0);
  await page.click('#runBtn');
  t0 = Date.now();
  for (let k = 0; k < 20; k++) await page.click('.pad[data-i="0"] [data-k="ar"]');
  console.log('20 taps ms', Date.now() - t0);
  t0 = Date.now();
  await page.click('#qbArch'); await page.click('#card [data-a="wtab"][data-v="stats"]');
  console.log('stats page ms', Date.now() - t0);
  const txt = await page.textContent('#card');
  console.log('stats has rows:', txt.indexOf('每个等级的平均角球') >= 0, txt.slice(txt.indexOf('我的六项平均'), txt.indexOf('我的六项平均') + 30));
  await page.click('#card [data-a="close"]');
  await page.evaluate(() => { const p = JSON.parse(localStorage.getItem('corner-six-pref') || '{}'); p.base = 'mine'; localStorage.setItem('corner-six-pref', JSON.stringify(p)); });
  await page.reload(); await page.waitForSelector('.pad[data-i="0"] [data-k="ar"]');
  t0 = Date.now();
  for (let k = 0; k < 20; k++) await page.click('.pad[data-i="1"] [data-k="ar"]');
  console.log('20 taps with my-records baseline ms', Date.now() - t0);
  const mine = await page.evaluate(() => document.querySelector('#hud') ? document.querySelector('.basel') && document.querySelector('.basel').textContent : '');
  console.log('baseline label:', mine);
  console.log('errors:', errs.length ? errs.join('\n') : 'none');
  await b.close();
})();
