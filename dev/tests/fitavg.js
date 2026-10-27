// Average marks fit: with two-digit counts and averages, nothing on a record button overflows (phones with and
// without the video band, iPads).  Usage: node fitavg.js <base_url> <out_dir>
const { chromium } = require(process.env.PLAYWRIGHT || '/opt/node-tools/node_modules/playwright');
const [base, out] = process.argv.slice(2);
let bad = 0;
(async () => {
  const b = await chromium.launch();
  const sizes = [['iPhoneSE', 375, 647, true], ['iPhone12mini', 375, 728, true], ['iPhone15', 393, 759, true], ['ProMax', 430, 839, true],
    ['ipad1024', 1024, 748, false], ['ipadmini_p', 744, 1109, false], ['ipadmini_l', 1133, 720, false], ['ipad10', 1080, 786, false]];
  for (const [name, w, h, mob] of sizes){
    for (const pip of mob ? [null, { pos: 'top', h: 230 }, { pos: 'top', h: 150 }] : [null]){
      const ctx = await b.newContext({ viewport: { width: w, height: h }, deviceScaleFactor: 2, isMobile: mob, hasTouch: mob, serviceWorkers: 'block' });
      if (pip) await ctx.addInitScript(p => localStorage.setItem('corner-six-pip', p), JSON.stringify(pip));
      const page = await ctx.newPage();
      await page.clock.install({ time: new Date('2026-10-28T10:00:00Z') });
      await page.goto(base + '/index.html');
      await page.click(pip ? '#hudS' : '#runBtn');
      await page.clock.runFor(42 * 60000);
      // two-digit counts on the busiest buttons
      await page.evaluate(mob => {
        const M = window.__six.M; let k = 90000;
        const add = (c, n) => { for (let j = 0; j < n; j++) M.ev.push({ t: 60 + j * 20, p: 1, i: 0, c: c, k: ++k }); };
        add('ar', 31); add('e', 12); add('p', 18); add(mob ? 'd' : 'dc', 14); add('ck', 11); add('lx', 10);
      }, mob);
      await page.click('.pad[data-i="1"] [data-k="ar"]');   // re-render with the new counts
      const r = await page.evaluate(() => {
        const els = [...document.querySelectorAll('.pad .k, .pad .rl')].filter(z => z.offsetParent);
        const over = els.filter(z => z.scrollWidth > z.clientWidth + 1 || [...z.querySelectorAll('.av')].some(a => { const x = a.getBoundingClientRect(), y = z.getBoundingClientRect(); return x.width && (x.left < y.left - 0.5 || x.right > y.right + 0.5); }));
        const st = document.querySelector('.strip').getBoundingClientRect();
        const keys = [...document.querySelectorAll('.pad .k')].filter(z => z.offsetParent).map(z => z.getBoundingClientRect());
        return { n: els.length, over: over.map(z => z.textContent.replace(/\s+/g, ' ').trim()).slice(0, 6), bottom: Math.max(...keys.map(k => k.bottom)), strip: st.top, sw: document.documentElement.scrollWidth, cw: document.documentElement.clientWidth };
      });
      const fit = r.bottom <= r.strip + 0.5 && r.sw <= r.cw;
      const tag = pip ? `pip-${pip.pos}${pip.h}` : 'nopip';
      if (r.over.length || !fit) bad++;
      console.log(`${name} ${tag}: ${r.n} keys, overflow ${r.over.length ? JSON.stringify(r.over) : 'none'}, ${fit ? 'fits' : 'DOES NOT FIT bottom=' + Math.round(r.bottom) + ' strip=' + Math.round(r.strip)}`);
      if (name === 'iPhoneSE' || name === 'ipad1024' || name === 'ipadmini_p') await page.screenshot({ path: `${out}/fitavg_${name}_${tag}.png` });
      await ctx.close();
    }
  }
  await b.close();
  console.log(bad ? bad + ' problems' : 'ALL FIT');
})();
