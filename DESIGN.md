---
name: Y Sesiwn
description: Welsh folk tunes to learn, play and share, framed in slate, cream paper and carthen.
colors:
  welsh-red: "#C8102E"
  welsh-red-soft: "#c8102e1a"
  accent-ink-night: "#ee4a66"
  brand-red-night: "#ee4a66"
  slate: "#3b4550"
  warm-off-white: "#fdfbf7"
  pale-slate: "#eef0f1"
  card-white: "#ffffff"
  cream-paper: "#fbf6ea"
  score-ink: "#000000"
  carthen-cream: "#f3ead3"
  ink: "#262b31"
  muted-slate: "#5f6973"
  hairline: "#dcdfe3"
  link-blue: "#1a67c2"
  land-grey: "#e2e5e8"
  flannel-black: "#1d1d1b"
  ivory: "#fffdf8"
  key-edge: "#b9bcc2"
  ebony: "#262b31"
  ebony-edge: "#111111"
  player-track: "#2a323b"
  night-bg: "#111418"
  night-sidebar: "#1a1f25"
  night-card: "#171b21"
  night-text: "#eef0f2"
  night-muted: "#a0a8b1"
  night-border: "#343b44"
  night-link: "#6fb1ff"
  night-paper: "#ddd6c6"
  type-jig: "#C8102E"
  type-polca: "#2f4f8f"
  type-walts: "#c28f1c"
  type-ril: "#2e6b4f"
  type-pibddawns: "#7b3f6e"
  type-ymdaith: "#2b7a7f"
  type-dawns: "#b4532a"
  type-alaw: "#5b6f8c"
  type-can: "#a3456a"
  type-carol: "#6b7b2c"
  type-other: "#6b737c"
typography:
  brand:
    fontFamily: "system-ui, -apple-system, Segoe UI, Roboto, sans-serif"
    fontSize: "1.75rem"
    fontWeight: 700
  headline:
    fontFamily: "system-ui, -apple-system, Segoe UI, Roboto, sans-serif"
    fontSize: "2rem"
    fontWeight: 700
    lineHeight: 1.2
  title:
    fontFamily: "system-ui, -apple-system, Segoe UI, Roboto, sans-serif"
    fontSize: "1.35rem"
    fontWeight: 700
  body:
    fontFamily: "system-ui, -apple-system, Segoe UI, Roboto, sans-serif"
    fontSize: "16px"
    fontWeight: 400
    lineHeight: 1.55
  lead:
    fontFamily: "system-ui, -apple-system, Segoe UI, Roboto, sans-serif"
    fontSize: "1.1rem"
    lineHeight: 1.55
  card-title:
    fontFamily: "system-ui, -apple-system, Segoe UI, Roboto, sans-serif"
    fontSize: "1.15rem"
    fontWeight: 700
  caption:
    fontFamily: "system-ui, -apple-system, Segoe UI, Roboto, sans-serif"
    fontSize: "0.9rem"
  small:
    fontFamily: "system-ui, -apple-system, Segoe UI, Roboto, sans-serif"
    fontSize: "0.85rem"
  fine:
    fontFamily: "system-ui, -apple-system, Segoe UI, Roboto, sans-serif"
    fontSize: "0.8rem"
  label:
    fontFamily: "system-ui, -apple-system, Segoe UI, Roboto, sans-serif"
    fontSize: "0.9rem"
    fontWeight: 600
  keycap:
    fontFamily: "ui-monospace, SF Mono, Menlo, monospace"
    fontSize: "0.75rem"
    fontWeight: 600
    lineHeight: 1
rounded:
  swatch: "2px"
  keycap: "4px"
  inset: "6px"
  md: "8px"
  pill: "999px"
spacing:
  band: "14px"
  band-thin: "7px"
  sidebar: "300px"
  main-max: "1200px"
  main-pad: "2.5rem 3rem 4rem"
  main-pad-phone: "1.5rem 1rem 3rem"
components:
  button:
    backgroundColor: "{colors.card-white}"
    textColor: "{colors.ink}"
    rounded: "{rounded.md}"
    padding: ".45rem .9rem"
  button-hover:
    backgroundColor: "{colors.card-white}"
    textColor: "{colors.welsh-red}"
  button-primary:
    backgroundColor: "{colors.welsh-red}"
    textColor: "{colors.card-white}"
    rounded: "{rounded.md}"
    padding: ".45rem .9rem"
  pill:
    backgroundColor: "{colors.card-white}"
    textColor: "{colors.ink}"
    rounded: "{rounded.pill}"
    padding: ".45rem .9rem"
  pill-chosen:
    backgroundColor: "{colors.slate}"
    textColor: "{colors.card-white}"
    rounded: "{rounded.pill}"
  search-input:
    backgroundColor: "{colors.card-white}"
    textColor: "{colors.ink}"
    rounded: "{rounded.pill}"
    padding: ".7rem 2.4rem .7rem 2.5rem"
  card:
    backgroundColor: "{colors.card-white}"
    textColor: "{colors.ink}"
    rounded: "{rounded.md}"
    padding: "1rem 1.1rem"
  score-paper:
    backgroundColor: "{colors.cream-paper}"
    textColor: "#000000"
    rounded: "{rounded.md}"
    padding: ".75rem 1rem 1rem"
  sidebar:
    backgroundColor: "{colors.pale-slate}"
    textColor: "{colors.ink}"
    width: "{spacing.sidebar}"
    padding: "1.5rem 1.25rem"
---

# Design System: Y Sesiwn

## Overview

**Creative North Star: "The Carthen on the Chair"**

Y Sesiwn looks like a warm, practical room in a Welsh house: a woven *carthen* blanket thrown over the chair, slate on the roof, sheet music on cream paper left open on the stand. It is homely and useful, never fussy. The furniture is plain (system fonts, thin borders, gentle corners) so that the few Welsh materials carry the identity: the carthen band across the top and bottom of every page, Welsh slate for structure, Welsh flag red for accents, and red-and-black flannel down the edge of a call-out.

Density is moderate and calm. A fixed slate sidebar holds the name, search and links; the page beside it has generous padding and a single readable column, with the sheet music as the largest and most important object on a tune page. Decoration is woven in, not laid on top: carthen strips under section headings, a carthen colourway for each tune type, a scrap of quilt behind the drawn instruments. Everything works in dark mode, where the paper stays paper (dimmed, never inverted).

The system is built for a phone at a session as much as a laptop at home, so every flourish has to survive 360px wide, offline, in a dark pub.

**Key Characteristics:**
- Plain, sturdy chrome; identity carried by Welsh materials (carthen, slate, flannel, red).
- Sheet music always on cream "paper", in light and dark mode.
- Red is for accents, focus and chosen states; slate is for structure.
- One colourway per tune type, shown as a small woven swatch.
- System font stack throughout; no web fonts.
- Light and dark themes from the same tokens; high-contrast and reduced-motion respected.

## Colors

A warm off-white room framed in Welsh slate, with Welsh flag red used sparingly and a family of carthen dye colours to tell tune types apart.

### Primary
- **Welsh Flag Red** (`welsh-red`): the accent. As a **fill** (`--accent`, the same in both themes, always with white text): primary buttons, the chosen language and segment, the skip link, the heard piano key, selection highlight. As **ink** (`--accent-ink`): focus outlines, hover text and borders, fold chevrons, the chord chart's repeat signs, lit map dots.
- **Night Red** (`brand-red-night`, `accent-ink-night`): the ink and the site name in dark mode, 4.5:1 or more on every dark surface. Fills stay Welsh Flag Red, because white on Night Red is only 3.6:1. Inside the score's cream paper the ink stays Welsh Flag Red in both themes.
- **Red Wash** (`welsh-red-soft`): a 10% tint of the red for hovered/selected suggestions, places and the search focus ring.

### Secondary
- **Welsh Slate** (`slate`): structure and the "chosen" state. A chosen key or filter pill is filled slate with white text; the audio player bar is slate; map dots are slate. In dark mode the chosen fill flips to pale grey with near-black text.

### Tertiary
- **Carthen Colourways** (`type-*`): one dye colour per tune type: Welsh red (jig), indigo (polca), mustard (walts), bottle green (rîl), plum (pibddawns), teal (ymdaith), rust (dawns), slate blue (alaw), rose (cân), olive (carol), slate grey (other). Used only as type swatches and as the border/tint of a chosen type pill.

### Neutral
- **Warm Off-White** (`warm-off-white`): page background.
- **Pale Slate** (`pale-slate`): sidebar and phone top bar.
- **Card White** (`card-white`): cards, buttons, inputs.
- **Cream Paper** (`cream-paper`): behind sheet music only; **Night Paper** (`night-paper`) in dark mode.
- **Score Ink** (`score-ink`): the notes, staves and text of the sheet music, on its paper in both themes; also the QR code.
- **Carthen Cream** (`carthen-cream`): the cream diamond in the carthen and swatches; the hovered piano key.
- **Ink** (`ink`): body text. **Muted Slate** (`muted-slate`): captions, labels, footer, held chords.
- **Hairline** (`hairline`): every border and divider.
- **Link Blue** (`link-blue`, `night-link` at night): links, chosen to reach 4.5:1 on every background including the sidebar.
- **Land Grey** (`land-grey`): the map of Wales.
- **Flannel Black** (`flannel-black`): the black stripe in the flannel edge.
- **Ivory and Ebony** (`ivory`, `ebony`, with `key-edge`, `ebony-edge`; hover `carthen-cream` and `slate`): the piano keyboard, the same in both themes. Key labels are Muted Slate (5.5:1 on ivory).
- **Player Track** (`player-track`): the player's position bar on its slate.

### Named Rules
**The Flag Not Paint Rule.** Welsh red marks what is active, focused, chosen or important. It never fills large areas or backgrounds.

**The Paper Stays Paper Rule.** Sheet music always sits on cream paper with black notes, in both themes. Dark mode dims the paper; it never inverts the music.

**The Ink and Fill Rule.** Red used as a line or text uses `--accent-ink`; red behind white text uses `--accent`. Never put red text or outlines on a dark surface in Welsh Flag Red: it is under 3:1.

**The Colourway Rule.** Tune-type colours belong to tune types only. Do not reuse them for status, categories or decoration elsewhere.

## Typography

**Body Font:** system-ui (with -apple-system, Segoe UI, Roboto, sans-serif)
**Label/Mono Font:** ui-monospace (SF Mono, Menlo), for keyboard keycaps and the typed-notes field only, where notes like `D E F# G` need to line up

**Character:** one native system face at every level, so the site loads instantly, works offline and feels at home on any device. Hierarchy comes from size and weight, never from a second display face.

### Hierarchy
- **Brand** (700, 1.75rem; 1.25rem on phones): the site name in Welsh red beside the harp icon.
- **Headline** (700, 2rem, 1.2): page titles, with nothing beneath: the size carries them, and the carthen band is already above.
- **Title** (700, 1.35rem): section headings, often with a carthen strip beneath; also the practice-mode page title.
- **Card title** (700, 1.15rem): card and offline-card headings; also the big home search's text.
- **Body** (400, 16px, 1.55): all reading text; long prose capped near 50rem.
- **Lead** (1.1rem): the opening line of a page.
- **Caption** (0.9rem, muted): notes under controls, footer, statuses, secondary lists.
- **Small** (0.85rem): the language switch, town labels on the map, compact controls on small phones.
- **Label** (600, 0.9rem, sentence case, ink): group labels over pill rows and lists ("Key", "Next seven days").
- **Keycap** (600, 0.75rem mono, bordered): keyboard shortcut hints like `/`.

### Named Rules
**The Ramp Rule.** Sizes come from the ramp: .75, .8, .85, .9, 1, 1.1, 1.15, 1.35 and 2rem, plus the brand (1.25/1.75rem), the piano's key labels (.72rem), chord superscripts (.65rem) and print-only chart sizes. Don't add in-between sizes like .95 or 1.05rem.

**The One Face Rule.** The system font stack is the only typeface. No web fonts: they cost the offline cache and the instant load.

## Layout

A two-column app shell: a sticky 300px pale-slate sidebar (name, language switch, search, Surprise me, links) beside a main column padded 2.5rem/3rem and capped at 1200px. A carthen band (14px tall) runs across the top of the page and the top of the footer.

Tune pages split the main column 3:1: score on the left, details card on the right (min 14rem). Lists of tunes flow into newspaper columns (3 × min 14rem); feature lists into 2 columns of 22rem.

Breakpoints:
- **≤1100px:** the instruments-on-quilt picture moves from beside the welcome to near the end of the home page, just before "Take it to the session", so phones still see it without it pushing the search down.
- **≤800px (phone):** the sidebar becomes a sticky top bar (name + search) with a row underneath (language, Surprise me, Menu); links fold under Menu. Single column, main padding 1.5rem/1rem; the tune's controls reorder so the music starts on the first screen.
- **≤420px / ≤380px:** tighter button padding so language, Surprise me and Menu stay on one row.
- **Touch screens (`pointer: coarse`):** every button, select, input, segment, version tab and fold heading is at least 44px tall (preview play and map zoom 44 × 44px); the player uses abcjs's large size; the piano widens to at least 36rem (black keys about 25px wide) and scrolls sideways within its own strip.

Practice mode drops the sidebar, side card and footer for a full-width score (up to 1400px), for a tablet on a music stand. Nothing ever scrolls sideways at phone width except the piano keyboard, which scrolls within itself.

## Elevation & Depth

Mostly flat: surfaces are separated by hairline borders and tonal steps (off-white page, pale-slate sidebar, white cards, cream paper). Shadows are faint and functional: a barely-there lift on paper and cards at rest, and a deeper shadow only on things that float over content (search suggestions, map popups).

### Shadow Vocabulary
- **Resting** (`box-shadow: 0 1px 3px #0000000f`): score paper, offline card.
- **Search** (`box-shadow: 0 1px 2px #0000000d`; hero search `0 2px 10px #0000000f`): the search fields.
- **Floating** (`box-shadow: 0 10px 30px var(--shadow-float)`, map popup and menus `0 8px 24px`; `--shadow-float` is `#00000026`): search suggestions, map popups, menus. Small floating controls (map zoom, the set's previous/next bar) use `--shadow-soft` (`#0000001f`).
- **Scrim** (`--scrim`, `#0006`): behind dialogs.
- **Top bar** (`box-shadow: 0 2px 8px #0000000f`): the sticky phone top bar.
- **Focus ring** (`0 0 0 3px` red wash): focused search inputs.

### Named Rules
**The Hairline First Rule.** Separate with a 1px hairline border and a tonal step before reaching for a shadow. Shadows are for things that float.

## Shapes

Gentle, consistent corners: 8px on buttons, cards, inputs, tabs, panels and the score; full pills (999px) for search fields and filter/key pills; 6px for small insets (audio bar, previews); 2px for swatches; 4px for keycaps; round for preview play buttons. Woven geometry (the carthen band, the rotated cream diamond inside each swatch) is the one recurring motif; it appears as bands and small marks, never as large fills.

## Components

Plain and sturdy throughout: thin borders, gentle corners, red only on hover and chosen; nothing glossy.

### Buttons
- **Shape:** gently rounded (8px).
- **Default:** white with a hairline border and ink text, padding .45rem .9rem.
- **Hover (pointer devices only):** border and text turn Welsh red; colour transitions at .15s. Touch screens get no hover look, so a tapped button doesn't seem stuck "on".
- **Primary:** filled Welsh red, white text; hover brightens slightly.
- **Disabled:** 50% opacity.
- **Focus:** 2px Welsh-red outline, 2px offset, everywhere.

### Chips / Pills
- **Style:** fully rounded white pills with a hairline border, in wrapping rows.
- **Type pills:** a small woven swatch in the type's colourway; chosen = border in the colourway, 14% tint fill, bold.
- **Key / plain pills:** chosen = filled slate, white text, bold.
- **All chosen pills** get a drawn tick before the label, so the state is never colour alone.

### Cards / Containers
- **Corner Style:** 8px.
- **Background:** card white.
- **Border:** hairline only. The title carries the card; no coloured edge.
- **Internal Padding:** 1rem 1.1rem.
- **Variants:** the offline card has a thin carthen strip along its top (the one card that does); folding panels (practice tools) use a red chevron that turns when open.

### Inputs / Fields
- **Search:** full pill, 1.5px hairline border, magnifier icon inset left, `/` keycap hint right (hidden on touch). Focus: red border plus a 3px red-wash ring. Suggestions drop below in a floating card; the one Enter opens has a red bar down its left side.
- **Selects:** 8px corners, hairline border, white.
- **Range / checkbox:** native, tinted with `accent-color` Welsh red.
- **Segmented control:** joined buttons in one bordered group; the chosen one fills red with white text.

### Icons
Drawn, never typed: the search magnifier, microphone, share, play and stop are inline SVGs in a 1.8 rounded stroke or solid fill; the chevron (on every `summary`, the Menu button and the Print menu) and the pill tick are SVG masks (`--chevron`, `--tick`) in the text's colour, so they follow the theme. A chevron points right when closed and turns down when open. Unicode stays for content only: the whistle fingering charts (● ○ ◐), "·" separators, and the "✓" in short confirmations ("✓ Link copied").

### Navigation
- **Sidebar:** pale slate, sticky, the name in red at top, a two-button language switch (chosen = red), then search, actions, and a list of links separated by a hairline. Links go red with underline on hover.
- **Phone:** sticky top bar (name + search) and a row with language, Surprise me and a Menu button (a drawn chevron) that unfolds the links.
- **Version tabs:** bordered boxes in a row; the active one has a red border and a 3px red underline.

### Sheet Music (signature)
The score sits on cream paper in an 8px bordered panel with a resting shadow; notes are black and the playing note turns red. The abcjs player bar is slate with a red progress knob and red pressed buttons. Tapping a note plays from it. Chord symbols are drawn but hidden unless switched on.

### Carthen Band (signature)
A repeating woven strip in Welsh red, slate and cream: 14px across the top of the page and footer, 7px under section headings (as long as the heading), along the top of the offline card, and beneath empty-state art.

### Tune Page Controls
Grouped by what you're doing, not by how they were built:
- **Listen** (always visible): Key and Tempo above the music; the player bar (restart, play, position) and the Tune / chords choice on the paper. At the end of the Key and Tempo row, apart from them, **how the music is shown**: Size − / + and Full screen. On a phone that row becomes two: Key with Size, then Tempo with Full screen, so the music starts on the first screen.
- **Practise** (folding, open on wide screens, folded on phones), three lines: Repeat (Off / The whole tune / Part A…) with Speed up *from* the tempo *to* a bpm box; Count-in, Click, Swing; Tablature. There is one way to repeat: the player's own repeat button is hidden.
- **Take it with you** (a quiet row under the practise tools): Share, Print / save, QR code, Add to set.
- **Reference** (side column): Details, On the map, ABC notation, Report a problem.

### Practice Tools: "Da iawn"
The one celebration in the system, saved for real effort. While **Speed up** repeats the tune or a part, a caption under the repeat line says how far there is to go ("now 94 of 100 bpm"). When it reaches the "to" bpm, the caption says "Reached 100 bpm.", ends with a red, Welsh **Da iawn!** (well done), and a 6rem strip of carthen weaves in under it, left to right, once (clip-path, 0.7s, exponential ease-out; static under reduced motion). The caption has its own line, so the controls never move; it is announced politely to screen readers.

**The Earned Moment Rule.** Celebrate only what took effort (working a tune up to speed), never a click. Use the carthen and a word of Welsh, not confetti or emoji.

### Chord Chart
One cell per bar in rows of 4 (3 or 5 where the part divides that way), bold 1.1rem chord names, muted bar lines, repeat signs as thick red bars with red colons; held chords muted.

### Piano Keyboard
G3–A5, ivory white keys (`#fffdf8`) with mid-grey borders and dark ink black keys; hover warms to carthen cream; a pressed or heard key flashes Welsh red. Scrolls horizontally inside itself on a phone.

### Session Cards
A hairline card per session: name (with a Tune club badge), when and next date, address, what's played, then a row of quiet bordered buttons, **Map**, **Add to calendar**, **More about it** (44px tall on touch), and one muted closing line, "Confirmed 2 Oct 2026 · Been lately? Tell us", which opens the report form. Session lines elsewhere (home "Coming up", the sessions page's own list) link to their card. Filters: days as pills (only days that have a session), areas as a drop-down with counts. On phones the list comes before the map, so a filter's result is in sight.

**The Plain Primary Rule.** On the home page nothing is red but the search's focus: the search box is the way in, and Surprise me is a plain button beside Browse.

### Map of Wales
Land in land grey as a mask so it follows the theme; session towns as small slate dots that keep their size when zoomed; the current or lit town in red; popups are plain hairline cards with the floating shadow.

## Do's and Don'ts

### Do:
- **Do** keep Welsh red for accents, focus, chosen states and the brand name only.
- **Do** put all sheet music on cream paper with black notes, in both themes.
- **Do** separate surfaces with a 1px hairline and a tonal step first; keep shadows faint.
- **Do** mark a chosen state with more than colour (a drawn tick, weight, an underline bar or a fill).
- **Do** use the carthen band as a strip or edge (14px or 7px), never as a full background.
- **Do** define every colour as a token in `:root` with a dark-mode value, and check it in forced-colors mode.
- **Do** use `--accent-ink` for red lines and text and `--accent` for red fills with white text.
- **Do** make every control at least 44px tall on touch screens.
- **Do** limit hover styles to `(hover: hover)` devices, and keep transitions short (.15s) and off under reduced motion.

### Don't:
- **Don't** put a coloured bar on one edge of a card or popup, or a short accent bar under a heading: the carthen strip is the system's one heading mark.
- **Don't** set labels in small tracked uppercase; use sentence case at .9rem, semibold.
- **Don't** use Unicode glyphs (▶ ▸ ▾ ⌫ ■) as icons; draw them.
- **Don't** add web fonts or a second typeface.
- **Don't** fill large areas with Welsh red or carthen pattern.
- **Don't** invert or dark-theme the sheet music.
- **Don't** reuse tune-type colourways for anything other than tune types.
- **Don't** add glossy gradients, heavy shadows or glassy blur; the chrome stays plain and sturdy.
- **Don't** let anything but the piano scroll sideways at phone width.
- **Don't** hard-code colours in rules; add a token in `:root` (the QR code's pure black on white is the one exception).
