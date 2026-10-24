# Draws the carthen band in each season's colourway (site/carthen-<season>.svg), worn
# across the top and bottom of every page in its season (app.js: SEASONS):
# python3 design/carthen-seasons.py site
# The weave is site/carthen.svg's; only the colours change.
import sys
from pathlib import Path

# season -> (edges and outlines, inner diamond, second diamond, small squares), on cream
SEASONS = {
    "calan-gaeaf": ("#1d1d1b", "#d4581c", "#1d1d1b", "#d4581c"),  # night and bonfire
    "nadolig": ("#2e5e3a", "#C8102E", "#2e5e3a", "#c28f1c"),      # holly, berries and candlelight
    "mari-lwyd": ("#3b4550", "#C8102E", "#2f4f8f", "#2e6b4f"),    # her ribbons
    "calennig": ("#3b4550", "#C8102E", "#2e5e3a", "#c28f1c"),     # apple, evergreen and oats
    "dwynwen": ("#7a1f2b", "#d94f6e", "#7a1f2b", "#d94f6e"),      # roses
    "gwyl-dewi": ("#2e6b4f", "#e9a800", "#2e6b4f", "#e9a800"),    # leek and daffodil
    "calan-mai": ("#4c7a2a", "#d94f6e", "#4c7a2a", "#e9a800"),    # birch, ribbons and gorse
}

for name, (edge, inner, second, square) in SEASONS.items():
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="48" height="14" viewBox="0 0 48 14">
  <!-- The carthen band in the colours of {name} (design/carthen-seasons.py). -->
  <rect width="48" height="14" fill="#f3ead3"/>
  <rect width="48" height="2" fill="{edge}"/>
  <rect y="12" width="48" height="2" fill="{edge}"/>
  <polygon points="12,2.5 17,7 12,11.5 7,7" fill="none" stroke="{edge}" stroke-width="1"/>
  <polygon points="12,4.5 14.5,7 12,9.5 9.5,7" fill="{inner}"/>
  <polygon points="36,4.5 38.5,7 36,9.5 33.5,7" fill="{second}"/>
  <rect x="23" y="6" width="2" height="2" fill="{square}"/>
  <rect x="47" y="6" width="1" height="2" fill="{square}"/>
  <rect x="0" y="6" width="1" height="2" fill="{square}"/>
</svg>
'''
    (Path(sys.argv[1]) / f"carthen-{name}.svg").write_text(svg)
