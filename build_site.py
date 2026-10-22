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
EMBED_DIR = "embed"  # each tune for other websites, embed/<folder>/ (see tune_pages)

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
# tempos in the ABC files are ignored; a `%%bpm` line overrides the default.
DEFAULT_BPM = {"jig": 112, "ril": 90, "reel": 90, "polca": 100, "polka": 100}
OTHER_BPM = 100
# Airs and songs are played slowly: crotchet = 66, whatever note is the beat.
SLOW_TYPES = {"Alaw", "Cân"}
SLOW_CROTCHETS = 66

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
    "Jig naid": ("slip jigs", "#7a5230"),  # walnut
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
    "Jig": "jig", "Jig naid": "slip jig", "Polca": "polka", "Walts": "waltz", "Rîl": "reel",
    "Pibddawns": "hornpipe", "Ymdaith": "march", "Dawns": "dance", "Alaw": "air", "Cân": "song", "Carol": "carol", "Other": "tune",
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


def melody_notes(abc: str) -> list[tuple[int, bool]]:
    """Each note (top note of chords) in written order: its MIDI pitch, and whether it
    only holds on the note before it (tied to it, the same pitch)."""
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

    notes: list[tuple[int, bool]] = []
    tie = False  # the note before ends in a tie, "-"
    for m in re.finditer(r"\[K:([^\]]*)\]|(?:" + NOTE_TOKEN.pattern + r")[\d/]*(\s*-)?", body):
        if m.group(1) is not None:  # key change
            signature = key_signature(m.group(1))
            bar.clear()
            continue
        tied = m.group(7) is not None
        m = NOTE_TOKEN.match(m.group(0))
        if m.group(5):
            bar.clear()
            continue
        if m.group(1) is not None:
            chord = [pitch(*n.groups()) for n in re.finditer(r"(\^\^|\^|__|_|=)?([A-Ga-g])([,']*)", m.group(1))]
            p = max(chord)
        else:
            p = pitch(m.group(2), m.group(3), m.group(4))
        notes.append((p, tie and bool(notes) and notes[-1][0] == p))
        tie = tied
    return notes


def melody(abc: str) -> list[int]:
    """MIDI pitches of the tune's notes in written order (top note of chords), a note
    tied to the one before it being the same note held, not another."""
    return [p for p, held in melody_notes(abc) if not held]


LENGTH_TOKEN = re.compile(
    r"\((\d)"                                                       # tuplet: (3
    r"|(?:\[[^\]|]*\]|(?:\^\^|\^|__|_|=)?[A-Ga-g][,']*|[zx])(\d*)(/*)(\d*)"  # chord/note/rest, length
    r"|(\|)"                                                         # bar line
)
TUPLETS = {2: Fraction(3, 2), 3: Fraction(2, 3), 4: Fraction(3, 4), 6: Fraction(2, 3)}


# The time signatures written as symbols: common time and cut time.
METER_SYMBOLS = {"C": "4/4", "C|": "2/2"}


def meter_length(abc: str) -> Fraction | None:
    """A bar's length in whole notes, from M: (C is 4/4, C| is 2/2)."""
    meter = (parse_headers(abc).get("M") or [""])[0].strip()
    meter = METER_SYMBOLS.get(meter, meter)
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
    return sum(not held for _, held in melody_notes(abc)[: lead_in(abc)])


def melody_string(abc: str) -> str:
    """The melody for the note search, one character per note: chr(MIDI pitch + 160).
    The app works it out itself (melodyOf in app.js); the tests check the two agree
    for every tune."""
    return "".join(chr(p + 160) for p in melody(abc))


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
    """Browsing category from R:, e.g. "polca/pibddawns" -> "Polca".

    A jig is in 6/8; one in 9/8 is a slip jig (jig naid), whatever R: calls it.
    """
    rhythm = normalize(" ".join(headers.get("R", [])))
    meter = "".join(headers.get("M", [""])[:1]).replace(" ", "")
    if re.search(r"\bslip ?jig|\bjig naid", rhythm) or (meter == "9/8" and "jig" in rhythm):
        return "Jig naid"
    words = rhythm.split()
    for table in (SPECIFIC_TYPES, GENERIC_TYPES):
        for word in words:
            for prefix, label in table.items():
                if word.startswith(prefix):
                    return label
    return "Other"


def beat_unit(meter: str, slow: bool = False) -> Fraction:
    """The note felt as one beat: 6/8 -> 3/8, 4/4 and 2/2 -> 1/2, 2/4 -> 1/4.

    4/4 is counted in two (minims), as reels and polcas are played, except in a
    slow air or song, which is counted in four.
    """
    meter = {"C": "4/4", "C|": "2/2"}.get(meter.strip(), meter.strip())
    m = re.match(r"^(\d+)/(\d+)$", meter)
    if not m:
        return Fraction(1, 4)
    num, den = int(m.group(1)), int(m.group(2))
    if den >= 8 and num % 3 == 0 and num > 3:
        return Fraction(3, den)  # compound time: dotted beats
    if (num, den) == (4, 4) and not slow:
        return Fraction(1, 2)
    return Fraction(1, den)


def own_beat(abc: str) -> Fraction | None:
    """The beat a tune's `%%beat 1/2` line gives, or None.

    For music written in notes twice as long as usual (Alawon Cymru's "Set Polcas
    Bob": a polca in 2/4 felt in minims, not crotchets), so its default tempo is
    counted on the note that's felt as the beat.
    """
    m = re.search(r"^%%beat\s+(\d+)/(\d+)\s*$", abc, re.M)
    return Fraction(int(m.group(1)), int(m.group(2))) if m and int(m.group(1)) else None


def own_bpm(abc: str) -> int | None:
    """The tempo a tune's `%%bpm 114` line gives (beats per minute), or None.

    For a tune whose composer gives a tempo the tune type's default doesn't match.
    """
    m = re.search(r"^%%bpm\s+(\d+)\s*$", abc, re.M)
    return int(m.group(1)) if m and int(m.group(1)) else None


def default_bpm(headers: dict[str, list[str]], beat: Fraction = Fraction(1, 4)) -> int:
    """Default from the tune type (earliest match in R:, e.g. "polca/ymdaith").

    An air or song is slow: crotchet = 66, so minim = 33 and dotted crotchet = 44.
    """
    if tune_type(headers) in SLOW_TYPES:
        return round(SLOW_CROTCHETS * Fraction(1, 4) / beat)
    rhythm = normalize(" ".join(headers.get("R", [])))
    matches = [(rhythm.find(word), bpm) for word, bpm in DEFAULT_BPM.items() if word in rhythm]
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
        if field == "M":  # as numbers, so "C" isn't read as a key
            values = [METER_SYMBOLS.get(v.strip(), v.strip()) for v in values]
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


def own_version_label(abc: str) -> str | None:
    """The name a tune's `%%version Bob Evans` line gives its version's tab, or None.

    For a version learnt from a player, with no book or site to name it after.
    """
    m = re.search(r"^%%version\s+(.*\S)", abc, re.M)
    return m.group(1) if m else None


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
    beat = own_beat(abc) or beat_unit((headers.get("M") or [""])[0], tune_type(headers) in SLOW_TYPES)
    rows, gloss = details(headers)
    # Versions of a tune ("Rheged (version 2)") share one page, under the base title.
    m = VERSION.match(titles[0])
    base, number = (m.group(1), int(m.group(2))) if m else (titles[0], 1)
    return {
        "slug": path.parent.name,
        "group": slugify(base),
        "base": base,
        "version": number,
        "source": own_version_label(abc) or version_label(headers),
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
        "bpm": own_bpm(abc) or default_bpm(headers, beat),
        "details": rows,
        # Where the melody starts after the lead-in. The app works out the title, the
        # search names and the melody (melody_string) itself, so they aren't in tunes.json.
        "lead": lead_index(abc),
        "gloss": gloss,
        "chords": chords_source(abc),
        "abc": abc,
    }


# The projection site/wales.svg was drawn with (see the comment in it).
MAP = {"lon0": -5.669900, "lat0": 53.435690, "k": 0.610145, "scale": 100}


def pronunciations(groups: set[str]) -> dict[str, str]:
    """pronunciation.json: how to say each Welsh tune name, by the tune's folder name."""
    data = json.loads((ROOT / "pronunciation.json").read_text(encoding="utf-8"))
    say, english = data["say"], set(data.get("english", []))
    unknown = (set(say) | english) - groups
    if unknown:
        raise SystemExit(f"pronunciation.json: no tune called {', '.join(sorted(unknown))}")
    both = set(say) & english
    if both:
        raise SystemExit(f"pronunciation.json: both said and English: {', '.join(sorted(both))}")
    return say


def places(groups: set[str]) -> list[dict]:
    """places.json, with each place's position on site/wales.svg."""
    result = []
    data = json.loads((ROOT / "places.json").read_text(encoding="utf-8"))
    unknown = set(data.get("not_places", [])) - groups
    if unknown:
        raise SystemExit(f"places.json: no tune called {', '.join(sorted(unknown))} (not_places)")
    for place in data["places"]:
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


# ---- Chords carried across from Alawon Cymru ---------------------------------------
# Alawon Cymru's scores have chords; the books mostly don't. Where a tune's Alawon Cymru
# version is the only one with chords, another version that has the same form and much
# the same melody gets them too (in its own key), marked as Alawon Cymru's.

CARRIED_CHORDS = "From Alawon Cymru's version of this tune"  # app.js: CY_CHORD_SOURCES
BODY_TOKEN = re.compile(r"""
  (?P<text>"[^"]*")                                          # chord name or annotation
 |(?P<grace>\{[^}]*\})|(?P<deco>![^!]*!|\+[^+]*\+)|(?P<short>[~.HLMOPSTuv])
 |(?P<field>\[[A-Za-z]:[^\]]*\])                              # [K:G], [M:3/4]
 |(?P<bar>(?::*\[?\|+\]?:*|::+)(?:\s*\[?(?P<ending>\d+(?:[,-]\d+)*))?)  # |, :|2, ::, |]
 |\[(?P<label>\d+(?:[,-]\d+)*)                                # [2: an ending
 |\((?P<tuplet>\d)(?::(?P<q>\d*))?(?::(?P<r>\d*))?           # (3, (3:2:3
 |\[(?P<chord>[^\]|]*)\](?P<chord_len>\d*/*\d*)               # [ceg]2
 |(?P<acc>\^\^|\^|__|_|=)?(?P<letter>[A-Ga-g])(?P<marks>[,']*)(?P<len>\d*/*\d*)
 |(?P<rest>[zx])(?P<rest_len>\d*/*\d*)
 |(?P<unsure>Z)                                               # a rest of several bars
 |(?P<broken>[<>]+)
 |(?P<space>\s+)
 |.""", re.X)
TUPLET_TIME = {2: 3, 3: 2, 4: 3, 6: 2, 8: 3}  # (p: p notes in the time of this many
CHORD_NAME = re.compile(r"^([A-G])([#b]?)([^/]*)(?:/([A-G])([#b]?))?$")
SHARP_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
FLAT_NAMES = ["C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B"]


def note_length(text: str) -> Fraction:
    """'3/2' -> 3/2, '/' -> 1/2, '' -> 1, in units of L:."""
    m = re.fullmatch(r"(\d*)(/*)(\d*)", text)
    n = Fraction(int(m.group(1) or 1))
    if m.group(2):
        n /= int(m.group(3)) if m.group(3) else 2 ** len(m.group(2))
    return n


def ending_numbers(text: str) -> set[int]:
    """'1,3' -> {1, 3}; '1-3' -> {1, 2, 3}."""
    out = set()
    for part in text.split(","):
        first, _, last = part.partition("-")
        out.update(range(int(first), int(last or first) + 1))
    return out


class Bar:
    def __init__(self, ending: set[int] = frozenset(), start_repeat: bool = False):
        self.notes: list[dict] = []  # each: at (where its chord name would go), start, length (in bars), pitch, chords
        self.ending, self.start_repeat = set(ending), start_repeat
        self.end_repeat = self.double = self.line_end = False


def score_bars(abc: str) -> tuple[list[Bar], Fraction] | None:
    """The tune's bars as written, and a bar's length in whole notes; None for what
    this doesn't follow (several voices, a change of metre, a rest of several bars)."""
    bar_len = meter_length(abc)
    if not bar_len or re.search(r"^V:", abc, re.M):
        return None
    unit = (parse_headers(abc).get("L") or [""])[0].strip()
    unit = Fraction(unit) if re.fullmatch(r"\d+/\d+", unit) else Fraction(1, 8 if bar_len >= Fraction(3, 4) else 16)
    lines = abc.split("\n")
    k = next(i for i, line in enumerate(lines) if line.startswith("K:"))
    signature = key_signature(lines[k][2:])
    offset = sum(len(line) + 1 for line in lines[: k + 1])
    bars, bar = [], Bar()
    accidentals: dict[tuple[str, int], int] = {}
    tuplet, left = Fraction(1), 0
    broken, last, prefix, chords = None, None, None, []

    def pitch(acc: str | None, letter: str, marks: str) -> int:
        octave = (1 if letter.islower() else 0) + marks.count("'") - marks.count(",")
        name = letter.upper()
        if acc:
            accidentals[(name, octave)] = ACCIDENTALS[acc]
        return 60 + 12 * octave + PITCH[name] + accidentals.get((name, octave), signature.get(name, 0))

    for line in lines[k + 1:]:
        here, offset = offset, offset + len(line) + 1
        if line.startswith("K:"):
            signature = key_signature(line[2:])
            continue
        if line.startswith("M:"):
            return None
        if re.match(r"^(%|[A-Za-z]:)", line):
            continue
        for m in BODY_TOKEN.finditer(re.sub(r"%.*", "", line)):
            if m["text"] or m["grace"] or m["deco"] or m["short"]:
                prefix = here + m.start() if prefix is None else prefix
                if m["text"] and re.match(r"[A-G]", m["text"][1:]):
                    chords.append(m["text"][1:-1])
            elif m["field"]:
                if m["field"].startswith("[M:"):
                    return None
                if m["field"].startswith("[K:"):
                    signature = key_signature(m["field"][3:-1])
            elif m["bar"] is not None:
                token, prefix = m["bar"], None
                accidentals.clear()
                end = token.lstrip().startswith(":")
                if bar.notes:
                    bar.end_repeat = end
                    bar.double = end or bool(re.search(r"\|\||\|\]|\[\||::", token))
                    bars.append(bar)
                    bar = Bar()
                elif end and bars:
                    bars[-1].end_repeat = bars[-1].double = True
                bar.start_repeat = bar.start_repeat or token.rstrip().endswith(":")
                if m["ending"]:
                    bar.ending = ending_numbers(m["ending"])
            elif m["label"]:
                bar.ending = ending_numbers(m["label"])
            elif m["tuplet"]:
                p = int(m["tuplet"])
                tuplet = Fraction(int(m["q"]) if m["q"] else TUPLET_TIME.get(p, 2), p)
                left = int(m["r"]) if m["r"] else p
            elif m["unsure"]:
                return None
            elif m["broken"]:
                broken = m["broken"]
            elif m["chord"] is not None or m["letter"] or m["rest"]:
                if m["chord"] is not None:
                    inside = list(re.finditer(r"(\^\^|\^|__|_|=)?([A-Ga-g])([,']*)(\d*/*\d*)", m["chord"]))
                    if not inside:
                        continue
                    length = note_length(inside[0][4]) * note_length(m["chord_len"])
                    sound = max(pitch(*n.groups()[:3]) for n in inside)
                elif m["letter"]:
                    length, sound = note_length(m["len"]), pitch(m["acc"], m["letter"], m["marks"])
                else:
                    length, sound = note_length(m["rest_len"]), None
                length *= unit / bar_len
                if left:
                    length, left = length * tuplet, left - 1
                if broken and last:
                    short = Fraction(1, 2 ** len(broken))
                    last["length"] *= 2 - short if broken[0] == ">" else short
                    length *= short if broken[0] == ">" else 2 - short
                broken = None
                last = {"at": here + m.start() if prefix is None else prefix, "length": length, "pitch": sound, "chords": chords}
                bar.notes.append(last)
                prefix, chords = None, []
            elif m["space"]:
                prefix = None
        (bar if bar.notes else bars[-1] if bars else bar).line_end = True
    if bar.notes:
        bars.append(bar)
    if not bars:
        return None
    bars[-1].double = True
    for b in bars:
        b.length = Fraction(0)
        for note in b.notes:
            note["start"], b.length = b.length, b.length + note["length"]
    return bars, bar_len


def played_order(bars: list[Bar]) -> list[int]:
    """The written bars in the order they're played: repeats and endings followed."""
    label: set[int] = set()  # an ending goes on to a repeat or double bar line, the line's end or the next ending
    for b in bars:
        if b.ending or b.start_repeat:
            label = b.ending
        b.ending = label
        if b.end_repeat or b.double or b.line_end:
            label = set()
    order, i, start, turn = [], 0, 0, 1
    while i < len(bars) and len(order) < 10 * len(bars):
        b = bars[i]
        if b.start_repeat and turn == 1:
            start = i
        if b.ending and turn not in b.ending:
            i += 1
            continue
        if not b.ending and turn > 1 and i > start and bars[i - 1].ending:
            turn, start = 1, i
        order.append(i)
        if b.end_repeat:
            if turn == 1 or turn + 1 in set().union(*(x.ending for x in bars[i + 1:i + 8])):
                turn, i = turn + 1, start
                continue
            turn, start = 1, i + 1
        elif b.double:
            turn, start = 1, i + 1
        i += 1
    return order


def played_notes(bars: list[Bar], whole: Fraction) -> list[tuple[Fraction, dict]]:
    """Each note as played, with when it starts: in whole notes from the first downbeat
    (a lead-in starts before 0), a bar being `whole` long."""
    order = played_order(bars)
    t = -bars[order[0]].length * whole if bars[order[0]].length < 1 else Fraction(0)
    out = []
    for i in order:
        out += [(t + note["start"] * whole, note) for note in bars[i].notes]
        t += bars[i].length * whole
    return out


def sounding(notes: list[tuple[Fraction, dict]], whole: Fraction, end: Fraction) -> list[int | None]:
    """The pitch heard every 1/48 of a whole note (None for a rest), from 0 to end."""
    out, k = [], 0
    for g in range(int(end * 48)):
        t = Fraction(g, 48)
        while k + 1 < len(notes) and notes[k + 1][0] <= t:
            k += 1
        start, note = notes[k]
        out.append(note["pitch"] if start <= t < start + note["length"] * whole else None)
    return out


def alike(a: list[int | None], b: list[int | None], shift: int) -> float:
    """How much of the time the two play the same note (b `shift` semitones up)."""
    either = sum(x is not None or y is not None for x, y in zip(a, b))
    same = sum(x is not None and y is not None and (x + shift - y) % 12 == 0 for x, y in zip(a, b))
    return same / either if either else 0


def transpose_chord(name: str, shift: int, flats: bool) -> str:
    m = CHORD_NAME.match(name)
    if not m or not shift:
        return name
    names = FLAT_NAMES if flats else SHARP_NAMES
    move = lambda root, acc: names[(PITCH[root] + {"#": 1, "b": -1}.get(acc, 0) + shift) % 12]
    return move(m[1], m[2]) + m[3] + (f"/{move(m[4], m[5])}" if m[4] else "")


def carried_chords(source: str, abc: str) -> tuple[float, str] | None:
    """abc with source's chords on it, and how alike their melodies are, if the two have
    the same form (bar for bar as played, allowing for lead-ins written differently and
    bars twice or half as long) and much the same melody: the same note at least 3/4 of
    the time, and at least half the time in any two bars. Every chord must start with a
    note. Else None."""
    a, b = score_bars(source), score_bars(abc)
    if not a or not b:
        return None
    (a_bars, a_whole), (b_bars, b_whole) = a, b
    a_notes = played_notes(a_bars, a_whole)
    a_end = sum(a_bars[i].length for i in played_order(a_bars)) * a_whole
    b_end = sum(b_bars[i].length for i in played_order(b_bars)) * b_whole
    if not b_end:
        return None
    scale = min((Fraction(1, 2), Fraction(1), Fraction(2)), key=lambda s: abs(a_end / b_end - s))
    b_whole *= scale
    b_notes = played_notes(b_bars, b_whole)
    b_end *= scale
    if abs(a_end - b_end) >= max(a_whole, b_whole):
        return None
    end = min(a_end, b_end)
    a_heard, b_heard = sounding(a_notes, a_whole, end), sounding(b_notes, b_whole, end)
    shift = max(range(12), key=lambda s: alike(a_heard, b_heard, s))
    window = int(2 * min(a_whole, b_whole) * 48)
    stretches = [alike(a_heard[i:i + window], b_heard[i:i + window], shift)
                 for i in range(0, max(1, len(a_heard) - window + 1), max(1, window // 2))]
    similar = alike(a_heard, b_heard, shift)
    if similar < 0.75 or min(stretches) < 0.5:
        return None
    starts: dict[Fraction, dict] = {}
    for t, note in b_notes:
        starts.setdefault(t, note)
    placed: dict[int, str] = {}  # id of the note -> its chord
    notes_by_id = {id(note): note for _, note in b_notes}
    for t, note in a_notes:
        for chord in note["chords"]:
            if t not in starts:
                return None
            placed.setdefault(id(starts[t]), chord)
    flats = any(v < 0 for v in key_signature((parse_headers(abc).get("K") or [""])[0]).values())
    edits, current = [], None
    for bar in b_bars:
        for i, note in enumerate(bar.notes):
            chord = placed.get(id(note))
            if chord is None or (chord == current and i):  # the same chord again, mid-bar
                continue
            current = chord
            edits.append((notes_by_id[id(note)]["at"], f'"{transpose_chord(chord, shift, flats)}"'))
    if not edits:
        return None
    for at, text in sorted(edits, reverse=True):
        abc = abc[:at] + text + abc[at:]
    return similar, re.sub(r"^K:", f"%%chords {CARRIED_CHORDS}\nK:", abc, count=1, flags=re.M)


def carry_chords(tunes: list[dict]) -> None:
    """Where a tune's only versions with chords are Alawon Cymru's, give its other
    versions those chords if they fit (carried_chords): from the one whose melody is
    most like theirs, if there are several."""
    groups: dict[str, list[dict]] = {}
    for tune in tunes:
        groups.setdefault(tune["group"], []).append(tune)
    for versions in groups.values():
        with_chords = [t for t in versions if t["chords"] is not None]
        if not with_chords or any(t["source"] != "Alawon Cymru" for t in with_chords):
            continue
        for tune in versions:
            if tune["chords"] is None:
                fits = [c for source in with_chords if (c := carried_chords(source["abc"], tune["abc"]))]
                if fits:
                    tune["abc"], tune["chords"] = max(fits, key=lambda c: c[0])[1], CARRIED_CHORDS


def show_versions(tunes: list[dict]) -> None:
    """Number each tune's versions in the order they're shown ("shown"): Alawon Cymru's
    after those from books and players, which are usually the better ones to learn from,
    and before any we don't know the source of; otherwise by version. A version's own
    number ("version") stays as it is, as its folder, ?v= and set links depend on it."""
    groups: dict[str, list[dict]] = {}
    for tune in tunes:
        groups.setdefault(tune["group"], []).append(tune)
    for versions in groups.values():
        rank = lambda t: 1 if t["source"] == "Alawon Cymru" else 2 if t["source"] in ("", "Source unknown") else 0
        versions.sort(key=lambda t: (rank(t), t["version"]))
        for shown, tune in enumerate(versions, 1):
            tune["shown"] = shown


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
    carry_chords(tunes)
    show_versions(tunes)
    first_shown = [t for t in tunes if t["shown"] == 1]  # a tune is the type of the version it opens on
    counts = {t: sum(tune["type"] == t for tune in first_shown) for t in TYPE_ORDER}
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
# GitHub Pages' "not found" page (offline, sw.js answers every address with the app), and
# GridinSoft's file proving we own the domain.
NOT_OFFLINE = {"sw.js", "og-image.png", "CNAME", "sitemap.xml", "robots.txt", "404.html", "embed.html",
               "gridinsoft-qwhiwg62aaa11k3qbqvvhusx8eo7c6v2tjj40adno3rw650jcp1du72cqupbn9ay.txt"}


# Welsh for the tune pages' descriptions (app.js has the same: CY_TYPE, CY_MODES).
CY_TYPE = {"Jig": "jig", "Jig naid": "jig naid", "Polca": "polca", "Walts": "walts", "Rîl": "rîl", "Pibddawns": "pibddawns", "Ymdaith": "ymdaith",
           "Dawns": "dawns", "Alaw": "alaw", "Cân": "cân", "Carol": "carol", "Other": "alaw"}
CY_MODES = {"major": "fwyaf", "minor": "leiaf", "Dorian": "Doriaidd", "Phrygian": "Phrygaidd", "Lydian": "Lydaidd",
            "Mixolydian": "Mixolydaidd", "Locrian": "Locriaidd"}

esc = lambda text: html.escape(text, quote=True)


def type_slug(name: str) -> str:
    """A type's page, math/<slug>/: 'Rîl' -> 'ril' (app.js: typeSlug)."""
    return slugify(name)


def app_page(template: str, *, title: str, description: str, url: str, head: str, main: str,
             scripts: str = "", up: str = "../../", loading: str = "Loading…", kind: str = "other") -> str:
    """The app (index.html) in a folder (two down, unless up says otherwise), with its
    own title, description and address in the head, for link previews and search
    engines (which don't run the app), and what they should read in <main> (hidden from
    readers whose browser runs the app, which shows loading until it takes over)."""
    def swap(page: str, old: str, new: str) -> str:
        if page.count(old) != 1:
            raise SystemExit(f"site/index.html: expected one {old!r} (for the tune and type pages)")
        return page.replace(old, new)

    page = template
    page = swap(page, '<base href="./">', f'<base href="{up}">')
    # What the app will mark it (body[data-page]), so its layout is right from the start.
    page = swap(page, "<body>", f'<body data-page="{kind}">')
    page = swap(page, '<script src="app.js" defer></script>', scripts + '<script src="app.js" defer></script>')
    page = swap(page, "<title>Y Sesiwn</title>", f"<title>{esc(title)} · Y Sesiwn</title>")
    page = re.sub(r'(<meta (?:name|property)="(?:og:)?description" content=")[^"]*"',
                  lambda m: m.group(1) + esc(description) + '"', page)
    page = swap(page, '<meta property="og:title" content="Y Sesiwn: Welsh folk tunes">',
                f'<meta property="og:title" content="{esc(title)} · Y Sesiwn">')
    page = swap(page, f'<meta property="og:url" content="{SITE_URL}">',
                f'<meta property="og:url" content="{url}">\n  <link rel="canonical" href="{url}">' + head)
    return swap(page, '<main id="main" tabindex="-1"><p class="loading">Loading tunes…</p></main>',
                f'<main id="main" tabindex="-1"><div class="static">{main}</div><p class="loading">{esc(loading)}</p></main>')


def write_page(folder: Path, page: str) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "index.html").write_text(page, encoding="utf-8")


def tune_pages(tunes: list[dict], index: dict) -> None:
    """A real page for each tune, at alaw/<folder>/, and for each type of tune, at
    math/<type>/ (see app_page). A tune's page also carries tunes.json cut down to this
    tune, so the app can draw it without waiting for every other tune (a shared link on
    a phone, say); a type's lists its tunes, so search engines find every tune by
    following links. Also sitemap.xml and robots.txt, and links to the type pages on
    the home page, for search engines too. And each tune for other websites to show, at
    embed/<folder>/ (site/embed.html, with the tune's data as its page has)."""
    template = (ROOT / "site" / "index.html").read_text(encoding="utf-8")
    embed_template = (ROOT / "site" / "embed.html").read_text(encoding="utf-8")
    (OUT / "embed.html").unlink()  # only the template
    groups: dict[str, list[dict]] = {}
    for tune in tunes:
        groups.setdefault(tune["group"], []).append(tune)
    for versions in groups.values():
        versions.sort(key=lambda t: t["shown"])
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
        description = (f"{name}: {about}. Sheet music{', example chords' if chords else ''} "
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
                 + f'<pre>{esc(first["abc"])}</pre><p>{type_link(first["type"])}</p>',
            loading="Loading the sheet music…", kind="tune"))
        page = embed_template.replace("<title>Y Sesiwn</title>", f"<title>{esc(name)} · Y Sesiwn</title>\n"
                                      f'  <link rel="canonical" href="{url}">\n'
                                      f'  <script type="application/json" id="tune-data">{own}</script>', 1)
        write_page(OUT / EMBED_DIR / group, page)

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
                 + "</ul>", loading="Loading tunes…"))

    # A moved tune's old address sends people (and search engines) on to the new one;
    # the app does the same offline, from tunes.json's "moved".
    by_slug = {t["slug"]: t for t in tunes}
    for move in index["moved"]:
        new = by_slug[move["to"]]
        to = f"../{new['group']}/" + (f"?v={new['version']}" if new["shown"] > 1 else "")  # from alaw/<old>/
        url = f"{SITE_URL}{TUNE_DIR}/{to[3:]}"
        write_page(OUT / TUNE_DIR / move["from"], (
            '<!doctype html>\n<html lang="en">\n<head>\n  <meta charset="utf-8">\n'
            f'  <title>{esc(new["base"])} · Y Sesiwn</title>\n  <link rel="canonical" href="{esc(url)}">\n'
            f'  <meta http-equiv="refresh" content="0; url={esc(to)}">\n</head>\n'
            f'<body><p>This tune has moved: <a href="{esc(to)}">{esc(new["base"])}</a>.</p></body>\n</html>\n'))

    sessions = session_data()
    sessions_page(template, sessions)
    urls += [f"{SITE_URL}{SESSIONS_DIR}/"] + [f"{SITE_URL}{SESSIONS_DIR}/{s['id']}/" for s in sessions]

    # The home page links to the type pages until the app takes over.
    home = OUT / "index.html"
    nav = "".join(f"<li>{type_link(name)}</li>" for name in types)
    page = home.read_text(encoding="utf-8")
    old = '<p class="loading">Loading tunes…</p>'
    if page.count(old) != 1:
        raise SystemExit(f"site/index.html: expected one {old!r}")
    home.write_text(page.replace(old, f'<div class="static"><ul class="type-links">{nav}</ul></div>' + old), encoding="utf-8")

    pages = [SITE_URL] + [f"{SITE_URL}?page={p}" for p in ("browse", "notes", "map", "about", "add", "fix", "embed", "offline", "contact")]
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
            s["repeat"] not in ("weekly", "fortnightly", "monthly", "dates") and 'repeat should be "weekly", "fortnightly", "monthly" or "dates"',
            s["repeat"] == "fortnightly" and not s.get("from") and "a fortnightly session needs from: the date of one it meets on",
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
        if s["repeat"] == "fortnightly" and DAYS[date.fromisoformat(s["from"]).weekday()] != s["day"]:
            raise SystemExit(f"{where}: from should be a {s['day']}, the day it meets")
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
    """'Every Tuesday, 19:00-21:00', 'Every other Thursday, from 20:00', '2nd Friday of the month, from 21:00' or
    'Thursday 22 October 2026, from 19:30', for the static page."""
    from datetime import date
    nth = {1: "1st", 2: "2nd", 3: "3rd", 4: "4th", -1: "Last"}
    time = f"{s['start']}–{s['end']}" if s.get("end") else f"from {s['start']}"
    if s["repeat"] == "dates":
        dates = upcoming_dates(s, today or date.today())
        if not dates:
            return "On dates announced as they come; none to come yet"
        return f"{', '.join(f'{DAYS[d.weekday()]} {d.day} {d:%B %Y}' for d in dates)}, {time}"
    when = {"weekly": f"Every {s['day']}", "fortnightly": f"Every other {s['day']}"}.get(s["repeat"]) \
        or f"{nth[s['nth']]} {s['day']} of the month"
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
            if s["repeat"] == "fortnightly":
                if (day - date.fromisoformat(s["from"])).days % 14 == 0:
                    return day
            elif s["repeat"] == "weekly" or (s["nth"] == -1 and last) or (s["nth"] != -1 and (day.day - 1) // 7 + 1 == s["nth"]):
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
                    "scheduleTimezone": "Europe/London", "repeatFrequency": {"weekly": "P1W", "fortnightly": "P2W"}.get(s["repeat"], "P1M")}
        if s.get("end"): schedule["endTime"] = s["end"]
        if s["repeat"] == "monthly": schedule["byMonthWeek"] = s["nth"]
        if s.get("from"): schedule["startDate"] = s["from"]
        if s.get("until"): schedule["endDate"] = s["until"]
        events.append({"@type": "Event", **about, "startDate": f"{nxt.isoformat()}T{s['start']}", "eventSchedule": schedule})
    return events


def session_title(s: dict) -> str:
    """A session's own page's title: its name, or what it is and where ('Session at Tŷ
    Tawe, Swansea'). A name that doesn't say where gets the town, and the venue too if it
    says neither ('Sesiwn Werin, Cwrw, Carmarthen': there's more than one Sesiwn Werin)
    (app.js: sessionTitle)."""
    if s.get("name"):
        has = lambda part: normalize(part) in normalize(s["name"])
        return ", ".join([s["name"]] + ([] if has(s["town"]) or has(s["venue"]) else [s["venue"]])
                         + ([] if has(s["town"]) else [s["town"]]))
    return f"{'Tune club' if s.get('kind') == 'tune club' else 'Session'} at {s['venue']}, {s['town']}"


def sessions_page(template: str, sessions: list[dict]) -> None:
    """sesiynau/: the sessions as plain HTML for search engines (the app draws its own),
    and sessions.json for the app. Each session also has a page of its own,
    sesiynau/<id>/, to send or link to: its link preview and search result are that
    session's, not the whole list's."""
    (OUT / "sessions.json").write_text(json.dumps({"sessions": sessions}, ensure_ascii=False, separators=(",", ":")),
                                       encoding="utf-8")
    towns = sorted({s["town"] for s in sessions}, key=normalize)
    description = ("Active folk sessions with a heavy focus on Welsh music, in " + ", ".join(towns)
                   + ": their days and times, on a map. Sesiynau cyfredol sy'n canolbwyntio'n drwm ar gerddoriaeth Gymreig.")
    body = "".join(
        f"<h2>{esc(town)}</h2><ul>" + "".join(
            f"<li><a href=\"{SESSIONS_DIR}/{s['id']}/\"><strong>{esc(s.get('name') or s['venue'])}</strong></a>{' (tune club)' if s.get('kind') == 'tune club' else ''}: {esc(describe_session(s))}. "
            f"{esc(s['venue'])}, {esc(s['address'])}. Last confirmed {esc(s['confirmed'])}.</li>"
            for s in sessions if s["town"] == town) + "</ul>"
        for town in towns)
    from datetime import date
    ld = json.dumps({"@context": "https://schema.org", "@graph": session_events(sessions, date.today())},
                    ensure_ascii=False).replace("</", "<\\/")
    write_page(OUT / SESSIONS_DIR, app_page(
        template, title="Active sessions", description=description, url=f"{SITE_URL}{SESSIONS_DIR}/",
        head=f'\n  <script type="application/ld+json">{ld}</script>', up="../", main=f"<h1>Active sessions</h1><p>{esc(description)}</p>{body}",
        loading="Loading the sessions…"))

    for s in sessions:
        title = session_title(s)
        kind = "Tune club" if s.get("kind") == "tune club" else "Folk session"
        cy_kind = "Clwb alawon" if s.get("kind") == "tune club" else "Sesiwn werin"
        description = (f"{kind} with Welsh tunes: {describe_session(s)}. {s['venue']}, {s['address']}. "
                       f"{cy_kind} gydag alawon Cymreig yn {s['town_cy']}.")
        ld = json.dumps({"@context": "https://schema.org", "@graph": session_events([s], date.today())},
                        ensure_ascii=False).replace("</", "<\\/")
        url = f"{SITE_URL}{SESSIONS_DIR}/{s['id']}/"
        write_page(OUT / SESSIONS_DIR / s["id"], app_page(
            template, title=title, description=description, url=url,
            head=f'\n  <script type="application/ld+json">{ld}</script>',
            main=f"<h1>{esc(title)}</h1><p>{esc(description)}</p>"
                 + (f"<p>{esc(s['music'])}</p>" if s.get("music") else "")
                 + (f'<p><a href="{esc(s["link"])}">{esc(s["link"])}</a></p>' if s.get("link") else "")
                 + f"<p>Last confirmed {esc(s['confirmed'])}.</p>"
                 + f'<p><a href="{SESSIONS_DIR}/">All sessions, on a map</a></p>',
            loading="Loading the session…"))


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
    # Nor are the tunes for other websites (embed/), which are only ever opened there.
    files = sorted(f for f in OUT.rglob("*") if f.is_file() and f.name not in NOT_OFFLINE
                   and not any(f.is_relative_to(OUT / d) for d in (TUNE_DIR, TYPE_DIR, SESSIONS_DIR, EMBED_DIR)))
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
