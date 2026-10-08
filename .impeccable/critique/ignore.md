# Critique: findings to drop

Decisions the owner has made, and things earlier critiques got wrong. Drop any finding that matches one of these, silently. Don't list it as a priority issue, minor observation, persona red flag or question, and don't count it against any heuristic score.

## Already handled (an earlier critique was wrong)

- **"No warning by Play when offline and the piano sounds aren't saved."** This is already handled. `fillSoundNote` (site/app.js) shows a note under the player when there's no signal. If no sounds are saved at all, it also disables Play ("Needs a signal the first time"). If only some are saved, it says which will sound. Once anything has been played, every note is saved automatically. A headless or online screenshot never shows this note, so check `fillSoundNote` / `.sound-note` before reporting it.

## Declined on purpose

- **"bpm" in the Welsh interface.** "bpm" is an internationally recognised abbreviation and is used in both languages on purpose. Don't flag it as untranslated, inconsistent or unexplained, and don't suggest "curiad y funud" or "c.y.f." instead.

- **A "Back to <original key>" / reset-key button on the tune page.** It was tried and removed because it crowds the controls. The way back is the Key menu, where the written key is marked "(original)". The phone's one line says "A (from G)" when the key has moved. Don't suggest a reset button or chip in any form.
- **"Play this next", related or next tunes, or ready-made sets.** The site never suggests sets or what to play next; the owner rules this out entirely. The empty space at the end of a tune page is not a reason to add one. Don't propose it as a fix, a peak-end idea or a provocative question.
