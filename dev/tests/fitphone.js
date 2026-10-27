// Phone fit check: every recording key ends above the bottom bar and is big enough to hit, also with the
// video-window band at the top or bottom, and the outcome menu fits in its column.
// Usage: node fitphone.js <base_url> <out_dir>
const { chromium } = require(process.env.PLAYWRIGHT || '/opt/node-tools/node_modules/playwright');
const [base, out] = process.argv.slice(2);
let bad = 0;
(async () => {
  const b = await chromium.launch();
  for (const [name, w, h] of [['iPhone15', 393, 852 - 59 - 34], ['iPhone13', 390, 844 - 47 - 34], ['iPhoneSE', 375, 667 - 20], ['ProMax', 430, 932 - 59 - 34], ['iPhone12mini', 375, 812 - 50 - 34]]){
    for (const pip of [null, { pos: 'top', h: 230 }, { pos: 'top', h: 190 }, { pos: 'bot', h: 190 }, { pos: 'top', h: 150 }]){
      const ctx = await b.newContext({ viewport: { width: w, height: h }, deviceScaleFactor: 2, isMobile: true, hasTouch: true, serviceWorkers: 'block' });
      if (pip) await ctx.addInitScript(p => localStorage.setItem('corner-six-pip', p), JSON.stringify(pip));
      const page = await ctx.newPage();
      await page.goto(base + '/index.html');
      await page.click(pip ? '#hudS' : '#runBtn');
      await page.click('.pad[data-i="0"] [data-act="s"]');
      const r = await page.evaluate(() => {
        const keys = [...document.querySelectorAll('.pad .acts > .k')].filter(z => z.offsetParent).map(z => z.getBoundingClientRect());
        const outs = [...document.querySelectorAll('.ov:not([hidden]) .ov-b .k')].map(z => z.getBoundingClientRect());
        const st = document.querySelector('.strip').getBoundingClientRect(), band = document.querySelector('#pipBand').getBoundingClientRect(), hud = document.querySelector('#hud').getBoundingClientRect();
        return { bottom: Math.max(...keys.map(k => k.bottom)), minH: Math.min(...keys.map(k => k.height)), outMin: Math.min(...outs.map(k => k.height)), outN: outs.length,
          strip: st.top, stripB: st.bottom, band: [band.top, band.bottom], hudT: hud.top, hudH: hud.height };
      });
      const fit = r.bottom <= r.strip + 0.5;
      const pipOk = !pip ? true : pip.pos === 'top' ? r.hudT >= r.band[1] - 0.5 : r.stripB <= r.band[0] + 0.5;
      const big = r.minH >= 36 && r.outMin >= 36;
      if (!fit || !pipOk || !big) bad++;
      const tag = pip ? `pip-${pip.pos}${pip.h}` : 'nopip';
      console.log(`${name} ${w}x${h} ${tag}: keysBottom=${Math.round(r.bottom)} stripTop=${Math.round(r.strip)} ${fit ? 'OK' : 'OVERLAP'} ${pipOk ? '' : 'PIP-OVERLAP'} smallestKey=${Math.round(r.minH)} smallestOutcome=${Math.round(r.outMin)} (${r.outN}) ${big ? '' : 'TOO-SMALL'}`);
      if (name === 'iPhoneSE' || name === 'iPhone15') await page.screenshot({ path: `${out}/fit_${name}_${tag}.png` });
      await ctx.close();
    }
  }
  await b.close();
  console.log(bad ? bad + ' problems' : 'ALL FIT');
})();
