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
        # {^GA2): they were moved twice, as notes (findNotes) and as grace notes
        # (replaceGrace), which counted 3 regex groups a note instead of 4 and replaced
        # each grace note's length with it. Test: test_transposing_grace_notes.
        # 1. findNotes skips {...}, as it does "chords" and !decorations!.
        ("for(var o=/(![^!]+!)+/g;null!==(n=o.exec(a));)i.push({start:o.lastIndex-n[0].length,end:o.lastIndex});",
         "for(var o=/(![^!]+!)+/g;null!==(n=o.exec(a));)i.push({start:o.lastIndex-n[0].length,end:o.lastIndex});"
         "for(var p=/\\{[^}]*\\}/g;null!==(n=p.exec(a));)i.push({start:p.lastIndex-n[0].length,end:p.lastIndex});"),
        # 2. replaceGrace counts 4 groups a note, and replaces the pitch only.
        ("s[3*c+2]&&(o+=s[3*c+2].length),s[3*c+3]&&(o+=s[3*c+3].length),s[3*c+4]&&(o+=s[3*c+4].length),"
         "s[3*c+5]&&(o+=s[3*c+5].length);s[3*a+2]&&(o+=s[3*c+2].length),t+=o;var l=s[3*a+3]?s[3*a+3].length:0;"
         "l+=s[3*a+4]?s[3*a+4].length:0,r=t+(l+=s[3*a+5]?s[3*a+5].length:0)",
         "s[4*c+2]&&(o+=s[4*c+2].length),s[4*c+3]&&(o+=s[4*c+3].length),s[4*c+4]&&(o+=s[4*c+4].length),"
         "s[4*c+5]&&(o+=s[4*c+5].length);s[4*a+2]&&(o+=s[4*a+2].length),t+=o;var l=s[4*a+3]?s[4*a+3].length:0;"
         "r=t+l"),
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
