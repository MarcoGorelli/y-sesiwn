# Critique: findings to drop

Decisions the owner has made, and things earlier critiques got wrong. Drop any finding that matches one of these, silently. Don't list it as a priority issue, minor observation, persona red flag or question, and don't count it against any heuristic score.

## Already handled (an earlier critique was wrong)

- **"No warning by Play when offline and the piano sounds aren't saved."** This is already handled. `fillSoundNote` (site/app.js) shows a note under the player when there's no signal. If no sounds are saved at all, it also disables Play ("Needs a signal the first time"). If only some are saved, it says which will sound. Once anything has been played, every note is saved automatically. A headless or online screenshot never shows this note, so check `fillSoundNote` / `.sound-note` before reporting it.

## Declined on purpose

- **"bpm" in the Welsh interface.** "bpm" is an internationally recognised abbreviation and is used in both languages on purpose. Don't flag it as untranslated, inconsistent or unexplained, and don't suggest "curiad y funud" or "c.y.f." instead.

- **A "Back to <original key>" / reset-key button on the tune page.** It was tried and removed because it crowds the controls. The way back is the Key menu, where the written key is marked "(original)". The phone's one line says "A (from G)" when the key has moved. Don't suggest a reset button or chip in any form.
- **"Play this next", related or next tunes, or ready-made sets.** The site never suggests sets or what to play next; the owner rules this out entirely. The empty space at the end of a tune page is not a reason to add one. Don't propose it as a fix, a peak-end idea or a provocative question.
- **A tempo for sets (one for the whole set, or one per tune, carried in the set's link).** Sets play each tune at its written tempo, on purpose. Don't flag that a set can't carry or change tempo, and don't suggest a set tempo control.
- **The tune-page holes/tabs invite going away for good once `tabKnown` is set** (by any menu choice, opening the practice tools, or playing three tunes with the music alone). This is intended. Don't flag it as hiding the feature from ear learners, and don't suggest shrinking it to a line, raising the count, or changing what counts as an answer.
- **Which settings are saved globally, per tune, or not at all.** The split is deliberate. Saved globally (on the device): count-in, click, chords on the sheet music, holes/tabs, and whether the practice tools are open or folded. Saved per tune (on the device): key, tempo, which chords you hear (tune only, tune and chords, chords only), and swing (hornpipes start swung). Not saved: repeat, speed up, and the tempo to speed up to. Don't flag any of these as inconsistent or surprising, and don't suggest moving one between groups, saving repeat/speed-up, or adding a "remember for all tunes" option.
- **Lower / higher in the Key menu** (optgroups, arrows, "up 2" or any other sign of direction). Whether a key is lower or higher depends on the octave the player chooses, so the menu doesn't say. Don't flag the key menu for having no direction, and don't suggest adding one.
