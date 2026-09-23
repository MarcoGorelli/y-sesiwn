---
name: alawon-abc
description: Download Welsh traditional tunes from alawoncymru.com (CLERA "Alawon Cymru" tune index) and convert their MIDI files to ABC notation whose bars, repeats and line breaks match the sheet music on the site. Use when the user wants alawoncymru / alawon tunes as ABC, wants to (re)transcribe, check or fix one of those tunes, or wants a tunebook built from them.
---

# alawoncymru.com MIDI -> ABC

The site (http://alawoncymru.com/alawon/Tunes/Tunesal.html) has, per tune, a
NoteWorthy Composer MIDI (melody only, repeats played out) and a GIF score.
The notes come from the MIDI; the **bar layout must match the score**: same
pickup, same bar lines, same repeat marks and endings, same line breaks.

Scripts are in `scripts/` next to this file. They need only `mido`; run them as

```bash
uv run --no-project --with mido python <skill-dir>/scripts/<script>.py ...
```

(or any Python with `mido` installed). `<skill-dir>` is this skill's directory.

## 1. Download (once, or again to pick up new tunes)

```bash
scrape.py --out tunes            # all tunes; --only <text> limits the downloads
```

Creates `tunes/<slug>/` with `tune.mid`, `score.gif` and `info.json` (name,
aliases, key hint and dance type from the index, source URLs, `pairing`
confidence) plus `tunes/manifest.json` and `tunes/unpaired.json`. Some MIDI
links on the site are dead (404 or empty); those tunes have no `tune.mid` and
are listed by `abctool.py status`.

## 2. Convert

```bash
abctool.py batch tunes           # every tune.mid -> tune.abc (skips existing files)
abctool.py convert tunes/<slug>/tune.mid [options]    # one tune
```

`convert` picks the melody track, rounds NoteWorthy's played lengths to note
values (rests, staccato), guesses the pickup, folds the played-out repeats
into `|: :|` / `[1 [2`, writes `tune.abc`, and runs the check. Options:

| option | use when |
|---|---|
| `--pickup 1/4` (or `0`) | the first bar in the score is a different length from the guess |
| `--transpose N --key Em` | the MIDI is in another key than the score (warning is printed) |
| `--key DMix` | the key/mode label is wrong (signature is taken from the key) |
| `--no-fold` | the score writes out what the MIDI repeats |
| `--bars A-B` | the MIDI also plays another tune; keep played bars A-B (see `bars`) |
| `--track N` | the melody is not the first note track (harmony parts exist) |
| `--bars-per-line N` | the score has N bars per line (short pickup bars are not counted) |

`abctool.py bars tune.mid` prints the MIDI bar by bar with numbers (repeats
written out) — use it to find `--bars` ranges or to see what the MIDI plays.

Options that change what is compared (track, transpose, pickup, bars) are
saved in a `%%alawon ...` line in the ABC, which `check` reads back. Keep it.

## 3. Review each tune against its score (the important part)

For each tune: read `tunes/<slug>/score.gif` (look at it) and `tune.abc`, then
go through this list and fix the ABC — by re-running `convert` with options, or
by editing the text directly (bar lines, repeat marks, line breaks).

1. **Right score?** The pairing is heuristic (`info.json` → `pairing: low`
   means check twice). If the score is a different tune or a different
   version, look for the right image in `info.json` → `page_url` /
   `tunes/unpaired.json`, download it as `score.gif`, and say so.
2. **Key.** Same signature and tonic as the score? A MIDI in another key needs
   `--transpose` (semitones from MIDI to score) and `--key`.
3. **Meter and first bar.** Same `M:`? Does bar 1 start with the same notes
   as the score, i.e. same pickup? Otherwise `--pickup`.
4. **Bar lines.** Every bar must hold the same notes as the score's bar.
   These scores often end a part on a short bar and start the next part with
   its own pickup bar (`... | G4 :| D2 | GA Bc dB |`); the converter does this
   when the parts repeat, but for written-out parts you may need to split a
   bar by hand (`G3- G2 D |` → `G3- G2 | D |`).
5. **Repeats.** Same `|:` `:|` `::` `[1` `[2` as the score. The MIDI sometimes
   plays a part a different number of times than the score shows — follow the
   score.
6. **Line breaks.** One ABC line per score line (system).
7. **Title.** `T:` should be the name printed on the score (keep the others as
   extra `T:` lines).

Then run:

```bash
abctool.py check tunes/<slug>/tune.abc tunes/<slug>/tune.mid
```

- `OK` — the ABC plays exactly the MIDI's notes and rhythms.
- `REPEATS-DIFFER` — same music, but a passage is repeated a different number
  of times than in the MIDI. Fine only if that is what the score's repeat
  marks say; mention it to the user.
- `MISMATCH` — a note, rhythm or bar was changed or lost. Fix it; never leave a
  tune in this state. (If the score and the MIDI genuinely disagree on notes,
  keep the MIDI's notes, add an `N:` line describing the difference, and tell
  the user.)

The "bars not matching the meter" list is information: a pickup bar and the
short bar that completes it are expected; anything else deserves a look.

When a tune is done, add the line `%%alawon-reviewed` after the `%%alawon`
line so `batch --force` never overwrites it.

Don't add chord symbols, part labels (`P:`) or decorations unless the user
asks; if they do, take them from the score image (`"Em"` before the note it
sits over).

## 4. Report / collect

```bash
abctool.py status tunes          # reviewed / converted / missing counts
abctool.py collect tunes -o alawon-tunes.abc [--reviewed-only]
```

Tell the user which tunes you reviewed, what you changed, and anything left
unresolved (dead links, wrong pairings, MIDI/score disagreements).

Many tunes means many images: work in batches (e.g. by set page or first
letter), and only review the tunes the user asked for.
