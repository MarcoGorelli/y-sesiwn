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
          const abc = accompaniment(setTempo(stripFields(tune.abc, "SZBNA"), tune.beat, tune.bpm), play === "both");
          const lines = ABCJS.renderAbc("*", abc)[0].lines;
          const notes = lines.flatMap((l) => l.staff?.[0].voices[0] ?? []).filter((e) => e.el_type === "note");
          if (!notes.length) empty.push(`${tune.slug} (${play})`);
        }
      }
      return empty;
    }""")
    assert empty == []


@pytest.mark.parametrize("slug", ["pibddawns-gwyr-gwrecsam", "glandyfi", "nyth-y-gog", "erddygan-y-pibydd-coch"])
def test_tune_page(page, slug):
    page.goto_site(f"?tune={slug}")
    page.wait_for_selector(".score .abcjs-staff")
    assert page.locator(".score .abcjs-note").count() > 20
    assert page.locator(".abcjs-inline-audio").count() == 1


def test_transposing(page):
    page.goto_site("?tune=glandyfi")
    page.wait_for_selector(".chart .bar")
    first = lambda: page.locator(".chart .beats span").first.inner_text()
    assert first() == "G"
    page.select_option("#key-select", "2")  # up a tone: G major -> A major
    page.wait_for_function("document.querySelector('.chart .beats span').textContent === 'A'")
    assert "F♯m" in page.locator(".chart").inner_text()  # Em -> F#m


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
    ("Sheet music", True, False, False),
    ("Sheet music with chords", True, True, False),
    ("Chord chart", False, False, True),
])
def test_print(page, mode, score, chords_on_score, chart):
    page.goto_site("?tune=glandyfi")
    page.wait_for_selector(".chart .bar")
    page.evaluate("window.print = () => {}")  # the real print dialog can't be driven
    page.select_option("#key-select", "2")  # prints in the key chosen on the page
    page.click("text=Print ▾")
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
    page.click("text=Print ▾")
    assert page.locator(".print-menu").is_visible()
    page.mouse.click(5, 900)  # clicking elsewhere closes it
    assert not page.locator(".print-menu").is_visible()
    page.goto_site("?tune=cawl-cennin")  # no chords: a plain Print button
    assert page.locator(".tune-actions button").first.inner_text() == "Print"


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
    results = page.evaluate("(n) => searchByNotes(n).map((r) => [r.tune.group, r.how])", notes)
    assert results[0][0] == group and how in results[0][1], results[:3]


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
    assert page.locator(".card.place h2").inner_text() == "Machynlleth"


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


@pytest.mark.parametrize("path", ["", "?page=browse", "?tune=glandyfi", "?page=map", "?page=offline", "?page=about",
                                  "?page=notes&q=D%20G%20B%20D%20C%20B%20G%20A"])
def test_fits_a_phone(browser, site, path):
    context = browser.new_context(viewport={"width": 360, "height": 800}, service_workers="block")
    page = context.new_page()
    page.goto(site + path)
    page.wait_for_timeout(700)
    assert page.evaluate("document.documentElement.scrollWidth") <= 360
    context.close()


def test_home_page(page):
    page.goto_site()
    features = page.locator(".features li").all_inner_texts()
    assert len(features) >= 8 and any("Accompaniment" in f for f in features)
    assert page.locator(".offline-card").is_visible()
    # Browsing every tune has its own page; the home page links to it.
    assert page.locator(".tune-list").count() == 0
    page.click("a.button-link:has-text('Browse all')")
    page.wait_for_selector(".tune-list li")
    assert page.locator(".tune-list li").count() == len(page.evaluate("state.groupList"))


# The home page's text, sidebar and footer as the reader sees them, except text marked
# lang="en" on purpose (the "English" button, browsers' own menu names).
VISIBLE_TEXT = """() => {
  const texts = [];
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  while (walker.nextNode()) {
    if (!walker.currentNode.parentElement.closest('.lang-switch, .suggestions, strong[lang="en"]')) texts.push(walker.currentNode.textContent.trim());
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
    assert page.inner_text("#home-button") == "Yn ôl i'r hafan"
    assert page.get_attribute("#search-input", "placeholder") == "Chwilio am alaw…"
    assert page.locator(".features li").count() == 12
    # Nothing left in English: no sentence of the English page shows up in the Welsh one.
    welsh = page.evaluate(VISIBLE_TEXT)
    fragments = {f.strip() for f in re.split(r"[.:;?!()\n]", english) if len(f.strip()) >= 12}
    assert fragments and not [f for f in fragments if f in welsh]
    # The choice is remembered.
    page.reload()
    page.wait_for_function("typeof state !== 'undefined' && state.data")
    assert page.inner_text("h1") == "Croeso i'r Sesiwn!"
    # Only the home page is translated so far: other pages say they're English.
    page.click(".sidebar-links a[href='?page=browse']")
    page.wait_for_selector(".tune-list li")
    assert page.get_attribute("#main", "lang") == "en"
    assert page.inner_text(".sidebar-links a[href='?page=browse']") == "Pori yn ôl math a chywair"
    page.click("#home-button")
    page.click(".lang-switch [data-lang=en]")
    assert page.inner_text("h1") == "Croeso! Welcome to Y Sesiwn"
    assert page.inner_text("#home-button") == "Back to home"
    assert page.evaluate(VISIBLE_TEXT) == english


def test_untranslated_pages_say_so(page):
    # In Welsh, the pages that are still English say so at the top.
    page.goto_site("?page=browse")
    assert page.locator(".lang-note").count() == 0
    page.click(".lang-switch [data-lang=cy]")
    assert page.inner_text("#main > .lang-note:first-child") == "Dyw'r dudalen hon ddim ar gael yn Gymraeg eto: dyma hi yn Saesneg."
    assert page.get_attribute(".lang-note", "lang") == "cy"
    for link in ["?page=about", "?page=map", "?page=notes"]:  # About is fetched first, then drawn
        page.click(f".sidebar-links a[href='{link}']")
        page.wait_for_selector("#main h1, #main h2")
        page.wait_for_selector("#main > .lang-note:first-child")
        assert page.locator(".lang-note").count() == 1
    page.click(".sidebar-links a[href='?page=browse']")
    page.click(".tune-list a >> nth=0")
    page.wait_for_selector(".score .abcjs-staff")
    assert page.locator("#main > .lang-note").count() == 1
    page.click("#home-button")
    page.wait_for_selector(".features")
    assert page.locator(".lang-note").count() == 0
    page.go_back()
    page.wait_for_selector(".score .abcjs-staff")
    page.click(".lang-switch [data-lang=en]")
    assert page.locator(".lang-note").count() == 0


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
    context.close()


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
    from urllib.parse import parse_qs, urlparse
    page.goto_site("?tune=glandyfi&v=2")
    href = page.get_attribute("a.report", "href")
    assert href.startswith("https://github.com/MarcoGorelli/y-sesiwn/issues/new?")
    query = parse_qs(urlparse(href).query)
    assert query["title"] == ["Problem with Glandyfi (version 2)"]
    assert "https://ysesiwn.cymru/?tune=glandyfi&v=2" in query["body"][0]
    assert "tunes/glandyfi-version-2/tune.abc" in query["body"][0]


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
                 "?page=notes&q=D%20G%20B%20D%20C%20B%20G%20A", "cy:", "cy:?tune=glandyfi"]:
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
    assert options == ["none", "mandolin", "guitar"]


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
          let abc = stripFields(tune.abc, "SZBNA");
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
