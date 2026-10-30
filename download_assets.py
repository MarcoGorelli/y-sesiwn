"""Download everything the app needs from the internet into ./static.

Run once (with internet access):  .venv/bin/python download_assets.py
Afterwards the app runs fully offline. Existing files are skipped.
"""

import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

STATIC = Path(__file__).parent / "static"
ABCJS = "https://cdn.jsdelivr.net/npm/abcjs@6.7.2"
SOUNDFONT = "https://paulrosen.github.io/midi-js-soundfonts/FluidR3_GM"
INSTRUMENT = "acoustic_grand_piano"
PERCUSSION = "https://paulrosen.github.io/midi-js-soundfonts/abcjs"

# abcjs names notes like this, for MIDI pitches 21 (A0) to 108 (C8).
NAMES = ["C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B"]
NOTES = [f"{NAMES[p % 12]}{p // 12 - 1}" for p in range(21, 109)]

FILES = {
    "abcjs/abcjs-basic-min.js": f"{ABCJS}/dist/abcjs-basic-min.js",
    "abcjs/abcjs-audio.css": f"{ABCJS}/abcjs-audio.css",
    # Markdown renderer for the static site's guide pages (CONTRIBUTING.md).
    "marked/marked.min.js": "https://cdn.jsdelivr.net/npm/marked@15.0.12/marked.min.js",
    **{
        f"soundfont/{INSTRUMENT}-mp3/{note}.mp3": f"{SOUNDFONT}/{INSTRUMENT}-mp3/{note}.mp3"
        for note in NOTES
    },
    # The metronome and count-in: General MIDI percussion 76 and 77 (high and low
    # woodblock), which abcjs names E5 and F5. From abcjs's own sound set, whose
    # percussion samples are real recordings (FluidR3's are near-silent stubs).
    **{
        f"soundfont/percussion-mp3/{note}.mp3": f"{PERCUSSION}/percussion-mp3/{note}.mp3"
        for note in ["E5", "F5"]
    },
}


# Fixes made to the downloaded files, as (old, new) text in the minified code, applied
# after every download. A new version whose code has moved on stops the script: see
# whether its tests still fail without the fix, then find the same code again or drop it.
PATCHES = {
    "abcjs/abcjs-basic-min.js": [
        # strTranspose broke grace notes with an accidental ({^F}G2 up a tone came out
        # {^GA2): it moved each grace note twice, with the notes (findNotes finds grace
        # notes too) and again on its own (replaceGrace), and the second change, made to
        # the text the first had already changed, took the } or a note with it. Without
        # the second one, the notes' own change does it right. Test: test_transposing_grace_notes.
        # Reported: https://github.com/paulrosen/abcjs/issues/1197 (drop this once a release fixes it).
        ("if(g.gracenotes)for(var A=0;A<g.gracenotes.length;A++){var N=b(g.gracenotes[A].name,n,a,u);"
         "N.acc&&(u[N.name.toUpperCase()]=N.acc);var B=m(N,s,l,u);B.acc&&(d[B.upper]=B.acc),"
         "c.push(x(e,g.startChar,g.endChar,B.acc+B.name,A))}", "/* Y Sesiwn: no second change to grace notes */"),
        # strTranspose renamed a key with its mode written out as if it were major
        # (K:G dorian down a semitone came out K:Gb dorian, its notes written for F# dorian):
        # the K: line's own change (changeAllKeySigs) knew a mode only by its short name
        # (dor, mix, m). It now goes by the first three letters, as ABC does.
        # Test: test_transposing_accidentals.
        # Reported: https://github.com/paulrosen/abcjs/issues/1199 (drop this once a release fixes it).
        ('h=l(o[5])?o[5]:""', 'h=l(o[5].slice(0,3))?o[5]:""'),
        # strTranspose remembered a bar's accidentals by letter only, in the tune (so ^G
        # made a later g sharp too, which abcjs itself doesn't) and in what it wrote, where it
        # stored them as B, and looked them up as B (so a note below or above the middle
        # octave lost the natural or flat it needed). Both now go by letter and octave
        # (parseNote, the notes loop and transposePitch). Test: test_transposing_accidentals.
        # Reported: https://github.com/paulrosen/abcjs/issues/1200 (drop these once a release fixes it).
        ('var l=n[s]||r[s]||"=";return{acc:i[1],name:s,pitch:o,oct:c,adj:w(i[1],r[s],n[s]),courtesy:i[1]===l}',
         'var l=n[s+c]||r[s]||"=";return{acc:i[1],name:s,pitch:o,oct:c,adj:w(i[1],r[s],n[s+c]),courtesy:i[1]===l}'),
        ("E.acc&&(u[E.name.toUpperCase()]=E.acc)", "E.acc&&(u[E.name+E.oct]=E.acc)"),
        ('switch(n[h]!==u&&(n[h]||u!==p)||e.courtesy||(u=""),c)', 'switch(n[h+c]!==u&&(n[h+c]||u!==p)||e.courtesy||(u=""),c)'),
        ("return c>4&&(h=h.toLowerCase()),{acc:u,name:h,upper:h.toUpperCase()}",
         "return c>4&&(h=h.toLowerCase()),{acc:u,name:h,upper:d[s]+c}"),
    ],
}


def patch(path: str, fixes: list[tuple[str, str]]) -> str:
    dest = STATIC / path
    text = dest.read_text(encoding="utf-8")
    for old, new in fixes:
        if new in text:
            continue
        if text.count(old) != 1:
            raise SystemExit(f"{path}: a fix in PATCHES no longer matches the code (see PATCHES)")
        text = text.replace(old, new)
    dest.write_text(text, encoding="utf-8")
    return f"fixed {path}"


def download(item: tuple[str, str]) -> str:
    path, url = item
    dest = STATIC / path
    if dest.exists() and dest.stat().st_size > 0:
        return f"skip {path}"
    dest.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url, timeout=30) as response:
        data = response.read()
    dest.write_bytes(data)
    return f"got  {path} ({len(data) // 1024} KB)"


def main() -> None:
    with ThreadPoolExecutor(max_workers=8) as pool:
        for line in pool.map(download, FILES.items()):
            print(line)
    for path, fixes in PATCHES.items():
        print(patch(path, fixes))
    print(f"done: {len(FILES)} files in {STATIC}")


if __name__ == "__main__":
    main()
