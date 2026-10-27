"""Average frequency of every recorded action and outcome, per team and minute, by half and home/away
(club 2015/16: EPL, La Liga, Serie A, Ligue 1). The app compares your live counts with these on the buttons.

Codes are the app's: ar arrival; d byline cross (from x >= 102, level with the box or nearer the byline),
e 45-degree cross (x < 102); p penetration; l long shot; s box shot; second letter = outcome; ck corner.

Usage: python3 -I six_rates.py <acts.csv> <halves.csv> <out_json>
"""
import csv
import json
import sys
from collections import defaultdict

ACTS, HALVES, OUT = sys.argv[1:4]
OC = {'cross': {'blk': 'b', 'clr': 'c', 'gk': 'g', 'ok': 'o', 'bad': 'x'}, 'pen': {'ok': 'o', 'lost': 'l'},
      'lshot': {'blk': 'b', 'parry': 'p', 'hold': 'h', 'off': 'x', 'goal': 'z'},
      'bshot': {'blk': 'b', 'parry': 'p', 'hold': 'h', 'off': 'x', 'goal': 'z'}}
CODES = (['ar'] + ['d' + o for o in 'bcgox'] + ['e' + o for o in 'bcgox'] + ['po', 'pl'] + ['l' + o for o in 'bphxz']
         + ['s' + o for o in 'bphxz'] + ['ck'])

cnt = defaultdict(lambda: defaultdict(int))     # (half, side) -> code -> count
mins = defaultdict(float)                      # (half, side) -> team minutes
n_team_matches = defaultdict(set)
for r in csv.DictReader(open(HALVES, encoding='utf-8')):
    if r['kind'] != 'club':
        continue
    key = (int(r['period']), int(r['side']))
    mins[key] += float(r['mins'])
    cnt[key]['ar'] += int(r['arr'])
    cnt[key]['ck'] += int(r['corners'])
    n_team_matches[int(r['side'])].add(r['match_id'])
for r in csv.DictReader(open(ACTS, encoding='utf-8')):
    if r['kind'] != 'club':
        continue
    key = (int(r['period']), int(r['side']))
    a = r['act']
    pre = ('d' if float(r['x']) >= 102 else 'e') if a == 'cross' else {'pen': 'p', 'lshot': 'l', 'bshot': 's'}[a]
    cnt[key][pre + OC[a][r['oc']]] += 1

rate = {str(h): [{c: round(cnt[(h, s)][c] / mins[(h, s)], 6) for c in CODES} for s in (0, 1)] for h in (1, 2)}

# per team per match (both halves), all teams and home / away
tm = {s: len(n_team_matches[s]) for s in (0, 1)}
per_match = {}
for c in CODES:
    tot = sum(cnt[(h, s)][c] for h in (1, 2) for s in (0, 1))
    per_match[c] = {'all': tot / (tm[0] + tm[1]), 'home': sum(cnt[(h, 0)][c] for h in (1, 2)) / tm[0], 'away': sum(cnt[(h, 1)][c] for h in (1, 2)) / tm[1],
                    'per10': tot / sum(mins.values()) * 10, 'per10_h1': sum(cnt[(1, s)][c] for s in (0, 1)) / (mins[(1, 0)] + mins[(1, 1)]) * 10,
                    'per10_h2': sum(cnt[(2, s)][c] for s in (0, 1)) / (mins[(2, 0)] + mins[(2, 1)]) * 10}
GROUP = {'d': '下底传中', 'e': '45度传中', 'p': '突破渗透', 'l': '远射', 's': '禁区射门'}
for g in GROUP:
    ks = [c for c in CODES if c[0] == g and len(c) == 2]
    per_match[g] = {k: sum(per_match[c][k] for c in ks) for k in ('all', 'home', 'away', 'per10', 'per10_h1', 'per10_h2')}
avg_half_len = {h: (mins[(h, 0)] + mins[(h, 1)]) / (len(n_team_matches[0]) + len(n_team_matches[1])) for h in (1, 2)}
json.dump({'rate': rate, 'per_match': per_match, 'team_matches': tm, 'half_len': avg_half_len}, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print('team-matches', tm, 'avg half length', {h: round(v, 1) for h, v in avg_half_len.items()})
for c in ['ar', 'd', 'e', 'p', 'l', 's', 'ck']:
    v = per_match[c]
    print(f"{c:3s} per match {v['all']:.2f} (home {v['home']:.2f}, away {v['away']:.2f})  per 10 min {v['per10']:.2f}  1st half {v['per10_h1']:.2f}  2nd half {v['per10_h2']:.2f}")
for g in GROUP:
    print(g, ' '.join(f"{c}:{per_match[c]['all']:.2f}" for c in CODES if c[0] == g and len(c) == 2))
