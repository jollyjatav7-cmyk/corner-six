"""Assemble the app from dev/src + dev/data into one index.html (plus sw.js, manifest, README).

Usage (from the repo root):  python3 -I dev/build.py [out_dir]
out_dir defaults to the repo root, which is what GitHub Pages serves.
"""
import json
import os
import re
import shutil
import sys

DEV = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(DEV, 'src')
DATA = os.path.join(DEV, 'data')
OUT = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else os.path.dirname(DEV)


def read(*p):
    return open(os.path.join(*p), encoding='utf-8').read()


base = json.loads(read(DATA, 'baseline.json'))
html = read(SRC, 'app.html')
for key in ('__BASE__', '__APPVER__'):
    assert html.count(key) == 1, f'{key} must appear exactly once in app.html'
ver = re.search(r"corner-six-(v\d+)", read(SRC, 'sw.js')).group(1)   # 版本号跟着 sw.js 的快取名称
html = html.replace('__APPVER__', ver).replace('__BASE__', json.dumps(base, ensure_ascii=False, separators=(',', ':')))
os.makedirs(OUT, exist_ok=True)
open(os.path.join(OUT, 'index.html'), 'w', encoding='utf-8').write(html)
for f in ('sw.js', 'manifest.webmanifest', 'README.md'):
    shutil.copy(os.path.join(SRC, f), os.path.join(OUT, f))
print('built', len(html), 'bytes, version', ver, '->', OUT)
