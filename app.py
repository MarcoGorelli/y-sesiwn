"""Tune browser: search tunes by name, render sheet music and play MIDI from ABC.

Run with:  .venv/bin/streamlit run app.py
"""

import difflib
import json
import re
import unicodedata
from fractions import Fraction
from pathlib import Path

import streamlit as st
from streamlit_searchbox import st_searchbox

TUNES_DIR = Path(__file__).parent / "tunes"
STATIC_DIR = Path(__file__).parent / "static"
# Local copies served by Streamlit from ./static (see download_assets.py),
# so the app needs no internet access.
# Relative, not "/app/static": the score iframe resolves it against the app's
# own URL, which on Streamlit Community Cloud is under a sub-path (/~/+/).
STATIC_URL = "app/static"
AUDIO_PARAMS = {
    "program": 0,
    "soundFontUrl": f"{STATIC_URL}/soundfont/",
    # abcjs only applies this boost automatically for its default online soundfont.
    "soundFontVolumeMultiplier": 3.0,
}

# ABC header fields worth showing to the user, in display order.
HEADER_LABELS = {
    "T": "Title",
    "R": "Tune type",
    "C": "Composer",
    "A": "Area",
    "O": "Origin",
    "B": "Book",
    "D": "Discography",
    "H": "History",
    "N": "Notes",
    "M": "Meter",
    "L": "Unit note length",
    "K": "Key",
}

NOTES = ["C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"]
PITCH = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}

# Default tempo (beats per minute) by tune type, matched against R:. The Q:
# tempos in the ABC files are ignored.
DEFAULT_BPM = {"jig": 112, "ril": 90, "reel": 90, "polca": 100, "polka": 100}
OTHER_BPM = 100
BEAT_NAMES = {
    Fraction(3, 8): "dotted crotchet",
    Fraction(1, 2): "minim",
    Fraction(1, 4): "crotchet",
    Fraction(1, 8): "quaver",
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


@st.cache_data
def load_tunes() -> list[dict]:
    tunes = []
    for path in sorted(TUNES_DIR.glob("*/tune.abc")):
        abc = path.read_text(encoding="utf-8")
        headers = parse_headers(abc)
        titles = headers.get("T") or [path.parent.name]
        tunes.append(
            {
                "slug": path.parent.name,
                "title": titles[0],
                "titles": titles,
                "search": [normalize(t) for t in titles],
                "headers": headers,
                "abc": abc,
            }
        )
    return tunes


def score(query: str, tune: dict) -> float:
    """1.0 for a substring match, otherwise a fuzzy similarity in [0, 1)."""
    best = 0.0
    for title in tune["search"]:
        if query in title:
            return 1.0
        # Compare word by word so small typos ("trefalwdyn") still match.
        q_words, t_words = query.split(), title.split()
        word_scores = [
            max(difflib.SequenceMatcher(None, q, t).ratio() for t in t_words)
            for q in q_words
        ]
        best = max(best, 0.99 * sum(word_scores) / len(word_scores))
    return best


def search(query: str, tunes: list[dict]) -> list[dict]:
    query = normalize(query)
    if not query:
        return tunes
    scored = [(score(query, t), t) for t in tunes]
    scored = [(s, t) for s, t in scored if s >= 0.7]
    scored.sort(key=lambda st_: (-st_[0], st_[1]["title"]))
    return [t for _, t in scored]


def parse_key(key: str) -> tuple[int, str, str] | None:
    """'F#m' -> (6, 'F#', 'm'); returns None for keys we can't parse."""
    m = re.match(r"^([A-Ga-g])([#b]?)\s*([A-Za-z]*)", key.strip())
    if not m:
        return None
    root = m.group(1).upper() + m.group(2)
    pitch = PITCH[root[0]] + {"#": 1, "b": -1, "": 0}[m.group(2)]
    return pitch % 12, root, m.group(3)


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


def set_tempo(abc: str, beat: Fraction, bpm: int) -> str:
    """Replace the Q: line (or add one before K:) with Q:<beat>=<bpm>."""
    tempo = f"Q:{beat}={bpm}"
    if re.search(r"^Q:", abc, flags=re.M):
        return re.sub(r"^Q:.*$", tempo, abc, count=1, flags=re.M)
    return re.sub(r"^K:", tempo + "\nK:", abc, count=1, flags=re.M)


def strip_fields(abc: str, fields: str) -> str:
    """Remove header lines for the given fields, e.g. fields="SZ"."""
    return "\n".join(
        line for line in abc.splitlines() if not re.match(rf"^[{fields}]:", line)
    )


def render_tune(abc: str, transpose: int) -> None:
    """Render ABC as sheet music with abcjs, plus a MIDI synth player."""
    # Without static serving, /app/static/... returns Streamlit's index page
    # instead of abcjs and the score silently fails to draw.
    if not st.get_option("server.enableStaticServing"):
        st.error(
            "Sheet music needs `server.enableStaticServing = true` (see "
            "`.streamlit/config.toml`). Restart the app from this folder so the "
            "config is read."
        )
        return
    if not (STATIC_DIR / "abcjs" / "abcjs-basic-min.js").exists():
        st.error("`static/` is missing abcjs. Run `.venv/bin/python download_assets.py`.")
        return
    html = f"""
<link rel="stylesheet" href="{STATIC_URL}/abcjs/abcjs-audio.css">
<script src="{STATIC_URL}/abcjs/abcjs-basic-min.js"></script>
<style>
  body {{ margin: 0; font-family: sans-serif; background: white; overflow: hidden; }}
  #audio {{ margin: 8px 0 12px; }}
  .abcjs-note_playing {{ fill: #d33; }}
</style>
<div id="audio"></div>
<div id="paper"></div>
<script>
  const original = {json.dumps(abc)};
  const steps = {transpose};
  const audioParams = {json.dumps(AUDIO_PARAMS)};
  let abc = original;
  if (steps !== 0) {{
    // strTranspose expects the full array of parsed tunes, not a single tune.
    const parsed = ABCJS.renderAbc("*", original);
    abc = ABCJS.strTranspose(original, parsed, steps);
  }}
  const visualObj = ABCJS.renderAbc("paper", abc, {{
    responsive: "resize",
    add_classes: true,
    paddingtop: 0,
  }})[0];

  class Cursor {{
    onEvent(ev) {{
      document.querySelectorAll(".abcjs-note_playing")
        .forEach(el => el.classList.remove("abcjs-note_playing"));
      if (!ev) return;
      ev.elements.flat().forEach(el => el.classList.add("abcjs-note_playing"));
    }}
    onFinished() {{ this.onEvent(null); }}
  }}

  if (ABCJS.synth.supportsAudio()) {{
    const controller = new ABCJS.synth.SynthController();
    controller.load("#audio", new Cursor(), {{
      displayLoop: true, displayRestart: true, displayPlay: true,
      displayProgress: true,
    }});
    controller.setTune(visualObj, false, audioParams);
    // Fetch and decode this tune's notes now, so pressing play doesn't wait
    // for the soundfont download. The audio context stays suspended until the
    // play button is clicked; abcjs shares the decoded notes via its cache.
    new ABCJS.synth.CreateSynth()
      .init({{ visualObj, options: audioParams }})
      .catch(err => console.warn("Soundfont preload failed", err));
  }} else {{
    document.getElementById("audio").textContent = "Audio is not supported in this browser.";
  }}
</script>
"""
    # height="content" makes Streamlit resize the frame to fit the rendered
    # score, so the whole tune is shown without an inner scrollbar.
    st.iframe(html, height="content")


def suggestions(query: str, tunes: list[dict], limit: int = 20) -> list[tuple[str, str]]:
    """(label, slug) pairs for the searchbox; duplicate titles show their folder."""
    results = search(query, tunes)
    if query.strip():
        results = results[:limit]
    titles = [t["title"] for t in results]
    return [
        (f"{t['title']} ({t['slug']})" if titles.count(t["title"]) > 1 else t["title"], t["slug"])
        for t in results
    ]


@st.fragment
def tune_search(tunes: list[dict]) -> None:
    """Sidebar search with live suggestions; reruns only this fragment while typing."""
    st.header("Find a tune")

    def open_tune(slug: str) -> None:
        # The selection lives in session state, so searching again doesn't
        # change the tune being displayed until you pick another one.
        st.session_state["selected"] = slug
        st.rerun()

    st_searchbox(
        lambda q: suggestions(q, tunes),
        placeholder="e.g. Llancesau Trefaldwyn",
        label="Search by name",
        help="Suggestions update as you type; press Enter to open the top one.",
        default_options=suggestions("", tunes),
        submit_function=open_tune,
        rerun_scope="fragment",
        key="tune_search",
    )
    st.caption(f"{len(tunes)} tunes")


def go_home() -> None:
    """Clear the selected tune, and reset the searchbox so it starts empty."""
    st.session_state.pop("selected", None)
    st.session_state.pop("tune_search", None)


def main() -> None:
    st.set_page_config(page_title="Y Sesiwn", page_icon=STATIC_DIR / "harp.svg", layout="wide")
    tunes = load_tunes()
    by_slug = {t["slug"]: t for t in tunes}

    with st.sidebar:
        st.title("Y Sesiwn")
        st.button(
            "Back to home",
            icon=":material/home:",
            on_click=go_home,
            disabled="selected" not in st.session_state,
            width="stretch",
        )
        tune_search(tunes)

    st.title("Y Sesiwn")

    slug = st.session_state.get("selected")
    if slug not in by_slug:  # e.g. a tune deleted since it was opened
        st.session_state.pop("selected", None)
        slug = None
    if not slug:
        st.write("Search for a tune in the sidebar and select it to see its sheet music.")
        return

    tune = by_slug[slug]
    headers = tune["headers"]
    st.header(tune["title"])
    if len(tune["titles"]) > 1:
        st.caption("Also known as: " + ", ".join(tune["titles"][1:]))

    # Key selector: the same mode, on any of the 12 roots.
    transpose = 0
    original_key = (headers.get("K") or [""])[0]
    parsed = parse_key(original_key)
    options: list[int] = []
    labels: dict[int, str] = {}
    if parsed:
        pitch, root, mode = parsed
        options = list(range(-5, 7))  # semitone shifts, nearest direction
        labels = {s: NOTES[(pitch + s) % 12] + mode for s in options}
        labels[0] = f"{root}{mode} (original)"
    col_key, col_tempo = st.columns([1, 3])
    if parsed:
        transpose = col_key.selectbox(
            "Key",
            options,
            index=options.index(0),
            format_func=labels.get,
            key=f"key-{slug}",
        )

    # Tempo slider; the default depends on the tune type (see DEFAULT_BPM).
    beat = beat_unit((headers.get("M") or [""])[0])
    bpm = col_tempo.slider(
        f"Tempo (bpm, {BEAT_NAMES.get(beat, str(beat))} beats)",
        min_value=30,
        max_value=200,
        value=default_bpm(headers),
        key=f"bpm-{slug}",
    )

    col_music, col_info = st.columns([3, 1])
    with col_music:
        # abcjs prints S: and Z: under the score; Source has its own box instead.
        render_tune(set_tempo(strip_fields(tune["abc"], "SZ"), beat, bpm), transpose)
    with col_info:
        with st.container(border=True):
            st.subheader("Details")
            for field, label in HEADER_LABELS.items():
                values = headers.get(field)
                if field == "T" or not values:
                    continue
                st.markdown(f"**{label}:** {', '.join(values)}")
        sources = headers.get("S")
        if sources:
            with st.container(border=True):
                st.subheader("Source")
                for source in sources:
                    st.markdown(f"[{source}]({source})" if source.startswith("http") else source)
        with st.expander("ABC notation"):
            st.code(strip_fields(tune["abc"], "Z"), language=None)


main()
