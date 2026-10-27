"""Time-stamped events in the app's codes, for the "joining midway" analysis.

One row per event: match_id, kind, period, side, minute (match clock in minutes, second half from 45),
code (the app's codes: ar, d?/e? crosses, p? dribble or penetration, l?/s? shots, ck corner, gl goal),
plus rows for what a live-score API also has: xsh (shot), xshb (blocked shot), xsht (shot on target incl. goals),
xpa (completed pass, for possession share). (x-prefix: 'sh' is already the app's code for a box shot held by the keeper.)

Usage: python3 -I six_timeline.py <statsbomb_repo> <out_csv> <n_procs>
"""
import csv
import json
import os
import sys
from multiprocessing import Pool

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import six_extract as X

REPO = OUT = None
OC = {'cross': {'blk': 'b', 'clr': 'c', 'gk': 'g', 'ok': 'o', 'bad': 'x'}, 'pen': {'ok': 'o', 'lost': 'l'},
      'lshot': {'blk': 'b', 'parry': 'p', 'hold': 'h', 'off': 'x', 'goal': 'z'},
      'bshot': {'blk': 'b', 'parry': 'p', 'hold': 'h', 'off': 'x', 'goal': 'z'}}


def process(job):
    comp, kind, m = job
    mid = m['match_id']
    ev = json.load(open(os.path.join(REPO, 'data', 'events', f'{mid}.json'), encoding='utf-8'))
    teams = (m['home_team']['home_team_name'], m['away_team']['away_team_name'])
    byid = {e['id']: e for e in ev}
    out = []
    stB, spb = {0: False, 1: False}, {0: False, 1: False}
    seenA = set()
    cur = None
    for i, e in enumerate(ev):
        per = e.get('period')
        if per not in (1, 2):
            continue
        if per != cur:
            cur = per
            spb = {0: False, 1: False}
        team = e.get('team', {}).get('name')
        if team not in teams:
            continue
        s = teams.index(team)
        mins = X.ts(e) / 60.0 + (45 if per == 2 else 0)
        row = lambda code: out.append((mid, kind, per, s, round(mins, 3), code))
        typ = e['type']['name']
        loc = e.get('location')
        pt = X.ptype(e)
        # arrivals (same rule as six_extract: once per possession, corner / free-kick deliveries excluded)
        if X.ends_other(e):
            spb[1 - s] = False
        if pt in X.SET_PIECE:
            spb = {0: False, 1: False}
            if pt in ('Corner', 'Free Kick'):
                spb[s] = True
        elif X.is_control(e) and loc is not None:
            pts = [loc[0]]
            if typ == 'Pass' and 'outcome' not in e['pass'] and e['pass'].get('end_location'):
                pts.append(e['pass']['end_location'][0])
            if typ == 'Carry' and e['carry'].get('end_location'):
                pts.append(e['carry']['end_location'][0])
            pkey = (per, e.get('possession'))
            own = e.get('possession_team', {}).get('name') == team
            for x in pts:
                if x < X.F3:
                    spb[s] = False
                if spb[s]:
                    continue
                if x >= X.NEAR and own and pkey not in seenA:
                    seenA.add(pkey)
                    row('ar')
        # actions
        if typ == 'Pass' and X.is_cross(e, ev, i):
            oc = X.cross_outcome(ev, i, team, byid)
            row(('d' if loc[0] >= 102 else 'e') + OC['cross'][oc])
        elif X.is_pen(e, ev, i):
            row('p' + OC['pen'][X.pen_outcome(ev, i, team, byid)])
        elif typ == 'Shot' and e['shot'].get('type', {}).get('name') == 'Open Play':
            oc = X.shot_outcome(ev, i, team, byid)
            row(('s' if X.in_box(loc) else 'l') + OC['bshot'][oc])
        if pt == 'Corner':
            row('ck')
        if (typ == 'Shot' and e['shot']['outcome']['name'] == 'Goal') or typ == 'Own Goal For':
            row('gl')
        # what a live-score API also has
        if typ == 'Shot':
            row('xsh')
            o = e['shot']['outcome']['name']
            if o == 'Blocked':
                row('xshb')
            if o in X.SAVED or o == 'Goal':
                row('xsht')
        if typ == 'Pass' and 'outcome' not in e['pass']:
            row('xpa')
    # match length per period (for exposure)
    for per in (1, 2):
        last = max((X.ts(e) for e in ev if e.get('period') == per), default=0) / 60.0
        out.append((mid, kind, per, -1, round(last + (45 if per == 2 else 0), 3), 'end'))
    return out


if __name__ == '__main__':
    REPO, OUT, NP = sys.argv[1], sys.argv[2], int(sys.argv[3])
    X.REPO = REPO
    jobs = []
    for (cid, sid), (comp, kind) in X.COMPS.items():
        for m in json.load(open(os.path.join(REPO, 'data', 'matches', str(cid), f'{sid}.json'), encoding='utf-8')):
            if os.path.exists(os.path.join(REPO, 'data', 'events', f"{m['match_id']}.json")):
                jobs.append((comp, kind, m))
    with open(OUT, 'w', newline='', encoding='utf-8') as f, Pool(NP) as pool:
        w = csv.writer(f)
        w.writerow(['match_id', 'kind', 'period', 'side', 'minute', 'code'])
        n = 0
        for rows in pool.imap_unordered(process, jobs, chunksize=4):
            w.writerows(rows)
            n += 1
    print('matches', n)
