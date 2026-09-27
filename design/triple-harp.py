# Draws static/harp.svg, the site's icon: python3 design/triple-harp.py static/harp.svg
# (then regenerate the PNG icons from the other design/ pages; see the README).
#
# A Welsh triple harp (telyn deires), after the photo on Wikipedia's "Triple harp" page:
# a tall straight pillar with a scroll on top, a "high head" (the neck climbs in a long
# curve from the short soundbox to the top of the pillar), a soundbox that widens down
# to the foot of the pillar, a plinth, and red strings among the plain ones.
import sys

def bez(p0, p1, p2, p3, t):
    return tuple((1-t)**3*a + 3*(1-t)**2*t*b + 3*(1-t)*t**2*c + t**3*d for a, b, c, d in zip(p0, p1, p2, p3))

# The neck's centre line, from the top of the soundbox (left) to the pillar (right).
NECK = [(21.5, 25), (29, 29.5), (37, 23), (43.5, 7.5)]
neck = [bez(*NECK, t / 400) for t in range(401)]
def neck_y(x):
    return min(neck, key=lambda p: abs(p[0] - x))[1]

# The soundboard: the front of the soundbox, where the strings end.
BOARD = ((24.5, 26.5), (42.5, 56.5))
def board_y(x):
    (x0, y0), (x1, y1) = BOARD
    return y0 + (x - x0) * (y1 - y0) / (x1 - x0)

wood, dark, gold, red = "#7a3e12", "#5c2d0c", "#c9a227", "#c8102e"
strings = []
for i in range(9):
    x = 26.3 + i * 1.85
    top, bottom = neck_y(x) + 1.9, board_y(x) - 0.8
    colour = red if i % 3 == 1 else gold
    strings.append(f'<line x1="{x:.2f}" y1="{top:.2f}" x2="{x:.2f}" y2="{bottom:.2f}" stroke="{colour}"/>')

svg = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="1.5 0 64 64">
  <!-- A Welsh triple harp (telyn deires). Made by design/triple-harp.py. -->
  <g stroke-width="0.8" stroke-linecap="round">
    {(chr(10) + "    ").join(strings)}
  </g>
  <g fill="none" stroke="{wood}" stroke-linecap="round" stroke-linejoin="round">
    <!-- neck, climbing to the top of the pillar -->
    <path d="M{NECK[0][0]} {NECK[0][1]} C {NECK[1][0]} {NECK[1][1]}, {NECK[2][0]} {NECK[2][1]}, {NECK[3][0]} {NECK[3][1]}" stroke-width="3"/>
    <!-- pillar, with a scroll on top curling back over the strings -->
    <path d="M45 58 V7 C 45 3.2, 40.6 2.6, 40.2 5.2 C 39.9 7, 42 7.8, 42.8 6.3" stroke-width="3.2"/>
  </g>
  <!-- finial where the neck meets the soundbox -->
  <circle cx="21" cy="23.6" r="1.9" fill="{wood}"/>
  <!-- soundbox: short, widening to the foot -->
  <path d="M20 25 L25 26 L43 56 L43 58 L29 58 Z" fill="{wood}" stroke="{wood}" stroke-width="1.2" stroke-linejoin="round"/>
  <!-- plinth -->
  <rect x="27" y="58" width="21.5" height="3" rx="0.8" fill="{dark}"/>
</svg>
'''
open(sys.argv[1], "w").write(svg)
