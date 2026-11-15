"""Link-preview pictures of each tune's music (og:image), for build_site.py --previews.

When a tune's page is shared (WhatsApp, Facebook, Slack, Bluesky...), the app that shows
the link fetches the page's og:image to show with it: here, a 1200x630 picture of the
tune's name and the opening of its music, drawn by abcjs in a headless browser (Playwright,
as the tests use). Only those apps ever fetch it: a visitor's browser never does, and
sw.js doesn't keep the pictures for offline use (they're under alaw/, which it skips).

Drawing them all takes a few minutes, so each picture is kept in .previews/ under a hash
of everything drawn in it (the music, the name, the type, the look below and abcjs
itself): a build only draws the tunes that are new or have changed (CI keeps the folder
between builds, in pages.yml). The hash is in the picture's address too, so an app that
remembers an old picture fetches the new one when the tune changes.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).parent
CACHE = ROOT / ".previews"
ABCJS = ROOT / "static" / "abcjs" / "abcjs-basic-min.js"
WIDTH, HEIGHT = 1200, 630

# The picture: a strip of carthen, the tune's name and type, and its opening on cream paper
# (DESIGN.md's colours). Change anything in this file and every picture is drawn again.
PAGE = """<!doctype html><meta charset="utf-8"><style>
  * { box-sizing: border-box; margin: 0; }
  body { width: %(w)dpx; height: %(h)dpx; overflow: hidden; background: #fbf6ea; color: #262b31;
         font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; }
  #card { width: %(w)dpx; height: %(h)dpx; display: flex; flex-direction: column; background: #fbf6ea; }
  .band { height: 28px; flex: none; background: url("data:image/svg+xml;base64,%(carthen)s") repeat-x left center / auto 28px; }
  header { padding: 30px 48px 0; display: flex; align-items: baseline; gap: 24px; }
  h1 { font-size: 60px; line-height: 1.1; font-weight: 700; flex: 1; min-width: 0;
       white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .type { font-size: 30px; font-weight: 600; white-space: nowrap; display: flex; align-items: center; gap: 12px; }
  .type i { width: 22px; height: 22px; border-radius: 50%%; display: inline-block; }
  #score { flex: 1; margin: 22px 48px 12px; overflow: hidden; }
  footer { padding: 0 48px 22px; display: flex; justify-content: space-between; font-size: 26px; color: #5f6973; }
  footer b { color: #3b4550; }
</style><div id="card"><div class="band"></div>
<header><h1 id="name"></h1><span class="type"><i id="dot"></i><span id="type"></span></span></header>
<div id="score"><div id="paper"></div></div><footer><b>Y Sesiwn</b><span>ysesiwn.cymru</span></footer></div>"""

# Drawn as the app's scores are (app.js: SCORE_FORMAT), without chords, at up to twice the
# size, so the notes still read in a phone's small preview.
DRAW = r"""([abc, name, type, colour]) => {
  document.getElementById("name").textContent = name;
  document.getElementById("type").textContent = type;
  document.getElementById("dot").style.background = colour;
  const box = document.getElementById("score"), paper = document.getElementById("paper");
  const face = '"system-ui, -apple-system, Segoe UI, Roboto, sans-serif"';
  const format = Object.fromEntries([["annotation", "12"], ["vocal", "13"], ["words", "16"],
    ["repeat", "13"], ["measure", "14 italic"], ["triplet", "11 italic"]].map(([n, s]) => [`${n}font`, `${face} ${s}`]));
  // The tune's own lines (each with its words under it).
  const [head, ...body] = abc.split("\n---\n");
  const lines = [];
  for (const line of body.join("\n").split("\n")) {
    if (lines.length && (/^[wW%]|^[A-Za-z]:/.test(line) || !line.trim())) lines[lines.length - 1] += "\n" + line;
    else lines.push(line);
  }
  const width = box.clientWidth, room = box.clientHeight;
  const draw = (scale, n) => {
    paper.innerHTML = "";
    ABCJS.renderAbc(paper, [head, "%%stretchlast 1", ...lines.slice(0, n)].join("\n"), { responsive: "resize",
      staffwidth: width / scale - 4, paddingtop: 0, paddingbottom: 0, paddingleft: 0, paddingright: 0, format });
    const svg = paper.querySelector("svg");
    const drawn = svg.getBBox(), view = svg.viewBox.baseVal;
    return svg.getBoundingClientRect().height <= room && drawn.x + drawn.width <= view.width + 1;
  };
  // As big as it goes with at least two lines (or the one, for a one-line tune), up to three.
  // Notes crowded on a long line are drawn smaller, rather than run off the edge.
  for (const least of [Math.min(2, lines.length), 1])
    for (const scale of [1.9, 1.65, 1.45, 1.25, 1.1])
      for (let n = Math.min(3, lines.length); n >= least; n--)
        if (draw(scale, n)) return;
  draw(1.1, 1);
}"""


def opening(abc: str) -> str:
    """The tune as drawn in the picture, its header and music split by ---: no title or other
    headers (the picture has its own name), no chords and no verses after the music (W:)."""
    lines = abc.splitlines()
    k = next(i for i, line in enumerate(lines) if line.startswith("K:"))
    head = [line for line in lines[:k + 1] if re.match(r"[XMLK]:", line)]
    # A chord is "G"; an annotation ("^text", "_text", ...) stays.
    body = [line if re.match(r"[A-Za-z]:", line) else re.sub(r'"[^"]*"', lambda m: m[0] if m[0][1:2] in "^_<>@" else "", line)
            for line in lines[k + 1:] if not line.startswith("W:")]
    return "\n".join(head) + "\n---\n" + "\n".join(body).strip()


def key_label(key: dict | None) -> str:
    """D, Em, E Dorian: short, and the same in Welsh and English (the picture is both pages')."""
    if not key:
        return ""
    return key["root"] + {"major": "", "minor": "m"}.get(key["modeName"], " " + key["modeName"])


def preview_hash(item: dict) -> str:
    h = hashlib.sha256()
    # This file (how the picture is drawn), abcjs, and the tune.
    for part in (Path(__file__).read_bytes(), ABCJS.read_bytes(), json.dumps(item, sort_keys=True, ensure_ascii=False).encode()):
        h.update(part)
    return h.hexdigest()[:12]


def draw_previews(items: dict[str, dict]) -> dict[str, Path]:
    """items: {group: {name, type, colour, key, abc}} -> {group: its picture in .previews/},
    drawing only the ones not already there."""
    CACHE.mkdir(exist_ok=True)
    wanted = {group: CACHE / f"{preview_hash(item)}.png" for group, item in items.items()}
    missing = [group for group, path in wanted.items() if not path.exists()]
    if missing:
        import base64
        from playwright.sync_api import sync_playwright

        carthen = base64.b64encode((ROOT / "site" / "carthen.svg").read_bytes()).decode()
        print(f"drawing {len(missing)} link-preview picture(s)…")
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": WIDTH, "height": HEIGHT})
            page.set_content(PAGE % {"w": WIDTH, "h": HEIGHT, "carthen": carthen})
            page.add_script_tag(path=str(ABCJS))
            for group in missing:
                item = items[group]
                # The type as the site names it (Welsh, in both languages); "Other" isn't one.
                label = " · ".join(x for x in (item["type"] if item["type"] != "Other" else "",
                                                key_label(item["key"])) if x)
                page.evaluate(DRAW, [opening(item["abc"]), item["name"], label, item["colour"]])
                tmp = wanted[group].with_suffix(".tmp.png")
                page.locator("#card").screenshot(path=str(tmp))
                tmp.replace(wanted[group])  # never a half-written picture in the cache
            browser.close()
    # Pictures no tune uses any more (old versions of changed tunes) aren't kept.
    keep = set(wanted.values())
    for old in CACHE.glob("*.png"):
        if old not in keep:
            old.unlink()
    return wanted
