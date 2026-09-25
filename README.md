# Y Sesiwn

A free, open-source web app to help you learn and share Welsh folk
tunes. Search for a tune by name or browse by type, see its sheet music,
change its key and play it back. Anyone can add tunes or suggest corrections
by pull request (see [CONTRIBUTING.md](CONTRIBUTING.md)).

Everything shown — sheet music, playback, key changes and tune details — is
generated from each tune's **ABC notation alone** (`tunes/<slug>/tune.abc`).
No MIDI files or score images are used by the app.

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

## Static site (in progress: replacing the Streamlit app)

`site/` is the same app as plain HTML/JavaScript, with no server: it can be
hosted anywhere (GitHub Pages is set up), never sleeps, and loads in a blink.
Each tune has its own link (`?tune=sawdl-y-fuwch`) and the back button works.
Extras over the Streamlit app: a big search box on the home page, `/` to jump
to search from anywhere, **practice mode** on tune pages (just the controls
and a full-width score, full screen where supported), a search bar pinned to
the top on phones, and a *carthen* (Welsh tapestry blanket) band across the
top (`site/carthen.svg`), with Welsh slate and cream "paper" behind the music.
The band returns in the footer and as short strips under section headings;
each tune type has a blanket colourway (a woven swatch in the type buttons and
tune list; colours in `TYPE_ORDER` in `build_site.py`). The **About** page
(`?page=about`) is `site/about.md`.

**Search by notes** (home page): type the first few notes (4 or more), or play
them on the piano keyboard (G3, the fiddle's open G, to A5; each key sounds its
note), in any key. Each tune's melody is worked out at build time by `melody()`
in `build_site.py` (a small ABC reader, checked note for note against abcjs's
playback for every tune) and stored in `tunes.json` as `melody`: one character
per note, `chr(MIDI pitch + 160)`, repeated notes collapsed. The page compares
the *steps* between notes, so the key doesn't matter. Played notes (and typed
ones with an octave, like `G3`) use exact steps, leaps included; note names
without an octave use the smaller way round, so no octaves are needed. Matches
at the start (allowing a pick-up) rank first, then later in the tune, then
"one note different" (a wrong first/last note, or one wrong note in between).

```bash
python build_site.py                    # builds _site/ (standard library only)
python -m http.server -d _site 8000     # preview at http://localhost:8000
```

(Opening `_site/index.html` directly won't work: browsers block `file://`
fetches of `tunes.json`.)

- `build_site.py` reads every `tunes/*/tune.abc` and writes `_site/tunes.json`:
  the ABC plus what the page needs (type, key parts, default tempo and beat,
  Details rows, credit glosses), worked out once in Python. It also copies
  `site/`, `static/` (abcjs, soundfont, marked, harp icon) and
  `CONTRIBUTING.md` into `_site/`, which is git-ignored.
- `site/app.js` does the rest in the browser: search (a port of the Python
  matching, including `difflib`'s similarity ratio), browsing, routing
  (`?tune=…`, `?page=add|fix`), sheet music and playback with abcjs, and the
  guide pages (sections of `CONTRIBUTING.md` rendered with marked).
- `.github/workflows/pages.yml` builds and publishes on every push to `main`.
  One-time setup: repo **Settings → Pages → Source: GitHub Actions**. The site
  is then at `https://marcogorelli.github.io/y-sesiwn/`.
- Everything uses relative URLs, so it works under the `/y-sesiwn/` sub-path.

Switching over from Streamlit means: point people to the new URL, then delete
`app.py`, `requirements.txt` and `.streamlit/`, and update the "run it
locally" part of `CONTRIBUTING.md` to the two commands above.

## Features

- **Home page**: a welcome, a **Surprise me** button (random tune; also in the
  sidebar) and **Browse by type**: buttons for each tune type (Jig, Polca,
  Walts, Rîl, Pibddawns, …, from `R:` via `tune_type()` in `app.py`) with a
  clickable list of that type's tunes.
- **Search** (sidebar): suggestions appear as you type; Enter opens the top
  match. Matching ignores case and accents (`fran` finds *Frân*), tolerates
  typos (`llancesau trefalwdyn` finds *Llancesau Trefaldwyn*) and also
  searches alternative titles (extra `T:` lines). Clicking the empty box lists
  every tune. Titles are unique (repeats are numbered "(version 2)").
- **Sheet music** for one tune at a time, shown in full.
- **Key** drop-down: transposes the notation and the playback, keeping the
  mode (e.g. Dm → Em), up to half an octave either way.
- **Playback** with play / loop / restart / tempo controls; notes are
  highlighted as they play.
- **Details** box: tune type, key (written out, e.g. *D Mixolydian*), time
  signature and composer/arranger, plus any other standard ABC fields present;
  Welsh credit words get an English gloss (*Trefniant* = arranged by). The
  raw ABC, including its source link, is in an expander.
- **Back to home** button in the sidebar.
- **How to add a tune** and **How to submit corrections** pages (linked from
  the sidebar, at `/how-to-add-a-tune` and `/how-to-submit-corrections`), each
  showing one `# ...` section of `CONTRIBUTING.md`, and links to this repo in the sidebar and the
  app's ⋮ menu.

## Files

| Path | What it is |
|---|---|
| `app.py` | The whole app: the tunes page and the two guide pages (`st.navigation`, hidden; the sidebar links between them). |
| `CONTRIBUTING.md` | How to add a tune, and how to submit corrections. Each `# ...` section is one page in the app, and GitHub shows the whole file, so edit it in one place. Keep the two `# ` headings as they are: the app finds the sections by them. |
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
- The soundfont and abcjs URLs must be relative (`app/static/...`, no leading
  slash). The score iframe resolves them against the app page's URL, which on
  Streamlit Community Cloud is `https://<app>.streamlit.app/~/+/`; an absolute
  `/app/static/...` hits Cloud's login redirect instead, and the score silently
  doesn't draw.
- "Back to home" must also delete the search box's state
  (`st.session_state["tune_search"]`); otherwise choosing the same tune again
  afterwards does nothing, because the search box only reports a *changed*
  choice.
- `st.components.v1.html` is deprecated in this Streamlit version; use
  `st.iframe`.
- Browsers keep audio paused until the user clicks, so notes can be loaded
  early but not played. abcjs resumes the audio when play is pressed.

## ABC sources

New tunes are added by pull request (see [CONTRIBUTING.md](CONTRIBUTING.md)).

**The *Blodau'r Grug* collection** (volumes 1–3, 90 tunes) was added from Brian
Martin's ABC transcriptions in John Chambers' archive
(`https://trillian.mit.edu/~jc/music/abc/mirror/BrianMartin/msg/welsh_tunes_1.abc`;
found via abcnotation.com, whose search pages ask robots not to crawl them, so
the tunes came from the archive directly). Each tune was matched to ours by
melody (steps between notes, any key) and name: 69 are versions of tunes we
already had (named `<our title> (version N)`, with their own titles, e.g.
*Knights of Snowdon*, kept as extra `T:` lines) and 21 are new. Their files got
`B:` (the volume), `S:` (the archive URL), `N:Transcribed by Brian Martin` (his
email address left out), and ABC2Win's `!` line breaks turned into real ones.

**Versions share a page.** Titles ending ` (version N)` are grouped with the
tune they're a version of (`build_site.py` adds `group`, `base`, `version` and a
`source` label to each tune); the site shows one entry per tune in browsing,
counts and search, and tabs on the tune page (`?tune=rheged&v=2`). The type
used for browsing is version 1's; `R:` can be Welsh or English (*Waltz*,
*Hornpipe*, *March*, *Set Dance*…).

The first batch was imported from
[alawoncymru.com](http://alawoncymru.com/alawon/Tunes/Tunesal.html) with the
**alawon-abc** skill in
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

- 551 tunes were found; 26 have no ABC (their MIDI link on the site is dead).
  92 more were deleted as duplicates, leaving 433 (441 tunes and 523 versions
  with *Blodau'r Grug*, below; *Mwynen Cynwyd, syml* was retitled *Mwynen
  Cynwyd* to match its score). Re-running
  `scrape.py` would bring them back. A folder was deleted when its melody was
  at least 95% the same as another's (compared by the steps between notes'
  pitches, so a different key doesn't matter; the key drop-down covers that)
  and it had the same name, a spelling variant (`(Y) Pural Fesur` =
  `Y Pural Fesur`) or a file-name abbreviation (`BchgMain` = *Y Bachgen Main*).
  Deliberate variants with their own names were kept: `... syml`,
  `... fel rîl`, `Jig ...`, `Walts ...`. The last 8 were mislabelled copies
  whose score image shows another tune already in the collection (e.g.
  the `Santiana` folder's score was *Sesiwn yng Nghymru*, with identical music).
  A final pass compared same-titled tunes by their MIDI (repeats played out,
  pitch steps and rhythm), which catches copies that write repeats
  differently (`|1 ... :| [2` vs written out). Near-identical pairs were merged
  by hand, keeping the more complete copy, including two that differ only in
  time signature (*Ar Lan y Môr*, *Da yw swllt*).
- **Titles come from the score images.** Every tune's `T:` was checked
  against the title printed on its `score.gif`: the printed title is the first
  `T:`, other genuine names follow as extra `T:` lines. File-name titles
  (`BachBoDw`), typos and index-style `(Y) ...` titles were replaced.
- **Naming:** titles have no brackets (`Ffaniglen Syml`), except that tunes
  sharing a title are numbered `... (version 2)`, `(version 3)`. Each folder
  is named after its first title: lowercase, accents dropped, anything else
  turned into hyphens (`Codi'r Hwyl` → `tunes/codi-r-hwyl/`,
  `Sawdl y Fuwch (version 2)` → `sawdl-y-fuwch-version-2`). The 26 folders
  with no `tune.abc` (dead MIDI links) keep the scraper's names.
- Some tunes named on the site aren't in the collection, because the scraper
  paired their name with another tune's MIDI: *Diafol yn y Llwyn*, *Neidod y
  Pant*, *Rali Twm Siôn*, and second versions of *Dere i Jigio*, *Sawdl y
  Fuwch*, *Meillionen Meirionnydd*, *Triban Morgannwg Syml* and *Hoffedd Miss
  Blisset*. The folders that carried those names now have the title of the
  music they actually contain.
- `ffoi-o-r-wcrain/score.gif` shows a different tune (*Shche Ne Vmerla
  Ukrainy*) from its ABC; the ABC's title was kept.
- **Credits (`C:`) come from the score images** too: the credit printed at the
  bottom of each score, as written (in Welsh: *Trefniant* = arrangement,
  *Addasiad* = adaptation, *Alaw* = tune by, *o alaw …* = from a tune by …),
  with only obvious typos fixed. 416 tunes have one; 17 scores print none.
  abcjs shows `C:` at the top right of the sheet music. Other header fields
  are `T:`, `R:` (type, mostly in Welsh: *jig*, *polca*, *walts*, *rîl*,
  *pibddawns*, …), `M:`, `L:`, `Q:`, `K:`, `S:` (source page) and `Z:`. The app
  shows other standard fields (`N:`, `O:`, …) automatically if you add them.
- `%%alawon ...` lines record the conversion options for `abctool.py check`.
  Keep them; abcjs ignores them.
- To fix a tune, edit its `tune.abc`, then restart the app or use the app
  menu (⋮) → *Clear cache*: the tune list is cached, so edits don't show on
  their own.
