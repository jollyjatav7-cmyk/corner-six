"""Does the six-factor reading of a half say anything about the corners still to come?

1) Same-half model: corners in a half ~ the half's six-factor metrics (rates and ratios, not counts of corners).
   Fit on club 2015/16 team-halves, coefficients used by the app for the "角球倾向" multiplier.
2) Forward test: second-half corners of each team from its first half: (a) league average only, (b) first-half
   corners, (c) first-half six factors, (d) both. Fit on club, scored on the 2018-2024 tournaments (out of sample).

Usage: python3 -I six_predict.py <in_dir> <res_dir>
"""
import csv
import json
import math
import os
import sys
from collections import defaultdict

import numpy as np

IN, RES = sys.argv[1], sys.argv[2]
NUM = ['mins', 'arr', 'cross', 'cross_blk', 'cross_clr', 'cross_gk', 'cross_ok', 'cross_bad', 'pen', 'pen_ok', 'pen_lost',
       'lshot', 'lshot_blk', 'lshot_hold', 'lshot_parry', 'lshot_off', 'lshot_goal', 'bshot', 'bshot_blk', 'bshot_hold',
       'bshot_parry', 'bshot_off', 'bshot_goal', 'corners', 'goals', 'score_for_start', 'score_against_start']
H = list(csv.DictReader(open(os.path.join(IN, 'halves.csv'), encoding='utf-8')))
for r in H:
    for k in NUM:
        r[k] = float(r[k])
    r['ecross'] = 0.0
K = {(r['match_id'], r['period'], r['side']): r for r in H}
for a in csv.DictReader(open(os.path.join(IN, 'acts.csv'), encoding='utf-8')):
    if a['act'] == 'cross' and float(a['x']) < 102:
        K[(a['match_id'], a['period'], a['side'])]['ecross'] += 1
for r in H:
    o = K[(r['match_id'], r['period'], '1' if r['side'] == '0' else '0')]
    r['opp_arr'] = o['arr']

# prior-shrunk metrics, the way the app computes them live (pseudo counts toward the club average)
P0 = {'arr_rate': 3.714, 'aggr': 0.891, 'block': 0.415, 'space': 0.55, 'err': 0.378, 'deep': 0.30}
NAMES = ['F1 到达 每10分', 'F5 心态', 'F4 被挡率', 'F3 禁区内空间', 'F6 失误率', '45度传中占比']


def feat(r):
    T = r['mins']
    rate = (r['arr'] + P0['arr_rate'] * 0.5) / (T + 5) * 10
    aggr = (r['cross'] + r['lshot'] + r['bshot'] + P0['aggr'] * 3) / (r['arr'] + 3)
    blk = (r['cross_blk'] + r['lshot_blk'] + r['pen_lost'] + P0['block'] * 3) / (r['cross'] + r['lshot'] + r['pen'] + 3)
    inbox = r['cross_ok'] + r['cross_clr'] + r['cross_gk'] + r['bshot']
    space = (r['cross_ok'] + r['bshot'] - r['bshot_blk'] + P0['space'] * 3) / (inbox + 3)
    unb = (r['cross'] - r['cross_blk']) + (r['lshot'] - r['lshot_blk']) + (r['bshot'] - r['bshot_blk'])
    err = (r['cross_bad'] + r['lshot_off'] + r['bshot_off'] + r['lshot_hold'] + r['bshot_hold'] + P0['err'] * 3) / (unb + 3)
    deep = (r['ecross'] + P0['deep'] * 3) / (r['cross'] + 3)
    return [rate, aggr, blk, space, err, deep]


def irls(A, y, off, it=60):
    b = np.zeros(A.shape[1])
    b[0] = math.log(max(y.mean(), 1e-6))
    for _ in range(it):
        eta = A @ b + off
        lam = np.exp(eta)
        z = eta - off + (y - lam) / lam
        AW = A * lam[:, None]
        nb = np.linalg.solve(A.T @ AW + 1e-8 * np.eye(A.shape[1]), AW.T @ z)
        if np.max(np.abs(nb - b)) < 1e-10:
            b = nb
            break
        b = nb
    return b


def loglik(y, lam):
    return float(np.sum(y * np.log(lam) - lam - np.array([math.lgamma(v + 1) for v in y])))


club = [r for r in H if r['kind'] == 'club']
intl = [r for r in H if r['kind'] == 'intl']

# ---------- 1) same-half model (for the app) ----------
X = np.array([feat(r) for r in club])
mu, sd = X.mean(axis=0), X.std(axis=0)
Z = (X - mu) / sd
y = np.array([r['corners'] for r in club])
off = np.log(np.array([r['mins'] for r in club]) / 45.0)
home = np.array([1.0 if r['side'] == '0' else 0.0 for r in club])
per2 = np.array([1.0 if r['period'] == '2' else 0.0 for r in club])
A = np.column_stack([np.ones(len(Z)), Z])
b = irls(A, y, off)
lam = np.exp(A @ b + off)
null = np.full(len(y), y.mean()) * np.exp(off)
same = {'n': len(y), 'intercept': float(b[0]), 'mu': mu.tolist(), 'sd': sd.tolist(), 'beta': b[1:].tolist(), 'names': NAMES,
        'loglik_model': loglik(y, lam), 'loglik_null': loglik(y, null),
        'p20_to_p80': {n: float(math.exp(b[j + 1] * (np.percentile(X[:, j], 80) - np.percentile(X[:, j], 20)) / sd[j])) for j, n in enumerate(NAMES)}}
# out of sample on the tournaments
Xi = (np.array([feat(r) for r in intl]) - mu) / sd
yi = np.array([r['corners'] for r in intl])
offi = np.log(np.array([r['mins'] for r in intl]) / 45.0)
lami = np.exp(np.column_stack([np.ones(len(Xi)), Xi]) @ b + offi)
same['intl'] = {'n': len(yi), 'mae_model': float(np.abs(yi - lami).mean()), 'mae_null': float(np.abs(yi - yi.mean()).mean()),
                'corr': float(np.corrcoef(lami, yi)[0, 1])}


# ---------- 2) forward test: first half -> second half ----------
def pairs(rs):
    g = defaultdict(dict)
    for r in rs:
        g[(r['match_id'], r['side'])][r['period']] = r
    return [(v['1'], v['2']) for v in g.values() if '1' in v and '2' in v]


def design(pp, cols):
    rows = []
    for h1, h2 in pp:
        f = feat(h1)
        x = []
        if 'ck' in cols:
            x.append(h1['corners'] / h1['mins'] * 45)
        if 'six' in cols:
            x.extend(f)
        if 'home' in cols:
            x.append(1.0 if h1['side'] == '0' else 0.0)
        if 'state' in cols:
            d = (h2['score_for_start'] - h2['score_against_start'])
            x.extend([1.0 if d < 0 else 0.0, 1.0 if d > 0 else 0.0])
        rows.append(x)
    return np.array(rows, dtype=float)


tr, te = pairs(club), pairs(intl)
ytr = np.array([h2['corners'] for _, h2 in tr]); ote = np.array([h2['corners'] for _, h2 in te])
otr = np.log(np.array([h2['mins'] for _, h2 in tr]) / 45.0); oote = np.log(np.array([h2['mins'] for _, h2 in te]) / 45.0)
fw = {}
for name, cols in (('平均', []), ('上半场角球', ['ck']), ('上半场六项', ['six']), ('角球＋六项', ['ck', 'six']),
                   ('角球＋六项＋主客＋比分', ['ck', 'six', 'home', 'state']), ('角球＋主客＋比分', ['ck', 'home', 'state'])):
    if cols:
        Xtr, Xte = design(tr, cols), design(te, cols)
        m_, s_ = Xtr.mean(axis=0), Xtr.std(axis=0)
        s_[s_ == 0] = 1
        Atr = np.column_stack([np.ones(len(Xtr)), (Xtr - m_) / s_])
        Ate = np.column_stack([np.ones(len(Xte)), (Xte - m_) / s_])
    else:
        Atr, Ate = np.ones((len(tr), 1)), np.ones((len(te), 1))
    bb = irls(Atr, ytr, otr)
    lt = np.exp(Ate @ bb + oote)
    if cols == ['six']:
        fwd_model = {'intercept': float(bb[0]), 'mu': m_.tolist(), 'sd': s_.tolist(), 'beta': bb[1:].tolist(), 'names': NAMES,
                     'p20_to_p80': {n: float(math.exp(bb[j + 1] * (np.percentile(Xtr[:, j], 80) - np.percentile(Xtr[:, j], 20)) / s_[j])) for j, n in enumerate(NAMES)}}
    fw[name] = {'loglik_per_half': loglik(ote, lt) / len(ote), 'mae': float(np.abs(ote - lt).mean()),
                'corr': float(np.corrcoef(lt, ote)[0, 1]) if np.std(lt) > 0 else 0.0}
json.dump({'same_half': same, 'forward': fw, 'forward_model': fwd_model, 'prior': P0}, open(os.path.join(RES, 'predict.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print(json.dumps(fwd_model, ensure_ascii=False, indent=1))
