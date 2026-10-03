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


def test_no_empty_details():
    # A blank header line (R: with nothing after it) isn't a row of the Details box.
    read = lambda slug: b.parse_headers((b.ROOT / "tunes" / slug / "tune.abc").read_text(encoding="utf-8"))
    assert "Tune type" not in [label for label, _ in b.details(read("a-honeyed-lip"))[0]]
    for path in TUNES:
        rows, _ = b.details(b.parse_headers(path.read_text(encoding="utf-8")))
        assert all(value.strip() for _, value in rows), path.parent.name


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


def test_pronunciations():
    # Every entry is a tune, and it's a respelling (letters, hyphens, capitals for stress).
    say = json.loads((b.ROOT / "pronunciation.json").read_text(encoding="utf-8"))["say"]
    groups = {b.tune_record(p)["group"] for p in TUNES}
    assert set(say) <= groups and len(say) > 500
    assert say["llancesau-trefaldwyn"] == "hlan-KEH-sai treh-VAL-dooin"
    assert "tom-jones" not in say  # English names have none
    assert all(re.fullmatch(r"[\w ,'-]+", v) for v in say.values())


def test_set_codes(site):
    # Every tune has its own five-character code for set links, which stays the same.
    index = json.loads((b.OUT / "tunes.json").read_text(encoding="utf-8"))
    codes = [t["id"] for t in index["tunes"]]
    assert len(set(codes)) == len(codes) and all(re.fullmatch(r"[0-9a-z]{5}", c) for c in codes)
    assert b.short_id("llancesau-trefaldwyn") == "bne0o"  # a set link made today still works later


def committed_numbers(revision):
    """tune_numbers.json as it was at a git revision (None if there's no such file or git)."""
    import subprocess
    try:
        text = subprocess.run(["git", "show", f"{revision}:tune_numbers.json"], cwd=b.ROOT, capture_output=True,
                              text=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        return None
    return json.loads(text)["numbers"]


def number_problems(before, now):
    """What would break set links made with the numbers before: a tune renumbered or
    dropped, or a number given to another tune."""
    problems = {slug: (n, now.get(slug)) for slug, n in before.items() if now.get(slug) != n}
    taken = {n: slug for slug, n in before.items()}
    problems.update({slug: ("reuses", n) for slug, n in now.items() if n in taken and taken[n] != slug})
    return problems


def test_number_check():
    # The check itself: only adding tunes passes.
    before = {"a": 0, "b": 1}
    assert number_problems(before, {"a": 0, "b": 1, "c": 2}) == {}
    assert number_problems(before, {"a": 0, "b": 2})              # renumbered
    assert number_problems(before, {"a": 0})                      # a removed tune's line deleted
    assert number_problems(before, {"a": 0, "b": 1, "c": 1})      # a number reused


def test_tune_numbers():
    # Set links name tunes by number, so a number must never change or go to another
    # tune: numbers are only ever added (a removed tune keeps its line). Checked against
    # the last commit and the one before (on GitHub, a pull request against main).
    numbers = b.load_numbers()
    assert len(set(numbers.values())) == len(numbers), "two tunes share a number"
    assert all(isinstance(n, int) and n >= 0 for n in numbers.values())
    for revision in ["HEAD", "HEAD^1"]:
        before = committed_numbers(revision)
        if before is None:
            continue
        changed = number_problems(before, numbers)
        assert not changed, (f"tune_numbers.json changes numbers that set links use (was, now): {changed}. "
                             "Only add new tunes (python build_site.py --number-tunes); keep removed ones.")


def test_pull_request_template():
    # The pull request template's tick box for new tunes names the real file and command.
    template = (b.ROOT / ".github" / "pull_request_template.md").read_text(encoding="utf-8")
    assert "- [ ] New tunes: I ran `python build_site.py --number-tunes`" in template
    assert "tune_numbers.json" in template and b.NUMBERS.name == "tune_numbers.json"
    assert "--number-tunes" in (b.ROOT / "build_site.py").read_text(encoding="utf-8")


def test_set_codes_for_new_tunes():
    # A tune added without a number yet still has a code: a little longer, never clashing.
    numbers = b.load_numbers()
    assert b.set_code("llancesau-trefaldwyn", numbers) == "5A"
    assert b.set_code("a-new-tune", numbers) == "." + b.short_id("a-new-tune")
    assert b.set_code("x", {"x": 4000}) == "-12w"  # past 3,844 tunes: three characters after "-"
    index = json.loads((b.OUT / "tunes.json").read_text(encoding="utf-8")) if b.OUT.exists() else None
    if index:
        codes = [t["code"] for t in index["tunes"]]
        assert len(set(codes)) == len(codes)


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
    description = ("Llancesau Trefaldwyn: a Welsh jig in D major. Sheet music, suggested chords and playback in any key, at any tempo (2 versions). "
                   "Alaw werin o Gymru (jig yn D fwyaf): y sgôr, cordiau a chwarae mewn unrhyw gywair.")
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
    # Each tune's page links to its type's page.
    assert '<a href="math/jig/">Welsh jigs (Jig)</a>' in (out / "alaw" / "llancesau-trefaldwyn" / "index.html").read_text(encoding="utf-8")


def test_type_pages(site):
    # A page per type (math/<type>/) listing its tunes, so search engines find every tune
    # by following links; the home page links to them all.
    out = b.OUT
    index = json.loads((out / "tunes.json").read_text(encoding="utf-8"))
    assert {p.name for p in (out / "math").iterdir()} == {b.type_slug(t["name"]) for t in index["types"]}
    page = (out / "math" / "ril" / "index.html").read_text(encoding="utf-8")
    assert "<title>Welsh reels (Rîl) · Y Sesiwn</title>" in page and '<base href="../../">' in page
    assert '<link rel="canonical" href="https://ysesiwn.cymru/math/ril/">' in page
    reels = {t["group"] for t in index["tunes"] if t["version"] == 1 and t["type"] == "Rîl"}
    assert set(re.findall(r'<a href="alaw/([^/]+)/">', page)) == reels
    assert "abcjs-basic-min.js" not in page  # no music on it
    home = (out / "index.html").read_text(encoding="utf-8")
    assert all(f'href="math/{b.type_slug(t["name"])}/"' in home for t in index["types"])
    sitemap = (out / "sitemap.xml").read_text(encoding="utf-8")
    assert sitemap.count("<loc>https://ysesiwn.cymru/math/") == len(index["types"])


def test_sessions(site):
    # sessions.json: checked by the build, written for the app, and a page of its own.
    out = b.OUT
    built = json.loads((out / "sessions.json").read_text(encoding="utf-8"))["sessions"]
    assert built and len({s["id"] for s in built}) == len(built)
    assert all(s["county"] == "Outside Wales" or ("x" in s and "y" in s) for s in built)
    page = (out / "sesiynau" / "index.html").read_text(encoding="utf-8")
    assert '<base href="../">' in page and "<title>Active sessions · Y Sesiwn</title>" in page
    assert "2nd Friday of the month, from 21:00" in page and "Last confirmed" in page
    assert "<strong>Llantrisant Tune Club</strong> (tune club): Last Tuesday of the month, from 19:00" in page
    assert "<loc>https://ysesiwn.cymru/sesiynau/</loc>" in (out / "sitemap.xml").read_text(encoding="utf-8")


def test_session_events():
    # The sessions page tells search engines about each session as a repeating event.
    from datetime import date
    sessions = b.session_data()
    ty_tawe = next(s for s in sessions if s["venue"] == "Tŷ Tawe")
    assert b.next_session(ty_tawe, date(2026, 10, 2)) == date(2026, 10, 9)  # 2nd Friday
    assert b.next_session({**ty_tawe, "nth": -1}, date(2026, 10, 2)) == date(2026, 10, 30)
    assert b.next_session({**ty_tawe, "repeat": "weekly"}, date(2026, 10, 2)) == date(2026, 10, 2)
    assert b.next_session({**ty_tawe, "until": "2026-10-01"}, date(2026, 10, 2)) is None
    events = b.session_events(sessions, date(2026, 10, 2))
    e = next(e for e in events if e["location"]["name"] == "Tŷ Tawe")
    assert e["startDate"] == "2026-10-09T21:00" and e["eventSchedule"]["byMonthWeek"] == 2
    assert e["eventSchedule"]["repeatFrequency"] == "P1M" and e["location"]["address"]["addressLocality"] == "Swansea"
    page = (b.OUT / "sesiynau" / "index.html").read_text(encoding="utf-8")
    assert '<script type="application/ld+json">' in page and '"@type": "Event"' in page


@pytest.mark.parametrize("change, says", [
    ({"day": "Tuesdays"}, "day should be one of"),
    ({"county": "South Glamorgan"}, "county should be one of"),
    ({"repeat": "monthly"}, "a monthly session needs nth"),
    ({"start": "7pm"}, "24-hour time"),
    ({"confirmed": "2/10/2026"}, "a date like"),
    ({"venue": ""}, "no venue"),
    ({"kind": "workshop"}, "kind should be"),
])
def test_session_mistakes(tmp_path, monkeypatch, change, says):
    # A mistake in sessions.json stops the build, saying what's wrong.
    good = {"venue": "Y Llew Coch", "address": "Stryd y Bont", "town": "Llandeilo", "county": "Carmarthenshire",
            "lat": 51.88, "lon": -3.99, "day": "Wednesday", "repeat": "weekly", "start": "20:00", "confirmed": "2026-10-02"}
    (tmp_path / "sessions.json").write_text(json.dumps({"sessions": [{**good, **change}]}), encoding="utf-8")
    monkeypatch.setattr(b, "ROOT", tmp_path)
    with pytest.raises(SystemExit, match=says):
        b.session_data()


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


def test_tunes_from_the_session(site):
    # A setting from thesession.org: its version tab says so, and on the tune's own page
    # the source's link part is a link and who added it is text.
    assert b.version_label({"S": ["https://thesession.org/tunes/10046#setting30987 (added by ceri rhys matthews)"]}) == "The Session"
    page = (b.OUT / "alaw" / "y-drochfa" / "index.html").read_text(encoding="utf-8")
    assert ('<a href="https://thesession.org/tunes/17046#setting32566">https://thesession.org/tunes/17046#setting32566</a>'
            " (added by Rowan Folk)") in page
