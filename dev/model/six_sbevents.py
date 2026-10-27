"""Events in the corner-sb app's definitions (same rules as corner-sb/dev/model/extract2.py) for the club
2015/16 leagues and the 2018-2024 tournaments: goals, red cards and corners for the base minute model, and
final-third entries, box entries and crosses to compare with corner-sb's own model (six_cbase.py).

Usage: python3 -I six_sbevents.py <statsbomb_repo> <out_dir> <n_procs>    ->  ev_sb.csv, mt_sb.csv
"""
import csv
import json
import os
import sys
from multiprocessing import Pool

COMPS = {(2, 27): ('Premier League', 'club'), (11, 27): ('La Liga', 'club'), (12, 27): ('Serie A', 'club'),
         (7, 27): ('Ligue 1', 'club'), (43, 106): ('World Cup 2022', 'intl'), (55, 282): ('Euro 2024', 'intl'),
         (223, 282): ('Copa America 2024', 'intl'), (1267, 107): ('AFCON 2023', 'intl'),
         (43, 3): ('World Cup 2018', 'intl'), (55, 43): ('Euro 2020', 'intl')}
SET_PIECE = {'Corner', 'Free Kick', 'Throw-in', 'Goal Kick', 'Kick Off'}
SHOT_MAP = {'Blocked': 'sb', 'Saved': 'ss', 'Saved Off T': 'ss', 'Saved To Post': 'ss',
            'Off T': 'so', 'Post': 'so', 'Wayward': 'so', 'Goal': 'sg'}
RED = {'Red Card', 'Second Yellow'}
REPO = None


def ts(s):
    h, m, x = s.split(':')
    return int(h) * 3600 + int(m) * 60 + float(x)


def in_box(p):
    return p is not None and p[0] >= 102 and 18 <= p[1] <= 62


def process(job):
    league, kind, m = job
    mid = m['match_id']
    ev = json.load(open(os.path.join(REPO, 'data', 'events', f'{mid}.json'), encoding='utf-8'))
    home = m['home_team']['home_team_name']
    rows, plen = [], {1: 0.0, 2: 0.0}
    for e in ev:
        per = e.get('period')
        if per not in (1, 2):
            continue
        t = ts(e['timestamp'])
        plen[per] = max(plen[per], t)
        typ = e['type']['name']
        team = e.get('team', {}).get('name')
        code = None
        if typ == 'Pass':
            p = e['pass']
            ptype = p.get('type', {}).get('name')
            done = 'outcome' not in p
            if ptype == 'Corner':
                code = 'ck'
            elif ptype not in SET_PIECE:
                s, en = e.get('location'), p.get('end_location')
                if p.get('cross'):
                    code = 'co' if done else 'cf'
                elif done and s and en:
                    if in_box(en) and not in_box(s):
                        code = 'bx'
                    elif s[0] < 80 <= en[0]:
                        code = 'f3'
        elif typ == 'Carry':
            s, en = e.get('location'), e['carry'].get('end_location')
            if s and en:
                if in_box(en) and not in_box(s):
                    code = 'bx'
                elif s[0] < 80 <= en[0]:
                    code = 'f3'
        elif typ == 'Shot':
            code = SHOT_MAP.get(e['shot']['outcome']['name'])
        elif typ == 'Own Goal For':
            code = 'og'
        elif typ == 'Foul Committed':
            if e.get('foul_committed', {}).get('card', {}).get('name') in RED:
                code = 'rc'
        elif typ == 'Bad Behaviour':
            if e.get('bad_behaviour', {}).get('card', {}).get('name') in RED:
                code = 'rc'
        if code:
            rows.append({'match_id': mid, 'period': per, 't': round(t, 2), 'side': 1 if team == home else 0, 'code': code})
    meta = {'match_id': mid, 'kind': kind, 'league': league, 'home': home, 'away': m['away_team']['away_team_name'],
            'p1_len': round(plen[1], 1), 'p2_len': round(plen[2], 1)}
    return meta, rows


if __name__ == '__main__':
    REPO, OUT, NP = sys.argv[1], sys.argv[2], int(sys.argv[3])
    jobs = []
    for (cid, sid), (lg, kind) in COMPS.items():
        for m in json.load(open(os.path.join(REPO, 'data', 'matches', str(cid), f'{sid}.json'), encoding='utf-8')):
            if os.path.exists(os.path.join(REPO, 'data', 'events', f"{m['match_id']}.json")):
                jobs.append((lg, kind, m))
    with Pool(NP) as pool:
        res = pool.map(process, jobs, chunksize=8)
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, 'ev_sb.csv'), 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=['match_id', 'period', 't', 'side', 'code'])
        w.writeheader()
        for _, rows in res:
            w.writerows(rows)
    with open(os.path.join(OUT, 'mt_sb.csv'), 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=list(res[0][0].keys()))
        w.writeheader()
        w.writerows([r[0] for r in res])
    print('matches', len(res))
