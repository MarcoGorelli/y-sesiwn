"""Download everything the app needs from the internet into ./static.

Run once (with internet access):  .venv/bin/python download_assets.py
Afterwards the app runs fully offline. Existing files are skipped.
"""

import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

STATIC = Path(__file__).parent / "static"
ABCJS = "https://cdn.jsdelivr.net/npm/abcjs@6.4.4"
SOUNDFONT = "https://paulrosen.github.io/midi-js-soundfonts/FluidR3_GM"
INSTRUMENT = "acoustic_grand_piano"

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
}


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
    print(f"done: {len(FILES)} files in {STATIC}")


if __name__ == "__main__":
    main()
