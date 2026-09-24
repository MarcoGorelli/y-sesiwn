"""Build the static Y Sesiwn site into _site/ (no dependencies beyond Python).

    python build_site.py                        # build
    python -m http.server -d _site 8000         # preview at http://localhost:8000

_site/ gets the page (site/), the vendored libraries and sounds (static/),
CONTRIBUTING.md, and tunes.json: every tune.abc plus everything the page needs
about it (type, key, default tempo, details), worked out here once instead of
in the browser. The GitHub Pages workflow runs this on every push to main.
"""

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
    "jig": "Jig", "polca": "Polca", "polka": "Polca", "walts": "Walts",
    "ril": "Rîl", "reel": "Rîl", "pibdd": "Pibddawns", "ymdaith": "Ymdaith",
    "ymdeithdon": "Ymdaith", "dawns": "Dawns", "carol": "Carol",
}
GENERIC_TYPES = {"alaw": "Alaw", "can": "Cân"}
TYPE_ORDER = {  # label -> English, in display order
    "Jig": "jigs", "Polca": "polkas", "Walts": "waltzes", "Rîl": "reels",
    "Pibddawns": "hornpipes", "Ymdaith": "marches", "Dawns": "dances",
    "Alaw": "airs", "Cân": "songs", "Carol": "carols", "Other": "untyped and other tunes",
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


def tune_record(path: Path) -> dict:
    abc = path.read_text(encoding="utf-8")
    headers = parse_headers(abc)
    titles = headers.get("T") or [path.parent.name]
    parsed = parse_key((headers.get("K") or [""])[0])
    beat = beat_unit((headers.get("M") or [""])[0])
    rows, gloss = details(headers)
    return {
        "slug": path.parent.name,
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
        "gloss": gloss,
        "abc": abc,
    }


def main() -> None:
    tunes = [tune_record(p) for p in sorted((ROOT / "tunes").glob("*/tune.abc"))]
    counts = {t: sum(tune["type"] == t for tune in tunes) for t in TYPE_ORDER}
    index = {
        "repo": REPO_URL,
        "types": [{"name": t, "english": e, "count": counts[t]} for t, e in TYPE_ORDER.items() if counts[t]],
        "tunes": tunes,
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
    print(f"built {OUT.relative_to(ROOT)}/ with {len(tunes)} tunes")


if __name__ == "__main__":
    main()
