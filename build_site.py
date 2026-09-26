"""Build the static Y Sesiwn site into _site/ (no dependencies beyond Python).

    python build_site.py                        # build
    python -m http.server -d _site 8000         # preview at http://localhost:8000

_site/ gets the page (site/), the vendored libraries and sounds (static/),
CONTRIBUTING.md, and tunes.json: every tune.abc plus everything the page needs
about it (type, key, default tempo, details), worked out here once instead of
in the browser. The GitHub Pages workflow runs this on every push to main.
"""

import hashlib
import json
import re
import shutil
import unicodedata
from fractions import Fraction
from pathlib import Path

ROOT = Path(__file__).parent
OUT = ROOT / "_site"
REPO_URL = "https://github.com/MarcoGorelli/y-sesiwn"

PITCH = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
MODE_NAMES = {
    "": "major", "maj": "major", "ion": "major", "m": "minor", "min": "minor",
    "aeo": "minor", "dor": "Dorian", "phr": "Phrygian", "lyd": "Lydian",
    "mix": "Mixolydian", "loc": "Locrian",
}
BEAT_NAMES = {
    Fraction(3, 8): "dotted crotchet",
    Fraction(1, 2): "minim",
    Fraction(1, 4): "crotchet",
    Fraction(1, 8): "quaver",
}
# Default tempo (beats per minute) by tune type, matched against R:. The Q:
# tempos in the ABC files are ignored.
DEFAULT_BPM = {"jig": 112, "ril": 90, "reel": 90, "polca": 100, "polka": 100}
OTHER_BPM = 100

# Browsing categories, matched against the first word of R: that fits. Specific
# dance types come before the generic "alaw" (air) and "cân" (song).
SPECIFIC_TYPES = {
    "jig": "Jig", "polca": "Polca", "polka": "Polca", "walts": "Walts", "waltz": "Walts",
    "ril": "Rîl", "reel": "Rîl", "pibdd": "Pibddawns", "hornpipe": "Pibddawns",
    "ymdaith": "Ymdaith", "ymdeithdon": "Ymdaith", "march": "Ymdaith",
    "dawns": "Dawns", "set": "Dawns", "carol": "Carol",  # "Set Dance"
}
GENERIC_TYPES = {"alaw": "Alaw", "air": "Alaw", "can": "Cân", "song": "Cân"}
# label -> (English, colour), in display order. The colours are carthen
# (Welsh tapestry blanket) colourways, shown as small swatches in the site.
TYPE_ORDER = {
    "Jig": ("jigs", "#C8102E"),           # Welsh red
    "Polca": ("polkas", "#2f4f8f"),       # indigo
    "Walts": ("waltzes", "#c28f1c"),      # mustard
    "Rîl": ("reels", "#2e6b4f"),          # bottle green
    "Pibddawns": ("hornpipes", "#7b3f6e"),  # plum
    "Ymdaith": ("marches", "#2b7a7f"),    # teal
    "Dawns": ("dances", "#b4532a"),       # rust
    "Alaw": ("airs", "#5b6f8c"),          # slate blue
    "Cân": ("songs", "#a3456a"),          # rose
    "Carol": ("carols", "#6b7b2c"),       # olive
    "Other": ("untyped and other tunes", "#6b737c"),  # slate grey
}

# ABC header fields shown under Details, in display order (only if present).
HEADER_LABELS = {
    "R": "Tune type",
    "K": "Key",
    "M": "Time signature",
    "C": "Composer / arranger",
    "A": "Area",
    "O": "Origin",
    "B": "Book",
    "D": "Discography",
    "H": "History",
    "N": "Notes",
}
# The credits (C:) are in Welsh, as printed on the original scores.
CREDIT_WORDS = {
    "Trefniant": "arranged by", "Trefniannau": "arrangements by", "Trefnwyd gan": "arranged by",
    "Addasiad": "adapted by", "Addaswyd gan": "adapted by", "Alaw": "tune by",
    "Alaw draddodiadol": "traditional tune",
}


# ---- Melody, for "search by notes" ----------------------------------------------

# Sharps (+) or flats (-) in each major key, and how far each mode shifts that.
KEY_SHARPS = {
    "C": 0, "G": 1, "D": 2, "A": 3, "E": 4, "B": 5, "F#": 6, "C#": 7,
    "F": -1, "Bb": -2, "Eb": -3, "Ab": -4, "Db": -5, "Gb": -6, "Cb": -7,
}
MODE_SHARPS = {"": 0, "maj": 0, "ion": 0, "lyd": 1, "mix": -1, "dor": -2, "m": -3,
               "min": -3, "aeo": -3, "phr": -4, "loc": -5}
NOTE_TOKEN = re.compile(
    r"\[([^\]|]*[A-Ga-g][^\]|]*)\]"          # chord: [ceg]
    r"|(\^\^|\^|__|_|=)?([A-Ga-g])([,']*)"   # note, with accidental and octave marks
    r"|(\|)"                                # bar line: accidentals end here
)
ACCIDENTALS = {"^^": 2, "^": 1, "=": 0, "_": -1, "__": -2}


def key_signature(key: str) -> dict[str, int]:
    """'DMix' -> {'F': 1}: the sharp (+1) or flat (-1) on each letter."""
    m = re.match(r"^([A-G][#b]?)\s*([A-Za-z]*)", key.strip())
    if not m or m.group(1) not in KEY_SHARPS:
        return {}
    n = KEY_SHARPS[m.group(1)] + MODE_SHARPS.get(m.group(2)[:3].lower(), 0)
    letters = "FCGDAEB" if n > 0 else "BEADGCF"
    return {letter: 1 if n > 0 else -1 for letter in letters[: abs(n)]}


def melody(abc: str) -> list[int]:
    """MIDI pitches of the tune's notes in written order (top note of chords)."""
    lines = abc.splitlines()
    start = next((i for i, line in enumerate(lines) if line.startswith("K:")), len(lines))
    signature: dict[str, int] = {}
    body_parts = []
    for line in lines[start:]:
        if line.startswith("K:"):  # the key, and key changes part-way through
            body_parts.append(f"[K:{line[2:].strip()}]")
        elif not re.match(r"^(%|[A-Za-z]:)", line):
            body_parts.append(line)
    body = " ".join(body_parts)
    body = re.sub(r'\{[^}]*\}|"[^"]*"', " ", body)  # grace notes; chord names and text
    body = re.sub(r"\[(?!K:)[A-Za-z]:[^\]]*\]", " ", body)  # other inline fields, e.g. [M:6/8]
    bar: dict[tuple[str, int], int] = {}  # accidentals written earlier in this bar

    def pitch(acc: str | None, letter: str, marks: str) -> int:
        octave = (1 if letter.islower() else 0) + marks.count("'") - marks.count(",")
        name = letter.upper()
        if acc:
            bar[(name, octave)] = ACCIDENTALS[acc]
        alter = bar.get((name, octave), signature.get(name, 0))
        return 60 + 12 * octave + PITCH[name] + alter

    notes = []
    for m in re.finditer(r"\[K:([^\]]*)\]|" + NOTE_TOKEN.pattern, body):
        if m.group(1) is not None:  # key change
            signature = key_signature(m.group(1))
            bar.clear()
            continue
        m = NOTE_TOKEN.match(m.group(0))
        if m.group(5):
            bar.clear()
        elif m.group(1) is not None:
            chord = [pitch(*n.groups()) for n in re.finditer(r"(\^\^|\^|__|_|=)?([A-Ga-g])([,']*)", m.group(1))]
            notes.append(max(chord))
        else:
            notes.append(pitch(m.group(2), m.group(3), m.group(4)))
    return notes


def melody_string(abc: str) -> str:
    """The melody for the note search, one character per note: chr(MIDI pitch + 160),
    repeated notes collapsed. Compact in JSON, and needs no escaping."""
    out = []
    for p in melody(abc):
        c = chr(p + 160)
        if not out or out[-1] != c:
            out.append(c)
    return "".join(out)


def normalize(text: str) -> str:
    """Lowercase, strip accents and punctuation, e.g. 'Frân' -> 'fran'."""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9 ]+", " ", text.lower()).strip()


def parse_headers(abc: str) -> dict[str, list[str]]:
    """Collect header fields (lines like 'T:...') up to and including K:."""
    headers: dict[str, list[str]] = {}
    for line in abc.splitlines():
        m = re.match(r"^([A-Za-z]):\s*(.*)$", line)
        if m:
            headers.setdefault(m.group(1), []).append(m.group(2).strip())
            if m.group(1) == "K":
                break
    return headers


def parse_key(key: str) -> tuple[int, str, str] | None:
    """'F#m' -> (6, 'F#', 'm'); returns None for keys we can't parse."""
    m = re.match(r"^([A-Ga-g])([#b]?)\s*([A-Za-z]*)", key.strip())
    if not m:
        return None
    root = m.group(1).upper() + m.group(2)
    pitch = PITCH[root[0]] + {"#": 1, "b": -1, "": 0}[m.group(2)]
    return pitch % 12, root, m.group(3)


def key_name(key: str) -> str:
    """'DMix' -> 'D Mixolydian', 'Em' -> 'E minor'; unknown keys as written."""
    parsed = parse_key(key)
    mode = MODE_NAMES.get(parsed[2][:3].lower()) if parsed else None
    return f"{parsed[1]} {mode}" if mode else key


def tune_type(headers: dict[str, list[str]]) -> str:
    """Browsing category from R:, e.g. "polca/pibddawns" -> "Polca"."""
    words = normalize(" ".join(headers.get("R", []))).split()
    for table in (SPECIFIC_TYPES, GENERIC_TYPES):
        for word in words:
            for prefix, label in table.items():
                if word.startswith(prefix):
                    return label
    return "Other"


def beat_unit(meter: str) -> Fraction:
    """The note felt as one beat: 6/8 -> 3/8, 4/4 and 2/2 -> 1/2, 2/4 -> 1/4.

    4/4 is counted in two (minims), as reels and polcas are played.
    """
    meter = {"C": "4/4", "C|": "2/2"}.get(meter.strip(), meter.strip())
    m = re.match(r"^(\d+)/(\d+)$", meter)
    if not m:
        return Fraction(1, 4)
    num, den = int(m.group(1)), int(m.group(2))
    if den >= 8 and num % 3 == 0 and num > 3:
        return Fraction(3, den)  # compound time: dotted beats
    if (num, den) == (4, 4):
        return Fraction(1, 2)
    return Fraction(1, den)


def default_bpm(headers: dict[str, list[str]]) -> int:
    """Default from the tune type (earliest match in R:, e.g. "polca/ymdaith")."""
    tune_type = normalize(" ".join(headers.get("R", [])))
    matches = [(tune_type.find(word), bpm) for word, bpm in DEFAULT_BPM.items() if word in tune_type]
    return min(matches)[1] if matches else OTHER_BPM


def details(headers: dict[str, list[str]]) -> tuple[list[list[str]], list[list[str]]]:
    """(label, value) rows for the Details box, and glosses for Welsh credit words."""
    rows, gloss = [], {}
    for field, label in HEADER_LABELS.items():
        values = headers.get(field)
        if not values:
            continue
        if field == "K":
            values = [key_name(v) for v in values]
        rows.append([label, ", ".join(values)])
        if field == "C":
            for word, meaning in CREDIT_WORDS.items():
                if any(v == word or v.startswith((word + " ", word + ",")) for v in values):
                    gloss[word] = meaning
    if "Alaw draddodiadol" in gloss:
        gloss.pop("Alaw", None)
    return rows, [[w, m] for w, m in gloss.items()]


VERSION = re.compile(r"^(.*) \(version (\d+)\)$")


def slugify(title: str) -> str:
    """Folder name for a title: 'Codi'r Hwyl' -> 'codi-r-hwyl'."""
    return re.sub(r"[^a-z0-9]+", "-", normalize(title).replace(" ", "-")).strip("-")


def version_label(headers: dict[str, list[str]]) -> str:
    """Where a version comes from, for its tab: the book, else the source site."""
    if headers.get("B"):
        return headers["B"][0]
    source = " ".join(headers.get("S", []))
    return "Alawon Cymru" if "alawoncymru" in source else ""


QUOTED = re.compile(r'"([^"]*)"')  # chord symbols ("G") and annotations ("^Fine")


def chords_source(abc: str) -> str | None:
    """None if the tune has no chord symbols, else where they come from: the
    tune's `%%chords <text>` line, or "" if it has none."""
    body = "\n".join(l for l in abc.splitlines() if not re.match(r"[A-Za-z]:|%", l))
    # A chord starts with a note name; an annotation with ^ _ < > or @.
    if not any(re.match(r"[A-G]", text) for text in QUOTED.findall(body)):
        return None
    m = re.search(r"^%%chords\s+(.*\S)", abc, re.M)
    return m.group(1) if m else ""


def tune_record(path: Path) -> dict:
    abc = path.read_text(encoding="utf-8")
    headers = parse_headers(abc)
    titles = headers.get("T") or [path.parent.name]
    parsed = parse_key((headers.get("K") or [""])[0])
    beat = beat_unit((headers.get("M") or [""])[0])
    rows, gloss = details(headers)
    # Versions of a tune ("Rheged (version 2)") share one page, under the base title.
    m = VERSION.match(titles[0])
    base, number = (m.group(1), int(m.group(2))) if m else (titles[0], 1)
    return {
        "slug": path.parent.name,
        "group": slugify(base),
        "base": base,
        "version": number,
        "source": version_label(headers),
        "title": titles[0],
        "titles": titles,
        "search": [normalize(t) for t in titles],
        "type": tune_type(headers),
        # modeName spells the mode out for the key menu: "EDor" -> "E Dorian".
        "key": {
            "pitch": parsed[0],
            "root": parsed[1],
            "modeName": MODE_NAMES.get(parsed[2][:3].lower(), parsed[2]),
        } if parsed else None,
        "beat": str(beat),
        "beatName": BEAT_NAMES.get(beat, str(beat)),
        "bpm": default_bpm(headers),
        "details": rows,
        "melody": melody_string(abc),
        "gloss": gloss,
        "chords": chords_source(abc),
        "abc": abc,
    }


# The projection site/wales.svg was drawn with (see the comment in it).
MAP = {"lon0": -5.669900, "lat0": 53.435690, "k": 0.610145, "scale": 100}


def places(groups: set[str]) -> list[dict]:
    """places.json, with each place's position on site/wales.svg."""
    result = []
    for place in json.loads((ROOT / "places.json").read_text(encoding="utf-8"))["places"]:
        unknown = set(place["tunes"]) - groups
        if unknown:
            raise SystemExit(f"places.json: no tune called {', '.join(sorted(unknown))}")
        result.append({
            "name": place["name"],
            "x": round((place["lon"] - MAP["lon0"]) * MAP["k"] * MAP["scale"], 1),
            "y": round((MAP["lat0"] - place["lat"]) * MAP["scale"], 1),
            "tunes": place["tunes"],
        })
    return result


def main() -> None:
    tunes = [tune_record(p) for p in sorted((ROOT / "tunes").glob("*/tune.abc"))]
    first_versions = [t for t in tunes if t["version"] == 1]
    counts = {t: sum(tune["type"] == t for tune in first_versions) for t in TYPE_ORDER}
    index = {
        "repo": REPO_URL,
        "types": [
            {"name": t, "english": english, "colour": colour, "count": counts[t]}
            for t, (english, colour) in TYPE_ORDER.items()
            if counts[t]
        ],
        "tunes": tunes,
        "places": places({t["group"] for t in tunes}),
        "mapSize": [float(n) for n in re.search(
            r'viewBox="0 0 ([\d.]+) ([\d.]+)"', (ROOT / "site" / "wales.svg").read_text()).groups()],
    }

    if OUT.exists():
        shutil.rmtree(OUT)
    shutil.copytree(ROOT / "site", OUT)
    for part in ["abcjs", "soundfont", "marked", "harp.svg"]:
        src = ROOT / "static" / part
        if src.is_dir():
            shutil.copytree(src, OUT / "static" / part)
        else:
            shutil.copy2(src, OUT / "static" / part)
    shutil.copy2(ROOT / "CONTRIBUTING.md", OUT / "CONTRIBUTING.md")
    (OUT / "tunes.json").write_text(
        json.dumps(index, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )
    write_service_worker()
    print(f"built {OUT.relative_to(ROOT)}/ with {len(tunes)} tunes")


# Not needed offline: link-preview images and the source of the service worker itself.
NOT_OFFLINE = {"sw.js", "og-image.png", "CNAME"}


def write_service_worker() -> None:
    """Fill in sw.js: which files to keep for offline use, and a version that
    changes whenever any of them does (so browsers pick up a new deploy)."""
    def digest(files: list[Path]) -> str:
        h = hashlib.sha256()
        for f in files:
            h.update(f.relative_to(OUT).as_posix().encode() + f.read_bytes())
        return h.hexdigest()[:12]

    files = sorted(f for f in OUT.rglob("*") if f.is_file() and f.name not in NOT_OFFLINE)
    sounds = [f for f in files if f.is_relative_to(OUT / "static" / "soundfont")]
    site = [f for f in files if f not in sounds]
    urls = lambda fs: json.dumps([f.relative_to(OUT).as_posix() for f in fs])
    sw = OUT / "sw.js"
    sw.write_text(
        sw.read_text(encoding="utf-8")
        .replace("__VERSION__", digest(site))
        .replace("__SOUNDS_VERSION__", digest(sounds))
        .replace("__SITE_FILES__", '["./", ' + urls(site)[1:])
        .replace("__SOUND_FILES__", urls(sounds)),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
