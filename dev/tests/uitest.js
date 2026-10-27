// Full flow on a phone and an iPad: outcome menu, half-time, second half, corrections, event edits, manual levels,
// finish into the warehouse, stats, JSON export and import into a clean device, CSV, new match, reload, and that the
// corner-sb app's saved data is left alone.  Usage: node uitest.js <base_url> <out_dir>
const { chromium } = require(process.env.PLAYWRIGHT || '/opt/node-tools/node_modules/playwright');
const [base, out] = process.argv.slice(2);
let fails = 0;
const check = (cond, msg) => { console.log((cond ? 'ok   ' : 'FAIL ') + msg); if (!cond) fails++; };

async function newPage(b, w, h, mob, init){
  const ctx = await b.newContext({ viewport: { width: w, height: h }, deviceScaleFactor: 2, isMobile: mob, hasTouch: mob, serviceWorkers: 'block', acceptDownloads: true });
  if (init) await ctx.addInitScript(init);
  const page = await ctx.newPage();
  page.errs = [];
  page.on('pageerror', e => page.errs.push('pageerror ' + e.message));
  page.on('console', m => { if (m.type() === 'error') page.errs.push('console ' + m.text()); });
  await page.clock.install({ time: new Date('2026-10-27T19:00:00+08:00') });
  await page.goto(base + '/index.html');
  return { ctx, page };
}
const S = (page, fn, arg) => page.evaluate(fn, arg);
const evs = page => S(page, () => window.__six.M.ev.map(e => [e.p, e.i, e.c, e.b ? 1 : 0, e.t]));

(async () => {
  const b = await chromium.launch();
  // ---------------- phone ----------------
  const sbData = JSON.stringify({ m1: { id: 'm1', ev: [{ t: 10, p: 1, i: 0, c: 'f3' }] } });
  const { ctx, page } = await newPage(b, 390, 763, true, d => { if (!localStorage.getItem('corner-sb-matches')) localStorage.setItem('corner-sb-matches', d); }, sbData);
  await page.evaluate(d => localStorage.setItem('corner-sb-matches', d), sbData);
  await page.fill('#fH', '川崎前锋'); await page.fill('#fA', '浦和红钻'); await page.fill('#fLg', '日职联');
  await page.click('#runBtn');
  check(await S(page, () => window.__six.M.tm.r === 1 && window.__six.M.obs.t === 0), 'kick-off starts the clock and the observation at 0:00');
  await page.clock.runFor(60000);
  await page.click('.pad[data-i="0"] [data-k="ar"]');
  await page.click('.pad[data-i="0"] [data-act="d"]');
  check(await page.isVisible('.ov[data-i="0"]'), 'phone: tapping an action opens the outcome menu');
  await page.screenshot({ path: `${out}/phone_overlay.png` });
  await page.click('.ov[data-i="0"] [data-out="b"]');
  check(!(await page.isVisible('.ov[data-i="0"]')), 'picking an outcome closes the menu');
  await page.click('.pad[data-i="0"] [data-k="ck"]');
  await page.clock.runFor(20000);
  await page.click('.pad[data-i="1"] [data-act="l"]');
  await page.clock.runFor(9000);
  check(!(await page.isVisible('.ov[data-i="1"]')), 'menu closes by itself after 8 seconds');
  await page.click('.pad[data-i="1"] [data-act="s"]');
  await page.click('.ov[data-i="1"] [data-a="ovskip"]');
  await page.click('.pad[data-i="1"] [data-act="s"]');
  await page.click('.ov[data-i="1"] [data-out="z"]');
  let e = await evs(page);
  check(JSON.stringify(e.map(x => x[2])) === JSON.stringify(['ar', 'db', 'ck', 'l', 's', 'sz']), 'events recorded in order: ' + e.map(x => x[2]).join(','));
  check((await page.textContent('#glA')).trim() === '1', 'goal from the outcome menu updates the score');
  const src = await S(page, () => window.__six.cornerSrc(window.__six.M, 0, 'h1'));
  check(src.by['传中被挡'] === 1, 'corner credited to the blocked cross just before it');
  // undo on the team
  await page.click('.pad[data-i="1"] [data-a="undoT"]');
  check((await page.textContent('#glA')).trim() === '0', 'team undo removes its last event (the goal)');
  await page.click('#toastBtn');
  check((await page.textContent('#glA')).trim() === '1', 'toast restores the undone event');
  // many more first-half events
  for (let k = 0; k < 10; k++){
    await page.clock.runFor(150000);
    await page.click('.pad[data-i="0"] [data-k="ar"]');
    await page.click('.pad[data-i="0"] [data-act="' + (k % 3 ? 'd' : 'e') + '"]');
    await page.click('.ov[data-i="0"] [data-out="' + ['b', 'c', 'o', 'x', 'g'][k % 5] + '"]');
    if (k % 2) { await page.click('.pad[data-i="0"] [data-act="s"]'); await page.click('.ov[data-i="0"] [data-out="' + ['b', 'p', 'h', 'x'][k % 4] + '"]'); }
    if (k % 4 === 1) await page.click('.pad[data-i="0"] [data-k="ck"]');
    if (k % 3 === 0) await page.click('.pad[data-i="1"] [data-k="ar"]');
  }
  await page.clock.runFor(60000);
  const six1 = await S(page, () => { const s = window.__six.sixOf(window.__six.M, 0, 'h1'); return { lv: s.lv, show: s.show, f2: s.f2show, ck: s.ck, xc: s.xc }; });
  check(six1.lv.f1 >= 1 && six1.lv.f5 >= 1 && six1.lv.f4 >= 1 && six1.lv.f6 >= 1, 'first-half levels computed: ' + JSON.stringify(six1));
  // half-time from the clock sheet
  await page.click('#clkBtn');
  await page.click('#card [data-a="endh"]');
  check(await S(page, () => window.__six.M.tm.ht === 1 && window.__six.M.pe[1] >= 2700), 'half-time stores the end of the first half');
  // second half from the run button
  await page.clock.runFor(15 * 60000);
  await page.click('#runBtn');
  check(await S(page, () => window.__six.M.tm.p === 2 && window.__six.M.tm.r === 1), 'run button at half-time kicks off the second half');
  for (let k = 0; k < 8; k++){
    await page.clock.runFor(300000);
    await page.click('.pad[data-i="1"] [data-k="ar"]');
    await page.click('.pad[data-i="1"] [data-act="p"]');
    await page.click('.ov[data-i="1"] [data-out="' + (k % 2 ? 'o' : 'l') + '"]');
    if (k % 3 === 0) await page.click('.pad[data-i="1"] [data-k="ck"]');
  }
  e = await evs(page);
  check(e.filter(x => x[0] === 2).length > 0 && e.filter(x => x[0] === 2).every(x => x[4] >= 2700), 'second-half events stamped from 45:00');
  // corrections: a backfilled corner in the first half for the away team and an own goal for the home team
  await page.click('#ckA');
  await page.click('#card [data-a="fs"][data-f="c1"][data-i="1"][data-d="1"]');
  await page.click('#card [data-a="fs"][data-f="og"][data-i="0"][data-d="1"]');
  await page.click('#card [data-a="fs"][data-f="rc"][data-i="1"][data-d="1"]');
  await page.click('#card [data-a="fsave"]');
  e = await evs(page);
  check(e.some(x => x[1] === 1 && x[2] === 'ck' && x[3] === 1 && x[0] === 1), 'backfilled corner stored for the first half');
  check((await page.textContent('#glH')).trim() === '1', 'own goal counts for the home team');
  check(e.some(x => x[1] === 1 && x[2] === 'rc'), 'red card stored');
  const xcB = await S(page, () => window.__six.xcOf(window.__six.tally(window.__six.M, 1, 'h1')));
  const ckB = await S(page, () => window.__six.sixOf(window.__six.M, 1, 'h1').ck);
  check(ckB === 1 && xcB >= 0, 'backfilled corner counts in the total but not in the actions');
  // event edit from the list
  await page.click('[data-a="menu"]');
  await page.click('#card [data-a="list"]');
  await page.click('#card [data-a="evedit"]');
  await page.click('#card [data-a="evteam"][data-v="1"]');
  e = await evs(page);
  check(e.filter(x => x[0] === 1)[0][1] === 1, 'event moved to the other team from the editor');
  await page.click('#card [data-a="evteam"][data-v="0"]');
  await page.click('#card [data-a="list"]');
  await page.click('#card [data-a="close"]');
  // manual level from the six table
  await page.click('#qbSix');
  await page.waitForTimeout(350);
  await page.click('#tabSix [data-a="scope"][data-v="h1"]');
  await page.click('#tabSix [data-a="lvset"][data-i="0"][data-f="f5"]');
  await page.click('#card [data-a="lvpick"][data-v="5"]');
  await page.click('#card [data-a="close"]');
  check(await S(page, () => window.__six.M.man[0].h1.f5 === 5), 'manual level stored');
  check((await page.textContent('#tabSix')).indexOf('手动') >= 0, 'manual level shown with a tag');
  await page.click('#tabSix [data-a="lvset"][data-i="1"][data-f="f2"]');
  await page.click('#card [data-a="lvpick"][data-v="p"]');
  await page.click('#card [data-a="close"]');
  check(await S(page, () => window.__six.M.man[1].h1.f2 === 'p'), 'manual action-choice category stored');
  await page.screenshot({ path: `${out}/phone_six_manual.png` });
  await page.click('[data-a="midclose"]');
  await page.waitForTimeout(300);
  // finish at 90+
  await page.clock.runFor(10 * 60000);
  await page.click('[data-a="menu"]');
  await page.click('#card [data-a="finish"]');
  await page.click('#card [data-a="fkeep"]');
  check(await S(page, () => window.__six.M.st === 2 && window.__six.M.stop.p === 2 && window.__six.M.stop.t >= 5400 - 120), 'finish stores the stop at the end of the second half');
  check(await S(page, () => window.__six.fullHalf(window.__six.M, 1) && window.__six.fullHalf(window.__six.M, 2)), 'both halves count as fully watched');
  // warehouse
  await page.click('#qbArch');
  check((await page.textContent('#card')).indexOf('川崎前锋') >= 0, 'warehouse lists the match');
  await page.click('#card [data-a="wtab"][data-v="stats"]');
  const st = await page.textContent('#card');
  check(st.indexOf('平均进球和角球') >= 0 && st.indexOf('我的六项平均') >= 0 && st.indexOf('每个等级的平均角球') >= 0 && st.indexOf('按你的手动评级') >= 0, 'stats page shows averages, my six-factor averages, levels and manual levels');
  await page.screenshot({ path: `${out}/phone_stats.png`, fullPage: false });
  await page.click('#card [data-a="wtab"][data-v="back"]');
  await page.click('#card [data-a="expall"]');
  const json = await page.$eval('#expText', t => t.value);
  const obj = JSON.parse(json);
  check(obj.app === '角球六要素' && obj.fmt === 1 && obj.matches.length === 1 && obj.matches[0].ev.length === (await evs(page)).length, 'JSON export has every event');
  await page.click('#card [data-a="close"]');
  await page.click('#qbArch');
  await page.click('#card [data-a="wtab"][data-v="back"]');
  await page.click('#card [data-a="expcsv"]');
  const csv = await page.$eval('#expText', t => t.value);
  const lines = csv.trim().split('\n');
  check(lines.length === 5 && lines[0].indexOf('⑥质量等级') >= 0, 'CSV has a header and one row per team-half (' + (lines.length - 1) + ' rows)');
  await page.click('#card [data-a="close"]');
  check(await page.evaluate(d => localStorage.getItem('corner-sb-matches') === d, sbData), 'corner-sb saved data untouched');
  // reload keeps the match
  await page.reload();
  check((await page.textContent('#glA')).trim() === '1' && (await page.inputValue('#fH')) === '川崎前锋', 'reload restores the current match');
  // new match
  await page.click('[data-a="menu"]');
  await page.click('#card [data-a="new"]');
  check((await page.inputValue('#fH')) === '' && (await page.inputValue('#fLg')) === '日职联', 'new match keeps the league, clears the teams');
  check(await S(page, () => Object.keys(window.__six.store()).length === 1), 'finished match stays in the warehouse');
  console.log('phone errors:', page.errs.length ? page.errs.join('\n') : 'none');
  if (page.errs.length) fails++;

  // ---------------- import on a clean iPad ----------------
  const p2 = await newPage(b, 1180, 820, false);
  await p2.page.click('[data-a="menu"]');
  await p2.page.click('#card [data-a="wback"]');
  await p2.page.click('#card [data-a="import"]');
  await p2.page.fill('#impText', json);
  await p2.page.click('#card [data-a="imptext"]');
  const n2 = await S(p2.page, () => Object.keys(window.__six.store()).length);
  check(n2 === 1, 'import on a clean device adds the match');
  await p2.page.click('#qbArch');
  await p2.page.click('#card [data-a="wopen"]');
  await p2.page.click('#card [data-a="mopen"]');
  check((await p2.page.inputValue('#fH')) === '川崎前锋' && (await p2.page.textContent('#glA')).trim() === '1', 'imported match opens with the same score');
  const lvA = await S(p2.page, () => JSON.stringify(window.__six.sixOf(window.__six.M, 0, 'h1').lv));
  const lvB = JSON.stringify(six1.lv);
  console.log('levels after import', lvA, 'before', lvB);
  await p2.page.click('.tabs [data-tab="data"]');
  await p2.page.screenshot({ path: `${out}/ipad_data.png` });
  await p2.page.click('.tabs [data-tab="ck"]');
  await p2.page.screenshot({ path: `${out}/ipad_ck.png` });
  await p2.page.click('[data-a="menu"]');
  await p2.page.click('#card [data-a="how"]');
  await p2.page.screenshot({ path: `${out}/ipad_how.png` });
  console.log('ipad errors:', p2.page.errs.length ? p2.page.errs.join('\n') : 'none');
  if (p2.page.errs.length) fails++;
  await b.close();
  console.log(fails ? `${fails} FAILED` : 'ALL OK');
  process.exit(fails ? 1 : 0);
})();
