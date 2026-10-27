"""The "接下来" estimate: corner-sb's base minute model (time within the half, home, score state, red cards, a corner in
the last 3 minutes; the app also simulates goals) times a multiplier from the six factors, plus the API numbers
(corners, shots, blocked shots, shots on target, possession) when the match is linked.

Fit: Poisson on each team's corners for the rest of the half, offset = corner-sb's base expectation, standardized
features, watching scenarios pooled (from kick-off, or only the last 5/10/15/20/30 minutes), checkpoints every 5
minutes. The intercept is re-centred like corner-sb's fit3.py because the app simulates the base on top.
Checks: leave-one-league-out with the base refitted on three leagues (against corner-sb's own model fitted the same
way), the 2018-2024 tournaments, and the simulated level against the actual corners.

Usage: python3 -I six_cbase.py <ev_sb.csv> <mt_sb.csv> <timeline.csv> <corner-sb/dev/model> <corner-sb model.json> <baseline.json> <out proj.json>
"""
import bisect
import csv
import json
import math
import sys
from collections import defaultdict

import numpy as np
import pandas as pd

EV, MT, TL, SBMOD, SBMODEL, SIXB, OUT = sys.argv[1:8]
sys.path.insert(0, SBMOD)
import model2 as M2  # noqa: E402  (corner-sb's own model code, used to refit its base per fold)

SHIP = json.load(open(SBMODEL, encoding='utf-8'))
P_SHIP = SHIP['base']
P0 = json.load(open(SIXB, encoding='utf-8'))['proj']['prior']
GRID = [(1, c) for c in (5, 10, 15, 20, 25, 30, 35, 38, 40)] + [(2, c) for c in (0, 5, 10, 15, 20, 25, 30, 35, 38, 40)]
CHK = [(1, 10), (1, 20), (1, 30), (1, 38), (2, 0), (2, 10), (2, 20), (2, 30), (2, 38)]   # same as the corner-sb comparison
SCEN = ['full', '5', '10', '15', '20', '30']
REPORT_SCEN = ['full', '10', '20']
SIXC = ['ar'] + ['d' + o for o in 'bcgox'] + ['e' + o for o in 'bcgox'] + ['po', 'pl'] + ['l' + o for o in 'bphxz'] + ['s' + o for o in 'bphxz']
APIC = ['ck', 'xsh', 'xshb', 'xsht', 'xpa']
SB_G = {'f3': ('f3',), 'bx': ('bx', 'co'), 'cr': ('co', 'cf')}
SB_FEATS = ['so_own_f3', 'so_own_bx', 'so_own_cr', 'so_opp_f3', 'so_opp_bx']

mtdf = pd.read_csv(MT)
evdf = pd.read_csv(EV)
kind_of = dict(zip(mtdf.match_id, mtdf.kind))
lg_of = dict(zip(mtdf.match_id, mtdf.league))
plen_of = {r.match_id: (float(r.p1_len), float(r.p2_len)) for r in mtdf.itertuples()}

# ---------------- events as sorted positions on one played-seconds line (second half after the first half's length)
sbp = defaultdict(lambda: defaultdict(list))      # mid -> (side, code) -> positions   (side 0 = home)
ckl = defaultdict(lambda: {0: [], 1: []})          # mid -> side -> [(period, t)]
for r in evdf.itertuples():
    p1 = plen_of[r.match_id][0]
    s = 0 if r.side == 1 else 1
    sbp[r.match_id][(s, r.code)].append(r.t if r.period == 1 else p1 + r.t)
    if r.code == 'ck':
        ckl[r.match_id][s].append((r.period, r.t))
sixp = defaultdict(lambda: defaultdict(list))
for r in csv.DictReader(open(TL, encoding='utf-8')):
    if r['code'] == 'end':
        continue
    mid = int(r['match_id'])
    per, mnt = int(r['period']), float(r['minute'])
    t = (mnt - 45.0) * 60 if per == 2 else mnt * 60
    sixp[mid][(int(r['side']), r['code'])].append(t if per == 1 else plen_of[mid][0] + t)
for d in (sbp, sixp):
    for mid in d:
        for k in d[mid]:
            d[mid][k].sort()


def cnt(lst, a, b):
    return bisect.bisect_left(lst, b) - bisect.bisect_left(lst, a)


def state_idx(d):
    return 0 if d <= -2 else 1 if d == -1 else 2 if d == 0 else 3 if d == 1 else 4


def six_feats(c, mins):
    g = lambda k: c.get(k, 0)
    D = sum(g('d' + o) for o in 'bcgox'); E = sum(g('e' + o) for o in 'bcgox')
    Pn = g('po') + g('pl'); L = sum(g('l' + o) for o in 'bphxz'); S = sum(g('s' + o) for o in 'bphxz')
    ar = g('ar')
    inN = g('do') + g('eo') + (S - g('sb')); inD = g('do') + g('eo') + g('dc') + g('ec') + g('dg') + g('eg') + S
    blN = g('db') + g('eb') + g('lb') + g('pl'); blD = D + E + L + Pn
    erN = g('dx') + g('ex') + g('lx') + g('sx') + g('lh') + g('sh'); erD = (D - g('db')) + (E - g('eb')) + (L - g('lb')) + (S - g('sb'))
    return [(ar + P0['arr_rate']) / (mins + 10) * 10, (D + E + L + S + P0['aggr'] * 4) / (ar + 4), (blN + P0['block'] * 4) / (blD + 4),
            (inN + P0['space'] * 4) / (inD + 4), (erN + P0['err'] * 4) / (erD + 4), (E + P0['deep'] * 4) / (D + E + 4)]


# ---------------- one row per team x checkpoint x watching scenario
rows = []
for mid, (p1, p2) in plen_of.items():
    S, X = sbp[mid], sixp[mid]
    for h, c in GRID:
        t0, plen = c * 60.0, (p1 if h == 1 else p2)
        if t0 >= plen - 60:
            continue
        pos0 = t0 if h == 1 else p1 + t0
        T = c if h == 1 else 45 + c
        goals = [cnt(S[(s, 'sg')], 0, pos0) + cnt(S[(s, 'og')], 0, pos0) for s in (0, 1)]
        reds = [cnt(S[(s, 'rc')], 0, pos0) for s in (0, 1)]
        yH, y2, have, lastc = [0, 0], [0, 0], [0, 0], [None, None]
        for s in (0, 1):
            for per, t in ckl[mid][s]:
                if per == h and t < t0:
                    have[s] += 1
                    lastc[s] = t if lastc[s] is None or t > lastc[s] else lastc[s]
                elif per == h:
                    yH[s] += 1
                elif h == 1 and per == 2:
                    y2[s] += 1
        k = 45.0 / max(T, 1)
        api = [{cd: cnt(X[(s, cd)], 0, pos0) for cd in APIC} for s in (0, 1)]
        for scen in SCEN:
            start = 0.0 if scen == 'full' else pos0 - int(scen) * 60
            if start < 0 or (scen != 'full' and int(scen) * 60 >= pos0):
                continue
            wmin = (pos0 - start) / 60.0
            c6 = [{cd: cnt(X[(s, cd)], start, pos0) for cd in SIXC} for s in (0, 1)]
            cs = [{g: sum(cnt(S[(s, cd)], start, pos0) for cd in codes) for g, codes in SB_G.items()} for s in (0, 1)]
            for i in (0, 1):
                d = goals[i] - goals[1 - i]
                pas = api[i]['xpa'] + api[1 - i]['xpa']
                lc = lastc[i] if lastc[i] is not None and (lastc[i] if h == 1 else p1 + lastc[i]) >= start else None
                rows.append({'mid': mid, 'kind': kind_of[mid], 'lg': lg_of[mid], 'h': h, 'c': c, 'scen': scen, 'i': i,
                             't0': t0, 'plen': plen, 'p2': p2, 'st': state_idx(d), 'man': int(np.sign(reds[1 - i] - reds[i])), 'lc': lc,
                             'yH': yH[i], 'yM': yH[i] + y2[i], 'have': have[i], 'cs': cs, 'wmin': wmin, 'g': goals, 'rd': reds,
                             'f6': six_feats(c6[i], wmin),
                             'fa': [api[i]['ck'] * k, api[1 - i]['ck'] * k, api[i]['xsh'] * k, api[i]['xshb'] * k, api[i]['xsht'] * k,
                                    api[i]['xpa'] / pas if pas else 0.5]})
print('rows', len(rows), flush=True)


# ---------------- corner-sb base expectation (exact integral of its piecewise-constant minute rates)
def make_base(P):
    cum = {}
    for h in (1, 2):
        b = P['bin'][(h - 1) * 10:(h - 1) * 10 + 10]
        cs = [0.0]
        for j in range(9):
            cs.append(cs[-1] + b[j] * 5.0)
        cum[h] = (b, cs)

    def F(h, t):
        b, cs = cum[h]
        if t <= 0:
            return 0.0
        if t >= 2700:
            return cs[9] + b[9] * (t - 2700) / 60.0
        j = int(t // 300)
        return cs[j] + b[j] * (t - j * 300) / 60.0

    def exp_(h, t0, end, i, st, man, lastc):
        f = (P['home'] if i == 0 else 1.0) * P['state'][st] * P['man'][man + 1]
        e = F(h, end) - F(h, t0)
        if lastc is not None and lastc + P['cluSec'] > t0:
            e += (P['clu'] - 1.0) * (F(h, min(end, lastc + P['cluSec'])) - F(h, t0))
        return f * e
    return exp_


def set_base(P, rs):
    be = make_base(P)
    for r in rs:
        r['bh'] = be(r['h'], r['t0'], r['plen'], r['i'], r['st'], r['man'], r['lc'])
        r['b2'] = be(2, 0.0, r['p2'], r['i'], r['st'], r['man'], None) if r['h'] == 1 else 0.0


def irls(A, y, off, ridge, it=100):
    b = np.zeros(A.shape[1])
    b[0] = math.log(max(y.sum(), 1e-9) / np.exp(off).sum())
    R = np.diag(ridge)
    for _ in range(it):
        eta = A @ b + off
        lam = np.exp(eta)
        z = eta - off + (y - lam) / lam
        AW = A * lam[:, None]
        nb = np.linalg.solve(A.T @ AW + R + 1e-9 * np.eye(len(b)), AW.T @ z)
        if np.max(np.abs(nb - b)) < 1e-10:
            return nb
        b = nb
    return b


FEATS = {'six': lambda r: r['f6'], 'net': lambda r: r['f6'] + r['fa']}


def fit_mult(tr, name):
    X = np.array([FEATS[name](r) for r in tr], float)
    mu, sd = X.mean(0), X.std(0); sd[sd == 0] = 1
    A = np.column_stack([np.ones(len(X)), (X - mu) / sd])
    y = np.array([r['yH'] for r in tr], float)
    off = np.log(np.array([r['bh'] for r in tr]))
    b = irls(A, y, off, np.r_[0.0, np.full(X.shape[1], 1.0)])
    b0 = float(b[0] - math.log(y.sum() / np.exp(off).sum()))   # re-centred: the app simulates the base on top
    return {'b0': b0, 'beta': [float(v) for v in b[1:]], 'mu': [float(v) for v in mu], 'sd': [float(v) for v in sd]}


def mult(m, x):
    return math.exp(m['b0'] + sum(b * (v - u) / s for b, v, u, s in zip(m['beta'], x, m['mu'], m['sd'])))


def sb_feats(r, rates):
    out = []
    for nm in SB_FEATS:
        _, who, g = nm.split('_')
        j = r['i'] if who == 'own' else 1 - r['i']
        n, rt = r['cs'][j][g], rates[j][g]
        a = rt * 15.0
        out.append(math.log((n + a) / (rt * r['wmin'] + a)))
    return out


def fit_sb(tr, rates):
    trf = [r for r in tr if r['scen'] == 'full']
    X = np.column_stack([np.ones(len(trf)), np.array([sb_feats(r, rates) for r in trf])])
    off = np.log(np.array([r['bh'] for r in trf]))
    y = np.array([r['yH'] for r in trf], float)
    b = irls(X, y, off, np.r_[0.0, np.full(X.shape[1] - 1, 30.0)])
    b[0] -= math.log(y.sum() / np.exp(off).sum())
    return b


def pois_ll(y, mu):
    mu = max(mu, 1e-9)
    return y * math.log(mu) - mu - math.lgamma(y + 1)


def tail(k, mu):
    if k < 0:
        return 1.0
    s, p = 0.0, math.exp(-mu)
    for j in range(k + 1):
        s += p; p *= mu / (j + 1)
    return max(0.0, 1.0 - s)


def pmf(mu, n=35):
    out, p = [], math.exp(-mu)
    for j in range(n):
        out.append(p); p *= mu / (j + 1)
    return out


def score(rs, pred, models):
    """within-checkpoint correlation, log-lik gain over the base, half O/U and handicap Brier (Poisson / Skellam)"""
    res = {}
    for scen in REPORT_SCEN:
        R = [n for n, r in enumerate(rs) if r['scen'] == scen and (r['h'], r['c']) in CHK]
        out = {'n': len(R)}
        for tgt, j, yk in (('half', 0, 'yH'), ('match', 1, 'yM')):
            y = np.array([rs[n][yk] for n in R], float)
            o = {}
            for m in models:
                mu = np.array([pred[m][n][j] for n in R])
                cs = []
                for hc in CHK:
                    msk = np.array([(rs[n]['h'], rs[n]['c']) == hc for n in R])
                    if msk.sum() > 30 and np.std(mu[msk]) > 0:
                        cs.append(float(np.corrcoef(mu[msk], y[msk])[0, 1]))
                o[m] = {'corr': float(np.mean(cs)), 'll': float(np.mean([pois_ll(a, b) for a, b in zip(y, mu)])), 'mean': float(mu.mean()), 'mean_y': float(y.mean())}
            for m in models:
                o[m]['ll_gain'] = o[m]['ll'] - o['base']['ll']
            out[tgt] = o
        byk = defaultdict(dict)
        for n in R:
            byk[(rs[n]['mid'], rs[n]['h'], rs[n]['c'])][rs[n]['i']] = n
        br = {m: {'ou': [], 'hcap': []} for m in models}
        for key, pr in byk.items():
            if len(pr) != 2:
                continue
            hm, aw = rs[pr[0]], rs[pr[1]]
            have, fin = hm['have'] + aw['have'], hm['have'] + aw['have'] + hm['yH'] + aw['yH']
            dnow, dfin = hm['have'] - aw['have'], (hm['have'] + hm['yH']) - (aw['have'] + aw['yH'])
            for m in models:
                m0, m1 = pred[m][pr[0]][0], pred[m][pr[1]][0]
                for L in ([3.5, 4.5, 5.5] if key[1] == 1 else [4.5, 5.5]):
                    br[m]['ou'].append((tail(int(math.floor(L - have)), m0 + m1) - (1 if fin > L else 0)) ** 2)
                f0, f1 = pmf(m0), pmf(m1)
                for L in (-1.5, -0.5, 0.5):
                    p = sum(f0[a] * f1[b] for a in range(len(f0)) for b in range(len(f1)) if dnow + a - b + L > 0)
                    br[m]['hcap'].append((p - (1 if dfin + L > 0 else 0)) ** 2)
        out['brier'] = {m: {k: float(np.mean(v)) for k, v in d.items()} for m, d in br.items()}
        res[scen] = out
    return res


def show(title, res, models):
    print('\n##', title)
    for scen, out in res.items():
        print(' scenario', scen, 'rows', out['n'])
        for tgt in ('half', 'match'):
            print('   ', tgt, ' '.join(f"{m}:{out[tgt][m]['corr']:.3f}({out[tgt][m]['ll_gain']*1000:+.1f})" for m in models))
        bb = out['brier']['base']
        print('    brier % vs base  ', ' '.join(f"{m}: O/U {100*(1-out['brier'][m]['ou']/bb['ou']):+.2f} hcap {100*(1-out['brier'][m]['hcap']/bb['hcap']):+.2f}" for m in models))


MODELS = ['base', 'sb', 'six', 'net']
club = [r for r in rows if r['kind'] == 'club']
intl = [r for r in rows if r['kind'] == 'intl']

# ---------------- leave one league out, base refitted on the other three
evc = evdf[evdf.match_id.isin(mtdf.match_id[mtdf.kind == 'club'])]
mtc = mtdf[mtdf.kind == 'club'].reset_index(drop=True)
print('corner-sb slots ...', flush=True)
slots = M2.build_slots(evc, mtc)
pred = {m: {} for m in MODELS}
for lg in sorted(mtc.league.unique()):
    trm = set(mtc.match_id[mtc.league != lg])
    P = M2.fit_base(slots[slots.match_id.isin(trm)])
    set_base(P, club)
    tm = mtc[mtc.league != lg]
    mins = (tm.p1_len.sum() + tm.p2_len.sum()) / 60.0
    tev = evc[evc.match_id.isin(trm)]
    rates = [{g: float(tev[tev.side == sd].code.isin(cd).sum() / mins) for g, cd in SB_G.items()} for sd in (1, 0)]
    tr = [r for r in club if r['lg'] != lg]
    bsb = fit_sb(tr, rates)
    ms = {m: fit_mult(tr, m) for m in ('six', 'net')}
    for n, r in enumerate(club):
        if r['lg'] != lg:
            continue
        fsb = math.exp(bsb[0] + sum(b * x for b, x in zip(bsb[1:], sb_feats(r, rates))))
        for m, f in (('base', 1.0), ('sb', fsb), ('six', mult(ms['six'], FEATS['six'](r))), ('net', mult(ms['net'], FEATS['net'](r)))):
            pred[m][n] = (r['bh'] * f, (r['bh'] + r['b2']) * f)
    print(lg, 'done', flush=True)
lolo = score(club, pred, MODELS)
show('leave one league out (club 2015/16)', lolo, MODELS)

# ---------------- final fit on all club data with corner-sb's shipped base; check on the tournaments
set_base(P_SHIP, rows)
final = {m: fit_mult(club, m) for m in ('six', 'net')}
rates_all = [{g: float(evc[evc.side == sd].code.isin(cd).sum() / ((mtc.p1_len.sum() + mtc.p2_len.sum()) / 60.0)) for g, cd in SB_G.items()} for sd in (1, 0)]
predi = {m: {} for m in MODELS}
for n, r in enumerate(intl):
    fsb = math.exp(SHIP['coefNoPrior'][0] + sum(b * x for b, x in zip(SHIP['coefNoPrior'][1:], sb_feats(r, SHIP['rates']))))
    for m, f in (('base', 1.0), ('sb', fsb), ('six', mult(final['six'], FEATS['six'](r))), ('net', mult(final['net'], FEATS['net'](r)))):
        predi[m][n] = (r['bh'] * f, (r['bh'] + r['b2']) * f)
intl_res = score(intl, predi, MODELS)
show('tournaments 2018-2024 (models fitted on club; corner-sb as shipped)', intl_res, MODELS)


# ---------------- level check: the app's simulation (goals and corner clusters) with the final multipliers
def simulate(P, half, t0, score_, reds, last, end, ml, n, rng, more_end=None):
    out = {0: np.zeros(n), 1: np.zeros(n)}
    sh, sa = np.full(n, float(score_[0])), np.full(n, float(score_[1]))
    man = {0: int(np.sign(reds[1] - reds[0])), 1: int(np.sign(reds[0] - reds[1]))}
    st = np.array(P['state'])
    segs = [(half, t0, end)] + ([(2, 0.0, more_end)] if more_end else [])
    for si, (hf, ts, te) in enumerate(segs):
        lc = {i: np.full(n, -1e9 if (si > 0 or last[i] is None) else last[i]) for i in (0, 1)}
        t = ts
        while t < te - 1e-9:
            mi = int(t // 60)
            step = min(60.0 - (t - mi * 60), te - t)
            dt = step / 60.0
            b = P['bin'][(hf - 1) * 10 + min(mi // 5, 9)]
            for i in (0, 1):
                diff = (sh - sa) if i == 0 else (sa - sh)
                sidx = np.select([diff <= -2, diff == -1, diff == 0, diff == 1], [0, 1, 2, 3], 4)
                lam = b * (P['home'] if i == 0 else 1.0) * P['man'][man[i] + 1] * st[sidx] * np.where(t - lc[i] <= P['cluSec'], P['clu'], 1.0) * ml[i] * dt
                kk = rng.poisson(lam)
                if si == 0:
                    out[i] += kk
                lc[i] = np.where(kk > 0, t + step / 2, lc[i])
                g = rng.poisson(P['goal'][hf - 1][1 if i == 0 else 0] * dt, n)
                if i == 0:
                    sh = sh + g
                else:
                    sa = sa + g
            t += step
    return out


rng = np.random.default_rng(7)
cal = {}
for name, pool in (('club', club), ('intl', intl)):
    byk = defaultdict(dict)
    for r in pool:
        if r['scen'] == 'full' and (r['h'], r['c']) in CHK:
            byk[(r['mid'], r['h'], r['c'])][r['i']] = r
    keys = [k for k, v in byk.items() if len(v) == 2]
    rng.shuffle(keys)
    sims, acts = {'net': [], 'six': []}, []
    for key in keys[:1200]:
        hm, aw = byk[key][0], byk[key][1]
        acts.append(hm['yH'] + aw['yH'])
        for m in ('six', 'net'):
            ml = [mult(final[m], FEATS[m](hm)), mult(final[m], FEATS[m](aw))]
            o = simulate(P_SHIP, hm['h'], hm['t0'], hm['g'], hm['rd'], [hm['lc'], aw['lc']], hm['plen'], ml, 300, rng)
            sims[m].append(float(o[0].mean() + o[1].mean()))
    cal[name] = {m: {'sim_mean': float(np.mean(v)), 'actual_mean': float(np.mean(acts))} for m, v in sims.items()}
    print('level check', name, {m: (round(v['sim_mean'], 3), round(v['actual_mean'], 3)) for m, v in cal[name].items()})

names = {'six': ['到达每10分', '心态', '被挡率', '禁区内空间', '失误率', '45度占比'],
         'net': ['到达每10分', '心态', '被挡率', '禁区内空间', '失误率', '45度占比', '角球/45', '对方角球/45', '射门/45', '被挡射门/45', '射正/45', '控球']}
for m in final:
    final[m]['names'] = names[m]
    print(m, 'b0', round(final[m]['b0'], 4), 'beta', [round(v, 4) for v in final[m]['beta']])
cb = {k: P_SHIP[k] for k in ('bin', 'home', 'state', 'clu', 'cluSec', 'man', 'goal')}
json.dump({'prior': P0, 'cb': cb, 'add': SHIP.get('addDef', [4, 6]), 'six': final['six'], 'net': final['net'],
           'check': {'lolo': lolo, 'intl': intl_res, 'level': cal}}, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
