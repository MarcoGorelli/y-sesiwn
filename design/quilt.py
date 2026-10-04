# Draws static/quilt.svg, the scrap of Welsh quilt the instruments stand on, on the
# home page and in the link-preview card (design/og-card.html):
# python3 design/quilt.py static/quilt.svg
#
# A wholecloth quilt quilted in the Welsh frame layout: a field framed by double stitched
# lines, a border filled with spirals, and fans in the corners of the field (all typical
# of Welsh quilting; see the Quilters' Guild's notes on Welsh wholecloths and frame quilts).
import math
import sys

W, H = 300, 170
slate, cream = "#3b4550", "#f3ead3"

def spiral(cx, cy, r, flip=1, turns=1.6, n=20):
    pts = []
    for k in range(n + 1):
        t = k / n
        a, rr = flip * t * turns * 2 * math.pi, r * (1 - t * 0.85)
        pts.append(f"{cx + rr * math.cos(a):.1f} {cy + rr * math.sin(a):.1f}")
    return "M" + " L".join(pts)

# Spirals along the border, between the outer and inner pairs of stitched lines.
spirals, step, mid = [], 18, 17
for x in range(mid + step, W - mid - step // 2, step):
    spirals += [spiral(x, mid, 4.6), spiral(x, H - mid, 4.6, -1)]
for y in range(mid + step, H - mid - step // 2, step):
    spirals += [spiral(mid, y, 4.6), spiral(W - mid, y, 4.6, -1)]
for cx, cy in [(mid, mid), (W - mid, mid), (mid, H - mid), (W - mid, H - mid)]:
    spirals.append(f"M{cx - 4} {cy} A4 4 0 1 0 {cx + 4} {cy} A4 4 0 1 0 {cx - 4} {cy}")

# A fan in each corner of the field: three arcs and three ribs.
fans = []
for cx, cy, sx, sy in [(27, 27, 1, 1), (W - 27, 27, -1, 1), (27, H - 27, 1, -1), (W - 27, H - 27, -1, -1)]:
    d = [f"M{cx + sx * r} {cy} A{r} {r} 0 0 {int(sx * sy > 0)} {cx} {cy + sy * r}" for r in (8, 14, 20)]
    d += [f"M{cx} {cy} L{cx + sx * 20 * math.cos(k * math.pi / 8):.1f} {cy + sy * 20 * math.sin(k * math.pi / 8):.1f}" for k in (1, 2, 3)]
    fans.append(" ".join(d))

frames = "\n".join(f'    <rect x="{i}" y="{i}" width="{W - 2 * i}" height="{H - 2 * i}" rx="2"/>' for i in (7, 10, 24, 27))
svg = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}">
  <!-- A scrap of Welsh wholecloth quilt, for the instruments. Made by design/quilt.py. -->
  <rect x="1" y="1" width="{W - 2}" height="{H - 2}" rx="4" fill="{cream}" stroke="{slate}" stroke-opacity=".6" stroke-width="1.2"/>
  <g stroke="{slate}" stroke-opacity=".55" stroke-width=".9" stroke-dasharray="2.4 1.8" fill="none" stroke-linecap="round">
{frames}
    <path d="{" ".join(spirals)}"/>
    <path d="{" ".join(fans)}"/>
  </g>
</svg>
'''
open(sys.argv[1], "w").write(svg)
