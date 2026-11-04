# Notes for AI agents

How to add a tune and what the ABC headers mean is in CONTRIBUTING.md. These are the extra rules the maintainer has given.

## Adding or renaming tunes

After adding, renaming or merging anything in `tunes/`, fill these in yourself instead of just listing what's missing:

- `pronunciation.json`: every Welsh-named tune needs a "Say it" respelling under `say`, kept in alphabetical order. English names go under `english` instead. The site marks a name as Welsh (`lang="cy"`) only when it has a respelling, so a missing one also makes screen readers read the name as English.
- `places.json`: a tune named after a place in Wales (or just over the border) goes on the map, under the place's Welsh name. Rivers aren't mapped. Names that only look like places go in `not_places`.
- `tune_numbers.json`: run `python build_site.py --number-tunes` to give new tunes their permanent set-link number. It only appends. Never edit or reuse an existing number, or old set links will open the wrong tune.

- Spelling: proofread the Welsh in every new or submitted tune (titles, `w:`/`W:` words, notes) and fix clear typos: wrong or swapped letters, missing circumflexes (lân, gân, môr, â), mutations that are plainly wrong. Put the corrected spelling as the first `T:` and keep the source's spelling as a later `T:`, so searches for it still work. If the slug changes, rename the folder and add the old name to `moved.json`. Old or dialect spellings (Pibddawns, yspryd, hogie) aren't typos; ask when unsure. Also add the well-known English name as a `T:` if there is one (Llwyn Onn: The Ash Grove).

`tests/test_build.py` fails until the first two are done (`test_every_tune_has_a_pronunciation_or_is_english`, `test_place_names_decided`). The place test only flags names that look likely, so read new titles yourself too.

## Writing ABC

- Keep the notes, rhythms, bars and repeats. Layout doesn't have to follow the score: break lines wherever reads most easily on a phone. This applies to every tune, including the Alawon Cymru ones and all submissions. Tunes with sung words (`w:`) read better with fewer bars a line, around 2, so the syllables don't crowd.
- Folding a written-out passage into `|: :|` or first/second endings is fine, even when the score writes it out, as long as it's clearer.
- First and second endings span one bar, two at most. If the copies differ over more bars, write the part out. Close the second ending with `||` (or `|]`, `|:`) straight after its bar(s): abcjs keeps an ending's bracket open until the next one of those, so `:|2 x |` followed by more bars shows as one long ending.

## The site

- Never suggest ready-made sets or "play this next" tunes, on tune pages or anywhere else. Sets are only what players build themselves. The one exception is a night's tunes at a session (`setlists/`), shown as they were played and playable from its page: a whole night's list doesn't say which tunes go together. Still never link from a tune to the nights it was played on, or to what was played after it.
- Many players read the dots. Any chooser for learner aids (holes, tabs) offers "Just the music" as an equal choice, selected by default, and choosing it dismisses the prompt for good. Word such choices by what's shown ("Under the notes"), not by instrument ("What do you play?").
