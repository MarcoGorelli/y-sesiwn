"""Quick checks of the tune files and build_site.py (no browser)."""
import json
import os
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
    for line in abc.split("\nK:", 1)[1].splitlines():  # the header ends at K:
        field = line[:1]
        assert not (line[1:2] == ":" and field in b.HEADER_LABELS.keys() - {"K", "M"}), \
            f"{line!r}: move it above K:, or it's left out of the Details box"
    for text in re.findall(r'"([^"]*)"', body):  # chord symbols, or text starting with ^ _ < > @
        assert re.match(r"[\^_<>@]|[A-G]", text), f'"{text}": text above the stave is written "^{text}"'


def test_titles_and_versions():
    records = [b.tune_record(p) for p in TUNES]
    by_group = {}
    for r in records:
        by_group.setdefault(r["group"], []).append(r["version"])
    for group, versions in by_group.items():
        assert sorted(versions) == list(range(1, len(versions) + 1)), f"{group}: versions {versions}"


# Tunes whose melodies are close but that are kept as separate tunes (on separate pages).
SEPARATE_TUNES = {
    ("llety-r-bugail", "llety-r-bugail-counterpoint"),
    ("ffarwel-i-aberystwyth", "gadael-aberystwyth"),
}


def test_no_tune_twice():
    # A tune already in the app under another name should be a version of it, not a new
    # page. Compared in any key: the runs of 8 steps between notes they share, out of the
    # shorter tune's (when that has at least 20, or a short repetitive air matches anything).
    # A melody recast in another rhythm (Nos Galan, Jig Nos Galan) is a tune of its own.
    runs, record = {}, {}
    for p in TUNES:
        r = b.tune_record(p)
        notes = [ord(c) for c in b.melody_string(r["abc"])]
        steps = [y - x for x, y in zip(notes, notes[1:])]
        runs[r["slug"]] = {tuple(steps[i:i + 8]) for i in range(len(steps) - 7)}
        record[r["slug"]] = r
    gone = [slug for pair in SEPARATE_TUNES for slug in pair if slug not in runs]
    assert not gone, f"SEPARATE_TUNES names tunes that aren't in the app: {gone}"
    tunes_with = {}
    for slug, own in runs.items():
        for run in own:
            tunes_with.setdefault(run, []).append(slug)
    shared = {}
    for slugs in tunes_with.values():
        if len(slugs) <= 40:  # a scale or arpeggio half the tunes have says nothing
            for i, one in enumerate(slugs):
                for other in slugs[i + 1:]:
                    pair = tuple(sorted((one, other)))
                    shared[pair] = shared.get(pair, 0) + 1
    same = []
    for (one, other), n in shared.items():
        fewer = min(len(runs[one]), len(runs[other]))
        a, z = record[one], record[other]
        if (a["group"] != z["group"] and a["type"] == z["type"] and fewer >= 20 and n / fewer >= 0.5
                and (one, other) not in SEPARATE_TUNES):
            same.append(f"{one} / {other} ({n / fewer:.0%})")
    assert not same, ("the same melody as another tune: if it's the same tune, make it a version of it "
                      "(T: <Name> (version N)); if not, add the pair to SEPARATE_TUNES:\n" + "\n".join(sorted(same)))


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


def test_versions_shown_alawon_cymru_last(site):
    # A tune's versions are shown with Alawon Cymru's after the books' and before any of
    # unknown source; each keeps its own number (its folder, ?v= and set links).
    index = json.loads((b.OUT / "tunes.json").read_text(encoding="utf-8"))
    shown = lambda group: [(t["version"], t["source"]) for t in sorted(
        (t for t in index["tunes"] if t["group"] == group), key=lambda t: t["shown"])]
    assert shown("nyth-y-gog") == [(2, "Cat's Claw"), (1, "Alawon Cymru")]
    assert shown("glandyfi") == [(2, "Blodau'r Grug Collection Vol. 1"), (3, "The Session"), (1, "Alawon Cymru")]
    assert shown("byth-adre") == [(1, "Alawon Cymru"), (2, "")]


def test_chords_carried_from_alawon_cymru(site):
    # A version without chords gets those of the tune's Alawon Cymru version, if it has the
    # same form and much the same melody: in its own key, and saying where they're from.
    index = json.loads((b.OUT / "tunes.json").read_text(encoding="utf-8"))
    tunes = {t["slug"]: t for t in index["tunes"]}
    read = lambda slug: (b.ROOT / "tunes" / slug / "tune.abc").read_text(encoding="utf-8")
    nyth = tunes["nyth-y-gog-version-2"]
    assert nyth["chords"] == b.CARRIED_CHORDS == "From Alawon Cymru's version of this tune"
    assert "%%chords From Alawon Cymru's version of this tune\nK:Em\n" in nyth["abc"]
    assert 'BA|"Em"GFGFE2 ge|"G"dBAG "D"FAGF|' in nyth["abc"]
    assert b.chords_source(read("nyth-y-gog-version-2")) is None  # the file keeps what the book has
    # Alawon Cymru's is in G, the book's in D: the chords move with it.
    assert 'A2|"D"d2d>dd2f>e|"D"d2A2"A"d2e2|' in tunes["ymdeithdon-capten-reed-version-2"]["abc"]
    # Bars twice as long (4/4 for 2/4): a chord the same as the one before, mid-bar, isn't repeated.
    assert '|:"G"B>AGD EED2|"D"DBA2 "G"DAG2|' in tunes["bois-y-chwarel-version-2"]["abc"]
    # Not carried: a different B part (Tŷ Crwn), a chord that would start mid-note
    # (Rhyfelgyrch Capten Morgan), a different form (Difyrrwch Gwŷr Caernarfon's D.C.).
    for slug in ["ty-crwn-version-2", "rhyfelgyrch-capten-morgan-version-2", "difyrrwch-gwyr-caernarfon-version-2"]:
        assert tunes[slug]["chords"] is None and tunes[slug]["abc"] == read(slug)
    # With two Alawon Cymru versions, from the one more like it (Ffaniglen's version 1, the
    # same note 92% of the time to version 3's 87%); none where another source has chords
    # of its own (Byth Adre).
    assert tunes["ffaniglen-version-2"]["chords"] == b.CARRIED_CHORDS
    assert b.carried_chords(tunes["ffaniglen"]["abc"], read("ffaniglen-version-2"))[1] == tunes["ffaniglen-version-2"]["abc"]
    assert tunes["byth-adre-version-2"]["chords"] == ""


def test_chord_names_transposed():
    assert b.transpose_chord("G", 7, False) == "D" and b.transpose_chord("Em7", 2, False) == "F#m7"
    assert b.transpose_chord("D/F#", -2, True) == "C/E" and b.transpose_chord("A", 1, True) == "Bb"


def test_types_and_tempos():
    read = lambda slug: b.parse_headers((b.ROOT / "tunes" / slug / "tune.abc").read_text(encoding="utf-8"))
    assert b.tune_type(read("glandyfi")) and b.default_bpm(read("llancesau-trefaldwyn")) == 112  # a jig
    assert b.tune_type(read("llancesau-trefaldwyn")) == "Jig"
    # Airs are slow and 4/4 airs are counted in four: crotchet = 66, dotted crotchet = 44.
    afon_elwy = read("afon-elwy")
    beat = b.beat_unit(afon_elwy["M"][0], b.tune_type(afon_elwy) in b.SLOW_TYPES)
    assert (beat, b.default_bpm(afon_elwy, beat)) == (b.Fraction(1, 4), 66)
    assert b.default_bpm(read("beauties-of-ragland"), b.Fraction(3, 8)) == 44
    assert b.beat_unit("4/4") == b.Fraction(1, 2)  # a reel is still counted in two
    # A polca written in notes twice as long as usual says so (%%beat 1/2): minim = 100,
    # as fast as the same tune written the usual way (Polca Redowa, version 2).
    redowa = b.tune_record(b.ROOT / "tunes" / "polca-redowa" / "tune.abc")
    assert (redowa["beat"], redowa["bpm"]) == ("1/2", 100)
    assert b.tune_record(b.ROOT / "tunes" / "polca-redowa-version-2" / "tune.abc")["beat"] == "1/4"
    assert b.own_beat("X:1\nK:G\n") is None
    assert b.tune_type(read("bwced")) == "Jig naid"  # R:Slip Jig
    assert b.tune_type(read("slipio")) == "Jig naid"  # R:jig naid
    assert b.tune_type({"R": ["jig"], "M": ["9/8"]}) == "Jig naid"  # a jig is in 6/8


def test_jigs_in_6_8():
    # A jig in 9/8 is a slip jig (jig naid): every tune called a jig is in 6/8.
    for path in TUNES:
        headers = b.parse_headers(path.read_text(encoding="utf-8"))
        if b.tune_type(headers) == "Jig":
            assert headers.get("M", [""])[0].replace(" ", "") != "9/8", path.parent.name


def test_no_empty_details():
    # A blank header line (R: with nothing after it) isn't a row of the Details box.
    read = lambda slug: b.parse_headers((b.ROOT / "tunes" / slug / "tune.abc").read_text(encoding="utf-8"))
    assert "Tune type" not in [label for label, _ in b.details(read("a-honeyed-lip"))[0]]
    for path in TUNES:
        rows, _ = b.details(b.parse_headers(path.read_text(encoding="utf-8")))
        assert all(value.strip() for _, value in rows), path.parent.name


def test_meter_as_numbers():
    # Common and cut time are shown as 4/4 and 2/2: a lone "C" would read as the key.
    meter = lambda m: dict(b.details({"M": [m]})[0])["Time signature"]
    assert (meter("C"), meter("C|"), meter("6/8")) == ("4/4", "2/2", "6/8")


def test_places():
    groups = {b.tune_record(p)["group"] for p in TUNES}
    places = b.places(groups)  # stops with an error if a tune doesn't exist
    width, height = map(float, re.search(r'viewBox="0 0 ([\d.]+) ([\d.]+)"',
                                         (b.ROOT / "site" / "wales.svg").read_text()).groups())
    for place in places:
        # On the map (Chester and Oswestry are just over the border, still inside it).
        assert 0 <= place["x"] <= width and 0 <= place["y"] <= height, place["name"]


# Words in a tune's name that suggest a place (in Welsh or English), for test_place_names_decided.
PLACE_WORDS = re.compile(
    r"\b(Llan\w*|Aber\w*|Caer\w*|Pont\w*|Cwm\w*|Tre[fn]\w*|Bryn\w*|Rhyd\w*|Ynys\w*|Glan\w*|Nant\w*|Porth\w*|Pen[- ]?\w+|"
    r"Castell|Castle|Vale|Bridge|Abbey|Ffestiniog|Gwynedd|Gwent|Glamorgan|Morgannwg|Clwyd|Dyfi|Dovey|Teifi|Hafren|Gwy|Wye|Wysg|Usk|"
    r"Menai|Mona|Môn|Anglesey|Snowdon|Eryri|Idris|Bala|Corris|Mawddwy|Ragland|Rhaglan|Tintern|Llanthony|Newport|Pool|"
    r"Denbigh|Dinbych|Kidwelli|Cydweli|Cardigan|Aberdare|Cwmbach|Aman|Neyland|Beacons|Brecon|Gower|Gŵyr|Chester|Harlech|Conwy|"
    r"Bangor|Carmarthen|Swansea|Cardiff|Merthyr|Tydfil|Dowlais|Rhondda|Caersws|Machynlleth|Dolgellau|Barmouth|Bermo|Pwllheli|"
    r"Margam|Nedd|Neath|Holywell|Rhuddlan|Caerleon|Chepstow|Hirwaun|Tywyn|Wrecsam|Wrexham|Monmouth|Mynwy|Powys|Ceredigion|"
    r"Pembroke|Penfro|Tenby|Freshwater|Rhuthun|Ruthin|Mwnge|Prestych|Wig|Wick|Darowen|Rheidol|Elwy|Camlad)\b", re.I)


def tune_names():
    """Each tune (its folder name, without "-version-2") and every title any version has."""
    names = {}
    for p in TUNES:
        record = b.tune_record(p)
        names.setdefault(record["group"], set()).update(record["titles"])
    return names


def test_every_tune_has_a_pronunciation_or_is_english():
    # A new tune needs a decision: how to say its Welsh name ("say"), or that it's English
    # ("english"), so a Welsh name is never left without its guide (or read out as English).
    data = json.loads((b.ROOT / "pronunciation.json").read_text(encoding="utf-8"))
    missing = sorted(set(tune_names()) - set(data["say"]) - set(data["english"]))
    assert not missing, ("pronunciation.json: add these tunes to \"say\" (how to say a Welsh name) "
                         f"or to \"english\": {', '.join(missing)}")


def test_place_names_decided():
    # A tune whose name looks like a place, or names one on the map (Pibddawns Corwen, as
    # well as Ymdaith Corwen), is on the map, or listed as not a place ("not_places").
    data = json.loads((b.ROOT / "places.json").read_text(encoding="utf-8"))
    decided = {t for place in data["places"] for t in place["tunes"]} | set(data["not_places"])
    on_map = re.compile(r"\b(" + "|".join(re.escape(p["name"]) for p in data["places"]) + r")\b", re.I)
    undecided = sorted(group for group, titles in tune_names().items()
                       if group not in decided and any(PLACE_WORDS.search(t) or on_map.search(t) for t in titles))
    assert not undecided, ("places.json: put these tunes on the map under their place, "
                           f"or in \"not_places\": {', '.join(undecided)}")


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
    assert not [k for k in say if k.startswith("the-")]  # "The Grey Cuckoo" isn't "theh gray kik-KO-o"
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
    # the last commit and the one before, and against NUMBERS_BASE when it's set: on
    # GitHub, what main was before the push (several commits may come at once) or a pull
    # request's base; before a push (.githooks/pre-push), the branch's upstream.
    numbers = b.load_numbers()
    assert len(set(numbers.values())) == len(numbers), "two tunes share a number"
    assert all(isinstance(n, int) and n >= 0 for n in numbers.values())
    base = os.environ.get("NUMBERS_BASE", "").strip()
    message = ("tune_numbers.json changes numbers that set links use (was, now): {}. "
               "Only add new tunes (python build_site.py --number-tunes); keep removed ones.")
    for revision in ["HEAD"] + ([base] if base and set(base) != {"0"} else []):
        before = committed_numbers(revision)
        if before is not None:
            changed = number_problems(before, numbers)
            assert not changed, message.format(changed)
    # The commit before: for a merge, one of its parents. Two branches can each give a new
    # tune the same number; the merge keeps the pushed one's and renumbers the other, which
    # had never been pushed, so it only has to agree with one parent (NUMBERS_BASE above
    # checks it against what was pushed).
    parents = [p for p in (committed_numbers(f"HEAD^{i}") for i in (1, 2)) if p is not None]
    problems = [number_problems(before, numbers) for before in parents]
    assert not parents or not all(problems), message.format(problems[0])


def test_moved_tunes(tmp_path, monkeypatch):
    # moved.json: a renamed tune's old folder name, with the codes old set links use for it.
    numbers = {"hen-enw": 7, "glandyfi": 3}
    (tmp_path / "moved.json").write_text(json.dumps({"moved": {"hen-enw": "glandyfi"}}), encoding="utf-8")
    monkeypatch.setattr(b, "ROOT", tmp_path)
    assert b.moved_tunes({"glandyfi"}, numbers) == [
        {"from": "hen-enw", "to": "glandyfi", "code": b.set_code("hen-enw", numbers), "id": b.short_id("hen-enw")}]
    with pytest.raises(SystemExit, match="still a folder"):
        b.moved_tunes({"glandyfi", "hen-enw"}, numbers)
    with pytest.raises(SystemExit, match="no tunes/glandyfi"):
        b.moved_tunes({"other"}, numbers)


def test_moved_tune_pages(tmp_path, monkeypatch):
    # The old address of a moved tune is a page sending people on to the new one: to its
    # version (Alawon Cymru's, shown after the book's), or the tune's own address for
    # the version it opens on.
    monkeypatch.setattr(b, "moved_tunes", lambda slugs, numbers: [
        {"from": "hen-enw", "to": "sawdl-y-fuwch", "code": "zz", "id": "zzzzz"},
        {"from": "enw-arall", "to": "sawdl-y-fuwch-version-2", "code": "zy", "id": "zzzzy"}])
    monkeypatch.setattr(b, "OUT", tmp_path / "_site")
    b.main()
    page = (b.OUT / "alaw" / "hen-enw" / "index.html").read_text(encoding="utf-8")
    assert '<meta http-equiv="refresh" content="0; url=../sawdl-y-fuwch/?v=1">' in page
    assert '<link rel="canonical" href="https://ysesiwn.cymru/alaw/sawdl-y-fuwch/?v=1">' in page
    page = (b.OUT / "alaw" / "enw-arall" / "index.html").read_text(encoding="utf-8")
    assert '<meta http-equiv="refresh" content="0; url=../sawdl-y-fuwch/">' in page


def test_decorations_are_not_notes():
    # !fermata! and the like aren't notes (its f, e and a once were, for the note search).
    abc = "X:1\nT:t\nM:4/4\nL:1/8\nK:D\n!fermata!A4 !trill!B4|]\n"
    assert b.melody(abc) == [69, 71]


def test_tied_notes_are_one_note():
    # A note tied to the next is held, not played again (for the note search); a repeat is played again.
    abc = "X:1\nT:t\nM:4/4\nL:1/8\nK:C\nA4- A2 AB | c4 -c4|]\n"
    assert b.melody(abc) == [69, 69, 71, 72]


def test_playwright_matches_the_dev_container():
    # The dev container's image comes with browsers for one Playwright version only.
    image = re.search(r"playwright/python:v([\d.]+)", (b.ROOT / ".devcontainer" / "Dockerfile").read_text(encoding="utf-8"))
    pinned = re.search(r"^playwright==([\d.]+)", (b.ROOT / "requirements-dev.txt").read_text(encoding="utf-8"), re.M)
    assert image and pinned and image.group(1) == pinned.group(1)


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
    moved = {m["from"] for m in index["moved"]}  # their old addresses send people on
    assert {p.name for p in (out / "alaw").iterdir()} == groups | moved
    page = (out / "alaw" / "llancesau-trefaldwyn" / "index.html").read_text(encoding="utf-8")
    url = "https://ysesiwn.cymru/alaw/llancesau-trefaldwyn/"
    assert '<base href="../../">' in page
    assert "<title>Llancesau Trefaldwyn · Y Sesiwn</title>" in page
    assert f'<meta property="og:url" content="{url}">' in page and f'<link rel="canonical" href="{url}">' in page
    assert '<meta property="og:title" content="Llancesau Trefaldwyn · Y Sesiwn">' in page
    description = ("Llancesau Trefaldwyn: a Welsh jig in D major. Sheet music, example chords and playback in any key, at any tempo (2 versions). "
                   "Alaw werin o Gymru (jig yn D fwyaf): y sgôr, cordiau a chwarae mewn unrhyw gywair.")
    assert f'<meta name="description" content="{description}">' in page
    assert f'<meta property="og:description" content="{description}">' in page
    data = json.loads(re.search(r'<script type="application/ld\+json">(.*?)</script>', page).group(1))
    assert data["name"] == "Llancesau Trefaldwyn" and data["musicalKey"] == "D major"
    assert "<h1>Llancesau Trefaldwyn</h1>" in page and "K:D" in page  # readable without the app
    source = "https://trillian.mit.edu/"  # the version it opens on, Cat's Claw's (Alawon Cymru's is last)
    assert f'<dt>Source</dt><dd><a href="{source}' in page
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
    reels = {t["group"] for t in index["tunes"] if t["shown"] == 1 and t["type"] == "Rîl"}
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
    assert "<strong>Llantrisant Tune Club</strong></a> (tune club): Last Tuesday of the month, from 19:00" in page
    assert '<a href="sesiynau/ty-tawe-swansea-friday/"><strong>Sesiwn Werin Tŷ Tawe</strong></a>' in page
    sitemap = (out / "sitemap.xml").read_text(encoding="utf-8")
    assert "<loc>https://ysesiwn.cymru/sesiynau/</loc>" in sitemap
    # Each session's own page, to send: its own title and description for the link preview.
    for s in built:
        assert f"<loc>https://ysesiwn.cymru/sesiynau/{s['id']}/</loc>" in sitemap
        assert (out / "sesiynau" / s["id"] / "index.html").exists()
    page = (out / "sesiynau" / "ty-tawe-swansea-friday" / "index.html").read_text(encoding="utf-8")
    assert '<base href="../../">' in page and "<title>Sesiwn Werin Tŷ Tawe, Swansea · Y Sesiwn</title>" in page
    assert '<meta property="og:description" content="Folk session with Welsh tunes: 2nd Friday of the month, from 21:00.' in page
    assert '<link rel="canonical" href="https://ysesiwn.cymru/sesiynau/ty-tawe-swansea-friday/">' in page
    assert page.count('"@type": "Event"') == 1
    assert b.session_title({"name": "Sesiwn Werin", "venue": "Cwrw", "town": "Carmarthen"}) == "Sesiwn Werin, Cwrw, Carmarthen"
    assert b.session_title({"name": "Llantrisant Tune Club", "venue": "Caerlan Hall", "town": "Llantrisant"}) == "Llantrisant Tune Club"
    assert b.session_title({"venue": "Hoogah", "town": "Swansea"}) == "Session at Hoogah, Swansea"


def test_session_events(site):
    # The sessions page tells search engines about each session as a repeating event.
    from datetime import date
    sessions = b.session_data()
    ty_tawe = next(s for s in sessions if s["venue"] == "Tŷ Tawe")
    assert b.next_session(ty_tawe, date(2026, 10, 2)) == date(2026, 10, 9)  # 2nd Friday
    assert b.next_session({**ty_tawe, "nth": -1}, date(2026, 10, 2)) == date(2026, 10, 30)
    assert b.next_session({**ty_tawe, "repeat": "weekly"}, date(2026, 10, 2)) == date(2026, 10, 2)
    assert b.next_session({**ty_tawe, "until": "2026-10-01"}, date(2026, 10, 2)) is None
    fortnightly = {**ty_tawe, "repeat": "fortnightly", "from": "2026-10-16"}  # a Friday
    assert b.next_session(fortnightly, date(2026, 10, 2)) == date(2026, 10, 16)  # not before it starts
    assert b.next_session(fortnightly, date(2026, 10, 17)) == date(2026, 10, 30)  # every other Friday
    assert b.next_session(fortnightly, date(2026, 10, 31)) == date(2026, 11, 13)  # across the clocks' change
    assert b.describe_session(fortnightly) == "Every other Friday, from 21:00"
    assert b.session_events([fortnightly], date(2026, 10, 2))[0]["eventSchedule"]["repeatFrequency"] == "P2W"
    events = b.session_events(sessions, date(2026, 10, 2))
    e = next(e for e in events if e["location"]["name"] == "Tŷ Tawe")
    assert e["startDate"] == "2026-10-09T21:00" and e["eventSchedule"]["byMonthWeek"] == 2
    assert e["eventSchedule"]["repeatFrequency"] == "P1M" and e["location"]["address"]["addressLocality"] == "Swansea"
    page = (b.OUT / "sesiynau" / "index.html").read_text(encoding="utf-8")
    assert '<script type="application/ld+json">' in page and '"@type": "Event"' in page


def test_embed_pages(site):
    # Every tune for other websites, at embed/<folder>/, with its own data, kept out of search
    # engines and out of the offline copy; the template itself isn't published.
    out = b.OUT
    groups = {t["group"] for t in json.loads((out / "tunes.json").read_text(encoding="utf-8"))["tunes"]}
    assert {p.name for p in (out / "embed").iterdir()} == groups
    page = (out / "embed" / "glandyfi" / "index.html").read_text(encoding="utf-8")
    assert '<base href="../../">' in page and '<meta name="robots" content="noindex">' in page
    assert "<title>Glandyfi · Y Sesiwn</title>" in page and '<link rel="canonical" href="https://ysesiwn.cymru/alaw/glandyfi/">' in page
    data = json.loads(re.search(r'<script type="application/json" id="tune-data">(.*?)</script>', page).group(1))
    assert {t["group"] for t in data["tunes"]} == {"glandyfi"} and len(data["tunes"]) > 1  # all its versions
    assert '<body data-page="embed">' in page and not (out / "embed.html").exists()
    sw = (out / "sw.js").read_text(encoding="utf-8")
    assert '"embed/glandyfi/' not in sw and '"embed.md"' in sw  # the guide is kept for offline, the tunes for other websites aren't
    assert "<loc>https://ysesiwn.cymru/?page=embed</loc>" in (out / "sitemap.xml").read_text(encoding="utf-8")


def test_static_copy_is_marked(site):
    # What each page says for search engines is in <main>'s .static, which readers whose
    # browser runs the app don't see (style.css); then the page's loading line.
    pages = {"index.html": "Loading tunes…", "alaw/glandyfi/index.html": "Loading the sheet music…",
             "math/jig/index.html": "Loading tunes…", "sesiynau/index.html": "Loading the sessions…"}
    for path, loading in pages.items():
        main = re.search(r'<main id="main" tabindex="-1">(.*)</main>', (b.OUT / path).read_text(encoding="utf-8"), re.S).group(1)
        assert main.startswith('<div class="static">') and main.endswith(f'</div><p class="loading">{loading}</p>'), path


def test_sessions_on_dates(tmp_path, monkeypatch, capsys):
    # A session on announced dates (repeat: "dates"): its next date, an event for each
    # date to come, the day of the next one (for the day filter), and no day of its own.
    from datetime import date
    session = {"venue": "Y Llew Coch", "address": "Stryd y Bont", "town": "Llandeilo", "county": "Carmarthenshire",
               "lat": 51.88, "lon": -3.99, "repeat": "dates", "dates": ["2026-10-22", "2026-11-19"],
               "start": "19:30", "confirmed": "2026-10-04"}
    (tmp_path / "sessions.json").write_text(json.dumps({"sessions": [session]}), encoding="utf-8")
    monkeypatch.setattr(b, "ROOT", tmp_path)
    [s] = b.session_data(date(2026, 10, 23))
    assert s["day"] == "Thursday" and s["id"] == "y-llew-coch-llandeilo"
    assert b.next_session(s, date(2026, 10, 4)) == date(2026, 10, 22)
    assert b.next_session(s, date(2026, 10, 22)) == date(2026, 10, 22)  # on the day itself
    assert b.next_session(s, date(2026, 11, 20)) is None
    assert b.describe_session(s, date(2026, 10, 4)) == "Thursday 22 October 2026, Thursday 19 November 2026, from 19:30"
    assert b.describe_session(s, date(2026, 12, 1)) == "On dates announced as they come; none to come yet"
    events = b.session_events([s], date(2026, 10, 4))
    assert [e["startDate"] for e in events] == ["2026-10-22T19:30", "2026-11-19T19:30"]
    assert not any("eventSchedule" in e for e in events) and events[0]["location"]["name"] == "Y Llew Coch"
    assert b.session_events([s], date(2026, 12, 1)) == []
    capsys.readouterr()
    b.session_data(date(2026, 12, 1))  # all past: still listed, with a note to add the next date
    assert "no dates to come" in capsys.readouterr().out


@pytest.mark.parametrize("change, says", [
    ({"day": "Tuesdays"}, "day should be one of"),
    ({"county": "South Glamorgan"}, "county should be one of"),
    ({"repeat": "monthly"}, "a monthly session needs nth"),
    ({"start": "7pm"}, "24-hour time"),
    ({"confirmed": "2/10/2026"}, "a date like"),
    ({"venue": ""}, "no venue"),
    ({"kind": "workshop"}, "kind should be"),
    ({"repeat": "dates"}, "no dates"),
    ({"repeat": "dates", "dates": ["2026-10-22"]}, "has no day"),
    ({"repeat": "dates", "dates": ["22/10/2026"], "day": None}, "a list of dates like"),
    ({"repeat": "dates", "dates": ["2026-11-19", "2026-10-22"], "day": None}, "in order"),
    ({"repeat": "yearly"}, 'repeat should be "weekly", "fortnightly", "monthly" or "dates"'),
    ({"repeat": "fortnightly"}, "a fortnightly session needs from"),
    ({"repeat": "fortnightly", "from": "2026-10-15"}, "from should be a Wednesday"),
])
def test_session_mistakes(tmp_path, monkeypatch, change, says):
    # A mistake in sessions.json stops the build, saying what's wrong.
    good = {"venue": "Y Llew Coch", "address": "Stryd y Bont", "town": "Llandeilo", "county": "Carmarthenshire",
            "lat": 51.88, "lon": -3.99, "day": "Wednesday", "repeat": "weekly", "start": "20:00", "confirmed": "2026-10-02"}
    session = {k: v for k, v in {**good, **change}.items() if v is not None}  # None: left out
    (tmp_path / "sessions.json").write_text(json.dumps({"sessions": [session]}), encoding="utf-8")
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
