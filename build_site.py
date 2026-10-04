"""Build the static Y Sesiwn site into _site/ (no dependencies beyond Python).

    python build_site.py                        # build
    python -m http.server -d _site 8000         # preview at http://localhost:8000

_site/ gets the page (site/), the vendored libraries and sounds (static/),
CONTRIBUTING.md, and tunes.json: every tune.abc plus everything the page needs
about it (type, key, default tempo, details), worked out here once instead of
in the browser. The GitHub Pages workflow runs this on every push to main.
"""

import hashlib
import html
import json
import re
import shutil
import unicodedata
from fractions import Fraction
from pathlib import Path

ROOT = Path(__file__).parent
OUT = ROOT / "_site"
REPO_URL = "https://github.com/MarcoGorelli/y-sesiwn"
SITE_URL = "https://ysesiwn.cymru/"
TUNE_DIR = "alaw"  # each tune's own page is alaw/<folder>/ (see tune_pages)
TYPE_DIR = "math"  # and each type's, math/<type>/
SESSIONS_DIR = "sesiynau"  # the sessions page (see session_data)

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

# One tune of each type, for the tune pages' descriptions ("a jig in G major").
TYPE_SINGULAR = {
    "Jig": "jig", "Polca": "polka", "Walts": "waltz", "Rîl": "reel", "Pibddawns": "hornpipe",
    "Ymdaith": "march", "Dawns": "dance", "Alaw": "air", "Cân": "song", "Carol": "carol", "Other": "tune",
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
    "S": "Source",  # a URL, shown as a link (and any words after it as text: "(added by …)")
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


def music(abc: str) -> str:
    """The tune's notes as one line: from the K: line on, without comments, other
    header lines, grace notes, chord names, text, decorations or inline fields (key
    changes are kept, as [K:...])."""
    lines = abc.splitlines()
    start = next((i for i, line in enumerate(lines) if line.startswith("K:")), len(lines))
    body_parts = []
    for line in lines[start:]:
        if line.startswith("K:"):  # the key, and key changes part-way through
            body_parts.append(f"[K:{line[2:].strip()}]")
        elif not re.match(r"^(%|[A-Za-z]:)", line):
            body_parts.append(line)
    body = " ".join(body_parts)
    body = re.sub(r'\{[^}]*\}|"[^"]*"|![^!\s]*!', " ", body)  # grace notes; chord names and text; !fermata! and the like
    return re.sub(r"\[(?!K:)[A-Za-z]:[^\]]*\]", " ", body)  # other inline fields, e.g. [M:6/8]


def melody(abc: str) -> list[int]:
    """MIDI pitches of the tune's notes in written order (top note of chords)."""
    signature: dict[str, int] = {}
    body = music(abc)
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


LENGTH_TOKEN = re.compile(
    r"\((\d)"                                                       # tuplet: (3
    r"|(?:\[[^\]|]*\]|(?:\^\^|\^|__|_|=)?[A-Ga-g][,']*|[zx])(\d*)(/*)(\d*)"  # chord/note/rest, length
    r"|(\|)"                                                         # bar line
)
TUPLETS = {2: Fraction(3, 2), 3: Fraction(2, 3), 4: Fraction(3, 4), 6: Fraction(2, 3)}


def meter_length(abc: str) -> Fraction | None:
    """A bar's length in whole notes, from M: (C is 4/4, C| is 2/2)."""
    meter = (parse_headers(abc).get("M") or [""])[0].strip()
    meter = {"C": "4/4", "C|": "2/2"}.get(meter, meter)
    m = re.match(r"(\d+)/(\d+)", meter)
    return Fraction(int(m.group(1)), int(m.group(2))) if m else None


def lead_in(abc: str) -> int:
    """How many notes the tune's lead-in (pick-up) has: the notes before the first
    bar line, if they don't fill a bar. 0 if the first bar is a full one."""
    bar = meter_length(abc)
    if not bar:
        return 0
    unit = (parse_headers(abc).get("L") or [""])[0].strip()
    unit = Fraction(unit) if re.fullmatch(r"\d+/\d+", unit) else Fraction(1, 8 if bar >= Fraction(3, 4) else 16)
    total, notes, tuplet, left = Fraction(0), 0, Fraction(1), 0
    for m in LENGTH_TOKEN.finditer(re.sub(r"\[K:[^\]]*\]", " ", music(abc))):
        if m.group(1):
            p = int(m.group(1))
            tuplet, left = TUPLETS.get(p, Fraction(1)), p
        elif m.group(5):
            if notes:  # a bar line before any note (|: at the start) doesn't end the bar
                break
        else:
            number, slashes, divisor = m.group(2), m.group(3), m.group(4)
            length = Fraction(int(number or 1))
            if slashes:
                length /= int(divisor) if divisor else 2 ** len(slashes)
            total += length * unit * (tuplet if left else 1)
            left = max(0, left - 1)
            if not m.group(0).startswith(("z", "x")):
                notes += 1
    else:
        return 0  # no bar line at all
    return notes if total < bar else 0


def lead_index(abc: str) -> int:
    """The position in melody_string() of the first note after the lead-in."""
    notes, k = melody(abc), lead_in(abc)
    if not k:
        return 0
    collapsed = len([p for i, p in enumerate(notes[:k]) if i == 0 or p != notes[i - 1]])
    return collapsed - 1 if k < len(notes) and notes[k] == notes[k - 1] else collapsed


def melody_string(abc: str) -> str:
    """The melody for the note search, one character per note: chr(MIDI pitch + 160),
    repeated notes collapsed. The app works it out itself (melodyOf in app.js); the
    tests check the two agree for every tune."""
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
        values = [v for v in headers.get(field, []) if v.strip()]  # an empty R: says nothing
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
    if "thesession.org" in source:
        return "The Session"
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
        "titles": titles,
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
        # Where the melody starts after the lead-in (its repeated notes are collapsed,
        # so count the same way). The app works out the title, the search names and the
        # melody (melody_string) itself, so they aren't in tunes.json.
        "lead": lead_index(abc),
        "gloss": gloss,
        "chords": chords_source(abc),
        "abc": abc,
    }


# The projection site/wales.svg was drawn with (see the comment in it).
MAP = {"lon0": -5.669900, "lat0": 53.435690, "k": 0.610145, "scale": 100}


def pronunciations(groups: set[str]) -> dict[str, str]:
    """pronunciation.json: how to say each Welsh tune name, by the tune's folder name."""
    say = json.loads((ROOT / "pronunciation.json").read_text(encoding="utf-8"))["say"]
    unknown = set(say) - groups
    if unknown:
        raise SystemExit(f"pronunciation.json: no tune called {', '.join(sorted(unknown))}")
    return say


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


def short_id(slug: str) -> str:
    """A tune's code in set links (?page=set&s=…): five letters and digits from its
    folder name, so it doesn't change when other tunes are added."""
    n = int(hashlib.sha1(slug.encode()).hexdigest(), 16) % 36 ** 5
    digits = "0123456789abcdefghijklmnopqrstuvwxyz"
    return "".join(digits[n // 36 ** i % 36] for i in reversed(range(5)))


BASE62 = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
NUMBERS = ROOT / "tune_numbers.json"


def load_numbers() -> dict[str, int]:
    """tune_numbers.json: each tune's number for set links, which never changes."""
    if not NUMBERS.exists():
        return {}
    return json.loads(NUMBERS.read_text(encoding="utf-8"))["numbers"]


def number_tunes() -> None:
    """Give tunes without a number the next ones (python build_site.py --number-tunes).
    Numbers are only ever added: a tune keeps its number, and a removed tune's number
    stays in the file, so it's never given to another tune (old set links would open it)."""
    numbers = load_numbers()
    new = sorted(p.parent.name for p in (ROOT / "tunes").glob("*/tune.abc") if p.parent.name not in numbers)
    start = max(numbers.values(), default=-1) + 1
    numbers.update({slug: start + i for i, slug in enumerate(new)})
    comment = ("Each tune's number in set links (?set=…), by folder name. Only ever add to it: never change "
               "or reuse a number, and keep a removed tune's line, or old set links would open the wrong tune. "
               "python build_site.py --number-tunes adds new tunes (a test checks the rest).")
    lines = ",\n".join(f'    "{slug}": {n}' for slug, n in sorted(numbers.items(), key=lambda x: x[1]))
    NUMBERS.write_text('{\n  "_comment": ' + json.dumps(comment, ensure_ascii=False) + ',\n  "numbers": {\n' + lines + "\n  }\n}\n",
                       encoding="utf-8")
    print(f"numbered {len(new)} new tune(s)" + (f": {', '.join(new)}" if new else ""))


def set_code(slug: str, numbers: dict[str, int]) -> str:
    """A tune's code in a set link: its number in two characters of base 62 (three,
    after "-", past 3,844 tunes); without a number yet, "." and its five-character short_id."""
    if slug not in numbers:
        return "." + short_id(slug)
    n = numbers[slug]
    digits = lambda n, width: "".join(BASE62[n // 62 ** i % 62] for i in reversed(range(width)))
    return digits(n, 2) if n < 62 ** 2 else "-" + digits(n, 3)


def moved_tunes(slugs: set[str], numbers: dict[str, int]) -> list[dict]:
    """moved.json: tunes whose folder was renamed (or that became another tune's
    version), with the old folder's set codes, so old links still find them."""
    path = ROOT / "moved.json"
    moved = json.loads(path.read_text(encoding="utf-8"))["moved"] if path.exists() else {}
    result = []
    for old, new in moved.items():
        if old in slugs:
            raise SystemExit(f"moved.json: {old} is still a folder in tunes/ (only list folders that have gone)")
        if new not in slugs:
            raise SystemExit(f"moved.json: {old} moved to {new}, but there's no tunes/{new}/")
        result.append({"from": old, "to": new, "code": set_code(old, numbers), "id": short_id(old)})
    return result


def main() -> None:
    tunes = [tune_record(p) for p in sorted((ROOT / "tunes").glob("*/tune.abc"))]
    numbers = load_numbers()
    unnumbered = [t["slug"] for t in tunes if t["slug"] not in numbers]
    if unnumbered:
        print(f"note: {len(unnumbered)} tune(s) without a set number yet (their set links are a little longer); "
              "run python build_site.py --number-tunes")
    ids: dict[str, str] = {}
    for tune in tunes:
        tune["code"] = set_code(tune["slug"], numbers)
        tune["id"] = short_id(tune["slug"])
        if tune["id"] in ids:  # very unlikely (1 in about 60 million per pair); rename a folder if it happens
            raise SystemExit(f"{tune['slug']} and {ids[tune['id']]} have the same set code {tune['id']}")
        ids[tune["id"]] = tune["slug"]
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
        "say": pronunciations({t["group"] for t in tunes}),
        "moved": moved_tunes({t["slug"] for t in tunes}, numbers),
        "mapSize": [float(n) for n in re.search(
            r'viewBox="0 0 ([\d.]+) ([\d.]+)"', (ROOT / "site" / "wales.svg").read_text()).groups()],
    }

    if OUT.exists():
        shutil.rmtree(OUT)
    shutil.copytree(ROOT / "site", OUT)
    for part in ["abcjs", "soundfont", "marked", "qrcode", "harp.svg", "crwth.svg", "pibgorn.svg", "lovespoon.svg", "quilt.svg"]:
        src = ROOT / "static" / part
        if src.is_dir():
            shutil.copytree(src, OUT / "static" / part)
        else:
            shutil.copy2(src, OUT / "static" / part)
    shutil.copy2(ROOT / "CONTRIBUTING.md", OUT / "CONTRIBUTING.md")
    (OUT / "tunes.json").write_text(
        json.dumps(index, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )
    tune_pages(tunes, index)
    write_service_worker()
    print(f"built {OUT.name}/ with {len(tunes)} tunes")


# Not needed offline: link-preview images, the source of the service worker itself, and
# GitHub Pages' "not found" page (offline, sw.js answers every address with the app).
NOT_OFFLINE = {"sw.js", "og-image.png", "CNAME", "sitemap.xml", "robots.txt", "404.html"}


# Welsh for the tune pages' descriptions (app.js has the same: CY_TYPE, CY_MODES).
CY_TYPE = {"Jig": "jig", "Polca": "polca", "Walts": "walts", "Rîl": "rîl", "Pibddawns": "pibddawns", "Ymdaith": "ymdaith",
           "Dawns": "dawns", "Alaw": "alaw", "Cân": "cân", "Carol": "carol", "Other": "alaw"}
CY_MODES = {"major": "fwyaf", "minor": "leiaf", "Dorian": "Doriaidd", "Phrygian": "Phrygaidd", "Lydian": "Lydaidd",
            "Mixolydian": "Mixolydaidd", "Locrian": "Locriaidd"}

esc = lambda text: html.escape(text, quote=True)


def type_slug(name: str) -> str:
    """A type's page, math/<slug>/: 'Rîl' -> 'ril' (app.js: typeSlug)."""
    return slugify(name)


def app_page(template: str, *, title: str, description: str, url: str, head: str, main: str,
             scripts: str = "", up: str = "../../") -> str:
    """The app (index.html) in a folder (two down, unless up says otherwise), with its
    own title, description and address in the head, for link previews and search
    engines (which don't run the app), and what they should read in <main> until the
    app takes over."""
    def swap(page: str, old: str, new: str) -> str:
        if page.count(old) != 1:
            raise SystemExit(f"site/index.html: expected one {old!r} (for the tune and type pages)")
        return page.replace(old, new)

    page = template
    page = swap(page, '<base href="./">', f'<base href="{up}">')
    page = swap(page, '<script src="app.js" defer></script>', scripts + '<script src="app.js" defer></script>')
    page = swap(page, "<title>Y Sesiwn</title>", f"<title>{esc(title)} · Y Sesiwn</title>")
    page = re.sub(r'(<meta (?:name|property)="(?:og:)?description" content=")[^"]*"',
                  lambda m: m.group(1) + esc(description) + '"', page)
    page = swap(page, '<meta property="og:title" content="Y Sesiwn: Welsh folk tunes">',
                f'<meta property="og:title" content="{esc(title)} · Y Sesiwn">')
    page = swap(page, f'<meta property="og:url" content="{SITE_URL}">',
                f'<meta property="og:url" content="{url}">\n  <link rel="canonical" href="{url}">' + head)
    return swap(page, '<main id="main" tabindex="-1"><p class="loading">Loading tunes…</p></main>',
                f'<main id="main" tabindex="-1">{main}</main>')


def write_page(folder: Path, page: str) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "index.html").write_text(page, encoding="utf-8")


def tune_pages(tunes: list[dict], index: dict) -> None:
    """A real page for each tune, at alaw/<folder>/, and for each type of tune, at
    math/<type>/ (see app_page). A tune's page also carries tunes.json cut down to this
    tune, so the app can draw it without waiting for every other tune (a shared link on
    a phone, say); a type's lists its tunes, so search engines find every tune by
    following links. Also sitemap.xml and robots.txt, and links to the type pages on
    the home page, for search engines too."""
    template = (ROOT / "site" / "index.html").read_text(encoding="utf-8")
    groups: dict[str, list[dict]] = {}
    for tune in tunes:
        groups.setdefault(tune["group"], []).append(tune)
    for versions in groups.values():
        versions.sort(key=lambda t: t["version"])
    types = {t["name"]: t for t in index["types"]}
    type_link = lambda name: f'<a href="{TYPE_DIR}/{type_slug(name)}/">{esc(type_heading(types[name]))}</a>'

    urls = []
    for group, versions in groups.items():
        first = versions[0]
        name = first["base"]
        url = f"{SITE_URL}{TUNE_DIR}/{group}/"
        urls.append(url)
        titles = list(dict.fromkeys(VERSION.sub(r"\1", t) for v in versions for t in v["titles"]))
        kind = TYPE_SINGULAR[first["type"]]
        key = f"{first['key']['root']} {first['key']['modeName']}" if first["key"] else None
        about = f"a{'n' if kind[0] in 'aeiou' else ''} Welsh {kind}" + (f" in {key}" if key else "")
        chords = any(v["chords"] is not None for v in versions)
        cy_key = f" yn {first['key']['root']} {CY_MODES.get(first['key']['modeName'], first['key']['modeName'])}" if key else ""
        description = (f"{name}: {about}. Sheet music{', suggested chords' if chords else ''} "
                       f"and playback in any key, at any tempo"
                       + (f" ({len(versions)} versions)" if len(versions) > 1 else "") + ". "
                       + f"Alaw werin o Gymru ({CY_TYPE[first['type']]}{cy_key}): y sgôr"
                       + (", cordiau" if chords else "") + " a chwarae mewn unrhyw gywair.")
        data = {"@context": "https://schema.org", "@type": "MusicComposition", "name": name, "url": url,
                "genre": "Welsh folk music"}
        if len(titles) > 1:
            data["alternateName"] = titles[1:]
        if key:
            data["musicalKey"] = key
        ld = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
        own = {**index, "tunes": versions, "say": {group: index["say"][group]} if group in index["say"] else {}}
        own = json.dumps(own, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
        details = "".join(f"<dt>{esc(label)}</dt><dd>"
                          + (re.sub(r"^(https?://\S+)", lambda m: f'<a href="{m[1]}">{m[1]}</a>', esc(value)) if label == "Source"
                             else esc(value))
                          + "</dd>" for label, value in first["details"])
        write_page(OUT / TUNE_DIR / group, app_page(
            template, title=name, description=description, url=url,
            head=f'\n  <script type="application/ld+json">{ld}</script>\n'
                 f'  <script type="application/json" id="tune-data">{own}</script>',
            scripts='<script src="static/abcjs/abcjs-basic-min.js" defer></script>\n  ',
            main=f"<h1>{esc(name)}</h1>"
                 + (f'<p class="caption">Also known as: {esc(", ".join(titles[1:]))}</p>' if len(titles) > 1 else "")
                 + f"<p>{esc(description)}</p><dl>{details}</dl>"
                 + f'<pre>{esc(first["abc"])}</pre><p>{type_link(first["type"])}</p>'
                 + '<p class="loading">Loading the sheet music…</p>'))

    # A page for each type: its tunes, A to Z.
    for name, kind in types.items():
        listed = sorted((v[0] for v in groups.values() if v[0]["type"] == name), key=lambda t: normalize(t["base"]))
        url = f"{SITE_URL}{TYPE_DIR}/{type_slug(name)}/"
        urls.append(url)
        heading = type_heading(kind)
        cy_kind = "alaw arall" if name == "Other" else CY_TYPE[name]
        some = ", ".join(t["base"] for t in listed[:4])
        plural = "other Welsh tunes" if name == "Other" else f"Welsh {kind['english']}"
        description = (f"{len(listed)} {plural}, each with its sheet music and playback in "
                       f"any key: {some} and more. {len(listed)} {cy_kind} o Gymru, gyda'r sgôr a chwarae mewn unrhyw gywair.")
        write_page(OUT / TYPE_DIR / type_slug(name), app_page(
            template, title=heading, description=description, url=url, head="",
            main=f"<h1>{esc(heading)}</h1><p>{esc(description)}</p><ul>"
                 + "".join(f'<li><a href="{TUNE_DIR}/{t["group"]}/">{esc(t["base"])}</a></li>' for t in listed)
                 + "</ul>"))

    # A moved tune's old address sends people (and search engines) on to the new one;
    # the app does the same offline, from tunes.json's "moved".
    by_slug = {t["slug"]: t for t in tunes}
    for move in index["moved"]:
        new = by_slug[move["to"]]
        to = f"../{new['group']}/" + (f"?v={new['version']}" if new["version"] > 1 else "")  # from alaw/<old>/
        url = f"{SITE_URL}{TUNE_DIR}/{to[3:]}"
        write_page(OUT / TUNE_DIR / move["from"], (
            '<!doctype html>\n<html lang="en">\n<head>\n  <meta charset="utf-8">\n'
            f'  <title>{esc(new["base"])} · Y Sesiwn</title>\n  <link rel="canonical" href="{esc(url)}">\n'
            f'  <meta http-equiv="refresh" content="0; url={esc(to)}">\n</head>\n'
            f'<body><p>This tune has moved: <a href="{esc(to)}">{esc(new["base"])}</a>.</p></body>\n</html>\n'))

    sessions_page(template, session_data())
    urls.append(f"{SITE_URL}{SESSIONS_DIR}/")

    # The home page links to the type pages until the app takes over.
    home = OUT / "index.html"
    nav = "".join(f"<li>{type_link(name)}</li>" for name in types)
    page = home.read_text(encoding="utf-8")
    old = '<p class="loading">Loading tunes…</p>'
    if page.count(old) != 1:
        raise SystemExit(f"site/index.html: expected one {old!r}")
    home.write_text(page.replace(old, old + f'<ul class="type-links">{nav}</ul>'), encoding="utf-8")

    pages = [SITE_URL] + [f"{SITE_URL}?page={p}" for p in ("browse", "notes", "map", "about", "add", "fix", "offline", "contact")]
    (OUT / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "".join(f"  <url><loc>{esc(u)}</loc></url>\n" for u in pages + urls) + "</urlset>\n", encoding="utf-8")
    (OUT / "robots.txt").write_text(f"User-agent: *\nAllow: /\nSitemap: {SITE_URL}sitemap.xml\n", encoding="utf-8")


# Wales's principal areas, for a session's county: English and Welsh.
COUNTIES = {
    "Isle of Anglesey": "Ynys Môn", "Gwynedd": "Gwynedd", "Conwy": "Conwy", "Denbighshire": "Sir Ddinbych",
    "Flintshire": "Sir y Fflint", "Wrexham": "Wrecsam", "Powys": "Powys", "Ceredigion": "Ceredigion",
    "Pembrokeshire": "Sir Benfro", "Carmarthenshire": "Sir Gâr", "Swansea": "Abertawe",
    "Neath Port Talbot": "Castell-nedd Port Talbot", "Bridgend": "Pen-y-bont ar Ogwr",
    "Vale of Glamorgan": "Bro Morgannwg", "Rhondda Cynon Taf": "Rhondda Cynon Taf", "Merthyr Tydfil": "Merthyr Tudful",
    "Caerphilly": "Caerffili", "Blaenau Gwent": "Blaenau Gwent", "Torfaen": "Tor-faen", "Monmouthshire": "Sir Fynwy",
    "Newport": "Casnewydd", "Cardiff": "Caerdydd", "Outside Wales": "Y tu allan i Gymru",
}
DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def session_data(today: "date | None" = None) -> list[dict]:
    """sessions.json, checked, with each session's id (for links to it), the Welsh for
    its town and county, and its position on site/wales.svg (none outside Wales). A
    session on announced dates (repeat: "dates") gets the day of its next one (as of
    the build, or its last if none is to come), for sorting and the day filter."""
    from datetime import date
    today = today or date.today()
    sessions, ids = [], set()
    for i, s in enumerate(json.loads((ROOT / "sessions.json").read_text(encoding="utf-8"))["sessions"]):
        where = f"sessions.json, session {i + 1} ({s.get('venue', '?')})"
        on_dates = s.get("repeat") == "dates"
        for field in ("venue", "address", "town", "county", "lat", "lon", "repeat", "start", "confirmed",
                      *(("dates",) if on_dates else ("day",))):
            if s.get(field) in (None, "", []):
                raise SystemExit(f"{where}: no {field}")
        dates = s.get("dates", [])
        problems = [
            s["county"] not in COUNTIES and f"county should be one of {', '.join(COUNTIES)}",
            not on_dates and s["day"] not in DAYS and f"day should be one of {', '.join(DAYS)}",
            on_dates and "day" in s and "a session on dates has no day (it's worked out from the dates)",
            on_dates and (not isinstance(dates, list) or not all(isinstance(d, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", d) for d in dates))
            and 'dates should be a list of dates like "2026-10-22"',
            on_dates and isinstance(dates, list) and dates != sorted(set(dates)) and "dates should be in order, each once",
            s["repeat"] not in ("weekly", "monthly", "dates") and 'repeat should be "weekly", "monthly" or "dates"',
            s.get("kind", "session") not in ("session", "tune club") and 'kind should be "tune club" (or left out, for a session)',
            s["repeat"] == "monthly" and s.get("nth") not in (1, 2, 3, 4, -1) and "a monthly session needs nth: 1-4, or -1 for the last",
            *[s.get(t) and not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", s[t]) and f'{t} should be a 24-hour time like "19:30"'
              for t in ("start", "end")],
            *[s.get(d) and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", s[d]) and f'{d} should be a date like "2026-10-02"'
              for d in ("from", "until", "confirmed")],
        ]
        for problem in problems:
            if problem:
                raise SystemExit(f"{where}: {problem}")
        if on_dates:
            upcoming = [d for d in dates if date.fromisoformat(d) >= today]
            if not upcoming:
                print(f"note: {where} has no dates to come (add the next one when it's announced)")
            s = {**s, "day": DAYS[date.fromisoformat((upcoming or dates[-1:])[0]).weekday()]}
        # (A session on dates is named without its day, which changes from date to date.)
        sid = slugify(f"{s['venue']} {s['town']}" + ("" if on_dates else f" {s['day']}"))
        if sid in ids:
            raise SystemExit(f"{where}: two sessions at {s['venue']}{'' if on_dates else ' on ' + s['day']}: give one a different venue name")
        ids.add(sid)
        x = round((s["lon"] - MAP["lon0"]) * MAP["k"] * MAP["scale"], 1)
        y = round((MAP["lat0"] - s["lat"]) * MAP["scale"], 1)
        sessions.append({**{k: v for k, v in s.items() if k not in ("lat", "lon")}, "id": sid,
                         "town_cy": s.get("town_cy", s["town"]), "county_cy": COUNTIES[s["county"]],
                         "lat": s["lat"], "lon": s["lon"],
                         **({"x": x, "y": y} if s["county"] != "Outside Wales" else {})})
    return sorted(sessions, key=lambda s: (normalize(s["town"]), DAYS.index(s["day"]), s["start"]))


def upcoming_dates(s: dict, today: "date") -> list["date"]:
    """A session on announced dates: those still to come (today's included)."""
    from datetime import date
    return [d for d in map(date.fromisoformat, s["dates"]) if d >= today]


def describe_session(s: dict, today: "date | None" = None) -> str:
    """'Every Tuesday, 19:00-21:00', '2nd Friday of the month, from 21:00' or
    'Thursday 22 October 2026, from 19:30', for the static page."""
    from datetime import date
    nth = {1: "1st", 2: "2nd", 3: "3rd", 4: "4th", -1: "Last"}
    time = f"{s['start']}–{s['end']}" if s.get("end") else f"from {s['start']}"
    if s["repeat"] == "dates":
        dates = upcoming_dates(s, today or date.today())
        if not dates:
            return "On dates announced as they come; none to come yet"
        return f"{', '.join(f'{DAYS[d.weekday()]} {d.day} {d:%B %Y}' for d in dates)}, {time}"
    when = f"Every {s['day']}" if s["repeat"] == "weekly" else f"{nth[s['nth']]} {s['day']} of the month"
    return f"{when}, {time}"


def next_session(s: dict, today: "date") -> "date | None":
    """The session's next date from today (app.js: nextSession)."""
    from datetime import date, timedelta
    if s["repeat"] == "dates":
        return next(iter(upcoming_dates(s, today)), None)
    day = max(today, date.fromisoformat(s["from"])) if s.get("from") else today
    until = date.fromisoformat(s["until"]) if s.get("until") else None
    for _ in range(400):
        if until and day > until:
            return None
        if day.weekday() == DAYS.index(s["day"]):
            last = (day + timedelta(days=7)).month != day.month
            if s["repeat"] == "weekly" or (s["nth"] == -1 and last) or (s["nth"] != -1 and (day.day - 1) // 7 + 1 == s["nth"]):
                return day
        day += timedelta(days=1)
    return None


def session_events(sessions: list[dict], today: "date") -> list[dict]:
    """The sessions as schema.org events (for search engines): where, and when they
    repeat, with the next date (as of the build) as startDate. A session on announced
    dates is an event for each date to come."""
    events = []
    for s in sessions:
        nxt = next_session(s, today)
        if not nxt:
            continue
        location = {"@type": "Place", "name": s["venue"],
                    "address": {"@type": "PostalAddress", "streetAddress": s["address"],
                                "addressLocality": s["town"], "addressRegion": s["county"], "addressCountry": "GB"},
                    "geo": {"@type": "GeoCoordinates", "latitude": s["lat"], "longitude": s["lon"]}}
        about = {"name": s.get("name") or f"Welsh folk session at {s['venue']}",
                 "eventStatus": "https://schema.org/EventScheduled",
                 "eventAttendanceMode": "https://schema.org/OfflineEventAttendanceMode",
                 "location": location, "description": s.get("music") or "A session where Welsh folk tunes are played.",
                 **({"url": s["link"]} if s.get("link") else {})}
        if s["repeat"] == "dates":
            for day in upcoming_dates(s, today):
                event = {"@type": "Event", **about, "startDate": f"{day.isoformat()}T{s['start']}"}
                if s.get("end"):
                    event["endDate"] = f"{day.isoformat()}T{s['end']}"
                events.append(event)
            continue
        schedule = {"@type": "Schedule", "byDay": f"https://schema.org/{s['day']}", "startTime": s["start"],
                    "scheduleTimezone": "Europe/London", "repeatFrequency": "P1W" if s["repeat"] == "weekly" else "P1M"}
        if s.get("end"): schedule["endTime"] = s["end"]
        if s["repeat"] == "monthly": schedule["byMonthWeek"] = s["nth"]
        if s.get("from"): schedule["startDate"] = s["from"]
        if s.get("until"): schedule["endDate"] = s["until"]
        events.append({"@type": "Event", **about, "startDate": f"{nxt.isoformat()}T{s['start']}", "eventSchedule": schedule})
    return events


def sessions_page(template: str, sessions: list[dict]) -> None:
    """sesiynau/: the sessions as plain HTML for search engines (the app draws its own),
    and sessions.json for the app."""
    (OUT / "sessions.json").write_text(json.dumps({"sessions": sessions}, ensure_ascii=False, separators=(",", ":")),
                                       encoding="utf-8")
    towns = sorted({s["town"] for s in sessions}, key=normalize)
    description = ("Active folk sessions with a heavy focus on Welsh music, in " + ", ".join(towns)
                   + ": their days and times, on a map. Sesiynau cyfredol sy'n canolbwyntio'n drwm ar gerddoriaeth Gymreig.")
    body = "".join(
        f"<h2>{esc(town)}</h2><ul>" + "".join(
            f"<li><strong>{esc(s.get('name') or s['venue'])}</strong>{' (tune club)' if s.get('kind') == 'tune club' else ''}: {esc(describe_session(s))}. "
            f"{esc(s['venue'])}, {esc(s['address'])}. Last confirmed {esc(s['confirmed'])}.</li>"
            for s in sessions if s["town"] == town) + "</ul>"
        for town in towns)
    from datetime import date
    ld = json.dumps({"@context": "https://schema.org", "@graph": session_events(sessions, date.today())},
                    ensure_ascii=False).replace("</", "<\\/")
    write_page(OUT / SESSIONS_DIR, app_page(
        template, title="Active sessions", description=description, url=f"{SITE_URL}{SESSIONS_DIR}/",
        head=f'\n  <script type="application/ld+json">{ld}</script>', up="../", main=f"<h1>Active sessions</h1><p>{esc(description)}</p>{body}"))


def type_heading(kind: dict) -> str:
    """'Welsh jigs (Jig)': the English for search engines, and the site's own name for it."""
    return "Other Welsh tunes" if kind["name"] == "Other" else f"Welsh {kind['english']} ({kind['name']})"


def write_service_worker() -> None:
    """Fill in sw.js: which files to keep for offline use, and a version that
    changes whenever any of them does (so browsers pick up a new deploy)."""
    def digest(files: list[Path]) -> str:
        h = hashlib.sha256()
        for f in files:
            h.update(f.relative_to(OUT).as_posix().encode() + f.read_bytes())
        return h.hexdigest()[:12]

    # The tunes', types' and sessions' own pages aren't kept: offline, sw.js answers them with the app itself.
    files = sorted(f for f in OUT.rglob("*") if f.is_file() and f.name not in NOT_OFFLINE
                   and not any(f.is_relative_to(OUT / d) for d in (TUNE_DIR, TYPE_DIR, SESSIONS_DIR)))
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
    import sys
    if "--number-tunes" in sys.argv:
        number_tunes()
    main()
