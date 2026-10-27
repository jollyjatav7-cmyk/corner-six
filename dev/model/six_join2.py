"""The app's "接下来" model when the match is linked to the live-score API.

At match minute T the app knows: the six factors over the minutes you recorded ([J, T), J = when you started),
and from the API the whole match so far ([0, T)): corners, shots, blocked shots, shots on target, possession, score.
One Poisson model for each team's corners after T (offset = minutes left), pooled over many (J, T) pairs, fitted on
club 2015/16 and checked on the 2018-2024 tournaments against the six-only model.

Usage: python3 -I six_join2.py <timeline.csv> <out_json>
"""
import json
import math
import os
import sys
from collections import defaultdict

import numpy as np

TL, OUTJ = sys.argv[1], sys.argv[2]
# reuse the loader and helpers from six_join.py (everything above its report section);
# six_join.py reads <timeline.csv> <out_json> from argv when loaded
src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'six_join.py'), encoding='utf-8').read().split('\nMODELS = ')[0]
sys.argv = [sys.argv[0], TL, os.devnull]
g = {'__name__': 'six_join'}
exec(compile(src, 'six_join.py', 'exec'), g)
matches, ends, kinds, six_feats, window, irls = g['matches'], g['ends'], g['kinds'], g['six_feats'], g['window'], g['irls']


def rows_for(J, T):
    out = []
    for mid, evs in matches.items():
        e = ends[mid]
        if 1 not in e or 2 not in e:
            continue
        end1, end2 = e[1], e[2]
        if T < 45 and T > end1:
            continue
        rem = (end1 - T) + (end2 - 45) if T < 45 else end2 - T
        if rem <= 5:
            continue
        p_obs = 1 if J < 45 else 2
        el = T if T <= 45 else 45 + (T - 45)   # minutes of play so far (first-half stoppage ignored)
        for side in (0, 1):
            wat = defaultdict(int); wato = defaultdict(int); api = defaultdict(int); apio = defaultdict(int)
            y = 0; gl = glo = 0
            for p, t, s, c in evs:
                after = (p == 2 and t >= T) or (p == 1 and T < 45 and t >= T)
                if after:
                    if s == side and c == 'ck':
                        y += 1
                    continue
                own = s == side
                if J <= t and (p == p_obs or J < 45 <= T):
                    (wat if own else wato)[c] += 1
                if c in ('ck', 'xsh', 'xshb', 'xsht', 'xpa'):
                    (api if own else apio)[c] += 1
                if c == 'gl':
                    if own: gl += 1
                    else: glo += 1
            pas = api['xpa'] + apio['xpa']
            k = 45.0 / max(el, 1)
            out.append({'kind': kinds[mid], 'y': y, 'rem': rem, 'J': J, 'T': T,
                        'six': six_feats(wat, wato, T - J),
                        'api': [api['ck'] * k, apio['ck'] * k, api['xsh'] * k, api['xshb'] * k, api['xsht'] * k, api['xpa'] / pas if pas else 0.5],
                        'st': [1.0 if gl > glo else 0.0, 1.0 if gl < glo else 0.0], 'time': [T / 90.0]})
    return out


PAIRS = [(0, 10), (0, 20), (0, 30), (0, 40), (0, 55), (0, 65), (0, 75), (10, 20), (20, 30), (25, 35), (30, 40), (30, 45), (45, 50), (45, 55),
         (45, 60), (50, 65), (55, 65), (60, 70), (60, 75), (65, 75), (70, 80), (20, 40), (45, 70)]
allrows = []
for J, T in PAIRS:
    allrows += rows_for(J, T)
tr = [r for r in allrows if r['kind'] == 'club']
te = [r for r in allrows if r['kind'] == 'intl']


def mat(rs, parts):
    return np.array([sum((r[p] for p in parts), []) for r in rs], dtype=float)


def fit(parts):
    Xtr = mat(tr, parts)
    mu, sd = Xtr.mean(0), Xtr.std(0); sd[sd == 0] = 1
    A = np.column_stack([np.ones(len(Xtr)), (Xtr - mu) / sd])
    y = np.array([r['y'] for r in tr], float); off = np.log(np.array([r['rem'] for r in tr]) / 45)
    b = irls(A, y, off)
    return {'b0': float(b[0]), 'beta': b[1:].tolist(), 'mu': mu.tolist(), 'sd': sd.tolist(), 'parts': parts}


def score(model, rs):
    X = mat(rs, model['parts'])
    A = np.column_stack([np.ones(len(X)), (X - np.array(model['mu'])) / np.array(model['sd'])])
    lam = np.exp(A @ np.array([model['b0']] + model['beta']) + np.log(np.array([r['rem'] for r in rs]) / 45))
    y = np.array([r['y'] for r in rs], float)
    return {'corr': float(np.corrcoef(lam, y)[0, 1]), 'mae': float(np.abs(lam - y).mean()),
            'll': float(np.mean(y * np.log(lam) - lam - np.array([math.lgamma(v + 1) for v in y])))}


models = {'six': fit(['six', 'time']), 'six_api': fit(['six', 'api', 'time']), 'six_api_state': fit(['six', 'api', 'st', 'time'])}
report = {}
for (J, T) in PAIRS:
    sub = [r for r in te if r['J'] == J and r['T'] == T]
    report[f'J{J}_T{T}'] = {k: score(m, sub) for k, m in models.items()}
    report[f'J{J}_T{T}']['n'] = len(sub)
overall = {k: score(m, te) for k, m in models.items()}
print('overall (tournaments, all join/now pairs):', json.dumps(overall, ensure_ascii=False))
for k, v in report.items():
    print(k, 'n', v['n'], ' '.join(f"{m}:{v[m]['corr']:.3f}" for m in models))
json.dump({'models': models, 'overall': overall, 'by_pair': report, 'feat_names': {
    'six': ['到达每10分', '心态', '被挡率', '禁区内空间', '失误率', '45度占比'], 'api': ['角球/45', '对方角球/45', '射门/45', '被挡射门/45', '射正/45', '控球'],
    'st': ['领先', '落后'], 'time': ['已踢分钟/90']}}, open(OUTJ, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
