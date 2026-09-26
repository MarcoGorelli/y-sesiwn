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


def test_no_chord_box_without_chords(page):
    page.goto_site("?tune=nyth-y-gog")
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
    page.goto_site()
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


@pytest.mark.parametrize("path", ["", "?tune=glandyfi", "?page=map", "?page=offline", "?page=about"])
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
    assert len(page.locator(".tune-list li").all()) == len(page.evaluate("state.groupList"))


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
    page.goto(site)
    page.wait_for_selector("button.listen")
    page.click("button.listen")
    page.wait_for_function("!document.querySelector('button.listen').classList.contains('on')", timeout=30000)
    heard = page.input_value("#notes-search")
    assert heard == "C# D E F# E D C# D C# B"
    assert page.locator(".notes-results li a").first.inner_text() == "Machynlleth"
    browser.close()
