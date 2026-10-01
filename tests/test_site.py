"""The site itself, in a headless browser: every tune draws, the searches find what
they should, and the chords, map, phone layout, offline copy and microphone work."""
import math
import random
import struct
import wave

import pytest

pytestmark = pytest.mark.browser


def test_every_tune_draws(page):
    # Every tune and version, with each playback setting, through the same steps as
    # drawScore(): a tune that comes out with no notes shows a blank score.
    page.goto_site()
    empty = page.evaluate("""() => {
      const empty = [];
      for (const tune of state.data.tunes) {
        for (const play of ["tune", "both", "chords"]) {
          const abc = accompaniment(setTempo(stripFields(tune.abc, "SZBNAH"), tune.beat, tune.bpm), play === "both");
          const lines = ABCJS.renderAbc("*", abc)[0].lines;
          const notes = lines.flatMap((l) => l.staff?.[0].voices[0] ?? []).filter((e) => e.el_type === "note");
          if (!notes.length) empty.push(`${tune.slug} (${play})`);
        }
      }
      return empty;
    }""")
    assert empty == []


# Bars that don't fill the time signature, other than a lead-in and the short bars at
# the end of a part, are usually a slip (a bar line missing or one too many).
EXPECTED_ODD_BARS = {
    "blwyddyn-newydd-dda": "changes to 6/8 for two bars",
    "llongau-caernarfon": "has one bar in 6/4",
    "bonheddwr-mawr-o-r-bala": "its second part starts with a lead-in, without a double bar",
    "merch-megan-version-2": "its third part starts with a lead-in, without a double bar",
    "rownd-yr-horn": "its endings are split across a tie, as on the score",
    "erddigan-caer-waen": "has a part in 6/8",
    "ffarwel-trwy-r-pwll": "has a part in 6/8",
    # A note short in Brian Martin's file, and in the tune's N: line; the right note isn't known.
    "castell-aberystwyth": "bar 4 of part B is a quaver short",
    "megan-a-gollodd-ei-gardas-version-3": "two bars are a quaver short",
    "plygiad-y-bedol": "bar 8 is two quavers short",
}


def test_bars_fill_the_time_signature(page):
    page.goto_site()
    odd = page.evaluate("""() => state.data.tunes.map((t) => {
      const v = ABCJS.renderAbc('*', t.abc)[0];
      const { num, den } = v.getMeterFraction();
      const bars = [];
      let length = 0, tuplet = 1;
      for (const line of v.lines) for (const item of line.staff?.[0]?.voices?.[0] ?? []) {
        if (item.el_type === 'note') {
          if (item.startTriplet) tuplet = item.tripletMultiplier ?? 1;
          length += (item.duration ?? 0) * tuplet;
          if (item.endTriplet) tuplet = 1;
        } else if (item.el_type === 'bar') {
          if (length > 1e-6) bars.push({ length, type: item.type });
          length = 0;
        }
      }
      const partEnd = (type) => /repeat|thin_thin|thin_thick/.test(type ?? '');
      return [t.slug, bars.filter((b, i) => i > 0 && i < bars.length - 1 && Math.abs(b.length - num / den) > 1e-6
        && !partEnd(b.type) && !partEnd(bars[i - 1].type)).length];
    }).filter(([, n]) => n).map(([slug]) => slug)""")
    assert sorted(odd) == sorted(EXPECTED_ODD_BARS)


@pytest.mark.parametrize("slug", ["pibddawns-gwyr-gwrecsam", "glandyfi", "nyth-y-gog", "erddygan-y-pibydd-coch"])
def test_tune_page(page, slug):
    page.goto_site(f"?tune={slug}")
    page.wait_for_selector(".score .abcjs-staff")
    assert page.locator(".score .abcjs-note").count() > 20
    assert page.locator(".abcjs-inline-audio").count() == 1


def test_details(page):
    # The source (S:) is a link; notes (N:) aren't shown.
    page.goto_site("?tune=glwysen&v=2")
    page.wait_for_selector(".card dl")
    dts = page.locator(".card dt").all_inner_texts()
    assert "Source" in dts and "Notes" not in dts
    link = page.locator(".card dd a")
    assert link.get_attribute("href") == "https://trillian.mit.edu/~jc/music/abc/mirror/BrianMartin/msg/welsh_tunes_1.abc"
    assert "Transcribed by Brian Martin" not in page.locator(".card dl").inner_text()


def test_recently_opened(page):
    # The home page lists the last five tunes opened here, most recent first.
    page.goto_site()
    assert page.locator(".recent").count() == 0  # none yet
    for slug in ["glandyfi", "machynlleth", "nyth-y-gog", "llancesau-trefaldwyn", "cawl-cennin", "sawdl-y-fuwch", "machynlleth"]:
        page.goto_site(f"alaw/{slug}/")
        page.wait_for_selector(".score .abcjs-staff")
    page.click(".brand")
    assert page.locator(".recent a").all_inner_texts() == [
        "Machynlleth", "Sawdl y Fuwch", "Cawl Cennin", "Llancesau Trefaldwyn", "Nyth y Gog"]


def test_markdown_reader_only_for_its_pages(page):
    # The Markdown reader is only loaded for About and the guides.
    requests = []
    page.on("request", lambda r: requests.append(r.url))
    page.goto_site("alaw/glandyfi/")
    page.wait_for_selector(".score .abcjs-staff")
    assert not [u for u in requests if "marked" in u]
    page.click(".sidebar-links a[href='?page=about']")
    page.wait_for_selector("main h1:text-is('About Y Sesiwn')")
    assert [u for u in requests if "marked" in u]


def test_history_in_details_not_on_the_score(page):
    # A long H: (history) would run off the edge of the score; it's in Details instead.
    page.goto_site("alaw/gorhoffedd-gwyr-harlech/")
    page.wait_for_selector(".score .abcjs-staff")
    assert "facsimile" not in page.inner_text(".score")
    assert "facsimile" in page.inner_text(".tune-side .card dl")


def test_transposing(page):
    page.goto_site("?tune=glandyfi")
    page.wait_for_selector(".chart .bar")
    first = lambda: page.locator(".chart .beats span").first.inner_text()
    assert first() == "G"
    page.select_option("#key-select", "2")  # up a tone: G major -> A major
    page.wait_for_function("document.querySelector('.chart .beats span').textContent === 'A'")
    assert "F♯m" in page.locator(".chart").inner_text()  # Em -> F#m


def drawn_range(page, abc_js):
    # The lowest and highest MIDI pitch of a tune's notes, as abcjs reads them.
    return page.evaluate("""(abc) => { const v = ABCJS.renderAbc('*', abc)[0]; v.setUpAudio();
      const p = v.lines.flatMap((l) => l.staff?.[0]?.voices?.[0] ?? []).flatMap((e) => (e.midiPitches || []).map((m) => m.pitch));
      return [Math.min(...p), Math.max(...p)]; }""", abc_js)


def test_transposing_keeps_a_sensible_range(page):
    # A key is reached up or down, whichever keeps the notes on the stave: Tros y Garreg
    # (A below middle C up to D) goes up a fifth to A minor, not down a fourth.
    page.goto_site("alaw/tros-y-garreg/")
    page.wait_for_selector(".score .abcjs-staff")
    assert page.evaluate("semitones(state.bySlug.get('tros-y-garreg'), -5)") == 7
    page.select_option("#key-select", "-5")
    page.wait_for_function("document.querySelector('#key-select').value === '-5'")
    assert page.evaluate("document.querySelector('#key-select').selectedOptions[0].textContent") == "A minor"
    abc = page.evaluate("""() => { const t = state.bySlug.get('tros-y-garreg');
      return ABCJS.strTranspose(t.abc, ABCJS.renderAbc('*', t.abc), semitones(t, -5)); }""")
    low, high = drawn_range(page, abc)
    assert 59 <= low and high <= 81  # E4 to A5, on the stave
    # Where the shorter way already fits, it's still the shorter way.
    assert page.evaluate("semitones(state.bySlug.get('glandyfi'), 2)") == 2
    assert page.evaluate("semitones(state.bySlug.get('glandyfi'), 0)") == 0


def test_chord_chart(page):
    page.goto_site("?tune=glandyfi")
    page.wait_for_selector(".chart .bar")
    # Two chords in a bar each get half of it (G on beat 1, D on beat 2 of 6/8).
    halves = page.evaluate("""() => [...document.querySelectorAll('.chart .beats')].filter((b) => b.children.length === 2)
      .map((b) => Math.round(100 * (b.children[1].getBoundingClientRect().left - b.getBoundingClientRect().left) / b.getBoundingClientRect().width))""")
    assert halves and all(48 <= h <= 52 for h in halves)
    assert page.locator(".chart .repeat-start").count() == 2 and page.locator(".chart .repeat-end").count() == 2
    # Chords on the score only when asked for; playback options set abcjs's switches.
    assert page.locator(".score .hide-chords").count() == 1
    page.check("text=Show on the sheet music")
    page.wait_for_function("!document.querySelector('.score .hide-chords')")
    page.click("text=Chords only")
    volumes = page.evaluate("""() => { const [melody, chords] = state.synth.visualObj.setUpAudio({ voicesOff: true }).tracks
      .map((t) => [...new Set(t.filter((e) => e.cmd === 'note').map((e) => e.volume))]); return { melody, chords }; }""")
    assert volumes["melody"] == [0] and max(volumes["chords"]) > 0


def chart_rows(page):
    """The chord chart as text: one string per row, "_" for a blank (indent) cell."""
    page.wait_for_selector(".chart .bar")
    return page.evaluate("""() => [...document.querySelectorAll('.chart-row')].map((r) => [...r.children]
      .map((c) => c.classList.contains('spacer') ? '_' : c.innerText.replace(/\\s+/g, '')).join(' '))""")


@pytest.mark.parametrize("slug", ["ffaniglen", "glandyfi", "machynlleth", "morgawr", "ty-a-gardd", "dic-y-cymro"])
def test_chord_chart_rows_of_four(page, slug):
    # Even rows of 4 bars, whatever the lines of the sheet music (Ffaniglen's has 5 and 3).
    page.goto_site(f"?tune={slug}")
    assert {len(row.split()) for row in chart_rows(page)} == {4}


def test_chord_chart_endings(page):
    # Yr Eingion Dur's A part: 4 bars with a first-time ending, then the second-time
    # ending (different chords) on its own row, under the first.
    page.goto_site("?tune=yr-eingion-dur")
    rows = chart_rows(page)
    assert rows[:2] == ["DG DG DG 1.DA", "_ _ _ 2.AD"]


@pytest.mark.parametrize("slug, first_rows", [
    ("llancesau-trefaldwyn", ["DA D G A", "DA D GA D"]),
    ("byth-adre", ["A DA A AE", "A D AE A"]),
])
def test_chord_chart_same_endings(page, slug, first_rows):
    # Endings whose chords are the same (only the melody differs) become a plain repeat.
    page.goto_site(f"?tune={slug}")
    rows = chart_rows(page)
    assert rows[:2] == first_rows
    assert not any("1." in r or "2." in r for r in rows)
    assert "repeat-end" in page.locator(".chart-row").nth(1).locator(".bar").last.get_attribute("class")


@pytest.mark.parametrize("mode, score, chords_on_score, chart", [
    ("Print the sheet music", True, False, False),
    ("Print with chords", True, True, False),
    ("Print the chord chart", False, False, True),
])
def test_print(page, mode, score, chords_on_score, chart):
    page.goto_site("?tune=glandyfi")
    page.wait_for_selector(".chart .bar")
    page.evaluate("window.print = () => {}")  # the real print dialog can't be driven
    page.select_option("#key-select", "2")  # prints in the key chosen on the page
    page.click("text=Print / save ▾")
    page.click(f".print-menu >> text='{mode}'")
    page.emulate_media(media="print")
    assert page.locator(".score").is_visible() == score
    assert page.locator(".score .abcjs-chord").first.is_visible() == chords_on_score
    assert page.locator(".chart").is_visible() == chart
    if chart:
        assert page.locator(".print-key").inner_text() == "Key: A major"
        assert page.locator("main > h1").is_visible()
    assert not page.locator(".nav").is_visible() and not page.locator(".controls").is_visible()
    # Afterwards the page is as it was.
    page.emulate_media(media="screen")
    page.evaluate("window.dispatchEvent(new Event('afterprint'))")
    assert page.evaluate("document.body.dataset.print") is None
    assert page.locator(".score .hide-chords").count() == 1


def test_print_menu(page):
    page.goto_site("?tune=glandyfi")
    page.click("text=Print / save ▾")
    assert page.locator(".print-menu").is_visible()
    page.mouse.click(5, 900)  # clicking elsewhere closes it
    assert not page.locator(".print-menu").is_visible()
    page.goto_site("?tune=cawl-cennin")  # no chords: no chord printing, but still saving
    page.click("text=Print / save ▾")
    assert page.locator(".print-menu button").all_inner_texts() == ["Print the sheet music", "Save as ABC", "Save as MIDI"]


SPY_SWING = """() => {
  window.swings = [];
  const Player = ABCJS.synth.SynthController;
  ABCJS.synth.SynthController = function () {
    const player = new Player(), setTune = player.setTune;
    player.setTune = (tune, userAction, params) => { window.swings.push(params.swing ?? null); return setTune.call(player, tune, userAction, params); };
    return player;
  };
}"""


def test_swing(page):
    # Hornpipes are played swung, with a switch; a polka in 2/4 can be; a jig in 6/8 can't.
    page.goto_site()
    page.evaluate(SPY_SWING)
    page.evaluate("navigate('alaw/pibddawns-abertawe/')")
    page.wait_for_selector(".score .abcjs-staff")
    assert page.locator(".swing input").is_checked()
    page.uncheck(".swing input")
    assert page.evaluate("window.swings") == [62, None]
    page.evaluate("navigate('alaw/abaty-waltham/')")  # a polka in 2/4: can swing, but doesn't to start with
    page.wait_for_selector(".score .abcjs-staff")
    assert not page.locator(".swing input").is_checked()
    page.evaluate("navigate('alaw/cawl-cennin/')")  # a jig in 6/8
    page.wait_for_selector(".score .abcjs-staff")
    assert page.locator(".swing").count() == 0


def test_whistle_fingerings(page):
    page.goto_site()
    f = lambda midi, whistle="whistle-D": page.evaluate(
        "([m, w]) => { const r = whistleFingering(m, WHISTLES[w]); return r && [r.holes, r.high]; }", [midi, whistle])
    assert f(62) == ["●●●●●●", False]   # D: all covered
    assert f(66) == ["●●●●○○", False]   # F sharp
    assert f(73) == ["○○○○○○", False]   # C sharp: all open
    assert f(74) == ["●●●●●●", True]    # D, second octave: blow harder
    assert f(72) == ["○●●○○○", False]   # C natural, cross-fingered
    assert f(61) is None and f(86) is None  # below and above a D whistle
    assert f(60, "whistle-C") == ["●●●●●●", False]
    # Lined up under their notes, a tied note's continuation included; rests take none.
    rows = page.evaluate("""() => { const v = ABCJS.renderAbc('*', withFingerings('X:1\\nM:6/8\\nL:1/8\\nK:D\\nD3- D2 E | F2 z G z A|', WHISTLES['whistle-D']))[0];
      return v.lines[0].staff[0].voices[0].filter((e) => e.el_type === 'note' && !e.rest).map((n) => (n.lyric || []).map((l) => l.syllable).join('')); }""")
    assert rows == ["●●●●●●", "", "●●●●●○", "●●●●○○", "●●●○○○", "●●○○○○"]


def test_whistle_on_a_tune(page):
    page.goto_site("alaw/llancesau-trefaldwyn/")
    page.wait_for_selector(".score .abcjs-staff")
    assert page.locator(".whistle-key").is_hidden()
    page.select_option("#tab-select", "whistle-D")
    page.wait_for_selector(".score .abcjs-lyric")
    assert page.locator(".whistle-key").is_visible()
    lyrics = lambda: "".join(page.locator(".score .abcjs-lyric").all_text_contents())
    in_d = lyrics()
    assert "?" not in in_d and "+" in in_d  # all on a D whistle, some in the second octave
    page.select_option("#key-select", "-5")  # down to A: its lowest notes are below the whistle
    page.wait_for_function("(before) => [...document.querySelectorAll('.score .abcjs-lyric')].map((e) => e.textContent).join('') !== before", arg=in_d)
    assert "?" in lyrics()
    page.select_option("#tab-select", "none")
    page.wait_for_function("!document.querySelector('.score .abcjs-lyric')")
    assert page.locator(".whistle-key").is_hidden()


@pytest.mark.parametrize("path", ["alaw/llancesau-trefaldwyn/", "alaw/pibddawns-abertawe/", "alaw/tom-jones/", "",
                                  "?page=sets", "?page=set&s=bne0o", "?page=map", "?page=notes&q=D%20E%20F"])
def test_no_stray_null(page, path):
    # A missing optional part must leave nothing behind, not the word "null" or "undefined".
    page.goto_site(path)
    page.wait_for_function("document.querySelector('#main h1') && !document.querySelector('#main .loading')")
    page.wait_for_timeout(300)
    text = page.inner_text("main")
    assert "null" not in text and "undefined" not in text


def test_source_as_text_or_link(page):
    # A source that's a web address is a link; a description (a recording) is text.
    page.goto_site("alaw/unwaith-eto/")
    page.wait_for_selector(".score .abcjs-staff")
    source = page.locator(".tune-side .card dd").filter(has_text="recording of Rowan Kodratoff")
    assert source.count() == 1 and source.locator("a").count() == 0
    page.goto_site("alaw/glandyfi/")
    page.wait_for_selector(".score .abcjs-staff")
    assert page.inner_text(".tune-side .card dd a").startswith("http://alawoncymru.com/")


def test_tunes_from_the_session(page):
    # Tunes from thesession.org: the setting's link as the source, then who added it there.
    page.goto_site("alaw/y-drochfa/")
    page.wait_for_selector(".score .abcjs-staff")
    source = page.locator(".tune-side .card dd").filter(has_text="thesession.org")
    assert source.inner_text() == "https://thesession.org/tunes/17046#setting32566 (added by Rowan Folk)"
    assert source.locator("a").get_attribute("href") == "https://thesession.org/tunes/17046#setting32566"
    assert "From the setting on The Session" in page.inner_text("main")  # where its chords come from
    page.click(".lang-switch [data-lang=cy]")
    page.wait_for_selector(".score .abcjs-staff")
    assert "O'r gosodiad ar The Session" in page.inner_text("main")
    # A tune already on the site gets The Session's setting as another version, so named.
    page.goto_site("alaw/deildy-aberteifi/?v=2")
    page.wait_for_selector(".score .abcjs-staff")
    assert "The Session" in page.inner_text("nav.versions")
    assert page.evaluate("search('basket of eggs')[0].slug") == "y-fasged-wyau"
    assert page.evaluate("search('bois y cware')[0].slug") == "bois-y-chwarel"


def test_say_it(page):
    # How to say a Welsh tune name, for English readers; not for English names, nor in Welsh.
    page.goto_site("alaw/machynlleth/")
    page.wait_for_selector(".score .abcjs-staff")
    assert page.inner_text(".say-words") == "ma-KHUHN-hleth"
    page.click(".say-key summary")
    assert "ch in loch" in page.inner_text(".say-key")
    page.goto_site("alaw/tom-jones/")
    page.wait_for_selector(".score .abcjs-staff")
    assert page.locator(".say").count() == 0
    page.goto_site("alaw/machynlleth/")
    page.click(".lang-switch [data-lang=cy]")
    page.wait_for_selector(".score .abcjs-staff")
    assert page.locator(".say").count() == 0


def test_save_abc_and_midi(page):
    # The tune as a file, in the key chosen on the page; the MIDI plays what the Play
    # choice says (the tune, or the tune and its chords).
    page.goto_site("alaw/glandyfi/")
    page.wait_for_selector(".score .abcjs-staff")
    page.select_option("#key-select", "2")  # G major -> A major
    page.click("text=Print / save ▾")
    with page.expect_download() as info:
        page.click(".print-menu >> text='Save as ABC'")
    abc = open(info.value.path(), encoding="utf-8").read()
    assert info.value.suggested_filename == "glandyfi-in-A.abc"
    assert "\nK:A" in abc and "T:Glandyfi" in abc
    sizes = {}
    for play in ["Tune only", "Tune and chords"]:
        page.click(f".playback label:has-text('{play}')")
        page.click("text=Print / save ▾")
        with page.expect_download() as info:
            page.click(".print-menu >> text='Save as MIDI'")
        data = open(info.value.path(), "rb").read()
        assert data[:4] == b"MThd" and info.value.suggested_filename == "glandyfi-in-A.mid"
        sizes[play] = len(data)
    assert sizes["Tune and chords"] > sizes["Tune only"]


def test_no_chord_box_without_chords(page):
    page.goto_site("?tune=cawl-cennin")
    page.wait_for_selector(".score .abcjs-staff")
    assert page.locator(".card.chords").count() == 0


@pytest.mark.parametrize("query, expected", [
    ("llancesau trefalwdyn", "Llancesau Trefaldwyn"),  # a typo
    ("fran", None),                                    # accents: "Frân"
    ("mon", "Môn"),                                    # the exact name first, not "harMONi"
    ("helfa'r sgwarnog", "Hel y Sgwarnog"),            # y / yr / 'r
    ("risiart annwyl", "Rhisiart Annwyl"),             # another spelling
])
def test_search_by_name(page, query, expected):
    page.goto_site()
    page.fill("#hero-search", query)
    first = page.locator("#hero-suggestions li").first.inner_text()
    if expected:
        assert first == expected
    else:
        assert "Frân" in first


def test_tunes_sharing_a_name(page):
    # Different tunes with the same name are separate tunes, told apart by their source;
    # searching the name finds them all.
    page.goto_site()
    page.fill("#hero-search", "Morfa Rhuddlan")
    found = page.locator("#hero-suggestions li").all_inner_texts()
    assert {"Morfa Rhuddlan", "Morfa Rhuddlan (Mary Richards)", "Morfa Rhuddlan (Robin Huw Bowen)"} <= set(found)
    versions = page.evaluate("state.groups.get('morfa-rhuddlan').versions.map((v) => v.source)")
    assert versions == ["Alawon Cymru", "51 Welsh Airs"]


@pytest.mark.parametrize("notes, group, how", [
    ("G B D C B G A", "glandyfi", "starts like this"),                # without its lead-in
    ("D G B D C B G A", "glandyfi", "starts like this"),              # with it
    ("G A B C E D C B", "pibddawns-caerfyrddin", "starts like this"),  # 3-note lead-in, in C
    ("D E B G F# G B G F# G", "ty-a-gardd", "after a different lead-in"),
    ("G4 F#4 G4 F#4 E4 E5 D5 B4", "nyth-y-gog", "starts like this"),  # with octaves
    ("D G B E C B G A G", "glandyfi", "close: 1 note different"),     # a wrong note
    ("B C D E C B C B A G", "machynlleth", "close: 1 note different"),  # a note missed
    ("F# E D F# G A B A F# A D", "dic-y-cymro", "close: 1 note different"),  # an extra note
])
def test_search_by_notes(page, notes, group, how):
    page.goto_site()
    results = page.evaluate("(n) => searchByNotes(n).map((r) => [r.tune.group, matchText(r)])", notes)
    # Among the first few: another tune may start the same way (listed alphabetically).
    assert any(g == group and how in h for g, h in results[:3]), results[:3]


def test_search_by_notes_never_empty(page):
    page.goto_site("?page=notes")
    page.fill("#notes-search", "C C# D D# E F F# G G# A")
    assert page.locator(".notes-results li").count() == 5
    assert "nearest" in page.locator("#notes-help").inner_text()


def test_map(page):
    page.goto_site("?page=map")
    page.wait_for_selector(".wales-map circle")
    dots = page.locator(".wales-map circle:not(.target)").count()
    assert dots == page.locator(".place-list li").count() > 50
    caernarfon = page.evaluate("state.data.places.findIndex((p) => p.name === 'Caernarfon')")
    page.hover(f".target[data-place='{caernarfon}']", force=True)
    assert "Castell Caernarfon" in page.locator(".map-popup").inner_text()
    page.goto_site("?tune=machynlleth")
    assert page.locator(".card.place h2").inner_text() == "On the map"  # not "Machynlleth" twice
    page.goto_site("alaw/llancesau-trefaldwyn/")
    assert page.locator(".card.place h2").inner_text() == "Trefaldwyn"


def test_phone_menu(browser, site):
    # On a phone the sidebar's links fold away behind Menu, and the music starts on the
    # first screen; loop, count-in, click and tablature are in practice mode.
    context = browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True,
                                  service_workers="block")
    page = context.new_page()
    page.goto(site + "alaw/glandyfi/")
    page.wait_for_selector(".score .abcjs-staff")
    assert not page.locator(".sidebar-links").is_visible()
    assert page.get_attribute("#menu-button", "aria-expanded") == "false"
    assert page.evaluate("document.querySelector('.score .abcjs-staff').getBoundingClientRect().top") < 844
    assert not page.locator(".practice-row").is_visible()
    page.click("#menu-button")
    assert page.locator(".sidebar-links").is_visible()
    assert page.get_attribute("#menu-button", "aria-expanded") == "true"
    page.click(".sidebar-links a[href='?page=map']")  # opening a page closes the menu
    page.wait_for_selector(".wales-map circle")
    assert not page.locator(".sidebar-links").is_visible()
    context.close()


def test_practice_row_in_practice_mode_on_a_phone(browser, site):
    context = browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True,
                                  service_workers="block")
    page = context.new_page()
    page.goto(site + "alaw/glandyfi/")
    page.wait_for_selector(".score .abcjs-staff")
    page.click(".practice-toggle")
    assert page.locator("#loop-select").is_visible() and page.locator("#tab-select").is_visible()
    context.close()


MAP_SCALE = "Number((document.querySelector('.map-canvas').style.transform.match(/scale\\(([\\d.]+)\\)/) || [0, 1])[1])"
MAP_SHIFT = "document.querySelector('.map-canvas').style.transform.match(/translate\\(([^)]*)\\)/)[1]"
DOT_SIZE = "document.querySelector('.wales-map circle:not(.target)').getBoundingClientRect().width"


def test_map_zoom(page):
    page.goto_site("?page=map")
    page.wait_for_selector(".wales-map circle")
    zoom_in, zoom_out, reset = (page.locator(".map-zoom button").nth(i) for i in range(3))
    assert zoom_out.is_disabled() and reset.is_disabled()
    size = page.evaluate(DOT_SIZE)
    zoom_in.click()
    zoom_in.click()
    assert page.evaluate(MAP_SCALE) > 3
    assert abs(page.evaluate(DOT_SIZE) - size) < 0.5  # dots keep their size on screen
    # Dragging moves about, and a drag that ends on a dot doesn't open it.
    before = page.evaluate(MAP_SHIFT)
    box = page.locator(".map-view").bounding_box()
    cx, cy = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
    page.mouse.move(cx, cy)
    page.mouse.down()
    page.mouse.move(cx + 60, cy + 40, steps=5)
    page.mouse.up()
    assert page.evaluate(MAP_SHIFT) != before
    assert page.locator(".map-popup").is_hidden()
    # Clicking a dot still opens its popup, next to the dot.
    merthyr = page.evaluate("state.data.places.findIndex((p) => p.name === 'Merthyr Tudful')")
    # Scrolling a dot into view once scrolled the zoomed map's own (clipped) view,
    # which then threw every zoom off; the view can't be scrolled now.
    page.locator(".target").nth(merthyr).scroll_into_view_if_needed()
    reset.click()
    assert page.evaluate(MAP_SCALE) == 1 and reset.is_disabled()
    dot = page.locator(f".target[data-place='{merthyr}']").bounding_box()
    page.mouse.move(dot["x"] + dot["width"] / 2, dot["y"] + dot["height"] / 2)
    page.keyboard.down("Control")
    page.mouse.wheel(0, -300)  # a trackpad pinch
    page.keyboard.up("Control")
    assert page.evaluate(MAP_SCALE) > 1
    dot = page.locator(f".target[data-place='{merthyr}']").bounding_box()
    page.mouse.click(dot["x"] + dot["width"] / 2, dot["y"] + dot["height"] / 2)
    assert "Merthyr Tudful" in page.inner_text(".map-popup")
    popup = page.locator(".map-popup").bounding_box()
    assert abs(popup["x"] + popup["width"] / 2 - (dot["x"] + dot["width"] / 2)) < popup["width"]
    # A plain wheel scrolls the page, not the map.
    reset.click()
    page.mouse.wheel(0, 200)
    assert page.evaluate(MAP_SCALE) == 1
    # The keyboard: + zooms, the arrows move about, 0 shows all of Wales.
    page.focus(".map-view")
    page.keyboard.press("+")
    assert page.evaluate(MAP_SCALE) > 1
    before = page.evaluate(MAP_SHIFT)
    page.keyboard.press("ArrowRight")
    assert page.evaluate(MAP_SHIFT) != before
    page.keyboard.press("0")
    assert page.evaluate(MAP_SCALE) == 1


def test_map_pinch_on_a_phone(browser, site):
    # A real two-finger pinch, one-finger drag and double-tap (Chrome's touch emulation).
    context = browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True,
                                  service_workers="block")
    page = context.new_page()
    page.goto(site + "?page=map")
    page.wait_for_selector(".wales-map circle")
    cdp = context.new_cdp_session(page)
    box = page.locator(".map-view").bounding_box()
    cx, cy = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
    touch = lambda kind, points: cdp.send("Input.dispatchTouchEvent", {"type": kind, "touchPoints": points})
    fingers = lambda gap: [{"x": cx - gap, "y": cy, "id": 0}, {"x": cx + gap, "y": cy, "id": 1}]
    touch("touchStart", fingers(20))
    for gap in range(25, 90, 5):
        touch("touchMove", fingers(gap))
    touch("touchEnd", [])
    scale = page.evaluate(MAP_SCALE)
    assert scale > 2
    before = page.evaluate(MAP_SHIFT)
    touch("touchStart", [{"x": cx, "y": cy, "id": 0}])
    for d in range(5, 60, 5):
        touch("touchMove", [{"x": cx + d, "y": cy + d, "id": 0}])
    touch("touchEnd", [])
    assert page.evaluate(MAP_SHIFT) != before and page.evaluate(MAP_SCALE) == scale
    page.wait_for_timeout(600)  # after a swipe, Chrome takes the next tap as "stop scrolling", not a click
    page.locator(".map-zoom button").nth(2).tap()  # all of Wales again
    assert page.evaluate(MAP_SCALE) == 1
    for _ in range(2):  # a double-tap zooms in
        touch("touchStart", [{"x": cx, "y": cy, "id": 0}])
        touch("touchEnd", [])
        page.wait_for_timeout(80)
    assert page.evaluate(MAP_SCALE) == 2
    context.close()


def test_map_on_a_phone(browser, site):
    # Tapping a dot opens its popup, which stays open after the finger lifts (issue #8);
    # tapping elsewhere closes it.
    context = browser.new_context(viewport={"width": 390, "height": 800}, has_touch=True, is_mobile=True,
                                  service_workers="block")
    page = context.new_page()
    page.goto(site + "?page=map")
    page.wait_for_selector(".wales-map .target")
    caernarfon = page.evaluate("state.data.places.findIndex((p) => p.name === 'Caernarfon')")
    page.tap(f".target[data-place='{caernarfon}']", force=True)
    page.wait_for_timeout(600)  # longer than the delay before a mouse-out closes it
    assert page.locator(".map-popup").is_visible()
    assert "Castell Caernarfon" in page.locator(".map-popup").inner_text()
    page.tap("h1")
    assert not page.locator(".map-popup").is_visible()
    context.close()


@pytest.mark.parametrize("lang", ["en", "cy"])  # Welsh labels are often longer
@pytest.mark.parametrize("path", ["", "?page=browse", "?tune=glandyfi", "?tune=llancesau-trefaldwyn", "?page=map",
                                  "?page=offline", "?page=about", "?page=add", "?page=contact",
                                  "?page=notes&q=D%20G%20B%20D%20C%20B%20G%20A"])
def test_fits_a_phone(browser, site, path, lang):
    context = browser.new_context(viewport={"width": 360, "height": 800}, service_workers="block")
    page = context.new_page()
    page.goto(site)
    page.evaluate(f"localStorage.setItem('lang', '{lang}')")
    page.goto(site + path)
    page.wait_for_timeout(700)
    assert page.evaluate("document.documentElement.scrollWidth") <= 360
    context.close()


def test_home_page(page):
    page.goto_site()
    features = page.locator(".features li").all_inner_texts()
    assert len(features) == 8 and any("Accompaniment" in f for f in features)
    assert page.locator(".offline-card").is_visible()
    # One search box on the home page: its own big one, not the sidebar's too.
    assert page.locator("#hero-search").is_visible() and not page.locator("#search-input").is_visible()
    # Browsing every tune has its own page; the home page links to it.
    assert page.locator(".tune-list").count() == 0
    page.click("a.button-link:has-text('Browse all')")
    page.wait_for_selector(".tune-list li")
    assert page.locator(".tune-list li").count() == len(page.evaluate("state.groupList"))


# A page's text, sidebar and footer as the reader sees them, except what is English on
# purpose: the "English" button, browsers' own menu names, and code examples.
VISIBLE_TEXT = """() => {
  const texts = [];
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  while (walker.nextNode()) {
    if (!walker.currentNode.parentElement.closest('.lang-switch, .suggestions, strong[lang="en"], pre, code, style, .abcjs-css-warning')) texts.push(walker.currentNode.textContent.trim());
  }
  for (const n of document.querySelectorAll('[placeholder], [title]')) {
    if (!n.closest('.lang-switch')) texts.push(n.getAttribute('placeholder') ?? '', n.getAttribute('title') ?? '');
  }
  return texts.filter(Boolean).join('\\n');
}"""


def test_welsh_home_page(page):
    import re
    page.goto_site()
    assert page.evaluate("document.documentElement.lang") == "en"
    assert page.get_attribute(".lang-switch [data-lang=en]", "aria-pressed") == "true"
    english = page.evaluate(VISIBLE_TEXT)
    page.click(".lang-switch [data-lang=cy]")
    assert page.inner_text("h1") == "Croeso i'r Sesiwn!"
    assert page.evaluate("document.documentElement.lang") == "cy"
    assert page.get_attribute(".lang-switch [data-lang=cy]", "aria-pressed") == "true"
    assert page.inner_text("#surprise-sidebar") == "Alaw ar hap"
    assert page.get_attribute("#search-input", "placeholder") == "Chwilio am alaw…"
    assert page.locator(".features li").count() == 8
    # Nothing left in English: no sentence of the English page shows up in the Welsh one.
    welsh = page.evaluate(VISIBLE_TEXT)
    fragments = {f.strip() for f in re.split(r"[.:;?!()\n]", english) if len(f.strip()) >= 12}
    assert fragments and not [f for f in fragments if f in welsh]
    # The choice is remembered.
    page.reload()
    page.wait_for_function("typeof state !== 'undefined' && state.data")
    assert page.inner_text("h1") == "Croeso i'r Sesiwn!"
    page.click(".sidebar-links a[href='?page=browse']")
    page.wait_for_selector(".tune-list li")
    assert page.get_attribute("#main", "lang") == "cy"
    assert page.inner_text("main h1") == "Pori yn ôl math a chywair"
    page.click(".brand")
    page.click(".lang-switch [data-lang=en]")
    assert page.inner_text("h1") == "Croeso! Welcome to Y Sesiwn"
    assert page.inner_text("#surprise-sidebar") == "Surprise me"
    assert page.evaluate(VISIBLE_TEXT) == english


# GitHub's and other tools' own names, left in English in the Welsh guides.
ENGLISH_ON_PURPOSE = {"abcjs Quick Editor", "Add file → Create new file", "Commit changes…", "Propose changes",
                      "Create pull request", "Edit this file", "pull request", "Add to Home Screen",
                      "Windows, Mac, Linux", "F2 F GFG | AFD DFA | …",
                      # Welsh on the English pages too
                      "Diolch yn fawr", "Cymdeithas Offerynnau Traddodiadol Cymru"}


@pytest.mark.parametrize("path", [
    "?page=browse", "?page=browse&type=Jig&key=D%20major", "?page=notes&q=D%20G%20B%20D%20C%20B%20G%20A",
    "?tune=glandyfi&v=2", "?tune=machynlleth", "?tune=llancesau-trefaldwyn", "?page=map", "?page=offline",
    "?page=about", "?page=add", "?page=fix", "?page=contact&about=glandyfi-version-2",
    "?page=set&s=bne0o.6m42r~2&name=Nos%20Iau", "?page=sets",
])
def test_every_page_in_welsh(page, path):
    # Switching to Welsh on a page redraws it, with no English left: no sentence of the
    # English page shows up in the Welsh one, except the tunes' own words (titles,
    # sources, notes), which stay as written.
    import re
    ready = "typeof state !== 'undefined' && state.data && document.querySelector('#main h1') && !document.querySelector('#main .loading')"
    page.goto_site(path)
    page.wait_for_function(ready)
    english = page.evaluate(VISIBLE_TEXT)
    data = page.evaluate("JSON.stringify(state.data)")
    page.click(".lang-switch [data-lang=cy]")
    page.wait_for_function(f"document.querySelector('#main').lang === 'cy' && {ready}")
    welsh = page.evaluate(VISIBLE_TEXT)
    fragments = {f.strip() for f in re.split(r"[.:;?!()\n]", english) if len(f.strip()) >= 12}
    tune_words = lambda f: re.sub(r" · \d+$", "", f) in data  # e.g. a type, "Pibddawns · 29"
    left = [f for f in fragments if f in welsh and not tune_words(f) and f not in ENGLISH_ON_PURPOSE]
    assert len(fragments) > 5 and not left, left


def test_welsh_browser_gets_welsh(browser, site):
    context = browser.new_context(locale="cy-GB", service_workers="block")
    page = context.new_page()
    page.goto(site)
    page.wait_for_selector("h1")
    assert page.inner_text("h1") == "Croeso i'r Sesiwn!"
    context.close()


@pytest.mark.parametrize("user_agent, touch, says", [
    ("Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",
     False, "File → Add to Dock"),
    ("Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:130.0) Gecko/20100101 Firefox/130.0", False, "Firefox can't install"),
    ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0 Safari/537.36",
     False, "install icon at the right-hand end of the address bar"),
    ("Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0 Mobile Safari/537.36",
     True, "Add to Home screen"),
    ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1",
     True, "Add to Home Screen"),
])
def test_install_card(browser, site, user_agent, touch, says):
    # How to install depends on the device and browser; the card should say the right thing.
    context = browser.new_context(user_agent=user_agent, has_touch=touch, service_workers="block")
    page = context.new_page()
    page.goto(site)
    assert says in page.locator(".offline-card").inner_text()
    context.close()


def test_install_button(page):
    # Chrome and Edge offer their own install dialog; the card's button opens it.
    page.goto_site()
    page.evaluate("""() => { const e = new Event("beforeinstallprompt");
      e.prompt = () => { window.prompted = true; }; e.userChoice = Promise.resolve({ outcome: "accepted" });
      window.dispatchEvent(e); }""")
    page.click("text=Install the app")
    assert page.evaluate("window.prompted")


def test_works_offline(browser, site):
    context = browser.new_context()  # service worker allowed
    page = context.new_page()
    page.goto(site)
    page.wait_for_function("navigator.serviceWorker.controller !== null", timeout=30000)
    context.set_offline(True)
    page.goto(site + "?tune=glandyfi")
    page.wait_for_selector(".score .abcjs-staff")
    assert page.locator(".score .abcjs-note").count() > 20
    # A tune's own page isn't kept offline: the app stands in for it.
    page.goto(site + "alaw/llancesau-trefaldwyn/?v=1")
    page.wait_for_selector(".score .abcjs-staff")
    assert page.inner_text("main h1") == "Llancesau Trefaldwyn"
    page.click(".sidebar-links a[href='?page=map']")
    page.wait_for_selector(".wales-map circle")
    assert page.url == site + "?page=map"
    context.close()


def test_new_version_straight_away(browser, site):
    # Someone who has used the site before opens a link after an update: online, they get
    # the new version at once, not their saved copy (which may not know a new kind of
    # link); offline, the saved copy.
    from conftest import ROOT
    app = ROOT / "_site" / "app.js"
    original = app.read_text(encoding="utf-8")
    context = browser.new_context()  # service worker allowed
    page = context.new_page()
    try:
        page.goto(site)
        page.wait_for_function("navigator.serviceWorker.controller !== null", timeout=30000)
        app.write_text(original + "\nwindow.newVersion = true;\n", encoding="utf-8")  # a deploy
        page.goto(site + "?set=5A3V~h&n=Nos%20Iau")
        page.wait_for_selector(".set-list li")
        assert page.evaluate("window.newVersion") is True
        context.set_offline(True)
        page.goto(site + "?set=5A3V~h&n=Nos%20Iau")
        page.wait_for_selector(".set-list li")
        assert page.evaluate("window.newVersion") is None  # offline: the saved copy
    finally:
        app.write_text(original, encoding="utf-8")
        context.close()


def test_tune_page_address(page, site):
    # Each tune has its own page, alaw/<folder>/, which opens straight into the app.
    failed = []
    page.on("response", lambda r: failed.append(r.url) if r.status >= 400 else None)
    page.on("requestfailed", lambda r: failed.append(r.url))
    page.goto(site + "alaw/glandyfi/?v=2")
    page.wait_for_selector(".score .abcjs-staff")
    assert page.inner_text("main h1") == "Glandyfi"
    assert page.locator(".versions a.active span").inner_text() == "Version 2"
    assert failed == []  # every file found from two folders down
    # Links from it lead back to the site's root, and to the other tunes' own pages.
    page.click(".versions a >> nth=0")
    assert page.url == site + "alaw/glandyfi/"
    page.click(".card.place a")
    page.wait_for_selector(".place-list a")
    assert page.url == site + "?page=map"
    page.click(".place-list a:text-is('Machynlleth')")
    page.wait_for_selector(".score .abcjs-staff")
    assert page.url == site + "alaw/machynlleth/"
    page.reload()  # a real page: reloading (or sharing the link) works
    page.wait_for_selector(".score .abcjs-staff")
    assert page.inner_text("main h1") == "Machynlleth"
    page.go_back()
    page.wait_for_selector(".place-list a")
    assert failed == []


@pytest.mark.parametrize("old, new", [
    ("?tune=glandyfi", "alaw/glandyfi/"),
    ("?tune=glandyfi&v=2", "alaw/glandyfi/?v=2"),
    ("?tune=glandyfi-version-2", "alaw/glandyfi/?v=2"),  # a version's own folder
])
def test_old_tune_links(page, site, old, new):
    page.goto_site(old)
    page.wait_for_selector(".score .abcjs-staff")
    assert page.url == site + new


def fiddle_recording(path, notes, seconds_per_note=0.13, rate=48000):
    """A made-up fiddle (harmonics, vibrato) playing MIDI `notes` at reel speed, with
    silence around it and a little noise: a stand-in for the microphone."""
    rng = random.Random(1)
    samples = [0.0] * int(2.0 * rate)
    for midi in notes:
        f, n = 440 * 2 ** ((midi - 69) / 12), int(seconds_per_note * rate)
        for i in range(n):
            t = i / rate
            wobble = 1 + 0.006 * math.sin(2 * math.pi * 5.5 * t)
            envelope = min(1, t / 0.01) * min(1, (n - i) / (0.005 * rate))
            samples.append(envelope * sum(math.sin(2 * math.pi * f * k * wobble * t) / k for k in (1, 2, 3, 4, 5)) * 0.3)
    samples += [0.0] * int(3.2 * rate)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"".join(struct.pack("<h", int(20000 * (x + rng.gauss(0, 0.004)))) for x in samples))


def test_microphone(playwright_instance, site, tmp_path):
    # Machynlleth's first ten notes, played a tone higher than written, fast.
    notes = [71, 72, 74, 76, 74, 72, 71, 72, 71, 69]
    fiddle_recording(tmp_path / "fiddle.wav", [n + 2 for n in notes])
    browser = playwright_instance.chromium.launch(args=[
        "--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream",
        f"--use-file-for-fake-audio-capture={tmp_path / 'fiddle.wav'}%noloop",
    ])
    page = browser.new_context(service_workers="block", permissions=["microphone"]).new_page()
    # From the home page: "Play it to me" opens the notes page and starts listening.
    page.goto(site)
    page.click("button.listen-start")
    page.wait_for_selector("button.listen.on")
    page.wait_for_function("!document.querySelector('button.listen').classList.contains('on')", timeout=30000)
    heard = page.input_value("#notes-search")
    assert heard == "C# D E F# E D C# D C# B"
    assert page.locator(".notes-results li a").first.inner_text() == "Machynlleth"
    # The previews (skipped while listening, so no notes are missed) appear once it stops.
    page.wait_for_selector(".notes-results .preview .abcjs-staff")
    browser.close()


# ---- Practice: parts, looping, speed-up, count-in, click, tablature ------------------

@pytest.mark.parametrize("slug, parts", [("glandyfi", 2), ("machynlleth", 4), ("ffaniglen", 2), ("morgawr", 3)])
def test_loop_parts(page, slug, parts):
    page.goto_site(f"?tune={slug}")
    page.wait_for_selector(".score .abcjs-staff")
    options = page.eval_on_selector_all("#loop-select option", "os => os.map((o) => o.textContent)")
    assert options == ["The whole tune"] + [f"Part {chr(65 + i)}" for i in range(parts)]
    assert not page.locator(".speed-up").is_visible()  # only when a part is looped
    page.select_option("#loop-select", "0")
    assert page.locator(".speed-up").is_visible()


def test_loop_part_and_speed_up(browser, site):
    # Loop Glandyfi's part B slowly, speeding up: each time playback reaches the end of
    # the tune it comes back to part B (not A), 5% faster.
    context = browser.new_context(service_workers="block")
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(site + "?tune=glandyfi")
    page.wait_for_selector(".score .abcjs-staff")
    page.fill("#tempo", "60")
    page.dispatch_event("#tempo", "change")
    page.select_option("#loop-select", "1")
    page.check("text=Speed up each time")
    page.click(".abcjs-midi-start")
    page.wait_for_function("document.querySelector('.abcjs-note_playing') && state.synth.timer")
    for bpm in [63, 66]:
        # Jump to just before the end of the tune and wait to come back round.
        page.evaluate("() => { const e = state.synth.timer.noteTimings.filter((e) => e.type === 'event'); "
                      "state.synth.seek((e.at(-1).milliseconds - 800) / 1000, 'seconds'); }")
        page.wait_for_function(f"document.querySelector('.speed-note').textContent === 'now {bpm} bpm'", timeout=15000)
        # Back in part B (not part A), still playing.
        page.wait_for_function(f"(() => {{ const n = document.querySelector('.abcjs-note_playing'); "
                               f"return n && state.synth.isStarted && "
                               f"[...document.querySelectorAll('.score .abcjs-note')].indexOf(n) >= 30; }})()", timeout=15000)
    page.click(".abcjs-midi-start")  # pause
    assert not errors, errors
    context.close()


def test_count_in_and_click(page):
    page.goto_site("?tune=glandyfi")
    page.wait_for_selector(".score .abcjs-staff")
    drum = """() => { const p = { ...AUDIO_PARAMS, ...clickParams(state.synth.visualObj, state.bySlug.get('glandyfi')) };
      const [melody, , drums] = state.synth.visualObj.setUpAudio(p).tracks.map((t) => t.filter((e) => e.cmd === 'note'));
      return { melodyStarts: melody[0].start, drums: drums ? drums.length : 0 }; }"""
    assert page.evaluate(drum)["drums"] == 0
    page.check("text=Count-in")
    count_in = page.evaluate(drum)
    assert count_in["melodyStarts"] > 0 and count_in["drums"] == 2  # one 6/8 bar: two dotted-crotchet clicks
    page.check("text=Click")
    assert page.evaluate(drum)["drums"] > 50  # a click on every beat of the tune


@pytest.mark.parametrize("tab, first", [("mandolin", "0"), ("guitar", "0")])
def test_tablature(page, tab, first):
    # Glandyfi starts on D above middle C: the open D string on a mandolin and on a guitar.
    page.goto_site("?tune=glandyfi")
    page.wait_for_selector(".score .abcjs-staff")
    page.select_option("#tab-select", tab)
    page.wait_for_function("document.querySelectorAll('.score .abcjs-tab-number, .score [data-name=\"tabNumber\"]').length > 50")
    numbers = page.evaluate("[...document.querySelectorAll('.score svg text')].map((t) => t.textContent).filter((t) => /^\\d+$/.test(t))")
    assert numbers[0] == first


# ---- Report a problem, browse by key -------------------------------------------------

def test_report_link(page):
    # One way to report a problem: the contact form, with the tune (and version) filled in.
    page.goto_site("alaw/glandyfi/?v=2")
    page.wait_for_selector(".score .abcjs-staff")
    assert page.locator(".report-line a").count() == 1
    page.click("a.report")
    page.wait_for_selector(".email-form")
    assert page.input_value("[name=subject]") == "About Glandyfi (version 2)"


def test_tune_details(page):
    # The key and the arranger are on the key menu and the score, so not repeated in
    # Details; the source stays, as its address.
    page.goto_site("alaw/glandyfi/")
    page.wait_for_selector(".score .abcjs-staff")
    labels = page.locator(".tune-side .card dt").all_inner_texts()
    assert "Key" not in labels and "Composer / arranger" not in labels
    assert page.inner_text(".tune-side .card dd a") == "http://alawoncymru.com/alawon/Tunes/SetyDwr/SetYDwr.html"


# ---- Sending a tune, the contact page ---------------------------------------------------

# Split up here too, so the tests don't put the address in the repository either.
ADDRESS = "@".join(["helo", ".".join(["ysesiwn", "cymru"])])

CATCH_MAIL = "window.openMail = (url) => { window.sentMail = url; }"


def sent_mail(page):
    from urllib.parse import parse_qs, unquote, urlparse
    url = page.evaluate("window.sentMail")
    assert url.startswith("mailto:")
    parts = urlparse(url)
    query = parse_qs(parts.query)
    return unquote(parts.path), query["subject"][0], query["body"][0]


def test_send_a_tune(page):
    page.goto_site("?page=add")
    page.wait_for_selector(".send-tune form")
    # The form first, then the GitHub way (without the note that sends GitHub readers here).
    assert page.locator("main h2").first.inner_text() == "Send us a tune"
    assert page.locator("main h2", has_text="Or add it yourself on GitHub").count() == 1
    assert page.locator("main h2", has_text="1. Write the tune in ABC").count() == 1
    assert "Not on GitHub" not in page.inner_text("main")
    page.evaluate(CATCH_MAIL)
    form = page.locator(".send-tune form")
    form.locator("[name=name]").fill("Codi'r Hwyl")
    form.locator("[name=type]").select_option("Jig")
    form.locator("[name=source]").fill("Learnt at the Aberystwyth session")
    abc = "X:1\nT:Codi'r Hwyl\nR:jig\nM:6/8\nL:1/8\nK:D\n|: DFA dAF | GBd gdB :|"
    form.locator("[name=abc]").fill(abc)
    page.wait_for_selector(".abc-preview .abcjs-note")
    assert page.locator(".abc-problem").inner_text() == ""
    # Nothing is sent until the permission box is ticked.
    form.locator("button[type=submit]").click()
    assert page.evaluate("window.sentMail") is None
    form.locator("[name=permission]").check()
    form.locator("button[type=submit]").click()
    to, subject, body = sent_mail(page)
    assert to == ADDRESS
    assert subject == "Y Sesiwn tune: Codi'r Hwyl"
    assert "Type: Jig" in body and "Where it comes from: Learnt at the Aberystwyth session" in body
    assert f"ABC:\n{abc}" in body
    # For anyone without an email app: the address and message to copy.
    assert ADDRESS in page.inner_text(".email-sent")
    assert page.locator(".email-sent button").all_inner_texts() == ["Copy the message", "Copy the address"]


def test_send_a_tune_without_abc(page):
    page.goto_site("?page=add")
    page.wait_for_selector(".send-tune form")
    page.evaluate(CATCH_MAIL)
    form = page.locator(".send-tune form")
    form.locator("[name=abc]").fill("T:Something\nABC def")
    page.wait_for_function("document.querySelector('.abc-problem').textContent.includes('K:')")
    form.locator("[name=abc]").fill("")
    form.locator("[name=name]").fill("Y Deryn Du")
    form.locator("[name=source]").fill("My grandmother")
    form.locator("[name=permission]").check()
    form.locator("button[type=submit]").click()
    _, _, body = sent_mail(page)
    assert "No ABC: I've attached a photo or recording." in body and "Type: not sure" in body


def test_contact_page(page):
    page.goto_site("?tune=glandyfi&v=2")
    page.click("a.report")
    page.wait_for_selector(".email-form")
    assert page.input_value("[name=subject]") == "About Glandyfi (version 2)"
    page.evaluate(CATCH_MAIL)
    page.fill("[name=message]", "Bar 3 of the B part sounds wrong to me.")
    page.click(".email-form button[type=submit]")
    to, subject, body = sent_mail(page)
    assert to == ADDRESS and subject == "Y Sesiwn: About Glandyfi (version 2)"
    assert body.startswith("Bar 3 of the B part") and "https://ysesiwn.cymru/alaw/glandyfi/?v=2" in body
    # From the sidebar: no tune, no subject needed.
    page.click(".sidebar-links a[href='?page=contact']")
    page.wait_for_selector(".email-form")
    page.evaluate(CATCH_MAIL)
    page.fill("[name=message]", "Diolch!")
    page.click(".email-form button[type=submit]")
    assert sent_mail(page)[1:] == ("Y Sesiwn: a message", "Diolch!\n")


def test_address_is_hidden(page, site):
    # Not in any file of the site or the repository, nor in a page until someone sends.
    from conftest import ROOT
    found = []
    for path in ROOT.rglob("*"):
        if ".git" in path.parts or not path.is_file() or path.stat().st_size > 5_000_000:
            continue
        if ADDRESS.encode() in path.read_bytes():
            found.append(str(path.relative_to(ROOT)))
    assert found == []
    for path in ["", "?page=add", "?page=contact", "?page=about"]:
        page.goto_site(path)
        page.wait_for_selector("main h1")
        assert ADDRESS not in page.content()


# ---- QR code ---------------------------------------------------------------------------------

@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_qr_code(browser, site, scheme):
    # The QR code opens this tune (and version): read back from a screenshot, as a phone would.
    import io
    import zxingcpp
    from PIL import Image
    context = browser.new_context(service_workers="block", color_scheme=scheme)
    page = context.new_page()
    requests = []
    page.on("request", lambda r: requests.append(r.url))
    page.goto(site + "alaw/glandyfi/?v=2")
    page.wait_for_selector(".score .abcjs-staff")
    assert not [u for u in requests if "qrcode" in u]  # only loaded when asked for
    page.click(".qr-button")
    page.wait_for_selector("dialog.qr-dialog[open] svg.qr")
    image = Image.open(io.BytesIO(page.locator("dialog svg.qr").screenshot()))
    assert [r.text for r in zxingcpp.read_barcodes(image)] == ["https://ysesiwn.cymru/alaw/glandyfi/?v=2"]
    page.keyboard.press("Escape")
    page.wait_for_selector("dialog.qr-dialog", state="detached")
    page.click(".qr-button")  # again, and closed with its button
    page.click("dialog.qr-dialog button:text-is('Close')")
    page.wait_for_selector("dialog.qr-dialog", state="detached")
    context.close()


# ---- Sets -------------------------------------------------------------------------------

def test_set_from_tune_pages(page):
    # "Add to set" on a tune adds it, in the key chosen; the set page arranges them, and
    # every change is in its address (and kept in this browser).
    for path, key in [("alaw/llancesau-trefaldwyn/", None), ("alaw/glandyfi/?v=2", "2"), ("alaw/nyth-y-gog/", None)]:
        page.goto_site(path)
        page.wait_for_selector(".score .abcjs-staff")
        if key:
            page.select_option("#key-select", key)
        page.click(".add-to-set")
    assert "(3 tunes)" in page.inner_text(".add-status")
    page.click(".add-status a")
    page.wait_for_selector(".set-list li")
    assert page.locator(".set-list li > a").all_inner_texts() == ["Llancesau Trefaldwyn", "Glandyfi", "Nyth y Gog"]
    assert "?set=5A3V~h7o&n=My%20set&my=" in page.url  # Glandyfi (version 2) up two: ~h
    assert page.locator(".set-list li").nth(1).locator("select").input_value() == "2"
    page.locator(".set-list li").nth(1).locator("button[aria-label='Move up']").click()
    page.locator(".set-list li").nth(2).locator("button[aria-label^='Remove']").click()
    page.fill(".set-name", "Nos Iau")
    page.press(".set-name", "Tab")
    assert page.locator(".set-list li > a").all_inner_texts() == ["Glandyfi", "Llancesau Trefaldwyn"]
    assert "?set=3V~h5A&n=Nos%20Iau" in page.url
    kept = page.evaluate("JSON.parse(localStorage.getItem('sets'))")
    assert [(x["name"], x["c"]) for x in kept] == [("Nos Iau", "3V~h5A")]
    page.locator(".set-paper").first.scroll_into_view_if_needed()
    page.wait_for_selector(".set-paper svg")
    # My sets lists it; it can be deleted there.
    page.click(".sidebar-links a[href='?page=sets']")
    assert page.locator(".set-list-mine li a").all_inner_texts() == ["Nos Iau"]
    assert "doesn't come with ready-made sets" in page.inner_text(".sets-own")  # make your own
    page.on("dialog", lambda d: d.accept())
    page.click(".set-list-mine button:text-is('Delete')")
    assert page.locator(".set-list-mine").count() == 0


def test_add_to_set_by_search(page):
    # On a set's page: type part of a name, press Enter, and it's added; the box is ready
    # for the next one straight away. Typos are forgiven, and the arrow keys pick another match.
    page.goto_site("?page=sets")
    page.click("text=New set")
    page.wait_for_selector("#set-add")
    assert page.locator("text=No tunes yet").is_visible()
    page.fill("#set-add", "llancesau")
    page.wait_for_selector("#set-add-list li")
    page.press("#set-add", "Enter")
    assert page.input_value("#set-add") == "" and page.evaluate("document.activeElement.id") == "set-add"
    page.keyboard.type("machynleth")  # a typo
    page.wait_for_selector("#set-add-list li")
    page.keyboard.press("Enter")
    page.keyboard.type("nyth y gog")
    page.wait_for_selector("#set-add-list li")
    second = page.locator("#set-add-list li").nth(1).inner_text()
    page.keyboard.press("ArrowDown")
    page.keyboard.press("Enter")
    assert page.locator(".set-list li > a").all_inner_texts() == ["Llancesau Trefaldwyn", "Machynlleth", second]
    assert page.inner_text(".set-added") == f"Added {second}."
    assert not page.locator("text=No tunes yet").is_visible()
    kept = page.evaluate("JSON.parse(localStorage.getItem('sets'))")
    assert len(kept[0]["c"]) == 6  # three tunes, two characters each


@pytest.mark.parametrize("link", [
    "?set=3V~h5Azz&n=Nos%20Iau",                      # zz: a code no tune has
    "?page=set&s=6m42r~2.bne0o.zzzzz&name=Nos%20Iau",  # the first form of set links still works
])
def test_shared_set(browser, site, link):
    # A set's link, opened on someone else's phone: the same tunes, in the same keys, to save.
    context = browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True,
                                  service_workers="block")
    page = context.new_page()
    page.goto(site + link)
    page.wait_for_selector(".set-list li")
    assert page.inner_text("main h1") == "Nos Iau"
    assert page.locator(".set-list li > a").all_inner_texts() == ["Glandyfi", "Llancesau Trefaldwyn"]
    assert "1 tune in this set isn't on the site any more" in page.inner_text("main")  # an unknown code
    assert page.locator(".set-list li select").first.input_value() == "2"
    page.click("text=Save to my sets")
    page.wait_for_selector(".set-name")
    assert "&my=" in page.url
    assert page.evaluate("JSON.parse(localStorage.getItem('sets'))[0].c") == "3V~h5A"
    assert "?set=3V~h5A&n=Nos%20Iau" in page.url  # an older link is shown in the new form
    context.close()


def test_copy_set_as_a_list(browser, site):
    # "Copy as a list": the name, a bullet for each tune (version and key), and the link.
    context = browser.new_context(service_workers="block", permissions=["clipboard-read", "clipboard-write"])
    page = context.new_page()
    page.goto(site + "?set=3V~h5A&n=Nos%20Iau")
    page.wait_for_selector(".set-list li")
    page.click("text=Copy as a list")
    assert page.evaluate("navigator.clipboard.readText()") == (
        "Nos Iau\n"
        "• Glandyfi (version 2): A major\n"
        "• Llancesau Trefaldwyn (version 1): D major\n"
        "https://ysesiwn.cymru/?set=3V~h5A&n=Nos%20Iau")
    assert page.inner_text(".set-actions") .count("✓ List copied") == 1
    page.click(".lang-switch [data-lang=cy]")
    page.wait_for_selector(".set-list li")
    page.click("text=Copïo fel rhestr")
    assert "• Glandyfi (fersiwn 2): A fwyaf" in page.evaluate("navigator.clipboard.readText()")
    context.close()


def test_set_codes_that_change(page):
    # A tune without a number when its link was made (".<short_id>") still opens once it
    # has one; sets kept in the browser in the first form are converted.
    page.goto_site()
    short_id = page.evaluate("state.bySlug.get('machynlleth').id")
    page.goto_site(f"?set=.{short_id}~a5A&n=Old")
    page.wait_for_selector(".set-list li")
    assert page.locator(".set-list li > a").all_inner_texts() == ["Machynlleth", "Llancesau Trefaldwyn"]
    assert page.locator(".set-list li select").first.input_value() == "-5"
    assert "?set=5Z~a5A&n=Old" in page.url
    page.evaluate("""localStorage.setItem('sets', JSON.stringify([{ id: 'old1', name: 'Old', s: '6m42r~2.bne0o' }]))""")
    page.goto_site("?page=sets")
    assert page.locator(".set-list-mine li a").all_inner_texts() == ["Old"]
    assert page.evaluate("JSON.parse(localStorage.getItem('sets'))[0]") == {"id": "old1", "name": "Old", "c": "3V~h5A"}


def test_big_set(page, site):
    # 100 tunes: a link of about 300 characters, a QR code that scans, and music drawn
    # only as it comes into view.
    import io
    import zxingcpp
    from PIL import Image
    page.goto_site()
    codes = page.evaluate("state.data.tunes.slice(0, 100).map((t, i) => t.code + (i % 3 ? '' : '~h')).join('')")
    page.goto_site(f"?set={codes}&n=Big")
    page.wait_for_selector(".set-list li")
    assert page.locator(".set-list li").count() == 100
    assert page.locator(".set-paper svg").count() == 0
    page.locator(".set-paper").first.scroll_into_view_if_needed()
    page.wait_for_selector(".set-paper svg")
    assert 0 < page.locator(".set-paper svg").count() < 30
    page.evaluate("window.scrollTo(0, 0)")
    page.click(".set-actions button:text-is('QR code')")
    page.wait_for_selector("dialog svg.qr")
    link = f"https://ysesiwn.cymru/?set={codes}&n=Big"
    assert len(link) < 320
    image = Image.open(io.BytesIO(page.locator("dialog svg.qr").screenshot()))
    assert [r.text for r in zxingcpp.read_barcodes(image)] == [link]


# ---- Visit counts --------------------------------------------------------------------------

def test_visit_counts(page):
    # Each page is counted (with a stand-in for GoatCounter), with only the safe parts of
    # its address: not the notes typed into the search, nor the tune a message is about.
    page.add_init_script("window.goatcounter = { count: (view) => (window.counted ||= []).push(view) }")
    page.goto_site("?page=contact&about=glandyfi-version-2")
    page.wait_for_selector(".email-form")
    page.click(".lang-switch [data-lang=cy]")
    counted = page.evaluate("window.counted")
    assert counted == [{"path": "/?page=contact", "title": "Contact · Y Sesiwn"},
                       {"path": "language-cy", "title": "Switched to Welsh", "event": True},
                       {"path": "/?page=contact", "title": "Cysylltu · Y Sesiwn"}]
    page.goto_site("?page=notes&q=D%20G%20B%20D%20C%20B%20G%20A")
    assert page.evaluate("window.counted") == [{"path": "/?page=notes", "title": "Canfod alaw o'i nodau · Y Sesiwn"}]


def test_visit_counts_in_order(page):
    page.add_init_script("window.goatcounter = { count: (view) => (window.counted ||= []).push(view.path) }")
    page.goto_site()
    page.wait_for_selector(".features")
    page.click(".sidebar-links a[href='?page=browse']")
    page.click(".pills button[data-type='Jig']")  # a filter isn't a new page
    page.click(".tune-list a >> nth=0")
    page.wait_for_selector(".score .abcjs-staff")
    slug = page.evaluate("addressTune()")
    assert page.evaluate("window.counted") == ["/", "/?page=browse", f"/alaw/{slug}/"]


def test_no_counting_away_from_the_live_site(page):
    # Only ysesiwn.cymru loads the counter: the tests (and anyone's own copy) send nothing.
    requests = []
    page.on("request", lambda r: requests.append(r.url))
    page.goto_site("?tune=glandyfi")
    page.wait_for_selector(".score .abcjs-staff")
    assert page.locator("script[src*='goatcounter'], script[src*='zgo.at']").count() == 0
    assert not [u for u in requests if "goatcounter" in u or "zgo.at" in u]
    assert page.context.cookies() == []


def test_browse_by_key(page):
    page.goto_site("?page=browse")
    page.click(".pills.keys button[data-key='D major']")
    in_d = page.locator(".tune-list li").count()
    assert in_d > 50 and "in D major" in page.locator("p.caption", has_text="in D major").inner_text()
    page.click(".pills button[data-type='Jig']")  # jigs in D major
    jigs_in_d = page.locator(".tune-list li").count()
    assert 0 < jigs_in_d < in_d
    assert page.locator("p.caption", has_text="jigs in D major").inner_text().startswith(str(jigs_in_d))
    # Key counts follow the type, and keys with no jigs are greyed out.
    assert page.locator(".pills.keys button[data-key='D major'] span").inner_text() == str(jigs_in_d)
    assert page.locator(".pills.keys button:disabled").count() > 0
    # The choice is kept in the address, so "the jigs in D" can be shared.
    assert "type=Jig" in page.url and "key=D+major" in page.url
    page.goto_site("?page=browse&type=Jig&key=D%20major")
    assert page.locator(".tune-list li").count() == jigs_in_d
    page.click(".pills.keys button[data-key='D major']")  # clicking again clears the key
    assert page.locator(".tune-list li").count() > jigs_in_d
    assert "key=" not in page.url


# ---- Accessibility -------------------------------------------------------------------

@pytest.mark.parametrize("scheme", ["light", "dark"])
@pytest.mark.parametrize("width", [1300, 390])
def test_accessibility(browser, site, scheme, width):
    # The axe checker (the standard automated accessibility test): labels, contrast,
    # keyboard access, ARIA, headings, … on the main pages.
    from axe_playwright_python.sync_playwright import Axe
    axe = Axe()
    context = browser.new_context(service_workers="block", color_scheme=scheme, viewport={"width": width, "height": 900})
    page = context.new_page()
    problems = []
    for path in ["", "?page=browse", "?tune=glandyfi", "?tune=nyth-y-gog", "?page=map", "?page=offline", "?page=about", "?page=add",
                 "?page=contact", "?page=set&s=bne0o.6m42r~2&name=Nos%20Iau", "?page=notes&q=D%20G%20B%20D%20C%20B%20G%20A", "cy:", "cy:?tune=glandyfi"]:
        if path.startswith("cy:"):  # in Welsh: the home page, and a page with the not-in-Welsh-yet note
            page.evaluate("localStorage.setItem('lang', 'cy')")
        page.goto(site + path.removeprefix("cy:"))
        # No fade-in: text caught half-faded would count as low contrast.
        page.add_style_tag(content="*, *::before, *::after { animation: none !important; transition: none !important; }")
        page.wait_for_function("typeof state !== 'undefined' && state.data && !document.querySelector('#main .loading')")
        for v in axe.run(page).response["violations"]:
            problems.append(f"{path or 'home'}: {v['id']} ({v['help']}) at {[n['target'] for n in v['nodes'][:3]]}")
    context.close()
    assert not problems, "\n".join(problems)



def test_tablature_choices(page):
    page.goto_site("?tune=glandyfi")
    options = page.eval_on_selector_all("#tab-select option", "os => os.map((o) => o.value)")
    assert options == ["none", "mandolin", "guitar", "whistle-D", "whistle-C", "whistle-G", "whistle-Bb"]


# ---- The notes page ---------------------------------------------------------------

def test_notes_page(page):
    # From the home page's invitation, typed notes are searched and kept in the address.
    page.goto_site()
    page.click("text=Tap or type the notes")
    page.fill("#notes-search", "D G B D C B G A")
    assert "q=D%20G%20B%20D%20C%20B%20G%20A" in page.url
    assert page.locator(".notes-results li a").first.inner_text() == "Glandyfi"
    # The best matches show their opening bars, with a play button.
    page.wait_for_function("document.querySelectorAll('.notes-results .preview svg').length === 5")
    assert page.locator(".notes-results .preview-play").count() == 5


def test_notes_page_link(page):
    # A shared link opens with the notes filled in and the results shown.
    page.goto_site("?page=notes&q=G%20B%20D%20C%20B%20G%20A")
    assert page.input_value("#notes-search") == "G B D C B G A"
    assert page.locator(".notes-results li a").first.inner_text() == "Glandyfi"
    # And it's in the sidebar on every page.
    page.goto_site("?tune=glandyfi")
    page.click(".sidebar-links >> text=Find a tune by its notes")
    assert page.locator("h1").inner_text() == "Find a tune by its notes"



def test_every_chord_chart(page):
    # Every tune with chords gets a chart with a chord in every row, in its own key and
    # transposed (chord names like "Gmaj7/F#" or "B5" must survive both).
    page.goto_site()
    problems = page.evaluate("""() => {
      const problems = [];
      for (const tune of state.data.tunes.filter((t) => t.chords != null)) {
        for (const shift of [0, 2]) {
          let abc = stripFields(tune.abc, "SZBNAH");
          if (shift) abc = ABCJS.strTranspose(abc, ABCJS.renderAbc("*", abc), shift);
          const rows = [...chordChart(ABCJS.renderAbc("*", abc)[0]).children];
          if (!rows.length || rows.some((r) => !r.textContent.trim())) problems.push(`${tune.slug} (+${shift})`);
        }
      }
      return problems;
    }""")
    assert problems == []


def test_preview_can_be_stopped(page):
    # A result's play button becomes a stop button while its opening plays (issue #6).
    page.goto_site("?page=notes&q=D%20G%20B%20D%20C%20B%20G%20A")
    button = page.locator(".notes-results .preview-play").first
    page.wait_for_selector(".notes-results .preview .abcjs-staff")
    page.evaluate("""() => { window.__started = 0; const P = ABCJS.synth.CreateSynth;
      ABCJS.synth.CreateSynth = function () { const s = new P(); const start = s.start;
        s.start = function (...a) { window.__started++; return start.apply(this, a); }; return s; }; }""")
    button.click()
    assert button.inner_text() == "■" and button.get_attribute("aria-label").startswith("Stop")
    # It really plays: abcjs stops the synth itself while getting it ready, which must
    # not count as pressing stop.
    page.wait_for_function("window.__started === 1")
    page.wait_for_timeout(500)
    assert button.inner_text() == "■"
    button.click()
    assert button.inner_text() == "▶" and button.get_attribute("aria-label").startswith("Play")
    # Starting another preview stops the first.
    button.click()
    page.locator(".notes-results .preview-play").nth(1).click()
    assert button.inner_text() == "▶"
    assert page.locator(".notes-results .preview-play").nth(1).inner_text() == "■"


def test_browse_groups_are_labelled(page):
    # The type and key buttons are two separate groups, each with a label (issue #7).
    page.goto_site("?page=browse")
    assert page.locator(".pills-label").all_text_contents() == ["Type", "Key"]
    types = page.locator(".pills").first.bounding_box()
    keys = page.locator(".pills.keys").bounding_box()
    assert keys["y"] - (types["y"] + types["height"]) > 30


def test_chord_playback_next_to_the_player(page):
    # "Play: Tune only / Tune and chords / Chords only" is just under the player (issue #9).
    page.goto_site("?tune=glandyfi")
    page.wait_for_selector(".score .abcjs-inline-audio")
    assert page.locator(".score > .playback").count() == 1
    player = page.locator(".score .audio").bounding_box()
    choice = page.locator(".score > .playback").bounding_box()
    score = page.locator(".score .abcjs-staff").first.bounding_box()
    assert player["y"] < choice["y"] < score["y"]
    assert page.locator(".card.chords .segmented").count() == 0
    page.goto_site("?tune=cawl-cennin")  # no chords, no choice
    page.wait_for_selector(".score .abcjs-inline-audio")
    assert page.locator(".score > .playback").count() == 0


def test_damaged_storage_and_backing_up_sets(browser, site):
    # What's kept in the browser may be anything (edited by hand, an old bug): pages still
    # work, with whatever sets are usable. My sets offers every set's link to keep.
    context = browser.new_context(service_workers="block", permissions=["clipboard-read", "clipboard-write"])
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(site)
    page.evaluate("""() => {
      localStorage.setItem('sets', JSON.stringify([1, null, {id: 5}, {id: 'ok', c: '5A', name: 7}, {id: 'old', s: ''}]));
      localStorage.setItem('recent', '"not a list"'); }""")
    page.goto(site + "?page=sets")
    page.wait_for_selector(".set-list-mine li")
    assert page.locator(".set-list-mine li").count() == 2
    assert "My set\n· 1 tune" in page.inner_text(".set-list-mine")
    page.click(".copy-all-sets")
    copied = page.evaluate("navigator.clipboard.readText()")
    assert "My set\nhttps://ysesiwn.cymru/?set=5A&n=My%20set" in copied
    assert page.inner_text(".copy-all-sets") == "✓ Links copied"
    page.evaluate("localStorage.setItem('sets', '{\"not\": \"a list\"}')")
    page.goto(site + "?page=sets")
    page.wait_for_selector("text=No sets yet")
    assert page.locator(".copy-all-sets").count() == 0  # nothing to back up
    page.goto(site)
    page.wait_for_selector("#hero-search")
    context.close()
    assert not errors, errors


def test_tune_not_found(page, site):
    # A tune's old address (renamed, merged, mistyped) says so and offers the nearest names.
    page.goto_site("?tune=tros-y-garreg-hen")
    page.wait_for_selector(".not-found")
    assert page.inner_text("h1") == "Tune not found"
    assert "Tros y Garreg" in page.inner_text(".not-found")
    page.click(".not-found a >> text=Tros y Garreg")
    page.wait_for_selector(".score .abcjs-staff")
    assert page.url.endswith("/alaw/tros-y-garreg/")
    # Before the app is installed, GitHub Pages answers the address with 404.html, which
    # opens the app on that tune.
    import build_site
    not_found = (build_site.OUT / "404.html").read_text(encoding="utf-8")
    page.route("**/alaw/no-such-tune/", lambda route: route.fulfill(status=404, body=not_found, content_type="text/html"))
    page.goto(site + "alaw/no-such-tune/")
    page.wait_for_selector(".not-found, main h1:text('Tune not found')")
    assert page.url == site + "?tune=no-such-tune"
    assert "no-such-tune" in page.inner_text("main")


def test_touch_targets(browser, site):
    # On a phone, every control is at least 24px each way (WCAG 2.5.8); links inside text don't count.
    context = browser.new_context(viewport={"width": 320, "height": 640}, is_mobile=True, has_touch=True,
                                  service_workers="block")
    page = context.new_page()
    small = {}
    for path in ["", "alaw/tros-y-garreg/", "?set=3V~h5A&n=Nos%20Iau", "?page=sets", "?page=add", "?page=contact", "?page=browse"]:
        page.goto(site + path)
        page.wait_for_function("typeof state !== 'undefined' && state.data && document.querySelector('main').children.length")
        page.wait_for_timeout(300)
        found = page.evaluate("""() => [...document.querySelectorAll('button, a, select, input, summary')]
          .filter((e) => e.offsetParent && !e.closest('.visually-hidden, .segmented'))
          .filter((e) => !(e.tagName === 'A' && e.closest('p, li, dd, td, .caption')))
          .filter((e) => { const r = e.getBoundingClientRect(); return r.width < 24 || r.height < 24; })
          .map((e) => e.outerHTML.slice(0, 90))""")
        if found:
            small[path] = found
    context.close()
    assert not small, small


WAKE_LOCK = """
  window.wakeLog = [];
  Object.defineProperty(navigator, 'wakeLock', { value: { request: async () => {
    const lock = new EventTarget();
    lock.release = async () => { wakeLog.push('release'); lock.dispatchEvent(new Event('release')); };
    wakeLog.push('request');
    return lock;
  } } });
"""


def test_screen_stays_on_with_music(page, site):
    # With a tune or a set showing, the phone's screen doesn't dim; elsewhere it may.
    page.add_init_script(WAKE_LOCK)
    page.goto_site("alaw/tros-y-garreg/")
    page.wait_for_function("wakeLog.length === 1")
    page.click("a[href='?page=map']")
    page.wait_for_function("wakeLog.join() === 'request,release'")
    page.goto_site("?set=3V~h5A&n=Nos%20Iau")
    page.wait_for_function("wakeLog.join() === 'request'")
    page.click(".set-list a >> nth=0")  # from a set to one of its tunes: kept on
    page.wait_for_selector(".score .abcjs-staff")
    assert page.evaluate("wakeLog.join()") == "request"


def test_set_next_and_previous(browser, site):
    # Playing through a set: the arrow keys (or a page-turner pedal), the buttons along
    # the bottom, or a swipe move from one tune's music to the next.
    context = browser.new_context(viewport={"width": 390, "height": 700}, is_mobile=True, has_touch=True,
                                  service_workers="block")
    page = context.new_page()
    page.goto(site + "?set=3V~h5A5B&n=Nos%20Iau")
    page.wait_for_selector(".set-nav")
    # Each tune's top, below the bar along the top of a phone's screen.
    tops = """() => [...document.querySelectorAll('.set-tune')].map((x) =>
      Math.round(x.getBoundingClientRect().top - document.querySelector('.topbar').getBoundingClientRect().bottom))"""
    where = lambda: page.inner_text(".set-nav-where")
    assert where() == "3 tunes"
    assert page.is_disabled(".set-nav button >> nth=0")
    page.keyboard.press("ArrowRight")
    page.wait_for_function("document.querySelector('.set-nav-where').textContent.startsWith('1 / 3')")
    assert 0 <= page.evaluate(tops)[0] <= 10
    page.click("[aria-label='Next tune']")
    page.wait_for_function("document.querySelector('.set-nav-where').textContent.startsWith('2 / 3')")
    assert where() == "2 / 3 · Llancesau Trefaldwyn"
    assert 0 <= page.evaluate(tops)[1] <= 10
    page.evaluate("""() => {  // a swipe to the left, across the music
      const music = document.querySelector('.set-music');
      const at = (x) => [new Touch({ identifier: 1, target: music, clientX: x, clientY: 300 })];
      music.dispatchEvent(new TouchEvent('touchstart', { touches: at(300), changedTouches: at(300), bubbles: true }));
      music.dispatchEvent(new TouchEvent('touchend', { touches: [], changedTouches: at(150), bubbles: true }));
    }""")
    page.wait_for_function("document.querySelector('.set-nav-where').textContent.startsWith('3 / 3')")
    assert page.is_disabled("[aria-label='Next tune']")
    page.keyboard.press("ArrowLeft")
    page.wait_for_function("document.querySelector('.set-nav-where').textContent.startsWith('2 / 3')")
    # Typing in a box (the set's name, adding a tune) keeps the arrow keys for the text.
    page.focus("#set-add")  # (which scrolls up to it)
    before = page.evaluate("scrollY")
    page.keyboard.press("ArrowLeft")
    page.wait_for_timeout(100)
    assert page.evaluate("scrollY") == before
    context.close()


def test_set_next_before_the_rest_is_drawn(browser, site):
    # On a slow phone, Next can come before the music below has been drawn. The tune
    # jumped to still ends up at the top once it has: not pushed up past by the ones after.
    # (A tall screen, so that without the rest the page is too short to scroll it there.)
    context = browser.new_context(viewport={"width": 390, "height": 1000}, is_mobile=True, has_touch=True,
                                  service_workers="block")
    page = context.new_page()
    # The lazy drawing never gets round to anything by itself; the test does it, later.
    page.add_init_script("window.IntersectionObserver = class { observe() {} unobserve() {} disconnect() {} };")
    page.goto(site + "?set=3V~h5A5B&n=Nos%20Iau")
    page.wait_for_selector(".set-nav")
    page.keyboard.press("ArrowRight")
    page.click("[aria-label='Next tune']")
    page.evaluate("for (const paper of document.querySelectorAll('.set-paper')) paper.draw()")
    page.evaluate("dispatchEvent(new Event('scroll'))")
    page.wait_for_timeout(100)
    assert page.inner_text(".set-nav-where") == "2 / 3 · Llancesau Trefaldwyn"
    top = page.evaluate("""() => Math.round(document.querySelectorAll('.set-tune')[1].getBoundingClientRect().top
      - document.querySelector('.topbar').getBoundingClientRect().bottom)""")
    assert 0 <= top <= 10
    context.close()


def test_tunes_load_alongside_the_scripts(page, site):
    # index.html starts fetching tunes.json straight away, and the app uses that one copy.
    requests = []
    page.on("request", lambda r: requests.append(r.url) if r.url.endswith("tunes.json") else None)
    page.goto_site()
    page.wait_for_timeout(300)
    assert len(requests) == 1
    page.goto_site("alaw/tros-y-garreg/")  # a tune's page, with its ../../ base
    page.wait_for_timeout(300)
    assert requests[1:] == [site + "tunes.json"]
