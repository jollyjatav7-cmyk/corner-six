"""Six-factor baselines from StatsBomb open data.

For every team and half: arrivals near the opponent's box, crosses / central penetrations / long shots / shots in
the box with their outcomes, corners and goals.  Also one row per action (with whether it led straight to a
corner) and one row per corner (where it came from).

Definitions (StatsBomb 120 x 80 pitch, every team attacking towards x = 120 in its own events)
  arrival  the team gets the ball under control within 30 yards of the opponent's goal line (x >= 90), open play.
           A new arrival starts after the opponent had the ball under control, after a stoppage, or after the
           ball went back to x < 80.  Corner kicks, free kicks and throw-ins themselves are not arrivals.
  cross    open-play pass marked cross, or an open-play pass from a wide area (y < 18 or y > 62, x >= 80) that
           ends in the box
  pen      central penetration: open-play pass (not a cross) from outside the box that ends in the box,
           a carry from outside into the box, or a failed dribble in front of the box (x >= 96, 18 <= y <= 62)
  lshot    open-play shot from outside the box (no direct free kicks)
  bshot    open-play shot inside the box (no penalties)
Outcomes
  cross   blk blocked near the crosser | clr cleared or intercepted by a defender | gk keeper claimed or punched |
          ok  a team-mate got it | bad out of play, offside, or nobody touched it
  pen     ok  reached the box | lost blocked, intercepted, tackled
  shots   blk blocked | hold saved and held | parry saved but not held | off off target or post | goal
An action "led to a corner" when it is the attacking team's last on-ball action before the corner kick and the
defending side never had the ball under control in between (same rule as corner-sb/dev/model/extract3.py).

Usage: python3 -I six_extract.py <statsbomb_repo> <out_dir> <n_procs>
"""
import csv
import json
import math
import os
import sys
from multiprocessing import Pool

REPO = OUT = NP = None
COMPS = {(2, 27): ('Premier League', 'club'), (11, 27): ('La Liga', 'club'), (12, 27): ('Serie A', 'club'),
         (7, 27): ('Ligue 1', 'club'), (43, 106): ('World Cup 2022', 'intl'), (55, 282): ('Euro 2024', 'intl'),
         (223, 282): ('Copa America 2024', 'intl'), (1267, 107): ('AFCON 2023', 'intl'),
         (43, 3): ('World Cup 2018', 'intl'), (55, 43): ('Euro 2020', 'intl')}
SET_PIECE = {'Corner', 'Free Kick', 'Throw-in', 'Goal Kick', 'Kick Off'}
SKIP = {'Ball Receipt*', 'Pressure', 'Substitution', 'Tactical Shift', 'Injury Stoppage', 'Referee Ball-Drop',
        'Player Off', 'Player On', 'Bad Behaviour', 'Starting XI', 'Half Start', 'Half End', 'Foul Committed',
        'Foul Won', 'Shield', 'Error', 'Camera On', 'Camera off', 'Offside', '50/50'}
ATTACK = {'Shot', 'Pass', 'Carry', 'Dribble', 'Duel', 'Miscontrol', 'Dispossessed'}
SAVED = {'Saved', 'Saved Off T', 'Saved To Post', 'Saved Off Target', 'Saved to Post'}
OFF = {'Off T', 'Wayward', 'Post'}
GK_CLAIM = {'Collected', 'Punch', 'Smother', 'Keeper Sweeper', 'Claim'}
NEAR, F3 = 90.0, 80.0


def ts(e):
    h, m, x = e['timestamp'].split(':')
    return int(h) * 3600 + int(m) * 60 + float(x)


def in_box(p):
    return p is not None and p[0] >= 102 and 18 <= p[1] <= 62


def ptype(e):
    return e['pass'].get('type', {}).get('name') if e['type']['name'] == 'Pass' else None


def last_attack(chain, A):
    """chain: on-ball events before the corner kick, most recent first (same rule as extract3.classify)."""
    b_last = None
    for e in chain:
        team = e.get('team', {}).get('name')
        typ = e['type']['name']
        if team != A:
            if b_last is None:
                b_last = e
            if typ == 'Pass' and 'outcome' not in e['pass']:
                return None, b_last
            continue
        if typ in ATTACK:
            return e, b_last
    return None, b_last


def corner_cat(a, b):
    bt = b['type']['name'] if b is not None else None
    gk = b.get('goalkeeper', {}).get('type', {}).get('name') if bt == 'Goal Keeper' else None
    if a is None:
        return 'def_own'                     # the defenders put it out from their own play
    at = a['type']['name']
    if at == 'Shot':
        oc = a['shot']['outcome']['name']
        if oc in SAVED or gk in ('Shot Saved', 'Save', 'Shot Saved Off Target', 'Shot Saved to Post'):
            return 'shot_saved'
        if oc == 'Blocked':
            return 'shot_blocked'
        return 'shot_other'
    if at == 'Pass':
        pt = ptype(a)
        if pt == 'Corner':
            return 'from_corner'
        if pt == 'Free Kick':
            return 'from_fk'
        if pt == 'Throw-in':
            return 'from_throw'
        if pt in ('Goal Kick', 'Kick Off'):
            return 'pass_other'
        if is_cross(a):
            if bt == 'Block':
                return 'cross_blocked'
            if bt in ('Clearance', 'Interception'):
                return 'cross_cleared'
            if bt == 'Goal Keeper':
                return 'cross_gk'
            return 'cross_other'
        if bt == 'Block':
            return 'pass_blocked'
        if bt in ('Clearance', 'Interception'):
            return 'pass_cleared'
        if bt == 'Goal Keeper':
            return 'pass_gk'
        return 'pass_other'
    return 'dribble'


def wide(loc):
    """Crossing zones: the flanks of the last 30 yards, and the wide parts of the box near the byline."""
    if loc is None or loc[0] < NEAR:
        return False
    if loc[1] < 18 or loc[1] > 62:
        return True
    return loc[0] >= 102 and (loc[1] < 30 or loc[1] > 50)


def is_cross(e, ev=None, i=None):
    """Open-play cross: marked cross by StatsBomb, or a pass from the wide area of the last 30 yards that ends in
    the box, or one that a defender blocks within 10 yards (StatsBomb does not mark those as crosses)."""
    if e['type']['name'] != 'Pass' or ptype(e) in SET_PIECE:
        return False
    p = e['pass']
    if p.get('cross'):
        return True
    loc, en = e.get('location'), p.get('end_location')
    if not wide(loc) or en is None:
        return False
    if in_box(en) and (not in_box(loc) or abs(en[1] - 40) < abs(loc[1] - 40)):
        return True
    if 'outcome' in p and ev is not None and abs(en[1] - 40) < abs(loc[1] - 40):
        d = next_def(ev, i, e['team']['name'])
        if d is not None and d.get('location') and d['type']['name'] in ('Block', 'Clearance', 'Interception', 'Duel'):
            dx, dy = 120 - d['location'][0], 80 - d['location'][1]
            return math.hypot(dx - loc[0], dy - loc[1]) <= 10
    return False


def is_pen(e, ev=None, i=None):
    """Dribble / central penetration toward the box (not a cross): a central pass from the last third into the
    box, a carry into the box, a failed dribble or a tackle on the ball carrier in the last 30 yards."""
    typ = e['type']['name']
    loc = e.get('location')
    if typ == 'Pass':
        if ptype(e) in SET_PIECE or is_cross(e, ev, i):
            return False
        en = e['pass'].get('end_location')
        if not (loc and en and loc[0] >= F3 and 18 <= loc[1] <= 62 and not in_box(loc)):
            return False
        if in_box(en):
            return True
        if 'outcome' in e['pass'] and ev is not None and en[0] >= loc[0] - 2:   # forward pass blocked at once
            d = next_def(ev, i, e['team']['name'])
            if d is not None and d.get('location') and d['type']['name'] in ('Block', 'Clearance', 'Interception', 'Duel'):
                dx, dy = 120 - d['location'][0], 80 - d['location'][1]
                return math.hypot(dx - loc[0], dy - loc[1]) <= 10
        return False
    if typ == 'Carry':
        en = e['carry'].get('end_location')
        return bool(loc and en and not in_box(loc) and in_box(en))
    if typ == 'Dribble':
        oc = e['dribble'].get('outcome', {}).get('name')
        return bool(loc and oc == 'Incomplete' and loc[0] >= NEAR)
    if typ == 'Dispossessed':
        return bool(loc and loc[0] >= NEAR)
    return False


def next_def(ev, i, A, window=3.0):
    """First defending-team event after i within `window` seconds (skips receipts and pressure)."""
    t0 = ts(ev[i])
    for x in ev[i + 1:i + 12]:
        if x.get('period') != ev[i].get('period') or ts(x) - t0 > window:
            return None
        typ = x['type']['name']
        if typ in ('Ball Receipt*', 'Pressure', 'Foul Won', 'Foul Committed'):
            continue
        if x.get('team', {}).get('name') == A:
            return None
        return x
    return None


def cross_outcome(ev, i, A, byid):
    """blk: first defensive touch within 10 yards of the crosser; clr: a defender dealt with it further away;
    gk: the keeper claimed or punched it; ok: a team-mate got it; bad: out of play, offside or nobody touched it."""
    e = ev[i]
    p = e['pass']
    oc = p.get('outcome', {}).get('name')
    if oc is None:
        return 'ok'
    if oc in ('Out', 'Pass Offside', 'Unknown', 'Injury Clearance'):
        return 'bad'
    d = None
    for r in e.get('related_events', []):
        x = byid.get(r)
        if x is not None and x.get('team', {}).get('name') != A and x['type']['name'] in ('Block', 'Clearance', 'Interception', 'Goal Keeper'):
            d = x
            break
    if d is None:
        d = next_def(ev, i, A)
    if d is None:
        return 'bad'
    t = d['type']['name']
    if t == 'Ball Recovery':
        return 'bad'
    if t == 'Goal Keeper':
        return 'gk'
    if d.get('location') and e.get('location'):
        dx, dy = 120 - d['location'][0], 80 - d['location'][1]
        if math.hypot(dx - e['location'][0], dy - e['location'][1]) <= 10:
            return 'blk'
    if t in ('Block', 'Clearance', 'Interception', 'Pass', 'Duel', 'Carry', 'Shot', 'Dribble', 'Miscontrol', 'Ball Receipt*'):
        return 'clr'
    return 'bad'


def pen_outcome(ev, i, A, byid):
    e = ev[i]
    typ = e['type']['name']
    if typ == 'Carry':
        return 'ok'
    if typ in ('Dribble', 'Dispossessed'):
        return 'lost'
    oc = e['pass'].get('outcome', {}).get('name')
    return 'ok' if oc is None else 'lost'


def shot_outcome(ev, i, A, byid):
    e = ev[i]
    oc = e['shot']['outcome']['name']
    if oc == 'Goal':
        return 'goal'
    if oc == 'Blocked':
        return 'blk'
    if oc in OFF:
        return 'off'
    if oc in SAVED:
        g = None
        for r in e.get('related_events', []):
            x = byid.get(r)
            if x is not None and x['type']['name'] == 'Goal Keeper' and x.get('team', {}).get('name') != A:
                g = x
                break
        if g is None:
            return 'parry'
        go = g.get('goalkeeper', {})
        out = go.get('outcome', {}).get('name', '')
        typ = go.get('type', {}).get('name', '')
        if typ in ('Shot Saved Off Target', 'Shot Saved to Post'):
            return 'parry'
        return 'hold' if out in ('Success', 'Collected Twice', 'Saved Twice', 'Claim') else 'parry'
    return 'off'


DEF_TOUCH = {'Clearance', 'Block', 'Interception', 'Goal Keeper', 'Ball Recovery'}


def is_control(e):
    """The event's team has the ball under control."""
    typ = e['type']['name']
    if typ in ('Pass', 'Carry', 'Shot', 'Dribble'):
        return True
    if typ == 'Ball Receipt*':
        return 'ball_receipt' not in e
    return False


def ends_other(e):
    """This event ends the other team's current arrival (they lost control or the defence got a touch)."""
    typ = e['type']['name']
    if is_control(e) or typ in DEF_TOUCH:
        return True
    if typ == 'Duel':
        return e.get('duel', {}).get('type', {}).get('name') != 'Aerial Lost'
    return False


def process(job):
    comp, kind, m = job
    mid = m['match_id']
    ev = json.load(open(os.path.join(REPO, 'data', 'events', f'{mid}.json'), encoding='utf-8'))
    home = m['home_team']['home_team_name']
    away = m['away_team']['away_team_name']
    byid = {e['id']: e for e in ev}
    teams = (home, away)
    rows = {}
    for per in (1, 2):
        for s, T in enumerate(teams):
            rows[(per, s)] = {'match_id': mid, 'comp': comp, 'kind': kind, 'period': per, 'side': s, 'team': T,
                              'opp': teams[1 - s], 'mins': 0.0, 'arr': 0, 'arrB': 0, 'arr80': 0, 'tilt_touch': 0,
                              'cross': 0, 'cross_blk': 0, 'cross_clr': 0, 'cross_gk': 0, 'cross_ok': 0, 'cross_bad': 0,
                              'cross_press': 0, 'pen': 0, 'pen_ok': 0, 'pen_lost': 0,
                              'lshot': 0, 'lshot_blk': 0, 'lshot_hold': 0, 'lshot_parry': 0, 'lshot_off': 0, 'lshot_goal': 0,
                              'bshot': 0, 'bshot_blk': 0, 'bshot_hold': 0, 'bshot_parry': 0, 'bshot_off': 0, 'bshot_goal': 0,
                              'corners': 0, 'goals': 0, 'score_for_start': 0, 'score_against_start': 0}
    acts, corners = [], []
    score = [0, 0]
    onball = []
    stB = {0: False, 1: False}     # control-based arrival in progress, per side
    spb = {0: False, 1: False}     # just took a corner / free kick: wait for a defensive touch
    seenA, seen80 = set(), set()   # possessions already counted as arrivals
    cur_per = None
    ck_src = {}
    act_oc = {}
    for i, e in enumerate(ev):
        per = e.get('period')
        if per not in (1, 2):
            continue
        if per != cur_per:
            cur_per = per
            onball = []
            stB = {0: False, 1: False}
            spb = {0: False, 1: False}
            for s in (0, 1):
                rows[(per, s)]['score_for_start'] = score[s]
                rows[(per, s)]['score_against_start'] = score[1 - s]
        t = ts(e)
        for s in (0, 1):
            rows[(per, s)]['mins'] = max(rows[(per, s)]['mins'], t / 60.0)
        typ = e['type']['name']
        team = e.get('team', {}).get('name')
        if team not in teams:
            continue
        s = teams.index(team)
        R = rows[(per, s)]
        loc = e.get('location')
        pt = ptype(e)
        # ---------- arrivals ----------
        if ends_other(e):
            stB[1 - s] = False
            spb[1 - s] = False
        if pt in SET_PIECE:
            stB = {0: False, 1: False}
            spb = {0: False, 1: False}
            if pt in ('Corner', 'Free Kick'):
                spb[s] = True      # the delivery itself and its first contact are not an arrival
        elif is_control(e) and loc is not None:
            if loc[0] >= F3:
                R['tilt_touch'] += 1
            pts = [loc[0]]
            if typ == 'Pass' and 'outcome' not in e['pass'] and e['pass'].get('end_location'):
                pts.append(e['pass']['end_location'][0])
            if typ == 'Carry' and e['carry'].get('end_location'):
                pts.append(e['carry']['end_location'][0])
            pkey = (per, e.get('possession'))
            own = e.get('possession_team', {}).get('name') == team
            for x in pts:
                if x < F3:
                    stB[s] = False
                    spb[s] = False
                if spb[s]:
                    continue
                if x >= NEAR:
                    if not stB[s]:
                        stB[s] = True
                        R['arrB'] += 1
                    if own and pkey not in seenA:
                        seenA.add(pkey)
                        R['arr'] += 1
                if x >= F3 and own and pkey not in seen80:
                    seen80.add(pkey)
                    R['arr80'] += 1
        # ---------- goals ----------
        if typ == 'Shot' and e['shot']['outcome']['name'] == 'Goal':
            score[s] += 1
            R['goals'] += 1
        if typ == 'Own Goal For':
            score[s] += 1
            R['goals'] += 1
        # ---------- actions ----------
        act = None
        if typ == 'Pass' and is_cross(e, ev, i):
            act, oc = 'cross', cross_outcome(ev, i, team, byid)
            R['cross'] += 1
            R['cross_' + oc] += 1
            if e.get('under_pressure'):
                R['cross_press'] += 1
        elif is_pen(e, ev, i):
            act, oc = 'pen', pen_outcome(ev, i, team, byid)
            R['pen'] += 1
            R['pen_' + oc] += 1
        elif typ == 'Shot' and e['shot'].get('type', {}).get('name') == 'Open Play':
            act = 'bshot' if in_box(loc) else 'lshot'
            oc = shot_outcome(ev, i, team, byid)
            R[act] += 1
            R[act + '_' + oc] += 1
        if act:
            act_oc[e['id']] = act + '_' + oc
            acts.append({'match_id': mid, 'comp': comp, 'kind': kind, 'period': per, 'side': s, 'id': e['id'],
                         'act': act, 'oc': oc, 'x': round(loc[0], 1) if loc else '', 'y': round(loc[1], 1) if loc else '',
                         'press': 1 if e.get('under_pressure') else 0,
                         'height': e['pass'].get('height', {}).get('name', '') if typ == 'Pass' else '',
                         'minute': e['minute'], 'diff': score[s] - score[1 - s] - (1 if oc == 'goal' else 0), 'ck': 0})
        # ---------- corners ----------
        if pt == 'Corner':
            R['corners'] += 1
            chain = [x for x in onball[-10:]][::-1]
            a, b = last_attack(chain, team)
            cat = corner_cat(a, b)
            if a is not None:
                ck_src[a['id']] = 1
                if a['id'] in act_oc:
                    cat = act_oc[a['id']]
            corners.append({'match_id': mid, 'comp': comp, 'kind': kind, 'period': per, 'side': s, 'minute': e['minute'],
                            'cat': cat, 'att_type': a['type']['name'] if a is not None else '',
                            'def_type': b['type']['name'] if b is not None else '',
                            'att_x': round(a['location'][0], 1) if a is not None and a.get('location') else '',
                            'att_y': round(a['location'][1], 1) if a is not None and a.get('location') else '',
                            'diff': score[s] - score[1 - s]})
        if typ not in SKIP:
            onball.append(e)
    for a in acts:
        if a['id'] in ck_src:
            a['ck'] = 1
    return list(rows.values()), acts, corners


if __name__ == "__main__":
    REPO, OUT, NP = sys.argv[1], sys.argv[2], int(sys.argv[3])
    jobs = []
    for (cid, sid), (comp, kind) in COMPS.items():
        for m in json.load(open(os.path.join(REPO, 'data', 'matches', str(cid), f'{sid}.json'), encoding='utf-8')):
            if os.path.exists(os.path.join(REPO, 'data', 'events', f"{m['match_id']}.json")):
                jobs.append((comp, kind, m))
    os.makedirs(OUT, exist_ok=True)
    names = ('halves', 'acts', 'corners')
    files = {k: open(os.path.join(OUT, k + '.csv'), 'w', newline='', encoding='utf-8') for k in names}
    writers = {}
    done = 0
    with Pool(NP) as pool:
        for res in pool.imap_unordered(process, jobs, chunksize=4):
            for k, rows in zip(names, res):
                if not rows:
                    continue
                if k not in writers:
                    writers[k] = csv.DictWriter(files[k], fieldnames=list(rows[0].keys()))
                    writers[k].writeheader()
                writers[k].writerows(rows)
            done += 1
            if done % 200 == 0:
                print('done', done, flush=True)
    for f in files.values():
        f.close()
    print('matches', done)
