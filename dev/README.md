# 角球六要素 — source code

The live app is the single file `index.html` in the repo root (served by GitHub Pages). It is **built** from this folder.

| Path | What it is |
| --- | --- |
| `src/app.html` | The whole app (layout, styles, logic). `__BASE__` is filled with `data/baseline.json`, `__APPVER__` with the cache version from `src/sw.js`. |
| `src/sw.js` | Service worker. **Bump `CACHE = 'corner-six-vN'` on every release**, or phones keep the old version. It only handles requests under its own path (other apps share the github.io origin). |
| `data/baseline.json` | What the app compares against: per-half and per-match means and quintiles of the six metrics, corner chance per outcome, corner origins, the forward model. |
| `data/report.json`, `data/more.json`, `data/predict.json` | Full analysis output (origins, explanatory power, the user's two cases, regressions, forward test). |
| `model/` | Python pipeline over StatsBomb open data. |
| `tests/` | Playwright UI tests. |
| `tools/make_icons.py` | Home-screen icons. |

localStorage keys all start with `corner-six-` (the corner-sb app uses `corner-sb-`).

## Build and release

```bash
python3 -I dev/build.py          # writes index.html, sw.js, manifest, README to the repo root
```
Bump the cache name in `dev/src/sw.js`, rebuild, commit, push to `main`.

## Tests

```bash
cd <repo root> && python3 -m http.server 8777 &
cd dev/tests && mkdir -p out
node uitest.js http://localhost:8777 out      # recording flow on iPad and phones, levels, warehouse, export/import
node fitphone.js http://localhost:8777 out    # phone layouts fit, with and without the video-window band
```

## Data pipeline (StatsBomb open data)

```bash
git clone --filter=blob:none https://github.com/statsbomb/open-data sb    # or a sparse checkout of the events needed
python3 -I dev/model/six_extract.py sb work 2          # halves.csv (per team-half counts), acts.csv, corners.csv
python3 -I dev/model/six_baseline.py work res          # baseline.json, report.json
python3 -I dev/model/six_more.py work res              # Poisson regression of corners on the six metrics
python3 -I dev/model/six_predict.py work res           # same-half model and first-half -> second-half forward test
```
Then merge `predict.json`'s `forward_model` into `baseline.json` as `fwd` (see git history for the exact snippet) and rebuild.

Definitions (StatsBomb 120x80 pitch): arrival = a possession that gets the ball under control within 30 yards of the goal line
(corner and free-kick deliveries excluded); byline cross = from x >= 102 (beside the box), deep cross = from outside the box line;
blocked = first defensive touch within 10 yards of the crosser; held vs parried save from the keeper event's outcome.
An action "led to a corner" when it is the attacking team's last on-ball action before the corner kick with no controlled
possession by the defenders in between.
