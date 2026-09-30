"""Quick checks of the tune files and build_site.py (no browser)."""
import json
import re
from pathlib import Path

import pytest

import build_site as b

TUNES = sorted(b.ROOT.glob("tunes/*/tune.abc"))


@pytest.mark.parametrize("path", TUNES, ids=lambda p: p.parent.name)
def test_tune_file(path: Path):
    abc = path.read_text(encoding="utf-8")
    headers = b.parse_headers(abc)
    for field in "XTMLK":
        assert headers.get(field), f"no {field}: line"
    assert b.slugify(headers["T"][0]) == path.parent.name, "folder should be named after the first title"
    assert b.parse_key(headers["K"][0]), "K: should be a key the site understands"
    assert len(b.melody(abc)) >= 8, "the note search needs the melody"
    body = b.music(abc)
    assert "\n\n" not in abc.split("\nK:", 1)[1].strip(), "a blank line ends an ABC tune"
    for text in re.findall(r'"([^"]*)"', body):  # chord symbols, or text starting with ^ _ < > @
        assert re.match(r"[\^_<>@]|[A-G]", text), f'"{text}": text above the stave is written "^{text}"'


def test_titles_and_versions():
    records = [b.tune_record(p) for p in TUNES]
    by_group = {}
    for r in records:
        by_group.setdefault(r["group"], []).append(r["version"])
    for group, versions in by_group.items():
        assert sorted(versions) == list(range(1, len(versions) + 1)), f"{group}: versions {versions}"


@pytest.mark.parametrize("slug, lead", [
    ("glandyfi", 1),               # D | G2 G ...
    ("machynlleth", 2),            # Bc | de dc ...
    ("pibddawns-caerfyrddin", 3),  # (3ABc | ...
    ("ty-a-gardd", 0),             # no lead-in
    ("hel-y-sgwarnog", 0),
])
def test_lead_in(slug, lead):
    assert b.lead_index((b.ROOT / "tunes" / slug / "tune.abc").read_text(encoding="utf-8")) == lead


# Lead-ins restored from the score (they had been folded into bar 1, shifting every bar
# line): how many notes the lead-in has.
@pytest.mark.parametrize("slug, notes", [
    ("clawdd-offa", 1), ("fflat-huw-puw", 1), ("marwnad-yr-ehedydd", 2),
    ("triban-morgannwg-syml", 1), ("y-pren-ar-y-bryn", 2), ("wele-gwawriodd", 2),
])
def test_restored_lead_ins(slug, notes):
    assert b.lead_in((b.ROOT / "tunes" / slug / "tune.abc").read_text(encoding="utf-8")) == notes


def test_chords_source():
    read = lambda slug: (b.ROOT / "tunes" / slug / "tune.abc").read_text(encoding="utf-8")
    assert b.chords_source(read("glandyfi")) == "From the Alawon Cymru score"
    assert b.chords_source(read("dawns-y-glocsen")) is None  # "^Fine" and "^D.C." are text, not chords
    assert b.chords_source(read("cawl-cennin")) is None


def test_types_and_tempos():
    read = lambda slug: b.parse_headers((b.ROOT / "tunes" / slug / "tune.abc").read_text(encoding="utf-8"))
    assert b.tune_type(read("glandyfi")) and b.default_bpm(read("llancesau-trefaldwyn")) == 112  # a jig


def test_places():
    groups = {b.tune_record(p)["group"] for p in TUNES}
    places = b.places(groups)  # stops with an error if a tune doesn't exist
    width, height = map(float, re.search(r'viewBox="0 0 ([\d.]+) ([\d.]+)"',
                                         (b.ROOT / "site" / "wales.svg").read_text()).groups())
    for place in places:
        # On the map (Chester and Oswestry are just over the border, still inside it).
        assert 0 <= place["x"] <= width and 0 <= place["y"] <= height, place["name"]


def test_built_site(site):
    out = b.OUT
    index = json.loads((out / "tunes.json").read_text(encoding="utf-8"))
    assert len(index["tunes"]) == len(TUNES)
    sw = (out / "sw.js").read_text(encoding="utf-8")
    for placeholder in ["__VERSION__", "__SOUNDS_VERSION__", "__SITE_FILES__", "__SOUND_FILES__"]:
        assert placeholder not in sw, f"sw.js: {placeholder} not filled in"
    files = json.loads(re.search(r"const SITE_FILES = (\[.*?\]);", sw).group(1))
    sounds = json.loads(re.search(r"const SOUND_FILES = (\[.*?\]);", sw).group(1))
    assert {"./", "index.html", "tunes.json", "app.js", "style.css", "wales.svg"} <= set(files)
    assert sum("acoustic_grand_piano" in f for f in sounds) == 88  # the piano, A0 to C8
    assert {"static/soundfont/percussion-mp3/E5.mp3", "static/soundfont/percussion-mp3/F5.mp3"} <= set(sounds)  # the click
    for f in files[1:] + sounds:
        assert (out / f).is_file(), f"sw.js would cache a missing file: {f}"
    # The tunes' own pages aren't in the offline copy (the app stands in for them).
    assert not [f for f in files if f.startswith("alaw/")]


def test_set_codes(site):
    # Every tune has its own five-character code for set links, which stays the same.
    index = json.loads((b.OUT / "tunes.json").read_text(encoding="utf-8"))
    codes = [t["id"] for t in index["tunes"]]
    assert len(set(codes)) == len(codes) and all(re.fullmatch(r"[0-9a-z]{5}", c) for c in codes)
    assert b.short_id("llancesau-trefaldwyn") == "bne0o"  # a set link made today still works later


def test_tune_pages(site):
    # A real page per tune (alaw/<folder>/), for link previews and search engines.
    out = b.OUT
    index = json.loads((out / "tunes.json").read_text(encoding="utf-8"))
    groups = {t["group"] for t in index["tunes"]}
    assert {p.name for p in (out / "alaw").iterdir()} == groups
    page = (out / "alaw" / "llancesau-trefaldwyn" / "index.html").read_text(encoding="utf-8")
    url = "https://ysesiwn.cymru/alaw/llancesau-trefaldwyn/"
    assert '<base href="../../">' in page
    assert "<title>Llancesau Trefaldwyn · Y Sesiwn</title>" in page
    assert f'<meta property="og:url" content="{url}">' in page and f'<link rel="canonical" href="{url}">' in page
    assert '<meta property="og:title" content="Llancesau Trefaldwyn · Y Sesiwn">' in page
    description = "Llancesau Trefaldwyn: a Welsh jig in D major. Sheet music, suggested chords and playback in any key, at any tempo (2 versions)."
    assert f'<meta name="description" content="{description}">' in page
    assert f'<meta property="og:description" content="{description}">' in page
    data = json.loads(re.search(r'<script type="application/ld\+json">(.*?)</script>', page).group(1))
    assert data["name"] == "Llancesau Trefaldwyn" and data["musicalKey"] == "D major"
    assert "<h1>Llancesau Trefaldwyn</h1>" in page and "K:D" in page  # readable without the app
    source = "http://alawoncymru.com/alawon/Tunes/"
    assert f'<dt>Source</dt><dd><a href="{source}' in page and "<dt>Notes</dt>" not in page
    # A title with an apostrophe, safely written into the page.
    page = (out / "alaw" / "codi-r-hwyl" / "index.html").read_text(encoding="utf-8")
    assert "<title>Codi&#x27;r Hwyl · Y Sesiwn</title>" in page and "<h1>Codi&#x27;r Hwyl</h1>" in page
    sitemap = (out / "sitemap.xml").read_text(encoding="utf-8")
    assert sitemap.count("<loc>https://ysesiwn.cymru/alaw/") == len(groups)
    assert "Sitemap: https://ysesiwn.cymru/sitemap.xml" in (out / "robots.txt").read_text(encoding="utf-8")


# Repeats checked against the score images (the recordings, which the ABC was made from,
# often play a part once that the score repeats, or play the whole tune twice).
@pytest.mark.parametrize("slug, end_repeats", [
    ("hoffedd-ap-hywel", 2), ("aly-grogan", 2), ("ar-ben-waun-tredegar", 1), ("diferiad-y-gwerwyn", 2),
    ("gweddi-eli-jenkins", 1), ("hela-r-wiwer", 2), ("taith-dadi", 1), ("hiraeth", 1),
    ("dydd-gwyl-dewi", 1), ("hela-r-geinach", 1), ("neyland-ferry", 2), ("pibddawns-dowlais-fel-ril", 2),
    ("roedd-yn-y-wlad-honno", 2), ("y-pibydd-du", 2), ("clawdd-offa", 3), ("distyll-y-don", 1),
    ("cainc-y-datgeiniad", 1), ("y-crwtyn-llwyd", 1), ("ymdeithdon-gwyr-hirwaun", 1),
])
def test_repeats_follow_the_score(slug, end_repeats):
    abc = (b.ROOT / "tunes" / slug / "tune.abc").read_text(encoding="utf-8")
    body = re.sub(r'"[^"]*"', "", abc.split("\nK:", 1)[1].split("\n", 1)[1])
    assert len(re.findall(r":\||::", body)) == end_repeats
