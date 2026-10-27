"""Baselines for the six factors, corner yields per outcome, where corners come from, and checks of the logic.

Input: halves.csv / acts.csv / corners.csv from six_extract.py
Output: baseline.json (embedded in the app) and report.json (numbers for the write-up)

Usage: python3 -I six_baseline.py <in_dir> <out_dir>
"""
import csv
import json
import math
import os
import random
import sys
from collections import Counter, defaultdict

IN, OUT = sys.argv[1], sys.argv[2]
os.makedirs(OUT, exist_ok=True)
NUM = ['mins', 'arr', 'arrB', 'arr80', 'tilt_touch', 'cross', 'cross_blk', 'cross_clr', 'cross_gk', 'cross_ok', 'cross_bad',
       'cross_press', 'pen', 'pen_ok', 'pen_lost', 'lshot', 'lshot_blk', 'lshot_hold', 'lshot_parry', 'lshot_off',
       'lshot_goal', 'bshot', 'bshot_blk', 'bshot_hold', 'bshot_parry', 'bshot_off', 'bshot_goal', 'corners', 'goals',
       'score_for_start', 'score_against_start']
rows = []
for r in csv.DictReader(open(os.path.join(IN, 'halves.csv'), encoding='utf-8')):
    for k in NUM:
        r[k] = float(r[k])
    rows.append(r)
by_key = {(r['match_id'], r['period'], r['side']): r for r in rows}
for r in rows:
    r['dcross'] = r['ecross'] = 0.0
for a in csv.DictReader(open(os.path.join(IN, 'acts.csv'), encoding='utf-8')):
    if a['act'] == 'cross':
        by_key[(a['match_id'], a['period'], a['side'])]['dcross' if float(a['x']) >= 102 else 'ecross'] += 1
for r in rows:
    o = by_key[(r['match_id'], r['period'], '1' if r['side'] == '0' else '0')]
    r['opp_arr'] = o['arr']
    r['opp_tilt'] = o['tilt_touch']
    r['opp_corners'] = o['corners']


def team_match(rs):
    """Sum the two halves of each team-match."""
    g = defaultdict(list)
    for r in rs:
        g[(r['match_id'], r['side'])].append(r)
    out = []
    for k, two in g.items():
        if len(two) != 2:
            continue
        m = {key: two[0][key] for key in ('match_id', 'comp', 'kind', 'side', 'team', 'opp')}
        for key in NUM + ['opp_arr', 'opp_tilt', 'opp_corners', 'dcross', 'ecross']:
            m[key] = two[0][key] + two[1][key]
        out.append(m)
    return out


def metrics(r):
    """The six-factor metrics of one team-half or team-match (None when the denominator is empty)."""
    d = lambda a, b: a / b if b > 0 else None
    shots = r['lshot'] + r['bshot']
    acts = r['cross'] + r['pen'] + r['lshot']
    unb = (r['cross'] - r['cross_blk']) + (r['lshot'] - r['lshot_blk']) + (r['bshot'] - r['bshot_blk'])
    err = r['cross_bad'] + r['lshot_off'] + r['bshot_off'] + r['lshot_hold'] + r['bshot_hold']
    inbox = r['cross_ok'] + r['cross_clr'] + r['cross_gk'] + r['bshot']
    return {
        'f1_rate': r['arr'] / r['mins'] * 10 if r['mins'] > 0 else None,          # arrivals per 10 minutes
        'f1_share': d(r['arr'], r['arr'] + r['opp_arr']),                          # share of both teams' arrivals
        'f2_cross': d(r['cross'], r['arr']),                                       # crosses per arrival
        'f2_dcross': d(r['dcross'], r['arr']),                                     # crosses from beside the box (byline)
        'f2_ecross': d(r['ecross'], r['arr']),                                     # crosses from outside the box line (deep, 45 degrees)
        'f2_deep_share': d(r['ecross'], r['cross']),
        'f2_pen': d(r['pen'], r['arr']),                                           # dribbles / penetrations per arrival
        'f2_lshot': d(r['lshot'], r['arr']),                                       # long shots per arrival
        'f2_mix_cross': d(r['cross'], acts), 'f2_mix_pen': d(r['pen'], acts), 'f2_mix_lshot': d(r['lshot'], acts),
        'f3_space': d(r['cross_ok'] + r['bshot'] - r['bshot_blk'], inbox),         # in the box the attackers win it
        'f3_cross_ok': d(r['cross_ok'], r['cross_ok'] + r['cross_clr'] + r['cross_gk']),
        'f4_block': d(r['cross_blk'] + r['lshot_blk'] + r['pen_lost'], r['cross'] + r['lshot'] + r['pen']),
        'f4_cross_blk': d(r['cross_blk'], r['cross']),
        'f5_aggr': d(r['cross'] + shots, r['arr']),                                # crosses + shots per arrival
        'f6_err': d(err, unb),                                                     # own errors among unblocked balls
        'corner_rate': r['corners'] / r['mins'] * 10 if r['mins'] > 0 else None,
    }


def pct(vals, qs=(0.2, 0.4, 0.6, 0.8)):
    v = sorted(x for x in vals if x is not None)
    if not v:
        return None
    out = []
    for q in qs:
        k = q * (len(v) - 1)
        lo, hi = int(math.floor(k)), int(math.ceil(k))
        out.append(v[lo] + (v[hi] - v[lo]) * (k - lo))
    return out


def summary(rs, scope):
    M = [metrics(r) for r in rs]
    keys = list(M[0].keys())
    out = {}
    for k in keys:
        vals = [m[k] for m in M if m[k] is not None]
        if not vals:
            continue
        out[k] = {'mean': sum(vals) / len(vals), 'q': pct(vals), 'n': len(vals)}
    # pooled ratios (sum of numerators / sum of denominators) are more stable than means of ratios
    S = {k: sum(r[k] for r in rs) for k in NUM + ['opp_arr', 'dcross', 'ecross']}
    mins = S['mins']
    per = 45.0 if scope == 'half' else 90.0
    out['vol'] = {k: S[k] / len(rs) for k in ('arr', 'arrB', 'arr80', 'cross', 'cross_blk', 'cross_clr', 'cross_gk', 'cross_ok', 'cross_bad',
                                             'pen', 'pen_ok', 'pen_lost', 'lshot', 'lshot_blk', 'lshot_hold', 'lshot_parry', 'lshot_off',
                                             'lshot_goal', 'bshot', 'bshot_blk', 'bshot_hold', 'bshot_parry', 'bshot_off', 'bshot_goal',
                                             'corners', 'goals', 'mins')}
    out['pooled'] = metrics(S | {'opp_arr': S['opp_arr']})
    out['n_rows'] = len(rs)
    return out


def yields(acts):
    c = defaultdict(lambda: [0, 0])
    for a in acts:
        k = a['act'] + '_' + a['oc']
        c[k][0] += 1
        c[k][1] += int(a['ck'])
        c[a['act']][0] += 1
        c[a['act']][1] += int(a['ck'])
    return {k: {'n': v[0], 'p': v[1] / v[0]} for k, v in sorted(c.items())}


acts = list(csv.DictReader(open(os.path.join(IN, 'acts.csv'), encoding='utf-8')))
corners = list(csv.DictReader(open(os.path.join(IN, 'corners.csv'), encoding='utf-8')))
club_h = [r for r in rows if r['kind'] == 'club']
intl_h = [r for r in rows if r['kind'] == 'intl']
club_m, intl_m = team_match(club_h), team_match(intl_h)

report = {'n': {'club_matches': len(club_m) // 2, 'intl_matches': len(intl_m) // 2, 'club_halves': len(club_h), 'intl_halves': len(intl_h)}}
report['half'] = {'club': summary(club_h, 'half'), 'intl': summary(intl_h, 'half')}
report['match'] = {'club': summary(club_m, 'match'), 'intl': summary(intl_m, 'match')}
report['yield'] = {'club': yields([a for a in acts if a['kind'] == 'club']), 'intl': yields([a for a in acts if a['kind'] == 'intl'])}
# home / away corners and arrivals
for kind, hs in (('club', club_h), ('intl', intl_h)):
    for side in ('0', '1'):
        sub = [r for r in hs if r['side'] == side]
        report.setdefault('side', {}).setdefault(kind, {})[side] = {
            'corners_half': sum(r['corners'] for r in sub) / len(sub), 'arr_half': sum(r['arr'] for r in sub) / len(sub)}
    for per in ('1', '2'):
        sub = [r for r in hs if r['period'] == per]
        report.setdefault('period', {}).setdefault(kind, {})[per] = {
            'corners': sum(r['corners'] for r in sub) / len(sub), 'arr': sum(r['arr'] for r in sub) / len(sub),
            'cross': sum(r['cross'] for r in sub) / len(sub), 'mins': sum(r['mins'] for r in sub) / len(sub)}

# where corners come from
GROUP = {'cross_blk': '传中被挡', 'cross_clr': '传中被解围', 'cross_gk': '传中被门将处理', 'cross_ok': '传中到人后',
         'cross_bad': '传中失误', 'pen_lost': '突破渗透被断', 'pen_ok': '突破渗透成功后',
         'lshot_blk': '远射被挡', 'lshot_parry': '远射被扑出', 'lshot_hold': '远射被没收', 'lshot_off': '远射偏出',
         'bshot_blk': '禁区射门被挡', 'bshot_parry': '禁区射门被扑出', 'bshot_hold': '禁区射门被没收', 'bshot_off': '禁区射门偏出',
         'from_corner': '角球后（连角球）', 'from_fk': '任意球后', 'from_throw': '界外球后'}
for kind in ('club', 'intl'):
    cc = Counter(GROUP.get(c['cat'], '其他') for c in corners if c['kind'] == kind)
    tot = sum(cc.values())
    report.setdefault('origins', {})[kind] = {'total': tot, 'share': {k: v / tot for k, v in cc.most_common()}}
    raw = Counter(c['cat'] for c in corners if c['kind'] == kind)
    report.setdefault('origins_raw', {})[kind] = dict(raw.most_common())

# cross corner yield by where it was hit from and pressure
def cross_yield(sub):
    g = defaultdict(lambda: [0, 0])
    for a in sub:
        x = float(a['x'])
        zone = 'byline' if x >= 102 else 'deep' if x < 102 else '?'
        g[(zone, a['oc'])][0] += 1
        g[(zone, a['oc'])][1] += int(a['ck'])
        g[(zone, 'all')][0] += 1
        g[(zone, 'all')][1] += int(a['ck'])
        g[('press' if a['press'] == '1' else 'free', 'all')][0] += 1
        g[('press' if a['press'] == '1' else 'free', 'all')][1] += int(a['ck'])
        g[('press' if a['press'] == '1' else 'free', a['oc'])][0] += 1
    return {f'{k[0]}|{k[1]}': {'n': v[0], 'p': v[1] / v[0] if v[0] else 0} for k, v in sorted(g.items())}


report['cross_zone'] = cross_yield([a for a in acts if a['act'] == 'cross' and a['kind'] == 'club'])

# ---------- does the logic explain corners? (club team-halves) ----------
Y = report['yield']['club']
OUTC = ['cross_blk', 'cross_clr', 'cross_gk', 'cross_ok', 'cross_bad', 'pen_ok', 'pen_lost', 'lshot_blk', 'lshot_hold',
        'lshot_parry', 'lshot_off', 'lshot_goal', 'bshot_blk', 'bshot_hold', 'bshot_parry', 'bshot_off', 'bshot_goal']


def corr(x, y):
    n = len(x)
    mx, my = sum(x) / n, sum(y) / n
    sx = math.sqrt(sum((a - mx) ** 2 for a in x))
    sy = math.sqrt(sum((b - my) ** 2 for b in y))
    return sum((a - mx) * (b - my) for a, b in zip(x, y)) / (sx * sy)


def explain(rs):
    y = [r['corners'] for r in rs]
    avg_y = {a: Y[a]['p'] for a in ('cross', 'pen', 'lshot', 'bshot')}
    l1 = [r['arr'] for r in rs]
    l2 = [sum(r[a] * avg_y[a] for a in ('cross', 'pen', 'lshot', 'bshot')) for r in rs]
    l3 = [sum(r[o] * Y[o]['p'] for o in OUTC) for r in rs]
    return {'n': len(rs), 'r_arrivals': corr(l1, y), 'r_actions': corr(l2, y), 'r_outcomes': corr(l3, y),
            'xc_mean': sum(l3) / len(l3), 'corners_mean': sum(y) / len(y), 'share_from_actions': sum(l3) / sum(y)}


report['explain'] = {'half': explain(club_h), 'match': explain(club_m)}

# ---------- the user's two cases and others (club team-matches, levels by quintile) ----------
TM = club_m
Mm = [metrics(r) for r in TM]
Q = report['match']['club']


def lvl(v, q, invert=False):
    if v is None or q is None:
        return None
    k = sum(1 for c in q if v > c) + 1
    return 6 - k if invert else k


for r, m in zip(TM, Mm):
    r['L1'] = lvl(m['f1_rate'], Q['f1_rate']['q'])
    r['L5'] = lvl(m['f5_aggr'], Q['f5_aggr']['q'])
    r['L4'] = lvl(m['f4_block'], Q['f4_block']['q'], invert=True)       # 5 = lots of space outside the box
    r['L3'] = lvl(m['f3_space'], Q['f3_space']['q'])                     # 5 = lots of space in the box
    r['L6'] = lvl(m['f6_err'], Q['f6_err']['q'], invert=True)           # 5 = few own errors
    r['L2c'] = lvl(m['f2_mix_cross'], Q['f2_mix_cross']['q'])


def grp(sel):
    s = [r for r in TM if sel(r)]
    if not s:
        return {'n': 0}
    return {'n': len(s), 'corners': sum(r['corners'] for r in s) / len(s), 'arr': sum(r['arr'] for r in s) / len(s),
            'cross': sum(r['cross'] for r in s) / len(s), 'shots': sum(r['lshot'] + r['bshot'] for r in s) / len(s)}


cases = {}
cases['all'] = grp(lambda r: True)
for k in ('L1', 'L5', 'L4', 'L3', 'L6', 'L2c'):
    cases['by_' + k] = {str(v): grp(lambda r, v=v, k=k: r[k] == v) for v in range(1, 6)}
hi = lambda r: r['L5'] is not None and r['L5'] >= 4
hi1 = lambda r: r['L1'] is not None and r['L1'] >= 3
cases['aggr_hi'] = grp(lambda r: hi(r) and hi1(r))
cases['case1_open_out_poor_quality'] = grp(lambda r: hi(r) and hi1(r) and r['L4'] >= 4 and r['L6'] <= 2)
cases['case1_open_out_good_quality'] = grp(lambda r: hi(r) and hi1(r) and r['L4'] >= 4 and r['L6'] >= 4)
cases['case2_cross_open_out_tight_in'] = grp(lambda r: hi(r) and hi1(r) and r['L2c'] >= 4 and r['L4'] >= 4 and r['L3'] <= 2)
cases['case2b_cross_open_out_open_in'] = grp(lambda r: hi(r) and hi1(r) and r['L2c'] >= 4 and r['L4'] >= 4 and r['L3'] >= 4)
cases['tight_out_any'] = grp(lambda r: hi(r) and hi1(r) and r['L4'] <= 2)
cases['open_out_any'] = grp(lambda r: hi(r) and hi1(r) and r['L4'] >= 4)
# two-way tables: aggression x outside space, aggression x quality
for a, b in (('L5', 'L4'), ('L5', 'L6'), ('L4', 'L6'), ('L1', 'L5')):
    t = {}
    for va in (1, 2, 3, 4, 5):
        for vb in (1, 2, 3, 4, 5):
            g = grp(lambda r, va=va, vb=vb: r[a] == va and r[b] == vb)
            t[f'{va}{vb}'] = [round(g.get('corners', 0), 2), g['n']]
    cases[f'tab_{a}_{b}'] = t
report['cases'] = cases

# keeper behaviour: share of crosses claimed by the keeper vs corners per cross (opponent keeper effect)
gk = defaultdict(lambda: [0, 0, 0])
for r in club_m:
    gk[(r['opp'],)][0] += r['cross_gk']
    gk[(r['opp'],)][1] += r['cross']
    gk[(r['opp'],)][2] += r['corners']
report['gk_teams'] = sorted(((k[0], v[0] / v[1], v[2] / v[1]) for k, v in gk.items() if v[1] > 200), key=lambda x: -x[1])[:8]

# ---------- baseline.json for the app (club 2015/16 + check against recent tournaments) ----------
def comp(scope):
    s = report[scope]['club']
    keep = {}
    for k in ('f1_rate', 'f1_share', 'f2_cross', 'f2_dcross', 'f2_ecross', 'f2_deep_share', 'f2_pen', 'f2_lshot', 'f2_mix_cross', 'f2_mix_pen', 'f2_mix_lshot',
              'f3_space', 'f3_cross_ok', 'f4_block', 'f4_cross_blk', 'f5_aggr', 'f6_err', 'corner_rate'):
        if k in s:
            keep[k] = {'m': round(s[k]['mean'], 4), 'q': [round(x, 4) for x in s[k]['q']]}
    keep['vol'] = {k: round(v, 3) for k, v in s['vol'].items()}
    keep['pooled'] = {k: (round(v, 4) if v is not None else None) for k, v in s['pooled'].items()}
    return keep


def app_yields():
    """Corner chance per recorded outcome, with the app's codes: d byline cross, e deep cross, p dribble or
    penetration, l long shot, s shot in the box; a lone letter is the action with its outcome not recorded."""
    cz = report['cross_zone']
    y = {}
    for zone, L in (('byline', 'd'), ('deep', 'e')):
        for oc, c in (('blk', 'b'), ('clr', 'c'), ('gk', 'g'), ('ok', 'o'), ('bad', 'x'), ('all', '')):
            y[L + c] = round(cz[f'{zone}|{oc}']['p'], 4)
    Y = report['yield']['club']
    y['p'], y['po'], y['pl'] = round(Y['pen']['p'], 4), round(Y['pen_ok']['p'], 4), round(Y['pen_lost']['p'], 4)
    for act, L in (('lshot', 'l'), ('bshot', 's')):
        y[L] = round(Y[act]['p'], 4)
        for oc, c in (('blk', 'b'), ('parry', 'p'), ('hold', 'h'), ('off', 'x'), ('goal', 'z')):
            y[L + c] = round(Y[f'{act}_{oc}']['p'], 4)
    return y


CODE = {'cross_blk': 'cb', 'cross_clr': 'cc', 'cross_gk': 'cg', 'cross_ok': 'co', 'cross_bad': 'cx', 'pen_ok': 'po',
        'pen_lost': 'pl', 'lshot_blk': 'lb', 'lshot_parry': 'lp', 'lshot_hold': 'lh', 'lshot_off': 'lx', 'lshot_goal': 'lg',
        'bshot_blk': 'bb', 'bshot_parry': 'bp', 'bshot_hold': 'bh', 'bshot_off': 'bx', 'bshot_goal': 'bg',
        'cross': 'c', 'pen': 'p', 'lshot': 'l', 'bshot': 'b'}
base = {'src': 'StatsBomb Open Data 2015/16 英超、西甲、意甲、法甲',
        'n': {'matches': report['n']['club_matches'], 'halves': report['n']['club_halves']},
        'half': comp('half'), 'match': comp('match'),
        'yield': app_yields(),
        'side': {k: {kk: round(vv, 3) for kk, vv in v.items()} for k, v in report['side']['club'].items()},
        'origins': {k: round(v, 4) for k, v in report['origins']['club']['share'].items()}}
json.dump(base, open(os.path.join(OUT, 'baseline.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
json.dump(report, open(os.path.join(OUT, 'report.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1, default=str)
print('ok')
