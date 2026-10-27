// Smoke test: loads on four screen sizes, records a short match with a fake clock, checks for console errors.
const { chromium } = require(process.env.PLAYWRIGHT || '/opt/node-tools/node_modules/playwright');
const [base, out] = process.argv.slice(2);
(async () => {
  const b = await chromium.launch();
  const sizes = [['ipadL', 1180, 820, false], ['ipadP', 820, 1180, false], ['iphone', 390, 844 - 47 - 34, true], ['se', 375, 667 - 20, true]];
  for (const [name, w, h, mob] of sizes){
    const ctx = await b.newContext({ viewport: { width: w, height: h }, deviceScaleFactor: 2, isMobile: mob, hasTouch: mob, serviceWorkers: 'block' });
    const page = await ctx.newPage();
    const errs = [];
    page.on('pageerror', e => errs.push('pageerror ' + e.message));
    page.on('console', m => { if (m.type() === 'error') errs.push('console ' + m.text()); });
    await page.clock.install({ time: new Date('2026-10-27T19:00:00+08:00') });
    await page.goto(base + '/index.html');
    await page.fill('#fLg', '日职联');
    await page.fill('#fH', '鹿岛鹿角');
    await page.fill('#fA', '横滨水手');
    await page.screenshot({ path: `${out}/${name}_0.png` });
    await page.click('#runBtn');
    // 30 minutes of play: taps spread over time
    const plan = mob
      ? [['ar', 0], ['d', 0, 'b'], ['ck', 0], ['ar', 1], ['l', 1, 'p'], ['ck', 1], ['ar', 0], ['e', 0, 'c'], ['ar', 0], ['s', 0, 'h'], ['ar', 0], ['p', 0, 'l'], ['ar', 1], ['d', 1, 'o'], ['s', 1, 'z'], ['ar', 0], ['d', 0], ['ar', 0], ['l', 0, 'x']]
      : [['ar', 0], ['db', 0], ['ck', 0], ['ar', 1], ['lp', 1], ['ck', 1], ['ar', 0], ['ec', 0], ['ar', 0], ['sh', 0], ['ar', 0], ['pl', 0], ['ar', 1], ['do', 1], ['sz', 1], ['ar', 0], ['dc', 0], ['ar', 0], ['lx', 0]];
    for (const step of plan){
      await page.clock.runFor(90 * 1000);
      const [code, i, out2] = step;
      if (mob && code.length === 1){
        await page.click(`.pad[data-i="${i}"] [data-act="${code}"]`);
        if (out2) await page.click(`.ov[data-i="${i}"] [data-out="${out2}"]`);
        else await page.clock.runFor(9000);
      } else {
        await page.click(`.pad[data-i="${i}"] [data-k="${code}"]`);
      }
    }
    await page.clock.runFor(16000);
    await page.screenshot({ path: `${out}/${name}_1.png` });
    const state = await page.evaluate(() => { const S = window.__six; const M = S.M; return { n: M.ev.length, codes: M.ev.map(e => e.c).join(','), mins: S.minsOf(M, 'h1').toFixed(1), six0: JSON.stringify(S.sixOf(M, 0, 'h1').show), proj: JSON.stringify(S.projection(M, 0)) }; });
    console.log(name, JSON.stringify(state));
    if (mob){ await page.click('#qbSix'); await page.waitForTimeout(400); await page.screenshot({ path: `${out}/${name}_six.png` }); await page.click('[data-a="midclose"]'); await page.waitForTimeout(300); }
    // sheets
    for (const a of ['menu', 'defs']){ await page.evaluate(x => document.querySelector(`[data-a="${x}"]`).click(), a); await page.waitForTimeout(150); await page.screenshot({ path: `${out}/${name}_${a}.png` }); await page.click('#card [data-a="close"]'); }
    console.log(name, errs.length ? errs.join('\n') : 'no errors');
    await ctx.close();
  }
  await b.close();
})();
