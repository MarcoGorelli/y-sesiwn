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


def test_chords_source():
    read = lambda slug: (b.ROOT / "tunes" / slug / "tune.abc").read_text(encoding="utf-8")
    assert b.chords_source(read("glandyfi")) == "From the Alawon Cymru score"
    assert b.chords_source(read("dawns-y-glocsen")) is None  # "^Fine" and "^D.C." are text, not chords
    assert b.chords_source(read("nyth-y-gog")) is None


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
    assert len(sounds) == 88
    for f in files[1:] + sounds:
        assert (out / f).is_file(), f"sw.js would cache a missing file: {f}"
