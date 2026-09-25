# Y Sesiwn

A free, open-source web app to help you learn and share Welsh folk tunes:
**https://ysesiwn.cymru/**. Search for a tune by name or by its first few
notes, or browse by type; see its sheet music, change its key and play it back.
Anyone can add tunes or suggest corrections by pull request (see
[CONTRIBUTING.md](CONTRIBUTING.md)).

Everything shown (sheet music, playback, key changes and tune details) is
generated from each tune's **ABC notation alone** (`tunes/<folder>/tune.abc`).
No MIDI files or score images are used by the site.

It's a **static site**: plain HTML, CSS and JavaScript with no server, so it
never sleeps and loads almost instantly. Everything it needs (the tunes, abcjs
and the piano sounds) is in this repo; it contacts no other website. After
the first visit it also **works offline**, and can be added to a phone's home
screen as an app.

## Running it locally

Needs Python 3.10 or newer, and nothing else (the build uses the standard
library only).

```bash
python build_site.py                    # builds _site/
python -m http.server -d _site 8000     # then open http://localhost:8000
```

Opening `_site/index.html` directly won't work: browsers block `file://`
fetches of `tunes.json`. Rebuild after editing a tune or anything in `site/`.

## Deploying

`.github/workflows/pages.yml` runs `build_site.py` and publishes `_site/` to
GitHub Pages on every push to `main` (repo **Settings → Pages → Source: GitHub
Actions**), served at the custom domain `ysesiwn.cymru`. Everything uses
relative URLs, so the site also works under a sub-path such as
`marcogorelli.github.io/y-sesiwn/`.

## Features

- **Home page:** a welcome, a big name search box, **Surprise me** (a random
  tune; also in the sidebar), **Search by notes** and **Browse by type**:
  buttons for each tune type (Jig, Polca, Walts, Rîl, Pibddawns, …, from `R:`,
  Welsh or English, via `tune_type()` in `build_site.py`), each with a
  *carthen* colourway, and a list of every tune (or that type's).
- **Search by name** (sidebar and home page): suggestions as you type; Enter
  opens the top one; `/` jumps to search from anywhere. Matching ignores case
  and accents (`fran` finds *Frân*), tolerates typos (`llancesau trefalwdyn`
  finds *Llancesau Trefaldwyn*, `risiart annwyl` finds *Rhisiart Annwyl*),
  ignores *y*, *yr* and *'r* (`helfa'r sgwarnog` finds *Hel y Sgwarnog*), and
  searches alternative titles (extra `T:` lines, e.g. *Knights of Snowdon*).
  Partial names match at the start of a word (`mon` finds *Mwynen Môn*, not
  *harmoni*), and an exact name comes first.
- **Search by notes:** type the first few notes (4 or more), or play them on
  the piano keyboard (G3, the fiddle's open G, to A5; each key sounds its
  note), in any key. Each tune's melody is worked out at build time by
  `melody()` in `build_site.py` (a small ABC reader, checked note for note
  against abcjs's playback for every tune) and stored in `tunes.json` as
  `melody`: one character per note, `chr(MIDI pitch + 160)`, repeated notes
  collapsed. The page compares the *steps* between notes, so the key doesn't
  matter. Played notes (and typed ones with an octave, like `G3`) use exact
  steps, leaps included; note names without an octave use the smaller way
  round. Matches at the start (allowing a pick-up) rank first, then later in
  the tune, then "one note different" (a wrong first/last note, or one wrong
  note in between).
- **One page per tune, with its versions:** titles ending ` (version N)` are
  grouped with their tune (`build_site.py` adds `group`, `base`, `version` and
  a `source` label, e.g. *Alawon Cymru* or the `B:` book); the page has a tab
  per version (`?tune=rheged&v=2`), and browsing, counts and search show one
  entry per tune. Old links to a version's folder (`?tune=rheged-version-2`)
  open the right tab.
- **Sheet music** on cream "paper", with a **key** drop-down (the same mode on
  any root, up to half an octave either way, e.g. *E Dorian*), a **tempo**
  slider (defaults: jigs 112, reels 90, polcas 100, others 100 bpm, in the
  felt beat: dotted crotchets in 6/8, minims in 4/4), and **playback** with
  the notes highlighted as they play.
- **Practice mode:** just the controls and a full-width score, full screen
  where supported.
- **Print:** a button on the tune page; the print styles leave just the
  sheet music, in the key chosen on the page.
- **Map:** tunes named after a place have a small map of Wales on their page,
  and *Tunes on the map* (`?page=map`) shows every place with its tunes. The
  places and their tunes are listed by hand in `places.json` (name, latitude,
  longitude, tune folders); `build_site.py` works out each dot's position on
  `site/wales.svg` and stops with an error if a folder doesn't exist.
- **Offline and home-screen app:** `site/sw.js` (a service worker) saves a
  copy of the whole site (about 3 MB, piano notes included) after the first
  visit, and `site/manifest.webmanifest` lets phones install it. The build
  fills in `sw.js`'s file lists and a version made from the files' contents,
  so each deploy is picked up in the background and used from the next visit.
  The piano notes are cached separately, so a deploy doesn't download them
  again.
- **Details:** tune type, key (written out), time signature,
  composer/arranger with an English gloss for Welsh credit words
  (*Trefniant* = arranged by), and any other standard ABC fields (book, notes,
  area…). The raw ABC, including its source, is in an expander.
- **Pages:** *How to add a tune* and *How to submit corrections* (the two
  `# ` sections of `CONTRIBUTING.md`), and *About* (`site/about.md`).
- **Look:** a *carthen* (Welsh tapestry blanket) band across the top and
  bottom (`site/carthen.svg`) and under section headings, Welsh slate, and
  Welsh red for accents. Works in dark mode and on phones (search pinned to
  the top).
- **Every tune has its own link** (`?tune=sawdl-y-fuwch`), and the back button
  works.

## Files

| Path | What it is |
|---|---|
| `build_site.py` | Builds `_site/` (git-ignored): copies `site/`, `static/`, `CONTRIBUTING.md`, and writes `tunes.json`: every `tune.abc` plus what the page needs about it (type, key, default tempo and beat, Details rows, credit glosses, melody for the note search, version grouping), worked out once in Python. Tune types, colourways and default tempos are set at the top. |
| `site/index.html`, `site/style.css`, `site/app.js` | The page. `app.js` does searching (a port of the original Python matching, including `difflib`'s similarity ratio), browsing, routing (`?tune=…&v=…`, `?page=add\|fix\|about`), sheet music and playback with abcjs, and renders the Markdown pages with marked. |
| `site/about.md`, `site/carthen.svg` | The About page; the tapestry band. |
| `places.json`, `site/wales.svg` | The places named in tune titles, for the map; the outline of Wales (made once from the ONS local authority boundaries via [UK-GeoJSON](https://github.com/martinjc/UK-GeoJSON), merged and simplified; its projection is in a comment in the file and in `MAP` in `build_site.py`). The outline is used as a CSS mask, so it takes the page's colours. |
| `site/sw.js`, `site/manifest.webmanifest`, `site/icon-*.png` | Offline use and the home-screen app (see Features). The icons are made from `design/app-icon.html`. |
| `site/og-image.png`, `site/apple-touch-icon.png` | The link-preview card (1200×630, used by the `og:`/`twitter:` tags in `index.html`) and the home-screen icon. Made from `design/og-card.html` and `design/apple-touch-icon.html`: open one in a browser at that size and screenshot it to regenerate. |
| `CONTRIBUTING.md` | How to add a tune, and how to submit corrections. Each `# ` section is one page on the site, and GitHub shows the whole file, so edit it in one place. Keep the two `# ` headings as they are: the site finds the sections by them. |
| `static/abcjs/` | [abcjs](https://www.abcjs.net/) 6.4.4 (`abcjs-basic-min.js`, `abcjs-audio.css`): draws and plays the music. |
| `static/soundfont/acoustic_grand_piano-mp3/` | The 88 piano notes (A0–C8) from the FluidR3_GM soundfont, one MP3 each; a tune loads only the notes it uses. |
| `static/marked/`, `static/harp.svg` | [marked](https://marked.js.org/) 15 (Markdown pages); the icon. |
| `download_assets.py` | Re-downloads everything in `static/` (skips files that exist). Only needed if `static/` is lost or you want to change version. |
| `tunes/<folder>/tune.abc` | One tune (or version) per folder; the site reads only these. |
| `.github/workflows/pages.yml` | Builds and publishes the site. |
| `.claude/skills/alawon-abc/` | The Claude Code skill that downloaded the first tunes and made their ABC files (see below). |

Not in git (see `.gitignore`): `_site/`, each tune's `score.gif`, `tune.mid`
and `info.json`, and `.venv/`.

### Gotchas (things that went wrong while building it)

- `ABCJS.strTranspose` needs the **whole array** returned by
  `renderAbc("*", abc)`, not its first element. Given one tune, it silently
  changes nothing.
- The abcjs stylesheet is at the package root (`abcjs@6.4.4/abcjs-audio.css`),
  not in `dist/`. Without it the player shows "CSS required: load
  abcjs-audio.css".
- abcjs boosts the volume (×3) only for its default online soundfont. With a
  local `soundFontUrl` the boost must be set explicitly
  (`soundFontVolumeMultiplier: 3.0` in `AUDIO_PARAMS`), or playback is quiet;
  `ABCJS.synth.playEvent` ignores it, so the keyboard builds its own
  `SynthSequence` instead.
- Keep URLs relative (`static/...`, no leading slash), so the site works
  under any path.
- Browsers keep audio paused until the user clicks, so notes are loaded as a
  tune opens (a second `CreateSynth().init()` fills abcjs's shared note cache)
  but only played once play is pressed.
- A service worker serves the cached copy first, so while testing locally
  a change shows up only on the second reload (or use the browser's
  "Update on reload" / "Bypass for network" developer setting).
- abcjs prints some header fields on the score; `S:`, `Z:`, `B:`, `N:` and
  `A:` are left off it (they're in the Details box), and so is a title's
  ` (version N)`, since the tabs say which version it is.

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
  *pibddawns*, …), `M:`, `L:`, `Q:`, `K:`, `S:` (source page) and `Z:`. The site
  shows other standard fields (`N:`, `O:`, …) automatically if you add them.
- `%%alawon ...` lines record the conversion options for `abctool.py check`.
  Keep them; abcjs ignores them.
- To fix a tune, edit its `tune.abc` and rebuild (`python build_site.py`);
  once pushed to `main`, the live site updates by itself.
