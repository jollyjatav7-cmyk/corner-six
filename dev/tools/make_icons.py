"""Draw the app icons: six level tiles on the pitch green with a yellow corner flag.
Usage: python3 -I make_icons.py <out_dir>
"""
import sys
from PIL import Image, ImageDraw

OUT = sys.argv[1]
GRASS, CHALK, FLAG = (36, 87, 61), (243, 245, 238), (242, 194, 48)
TILES = [(228, 236, 230), (198, 220, 205), (147, 191, 162), (78, 145, 104), (243, 245, 238), (147, 191, 162)]


def icon(size):
    S = 4 * size
    im = Image.new('RGB', (S, S), GRASS)
    d = ImageDraw.Draw(im)
    # six tiles (2 rows x 3), heights rising like levels
    pad, gap = int(S * 0.17), int(S * 0.045)
    tw = (S - 2 * pad - 2 * gap) // 3
    levels = [2, 3, 5, 1, 4, 3]
    for k, lv in enumerate(levels):
        col, row = k % 3, k // 3
        x0 = pad + col * (tw + gap)
        y1 = int(S * (0.52 if row == 0 else 0.86))
        h = int(S * 0.07 * lv)
        r = int(S * 0.025)
        d.rounded_rectangle([x0, y1 - h, x0 + tw, y1], radius=r, fill=TILES[lv])
    # corner flag top-left
    w = max(4, S // 45)
    fx, fy = int(S * 0.17), int(S * 0.08)
    d.line([(fx, fy), (fx, int(S * 0.3))], fill=CHALK, width=w)
    fw, fh = int(S * 0.2), int(S * 0.12)
    d.polygon([(fx + w // 2, fy), (fx + w // 2 + fw, fy), (fx + w // 2 + int(fw * 0.7), fy + fh // 2), (fx + w // 2 + fw, fy + fh), (fx + w // 2, fy + fh)], fill=FLAG)
    return im.resize((size, size), Image.LANCZOS)


for n in (180, 192, 512):
    icon(n).save(f'{OUT}/icon-{n}.png', optimize=True)
print('ok')
