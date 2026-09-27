# Draws static/harp.svg, the site's icon: python3 design/triple-harp.py static/harp.svg
# (then regenerate the PNG icons from the other design/ pages; see the README).
# Welsh triple harp, side view: soundbox on the left leaning back, straight fore-pillar
# on the right rising to a scrolled head, neck sweeping up from the soundbox to the head.
import sys

def bez(p0, p1, p2, p3, t):
    return tuple((1-t)**3*a + 3*(1-t)**2*t*b + 3*(1-t)*t**2*c + t**3*d for a, b, c, d in zip(p0, p1, p2, p3))

# neck: two cubic segments
N1 = [(16.5, 12.5), (24, 16), (32, 17), (38.5, 12)]
N2 = [(38.5, 12), (42, 9), (44.5, 6.5), (47.5, 6.5)]
neck_pts = [bez(*N1, t/200) for t in range(201)] + [bez(*N2, t/200) for t in range(201)]
def neck_y(x):  # underside is ~ the centre line; strings start a bit below
    return min(neck_pts, key=lambda p: abs(p[0]-x))[1]

# soundboard (string side of the soundbox): straight line
SB = ((19.5, 14), (43, 56.5))
def board_y(x):
    (x0, y0), (x1, y1) = SB
    return y0 + (x - x0) * (y1 - y0) / (x1 - x0)

strings = []
xs = [22.5 + i * 2.35 for i in range(11)]
for i, x in enumerate(xs):
    top, bottom = neck_y(x) + 2.2, board_y(x) - 1.2
    if bottom - top > 2:
        strings.append(f'<line x1="{x:.1f}" y1="{top:.1f}" x2="{x:.1f}" y2="{bottom:.1f}"/>')

wood, dark, gold = "#7a3e12", "#5c2d0c", "#c9a227"
svg = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="2.5 0 64 64">
  <!-- A Welsh triple harp (telyn deires): tall soundbox, straight fore-pillar with a
       scrolled head, and a neck that sweeps up to it. Made by design/triple-harp.py. -->
  <g stroke="{gold}" stroke-width="0.9" stroke-linecap="round">
    {chr(10).join("    " + s for s in strings).strip()}
  </g>
  <g fill="none" stroke="{wood}" stroke-linecap="round" stroke-linejoin="round">
    <!-- fore-pillar, with the head's scroll curling forward at the top -->
    <path d="M47.5 59 L48 7.5 C 48 4, 51.8 3, 52.6 5.4 C 53.2 7.3, 51.2 8.4, 50.2 7" stroke-width="3"/>
    <!-- neck -->
    <path d="M{N1[0][0]} {N1[0][1]} C {N1[1][0]} {N1[1][1]}, {N1[2][0]} {N1[2][1]}, {N1[3][0]} {N1[3][1]} C {N2[1][0]} {N2[1][1]}, {N2[2][0]} {N2[2][1]}, {N2[3][0]} {N2[3][1]}" stroke-width="3.2"/>
  </g>
  <!-- soundbox: narrow at the top, wide at the foot -->
  <path d="M16 11.5 L20.5 13 L43.5 56.5 L42.5 59.5 L37 59.5 Z" fill="{wood}" stroke="{wood}" stroke-width="1.5" stroke-linejoin="round"/>
  <!-- feet -->
  <path d="M35 60.5 H50" stroke="{dark}" stroke-width="2.4" stroke-linecap="round"/>
</svg>
'''
open(sys.argv[1], "w").write(svg)
