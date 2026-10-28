// After a match is finished: the record keys give way to a "这场已经结束" card with 开始新比赛; play, record keys,
// the clock and the team names no longer reopen or rename the finished match; the next match starts cleanly.
// Usage: node uitest_end.js <base_url> <out_dir>
const { chromium } = require(process.env.PLAYWRIGHT || '/opt/node-tools/node_modules/playwright');
const [base, out] = process.argv.slice(2);
let fails = 0;
const check = (cond, msg) => { console.log((cond ? 'ok   ' : 'FAIL ') + msg); if (!cond) fails++; };
const S = (p, fn, arg) => p.evaluate(fn, arg);
const cur = p => S(p, () => { const M = window.__six.M; return { id: M.id, st: M.st, h: M.h, a: M.a, lg: M.lg, ev: M.ev.length, r: M.tm.r, b: M.tm.b }; });
const stored = (p, id) => S(p, id => { const s = JSON.parse(localStorage.getItem('corner-six-matches')); const m = s[id]; return m ? { st: m.st, h: m.h, a: m.a, ev: m.ev.length, keep: m.keep } : null; }, id);

async function play(b, w, h, mob){
  const ctx = await b.newContext({ viewport: { width: w, height: h }, deviceScaleFactor: 2, isMobile: mob, hasTouch: mob, serviceWorkers: 'block' });
  const p = await ctx.newPage();
  p.errs = [];
  p.on('pageerror', e => p.errs.push('pageerror ' + e.message));
  p.on('console', m => { if (m.type() === 'error') p.errs.push('console ' + m.text()); });
  await p.clock.install({ time: new Date('2026-10-28T10:00:00Z') });
  await p.goto(base + '/index.html');
  await p.fill('#fLg', 'J1'); await p.fill('#fH', '鹿岛鹿角'); await p.fill('#fA', '横滨水手');
  await p.click('#runBtn');
  await p.clock.runFor(6 * 60000);
  await p.click('.pad[data-i="0"] [data-k="ar"]');
  await p.click('.pad[data-i="0"] [data-k="ck"]');
  await p.click('[data-a="menu"]'); await p.click('#card [data-a="finish"]'); await p.click('#card [data-a="fkeep"]');
  return { ctx, p };
}

(async () => {
  const b = await chromium.launch();
  // ---------------- phone
  let { ctx, p } = await play(b, 390, 763, true);
  const fin = await cur(p);
  check(fin.st === 2, 'match finished');
  check(await p.isVisible('.endc [data-a="new"]'), 'ended card with 开始新比赛 replaces the record keys');
  check((await p.textContent('.endc')).indexOf('鹿岛鹿角 0–0 横滨水手') >= 0 && (await p.textContent('.endc')).indexOf('已加入比赛仓库') >= 0, 'card shows the result and that it is in the warehouse');
  check((await p.textContent('#toastBtn')) === '开始新比赛' && await p.isVisible('#toastBtn'), 'finish toast offers 开始新比赛');
  await p.screenshot({ path: `${out}/end_phone.png` });
  // play does not reopen
  await p.click('#runBtn'); await p.clock.runFor(3000);
  let c = await cur(p);
  check(c.id === fin.id && c.st === 2 && !c.r, 'play on a finished match does not reopen it or run its clock');
  check((await p.textContent('#toastMsg')).indexOf('已经结束') >= 0 && (await p.textContent('#toastBtn')) === '开始新比赛', 'play explains and offers 开始新比赛');
  // names cannot be overwritten
  check(await p.$eval('#fH', el => el.readOnly), 'team names are read-only on a finished match');
  await p.click('#fH');
  check((await p.textContent('#toastMsg')).indexOf('已经结束') >= 0, 'tapping a name explains it');
  await p.keyboard.type('浦和');
  check((await stored(p, fin.id)).h === '鹿岛鹿角', 'finished match keeps its name in the warehouse');
  // clock does not reopen either
  await p.click('#clkBtn');
  check(!(await p.isVisible('#card')) || (await p.textContent('#card')).indexOf('比赛时间') < 0, 'clock button does not open the time sheet on a finished match');
  check((await cur(p)).st === 2, 'still finished');
  // start the next match from the card
  await p.click('.endc [data-a="new"]');
  c = await cur(p);
  check(c.id !== fin.id && c.st === 1 && c.h === '' && c.a === '' && c.lg === 'J1' && c.ev === 0 && !c.b, 'new match: empty teams, league kept, no events, clock at 0');
  check(await p.isVisible('.pad[data-i="0"] [data-k="ar"]') && !(await p.isVisible('.endc')), 'record keys are back');
  const old = await stored(p, fin.id);
  check(old && old.st === 2 && old.h === '鹿岛鹿角' && old.ev === 2 && old.keep === 1, 'finished match is untouched in the warehouse');
  await p.fill('#fH', '浦和红钻'); await p.fill('#fA', '大阪钢巴');
  await p.click('#runBtn'); await p.clock.runFor(61000);
  c = await cur(p);
  const clk = (await p.textContent('#clkT')).trim(); check(c.h === '浦和红钻' && c.r === 1 && /^01:0\d$/.test(clk), 'next match records and its clock starts at 00:00 (' + JSON.stringify(c) + ' ' + clk + ')');
  // finish again and use the toast button this time
  await p.click('.pad[data-i="1"] [data-k="ar"]');
  await p.click('[data-a="menu"]'); await p.click('#card [data-a="finish"]'); await p.click('#card [data-a="fkeep"]');
  const fin2 = await cur(p);
  await p.click('#toastBtn');
  c = await cur(p);
  check(c.id !== fin2.id && c.st === 1, 'toast button starts the next match');
  // reopen still works from the warehouse card
  await S(p, id => { }, null);
  await p.click('[data-a="menu"]'); await p.click('#card [data-a="arch"]');
  await p.click('#card [data-a="wopen"][data-id="' + fin.id + '"]');
  await p.click('#card [data-a="mopen"][data-id="' + fin.id + '"]');
  check((await cur(p)).id === fin.id && await p.isVisible('.endc'), 'opening a finished match from the warehouse shows the ended card');
  await p.click('.endc [data-a="reopen"]');
  c = await cur(p);
  check(c.id === fin.id && c.st === 1 && await p.isVisible('.pad[data-i="0"] [data-k="ar"]'), '“重新打开” makes it recordable again');
  // join midway from a finished match starts a new one
  await p.click('[data-a="menu"]'); await p.click('#card [data-a="finish"]'); await p.click('#card [data-a="fkeep"]');
  await p.click('[data-a="menu"]'); await p.click('#card [data-a="join"]');
  c = await cur(p);
  check(c.id !== fin.id && await p.isVisible('#card [data-a="jgo"]'), '中途加入 from a finished match opens the join sheet for a new match');
  check((await stored(p, fin.id)).st === 2, 'the finished match stays finished');
  console.log('phone errors:', p.errs.length ? p.errs.join('\n') : 'none'); if (p.errs.length) fails++;
  await ctx.close();

  // ---------------- iPad landscape and portrait
  for (const [w, h, tag] of [[1180, 820, 'L'], [820, 1180, 'P'], [1024, 748, 'S']]){
    ({ ctx, p } = await play(b, w, h, false));
    const r = await S(p, () => { const c = document.querySelector('.endc').getBoundingClientRect(), m = document.querySelector('#mid').getBoundingClientRect(); return { cw: c.width, ch: c.height, mid: m.width, sw: document.documentElement.scrollWidth, vw: document.documentElement.clientWidth, overlap: !(c.right <= m.left + 1 || c.bottom <= m.top + 1) }; });
    check(r.cw > 250 && r.sw <= r.vw && !r.overlap, `iPad ${tag}: ended card ${Math.round(r.cw)}px wide beside the six table (${Math.round(r.mid)}px), no overlap, no sideways scroll`);
    await p.screenshot({ path: `${out}/end_ipad${tag}.png` });
    await p.click('.endc [data-a="new"]');
    check(await p.isVisible('.pad[data-i="1"] [data-k="ar"]'), `iPad ${tag}: both teams' keys back for the new match`);
    console.log('ipad errors:', p.errs.length ? p.errs.join('\n') : 'none'); if (p.errs.length) fails++;
    await ctx.close();
  }
  await b.close();
  console.log(fails ? fails + ' FAILED' : 'ALL OK');
  process.exit(fails ? 1 : 0);
})();
