"""Extra checks: Poisson regression of corners on the six-factor metrics (each factor's effect with the others
held fixed), the user's case 2 with the cross-to-team-mate rate, and the share of deep (early) crosses.

Usage: python3 -I six_more.py <in_dir> <res_dir>
"""
import csv
import json
import math
import os
import sys
from collections import defaultdict

import numpy as np

IN, RES = sys.argv[1], sys.argv[2]
sys.argv = [sys.argv[0], IN, RES]
NUM = ['mins', 'arr', 'cross', 'cross_blk', 'cross_clr', 'cross_gk', 'cross_ok', 'cross_bad', 'pen', 'pen_ok', 'pen_lost',
       'lshot', 'lshot_blk', 'lshot_hold', 'lshot_parry', 'lshot_off', 'lshot_goal', 'bshot', 'bshot_blk', 'bshot_hold',
       'bshot_parry', 'bshot_off', 'bshot_goal', 'corners', 'goals', 'score_for_start', 'score_against_start']
halves = list(csv.DictReader(open(os.path.join(IN, 'halves.csv'), encoding='utf-8')))
for r in halves:
    for k in NUM:
        r[k] = float(r[k])
key = {(r['match_id'], r['period'], r['side']): r for r in halves}
for r in halves:
    o = key[(r['match_id'], r['period'], '1' if r['side'] == '0' else '0')]
    r['opp_arr'] = o['arr']
# deep crosses per team-half
deep = defaultdict(int)
for a in csv.DictReader(open(os.path.join(IN, 'acts.csv'), encoding='utf-8')):
    if a['act'] == 'cross' and float(a['x']) < 102:
        deep[(a['match_id'], a['period'], a['side'])] += 1
for r in halves:
    r['cross_deep'] = deep[(r['match_id'], r['period'], r['side'])]

# team-matches (club only)
tm = defaultdict(list)
for r in halves:
    if r['kind'] == 'club':
        tm[(r['match_id'], r['side'])].append(r)
rows = []
for (mid, side), two in tm.items():
    if len(two) != 2:
        continue
    m = {'side': int(side)}
    for k in NUM + ['opp_arr', 'cross_deep']:
        m[k] = two[0][k] + two[1][k]
    rows.append(m)


def d(a, b):
    return a / b if b > 0 else np.nan


def feats(m):
    unb = (m['cross'] - m['cross_blk']) + (m['lshot'] - m['lshot_blk']) + (m['bshot'] - m['bshot_blk'])
    err = m['cross_bad'] + m['lshot_off'] + m['bshot_off'] + m['lshot_hold'] + m['bshot_hold']
    inbox = m['cross_ok'] + m['cross_clr'] + m['cross_gk'] + m['bshot']
    acts = m['cross'] + m['pen'] + m['lshot']
    return {
        'F1 到达 每10分': m['arr'] / m['mins'] * 10,
        'F2 传中占比': d(m['cross'], acts),
        'F2 远射占比': d(m['lshot'], acts),
        'F3 禁区内空间': d(m['cross_ok'] + m['bshot'] - m['bshot_blk'], inbox),
        'F4 被挡率': d(m['cross_blk'] + m['lshot_blk'] + m['pen_lost'], m['cross'] + m['lshot'] + m['pen']),
        'F5 心态': d(m['cross'] + m['lshot'] + m['bshot'], m['arr']),
        'F6 失误率': d(err, unb),
        '45度传中占比': d(m['cross_deep'], m['cross']),
        '主场': float(m['side'] == 0),
    }


F = [feats(m) for m in rows]
names = list(F[0].keys())
X = np.array([[f[k] for k in names] for f in F], dtype=float)
y = np.array([m['corners'] for m in rows], dtype=float)
off = np.log(np.array([m['mins'] for m in rows]) / 90.0)
ok = ~np.isnan(X).any(axis=1)
X, y, off = X[ok], y[ok], off[ok]
mu, sd = X.mean(axis=0), X.std(axis=0)
Z = (X - mu) / sd
Z[:, names.index('主场')] = X[:, names.index('主场')]


def poisson(Z, y, off, it=50):
    A = np.column_stack([np.ones(len(Z)), Z])
    b = np.zeros(A.shape[1])
    b[0] = math.log(y.mean())
    for _ in range(it):
        eta = A @ b + off
        lam = np.exp(eta)
        W = lam
        zz = eta - off + (y - lam) / lam
        AW = A * W[:, None]
        b_new = np.linalg.solve(A.T @ AW, AW.T @ zz)
        if np.max(np.abs(b_new - b)) < 1e-9:
            b = b_new
            break
        b = b_new
    lam = np.exp(A @ b + off)
    cov = np.linalg.inv((A * lam[:, None]).T @ A)
    dev = 2 * np.sum(np.where(y > 0, y * np.log(np.where(y > 0, y, 1) / lam), 0) - (y - lam))
    null = 2 * np.sum(np.where(y > 0, y * np.log(np.where(y > 0, y, 1) / y.mean()), 0) - (y - y.mean()))
    return b, np.sqrt(np.diag(cov)), 1 - dev / null


b, se, pr2 = poisson(Z, y, off)
res = {'n': int(len(y)), 'pseudo_r2': pr2, 'coef': {}}
q = lambda col: np.percentile(X[:, col], [20, 80])
for j, k in enumerate(names):
    lo, hi = q(j)
    step = (hi - lo) / sd[j] if k != '主场' else 1.0
    res['coef'][k] = {'per_sd': math.exp(b[j + 1]), 'p20_to_p80': math.exp(b[j + 1] * step), 'z': b[j + 1] / se[j + 1],
                      'p20': lo, 'p80': hi}
# case 2 with the plain cross-to-team-mate rate (aggressive, crossing a lot, space outside)
qs = lambda vals: np.nanpercentile(vals, [20, 40, 60, 80])
f1 = np.array([f['F1 到达 每10分'] for f in F]); f5 = np.array([f['F5 心态'] for f in F])
f2 = np.array([f['F2 传中占比'] for f in F]); f4 = np.array([f['F4 被挡率'] for f in F])
cok = np.array([d(m['cross_ok'], m['cross_ok'] + m['cross_clr'] + m['cross_gk']) for m in rows])
gkr = np.array([d(m['cross_gk'], m['cross']) for m in rows])
deepr = np.array([f['45度传中占比'] for f in F])
cor = np.array([m['corners'] for m in rows])
base = (f5 >= np.nanpercentile(f5, 60)) & (f1 >= np.nanpercentile(f1, 40)) & (f2 >= np.nanpercentile(f2, 60)) & (f4 <= np.nanpercentile(f4, 40))
out = {}
for name, arr in (('传中到人率', cok), ('门将收传中比例', gkr), ('45度传中占比', deepr)):
    lo, hi = np.nanpercentile(arr[base], [33.3, 66.7])
    out[name] = {'low': [float(cor[base & (arr <= lo)].mean()), int((base & (arr <= lo)).sum())],
                 'mid': [float(cor[base & (arr > lo) & (arr < hi)].mean()), int((base & (arr > lo) & (arr < hi)).sum())],
                 'high': [float(cor[base & (arr >= hi)].mean()), int((base & (arr >= hi)).sum())]}
res['case2_group'] = {'n': int(base.sum()), 'corners': float(cor[base].mean()), 'split': out}
# overall: deep-cross share terciles among all teams with >= 10 crosses
m10 = np.array([m['cross'] >= 10 for m in rows])
lo, hi = np.nanpercentile(deepr[m10], [33.3, 66.7])
res['deep_share_all'] = {'cut': [float(lo), float(hi)],
                         'corners_per_cross': [float((cor[m10 & (deepr <= lo)] / np.array([m['cross'] for m in rows])[m10 & (deepr <= lo)]).mean()),
                                               float((cor[m10 & (deepr >= hi)] / np.array([m['cross'] for m in rows])[m10 & (deepr >= hi)]).mean())]}
json.dump(res, open(os.path.join(RES, 'more.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print(json.dumps(res, ensure_ascii=False, indent=1))
