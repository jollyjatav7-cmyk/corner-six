// v4: live counts against the average on the buttons, the data tab, cross-to-header in one flow (phone),
// and the corner estimate on corner-sb's model (score, red cards, time) from kick-off.
// Usage: node uitest_v4.js <base_url> <out_dir>
const { chromium } = require(process.env.PLAYWRIGHT || '/opt/node-tools/node_modules/playwright');
const [base, out] = process.argv.slice(2);
let fails = 0;
const check = (cond, msg) => { console.log((cond ? 'ok   ' : 'FAIL ') + msg); if (!cond) fails++; };
const S = (p, fn, arg) => p.evaluate(fn, arg);

async function open(b, w, h, mob){
  const ctx = await b.newContext({ viewport: { width: w, height: h }, deviceScaleFactor: 2, isMobile: mob, hasTouch: mob, serviceWorkers: 'block' });
  const p = await ctx.newPage();
  p.errs = [];
  p.on('pageerror', e => p.errs.push('pageerror ' + e.message));
  p.on('console', m => { if (m.type() === 'error') p.errs.push('console ' + m.text()); });
  await p.clock.install({ time: new Date('2026-10-28T10:00:00Z') });
  await p.goto(base + '/index.html');
  await p.fill('#fH', '鹿岛鹿角'); await p.fill('#fA', '横滨水手');
  return { ctx, p };
}
const proj = (p, i) => S(p, i => window.__six.projection(window.__six.M, i), i);
const codes = p => S(p, () => window.__six.M.ev.map(e => e.c));

(async () => {
  const b = await chromium.launch();
  // ---------------- phone
  let { ctx, p } = await open(b, 390, 763, true);
  check((await p.textContent('.hud')).indexOf('预计：开球后') >= 0, 'before kick-off the summary says the estimate starts at kick-off');
  await p.click('#runBtn');
  await p.clock.runFor(60000);
  let pj = await proj(p, 0);
  check(pj && pj.half > 1 && pj.half < 4 && pj.ft > 3 && pj.ft < 8, 'estimate right after kick-off (no 8-minute wait): home first half ' + (pj && pj.half.toFixed(2)) + ', match ' + (pj && pj.ft.toFixed(2)));
  check(/预计上半 <b>|预计上半/.test(await p.textContent('.hud')), 'summary bar shows the estimate');
  const t0 = Date.now();
  await p.clock.runFor(9 * 60000);
  // pace on the buttons after 10 minutes: current and all-team average per 10 minutes, and a level
  const txt = async sel => (await p.textContent(sel)).replace(/\s+/g, ' ');
  let arTxt = await txt('.pad[data-i="0"] [data-k="ar"]');
  check(/现在0\.0 平均3\.7 次\/10分/.test(arTxt) && arTxt.indexOf('很慢') >= 0, 'arrival button: current vs all-team average per 10 minutes, 很慢 with none in 10 minutes: ' + arTxt);
  check((await txt('.pad[data-i="1"] [data-k="ar"]')).indexOf('平均3.7') >= 0, 'both teams compared with the same all-team average');
  for (let k = 0; k < 9; k++) await p.click('.pad[data-i="0"] [data-k="ar"]');
  arTxt = await txt('.pad[data-i="0"] [data-k="ar"]');
  check(/现在9\.\d/.test(arTxt) && arTxt.indexOf('很快') >= 0, '9 arrivals in 10 minutes: 现在 9.x, 很快: ' + arTxt);
  const dTxt = await txt('.pad[data-i="0"] [data-act="d"]');
  check(dTxt.indexOf('平均1.5') >= 0 && dTxt.indexOf('还早') >= 0, 'cross button: average 1.5 per 10 minutes, too early for a level: ' + dTxt);
  await p.clock.runFor(16000);
  check((await txt('.pad[data-i="1"] [data-k="ar"]')).indexOf('现在0.0') >= 0, 'pace line refreshes as time passes');
  // cross reaches a team-mate, header saved: one flow
  await p.click('.pad[data-i="0"] [data-act="d"]');
  await p.click('.ov[data-i="0"] [data-out="o"]');
  check(await p.isVisible('.ov.fol[data-i="0"]'), 'after 到人 the box-shot outcomes pop up');
  check((await p.textContent('.ov.fol[data-i="0"] .ov-h')).indexOf('接着射门') >= 0, 'follow-up menu asks about the shot');
  await p.screenshot({ path: `${out}/v4_phone_follow.png` });
  await p.click('.ov.fol[data-i="0"] [data-out="p"]');
  let cs = await codes(p);
  check(cs.slice(-2).join() === 'do,sp', 'cross 到人 + header saved recorded as two events: ' + cs.slice(-2).join());
  check(!(await p.isVisible('.ov[data-i="0"]')), 'menu closes after the shot outcome');
  // cross reaches a team-mate, no shot
  await p.click('.pad[data-i="0"] [data-act="e"]');
  await p.click('.ov[data-i="0"] [data-out="o"]');
  await p.click('.ov.fol[data-i="0"] [data-a="ovskip"]');
  cs = await codes(p);
  check(cs[cs.length - 1] === 'eo' && !(await p.isVisible('.ov[data-i="0"]')), '“没有射门” records only the cross');
  // the follow-up menu closes by itself
  await p.click('.pad[data-i="0"] [data-act="d"]');
  await p.click('.ov[data-i="0"] [data-out="o"]');
  await p.clock.runFor(9000);
  cs = await codes(p);
  check(cs[cs.length - 1] === 'do' && !(await p.isVisible('.ov[data-i="0"]')), 'follow-up closes after 8 s without adding a shot');
  // other outcomes do not trigger it
  await p.click('.pad[data-i="0"] [data-act="d"]');
  await p.click('.ov[data-i="0"] [data-out="b"]');
  check(!(await p.isVisible('.ov[data-i="0"]')), 'a blocked cross does not ask about a shot');
  // score effects in the estimate
  await p.clock.runFor(60000);
  const before = [await proj(p, 0), await proj(p, 1)];
  await p.click('.pad[data-i="0"] [data-act="s"]');
  await p.click('.ov[data-i="0"] [data-out="z"]');
  await p.clock.runFor(11000);
  const after = [await proj(p, 0), await proj(p, 1)];
  check(after[0].per10 < before[0].per10 * 0.9 && after[1].per10 > before[1].per10 * 1.03, 'after the home goal: home corner pace down (' + before[0].per10.toFixed(2) + ' -> ' + after[0].per10.toFixed(2) + '), away up (' + before[1].per10.toFixed(2) + ' -> ' + after[1].per10.toFixed(2) + ')');
  check(after[0].fac.d === 1 && Math.abs(after[0].fac.st - 0.768) < 0.01 && Math.abs(after[1].fac.st - 1.124) < 0.01, 'factors: leading x0.77, trailing x1.12');
  await p.click('#qbSix'); await p.waitForTimeout(350);
  const six = await p.textContent('#tabSix');
  check(six.indexOf('领先1球 ×0.77') >= 0 && six.indexOf('落后1球 ×1.12') >= 0 && six.indexOf('六项 ×') >= 0, 'six table shows the factors (领先1球 ×0.77 / 落后1球 ×1.12 / 六项 ×…)');
  check(six.indexOf('比分、时段＋六项') >= 0, 'estimate labelled: score, time + six factors');
  await p.evaluate(() => { const m = document.querySelector('#mid'); m.scrollTop = m.scrollHeight; });
  await p.screenshot({ path: `${out}/v4_phone_six.png` });
  await p.click('.tabs [data-tab="data"]');
  const dt = await p.textContent('#tabData');
  const dtc = dt.replace(/\s+/g, '');
  check(/到达3\.7\d+\.\d很快\d+次/.test(dtc) && dtc.indexOf('次/10分钟') >= 0, 'data tab: average, current pace and level per team');
  check(dt.indexOf('现在＝你记的次数') >= 0 && dt.indexOf('1.5 倍以上很快') >= 0, 'data tab explains current, average and the levels');
  await p.screenshot({ path: `${out}/v4_phone_data.png` });
  await p.click('[data-a="midclose"]'); await p.waitForTimeout(300);
  await p.screenshot({ path: `${out}/v4_phone_pads.png` });
  // a red card for the away team
  await S(p, () => { const M = window.__six.M; M.ev.push({ t: 1300, p: 1, i: 1, c: 'rc', k: 99999 }); });
  await p.clock.runFor(11000);
  const red = [await proj(p, 0), await proj(p, 1)];
  check(red[1].fac.man === -1 && red[0].fac.man === 1 && red[1].per10 < after[1].per10 * 0.75, 'away red card: away pace down (' + after[1].per10.toFixed(2) + ' -> ' + red[1].per10.toFixed(2) + '), home more players');
  // speed of one estimate (cache cleared by moving 10 s on)
  await p.clock.runFor(10000);
  const ms = await S(p, () => { const t = performance.now(); window.__six.projection(window.__six.M, 0); return performance.now() - t; });
  console.log('estimate simulation took', ms.toFixed(1), 'ms (desktop)');
  // half-time and the second half
  await S(p, () => { const M = window.__six.M; M.tm = { p: 1, b: 2820, r: 0, at: 0, ht: 1 }; M.pe[1] = 2820; });
  await p.clock.runFor(11000);
  const htp = await proj(p, 0);
  check(htp && htp.p === 2 && htp.remH > 0.8, 'at half-time the estimate covers the whole second half (' + (htp && htp.remH.toFixed(2)) + ')');
  // help texts carry the check numbers and the new definitions
  await p.click('[data-a="menu"]'); await p.click('#card [data-a="help"]');
  const hp = await p.textContent('#card');
  check(/只用六项 0\.\d\d、加联网 0\.\d\d/.test(hp) && hp.indexOf('领先的一方角球少') >= 0, 'help explains the estimate with its check numbers');
  await p.click('#card [data-a="close"]');
  await p.click('[data-a="menu"]'); await p.click('#card [data-a="how"]');
  check(/从开球看，只用六项 0\.\d\d/.test(await p.textContent('#card')), 'how-it-works sheet shows the check numbers');
  await p.click('#card [data-a="close"]');
  await p.click('[data-a="menu"]'); await p.click('#card [data-a="defs"]');
  const df = await p.textContent('#card');
  check(df.indexOf('平齐') >= 0 && df.indexOf('再记一次禁区射门') >= 0 && df.indexOf('按键上的频率') >= 0, 'key definitions: level-with-the-box rule, cross then header, the average mark');
  await p.click('#card [data-a="close"]');
  console.log('phone errors:', p.errs.length ? p.errs.join('\n') : 'none'); if (p.errs.length) fails++;
  await ctx.close();

  // ---------------- iPad: averages on every outcome button
  ({ ctx, p } = await open(b, 1180, 820, false));
  await p.click('#runBtn');
  await p.clock.runFor(15 * 60000);
  for (const k of ['db', 'db', 'db', 'db', 'dc', 'sp']) await p.click('.pad[data-i="0"] [data-k="' + k + '"]');
  const rq = (await p.textContent('.pad[data-i="0"] .rowq')).replace(/\s+/g, ' ');
  check(rq.indexOf('很快') >= 0 && /现在3\.3 平均1\.5 次\/10分/.test(rq), 'iPad: line under the cross row: ' + rq);
  check((await p.textContent('.pad[data-i="0"] [data-k="db"]')).replace(/\s+/g, '') === '被挡4', 'iPad: outcome buttons stay clean (label and count)');
  const lay = await S(p, () => { const pad = document.querySelector('.pad[data-i="0"] .board').getBoundingClientRect(); const ok = [...document.querySelectorAll('.pad .fq')].every(f => { const r = f.getBoundingClientRect(), k = f.closest('.k, .rowq').getBoundingClientRect(); return r.left >= k.left - 0.5 && r.right <= k.right + 0.5; }); return { ok: ok, sw: document.documentElement.scrollWidth, cw: document.documentElement.clientWidth }; });
  check(lay.ok && lay.sw <= lay.cw, 'iPad: pace text fits, no sideways scroll');
  await p.screenshot({ path: `${out}/v4_ipad.png` });
  console.log('ipad errors:', p.errs.length ? p.errs.join('\n') : 'none'); if (p.errs.length) fails++;
  await ctx.close();
  await b.close();
  console.log(fails ? fails + ' FAILED' : 'ALL OK');
  process.exit(fails ? 1 : 0);
})();
