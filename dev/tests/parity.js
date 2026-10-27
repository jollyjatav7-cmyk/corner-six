// The app's six-factor numerators and denominators equal the Python pipeline's for real StatsBomb team-halves.
// Usage: node parity.js <base_url> <cases.json>
const { chromium } = require(process.env.PLAYWRIGHT || '/opt/node-tools/node_modules/playwright');
const fs = require('fs');
const [base, file] = process.argv.slice(2);
(async () => {
  const cases = JSON.parse(fs.readFileSync(file, 'utf8'));
  const b = await chromium.launch(); const page = await (await b.newContext({ serviceWorkers: 'block' })).newPage();
  await page.goto(base + '/index.html');
  let bad = 0;
  for (const c of cases){
    const js = await page.evaluate(c => {
      const S = window.__six, m = { ev: c.ev.map((e, k) => Object.assign({ k: k + 1 }, e)) };
      const P = S.parts(S.tally(m, c.side, 'h' + c.per), S.tally(m, 1 - c.side, 'h' + c.per), 45);
      return { f3: P.f3, f4: P.f4, f5: P.f5, f6: P.f6 };
    }, c);
    for (const k of ['f3', 'f4', 'f5', 'f6']){
      if (Math.abs(js[k][0] - c.py[k][0]) > 1e-9 || Math.abs(js[k][1] - c.py[k][1]) > 1e-9){ bad++; console.log('MISMATCH', c.mid, c.per, c.side, k, js[k], c.py[k]); }
    }
  }
  console.log(bad ? bad + ' mismatches' : `parity OK on ${cases.length} team-halves`);
  await b.close();
})();
