"""Joining a match midway: what predicts the corners still to come?

For a join minute J and a watching window W, each team's corners after J+W are predicted from
  - what a live-score API can fill in for [0, J): corners, goals (score), shots, blocked shots, shots on target, possession
  - what you record yourself in [J, J+W): the six factors (same shrinkage as the app's "接下来")
Poisson models fitted on club 2015/16, scored out of sample on the 2018-2024 tournaments.

Usage: python3 -I six_join.py <timeline.csv> <out_json>
"""
import csv
import json
import math
import sys
from collections import defaultdict

import numpy as np

TL, OUT = sys.argv[1], sys.argv[2]
P0 = {'arr_rate': 3.714, 'aggr': 0.891, 'block': 0.415, 'space': 0.55, 'err': 0.378, 'deep': 0.30}
matches = defaultdict(list)
ends = defaultdict(dict)
kinds = {}
for r in csv.DictReader(open(TL, encoding='utf-8')):
    mid = r['match_id']
    kinds[mid] = r['kind']
    if r['code'] == 'end':
        ends[mid][int(r['period'])] = float(r['minute'])
        continue
    matches[mid].append((int(r['period']), float(r['minute']), int(r['side']), r['code']))


def six_feats(c, co, mins):
    g = lambda k: c.get(k, 0)
    D = sum(g('d' + o) for o in 'bcgox'); E = sum(g('e' + o) for o in 'bcgox')
    Pn = g('po') + g('pl'); L = sum(g('l' + o) for o in 'bphxz'); S = sum(g('s' + o) for o in 'bphxz')
    ar = g('ar')
    inN = g('do') + g('eo') + (S - g('sb')); inD = g('do') + g('eo') + g('dc') + g('ec') + g('dg') + g('eg') + S
    blN = g('db') + g('eb') + g('lb') + g('pl'); blD = D + E + L + Pn
    erN = g('dx') + g('ex') + g('lx') + g('sx') + g('lh') + g('sh'); erD = (D - g('db')) + (E - g('eb')) + (L - g('lb')) + (S - g('sb'))
    return [(ar + P0['arr_rate']) / (mins + 10) * 10, (D + E + L + S + P0['aggr'] * 4) / (ar + 4), (blN + P0['block'] * 4) / (blD + 4),
            (inN + P0['space'] * 4) / (inD + 4), (erN + P0['err'] * 4) / (erD + 4), (E + P0['deep'] * 4) / (D + E + 4)]


def window(evs, side, a, b, period=None):
    c = defaultdict(int)
    for p, t, s, code in evs:
        if s == side and a <= t < b and (period is None or p == period):
            c[code] += 1
    return c


def build(J, W):
    rows = []
    for mid, evs in matches.items():
        e = ends[mid]
        if 1 not in e or 2 not in e:
            continue
        end1, end2 = e[1], e[2]
        t1 = J + W
        if J < 45 and t1 > end1:
            continue
        if J < 45:
            obs_p = 1
            rem = (end1 - t1) + (end2 - 45)
        else:
            obs_p = 2
            rem = end2 - t1
        if rem <= 5:
            continue
        for side in (0, 1):
            pre = window(evs, side, 0, J) if J > 0 else defaultdict(int)
            preo = window(evs, 1 - side, 0, J) if J > 0 else defaultdict(int)
            pre_min = J if J <= 45 else 45 + (J - 45)
            wat = window(evs, side, J, t1, obs_p)
            wato = window(evs, 1 - side, J, t1, obs_p)
            full = window(evs, side, 0, t1)
            fullo = window(evs, 1 - side, 0, t1)
            gl = sum(1 for p, t, s, c in evs if s == side and c == 'gl' and t < t1)
            glo = sum(1 for p, t, s, c in evs if s == 1 - side and c == 'gl' and t < t1)
            y = sum(1 for p, t, s, c in evs if s == side and c == 'ck' and t >= t1)
            pas = pre.get('xpa', 0) + preo.get('xpa', 0)
            rows.append({
                'kind': kinds[mid], 'y': y, 'rem': rem,
                'pre_ck': pre.get('ck', 0) / max(pre_min, 1) * 45, 'pre_cko': preo.get('ck', 0) / max(pre_min, 1) * 45,
                'pre_sh': pre.get('xsh', 0) / max(pre_min, 1) * 45, 'pre_shb': pre.get('xshb', 0) / max(pre_min, 1) * 45,
                'pre_sht': pre.get('xsht', 0) / max(pre_min, 1) * 45, 'pre_pos': pre.get('xpa', 0) / pas if pas else 0.5,
                'six': six_feats(wat, wato, W), 'full6': six_feats(full, fullo, t1),
                'lead': 1.0 if gl > glo else 0.0, 'trail': 1.0 if gl < glo else 0.0, 'home': 1.0 if side == 0 else 0.0,
            })
    return rows


def irls(A, y, off, it=60):
    b = np.zeros(A.shape[1]); b[0] = math.log(max(y.mean(), 1e-6) / max(np.exp(off).mean(), 1e-6))
    for _ in range(it):
        eta = A @ b + off
        lam = np.exp(eta)
        z = eta - off + (y - lam) / lam
        AW = A * lam[:, None]
        nb = np.linalg.solve(A.T @ AW + 1e-8 * np.eye(A.shape[1]), AW.T @ z)
        if np.max(np.abs(nb - b)) < 1e-10:
            return nb
        b = nb
    return b


def feats(rows, which):
    X = []
    for r in rows:
        x = []
        if 'ck' in which: x += [r['pre_ck'], r['pre_cko']]
        if 'api' in which: x += [r['pre_sh'], r['pre_shb'], r['pre_sht'], r['pre_pos']]
        if 'six' in which: x += r['six']
        if 'full' in which: x += r['full6']
        if 'state' in which: x += [r['lead'], r['trail']]
        if 'home' in which: x += [r['home']]
        X.append(x)
    return np.array(X, dtype=float)


MODELS = [('平均', []), ('加入前角球（联网）', ['ck']), ('加入前角球＋射门＋控球（联网）', ['ck', 'api']), ('看的这几分钟六项', ['six']),
          ('六项＋加入前角球', ['six', 'ck']), ('六项＋联网全部', ['six', 'ck', 'api']), ('六项＋联网全部＋比分', ['six', 'ck', 'api', 'state']),
          ('从头看到现在的六项（对照）', ['full'])]
res = {}
for J, W in [(15, 10), (25, 10), (30, 5), (30, 15), (45, 10), (55, 10), (60, 5), (60, 15), (70, 10)]:
    rows = build(J, W)
    tr = [r for r in rows if r['kind'] == 'club']; te = [r for r in rows if r['kind'] == 'intl']
    ytr = np.array([r['y'] for r in tr], float); yte = np.array([r['y'] for r in te], float)
    otr = np.log(np.array([r['rem'] for r in tr]) / 45); ote = np.log(np.array([r['rem'] for r in te]) / 45)
    out = {}
    for name, which in MODELS:
        if which:
            Xtr, Xte = feats(tr, which), feats(te, which)
            mu, sd = Xtr.mean(0), Xtr.std(0); sd[sd == 0] = 1
            Atr = np.column_stack([np.ones(len(Xtr)), (Xtr - mu) / sd]); Ate = np.column_stack([np.ones(len(Xte)), (Xte - mu) / sd])
        else:
            Atr, Ate = np.ones((len(tr), 1)), np.ones((len(te), 1))
        b = irls(Atr, ytr, otr)
        lt = np.exp(Ate @ b + ote)
        ll = float(np.mean(yte * np.log(lt) - lt - np.array([math.lgamma(v + 1) for v in yte])))
        out[name] = {'corr': float(np.corrcoef(lt, yte)[0, 1]) if np.std(lt) > 0 else 0.0, 'mae': float(np.abs(lt - yte).mean()), 'll': ll}
    base_ll = out['平均']['ll']
    for k in out:
        out[k]['gain'] = out[k]['ll'] - base_ll
    res[f'J{J}_W{W}'] = {'n_train': len(tr), 'n_test': len(te), 'mean_y': float(yte.mean()), 'models': out}
    print(f'join {J}\' watch {W} min (test n={len(te)}, avg remaining corners {yte.mean():.2f})')
    for k, v in out.items():
        print(f'   {k:22s} corr {v["corr"]:.3f}  mae {v["mae"]:.3f}  gain {v["gain"]:+.4f}')
json.dump(res, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
