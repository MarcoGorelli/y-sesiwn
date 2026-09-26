# Y Sesiwn

A free, open-source web app to help you learn and share Welsh folk tunes:
**https://ysesiwn.cymru/**. Search for a tune by name or by its first few
notes, or browse by type and key; see its sheet music, change its key and play it back.
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

## Tests

```bash
pip install -r requirements-dev.txt        # pytest and Playwright
python -m playwright install chromium      # the headless browser (once)
python -m pytest                           # everything, about 30 seconds
python -m pytest -m "not browser"          # just the quick file and build checks
```

(With uv instead of pip: `uv run --no-project --with-requirements
requirements-dev.txt python -m pytest`.)

- `tests/test_build.py` checks every `tune.abc` (headers, folder name,
  key, melody, no blank line in the music, text above the stave written as
  `"^text"`) and `build_site.py` (versions, lead-ins, chords, places, and
  that `sw.js` lists only files that exist).
- `tests/test_site.py` builds the site, serves it and opens it in headless
  Chromium: every tune and version draws notes with each playback setting;
  tune pages, key changes, the chord chart (spacing, repeats, switches),
  search by name and by notes (lead-ins, close matches, never empty), the
  map and its popups, the home page, phone widths (no sideways scrolling),
  working offline, the microphone (a generated fiddle recording played to
  Chromium's fake microphone), the practice row (parts, looping and
  speeding up during real playback, count-in and click, tablature), the
  report link, browsing by key, the install card on five device/browser
  mixes, printing, and an **accessibility** check with axe (labels,
  contrast, keyboard access, ARIA…) on seven pages, light and dark, desktop
  and phone widths. Any JavaScript error fails the test.

They run on every push and pull request (`.github/workflows/pages.yml`), and
the site is only deployed if they pass. To run them before every push too,
turn on the hook once per clone: `git config core.hooksPath .githooks`
(`git push --no-verify` skips it).

## Deploying

`.github/workflows/pages.yml` runs the tests, then `build_site.py`, and
publishes `_site/` to GitHub Pages on every push to `main` (repo **Settings → Pages → Source: GitHub
Actions**), served at the custom domain `ysesiwn.cymru`. Everything uses
relative URLs, so the site also works under a sub-path such as
`marcogorelli.github.io/y-sesiwn/`.

## Features

- **Home page:** a welcome, a big name search box, **Surprise me** (a random
  tune; also in the sidebar), **What you can do** (every feature in one list,
  `features()` in `app.js`; keep it up to date when adding one), **Search by notes** and **Browse by type and key**:
  buttons for each tune type (Jig, Polca, Walts, Rîl, Pibddawns, …, from `R:`,
  Welsh or English, via `tune_type()` in `build_site.py`), each with a
  *carthen* colourway, a second row of keys (the key each tune's first version
  is in, most common first), and a list of every tune, or those of the chosen
  type and/or key ("31 jigs in D major"). Key counts follow the chosen type,
  and keys with none of that type are greyed out.
- **Search by name** (sidebar and home page): suggestions as you type; Enter
  opens the top one; `/` jumps to search from anywhere. Matching ignores case
  and accents (`fran` finds *Frân*), tolerates typos (`llancesau trefalwdyn`
  finds *Llancesau Trefaldwyn*, `risiart annwyl` finds *Rhisiart Annwyl*),
  ignores *y*, *yr* and *'r* (`helfa'r sgwarnog` finds *Hel y Sgwarnog*), and
  searches alternative titles (extra `T:` lines, e.g. *Knights of Snowdon*).
  Partial names match at the start of a word (`mon` finds *Mwynen Môn*, not
  *harmoni*), and an exact name comes first.
- **Search by notes:** type the first few notes (4 or more), play them on
  the piano keyboard (G3, the fiddle's open G, to A5; each key sounds its
  note), or press **Play it to me** and play them on an instrument to the
  microphone, in any key. Listening (`startListening()` in `app.js`) measures
  the pitch on every screen frame with the YIN method over the last ~45 ms,
  rounds it to the nearest semitone, and counts a pitch held for 45 ms as a
  note, lighting its key; it stops after 2.5 s of quiet. Notes go in without
  their octave, so an octave misheard doesn't matter. It's meant for an
  in-tune fiddle, whistle, flute or guitar (single notes), not humming; it
  was tested with synthesised fiddle, whistle and guitar recordings of real
  tunes, slow and at reel speed (~8 notes a second), fed to Chromium as a
  fake microphone. Nothing is recorded or sent anywhere. On iPhones the
  audio session switches to `play-and-record` while listening. Each tune's melody is worked out at build time by
  `melody()` in `build_site.py` (a small ABC reader, checked note for note
  against abcjs's playback for every tune) and stored in `tunes.json` as
  `melody`: one character per note, `chr(MIDI pitch + 160)`, repeated notes
  collapsed. The page compares the *steps* between notes, so the key doesn't
  matter. Played notes (and typed ones with an octave, like `G3`) use exact
  steps, leaps included; note names without an octave use the smaller way
  round. Lead-ins (pick-ups) are handled both ways round: the build works
  out each tune's lead-in (`lead_in()`: the notes before the first bar line
  if they don't fill a bar) and stores where its melody starts after it as
  `lead`, so a query matches the start of a tune with or without its
  lead-in; and the query's own first 1–3 notes are also tried as a lead-in
  the tune doesn't have, if 5 or more notes are left. Matches at the start
  rank first, then later in the tune. Tunes without the notes are ranked by
  how many notes are different (wrong, missing or extra; `editDistance()`,
  worked on the steps, so key-independent, with a wrong note counted once
  even though it changes two steps), near the start counting one fewer:
  those within a quarter of the query's notes are listed as *close*, and the
  nearest are added until there are at least 5 suggestions, so a search
  never comes back empty.
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
- **Practice row** (under the key and tempo): **Loop** one part of the tune
  (parts start at a repeat sign or double bar line, as in the chord chart;
  `tuneParts()`), optionally **speeding up** 5% each time round up to the
  tune's usual tempo (`partLoop()`: whenever playback reaches a note outside
  the part it seeks back to the part's first note, and abcjs's own loop
  brings it round after the last part; the speed-up uses `setWarp`, which
  keeps playing from the same place). **Count-in** (one bar of woodblock
  clicks before the tune) and **Click** (a woodblock on every felt beat, high
  on the first of the bar) use abcjs's `drum`, `drumIntro` and `drumOff`
  options, with General MIDI percussion 76/77 from abcjs's own sound set in
  `static/soundfont/percussion-mp3/` (FluidR3's percussion samples are
  near-silent stubs). **Tablature** under the stave for mandolin/fiddle
  (GDAE) or guitar, with abcjs's
  tablature plugin.
- **Report a problem with this tune:** a link on every tune page to a new
  GitHub issue with the tune's name, page and file filled in.
- **Suggested chords:** tunes with chord symbols in their ABC (`"G"B2 G`)
  get a chord chart under the sheet music, for accompanists: one cell per
  bar, in rows of 4 (3 or 5 for a part that divides into those but not 4),
  each part (after a repeat sign or double bar line) starting a new row, a
  second-time ending on its own row under the first-time one, and repeat
  signs marked. Within a bar
  each chord gets the share of the width it lasts for (`| G  D |` in 4/4 is
  G on beat 1, D on beat 3; triplets counted at their played length), and a
  bar that doesn't start with a chord of its own begins with the one still
  sounding, faintly. It's
  built from abcjs's parsed tune (`chordChart()` in `app.js`), so it follows
  the key drop-down. A switch shows the chords on the sheet music (always
  drawn, hidden by CSS unless on), and **Play** chooses *Tune only*, *Tune
  and chords* or *Chords only* (abcjs's `chordsOff` / `voicesOff`). Jigs
  (6/8, and 9/8, 12/8) are accompanied like a guitar or bodhrán, on every
  quaver, "Down up down, Down up down" (`%%MIDI gchord bIcbIc`), instead of abcjs's
  "boom · chick" default. With *Tune and chords*, the chords and bass are played more quietly than
  abcjs's default (with *Chords only* they keep it) (`%%MIDI chordvol 32`, `bassvol 50`; `CHORD_VOLUME` and
  `BASS_VOLUME` in `app.js`), so the tune stays on top. They're not moved an
  octave down: abcjs already voices them below most melodies (about A2–D4),
  and an octave lower (A1–D3) sits on the bass and sounds muddy.
  `accompaniment()` in `app.js` adds these lines unless the tune sets its own. A `%%chords <text>` line says where they come from; the build
  passes it on as `chords` (`null` when a tune has no chords). The first
  chords were copied from the Alawon Cymru score images.
- **Print:** a button on the tune page; the print styles leave just the
  sheet music, in the key chosen on the page. For a tune with chords it's a
  menu: *Sheet music*, *Sheet music with chords* (above the stave), or
  *Chord chart* (title, key and chart only, big). `printAs()` sets
  `body[data-print]` for the print styles and puts things back on
  `afterprint`.
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
  again. A **"Take it to the session"** card on the home page (and the *Use
  it offline* page, `?page=offline`) advertises it: on Chrome/Edge it's an
  **Install the app** button (from the `beforeinstallprompt` event), on
  iPhones and iPads the Share → Add to Home Screen steps (Apple has no install
  prompt for websites), on a Mac in Safari *File → Add to Dock*, in Firefox (which can't
  install sites) a note that it works offline anyway, and otherwise the
  install icon in the address bar or the browser's menu. The *Use it
  offline* page lists every case, for phones and computers. It shows
  "✓ Saved on this device" once the service worker is active (it only
  activates after saving every file), and is hidden when the site is already
  open as an installed app.
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
| `.github/workflows/pages.yml` | Tests, builds and publishes the site. |
| `tests/`, `pytest.ini`, `requirements-dev.txt`, `.githooks/pre-push` | The tests (see Tests), and the hook that runs them before a push. |
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
