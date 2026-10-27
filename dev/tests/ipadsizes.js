// Older and smaller iPads: the three-column (or two-column portrait) layout fits without horizontal scroll.
const { chromium } = require(process.env.PLAYWRIGHT || '/opt/node-tools/node_modules/playwright');
const [base, out] = process.argv.slice(2);
(async () => {
  const b = await chromium.launch();
  for (const [name, w, h] of [['ipad1024', 1024, 768 - 20], ['ipadmini_l', 1133, 744 - 24], ['ipadmini_p', 744, 1133 - 24], ['ipad10', 1080, 810 - 24], ['ipadpro13', 1376, 1032 - 24]]){
    const ctx = await b.newContext({ viewport: { width: w, height: h }, deviceScaleFactor: 2, hasTouch: true, serviceWorkers: 'block' });
    const page = await ctx.newPage();
    await page.goto(base + '/index.html');
    await page.fill('#fH', '名古屋鲸八'); await page.fill('#fA', '广岛三箭');
    await page.click('#runBtn');
    for (const k of ['ar', 'db', 'ck', 'sp', 'ec']) await page.click(`.pad[data-i="0"] [data-k="${k}"]`);
    const r = await page.evaluate(() => {
      const de = document.documentElement;
      const keys = [...document.querySelectorAll('.pad .k')].map(z => z.getBoundingClientRect());
      return { sw: de.scrollWidth, cw: de.clientWidth, minW: Math.round(Math.min(...keys.map(k => k.width))), minH: Math.round(Math.min(...keys.map(k => k.height))), boardBottom: Math.round(Math.max(...keys.map(k => k.bottom))), stripTop: Math.round(document.querySelector('.strip').getBoundingClientRect().top) };
    });
    console.log(name, w + 'x' + h, JSON.stringify(r), r.sw <= r.cw ? 'no h-scroll' : 'H-SCROLL');
    await page.screenshot({ path: `${out}/${name}.png` });
    await ctx.close();
  }
  await b.close();
})();
