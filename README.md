# Y Sesiwn

A small Streamlit app for browsing Welsh traditional tunes from
[alawoncymru.com](http://alawoncymru.com/alawon/Tunes/Tunesal.html).
Search for a tune by name, see its sheet music, change its key and play it back.

Everything shown — sheet music, playback, key changes and tune details — is
generated from each tune's **ABC notation alone** (`tunes/<slug>/tune.abc`).
The site's MIDI files and score images are not used by the app.

The app runs fully **offline**: the music library and the piano sounds are
stored in `static/`.

## Running it

Needs Python 3.10 or newer.

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt      # needs internet, once
.venv/bin/streamlit run app.py
```

Then open http://localhost:8501. Run the `streamlit` command from this folder:
`.streamlit/config.toml` and `static/` are found relative to it, and the
config is only read at startup.

## Features

- **Search** (sidebar): suggestions appear as you type; Enter opens the top
  match. Matching ignores case and accents (`fran` finds *Frân*), tolerates
  typos (`llancesau trefalwdyn` finds *Llancesau Trefaldwyn*) and also
  searches alternative titles (extra `T:` lines). Clicking the empty box lists
  every tune. Tunes sharing a title show their folder name.
- **Sheet music** for one tune at a time, shown in full.
- **Key** drop-down: transposes the notation and the playback, keeping the
  mode (e.g. Dm → Em), up to half an octave either way.
- **Playback** with play / loop / restart / tempo controls; notes are
  highlighted as they play.
- **Details** box (tune type, meter, tempo, key, … from the ABC header), a
  separate **Source** box with the link to the original page, and the raw
  ABC in an expander.
- **Back to home** button in the sidebar.

## Files

| Path | What it is |
|---|---|
| `app.py` | The whole app. |
| `requirements.txt` | Python packages: `streamlit`, `streamlit-searchbox`. |
| `.streamlit/config.toml` | Turns on serving of `static/` at `/app/static/`; turns off Streamlit's usage statistics (which would go online). |
| `static/abcjs/` | [abcjs](https://www.abcjs.net/) 6.4.4 (`abcjs-basic-min.js`, `abcjs-audio.css`). |
| `static/soundfont/acoustic_grand_piano-mp3/` | The 88 piano notes (A0–C8) from the FluidR3_GM soundfont, one MP3 each. |
| `download_assets.py` | Re-downloads everything in `static/` (skips files that exist). Only needed if `static/` is lost or you want to change version. |
| `tunes/<slug>/tune.abc` | One tune per folder; the app reads only these. |
| `.claude/skills/alawon-abc/` | The Claude Code skill that downloaded the tunes and made the ABC files (see below). |

Not in git (see `.gitignore`): each tune's `score.gif`, `tune.mid` and
`info.json`, and `.venv/`.

## How the app works

- **Loading tunes:** every `tunes/*/tune.abc` is read once (cached with
  `st.cache_data`). Header lines up to `K:` are parsed into fields; the first
  `T:` is the title and further `T:` lines are alternative titles.
- **Search:** `streamlit-searchbox` calls `suggestions()` on every keystroke.
  A title containing the query scores 1.0; otherwise each query word is
  compared with the title's words using `difflib`, and results scoring below
  0.7 are dropped. The search box lives in an `st.fragment`, so typing reruns
  only the sidebar; choosing a tune stores its folder name in
  `st.session_state["selected"]` and reruns the whole page.
- **Rendering and playback:** `render_tune()` puts an HTML page with abcjs
  into `st.iframe(..., height="content")`. Streamlit re-measures that frame
  whenever its content changes, so the whole score shows with no scrollbar.
  abcjs draws the score (`renderAbc`) and `SynthController` plays it.
- **Key changes:** done in the browser with
  `ABCJS.strTranspose(abc, parsedTunes, semitones)`, which rewrites the ABC
  text (notes and `K:`) before drawing, so the audio follows too.
- **Faster playback start:** when a tune opens, a second `CreateSynth().init()`
  fetches and decodes its notes in the background (into abcjs's shared note
  cache), so pressing play doesn't wait for them.
- **Hidden fields:** abcjs prints `S:` (source) and `Z:` (transcription)
  under the score. The app removes them before drawing, since Source has its
  own box and `Z:` only says the file was made with alawon-abc.

### Gotchas (things that went wrong while building it)

- `ABCJS.strTranspose` needs the **whole array** returned by
  `renderAbc("*", abc)`, not its first element. Given one tune, it silently
  changes nothing.
- The abcjs stylesheet is at the package root (`abcjs@6.4.4/abcjs-audio.css`),
  not in `dist/`. Without it the player shows "CSS required: load
  abcjs-audio.css".
- abcjs boosts the volume (×3) only for its default online soundfont. With a
  local `soundFontUrl` the boost must be set explicitly
  (`soundFontVolumeMultiplier: 3.0` in `AUDIO_PARAMS`), or playback is quiet.
- The soundfont and abcjs URLs are absolute paths (`/app/static/...`). If the
  app is ever served under a sub-path (`server.baseUrlPath`), update
  `STATIC_URL` in `app.py`.
- "Back to home" must also delete the search box's state
  (`st.session_state["tune_search"]`); otherwise choosing the same tune again
  afterwards does nothing, because the search box only reports a *changed*
  choice.
- `st.components.v1.html` is deprecated in this Streamlit version; use
  `st.iframe`.
- Browsers keep audio paused until the user clicks, so notes can be loaded
  early but not played. abcjs resumes the audio when play is pressed.

## Where the tunes come from

The `tunes/` folder was built with the **alawon-abc** skill in
`.claude/skills/alawon-abc/` (read its `SKILL.md` for full instructions). In
short:

1. `scrape.py --out tunes` downloads each tune's MIDI (`tune.mid`), score
   image (`score.gif`) and metadata (`info.json`) from alawoncymru.com.
2. `abctool.py batch tunes` converts every MIDI to `tune.abc`, laying out
   bars, repeats and line breaks to match the score image.
3. Each tune can then be reviewed against its score and fixed;
   `abctool.py check` compares the ABC with the MIDI note for note.
   Reviewed tunes are marked with a `%%alawon-reviewed` line.

Run the scripts with:

```bash
uv run --no-project --with mido python .claude/skills/alawon-abc/scripts/<script>.py ...
```

Useful to know:

- 551 tunes were found; 26 have no ABC (their MIDI link on the site is dead),
  so the app shows 525.
- The ABC files have no composer or arranger (`C:`) fields, only `T:`, `R:`
  (type, mostly in Welsh: *jig*, *polca*, *walts*, *rîl*, *pibddawns*, …),
  `M:`, `L:`, `Q:`, `K:`, `S:` (source page) and `Z:`. The app shows any
  other standard field (`C:`, `N:`, `O:`, …) automatically if you add one.
- `%%alawon ...` lines record the conversion options for `abctool.py check`.
  Keep them; abcjs ignores them.
- To fix a tune, edit its `tune.abc`, then restart the app or use the app
  menu (⋮) → *Clear cache*: the tune list is cached, so edits don't show on
  their own.
