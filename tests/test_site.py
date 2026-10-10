"""The site itself, in a headless browser: every tune draws, the searches find what
they should, and the chords, map, phone layout, offline copy and microphone work."""
import math
import random
import re
import struct
import wave

import pytest
from pathlib import Path

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
    "erddigan-caer-waen-version-2": "its third part is in 6/8",
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
    # The same in Peter Dunk's transcription of Davidson's 250 Welsh Airs.
    "hew-wraig-llanallgo": "bar 18 is three quavers short",
    "hoffedd-howell": "bar 21 is two quavers short",
    "sion-ab-ifan-version-2": "bar 6 is two quavers long",
    "the-damsels-of-cardigan": "bar 9 is a quaver long",
    "the-tune-of-morvydd-s-pipes": "bar 31 is a quaver long",
    "the-vale-of-clwyd": "bar 5 is a quaver short",
    "y-berllan": "bar 12 is a quaver long",
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


def test_your_sets_on_home(page):
    # The sets made here are on the home page too, newest first, three of them and then all.
    page.goto_site()
    page.evaluate("""() => localStorage.setItem('sets', JSON.stringify([
      {id: 'a1', name: 'Tuesday', c: '', updated: 3}, {id: 'a2', name: 'Class 2', c: '', updated: 1},
      {id: 'a3', name: 'Ffair', c: '', updated: 2}, {id: 'a4', name: 'Old', c: '', updated: 0}]))""")
    page.goto_site()
    assert page.locator(".recent a").all_text_contents() == [
        "Tuesday · 0 tunes", "Ffair · 0 tunes", "Class 2 · 0 tunes", "All 4 sets"]


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
    page.open_tools()
    page.wait_for_selector(".chart .bar")
    # Two chords in a bar each get half of it (G on beat 1, D on beat 2 of 6/8).
    halves = page.evaluate("""() => [...document.querySelectorAll('.chart .beats')].filter((b) => b.children.length === 2)
      .map((b) => Math.round(100 * (b.children[1].getBoundingClientRect().left - b.getBoundingClientRect().left) / b.getBoundingClientRect().width))""")
    assert halves and all(48 <= h <= 52 for h in halves)
    assert page.locator(".chart .repeat-start").count() == 2 and page.locator(".chart .repeat-end").count() == 2
    # Chords on the score only when asked for; playback options set abcjs's switches.
    assert page.locator(".score .hide-chords").count() == 1
    page.check("text=Chords on the sheet music")
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
    page.click("text=Print / save")
    page.click(f"[id^=print-menu] >> text='{mode}'")
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
    page.click("text=Print / save")
    assert page.locator("[id^=print-menu]").is_visible()
    page.mouse.click(5, 900)  # clicking elsewhere closes it
    assert not page.locator("[id^=print-menu]").is_visible()
    page.goto_site("?tune=cawl-cennin")  # no chords: no chord printing, but still saving
    page.click("text=Print / save")
    assert page.locator("[id^=print-menu] button").all_inner_texts() == ["Print the sheet music", "Save as ABC", "Save as MIDI"]


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
    page.open_tools()
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
    f = lambda midi, instrument="whistle-D": page.evaluate(
        "([m, w]) => { const r = fingering(m, FINGERED[w]); return r && [r.holes, r.high, ...(r.up ? ['up'] : [])]; }", [midi, instrument])
    assert f(62) == ["●●●●●●", False]   # D: all covered
    assert f(66) == ["●●●●○○", False]   # F sharp
    assert f(73) == ["○○○○○○", False]   # C sharp: all open
    assert f(74) == ["●●●●●●", True]    # D, second octave: blow harder
    assert f(72) == ["○●●○○○", False]   # C natural, cross-fingered
    assert f(61) is None and f(86) is None  # below and above a D whistle
    assert f(60, "whistle-C") == ["●●●●●●", False]
    assert f(60, "recorder") == ["●●●●●●●●", False]  # recorder: thumb and all seven covered
    assert f(65, "recorder") == ["●●●●●○●●", False]  # F, forked
    assert f(76, "recorder") == ["◐●●●●●○○", False]  # E, second octave: thumb pinched
    assert f(59, "recorder") == ["●●○○○○○○", False, "up"] and f(88, "recorder") is None  # too low: an octave up
    # Lined up under their notes, a tied note's continuation included; rests take none.
    rows = page.evaluate("""() => { const v = ABCJS.renderAbc('*', withFingerings('X:1\\nM:6/8\\nL:1/8\\nK:D\\nD3- D2 E | F2 z G z A|', FINGERED['whistle-D']))[0];
      return v.lines[0].staff[0].voices[0].filter((e) => e.el_type === 'note' && !e.rest).map((n) => (n.lyric || []).map((l) => l.syllable).join('')); }""")
    assert rows == ["●●●●●●", "", "●●●●●○", "●●●●○○", "●●●○○○", "●●○○○○"]


# For a learner who doesn't read the stave: a line under the music, the way to the tablature
# menu (opening the practice tools), gone once any tablature has been chosen, for good.
def test_tablature_invite(page):
    page.goto_site("alaw/llancesau-trefaldwyn/")
    page.wait_for_selector(".score .abcjs-staff")
    assert page.locator(".practice-tools").evaluate("d => !d.open")
    page.click(".tab-invite .link-button")
    page.wait_for_function("document.activeElement.id === 'tab-select'")
    assert page.locator(".practice-tools").evaluate("d => d.open")
    page.select_option("#tab-select", "whistle-D")
    assert page.locator(".tab-invite").is_hidden()
    page.select_option("#tab-select", "none")
    page.reload()
    page.wait_for_selector(".score .abcjs-staff")
    assert page.locator(".tab-invite").is_hidden()


def test_whistle_on_a_tune(page):
    page.goto_site("alaw/llancesau-trefaldwyn/")
    page.open_tools()
    page.wait_for_selector(".score .abcjs-staff")
    assert page.locator(".fingering-key").is_hidden()
    page.select_option("#tab-select", "whistle-D")
    page.wait_for_selector(".score .abcjs-lyric")
    assert page.locator(".fingering-key").is_visible()
    lyrics = lambda: "".join(page.locator(".score .abcjs-lyric").all_text_contents())
    in_d = lyrics()
    assert "?" not in in_d and "+" in in_d  # all on a D whistle, some in the second octave
    page.select_option("#key-select", "-5")  # down to A: its lowest notes are below the whistle
    page.wait_for_function("(before) => [...document.querySelectorAll('.score .abcjs-lyric')].map((e) => e.textContent).join('') !== before", arg=in_d)
    assert "?" in lyrics()
    in_a = lyrics()
    page.select_option("#tab-select", "recorder")  # its lowest note is C: in A, some go an octave up
    page.wait_for_function("(before) => [...document.querySelectorAll('.score .abcjs-lyric')].map((e) => e.textContent).join('') !== before", arg=in_a)
    assert "?" not in lyrics() and "8va" in lyrics()
    assert page.locator(".score .octave-up").count() > 0  # "8va", in red
    # Drawn as circles, thumb | left hand | right hand: a wider step between the hands
    gaps = page.evaluate("""() => [...document.querySelector('.score g.holes').querySelectorAll('circle')]
      .map((c) => +c.getAttribute('cy')).map((y, i, all) => i ? Math.round(y - all[i - 1]) : 0).slice(1)""")
    assert len(gaps) == 7 and gaps[0] == gaps[3] > gaps[1] == gaps[2] == gaps[4]
    page.select_option("#key-select", "0")  # back to D: all where they're written
    page.wait_for_function("() => !document.querySelector('.score .octave-up')")
    assert "recorder" in page.locator(".fingering-key").text_content()
    page.select_option("#tab-select", "none")
    page.wait_for_function("!document.querySelector('.score .abcjs-lyric')")
    assert page.locator(".fingering-key").is_hidden()


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
    assert page.inner_text(".tune-side .card dd a") == "Alawon Cymru (alawoncymru.com)"  # named, not the whole address
    assert page.get_attribute(".tune-side .card dd a", "href").startswith("http://alawoncymru.com/")


def test_tunes_from_the_session(page):
    # Tunes from thesession.org: the setting's link as the source, then who added it there.
    page.goto_site("alaw/y-drochfa/")
    page.wait_for_selector(".score .abcjs-staff")
    source = page.locator(".tune-side .card dd").filter(has_text="thesession.org")
    assert source.inner_text() == "The Session (thesession.org) (added by Rowan Folk)"
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
    page.open_tools()
    page.wait_for_selector(".score .abcjs-staff")
    page.select_option("#key-select", "2")  # G major -> A major
    page.click("text=Print / save")
    with page.expect_download() as info:
        page.click("[id^=print-menu] >> text='Save as ABC'")
    abc = open(info.value.path(), encoding="utf-8").read()
    assert info.value.suggested_filename == "glandyfi-in-A.abc"
    assert "\nK:A" in abc and "T:Glandyfi" in abc
    sizes = {}
    for play in ["Tune only", "Tune and chords"]:
        page.click(f".playback label:has-text('{play}')")
        page.click("text=Print / save")
        with page.expect_download() as info:
            page.click("[id^=print-menu] >> text='Save as MIDI'")
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
    ("pont", "Pont Cleddau"),                          # a name that starts with it, before another name of a tune ("The Pontnewydd Quickstep")
])
def test_search_by_name(page, query, expected):
    page.goto_site()
    page.fill("#hero-search", query)
    first = page.locator("#hero-suggestions li > span[lang]").first.inner_text()
    if expected:
        assert first == expected
    else:
        assert "Frân" in first


def test_tunes_sharing_a_name(page):
    # Different tunes with the same name are separate tunes, told apart by their source;
    # searching the name finds them all.
    page.goto_site()
    page.fill("#hero-search", "Morfa Rhuddlan")
    found = page.locator("#hero-suggestions li > span[lang]").all_inner_texts()
    assert {"Morfa Rhuddlan", "Morfa Rhuddlan (Mary Richards)", "Morfa Rhuddlan (Robin Huw Bowen)"} <= set(found)
    versions = page.evaluate("state.groups.get('morfa-rhuddlan').versions.map((v) => v.source)")
    assert versions == ["Alawon Cymru", "51 Welsh Airs", "Antient British Music (John Parry and Evan Williams, 1742)"]


def test_search_keys(page):
    # The first match is picked as the list opens (Enter opens it), and a screen reader
    # is told so; ↓ goes on to the second, and Escape closes the list.
    page.goto_site()
    page.fill("#hero-search", "llongau")
    box = page.locator("#hero-search")
    assert box.get_attribute("aria-activedescendant") == "hero-search-option-0"
    assert page.locator("#hero-search-option-0").get_attribute("aria-selected") == "true"
    page.keyboard.press("ArrowDown")
    assert box.get_attribute("aria-activedescendant") == "hero-search-option-1"
    page.keyboard.press("Escape")
    assert box.get_attribute("aria-activedescendant") is None
    page.fill("#hero-search", "xqzxqz")  # nothing found: nothing picked
    assert box.get_attribute("aria-activedescendant") is None


def test_piano_keys_in_pitch_order(page):
    # Tab and a screen reader go up the keyboard a semitone at a time.
    page.goto_site("?page=notes")
    labels = page.locator(".piano .key").evaluate_all("(keys) => keys.map((k) => k.getAttribute('aria-label'))")
    assert labels[:4] == ["G3", "G sharp 3", "A3", "A sharp 3"] and labels[-1] == "A5" and len(labels) == 27


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
    # first screen; loop, count-in, click and tablature are folded away under it.
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


def test_music_readable_on_a_phone(browser, site):
    # On a phone the music is laid out again in shorter lines, at a readable size, not
    # the tune's own lines shrunk to fit; turned on its side, it's laid out again.
    context = browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True,
                                  service_workers="block")
    page = context.new_page()
    page.goto(site + "alaw/a-honeyed-lip/")
    page.wait_for_selector(".score .abcjs-staff")
    scale = "(() => { const s = document.querySelector('.score [data-layout] svg'); return s.getBoundingClientRect().width / s.viewBox.baseVal.width; })()"
    assert page.evaluate(scale) > 0.65
    assert page.locator(".score .abcjs-staff").count() > 3  # three lines in the tune's own layout
    page.set_viewport_size({"width": 1300, "height": 800})
    page.wait_for_function("document.querySelectorAll('.score .abcjs-staff').length === 3")
    context.close()


def test_long_credit_on_a_phone(browser, site):
    # A long credit (C:) is split over two lines on a narrow score, and the tune type (R:,
    # shown under Details) isn't printed on the score to crowd it.
    context = browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, service_workers="block")
    page = context.new_page()
    page.goto(site + "alaw/dyffryn-clydach/")
    page.wait_for_selector(".score .abcjs-staff")
    lines = page.evaluate("[...document.querySelectorAll('.score [data-layout] svg .abcjs-composer tspan')].map((t) => t.textContent)")
    assert lines == ["Trefniant Meurig Williams", "o alaw Alyson a Ken Thomas"]
    assert page.locator(".score [data-layout] svg .abcjs-rhythm").count() == 0
    assert "ymdeithdon" not in page.inner_text(".score [data-layout]")
    context.close()


def test_practice_tools_folded_at_first(browser, site, page):
    page.goto_site("?tune=glandyfi")
    page.wait_for_selector(".score .abcjs-staff")
    assert not page.locator("#loop-select").is_visible()  # folded on a wide screen too, so the music is the page
    context = browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True,
                                  service_workers="block")
    phone = context.new_page()
    phone.goto(site + "alaw/glandyfi/")
    phone.wait_for_selector(".score .abcjs-staff")
    assert not phone.locator("#loop-select").is_visible()
    phone.click(".practice-tools summary")
    assert phone.locator("#loop-select").is_visible()
    phone.click(".brand")
    phone.go_back()
    phone.wait_for_selector(".score .abcjs-staff")
    assert phone.locator("#loop-select").is_visible()  # left open
    # Under the music on a phone too, so the music starts on the first screen
    assert phone.evaluate("""document.querySelector('.practice-tools').getBoundingClientRect().top
      > document.querySelector('.score').getBoundingClientRect().bottom - 1""")
    context.close()
    page.click(".practice-tools summary")
    page.wait_for_function("state.practice.open")  # the toggle event comes a moment after the click
    page.evaluate("navigate('alaw/abaty-waltham/')")
    page.wait_for_selector(".score .abcjs-staff")
    assert page.locator("#loop-select").is_visible()


def test_upcoming_sessions(page):
    # The home page lists the next few sessions in order; then, under "Also coming up: one-off dates", ones
    # on announced dates that aren't among them (up to four weeks ahead: the occasional
    # ones, easy to miss); then how many more there are in the next seven days.
    page.goto_site()
    page.wait_for_selector(".coming-up li")
    soon = page.evaluate("""async () => { const { sessions } = await loadSessions();
      const { soon, later } = comingUp(sessions); return [soon.length, later.length]; }""")
    assert soon[0] > 0  # there are weekly sessions, so the list is never empty
    # A made-up fortnight: four weekly sessions in the next few days, one on announced dates
    # among them, and another in three weeks.
    texts = page.evaluate("""() => {
      const day = (n) => { const d = new Date(); d.setDate(d.getDate() + n); return d; };
      const iso = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
      const weekday = (n) => ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"][day(n).getDay()];
      const at = (n, more = {}) => ({ venue: `Venue ${n}`, town: "Llandeilo", start: "19:30", id: `v${n}`,
        repeat: "weekly", day: weekday(n), ...more });
      const sessions = [at(0), at(1), at(2), at(3), at(4), at(5, { repeat: "dates", dates: [iso(day(5))] }),
        at(21, { repeat: "dates", dates: [iso(day(21))] }), at(40, { repeat: "dates", dates: [iso(day(40))] })];
      state.sessionData = Promise.resolve({ sessions });
      const box = upcomingSessions(); document.body.append(box);
      return new Promise((done) => setTimeout(() => {
        done([...box.querySelectorAll("li, p")].map((x) => x.textContent)); box.remove(); }, 50));
    }""")
    venue = lambda t: t.split(" · ")[1].split(",")[0]
    assert [venue(t) for t in texts[:3]] == ["Venue 0", "Venue 1", "Venue 2"]  # the next three, in order
    assert texts[3] == "Also coming up: one-off dates" and [venue(t) for t in texts[4:6]] == ["Venue 5", "Venue 21"]  # not 40: too far
    assert texts[6].startswith("And 2 more in the next seven days")  # Venue 3 and 4
    page.click(".coming-up a[href='sesiynau/']")
    page.wait_for_selector(".card.session")


def test_coming_up_on_the_sessions_page(page):
    # The sessions page lists every session in the next seven days at the top, then ones on
    # announced dates further ahead, each a link down to its card, even when the filters
    # had hidden it.
    page.goto_site("sesiynau/")
    page.wait_for_selector(".card.session")
    soon, later = page.evaluate("async () => { const { soon, later } = comingUp((await loadSessions()).sessions); return [soon.length, later.length]; }")
    assert page.locator(".coming-up li").count() == soon + later and soon > 0
    text = page.text_content(".coming-up")  # (the labels are shown in capitals)
    assert "Next seven days" in text and ("Further ahead" in text) == (later > 0)
    link = page.locator(".coming-up li a").first
    card = link.get_attribute("href")[1:]
    day = page.evaluate(f"async () => (await loadSessions()).sessions.find((s) => 'session-' + s.id === '{card}').day")
    page.locator(f".pills [data-day]:not([data-day='{day}'], [data-day='']):not([disabled])").first.click()  # another day: its card is hidden
    assert page.locator(f"#{card}").count() == 0
    link.click()
    page.wait_for_function(f"document.activeElement.id === '{card}'")
    assert page.url.endswith("sesiynau/")


def test_home_page_on_a_phone(browser, site):
    # The search is near the top (no pictures above it), and "What you can do" is short
    # enough to show whole.
    context = browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True,
                                  service_workers="block")
    page = context.new_page()
    page.goto(site)
    page.wait_for_selector(".features")
    assert not page.locator(".instruments.at-top").is_visible()
    assert page.locator("#hero-search").bounding_box()["y"] < 844 / 2
    # The picture comes near the end instead, after "What you can do".
    assert page.locator(".instruments.at-end").bounding_box()["y"] > page.locator(".features").bounding_box()["y"]
    assert page.locator(".features li").count() == 4 and page.locator(".features li").last.is_visible()
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


@pytest.mark.parametrize("path", ["?tune=glandyfi", "?tune=llancesau-trefaldwyn"])
def test_fits_a_phone_with_everything_open(browser, site, path):
    # The folds (the ABC, how to say it, the practice tools) open: still no sideways scroll.
    context = browser.new_context(viewport={"width": 360, "height": 800}, service_workers="block")
    page = context.new_page()
    page.goto(site + path)
    page.wait_for_selector(".score .abcjs-staff")
    page.evaluate("document.querySelectorAll('details').forEach((d) => { d.open = true; })")
    page.wait_for_timeout(300)
    assert page.evaluate("document.documentElement.scrollWidth") <= 360
    context.close()


def test_home_page(page):
    page.goto_site()
    features = page.locator(".features li").all_inner_texts()
    assert len(features) == 4 and any(f.startswith("Chords\n") for f in features)
    # No red button competes with the search: Surprise me is a plain one, and finding a
    # tune by its notes is a line of text.
    assert page.locator("main button.primary:visible").count() == 0
    assert page.locator(".notes-invite a[href='?page=notes']").is_visible()
    assert page.locator(".offline-card").is_visible()
    # One Surprise me: the home page's own, not the sidebar's too.
    assert page.locator(".home-actions button:has-text('Surprise me')").is_visible() and not page.locator("#surprise-sidebar").is_visible()
    # One search box on the home page: its own big one, not the sidebar's too.
    assert page.locator("#hero-search").is_visible() and not page.locator("#search-input").is_visible()
    # Browsing every tune has its own page; the home page links to it.
    assert page.locator(".tune-list").count() == 0
    page.click("a.button-link:has-text('Browse all')")
    page.wait_for_selector(".tune-list li", state="attached")
    assert page.locator("details.all-tunes").evaluate("d => d.open")  # all of them, as it says
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
    assert page.locator(".features li").count() == 4
    # Nothing left in English: no sentence of the English page shows up in the Welsh one.
    welsh = page.evaluate(VISIBLE_TEXT)
    names = set(page.locator(".coming-up li a").all_inner_texts())  # sessions' own names stay as they are
    fragments = {f.strip() for f in re.split(r"[.:;?!()\n]", english) if len(f.strip()) >= 12 and not any(f.strip() in n for n in names)}
    assert fragments and not [f for f in fragments if f in welsh]
    # The choice is remembered.
    page.reload()
    page.wait_for_function("typeof state !== 'undefined' && state.data")
    assert page.inner_text("h1") == "Croeso i'r Sesiwn!"
    page.click(".sidebar-links a[href='?page=browse']")
    page.wait_for_selector(".tune-list li", state="attached")
    assert page.get_attribute("#main", "lang") == "cy"
    assert page.inner_text("main h1") == "Pori yn ôl math a chywair"
    page.click(".brand")
    page.click(".lang-switch [data-lang=en]")
    assert page.inner_text("h1").replace("\u00a0", " ") == "Croeso! Welcome to Y Sesiwn"
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
    # The phone's one line, a key in short and the tempo, reads the same in Welsh ("G, 112 bpm")
    key_line = lambda f: re.fullmatch(r"[A-G][#b]?( [a-z]{3})?( → [A-G][#b]?( [a-z]{3})?)?, \d+ bpm", f)
    # A version's note is its source and time signature (and keys, in Welsh): "Alawon Cymru · 4/4"
    version_note = lambda f: all(p in data or re.fullmatch(r"\d+/\d+|C\|?", p) for p in f.strip("· ").split(" · "))
    left = [f for f in fragments if f in welsh and not tune_words(f) and not key_line(f) and not version_note(f)
            and f not in ENGLISH_ON_PURPOSE]
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
    page.goto(site + "?page=offline")  # the home page's card only links here
    assert says in page.locator("main").inner_text()  # the card, or the list of steps under it
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


def test_with_the_offline_copy(browser, site):
    # Once sw.js answers for the site: tunes.json is fetched once a visit, not twice
    # (as a <link rel="preload"> was), and an address with no page says so (the server's
    # 404), rather than showing the home page as if the address were right.
    context = browser.new_context()  # service worker allowed
    page = context.new_page()
    page.goto(site)
    page.wait_for_function("navigator.serviceWorker.controller !== null", timeout=30000)
    requests = []
    page.on("request", lambda r: requests.append(r.url) if r.url.endswith("tunes.json") else None)
    page.reload()
    page.wait_for_selector(".features")
    page.wait_for_timeout(300)
    assert len(requests) == 1
    answer = page.goto(site + "no-such-page/")
    assert answer.status == 404 and not page.locator(".features").count()
    context.close()


SAVED_SOUNDS = """async () => (await Promise.all((await caches.keys()).filter((k) => k.startsWith("sounds-"))
  .map(async (k) => (await (await caches.open(k)).keys()).map((r) => r.url)))).flat()"""


@pytest.mark.parametrize("phone", [False, True])
def test_piano_sounds_offline(browser, site, phone):
    # On a computer every piano note is saved for offline playback once something has
    # been played (none for someone who only reads the music); on a phone's data, only
    # when asked (the offline card's Save them now).
    android = "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0 Mobile Safari/537.36"
    context = browser.new_context(**({"user_agent": android, "is_mobile": True, "has_touch": True,
                                       "viewport": {"width": 390, "height": 844}} if phone else {}))
    page = context.new_page()
    page.goto(site + "?page=offline")
    page.wait_for_function("state.sounds !== null", timeout=30000)
    all_saved = "state.sounds.saved === state.sounds.total"
    page.wait_for_timeout(1000)
    assert not page.evaluate(SAVED_SOUNDS)  # nothing played yet: no sounds
    if phone:
        page.click("button.save-sounds")
    else:
        page.goto(site + "?page=notes")
        page.click(".piano [data-midi='67']")  # a key of the keyboard
        page.goto(site + "?page=offline")
        page.wait_for_function("state.sounds !== null", timeout=30000)
    page.wait_for_function(all_saved, timeout=30000)
    assert "Saved on this device" in page.inner_text(".offline-card")
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
        page.wait_for_selector(".set-list li", state="attached")
        assert page.evaluate("window.newVersion") is True
        context.set_offline(True)
        page.goto(site + "?set=5A3V~h&n=Nos%20Iau")
        page.wait_for_selector(".set-list li", state="attached")
        assert page.evaluate("window.newVersion") is None  # offline: the saved copy
    finally:
        app.write_text(original, encoding="utf-8")
        context.close()


def test_first_visit_downloads_once(browser, site):
    # The offline copy is saved without downloading again what the page has just loaded
    # (the server answers "not modified").
    from conftest import SERVED
    context = browser.new_context()  # service worker allowed
    page = context.new_page()
    SERVED.clear()
    page.goto(site)
    page.wait_for_function("navigator.serviceWorker.controller !== null", timeout=30000)
    for path in ["/tunes.json", "/app.js", "/style.css"]:
        assert [status for p, status in SERVED if p == path].count(200) == 1, path
    context.close()


def test_a_deploy_updates_the_offline_copy(browser, site):
    # Someone who has visited before comes back after a deploy: the files that changed
    # are saved anew, even with the old ones still in the browser's own cache.
    import time
    from conftest import ROOT
    out = ROOT / "_site"
    originals = {name: (out / name).read_text(encoding="utf-8") for name in ["app.js", "style.css", "sw.js"]}
    context = browser.new_context()  # service worker allowed
    page = context.new_page()
    try:
        page.goto(site)
        page.wait_for_function("navigator.serviceWorker.controller !== null", timeout=30000)
        page.goto(site + "?tune=glandyfi")
        page.wait_for_selector(".score .abcjs-staff")
        time.sleep(1.1)  # the test server's "last modified" is to the second
        (out / "app.js").write_text(originals["app.js"] + "\nwindow.deployed = 2;\n", encoding="utf-8")
        (out / "style.css").write_text(originals["style.css"] + "\n/* deployed */\n", encoding="utf-8")
        (out / "sw.js").write_text(re.sub(r'const VERSION = "[^"]+"', 'const VERSION = "deployed"', originals["sw.js"]), encoding="utf-8")
        page.reload()
        for _ in range(100):  # until the new copy is saved and the old one gone
            keys = page.evaluate("caches.keys()")
            if "site-deployed" in keys and not [k for k in keys if k.startswith("site-") and k != "site-deployed"]:
                break
            page.wait_for_timeout(200)
        context.set_offline(True)
        page.goto(site + "?tune=glandyfi")
        page.wait_for_selector(".score .abcjs-staff")
        assert page.evaluate("window.deployed") == 2
        assert page.evaluate("caches.match('style.css').then((r) => r.text())").endswith("/* deployed */\n")
    finally:
        for name, text in originals.items():
            (out / name).write_text(text, encoding="utf-8")
        context.close()


def test_a_page_left_open_gets_a_deploy(browser, site):
    # A page left open (the app on a phone) picks up a deploy: not by reloading the page
    # being read, but on the next page opened; that page comes from the new saved copy,
    # even with no signal by then.
    import time
    from conftest import ROOT
    out = ROOT / "_site"
    originals = {name: (out / name).read_text(encoding="utf-8") for name in ["app.js", "sw.js"]}
    context = browser.new_context()  # service worker allowed
    page = context.new_page()
    try:
        page.goto(site + "?tune=glandyfi")
        page.wait_for_function("navigator.serviceWorker.controller !== null", timeout=30000)
        page.wait_for_selector(".score .abcjs-staff")
        page.evaluate("window.oldPage = true")
        time.sleep(1.1)  # the test server's "last modified" is to the second
        (out / "app.js").write_text(originals["app.js"] + "\nwindow.deployed = 2;\n", encoding="utf-8")
        (out / "sw.js").write_text(re.sub(r'const VERSION = "[^"]+"', 'const VERSION = "deployed"', originals["sw.js"]), encoding="utf-8")
        # What coming back into view does, without its ten minutes' wait.
        page.evaluate("navigator.serviceWorker.getRegistration().then((r) => r.update())")
        page.wait_for_function("state.updated", timeout=30000)
        assert page.evaluate("window.oldPage") is True  # still the same page
        context.set_offline(True)
        page.click(".sidebar-links a[href='?page=browse']")
        page.wait_for_selector(".tune-list li", state="attached", timeout=10000)
        assert page.evaluate("window.oldPage") is None
        assert page.evaluate("window.deployed") == 2
    finally:
        for name, text in originals.items():
            (out / name).write_text(text, encoding="utf-8")
        context.close()


@pytest.mark.parametrize("junk, opens, address", [
    ("alaw/glandyfi/%C2%A0", "Glandyfi", "alaw/glandyfi/"),      # a non-breaking space, pasted with the link
    ("alaw/glandyfi/%20", "Glandyfi", "alaw/glandyfi/"),
    ("alaw/glandyfi.", "Glandyfi", "alaw/glandyfi/"),            # the full stop of the sentence it was in
    ("alaw/glandyfi/)", "Glandyfi", "alaw/glandyfi/"),
    ("sesiynau/%C2%A0", "Active sessions", "sesiynau/"),
])
def test_address_with_something_stuck_to_it(page, site, junk, opens, address):
    # On a phone the offline copy opens the app at whatever address was pasted: it should
    # find the page, and put the address right.
    page.goto_site()
    page.evaluate(f"history.pushState(null, '', '{junk}'); render()")
    page.wait_for_function(f"document.querySelector('main h1')?.textContent === {opens!r}")
    assert page.url == site + address


def test_not_found_page_takes_junk_off(page, site):
    # On a computer GitHub Pages shows 404.html for such an address: it goes on to the page.
    from conftest import ROOT
    body = (ROOT / "_site" / "404.html").read_text(encoding="utf-8")
    page.route(site + "alaw/glandyfi/%C2%A0", lambda route: route.fulfill(status=404, body=body, content_type="text/html"))
    page.goto(site + "alaw/glandyfi/%C2%A0")
    page.wait_for_url(site + "alaw/glandyfi/")
    page.wait_for_selector(".score .abcjs-staff")
    assert page.inner_text("main h1") == "Glandyfi"


def test_share_in_a_key(page, site):
    # ?key=A opens the tune in A; changing the key changes the address (and so the link
    # that Share and the QR code give). So does a tempo other than the tune's own, so
    # "learn it at 70" can be sent too.
    page.goto_site("alaw/glandyfi/?key=A")  # Glandyfi is in G
    page.wait_for_selector(".score .abcjs-staff")
    assert page.input_value("#key-select") == "2"
    page.select_option("#key-select", "-2")
    assert page.url == site + "alaw/glandyfi/?key=F"
    page.fill("#tempo", "150")
    page.dispatch_event("#tempo", "change")
    assert page.url == site + "alaw/glandyfi/?key=F&tempo=150"
    page.select_option("#key-select", "0")
    assert page.url == site + "alaw/glandyfi/?tempo=150"
    page.goto_site("alaw/glandyfi/?v=2&key=Bb&tempo=70&bpm=120")  # ?tempo= opens it at that tempo; anything else is ignored
    page.wait_for_selector(".score .abcjs-staff")
    assert page.input_value("#key-select") == "3" and page.input_value("#tempo") == "70"
    assert page.url == site + "alaw/glandyfi/?v=2&key=Bb&tempo=70"
    page.goto_site("?tune=glandyfi&key=D")  # an older link: moves to the tune's address, key kept
    page.wait_for_selector(".score .abcjs-staff")
    assert page.url == site + "alaw/glandyfi/?key=D&tempo=150"  # at the tempo kept for it (chosen above)


def test_keyboard_shortcuts(page):
    # "?" lists the shortcuts; Esc closes the list; the footer's link opens it too.
    page.goto_site()
    page.keyboard.press("?")
    assert page.locator("dialog.shortcuts").is_visible()
    assert "Search for a tune by name" in page.inner_text("dialog.shortcuts")
    page.keyboard.press("Escape")
    page.wait_for_selector("dialog.shortcuts", state="detached")  # removed once its close event has run
    page.click("#shortcuts-button")
    assert page.locator("dialog.shortcuts").is_visible()


def test_focus_on_new_page(page):
    # Moving to another page puts the focus on its heading, so screen readers say where you are.
    page.goto_site()
    page.click(".sidebar-links a[href='?page=browse']")
    page.wait_for_function("document.activeElement?.matches('main h1')")
    assert page.evaluate("document.activeElement.textContent") == "Browse by type and key"
    page.go_back()
    page.wait_for_function("document.activeElement?.matches('main h1')")


def test_search_count_said(page):
    # How many tunes the search finds, for screen readers.
    page.goto_site("?page=browse")
    page.fill("#search-input", "glandyfi")
    page.wait_for_function("document.querySelector('.search [role=status]').textContent.startsWith('1 tune')")
    page.fill("#search-input", "zzzqqq")
    page.wait_for_function("document.querySelector('.search [role=status]').textContent === 'No tunes match that name.'")


def test_tune_names_marked_welsh_or_english(page):
    # Screen readers say each tune's name in its own language.
    page.goto_site("alaw/glandyfi/")
    page.wait_for_selector(".score .abcjs-staff")
    assert page.get_attribute("main h1", "lang") == "cy"
    page.goto_site("?page=browse")
    page.wait_for_selector(".tune-list li", state="attached")
    assert page.get_attribute(".tune-list a[href='alaw/gower-reel/'] span", "lang") == "en"
    assert page.get_attribute(".tune-list a[href='alaw/glandyfi/'] span", "lang") == "cy"


def test_keys_spelt_as_players_write_them(page):
    # The fewest sharps or flats, and sharps when it's six either way; the music is written
    # in the key the menu says (abcjs's Gb major comes out as F# major, notes and chords).
    page.goto_site("alaw/glandyfi/?key=F%23")
    page.wait_for_selector(".score .abcjs-staff")
    assert page.locator("#key-select option").all_inner_texts() == [
        "D major", "Eb major", "E major", "F major", "F# major", "G major (original)",
        "Ab major", "A major", "Bb major", "B major", "C major", "Db major"]
    assert page.inner_text(".controls-summary .now").startswith("F# (from G)")
    assert page.evaluate("""() => respell('X:1\\nK:Gb\\n"Gb"GABc =Bd|"Cb"e_f|]')""") == 'X:1\nK:F#\n"F#"FGAB ^^Ac|"B"d=e|]'
    assert page.evaluate("""() => respell('X:1\\nK:Ab\\n"Ab"ABc|]')""") == 'X:1\nK:Ab\n"Ab"ABc|]'  # 4 flats: as it is


def test_usual_key_remembered(page, site):
    # The key chosen for a tune is kept on the device and used next time (and said so, then,
    # not as it's chosen); a shared link's key wins without replacing it.
    page.goto_site("alaw/glandyfi/")
    page.wait_for_selector(".score .abcjs-staff")
    page.select_option("#key-select", "2")
    assert page.inner_text(".usual-key") == ""
    page.goto_site("alaw/glandyfi/")
    page.wait_for_selector(".score .abcjs-staff")
    assert page.input_value("#key-select") == "2" and page.url == site + "alaw/glandyfi/?key=A"
    assert page.inner_text(".usual-key") == "Your key last time"
    page.select_option("#key-select", "3")
    assert page.inner_text(".usual-key") == ""
    page.select_option("#key-select", "2")  # back to it: it is last time's key
    assert page.inner_text(".usual-key") == "Your key last time"
    page.goto_site("alaw/glandyfi/?key=C")
    page.wait_for_selector(".score .abcjs-staff")
    assert page.input_value("#key-select") == "5" and page.inner_text(".usual-key") == ""
    page.goto_site("alaw/glandyfi/")
    page.wait_for_selector(".score .abcjs-staff")
    assert page.input_value("#key-select") == "2"
    page.select_option("#key-select", "0")  # back to the written key: nothing kept
    assert page.evaluate("localStorage.getItem('tunes')") == "{}"


def test_play_from_a_note(page):
    # Tapping a note starts playback from there (and the notes aren't Tab stops).
    page.goto_site("alaw/glandyfi/")
    page.wait_for_selector(".score .abcjs-staff")
    assert page.locator(".score [data-layout] svg [tabindex]").count() == 0
    page.evaluate("""() => { window.seeks = []; const s = state.synth.seek.bind(state.synth);
      state.synth.seek = (t, u) => { seeks.push([t, u]); return s(t, u); }; }""")
    note = page.locator(".score [data-layout] .abcjs-l1 .abcjs-note").first
    box = note.bounding_box()
    page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    page.wait_for_function("window.seeks.length > 0")
    (seconds, units), = page.evaluate("window.seeks")
    assert units == "seconds" and seconds > 1  # the second line, not the start


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
    page.click(".place-list a span:text-is('Machynlleth')")
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
            # Vibrato: the pitch swings ±0.6% (about 10 cents), 5.5 times a second. This is
            # the phase of that frequency (its integral), so the swing doesn't grow with time.
            phase = 2 * math.pi * f * t - f * 0.006 / 5.5 * math.cos(2 * math.pi * 5.5 * t)
            envelope = min(1, t / 0.01) * min(1, (n - i) / (0.005 * rate))
            samples.append(envelope * sum(math.sin(k * phase) / k for k in (1, 2, 3, 4, 5)) * 0.3)
    samples += [0.0] * int(3.2 * rate)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"".join(struct.pack("<h", int(20000 * (x + rng.gauss(0, 0.004)))) for x in samples))


@pytest.mark.parametrize("slow", [1, 6])
def test_microphone(playwright_instance, site, tmp_path, slow):
    # Machynlleth's first ten notes, played a tone higher than written, fast: every note
    # heard, also on a slow, busy device (the page six times slower) that redraws the
    # screen less often.
    notes = [71, 72, 74, 76, 74, 72, 71, 72, 71, 69]
    fiddle_recording(tmp_path / "fiddle.wav", [n + 2 for n in notes])
    browser = playwright_instance.chromium.launch(args=[
        "--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream",
        f"--use-file-for-fake-audio-capture={tmp_path / 'fiddle.wav'}%noloop",
    ])
    page = browser.new_context(service_workers="block", permissions=["microphone"]).new_page()
    if slow > 1:
        page.context.new_cdp_session(page).send("Emulation.setCPUThrottlingRate", {"rate": slow})
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


def test_microphone_without_audio_worklet(playwright_instance, site, tmp_path):
    # Browsers without AudioWorklet look at the sound once a screen redraw instead: still
    # fine for notes played at a steady pace.
    notes = [71, 72, 74, 76, 74, 72, 71, 72, 71, 69]
    fiddle_recording(tmp_path / "fiddle.wav", [n + 2 for n in notes], seconds_per_note=0.3)
    browser = playwright_instance.chromium.launch(args=[
        "--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream",
        f"--use-file-for-fake-audio-capture={tmp_path / 'fiddle.wav'}%noloop",
    ])
    page = browser.new_context(service_workers="block", permissions=["microphone"]).new_page()
    page.add_init_script("Object.defineProperty(BaseAudioContext.prototype, 'audioWorklet', { get: () => undefined })")
    page.goto(site + "?page=notes")
    page.click("button.listen")
    page.wait_for_selector("button.listen.on")
    page.wait_for_function("!document.querySelector('button.listen').classList.contains('on')", timeout=30000)
    assert page.input_value("#notes-search") == "C# D E F# E D C# D C# B"
    browser.close()


# ---- Practice: parts, looping, speed-up, count-in, click, tablature ------------------

@pytest.mark.parametrize("slug, parts", [("glandyfi", 2), ("machynlleth", 4), ("ffaniglen", 2), ("morgawr", 3)])
def test_loop_parts(page, slug, parts):
    page.goto_site(f"?tune={slug}")
    page.open_tools()
    page.wait_for_selector(".score .abcjs-staff")
    options = page.eval_on_selector_all("#loop-select option", "os => os.map((o) => o.textContent)")
    assert options == ["Off", "The whole tune"] + [f"Part {chr(65 + i)}" for i in range(parts)]
    page.select_option("#loop-select", "-1")
    assert page.locator(".speed-up").is_visible()
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
    page.click(".practice-tools summary")  # folded at first
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
        page.wait_for_function(f"document.querySelector('.speed-note').textContent === 'now {bpm} of 112 bpm'", timeout=15000)
        # Back in part B (not part A), still playing.
        page.wait_for_function(f"(() => {{ const n = document.querySelector('.abcjs-note_playing'); "
                               f"return n && state.synth.isStarted && "
                               f"[...document.querySelectorAll('.score .abcjs-note')].indexOf(n) >= 30; }})()", timeout=15000)
    page.click(".abcjs-midi-start")  # pause
    assert not errors, errors
    context.close()


def test_paused_after_a_jump_plays_on_from_the_lit_notes(browser, site):
    # Moved on while playing, then paused and played again, the sound carries on from
    # the notes that are lit (abcjs's own would carry on from where it was before the jump).
    context = browser.new_context(service_workers="block")
    page = context.new_page()
    page.goto(site + "?tune=glandyfi")
    page.wait_for_selector(".score .abcjs-staff")
    page.click(".abcjs-midi-start")
    page.wait_for_function("document.querySelector('.abcjs-note_playing') && state.synth.timer")
    page.evaluate("state.synth.seek(.6)")
    page.click(".abcjs-midi-start")  # pause
    page.wait_for_function("!state.synth.isStarted")
    page.click(".abcjs-midi-start")  # play
    page.wait_for_function("state.synth.isStarted && state.synth.timer.isRunning")
    # Where the sound is (abcjs's audio clock) against where the lit notes are, in seconds.
    sound, notes = page.evaluate("""() => { const b = state.synth.midiBuffer;
      return [ABCJS.synth.activeAudioContext().currentTime - b.startTimeSec, state.synth.timer.currentMillisecond() / 1000]; }""")
    assert notes > 5 and abs(sound - notes) < .25, (sound, notes)
    page.click(".abcjs-midi-start")  # pause
    context.close()


def test_other_sound_pauses_the_tune(browser, site):
    # A phone pausing the page's silent <audio> (another tab or app has started playing)
    # pauses the tune too; pausing the tune lets the <audio> go.
    context = browser.new_context(service_workers="block")
    page = context.new_page()
    page.goto(site + "?tune=glandyfi")
    page.wait_for_selector(".score .abcjs-staff")
    page.click(".abcjs-midi-start")
    page.wait_for_function("document.querySelector('.abcjs-note_playing') && audioFocus.playing")
    page.evaluate("audioFocus.element.pause()")
    page.wait_for_function("!state.synth.isStarted && !document.querySelector('.abcjs-midi-start.abcjs-pushed')")
    assert not page.evaluate("audioFocus.playing")
    page.click(".abcjs-midi-start")  # plays again at the first press
    page.wait_for_function("audioFocus.playing && !audioFocus.element.paused && state.synth.timer.isRunning")
    page.click(".abcjs-midi-start")  # pause
    page.wait_for_function("!audioFocus.playing && audioFocus.element.paused")
    context.close()


def test_speed_up_arrives(browser, site):
    # Sped up to the tune's usual tempo (112 bpm, a jig's, from 107), the note says so: "da iawn".
    context = browser.new_context(service_workers="block")
    page = context.new_page()
    page.goto(site + "?tune=glandyfi")
    page.wait_for_selector(".score .abcjs-staff")
    page.click(".practice-tools summary")  # folded at first
    page.fill("#tempo", "107")
    page.dispatch_event("#tempo", "change")
    page.select_option("#loop-select", "1")
    page.check("text=Speed up each time")
    page.click(".abcjs-midi-start")
    page.wait_for_function("document.querySelector('.abcjs-note_playing') && state.synth.timer")
    page.evaluate("() => { const e = state.synth.timer.noteTimings.filter((e) => e.type === 'event'); "
                  "state.synth.seek((e.at(-1).milliseconds - 800) / 1000, 'seconds'); }")
    page.wait_for_function("document.querySelector('.speed-note.arrived')", timeout=15000)
    assert page.inner_text(".speed-note") == "Reached 112 bpm. Da iawn!"
    assert page.get_attribute(".speed-note strong", "lang") == "cy"
    page.click(".abcjs-midi-start")  # pause
    context.close()


def test_speed_up_the_whole_tune(browser, site):
    # Repeating the whole tune speeds up each time it comes round, up to the "to" bpm; a
    # "to" no faster than the tempo says what to do instead.
    context = browser.new_context(service_workers="block")
    page = context.new_page()
    page.goto(site + "?tune=glandyfi")
    page.wait_for_selector(".score .abcjs-staff")
    page.click(".practice-tools summary")  # folded at first
    # Ticked with nothing repeating and the tempo at the tune's own: it works at once, the
    # whole tune from 70% of the tempo up to it.
    page.check("text=Speed up each time")
    assert page.input_value("#loop-select") == "-1"
    assert " ".join(page.text_content(".speed-range").split()) == "from 78 to bpm" and page.input_value("#speed-to") == "112"
    assert page.input_value("#tempo") == "78" and page.inner_text(".speed-note") == ""
    page.fill("#tempo", "120")  # faster than the goal: says what to do
    page.dispatch_event("#tempo", "change")
    assert page.inner_text(".speed-note").startswith("To speed up, start slower")
    page.fill("#tempo", "90")
    page.dispatch_event("#tempo", "change")
    page.fill("#speed-to", "99")
    page.dispatch_event("#speed-to", "change")
    assert page.inner_text(".speed-note") == ""
    page.click(".abcjs-midi-start")
    page.wait_for_function("document.querySelector('.abcjs-note_playing') && state.synth.timer")
    page.evaluate("() => { const e = state.synth.timer.noteTimings.filter((e) => e.type === 'event'); "
                  "state.synth.seek((e.at(-1).milliseconds - 800) / 1000, 'seconds'); }")
    page.wait_for_function("document.querySelector('.speed-note').textContent === 'now 95 of 99 bpm'", timeout=15000)
    page.click(".abcjs-midi-start")  # pause
    page.fill("#speed-to", "1000")  # out of range: the fastest allowed
    page.dispatch_event("#speed-to", "change")
    assert page.input_value("#speed-to") == "240"
    context.close()


def test_count_in_and_click(page):
    page.goto_site("?tune=glandyfi")
    page.open_tools()
    page.wait_for_selector(".score .abcjs-staff")
    drum = """() => { const p = { ...AUDIO_PARAMS, ...clickParams(state.synth.visualObj, state.bySlug.get('glandyfi')) };
      const [melody, , drums] = state.synth.visualObj.setUpAudio(p).tracks.map((t) => t.filter((e) => e.cmd === 'note'));
      return { melodyStarts: melody[0].start, drums: drums ? drums.length : 0 }; }"""
    assert page.evaluate(drum)["drums"] == 0
    page.check(".practice-row label:has-text('Count-in')")
    count_in = page.evaluate(drum)
    assert count_in["melodyStarts"] > 0 and count_in["drums"] == 2  # one 6/8 bar: two dotted-crotchet clicks
    page.check(".practice-row label:has-text('Click · on every beat')")
    assert page.evaluate(drum)["drums"] > 50  # a click on every beat of the tune


def test_practice_tools_remembered(page):
    # How a tune is practised is kept on the device for that tune only: its tempo, the
    # chords, repeat, count-in and click. Another tune opens as written, so nothing left on at
    # home sounds at a session. The tablature (the reader's instrument) and the tools open
    # or folded are kept for every tune; one since taken out: none.
    page.goto_site("?tune=glandyfi")
    page.open_tools()
    page.wait_for_selector(".score .abcjs-staff")
    page.check(".practice-row label:has-text('Count-in')")
    page.check(".practice-row label:has-text('Click · on every beat')")
    page.select_option("#tab-select", "mandolin")
    page.check(".practice-row label:has-text('Chords on the sheet music')")
    page.check(".practice-row input[value=both]", force=True)
    page.select_option("#loop-select", "-1")
    page.fill("#tempo", "90")
    page.dispatch_event("#tempo", "change")
    page.goto_site("?tune=cawl-cennin")
    page.wait_for_selector(".score .abcjs-staff")
    assert page.locator(".practice-tools").get_attribute("open") is not None
    assert not page.is_checked(".practice-row label:has-text('Count-in') input")
    assert not page.is_checked(".practice-row label:has-text('Click · on every beat') input")
    assert page.input_value("#tab-select") == "mandolin"
    assert page.locator(".sound-on").is_hidden()
    assert page.evaluate("state.practice") == {"tab": "mandolin", "open": True, "tabKnown": True}
    page.goto_site("alaw/glandyfi/")
    page.wait_for_selector(".score .abcjs-staff")
    assert page.is_checked(".practice-row label:has-text('Count-in') input")
    assert page.is_checked(".practice-row label:has-text('Click · on every beat') input")
    assert page.is_checked(".practice-row label:has-text('Chords on the sheet music') input")
    assert page.is_checked(".practice-row input[value=both]")
    assert page.input_value("#loop-select") == "-1" and page.input_value("#tempo") == "90"
    assert page.inner_text(".usual-key >> nth=-1") == "Your tempo last time"
    # Said by Play, where it's pressed; and turned off from there (the tablature stays).
    assert page.inner_text(".sound-on") == "Plays with chords, repeat, count-in, click · Turn off"
    page.click(".sound-on .link-button")
    assert page.locator(".sound-on").is_hidden()
    assert not page.is_checked(".practice-row label:has-text('Click · on every beat') input")
    assert page.input_value("#loop-select") == "-2" and page.input_value("#tab-select") == "mandolin"
    assert page.evaluate("JSON.parse(localStorage.getItem('tunes'))") == {"glandyfi": {"bpm": 90, "onScore": True}}
    # Turn all off: the chords on the music and the tablature too; the tempo stays.
    page.click(".kept-note .link-button")
    assert page.input_value("#tab-select") == "none"
    assert page.evaluate("JSON.parse(localStorage.getItem('tunes'))") == {"glandyfi": {"bpm": 90}}
    assert page.locator(".kept-note .link-button").is_hidden()
    page.evaluate("localStorage.setItem('practice', JSON.stringify({ tab: 'treble-recorder', open: 'yes' }))")
    page.goto_site("?tune=glandyfi")
    page.wait_for_selector(".score .abcjs-staff")
    assert page.evaluate("state.practice") == {"tab": "none", "open": None, "tabKnown": False}


@pytest.mark.parametrize("tab, first", [("mandolin", "0"), ("guitar", "0")])
@pytest.mark.parametrize("width", [1280, 390])
def test_tablature(page, tab, first, width):
    # Glandyfi starts on D above middle C: the open D string on a mandolin and on a guitar.
    # On a phone too, where the music is laid out again in shorter lines (abcjs leaves the
    # tablature behind then, unless given it back: see drawScore).
    page.set_viewport_size({"width": width, "height": 900})
    page.goto_site("?tune=glandyfi")
    page.open_tools()
    page.wait_for_selector(".score .abcjs-staff")
    page.select_option("#tab-select", tab)
    page.wait_for_function("document.querySelectorAll('.score .abcjs-tab-number, .score [data-name=\"tabNumber\"]').length > 50")
    numbers = page.evaluate("[...document.querySelectorAll('.score svg text')].map((t) => t.textContent).filter((t) => /^\\d+$/.test(t))")
    assert numbers[0] == first
    # Said once, above the music, with its tuning; not on every line.
    assert page.inner_text(".fingering-name strong") in ("Mandolin / fiddle (GDAE)", "Guitar (EADGBE)")
    assert page.locator(".score .abcjs-tab-label, .score text:has-text('EADGBE')").count() == 0


def test_tablature_on_bigger_music(page):
    # Made bigger, the music is laid out again in shorter lines: the tablature stays.
    page.goto_site("?tune=glandyfi")
    page.open_tools()
    page.wait_for_selector(".score .abcjs-staff")
    page.select_option("#tab-select", "guitar")
    tabs = "document.querySelectorAll('.score .abcjs-tab-number, .score [data-name=\"tabNumber\"]').length"
    page.wait_for_function(f"{tabs} > 50")
    page.click(".music-size button:last-child")
    page.wait_for_function("JSON.parse(document.querySelector('.score [data-layout]').dataset.layout).wrap")
    assert page.evaluate(tabs) > 50


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
    assert page.inner_text(".tune-side .card dd a") == "Alawon Cymru (alawoncymru.com)"
    assert page.get_attribute(".tune-side .card dd a", "href") == "http://alawoncymru.com/alawon/Tunes/SetyDwr/SetYDwr.html"


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


# ---- Sessions ---------------------------------------------------------------------

def test_session_dates(page):
    # A session's next date: weekly, the nth or last weekday of the month, within its season.
    page.goto_site()
    next_date = """([session, today]) => { const d = nextSession({ from: null, until: null, ...session }, new Date(`${today}T12:00`));
      return d && `${d.getFullYear()}-${d.getMonth() + 1}-${d.getDate()}`; }"""
    when = lambda session, today="2026-10-02": page.evaluate(next_date, [session, today])
    assert when({"day": "Monday", "repeat": "weekly"}) == "2026-10-5"
    assert when({"day": "Friday", "repeat": "weekly"}) == "2026-10-2"  # today
    assert when({"day": "Friday", "repeat": "monthly", "nth": 2}) == "2026-10-9"
    assert when({"day": "Friday", "repeat": "monthly", "nth": 1}) == "2026-10-2"
    assert when({"day": "Friday", "repeat": "monthly", "nth": -1}) == "2026-10-30"
    assert when({"day": "Friday", "repeat": "monthly", "nth": 1}, "2026-10-03") == "2026-11-6"
    assert when({"day": "Tuesday", "repeat": "weekly", "from": "2026-10-06", "until": "2026-12-29"}) == "2026-10-6"
    assert when({"day": "Tuesday", "repeat": "weekly", "from": "2026-10-06", "until": "2026-12-29"}, "2026-12-30") is None
    times = page.evaluate("""() => [sessionTime({ start: "19:00", end: "21:00" }), sessionTime({ start: "20:30", end: "23:00" }),
      sessionTime({ start: "11:00", end: "13:00" }), sessionTime({ start: "21:00" })]""")
    assert times == ["7–9pm", "8:30–11pm", "11am–1pm", "from 9pm"]
    # A session on announced dates: the next one to come (today's included), or none.
    on_dates = {"repeat": "dates", "dates": ["2026-10-22", "2026-11-19"]}
    assert when(on_dates) == "2026-10-22" and when(on_dates, "2026-10-22") == "2026-10-22"
    assert when(on_dates, "2026-10-23") == "2026-11-19" and when(on_dates, "2026-11-20") is None
    days = """([session, today]) => sessionDays(session, new Date(`${today}T12:00`))"""
    assert page.evaluate(days, [on_dates, "2026-10-02"]) == "Thursday 22 October"
    assert page.evaluate(days, [on_dates, "2026-12-01"]) == "No date announced yet"
    page.click(".lang-switch [data-lang=cy]")
    assert page.evaluate("""() => [sessionDays({ day: "Friday", repeat: "monthly", nth: 2 }), sessionDays({ day: "Tuesday", repeat: "weekly" }),
      sessionTime({ start: "21:00" })]""") == ["Ail ddydd Gwener y mis", "Bob dydd Mawrth", "o 9yh"]
    assert page.evaluate(days, [on_dates, "2026-12-01"]) == "Dim dyddiad wedi'i gyhoeddi eto"


def test_sessions_page(page, site):
    # Sessions by town, with a dot on the map for each town; filtering by day and area.
    page.goto_site("sesiynau/")
    page.wait_for_selector(".card.session")
    import build_site as b
    sessions = b.session_data()
    assert page.locator(".card.session").count() == len(sessions)
    assert page.locator(".session-list .town h2").first.inner_text().startswith("Aberystwyth")  # towns A to Z
    assert "Confirmed " in page.locator(".card.session").first.inner_text()
    towns = {s["town"] for s in sessions}
    assert page.locator(".wales-map circle:not(.target):not(.off)").count() == len(towns)
    page.click(".pills [data-day='Friday']")
    assert page.locator(".card.session").count() == sum(s["day"] == "Friday" for s in sessions)
    assert page.locator(".wales-map circle:not(.target):not(.off)").count() == len({s["town"] for s in sessions if s["day"] == "Friday"})
    # Each town's name beside its dot, as page text (sharp at any zoom), none overlapping.
    boxes = page.evaluate("""() => [...document.querySelectorAll('.town-label:not([hidden])')].map((l) => {
      const r = l.getBoundingClientRect(); return [r.left, r.right, r.top, r.bottom]; })""")
    assert len(boxes) == len({s["town"] for s in sessions if s["day"] == "Friday"})
    page.click(".pills [data-day='Friday']")  # again: every day
    boxes = page.evaluate("""() => [...document.querySelectorAll('.town-label:not([hidden])')].map((l) => {
      const r = l.getBoundingClientRect(); return [r.left, r.right, r.top, r.bottom]; })""")
    assert len(boxes) == len(towns)
    assert not [(a, b) for i, a in enumerate(boxes) for b in boxes[i + 1:] if a[0] < b[1] and a[1] > b[0] and a[2] < b[3] and a[3] > b[2]]
    page.select_option("#area-select", "Cardiff")
    assert page.locator(".card.session").count() == sum(s["county"] == "Cardiff" for s in sessions)
    # Opened from the sidebar, it's the page's own address.
    page.click(".brand")
    page.click(".sidebar-links a[href='sesiynau/']")
    page.wait_for_selector(".card.session")
    assert page.url == site + "sesiynau/"


def test_session_dates_in_welsh(page):
    # Welsh dates are written by the site (many browsers have none, and give English ones).
    page.goto_site("sesiynau/")
    page.wait_for_selector(".card.session")
    page.click(".lang-switch [data-lang=cy]")
    page.wait_for_function("document.querySelector('main h1').textContent === 'Sesiynau cyfredol'")
    import re
    text = page.inner_text("main")
    english = re.findall(r"\b(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday|January|February|March|April|June|July|"
                         r"August|September|October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\b", text)
    assert not english, english
    assert re.search(r"Cadarnhawyd \d+ (Ion|Chwef|Maw|Ebr|Mai|Meh|Gorff|Awst|Medi|Hyd|Tach|Rhag) 20\d\d", text)


def test_home_sessions_link_to_their_cards(page):
    # Tonight's session on the home page opens its card on the sessions page.
    page.goto_site()
    link = page.locator(".coming-up li a").first
    link.wait_for()
    target = link.get_attribute("href").split("#")[1]
    link.click()
    page.wait_for_function(f"document.activeElement && document.activeElement.id === '{target}'")
    assert page.locator(f"#{target}").is_visible()


def test_session_calendar(page):
    # "Add to calendar": an .ics file that repeats as the session does, in Welsh time.
    page.goto_site("sesiynau/")
    page.wait_for_selector(".card.session")
    with page.expect_download() as info:
        page.click("#session-ty-tawe-swansea-friday .session-links button")
    ics = Path(info.value.path()).read_bytes().decode("utf-8")  # as it is: CRLF line ends
    assert info.value.suggested_filename == "ty-tawe-swansea-friday.ics"
    unfolded = ics.replace("\r\n ", "")
    assert "RRULE:FREQ=MONTHLY;BYDAY=2FR" in unfolded and "DTSTART;TZID=Europe/London:" in unfolded and "T210000" in unfolded
    assert "TZID:Europe/London" in unfolded and "LOCATION:Tŷ Tawe\\, 9 Christina Street\\, Swansea SA1 4EW" in unfolded
    assert all(len(line.encode()) <= 75 for line in ics.split("\r\n"))  # long lines folded
    with page.expect_download() as info:
        page.click("#session-chapter-cardiff-tuesday .session-links button")
    unfolded = Path(info.value.path()).read_bytes().decode("utf-8").replace("\r\n ", "")
    assert "RRULE:FREQ=WEEKLY;BYDAY=TU;UNTIL=20261229T235959Z" in unfolded
    # A session on announced dates: an event for each date to come, none repeating.
    ics = page.evaluate("""() => sessionCalendar({ id: "y-llew-coch-llandeilo", venue: "Y Llew Coch", address: "Stryd y Bont",
      repeat: "dates", dates: ["2026-10-22", "2026-11-19"], start: "19:30" }, new Date(2026, 9, 22))""").replace("\r\n ", "")
    assert "RRULE:FREQ=WEEKLY" not in ics and "RRULE:FREQ=MONTHLY" not in ics and ics.count("BEGIN:VEVENT") == 2
    assert "DTSTART;TZID=Europe/London:20261022T193000" in ics and "DTEND;TZID=Europe/London:20261119T213000" in ics
    assert "UID:y-llew-coch-llandeilo-20261119@ysesiwn.cymru" in ics


@pytest.mark.parametrize("path, button", [
    ("sesiynau/", ".pills [data-day='Monday']"),
    ("?page=browse", ".pills [data-type='Jig']"),
    ("?page=browse", ".pills.keys [data-key='D major']"),
])
def test_filter_unchosen_on_a_phone(browser, site, path, button):
    # Tapping a filter again un-chooses it, and it looks un-chosen again (a phone keeps the
    # tapped button's hover look, so there is none).
    context = browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True, service_workers="block")
    page = context.new_page()
    page.goto(site + path)
    page.wait_for_selector(".card.session, .tune-list li", state="attached")
    page.add_style_tag(content="* { transition: none !important; }")
    look = "(b) => { const s = getComputedStyle(b); return [s.backgroundColor, s.borderColor, s.color]; }"
    plain = page.eval_on_selector(button, look)
    page.tap(button)
    assert page.get_attribute(button, "aria-pressed") == "true" and page.eval_on_selector(button, look) != plain
    page.tap(button)
    assert page.get_attribute(button, "aria-pressed") == "false" and page.eval_on_selector(button, look) == plain
    context.close()


def test_session_report(page):
    # "Been lately?" writes an email saying which session, and whether it's still on.
    page.goto_site("sesiynau/")
    page.wait_for_selector(".card.session")
    page.evaluate(CATCH_MAIL)
    card = page.locator("#session-ty-tawe-swansea-friday")
    card.locator("summary").click()
    card.locator("input[value='stopped']").check()
    card.locator("textarea").fill("Not on in September.")
    card.locator("button[type=submit]").click()
    _, subject, body = sent_mail(page)
    assert subject == "Y Sesiwn: session, Tŷ Tawe, Swansea (stopped)"
    assert "It has stopped." in body and "Not on in September." in body and "ty-tawe-swansea-friday" in body


def test_add_a_session(page, site):
    page.goto_site("sesiynau/")
    page.wait_for_selector(".add-session form", state="attached")
    assert not page.locator(".add-session form").is_visible()  # folded at the foot until it's wanted
    # The introduction links down to the form, staying on the page.
    page.click(".lead a[href='#add-session']")
    assert page.evaluate("document.activeElement.id") == "add-session" and page.url == site + "sesiynau/"
    page.evaluate(CATCH_MAIL)
    form = page.locator(".add-session form")
    fields = form.locator("input")
    fields.nth(0).fill("The Red Lion, Llandeilo")
    fields.nth(1).fill("Every Wednesday")
    fields.nth(2).fill("8-10pm")
    form.locator("button[type=submit]").click()
    _, subject, body = sent_mail(page)
    assert subject == "Y Sesiwn: a session, The Red Lion, Llandeilo"
    assert "Venue and town: The Red Lion, Llandeilo\nDay, and how often: Every Wednesday\nTime: 8-10pm" in body


def test_send_a_tune(page):
    page.goto_site("?page=add")
    page.wait_for_selector(".send-tune form")
    # The form first, then the GitHub way (without the note that sends GitHub readers here).
    assert page.locator("main h2").first.inner_text() == "Send us a tune"
    assert page.locator("main h2", has_text="Or add it yourself on GitHub").count() == 1
    assert page.locator("main h2", has_text="1. Write the tune in ABC").count() == 1
    assert not page.locator("main h2", has_text="1. Write the tune in ABC").is_visible()  # folded away
    page.click(".github-way > summary")
    assert page.locator("main h2", has_text="1. Write the tune in ABC").is_visible()
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
    # The ABC starts with its header, the title following the tune's name; a header alone isn't a tune.
    header = form.locator("[name=abc]").input_value()
    assert header == "X:1\nT:\nR:\nM:\nL:1/8\nK:\n"
    form.locator("[name=abc]").fill("T:Something\nABC def")
    page.wait_for_function("document.querySelector('.abc-problem').textContent.includes('K:')")
    form.locator("[name=abc]").fill(header)
    page.wait_for_selector(".abc-preview", state="hidden")
    form.locator("[name=name]").fill("Y Deryn Du")
    assert form.locator("[name=abc]").input_value() == "X:1\nT:Y Deryn Du\nR:\nM:\nL:1/8\nK:\n"
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
    page.click(".tune-actions .share")
    page.click(".tune-actions button:text-is('QR code')")
    page.wait_for_selector("dialog.qr-dialog[open] svg.qr")
    image = Image.open(io.BytesIO(page.locator("dialog svg.qr").screenshot()))
    assert [r.text for r in zxingcpp.read_barcodes(image)] == ["https://ysesiwn.cymru/alaw/glandyfi/?v=2"]
    page.keyboard.press("Escape")
    page.wait_for_selector("dialog.qr-dialog", state="detached")
    page.click(".tune-actions .share")  # again, and closed with its button
    page.click(".tune-actions button:text-is('QR code')")
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
        if path == "alaw/llancesau-trefaldwyn/":  # the first makes the set, named first ("My set", ready to type over)
            assert page.input_value(".set-namer input") == "My set"
            assert page.evaluate("document.activeElement.selectionEnd - document.activeElement.selectionStart") == len("My set")
            page.press(".set-namer input", "Enter")
        else:  # then it's in the list, with a new one
            menu = page.locator(".add-to-set-wrap .print-menu")
            assert menu.locator("button").all_inner_texts() == [f"My set\n{1 if key else 2} tune{'' if key else 's'}", "A new set"]
            menu.locator("button", has_text="My set").click()
    assert "(3 tunes)" in page.inner_text(".add-status")
    page.click(".add-status a")
    # The set opens as a music stand: its tunes and keys folded above the music
    page.wait_for_selector(".set-edit")
    assert not page.locator(".set-list").is_visible()
    # Your own set's name, to edit, is the page's heading; each tune's music is under its
    # number, name (to its page, in this key) and key, with a Play for practising it.
    assert page.locator("h1 > input.set-name").input_value() == "My set"
    heads = page.locator(".set-tune h2")
    assert [" ".join(t.split()) for t in heads.all_inner_texts()] == [
        "1. Llancesau Trefaldwyn · D major", "2. Glandyfi · A major", "3. Nyth y Gog · E minor"]
    assert heads.nth(1).locator("a").get_attribute("href") == "alaw/glandyfi/?v=2&key=A"
    assert page.get_attribute(".set-tune:nth-child(2) .preview-play", "aria-label") == "Play Glandyfi in A major"
    page.click(".set-edit > summary")
    assert page.locator(".set-list li > a").all_inner_texts() == ["Llancesau Trefaldwyn", "Glandyfi", "Nyth y Gog"]
    assert "?set=5A3V~h7o&n=My%20set&my=" in page.url  # Glandyfi (version 2) up two: ~h
    assert page.locator(".set-list li").nth(1).locator("select").input_value() == "2"
    page.locator(".set-list li").nth(1).locator("button[aria-label='Move up']").click()
    page.locator(".set-list li").nth(2).locator("button[aria-label^='Remove']").click()
    # A tune taken out can be put back, in its place and key.
    assert page.locator(".set-undo").inner_text().startswith("Removed Nyth y Gog.")
    page.click(".set-undo button")
    assert page.locator(".set-list li > a").all_inner_texts() == ["Glandyfi", "Llancesau Trefaldwyn", "Nyth y Gog"]
    assert not page.locator(".set-undo").is_visible()
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


def test_add_to_set_choosing_the_set(page):
    # With more than one set, Add to set opens to the list of them (the last added to
    # first), and a new one; choosing one adds the tune there.
    page.goto_site("alaw/glandyfi/")
    page.evaluate("""() => { localStorage.setItem('sets', JSON.stringify([
      { id: 'aaaaaa', name: 'Nos Iau', c: '5A', updated: 1 }, { id: 'bbbbbb', name: 'Class', c: '', updated: 2 }]));
      localStorage.setItem('currentSet', 'aaaaaa'); }""")
    page.reload()
    page.wait_for_selector(".score .abcjs-staff")
    assert page.locator(".which-set").count() == 0
    menu = page.locator(".add-to-set-wrap .print-menu")
    assert menu.is_hidden()
    page.click(".add-to-set")
    assert menu.locator("button").all_inner_texts() == ["Nos Iau\n1 tune", "Class\n0 tunes", "A new set"]
    menu.locator("button", has_text="Class").click()
    assert "Added to Class in G major (1 tune)" in page.inner_text(".add-status")
    assert menu.is_hidden()
    page.click(".add-to-set")  # now Class is first, ticked: it has the tune
    assert menu.locator("button").all_inner_texts()[:2] == ["Class\n1 tune · take it out", "Nos Iau\n1 tune"]
    menu.locator("button", has_text="A new set").click()
    # Named first: a name another set has isn't used twice; that set is offered instead
    assert page.evaluate("document.activeElement.matches('.set-namer input')")
    page.fill(".set-namer input", "nos iau")
    page.press(".set-namer input", "Enter")
    assert page.inner_text(".set-namer-hint") == "You have a set called Nos Iau already. Add it to Nos Iau"
    page.fill(".set-namer input", " Class ")
    page.press(".set-namer input", "Enter")
    assert page.inner_text(".set-namer-hint") == "Class has this tune already: give the new set another name."
    page.keyboard.press("Escape")  # put away
    assert page.locator(".set-namer").count() == 0
    page.click(".add-to-set")
    menu.locator("button", has_text="A new set").click()
    page.fill(".set-namer input", "Dydd Sadwrn")
    page.press(".set-namer input", "Enter")
    assert "Added to Dydd Sadwrn in G major (1 tune)" in page.inner_text(".add-status")
    kept = page.evaluate("JSON.parse(localStorage.getItem('sets'))")
    assert [(x["name"], len(x["c"])) for x in kept] == [("Nos Iau", 2), ("Class", 2), ("Dydd Sadwrn", 2)]


def test_add_to_set_knows_its_sets(page):
    # The tune page says which sets have the tune; in the menu they're ticked, and choosing
    # one takes it out (with Undo), so a set never has it twice by mistake.
    page.goto_site("alaw/glandyfi/")
    page.wait_for_selector(".score .abcjs-staff")
    code = page.evaluate("state.groups.get('glandyfi').versions[0].code")
    page.evaluate(f"""() => localStorage.setItem('sets', JSON.stringify([
      {{ id: 'aaaaaa', name: 'Nos Iau', c: '5A{code}', updated: 2 }}, {{ id: 'bbbbbb', name: 'Class', c: '5A', updated: 1 }}]))""")
    page.reload()
    page.wait_for_selector(".score .abcjs-staff")
    assert page.inner_text(".add-status") == "In your set Nos Iau"
    page.click(".add-to-set")
    menu = page.locator(".add-to-set-wrap .print-menu")
    assert menu.locator("button").all_inner_texts() == ["Nos Iau\n2 tunes · take it out", "Class\n1 tune", "A new set"]
    assert menu.locator("button.has-tune .tick-icon").count() == 1
    # The menu opens on the side with room, never over the sidebar.
    assert menu.bounding_box()["x"] >= page.locator("main").bounding_box()["x"]
    menu.locator("button", has_text="Nos Iau").click()
    assert page.inner_text(".add-status").startswith("Taken out of Nos Iau.")
    assert page.evaluate("JSON.parse(localStorage.getItem('sets'))[0].c") == "5A"
    page.click(".add-status button:text-is('Undo')")
    assert page.evaluate("JSON.parse(localStorage.getItem('sets'))[0].c") == f"5A{code}"
    assert page.inner_text(".add-status") == "In your set Nos Iau"
    page.click(".add-to-set")
    menu.locator("button", has_text="Class").click()
    assert page.inner_text(".add-status").startswith("Added to Class in G major (2 tunes)")
    page.goto_site("alaw/glandyfi/")
    page.wait_for_selector(".score .abcjs-staff")
    assert page.inner_text(".add-status") == "In your sets Nos Iau, Class"
    page.click(".add-status a >> nth=0")
    page.wait_for_selector(".set-list li", state="attached")


def test_current_page_marked(page):
    # The page you're on is marked in the sidebar (and the phone's menu), for screen readers too.
    page.goto_site("?page=browse")
    page.wait_for_selector(".pills")
    assert page.locator(".sidebar-links [aria-current='page']").all_inner_texts() == ["Browse by type and key"]
    page.click(".sidebar-links a[href='?page=notes']")
    page.wait_for_selector("#notes-search")
    assert page.locator(".sidebar-links [aria-current='page']").all_inner_texts() == ["Find a tune by its notes"]
    page.click(".brand")
    page.wait_for_selector("#hero-search")
    assert page.locator(".sidebar-links [aria-current]").count() == 0


def test_add_to_set_by_search(page):
    # On a set's page: type part of a name, press Enter, and it's added; the box is ready
    # for the next one straight away. Typos are forgiven, and the arrow keys pick another match.
    page.goto_site("?page=sets")
    page.click("text=New set")
    page.wait_for_selector("#set-add")
    # A new set opens with its name ready to type over, and its tunes unfolded
    assert page.evaluate("document.activeElement.matches('.set-name')")
    assert page.evaluate("document.activeElement.selectionEnd") == len("My set")
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
    second = page.locator("#set-add-list li > span[lang]").nth(1).inner_text()
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
    page.wait_for_selector(".set-list li", state="attached")
    assert page.inner_text("main h1") == "Nos Iau"
    assert page.locator(".set-list li > a").all_text_contents() == ["Glandyfi", "Llancesau Trefaldwyn"]
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
    page.wait_for_selector(".set-list li", state="attached")
    page.click(".set-actions .share")
    page.click("text=Copy as a list")
    assert page.evaluate("navigator.clipboard.readText()") == (
        "Nos Iau\n"
        "• Glandyfi (version 2): A major\n"
        "• Llancesau Trefaldwyn (version 1): D major\n"
        "https://ysesiwn.cymru/?set=3V~h5A&n=Nos%20Iau")
    assert page.inner_text(".set-shared") == "List copied"
    page.click(".lang-switch [data-lang=cy]")
    page.wait_for_selector(".set-list li", state="attached")
    page.click(".set-actions .share")
    page.click("text=Copïo fel rhestr")
    assert "• Glandyfi (fersiwn 2): A fwyaf" in page.evaluate("navigator.clipboard.readText()")
    context.close()


def test_set_codes_that_change(page):
    # A tune without a number when its link was made (".<short_id>") still opens once it
    # has one; sets kept in the browser in the first form are converted.
    page.goto_site()
    short_id = page.evaluate("state.bySlug.get('machynlleth').id")
    page.goto_site(f"?set=.{short_id}~a5A&n=Old")
    page.wait_for_selector(".set-list li", state="attached")
    assert page.locator(".set-list li > a").all_text_contents() == ["Machynlleth", "Llancesau Trefaldwyn"]
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
    page.wait_for_selector(".set-list li", state="attached")
    assert page.locator(".set-list li").count() == 100
    page.wait_for_selector(".set-paper svg")  # the music comes first, under the buttons
    assert 0 < page.locator(".set-paper svg").count() < 30
    page.evaluate("window.scrollTo(0, 0)")
    page.click(".set-actions .share")
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


def test_search_misses_counted(page):
    # A name search that finds nothing is counted (its words, once, after a pause); one
    # that finds tunes isn't.
    page.add_init_script("window.goatcounter = { count: (view) => (window.counted ||= []).push(view) }")
    page.goto_site("?page=browse")
    page.fill("#search-input", "glandy")
    page.fill("#search-input", "Zzyxq Wobble")
    page.wait_for_timeout(2000)
    page.fill("#search-input", "Zzyxq Wobble ")  # the same words again: not counted twice
    page.wait_for_timeout(2000)
    events = [v for v in page.evaluate("window.counted") if v.get("event")]
    assert events == [{"path": "search-miss/zzyxq-wobble", "title": "No tune found: zzyxq wobble", "event": True}]


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

def test_skip_link_and_tabbing_past_search(page):
    # The first Tab stop skips past the search and the menu to the page itself; and Tab
    # out of the search box goes on to the next control, not lost onto the page.
    page.goto_site("alaw/glandyfi/")
    page.wait_for_selector(".score .abcjs-staff")
    page.keyboard.press("Tab")
    assert page.evaluate("document.activeElement.className") == "skip-link"
    page.keyboard.press("Enter")
    assert page.evaluate("document.activeElement.id") == "main"
    assert page.url.endswith("/alaw/glandyfi/")  # not the home page (<base href> would send #main there)
    page.focus("#search-input")
    page.wait_for_selector("#suggestions:not([hidden])")
    page.keyboard.press("Tab")
    assert page.evaluate("document.activeElement.textContent") == "Cymraeg"


def test_score_and_player_names(page):
    # A screen reader hears the score's key (as transposed) and time, and the player's own
    # names for its buttons, with the repeat button saying whether it's on.
    page.goto_site("?tune=glandyfi")
    page.open_tools()
    page.wait_for_selector(".score .abcjs-staff")
    label = lambda: page.get_attribute(".score svg[role=img]", "aria-label")
    assert label() == 'Sheet Music for "Glandyfi": G major, 6/8 time'
    page.select_option("#key-select", "2")
    page.wait_for_function("document.querySelector('.score svg[role=img]').getAttribute('aria-label').includes('A major')")
    # Repeating is the Repeat menu's (the player's own repeat button is left out).
    assert page.locator(".abcjs-midi-loop").count() == 0
    assert page.inner_text("label[for=loop-select]") == "Repeat"
    assert not page.evaluate("state.synth.isLooping")
    page.select_option("#loop-select", "-1")
    page.wait_for_function("state.synth.isLooping")
    assert page.get_attribute(".abcjs-midi-start", "aria-label") == "Play (space bar)"  # "Pause (space bar)" while playing
    page.click(".lang-switch [data-lang=cy]")
    page.wait_for_function("document.querySelector('label[for=loop-select]').textContent === 'Ailadrodd'")
    assert label().startswith('Sgôr "Glandyfi": A fwyaf')


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
    for path in ["", "?page=browse", "?tune=glandyfi", "?tune=nyth-y-gog", "?page=map", "sesiynau/", "?page=offline", "?page=about", "?page=add",
                 "?page=contact", "?page=set&s=bne0o.6m42r~2&name=Nos%20Iau", "my:?set=3V~h5A&n=Nos%20Iau&my=aaaaaa", "?page=notes&q=D%20G%20B%20D%20C%20B%20G%20A", "cy:", "cy:?tune=glandyfi"]:
        if path.startswith("cy:"):  # in Welsh: the home page, and a page with the not-in-Welsh-yet note
            page.evaluate("localStorage.setItem('lang', 'cy')")
        if path.startswith("my:"):  # your own set: its name is a field to edit, in the heading
            page.evaluate("localStorage.setItem('sets', JSON.stringify([{ id: 'aaaaaa', name: 'Nos Iau', c: '3V~h5A', updated: 1 }]))")
        page.goto(site + path.removeprefix("cy:").removeprefix("my:"))
        # No fade-in: text caught half-faded would count as low contrast.
        page.add_style_tag(content="*, *::before, *::after { animation: none !important; transition: none !important; }")
        page.wait_for_function("typeof state !== 'undefined' && state.data && !document.querySelector('#main .loading')")
        for v in axe.run(page).response["violations"]:
            problems.append(f"{path or 'home'}: {v['id']} ({v['help']}) at {[n['target'] for n in v['nodes'][:3]]}")
    context.close()
    assert not problems, "\n".join(problems)



def test_melody_and_search_names_as_built(page):
    # tunes.json leaves out each tune's melody and search names: the app works them out
    # from the ABC and titles, and should get what build_site.py would.
    import build_site as b
    page.goto_site()
    page.wait_for_function("state.complete")
    got = page.evaluate("""() => state.data.tunes.map((t) => [t.slug,
      melodyOf(t).map((p) => String.fromCharCode(p + 160)).join(""), t.search])""")
    wrong = []
    for slug, melody, search in got:
        abc = (b.ROOT / "tunes" / slug / "tune.abc").read_text(encoding="utf-8")
        titles = b.parse_headers(abc).get("T") or [slug]
        if melody != b.melody_string(abc) or search != [b.normalize(t) for t in titles]:
            wrong.append(slug)
    assert len(got) == len(list(b.ROOT.glob("tunes/*/tune.abc"))) and not wrong, wrong


@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_chosen_key_stands_out(browser, site, scheme):
    # A chosen key is filled (not just a faint tint) and ticked, in light and dark mode.
    context = browser.new_context(color_scheme=scheme, service_workers="block")
    page = context.new_page()
    page.goto(site + "?page=browse&key=D%20major")
    page.wait_for_selector(".tune-list li", state="attached")
    look = """(b) => { const s = getComputedStyle(b); return [s.backgroundColor, s.color, getComputedStyle(b, '::before').content]; }"""
    chosen = page.eval_on_selector(".pills.keys [aria-pressed=true]", look)
    other = page.eval_on_selector(".pills.keys [aria-pressed=false]", look)
    assert chosen[0] != other[0] and chosen[1] != other[1]  # its own fill and text colour
    assert chosen[2] != "none" and other[2] == "none"  # the drawn tick
    context.close()


def test_browse_type_counts_follow_the_key(page):
    # Type counts follow the chosen key, as the key counts follow the type; a type with no
    # tunes in it is greyed out.
    page.goto_site("?page=browse")
    page.click(".pills.keys button[data-key='D major']")
    groups = page.evaluate("state.groupList.filter((g) => g.versions[0].key && `${g.versions[0].key.root} ${g.versions[0].key.modeName}` === 'D major').map((g) => g.type)")
    assert page.locator(".pills [data-type='Jig']").inner_text().endswith(f"· {groups.count('Jig')}")
    for t in page.evaluate("state.data.types.map((t) => t.name)"):
        assert page.locator(f".pills [data-type='{t}']").is_disabled() == (groups.count(t) == 0)


def test_browse_several_types_and_keys(page, site):
    # Types add up (jigs and polkas), keys add up (D or G), and the two narrow each other
    # down; clicking a chosen one again takes just that one off.
    page.goto_site("?page=browse")
    page.wait_for_selector(".tune-list li", state="attached")
    groups = page.evaluate("state.groupList.map((g) => [g.type, g.versions[0].key ? `${g.versions[0].key.root} ${g.versions[0].key.modeName}` : null])")
    count = lambda types=(), keys=(): sum((not types or t in types) and (not keys or k in keys) for t, k in groups)
    shown = lambda: page.locator(".tune-list li").count()
    page.click(".pills [data-type='Jig']")
    page.click(".pills [data-type='Polca']")
    assert shown() == count({"Jig", "Polca"})
    assert page.locator("p.caption", has_text="jigs and polkas").count() == 1
    page.click(".pills.keys [data-key='D major']")
    page.click(".pills.keys [data-key='G major']")
    assert shown() == count({"Jig", "Polca"}, {"D major", "G major"})
    assert page.locator("p.caption", has_text="jigs and polkas in G major or D major").count() == 1
    assert page.url == site + "?page=browse&type=Jig&type=Polca&key=G+major&key=D+major"
    page.click(".pills [data-type='Jig']")  # takes off just the jigs
    assert page.get_attribute(".pills [data-type='Polca']", "aria-pressed") == "true"
    assert shown() == count({"Polca"}, {"D major", "G major"})
    page.reload()  # the choice is in the address
    page.wait_for_selector(".tune-list li", state="attached")
    assert shown() == count({"Polca"}, {"D major", "G major"})


def test_type_page(page, site):
    # A type's own page (math/<type>/) opens the browse page with that type chosen, at
    # its own address; choosing another (as well) moves to the browse page's.
    page.goto_site("math/pibddawns/")
    page.wait_for_selector(".tune-list li", state="attached")
    assert page.get_attribute(".pills [data-type='Pibddawns']", "aria-pressed") == "true"
    assert page.url == site + "math/pibddawns/"
    page.click(".pills [data-type='Jig']")
    assert page.url == site + "?page=browse&type=Jig&type=Pibddawns"
    page.click(".tune-list a >> nth=0")
    page.wait_for_selector(".score .abcjs-staff")


def test_home_page_before_abcjs(browser, site):
    # The home page doesn't wait for abcjs (the sheet music), which follows it.
    context = browser.new_context(service_workers="block")
    page = context.new_page()
    page.route("**/abcjs-basic-min.js", lambda route: None)  # never answers
    page.goto(site)
    page.wait_for_selector(".features")
    assert page.evaluate("typeof ABCJS") == "undefined"
    context.close()


def test_music_size(page):
    # + makes the music bigger (laid out in shorter lines), − smaller; kept on this device.
    page.goto_site("alaw/a-honeyed-lip/")
    page.wait_for_selector(".score .abcjs-staff")
    staves = "document.querySelectorAll('.score .abcjs-staff').length"
    assert page.evaluate(staves) == 3
    page.click("[aria-label='Bigger music']")
    page.click("[aria-label='Bigger music']")
    assert page.evaluate(staves) > 3
    page.reload()
    page.wait_for_selector(".score .abcjs-staff")
    assert page.evaluate(staves) > 3
    for _ in range(4):
        if page.is_enabled("[aria-label='Smaller music']"):
            page.click("[aria-label='Smaller music']")
    assert page.is_disabled("[aria-label='Smaller music']")
    assert page.evaluate("JSON.parse(document.querySelector('.score [data-layout]').dataset.layout).staffwidth") > 740  # longer lines


def test_space_bar_plays(page):
    # Space plays or pauses, unless a control has the focus (then it's the control's).
    page.goto_site("?tune=glandyfi")
    page.wait_for_selector(".score .abcjs-midi-start")
    page.evaluate("window.presses = 0; document.querySelector('.score .abcjs-midi-start').addEventListener('click', () => presses++)")
    page.evaluate("document.activeElement.blur()")
    page.keyboard.press(" ")
    assert page.evaluate("presses") == 1
    page.focus("#key-select")
    page.keyboard.press(" ")
    assert page.evaluate("presses") == 1


def test_share_button(browser, site):
    # Where the device has a share sheet, Share's menu opens it with the tune's own address,
    # on a tune's page as on a set's.
    context = browser.new_context(service_workers="block")
    page = context.new_page()
    page.add_init_script("navigator.share = async (data) => { window.shared = data; }")
    page.goto(site + "?tune=glandyfi")
    page.click(".tune-actions .share")
    page.click(".tune-actions button:text-is('Send with an app…')")
    assert page.evaluate("window.shared") == {"title": "Glandyfi", "url": "https://ysesiwn.cymru/alaw/glandyfi/"}
    page.goto(site + "?set=3V~h5A&n=Nos%20Iau")
    page.click(".set-actions .share")
    page.click("#set-share-menu button:text-is('Send with an app…')")
    assert page.evaluate("window.shared.title") == "Nos Iau" and "?set=3V~h5A" in page.evaluate("window.shared.url")
    context.close()


def test_tablature_choices(page):
    page.goto_site("?tune=glandyfi")
    options = page.eval_on_selector_all("#tab-select option", "os => os.map((o) => o.value)")
    assert options == ["none", "mandolin", "guitar", "whistle-D", "whistle-C", "whistle-G", "whistle-Bb", "recorder"]


# ---- The notes page ---------------------------------------------------------------

def test_notes_page(page):
    # From the home page's invitation, typed notes are searched and kept in the address.
    page.goto_site()
    page.click(".notes-invite a[href='?page=notes']")
    page.fill("#notes-search", "D G B D C B G A")
    assert "q=D%20G%20B%20D%20C%20B%20G%20A" in page.url
    assert page.locator(".notes-results li a").first.inner_text() == "Glandyfi"
    # The best matches show their opening bars, with a play button.
    page.wait_for_function("document.querySelectorAll('.notes-results .preview-score svg').length === 5")
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
    playing = lambda b: b.get_attribute("data-playing") == "true"
    assert playing(button) and button.get_attribute("aria-label").startswith("Stop")
    # It really plays: abcjs stops the synth itself while getting it ready, which must
    # not count as pressing stop.
    page.wait_for_function("window.__started === 1")
    page.wait_for_timeout(500)
    assert playing(button)
    button.click()
    assert not playing(button) and button.get_attribute("aria-label").startswith("Play")
    # Starting another preview stops the first.
    button.click()
    page.locator(".notes-results .preview-play").nth(1).click()
    assert not playing(button)
    assert playing(page.locator(".notes-results .preview-play").nth(1))


def test_browse_groups_are_labelled(page):
    # The type and key buttons are two separate groups, each with a label (issue #7).
    page.goto_site("?page=browse")
    assert page.locator(".pills-label").all_text_contents() == ["Type", "Key"]
    types = page.locator(".pills").first.bounding_box()
    keys = page.locator(".pills.keys").bounding_box()
    assert keys["y"] - (types["y"] + types["height"]) > 30


ANDROID = "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0 Mobile Safari/537.36"
PHONE = {"user_agent": ANDROID, "is_mobile": True, "has_touch": True, "viewport": {"width": 390, "height": 844}}


def test_phone_controls_fold_into_one_line(browser, site):
    # On a phone the key, tempo and size are one line ("G, 112 bpm · Change"), with
    # full screen beside it, so the music starts high on the first screen; it opens to change them.
    context = browser.new_context(service_workers="block", **PHONE)
    page = context.new_page()
    page.goto(site + "?tune=glandyfi")
    page.wait_for_selector(".score .abcjs-inline-audio")
    summary = page.locator(".controls-summary")
    assert summary.inner_text().startswith("G, 112 bpm")  # the key in short
    assert not page.locator("#key-select").is_visible() and not page.locator(".music-size").is_visible()
    assert abs(summary.bounding_box()["y"] - page.locator(".practice-toggle").bounding_box()["y"]) < 5  # one line
    # Under the one line, and the folded practice tools; the type and "Say it" line under the
    # name may wrap to two, depending on the font (it does with Arial's widths, and on CI).
    assert page.locator(".score").bounding_box()["y"] < 520
    summary.click()
    assert summary.get_attribute("aria-expanded") == "true"
    assert page.locator(".music-size .label").is_visible()  # "Size", so − and + aren't taken for the key
    page.select_option("#key-select", "2")
    assert summary.inner_text().startswith("A (from G), 112 bpm")  # moved, so it says from what
    page.select_option("#key-select", "0")  # back to the written key, marked "(original)" in the menu
    assert summary.inner_text().startswith("G, 112 bpm")
    context.close()


def test_player_stays_in_reach(browser, site):
    # While the page follows the music, the player stays on screen (pinned under the top bar
    # on a phone), and says whether it's playing; its position bar is a slider for the keyboard.
    for args in [PHONE, {"viewport": {"width": 1280, "height": 800}}]:
        context = browser.new_context(service_workers="block", **args)
        page = context.new_page()
        page.goto(site + "?tune=glandyfi")
        page.wait_for_selector(".score .abcjs-inline-audio")
        start = page.locator(".abcjs-midi-start")
        assert start.get_attribute("aria-label") == "Play (space bar)"
        start.click()
        page.wait_for_function("document.querySelector('.abcjs-note_playing')")
        assert start.get_attribute("aria-label") == "Pause (space bar)"
        page.evaluate("window.scrollTo(0, 600)")
        box = start.bounding_box()
        assert 0 <= box["y"] and box["y"] + box["height"] <= args["viewport"]["height"]
        seek = page.locator(".score .seek")  # a real slider over abcjs's position bar (a button)
        assert seek.get_attribute("type") == "range" and seek.get_attribute("aria-label") == "Position in the tune"
        start.click()  # pause
        seek.focus()
        page.keyboard.press("End")
        assert int(seek.input_value()) == 100 and page.evaluate("state.synth.percent") > .9
        assert seek.get_attribute("aria-valuetext").endswith("%)")
        context.close()


@pytest.mark.parametrize("phone", [True, False])
def test_score_leaves_out_the_name(browser, site, phone):
    # The heading names the tune: the score doesn't repeat it, except printed.
    context = browser.new_context(service_workers="block", **(PHONE if phone else {}))
    page = context.new_page()
    page.goto(site + "?tune=glandyfi")
    page.wait_for_selector(".score .abcjs-staff")
    assert page.locator(".score .abcjs-title").count() == 0
    page.evaluate("dispatchEvent(new Event('beforeprint'))")
    assert page.locator(".score .abcjs-title").text_content() == "Glandyfi"
    page.evaluate("dispatchEvent(new Event('afterprint'))")
    assert page.locator(".score .abcjs-title").count() == 0
    context.close()


def test_copy_link(page):
    # Copy link, in Share's menu: the tune's link, said on the line under the buttons.
    page.goto_site("?tune=glandyfi")
    page.wait_for_selector(".score .abcjs-inline-audio")
    page.context.grant_permissions(["clipboard-read", "clipboard-write"])
    # Copied (asynchronously: wait for it), or, where the clipboard is refused, offered to copy by hand.
    offered = []
    page.on("dialog", lambda d: (offered.append(d.default_value), d.dismiss()))
    page.click(".tune-actions .share")
    page.click(".tune-actions button:text-is('Copy link')")
    for _ in range(50):
        if offered or page.inner_text(".share-status") == "Link copied":
            break
        page.wait_for_timeout(100)
    link = offered[0] if offered else page.evaluate("navigator.clipboard.readText()")
    assert offered or page.inner_text(".share-status") == "Link copied"
    assert link.startswith("https://ysesiwn.cymru/alaw/glandyfi/")


def test_phone_downloads_no_piano_notes_until_play(browser, site):
    # On a phone (not the installed app), reading the music downloads no piano notes, on
    # any page, until Play is pressed: at the session the music is mostly read. Then that
    # tune's notes come, and the rest of the piano's in the background.
    context = browser.new_context(**PHONE)
    fetched = []
    context.on("request", lambda r: fetched.append(r.url) if "/soundfont/" in r.url else None)
    page = context.new_page()
    for path in ["", "?page=browse", "?page=notes", "?page=sets", "alaw/glandyfi/", "alaw/walts-dinefwr/?v=1", "?set=5A3V~h&n=Nos%20Iau"]:
        page.goto(site + path)
        page.wait_for_timeout(1500)
    page.goto(site + "alaw/glandyfi/")
    page.wait_for_function("state.offlineReady && state.sounds", timeout=30000)
    page.click(".controls-summary")  # changing the key or tempo doesn't play either
    page.select_option("#key-select", "2")
    page.wait_for_timeout(1000)
    assert fetched == []
    page.click(".score .abcjs-midi-start")
    page.wait_for_function("document.querySelector('.abcjs-note_playing')", timeout=30000)
    assert fetched
    context.close()


def test_sound_note_under_the_player(browser, site):
    # On a phone, once a tune is played, every piano note is saved by itself. Before that,
    # with no signal, Play waits for a signal and says why (rather than playing silence);
    # with some notes saved, it says which will still sound.
    context = browser.new_context(**PHONE)
    page = context.new_page()
    page.goto(site + "?tune=glandyfi")
    page.wait_for_function("state.offlineReady && state.sounds", timeout=30000)
    note = page.locator(".sound-note")
    assert note.is_hidden() and page.locator(".score .save-sounds").count() == 0
    context.set_offline(True)
    page.evaluate("dispatchEvent(new Event('offline'))")
    assert "no piano sounds on this device yet" in note.inner_text()
    assert page.locator(".abcjs-midi-start").is_disabled()
    assert note.bounding_box()["y"] < page.locator(".score .abcjs-staff").first.bounding_box()["y"]  # above the music
    page.evaluate("state.sounds = { saved: 5, total: 90 }; refreshOfflineCards()")  # a few notes played before
    assert "notes you've played before will sound" in note.inner_text()
    assert page.locator(".abcjs-midi-start").is_enabled()
    context.set_offline(False)
    page.evaluate("dispatchEvent(new Event('online'))")
    page.evaluate("soundPlayed()")
    page.wait_for_function("state.sounds.saved === state.sounds.total", timeout=30000)
    assert note.is_hidden()
    context.close()


def test_print_list_and_chart_words(page):
    # Print / save is a plain list of buttons (no menu roles promised): Esc closes it and
    # puts focus back on its button. The chord chart is read bar by bar, in words.
    page.goto_site("?tune=glandyfi")
    page.wait_for_selector(".score .abcjs-staff")
    toggle = page.locator("[aria-controls^=print-menu]")
    assert toggle.get_attribute("aria-haspopup") is None and page.locator("[role=menu], [role=menuitem]").count() == 0
    toggle.click()
    assert page.locator("[id^=print-menu]").is_visible() and toggle.get_attribute("aria-expanded") == "true"
    page.locator("[id^=print-menu] button").first.focus()
    page.keyboard.press("Escape")
    assert page.locator("[id^=print-menu]").is_hidden()
    assert page.evaluate("document.activeElement === document.querySelector('[aria-controls^=print-menu]')")
    words = page.text_content(".chart-box .visually-hidden")
    assert words.startswith("Bar 1: repeat from here, G.") and "; repeat." in words
    assert page.get_attribute(".chart-box .chart", "aria-hidden") == "true"


def test_full_screen_leaves_practice_tools_as_they_were(browser, site):
    # The music stand opens the practice tools; leaving it puts them back as the reader had
    # them (folded on a phone), for this tune and the next.
    context = browser.new_context(service_workers="block", **PHONE)
    page = context.new_page()
    page.goto(site + "alaw/glandyfi/")
    page.wait_for_selector(".score .abcjs-inline-audio")
    tools = page.locator(".practice-tools")
    assert tools.get_attribute("open") is None
    page.click(".practice-toggle")
    assert tools.get_attribute("open") is not None
    page.click(".practice-toggle")
    assert tools.get_attribute("open") is None
    page.evaluate("navigate('?tune=cawl-cennin')")  # the next tune, in the same visit
    page.wait_for_function("document.querySelector('main h1')?.textContent === 'Cawl Cennin'")
    page.wait_for_selector(".score .abcjs-inline-audio")
    assert page.locator(".practice-tools").get_attribute("open") is None
    context.close()


def test_summary_says_the_key_changes(browser, site):
    # Walts Dinefwr goes from G to D and back: the phone's one line says the key changes.
    context = browser.new_context(service_workers="block", **PHONE)
    page = context.new_page()
    page.goto(site + "alaw/walts-dinefwr/")
    page.wait_for_selector(".score .abcjs-inline-audio")
    assert page.inner_text(".controls-summary .now") == "G → D, 100 bpm"
    page.goto(site + "alaw/glandyfi/")
    page.wait_for_selector(".score .abcjs-inline-audio")
    assert "→" not in page.inner_text(".controls-summary .now")
    context.close()


def test_chord_settings_with_the_practice_tools(page):
    # The paper is the player and the music; a tune's chord settings are among the practice
    # tools, by what they change: what's heard (Hear), shown on the sheet music or not (See).
    page.goto_site("?tune=glandyfi")
    page.wait_for_selector(".score .abcjs-inline-audio")
    assert page.locator(".score .playback").count() == 0
    groups = page.locator(".practice-tools .practice-group")
    assert [g.get_attribute("aria-label") for g in groups.all()] == ["Hear", "Practise", "See"]
    assert groups.nth(0).locator("input[name=chord-playback]").count() == 3
    assert groups.nth(2).locator("text=Chords on the sheet music").count() == 1
    assert page.locator(".card.chords input[type=checkbox]").count() == 0
    page.goto_site("?tune=cawl-cennin")  # no chords, no chord settings
    page.wait_for_selector(".score .abcjs-inline-audio")
    assert page.locator("input[name=chord-playback], .chords-on-score").count() == 0
    assert [g.get_attribute("aria-label") for g in page.locator(".practice-group").all()] == ["Practise", "See"]


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
    assert page.inner_text(".copy-all-sets") == "Links copied"
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


def test_moved_tune(page, site):
    # A tune renamed (moved.json): its old address, its old code in set links and the key
    # kept for it on this device all find it under its new name. tunes.json is given a
    # move here, from a made-up old name to Glandyfi.
    import json

    def with_move(route):
        index = json.loads(route.fetch().text())
        index["moved"] = [{"from": "hen-glandyfi", "to": "glandyfi", "code": "zz", "id": "zzzzz"}]
        route.fulfill(json=index)

    page.route("**/tunes.json", with_move)
    page.goto(site)
    page.evaluate("localStorage.setItem('keys', JSON.stringify({ 'hen-glandyfi': 2 }))")
    page.goto_site("?tune=hen-glandyfi")
    page.wait_for_selector(".score .abcjs-staff")
    assert page.url.endswith("/alaw/glandyfi/?key=A")  # Glandyfi is in G: 2 up, as kept for its old name
    assert page.inner_text("h1") == "Glandyfi" and page.input_value("#key-select") == "2"
    page.goto_site("?set=zz~h")
    page.wait_for_selector(".set-list li", state="attached")
    assert page.text_content(".set-list li a") == "Glandyfi" and page.input_value(".set-list select") == "2"


def test_tune_page_without_tunes_json(page, site):
    # A tune's page comes with its own data: if tunes.json can't be had (a bad connection),
    # the tune stays on the page, and the sidebar works from the start.
    page.route("**/tunes.json", lambda route: route.abort())
    page.goto(site + "alaw/glandyfi/")
    page.wait_for_selector(".score .abcjs-staff")
    page.wait_for_timeout(500)  # tunes.json has failed by now
    assert page.inner_text("main h1") == "Glandyfi"
    page.click(".lang-switch [data-lang=cy]")
    page.wait_for_selector("main h2:text('Manylion')")
    assert page.inner_text("main h1") == "Glandyfi"


def test_tune_page_without_audio(browser, site):
    # A browser without Web Audio shows the music and says it can't play it (no error).
    context = browser.new_context(service_workers="block")
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.add_init_script("delete window.AudioContext; delete window.webkitAudioContext;")
    page.goto(site + "alaw/glandyfi/")
    page.wait_for_selector(".score .abcjs-staff")
    assert "Audio is not supported" in page.inner_text(".score .audio")
    assert page.locator("#loop-select option").count() > 1
    assert not errors, errors
    context.close()


def test_guides_run_nothing(page, site):
    # The guides are Markdown anyone can suggest changes to: HTML in them that could run
    # is taken out. A guide that can't be fetched says so.
    def with_html(route):
        text = route.fetch().text().replace(
            "# How to submit corrections\n",
            "# How to submit corrections\n\n<img src=x onerror=\"window.ran = 1\"> <script>window.ran = 2</script>\n"
            "<a href=\"javascript:window.ran = 3\">here</a> <iframe src=\"about:blank\"></iframe>\n\n", 1)
        route.fulfill(body=text, content_type="text/markdown")

    page.route("**/CONTRIBUTING.md", with_html)
    page.goto_site("?page=fix")
    page.wait_for_selector("article.guide img")
    page.click("article.guide a:text('here')")
    page.wait_for_timeout(300)
    assert page.evaluate("window.ran") is None
    assert page.locator("article.guide [onerror], article.guide script, article.guide iframe").count() == 0
    page.route("**/about.md", lambda route: route.abort())
    page.goto_site("?page=about")
    page.wait_for_selector("main p:has-text('load this page')")


def test_playback_carries_on_through_a_change(page):
    # Changing the tempo (or the key, or turning a phone) draws the music again: a tune
    # that was playing carries on, from about where it was.
    page.goto_site("alaw/glandyfi/")
    page.wait_for_selector(".score .abcjs-staff")
    page.click(".abcjs-midi-start")
    page.wait_for_function("state.synth.isStarted && state.synth.percent > 0.05", timeout=15000)
    before = page.evaluate("state.synth.percent")
    page.fill("#tempo", "150")
    page.dispatch_event("#tempo", "change")
    page.wait_for_function(f"state.synth.isStarted && state.synth.percent >= {before}", timeout=15000)
    page.click(".abcjs-midi-start")  # pause


def test_no_flash_of_the_static_page(browser, site):
    # The page as written for search engines isn't shown where the app runs: while the tunes
    # load there's nothing but (after a moment) "Loading tunes…". Without JavaScript it's
    # all there; and if the app never comes, it shows after 8 s.
    import time
    context = browser.new_context(service_workers="block")
    page = context.new_page()
    page.route("**/tunes.json", lambda route: (time.sleep(1.5), route.continue_()))
    page.goto(site, wait_until="commit")
    page.wait_for_selector("#main .loading")
    assert page.locator("#main .static").is_hidden()
    page.wait_for_selector("#main .loading", state="visible")
    page.wait_for_selector("#hero-search")
    assert page.locator("#main .static").count() == 0
    context.close()
    context = browser.new_context(service_workers="block", java_script_enabled=False)
    page = context.new_page()
    page.goto(site + "math/jig/")
    assert page.locator("#main .static h1").is_visible() and page.locator("#main .static li a").count() > 50
    context.close()
    context = browser.new_context(service_workers="block")
    page = context.new_page()
    page.clock.install()
    page.route("**/app.js", lambda route: route.abort())
    page.goto(site)
    assert page.locator("#main .static").is_hidden()
    page.clock.run_for(9000)
    page.wait_for_selector("#main .static .type-links", state="visible")
    context.close()


def test_touch_targets(browser, site):
    # On a phone, every control is at least 24px each way (WCAG 2.5.8); links inside text don't count.
    context = browser.new_context(viewport={"width": 320, "height": 640}, is_mobile=True, has_touch=True,
                                  service_workers="block")
    page = context.new_page()
    small = {}
    for path in ["", "alaw/tros-y-garreg/", "?set=3V~h5A&n=Nos%20Iau", "?page=sets", "?page=add", "?page=contact", "?page=browse", "sesiynau/"]:
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
    page.click(".set-edit > summary")
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
    page.click(".set-edit > summary")  # (which scrolls up to it)
    page.focus("#set-add")
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


def test_tune_page_before_the_other_tunes(page, site):
    # A tune's own page carries that tune, so its music is drawn without waiting for
    # tunes.json; a link to anywhere else waits for the rest, then opens as usual.
    held = []
    page.route("**/tunes.json", lambda route: held.append(route))
    page.goto(site + "alaw/tros-y-garreg/")
    page.wait_for_selector(".score .abcjs-staff")
    assert page.evaluate("state.complete") is False
    page.click("a[href='?page=browse']")
    page.wait_for_timeout(200)
    assert page.locator(".score .abcjs-staff").count() > 0  # still the tune, for now
    held[0].continue_()
    page.wait_for_selector(".pills")
    assert page.evaluate("state.groupList.length") > 500


def test_music_stand_on_a_phone(browser, site):
    # Full screen on a phone is a music stand: the key and tempo folded into their line even
    # if they were open, the player pinned at the top, and the playing line kept in view
    # (when the tune is longer than the screen: a short one stays put).
    context = browser.new_context(service_workers="block", **PHONE)
    page = context.new_page()
    page.goto(site + "alaw/walts-dinefwr/?tempo=200")  # a long tune: more than a screen, even on the stand
    page.wait_for_selector(".score .abcjs-inline-audio")
    page.click(".controls-summary")
    page.click(".practice-toggle")
    assert not page.locator("#key-select").is_visible()
    assert page.locator(".score").bounding_box()["y"] < 200
    page.click(".score .abcjs-midi-start")
    page.wait_for_function("document.querySelector('.abcjs-note_playing')")
    page.evaluate("state.synth.seek(.6)")  # on to the lines further down
    page.wait_for_function("scrollY > 100", timeout=30000)  # followed the music down
    assert page.locator(".score > .audio").bounding_box()["y"] < 5  # pinned
    context.close()


def test_tempo_and_key_shortcuts(page):
    page.goto_site("alaw/glandyfi/")
    page.wait_for_selector(".score .abcjs-staff")
    page.keyboard.press("]")
    page.keyboard.press(".")
    assert page.input_value("#tempo") == "117" and page.input_value("#key-select") == "1"
    assert page.url.endswith("alaw/glandyfi/?key=Ab&tempo=117")


def test_browse_grouped_by_type_with_keys(page):
    # With nothing chosen, the types are the pills and the tunes one folded list, A to Z,
    # each with its key; the less common keys wait behind "More keys"; something chosen
    # lists the tunes under their types; one type chosen is a plain list.
    page.goto_site("?page=browse")
    page.wait_for_selector(".all-tunes")
    assert page.locator(".type-group").count() == 0
    assert page.locator(".tune-list li").count() == len(page.evaluate("state.groupList"))
    assert not page.locator(".tune-list li").first.is_visible()
    page.click("details.all-tunes > summary")
    assert page.locator(".tune-list li").first.is_visible()
    # In English, the Welsh type names say what they are, where the English word differs.
    assert page.locator(".pills [data-type='Walts'] .gloss").inner_text().strip() == "(waltz)"
    assert page.locator(".pills [data-type='Jig'] .gloss").count() == 0
    assert page.locator("a[href='alaw/glandyfi/'] + .tune-key").inner_text() == "G"
    shown = lambda: page.locator(".pills.keys [data-key]:visible").count()
    assert shown() == 6 and page.locator(".more-keys").is_visible()
    page.click(".more-keys")
    assert shown() > 6 and not page.locator(".more-keys").is_visible()
    page.goto_site("?page=browse&key=D%20major")  # something chosen: under their types, open
    page.wait_for_selector(".tune-list li", state="attached")
    assert page.locator("section.type-group").count() > 1 and page.locator(".tune-list li").first.is_visible()
    page.goto_site("?page=browse&type=Jig&key=D%20major")
    page.wait_for_selector(".tune-list li", state="attached")
    assert page.locator(".type-group").count() == 0 and page.locator(".tune-key").count() == 0  # the key goes without saying
    page.goto_site("?page=browse&key=A%20Dorian")  # a less common key, chosen: the keys stay open
    page.wait_for_selector(".tune-list li", state="attached")
    assert not page.locator(".more-keys").is_visible()


def test_browse_link_on_a_phone_folds_the_choices(browser, site):
    # A shared Browse link on a phone: the choices in one line, the tunes on the first
    # screen; Change opens them again.
    context = browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True,
                                  service_workers="block")
    phone = context.new_page()
    phone.goto(site + "?page=browse&type=Jig&key=D%20major")
    phone.wait_for_selector(".tune-list li")
    assert phone.locator(".browse-chosen .now").inner_text() == "Jig · D major"
    assert not phone.locator(".pills [data-type='Jig']").is_visible()
    assert phone.locator(".tune-list li").first.bounding_box()["y"] < 844 - 100
    phone.click(".browse-chosen .change")
    assert phone.locator(".pills [data-type='Jig']").is_visible() and not phone.locator(".browse-chosen").is_visible()
    context.close()


def test_versions_told_apart(page):
    # Two versions from the same book in the same key: the one with a name of its own says
    # it, and so the other says the tune's own name.
    page.goto_site("alaw/merch-megan/")
    page.wait_for_selector(".score .abcjs-staff")
    labels = page.locator(".versions a small").all_inner_texts()
    assert labels[0].endswith("“Merch Megan”") and labels[3].endswith("“Merch Megan syml”")
    assert len(set(labels)) == len(labels)


def test_tunes_not_loading_offers_to_try_again(browser, site):
    # No tunes (no signal on a first visit): a plain sentence and Try again, not an error's text.
    context = browser.new_context(service_workers="block")
    page = context.new_page()
    page.route("**/tunes.json*", lambda route: route.abort())
    page.goto(site)
    page.wait_for_selector("main .primary")
    text = page.inner_text("main")
    assert "Check your connection" in text and "TypeError" not in text
    assert page.locator("main button.primary").inner_text() == "Try again"
    context.close()


def test_a_moved_key_says_so_when_shared(browser, site):
    # A shared link in another key: the page says where it's from, Copy link and the QR code
    # say what the link carries.
    context = browser.new_context(service_workers="block", permissions=["clipboard-read", "clipboard-write"])
    page = context.new_page()
    page.goto(site + "alaw/glandyfi/?key=A&tempo=80")
    page.wait_for_selector(".score .abcjs-inline-audio")
    page.click(".tune-actions .share")
    page.click(".tune-actions button:text-is('Copy link')")
    page.wait_for_function("document.querySelector('.share-status').innerText.startsWith('Link copied')")  # once the clipboard has it
    assert page.inner_text(".share-status") == "Link copied, in A major, at 80 bpm"
    page.click(".tune-actions .share")
    page.click(".tune-actions button:text-is('QR code')")
    assert "this tune, in A major, at 80 bpm." in page.inner_text(".qr-dialog .caption >> nth=0")
    page.keyboard.press("Escape")
    page.select_option("#key-select", "0")
    assert "key=" not in page.url
    context.close()


def test_deleting_a_set_can_be_undone(page):
    page.goto_site("?page=sets")
    page.evaluate("saveSets([{ id: 'a', name: 'Workshop', c: '', updated: 1 }])")
    page.goto_site("?page=sets")
    page.wait_for_selector(".set-list-mine li")
    page.click(".set-list-mine .link-button")  # no "are you sure?": it's undone instead
    assert page.locator(".set-list-mine li").count() == 0
    assert page.inner_text(".set-undo") .startswith("Deleted “Workshop”.")
    page.click(".set-undo button")
    assert page.inner_text(".set-list-mine li a") == "Workshop" and page.locator(".set-undo").count() == 0


def test_notes_results_say_only_what_differs(page):
    # The count says these start like this; each result only says so if it's different.
    page.goto_site("?page=notes&q=G%20B%20D%20C%20B%20G%20A")
    page.wait_for_selector(".notes-results li")
    first = page.locator(".notes-results li").first.inner_text()
    assert "starts like this" not in first


def test_set_music_in_the_site_typeface(page):
    # A set's music is drawn as a tune's page draws it: its credit and tempo in the site's
    # own typeface, never abcjs's Times.
    page.goto_site("?set=3V~h5A&n=Nos%20Iau")
    page.wait_for_selector(".set-paper .abcjs-staff")
    fonts = page.eval_on_selector_all(".set-paper svg text", "ts => [...new Set(ts.map((t) => getComputedStyle(t).fontFamily))]")
    assert fonts and all("system-ui" in f for f in fonts), fonts


def test_music_size_says_its_size(page):
    page.goto_site("alaw/glandyfi/")
    page.wait_for_selector(".score .abcjs-staff")
    assert page.inner_text(".music-size .label") == "Size: 100%"
    page.click("[aria-label='Bigger music']")
    assert page.inner_text(".music-size .label") == "Size: 125%"
    assert page.get_attribute(".music-size", "aria-label") == "Size of the music: 125%"


def test_browse_says_what_the_types_are(page):
    # With nothing chosen, what each type is, under the folded list; gone once one is chosen.
    page.goto_site("?page=browse")
    about = page.locator(".types-about")
    assert about.locator("dt").first.inner_text() == "Jig"
    assert about.locator("dd").count() == page.locator(".pills button[data-type]").count()
    page.click(".pills button[data-type='Jig']")
    assert about.count() == 0


def test_home_features_only_on_a_first_visit(page):
    # "What you can do" is for a first visit: once a tune has been opened here, the home page
    # has Recently opened instead.
    page.goto_site()
    page.wait_for_selector(".features")
    page.goto_site("alaw/glandyfi/")
    page.wait_for_selector(".score .abcjs-staff")
    page.goto_site()
    page.wait_for_selector(".recent-list")
    assert page.locator(".features").count() == 0
