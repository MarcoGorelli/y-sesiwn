"use strict";
// Y Sesiwn: everything runs in the browser from tunes.json (see build_site.py).
// Pages: ./ (home), alaw/<folder>/ (a tune; ?v=2 for its second version), ?page=add / ?page=fix
// (guides), ?page=contact, … Every address is relative to <base href> in index.html.

const NOTES = ["C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"];
const AUDIO_PARAMS = {
  program: 0,
  soundFontUrl: "static/soundfont/",
  // abcjs only applies this boost automatically for its default online soundfont.
  soundFontVolumeMultiplier: 3.0,
};
// On iPhone/iPad, web audio is muted by the silent switch unless the page says
// its sound is "playback" (like a music app). Ours only plays when someone presses
// play or a piano key, so ask for playback. (Safari 16.4+; ignored elsewhere.)
if ("audioSession" in navigator) navigator.audioSession.type = "playback";

// Markdown pages: ?page=<key> shows the "# heading" section of file (or all of it).
// The Welsh versions (cy) are separate files, kept in step with the English ones.
const PAGES = {
  add: { file: "CONTRIBUTING.md", heading: "How to add a tune", cy: { file: "guides.cy.md", heading: "Sut i ychwanegu alaw" } },
  fix: { file: "CONTRIBUTING.md", heading: "How to submit corrections", cy: { file: "guides.cy.md", heading: "Sut i gyflwyno cywiriadau" } },
  about: { file: "about.md", heading: "About Y Sesiwn", className: "about", cy: { file: "about.cy.md", heading: "Am Y Sesiwn" } },
};

const state = {
  data: null,           // tunes.json (on a tune's own page, at first, only that tune: see start())
  loaded: null,         // tunes.json, on its way
  complete: false,      // whether data is all of it yet
  bySlug: new Map(),    // every tune file ("version"), by folder name
  byId: new Map(),      // and by its short_id (older set links)
  byCode: new Map(),    // and by its code in set links (build_site.py's set_code)
  moved: new Map(),     // a renamed tune's old folder name -> its new one (moved.json)
  groups: new Map(),    // one page per tune: its versions, by the first version's folder
  groupList: [],        // groups sorted by title
  settings: new Map(),  // per tune: { transpose, bpm }, kept while the page is open
  synth: null,          // the playing SynthController, stopped when leaving a tune
  keyNote: null,        // the note sounding from the search-by-notes keyboard
  listening: null,      // the microphone, while "Play it to me" listens
  autoListen: false,    // start listening when the notes page opens (from the home page)
  docs: new Map(),      // markdown files, fetched on first use
  chords: { onScore: false, play: "tune" },  // the chord box's settings, for every tune; play: tune, both or chords
  practice: { countIn: false, click: false, tab: "none", open: null },  // the practice tools, for every tune (open: folded or not)
  lang: savedLang(),    // "cy" or "en", for the whole site (tune names and the tunes' own notes stay as written)
  musicSize: savedSize(),  // the music's size, an index into SIZES (1: as drawn)
  offlineReady: false,  // the offline copy (sw.js) is saved
  sounds: null,         // how many piano notes it keeps: { saved, total }
  savingSounds: false,  // while it saves the rest, asked for on the offline card
};

// ---- Welsh or English --------------------------------------------------------------

function savedLang() {
  try {
    const saved = localStorage.getItem("lang");
    if (saved === "cy" || saved === "en") return saved;
  } catch {}
  return (navigator.languages ?? [navigator.language]).some((l) => /^cy\b/i.test(l)) ? "cy" : "en";
}

function savedSize() {
  try {
    const size = Number(localStorage.getItem("musicSize") ?? 1);
    if (Number.isInteger(size) && size >= 0 && size <= 4) return size;
  } catch {}
  return 1;
}

// The text in the chosen language: tr("Browse", "Pori").
function tr(en, cy) {
  return state.lang === "cy" ? cy : en;
}

// The sidebar, top bar and footer are in index.html, with the Welsh in data-cy attributes.
function applyLang() {
  document.documentElement.lang = state.lang;
  for (const node of document.querySelectorAll("[data-cy]")) {
    node.dataset.en ??= node.textContent;
    node.textContent = tr(node.dataset.en, node.dataset.cy);
  }
  for (const attr of ["placeholder", "title"]) {
    for (const node of document.querySelectorAll(`[data-cy-${attr}]`)) {
      if (!node.hasAttribute(`data-en-${attr}`)) node.setAttribute(`data-en-${attr}`, node.getAttribute(attr));
      node.setAttribute(attr, tr(node.getAttribute(`data-en-${attr}`), node.getAttribute(`data-cy-${attr}`)));
    }
  }
  for (const button of document.querySelectorAll(".lang-switch button")) {
    button.setAttribute("aria-pressed", button.dataset.lang === state.lang);
  }
}

function setLang(lang) {
  state.lang = lang;
  try { localStorage.setItem("lang", lang); } catch {}
  applyLang();
  countEvent(`language-${lang}`, lang === "cy" ? "Switched to Welsh" : "Switched to English");
  render();  // the page again, in the other language
}

// Musical names in Welsh: the key menu and details ("D major" -> "D fwyaf"), note values.
const CY_MODES = { major: "fwyaf", minor: "leiaf", Dorian: "Doriaidd", Phrygian: "Phrygaidd", Lydian: "Lydaidd",
  Mixolydian: "Mixolydaidd", Locrian: "Locriaidd" };
const CY_BEATS = { "dotted crotchet": "crosiet dotiog", minim: "minim", crotchet: "crosiet", quaver: "cwafer" };
const modeName = (name) => tr(name, CY_MODES[name] ?? name);
const keyLabel = (text) => tr(text, text.replace(/\b(major|minor|Dorian|Phrygian|Lydian|Mixolydian|Locrian)\b/g, (m) => CY_MODES[m]));
// A type of tune after a number, in Welsh ("96 jig"); in English the type's plural ("96 jigs").
const CY_TYPE = { Jig: "jig", Polca: "polca", Walts: "walts", "Rîl": "rîl", Pibddawns: "pibddawns", Ymdaith: "ymdaith",
  Dawns: "dawns", Alaw: "alaw", "Cân": "cân", Carol: "carol", Other: "alaw arall" };
const typeName = (name) => (name === "Other" ? tr("Other", "Arall") : name);

// ---- Small DOM helper ----------------------------------------------------

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [name, value] of Object.entries(attrs)) {
    if (value === false || value == null) continue;
    if (name.startsWith("on")) node.addEventListener(name.slice(2), value);
    else node.setAttribute(name, value === true ? "" : value);
  }
  node.append(...children.flat(Infinity).filter((c) => c != null));
  return node;
}

// ---- Search (same matching as the original Python app) --------------------

function normalize(text) {
  // Lowercase, strip accents and punctuation, e.g. "Frân" -> "fran".
  return text.normalize("NFKD").replace(/\p{M}/gu, "").toLowerCase()
    .replace(/[^a-z0-9 ]+/g, " ").trim();
}

// difflib.SequenceMatcher(None, a, b).ratio(): matching characters found by
// taking the longest common substring and recursing on both sides of it.
function matched(a, alo, ahi, b, blo, bhi) {
  let best = 0, bi = alo, bj = blo;
  for (let i = alo; i < ahi; i++) {
    for (let j = blo; j < bhi; j++) {
      let k = 0;
      while (i + k < ahi && j + k < bhi && a[i + k] === b[j + k]) k++;
      if (k > best) { best = k; bi = i; bj = j; }
    }
  }
  if (!best) return 0;
  return best + matched(a, alo, bi, b, blo, bj) + matched(a, bi + best, ahi, b, bj + best, bhi);
}
function ratio(a, b) {
  return a.length + b.length ? (2 * matched(a, 0, a.length, b, 0, b.length)) / (a.length + b.length) : 1;
}

// "y", "yr" and "'r" (the), so "Helfa'r Sgwarnog" finds "Hel y Sgwarnog".
const ARTICLES = new Set(["y", "yr", "r", "the"]);
const words = (text) => {
  const all = text.split(/\s+/).filter(Boolean);
  const kept = all.filter((w) => !ARTICLES.has(w));
  return kept.length ? kept : all;
};

function score(query, tune) {
  // 2 for the exact name, 1 if the title has the query at the start of a word ("mon" finds "Mwynen Môn",
  // not "harmoni"), otherwise the average word-by-word similarity, so small typos
  // and other spellings ("trefalwdyn", "Risiart") still match.
  let best = 0;
  const queryWords = words(query);
  for (const title of tune.search) {
    if (title === query) return 2;  // the exact name comes first
    if (` ${title}`.includes(` ${query}`)) { best = 1; continue; }
    const titleWords = words(title);
    const scores = queryWords.map((q) => Math.max(0, ...titleWords.map((t) => ratio(q, t))));
    best = Math.max(best, (0.99 * scores.reduce((s, x) => s + x, 0)) / scores.length);
  }
  return best;
}

function search(query) {
  // Tunes (groups of versions) whose names match; any version's titles count.
  const q = normalize(query);
  if (!q) return state.groupList;
  return state.groupList
    .map((tune) => [score(q, tune), tune])
    .filter(([s]) => s >= 0.7)
    .sort((x, y) => y[0] - x[0] || (x[1].title < y[1].title ? -1 : 1))
    .map(([, tune]) => tune);
}

// ---- Search by notes (any key) ------------------------------------------------------
// Tunes and queries become the steps between successive notes, in semitones, and
// repeated notes are ignored; steps don't depend on the key. Notes tapped on the
// keyboard (or typed with an octave, "G3") give exact steps, leaps included. Note
// names without an octave ("D E F#") are compared by the smaller way round
// (-5..+6 semitones), since people rarely know the octave of a tune they hum.

const LETTER_PITCH = { C: 0, D: 2, E: 4, F: 5, G: 7, A: 9, B: 11 };
const MIN_NOTES = 4;
const KEYBOARD = { from: 55, to: 81 };  // G3 (fiddle's open G string) to A5
const NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"];

function parseNotes(text) {
  // "D E F# G", "G3 A3", "Bb", "B♭", "^F" (ABC); a "b" straight after a letter is a flat.
  // Returns [{ pc, midi }], midi being null when no octave was given.
  const notes = [];
  for (const m of text.matchAll(/(\^|_|=)?([A-Ga-g])(#|♯|b|♭)?(\d)?/g)) {
    const alter = { "^": 1, "_": -1 }[m[1]] ?? { "#": 1, "♯": 1, b: -1, "♭": -1 }[m[3]] ?? 0;
    const semitone = LETTER_PITCH[m[2].toUpperCase()] + alter;
    notes.push({ pc: (semitone + 12) % 12, midi: m[4] === undefined ? null : 12 * (+m[4] + 1) + semitone });
  }
  return notes;
}

function collapse(values) { return values.filter((v, i) => i === 0 || v !== values[i - 1]); }

// One character per step, so matching is a plain string search.
function foldedSteps(pitchClasses) {
  let out = "";
  for (let i = 1; i < pitchClasses.length; i++) {
    let d = (pitchClasses[i] - pitchClasses[i - 1] + 12) % 12;
    if (d > 6) d -= 12;
    out += String.fromCharCode(70 + d);
  }
  return out;
}
function exactSteps(midis) {
  let out = "";
  for (let i = 1; i < midis.length; i++) out += String.fromCharCode(80 + midis[i] - midis[i - 1]);
  return out;
}

// A tune's melody: the MIDI pitches of its notes in written order (the top note of a
// chord), repeated notes collapsed. Worked out from its ABC on first use, exactly as
// build_site.py's melody_string() does (tests/test_site.py checks every tune), rather
// than shipped in tunes.json.
const KEY_SHARPS = { C: 0, G: 1, D: 2, A: 3, E: 4, B: 5, "F#": 6, "C#": 7, F: -1, Bb: -2, Eb: -3, Ab: -4, Db: -5, Gb: -6, Cb: -7 };
const MODE_SHARPS = { "": 0, maj: 0, ion: 0, lyd: 1, mix: -1, dor: -2, m: -3, min: -3, aeo: -3, phr: -4, loc: -5 };
const ACCIDENTALS = { "^^": 2, "^": 1, "=": 0, "_": -1, "__": -2 };

function keySignature(key) {  // "DMix" -> { F: 1 }: the sharp (+1) or flat (-1) on each letter
  const m = key.trim().match(/^([A-G][#b]?)\s*([A-Za-z]*)/);
  if (!m || !(m[1] in KEY_SHARPS)) return {};
  const n = KEY_SHARPS[m[1]] + (MODE_SHARPS[m[2].slice(0, 3).toLowerCase()] ?? 0);
  const letters = n > 0 ? "FCGDAEB" : "BEADGCF";
  return Object.fromEntries([...letters.slice(0, Math.abs(n))].map((l) => [l, n > 0 ? 1 : -1]));
}

function musicLine(abc) {  // build_site.py's music(): the notes, from K: on, as one line
  const lines = abc.split(/\r?\n/);
  const start = lines.findIndex((line) => line.startsWith("K:"));
  const body = (start < 0 ? [] : lines.slice(start))
    .map((line) => (line.startsWith("K:") ? `[K:${line.slice(2).trim()}]` : /^(%|[A-Za-z]:)/.test(line) ? null : line))
    .filter((line) => line != null).join(" ");
  return body.replace(/\{[^}]*\}|"[^"]*"|![^!\s]*!/g, " ").replace(/\[(?!K:)[A-Za-z]:[^\]]*\]/g, " ");
}

function melodyOf(tune) {
  if (tune.melody) return tune.melody;
  let signature = {};
  const bar = new Map();  // accidentals written earlier in this bar
  const pitch = (acc, letter, marks) => {
    const octave = (letter === letter.toLowerCase() ? 1 : 0) + (marks.match(/'/g)?.length ?? 0) - (marks.match(/,/g)?.length ?? 0);
    const name = letter.toUpperCase();
    if (acc) bar.set(`${name}${octave}`, ACCIDENTALS[acc]);
    const alter = bar.get(`${name}${octave}`) ?? signature[name] ?? 0;
    return 60 + 12 * octave + LETTER_PITCH[name] + alter;
  };
  const notes = [];
  const token = /\[K:([^\]]*)\]|\[([^\]|]*[A-Ga-g][^\]|]*)\]|(\^\^|\^|__|_|=)?([A-Ga-g])([,']*)|(\|)/g;
  for (const m of musicLine(tune.abc).matchAll(token)) {
    if (m[1] != null) { signature = keySignature(m[1]); bar.clear(); }
    else if (m[6]) bar.clear();
    else if (m[2] != null) notes.push(Math.max(...[...m[2].matchAll(/(\^\^|\^|__|_|=)?([A-Ga-g])([,']*)/g)].map((n) => pitch(n[1], n[2], n[3]))));
    else notes.push(pitch(m[3], m[4], m[5]));
  }
  tune.melody = collapse(notes);
  return tune.melody;
}

function tuneSteps(tune) {
  const midis = melodyOf(tune);
  tune.steps ??= {
    exact: exactSteps(collapse(midis)),
    folded: foldedSteps(collapse(midis.map((m) => m % 12))),
  };
  return tune.steps;
}

// Lead-ins (pick-ups) are handled both ways round. A tune's own lead-in is known
// (tune.lead: where its melody starts after it, worked out in build_site.py), so a
// query matches the start of a tune from its first note or from just after its
// lead-in. And the query's first one to three notes may be a lead-in the tune doesn't
// have (or has differently): they're tried without, when enough notes are left.
const LEAD_TRIES = 3;       // query notes that may be dropped as a lead-in
const MIN_AFTER_LEAD = 5;   // notes that must be left after dropping them
// Close matches: tunes without the notes exactly are ranked by how many notes are
// different (wrong, missing or extra; editDistance), counting one more if the
// passage isn't at the start. Those within CLOSE_SHARE of the query's notes are
// listed after the exact matches, and the nearest are added until there are at
// least NEAREST suggestions, so there's always somewhere to look.
const CLOSE_SHARE = 0.25;
const NEAREST = 5;

function editDistance(query, steps, fromStart, octaves) {
  // How many notes must change (be replaced, added or left out) to turn the query
  // into a stretch of the tune: one starting at its first step if fromStart, else
  // anywhere. Worked on steps, so the key doesn't matter: a wrong note in the middle
  // changes two steps but keeps their total (into it and out of it), a missing note
  // is one step where the tune has two with the same total, an extra note the
  // reverse; each of these, and a wrong first or last note (one step), costs 1.
  const base = octaves ? 80 : 70;
  const v = (str, k) => str.charCodeAt(k) - base;
  const same = (a, b) => (octaves ? a === b : (((a - b) % 12) + 12) % 12 === 0);
  const n = steps.length;
  const rows = [Array.from({ length: n + 1 }, (_, j) => (fromStart ? j : 0))];
  for (let i = 1; i <= query.length; i++) {
    const row = [i];
    for (let j = 1; j <= n; j++) {
      let best = Math.min(
        rows[i - 1][j - 1] + (query[i - 1] === steps[j - 1] ? 0 : 1),  // step kept or replaced
        rows[i - 1][j] + 1, row[j - 1] + 1);                           // step added or left out
      const q2 = i >= 2 ? v(query, i - 2) + v(query, i - 1) : null;
      const t2 = j >= 2 ? v(steps, j - 2) + v(steps, j - 1) : null;
      if (q2 !== null && t2 !== null && same(q2, t2)) best = Math.min(best, rows[i - 2][j - 2] + 1);  // a wrong note
      if (t2 !== null && same(v(query, i - 1), t2)) best = Math.min(best, rows[i - 1][j - 2] + 1);     // a note missed
      if (q2 !== null && same(q2, v(steps, j - 1))) best = Math.min(best, rows[i - 2][j - 1] + 1);     // an extra note
      row[j] = best;
    }
    rows.push(row);
  }
  return Math.min(...rows[query.length]);
}

function searchByNotes(text) {
  const notes = parseNotes(text);
  const octaves = notes.length > 0 && notes.every((n) => n.midi !== null);
  const query = octaves ? exactSteps(collapse(notes.map((n) => n.midi))) : foldedSteps(collapse(notes.map((n) => n.pc)));
  if (query.length < MIN_NOTES - 1) return null;
  // The query, then the query without its first 1, 2, 3 notes (a step fewer each).
  const trimmed = [];
  for (let drop = 1; drop <= LEAD_TRIES && query.length - drop >= MIN_AFTER_LEAD - 1; drop++) trimmed.push(query.slice(drop));
  const results = [], close = [];
  for (const tune of state.data.tunes) {
    const steps = tuneSteps(tune)[octaves ? "exact" : "folded"];
    const starts = new Set([0, tune.lead]);  // with and without the tune's lead-in
    const atStart = (q) => [...starts].find((i) => steps.startsWith(q, i));
    let score = 0, where = 0, how = "";
    if (atStart(query) !== undefined) {
      [score, how] = [6, "start"];
    } else if (trimmed.some((q) => atStart(q) !== undefined)) {
      [score, how] = [5, "lead"];
    } else {
      const at = steps.indexOf(query);
      if (at >= 0) [score, where, how] = at <= 2 ? [4, at, "start"] : [3, at, "later"];
    }
    if (score) { results.push({ tune, score, where, how }); continue; }
    // Not a match: how close is it? Near the start (with or without the tune's
    // lead-in) counts a note less than further in.
    const fromStart = Math.min(...[...starts].map((i) =>
      editDistance(query, steps.slice(i, i + query.length + 4), true, octaves)));
    const anywhere = editDistance(query, steps, false, octaves);
    const atStartToo = fromStart <= anywhere + 1;
    const off = atStartToo ? fromStart : anywhere;
    close.push({ tune, score: 0, where: atStartToo ? off : off + 1, close: true, how: "close", off, nearStart: atStartToo });
  }
  const byRank = (a, b) => b.score - a.score || a.where - b.where || (a.tune.title < b.tune.title ? -1 : 1);
  // One entry per tune: its best-matching version.
  const seen = new Set();
  const best = (list) => list.sort(byRank).filter((r) => !seen.has(r.tune.group) && seen.add(r.tune.group));
  const found = best(results);
  const limit = Math.max(1, Math.round((query.length + 1) * CLOSE_SHARE));
  close.sort(byRank);
  const near = best(close.filter((r) => r.where <= limit));
  // Too few? Add the nearest of the rest (labelled as such) up to NEAREST.
  const more = best(close.filter((r) => r.where > limit)).slice(0, Math.max(0, NEAREST - found.length - near.length))
    .map((r) => ({ ...r, how: "nearest" }));
  return [...found, ...near, ...more];
}

// How a result matches, in words: "starts like this", "close: 2 notes different", ….
function matchText({ how, off, nearStart }) {
  if (how === "start") return tr("starts like this", "yn dechrau fel hyn");
  if (how === "lead") return tr("starts like this, after a different lead-in", "yn dechrau fel hyn, ar ôl nodau arwain gwahanol");
  if (how === "later") return tr("later in the tune", "yn nes ymlaen yn yr alaw");
  const word = how === "close" ? tr("close", "agos") : tr("nearest", "agosaf");
  return tr(`${word}: ${off} note${off > 1 ? "s" : ""} different${nearStart ? ", near the start" : ""}`,
    `${word}: ${off} nodyn yn wahanol${nearStart ? ", ger y dechrau" : ""}`);
}

function playNote(midi) {
  // Sound one keyboard note with the same piano (and volume) as the player: short
  // (1/8 of a 2 s bar = 250 ms) with a quick 60 ms fade instead of abcjs's 200 ms,
  // and stopping the previous key's note, so taps don't ring into each other.
  state.keyNote?.stop();
  const sequence = new ABCJS.synth.SynthSequence();
  const track = sequence.addTrack();
  sequence.setInstrument(track, 0);
  sequence.appendNote(track, midi, 1 / 8, 100);
  const synth = new ABCJS.synth.CreateSynth();
  state.keyNote = synth;
  synth.init({ sequence, millisecondsPerMeasure: 2000, options: { ...AUDIO_PARAMS, fadeLength: 60 } })
    .then(() => synth.prime())
    .then(() => { if (state.keyNote === synth) synth.start(); })  // skip if another key came first
    .catch(() => {});
}

function keyboard(onPress) {
  // A piano keyboard from G3 to A5: white keys in a row, black keys laid over them.
  const whites = [], blacks = [];
  for (let midi = KEYBOARD.from; midi <= KEYBOARD.to; midi++) {
    const name = NOTE_NAMES[midi % 12] + (Math.floor(midi / 12) - 1);
    const key = el("button", {
      type: "button", "aria-label": name.replace("#", tr(" sharp ", " llon ")), title: name.replace("#", "♯"), "data-midi": midi,
      onclick: () => { playNote(midi); onPress(name); },
    });
    if (name.includes("#")) {
      key.className = "key black";
      key.style.left = `calc(${whites.length} * var(--white) - var(--black) / 2)`;
      blacks.push(key);
    } else {
      key.className = `key white${name.startsWith("C") ? " c" : ""}`;
      key.append(el("span", {}, name.startsWith("C") ? name : name[0]));  // label C's with their octave
      whites.push(key);
    }
  }
  // In pitch order (G3, G♯3, A3, …), for Tab and screen readers; the black keys are placed over the white ones.
  const keys = [...whites, ...blacks].sort((a, b) => a.dataset.midi - b.dataset.midi);
  return el("div", { class: "piano", role: "group", "aria-label": tr("Piano keyboard, G3 to A5", "Bysellfwrdd piano, G3 i A5"), style: `--whites: ${whites.length}` },
    keys);
}

// ---- Listening: find a tune by playing it to the microphone ------------------------------
// For a fiddle, whistle, flute or guitar played in tune: the pitch of the last ~45 ms
// (two periods of a guitar's low E) is measured on every screen frame (the YIN
// method, below), rounded to the nearest semitone, and a pitch held for LISTEN.hold
// ms counts as a note, so even reel-speed notes (~120 ms) are caught. Notes are
// passed on without their octave ("G A B"), so the search compares them the "any
// octave" way: a note heard an octave out doesn't matter. Nothing is
// recorded or sent anywhere; it all happens on the device.

const LISTEN = {
  hold: 45,          // ms a pitch must last to count as a note
  silence: 2500,     // ms of quiet (after some notes) before it stops by itself
  maxTime: 30000,    // ms before it stops anyway
  minLevel: 0.01,    // RMS below this is silence
  minHz: 70, maxHz: 1800,  // below a guitar's low E (82 Hz) to a whistle's top notes
};

function detectPitch(samples, sampleRate) {
  // YIN (de Cheveigné & Kawahara, 2002): the period is the smallest lag at which
  // the signal looks most like a copy of itself. Returns Hz, or null if unpitched.
  let power = 0;
  for (const x of samples) power += x * x;
  if (Math.sqrt(power / samples.length) < LISTEN.minLevel) return null;
  const minLag = Math.floor(sampleRate / LISTEN.maxHz);
  const maxLag = Math.min(Math.ceil(sampleRate / LISTEN.minHz), samples.length >> 1);
  const width = samples.length - maxLag;
  const d = new Float32Array(maxLag + 1);
  for (let lag = 1; lag <= maxLag; lag++) {
    let sum = 0;
    for (let i = 0; i < width; i++) { const diff = samples[i] - samples[i + lag]; sum += diff * diff; }
    d[lag] = sum;
  }
  // Cumulative mean normalised difference; the first dip below the threshold wins,
  // which avoids picking a multiple of the period (an octave too low).
  const norm = new Float32Array(maxLag + 1).fill(1);
  let running = 0;
  for (let t = 1; t <= maxLag; t++) {
    running += d[t];
    if (running) norm[t] = (d[t] * t) / running;
  }
  let lag = minLag;
  while (lag <= maxLag && norm[lag] >= 0.15) lag++;
  if (lag > maxLag) return null;
  while (lag < maxLag && norm[lag + 1] < norm[lag]) lag++;  // down to the bottom of the dip
  // Parabolic interpolation between neighbouring lags, for a finer period.
  const [a, b, c] = [norm[lag - 1], norm[lag], norm[lag + 1] ?? norm[lag]];
  const shift = (a - c) / (2 * (a - 2 * b + c)) || 0;
  return sampleRate / (lag + Math.max(-1, Math.min(1, shift)));
}

// The microphone's sound reaches the page through an AudioWorklet, every bit of it in
// order however busy the page is (a slow phone, a background tab), and is timed by the
// sound's own clock: a short note at reel speed isn't missed between two screen redraws.
// Where there's no AudioWorklet, the sound is looked at once a redraw instead.
const TAP = `registerProcessor("y-sesiwn-tap", class extends AudioWorkletProcessor {
  process(inputs) { const sound = inputs[0]?.[0]; if (sound) this.port.postMessage(sound.slice(0)); return true; }
});`;
const LISTEN_STEP = 1024;  // samples between two looks (about 21 ms)

async function startListening({ onNote, onHear, onStop }) {
  stopListening();
  if ("audioSession" in navigator) navigator.audioSession.type = "play-and-record";  // iPhone: allow the mic
  // Made before the permission prompt, while the tap that started this still counts
  // as the user's go-ahead for sound; otherwise some browsers start it suspended.
  const context = new AudioContext();
  // Raw sound: phone "voice" processing (echo and noise cancelling, level control) warps notes.
  let stream;
  try {
    stream = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: false, noiseSuppression: false, autoGainControl: false },
    });
  } catch (error) {
    context.close().catch(() => {});
    if ("audioSession" in navigator) navigator.audioSession.type = "playback";
    throw error;
  }
  await context.resume().catch(() => {});
  const source = context.createMediaStreamSource(stream);
  const samples = new Float32Array(2048);  // ~45 ms of sound: two periods of the lowest note
  let candidate = null, since = 0, last = null, lastSound = 0, heardAny = false, frame = 0, tap = null;
  const listening = {
    stop(reason) {
      cancelAnimationFrame(frame);
      if (tap) tap.port.onmessage = null;
      stream.getTracks().forEach((t) => t.stop());
      context.close().catch(() => {});
      if ("audioSession" in navigator) navigator.audioSession.type = "playback";
      if (state.listening === listening) state.listening = null;
      onStop(reason);
    },
  };
  state.listening = listening;
  // One look at the last 45 ms of sound, at time now (ms since listening started).
  const look = (now) => {
    const hz = detectPitch(samples, context.sampleRate);
    const midi = hz ? Math.round(69 + 12 * Math.log2(hz / 440)) : null;
    if (midi !== candidate) { candidate = midi; since = now; }
    if (midi !== null) lastSound = now;
    onHear(midi);
    if (midi !== null && now - since >= LISTEN.hold && midi !== last) {
      last = midi;
      heardAny = true;
      onNote(midi);
    }
    if (midi === null && now - since > 150) last = null;  // a gap: the same note may come again
    if ((heardAny && now - lastSound > LISTEN.silence) || now > LISTEN.maxTime) listening.stop("done");
  };
  try {
    await context.audioWorklet.addModule(URL.createObjectURL(new Blob([TAP], { type: "text/javascript" })));
    tap = new AudioWorkletNode(context, "y-sesiwn-tap");
    const silent = context.createGain();
    silent.gain.value = 0;  // the worklet needs pulling by the speakers to run, but nothing is played
    source.connect(tap).connect(silent).connect(context.destination);
    let total = 0, untilLook = LISTEN_STEP;
    tap.port.onmessage = ({ data }) => {
      samples.copyWithin(0, data.length);
      samples.set(data, samples.length - data.length);
      total += data.length;
      untilLook -= data.length;
      if (untilLook <= 0 && total >= samples.length && state.listening === listening) {
        untilLook += LISTEN_STEP;
        look((total / context.sampleRate) * 1000);
      }
    };
  } catch {
    // No AudioWorklet (older browsers): look at the sound once a screen redraw.
    tap = null;
    const analyser = context.createAnalyser();
    analyser.fftSize = samples.length;
    source.connect(analyser);
    const started = performance.now();
    const tick = (now) => {
      frame = requestAnimationFrame(tick);
      analyser.getFloatTimeDomainData(samples);
      look(now - started);
    };
    frame = requestAnimationFrame(tick);
  }
}

function stopListening() {
  state.listening?.stop("left");
}

const micIcon = () => svg("svg", { viewBox: "0 0 24 24", class: "mic-icon", "aria-hidden": "true" },
  svg("rect", { x: 9, y: 3, width: 6, height: 11, rx: 3, fill: "currentColor" }),
  svg("path", { d: "M5.5 11a6.5 6.5 0 0 0 13 0M12 17.5V21M8.5 21h7", fill: "none", stroke: "currentColor",
    "stroke-width": 1.8, "stroke-linecap": "round" }));
// Play and stop, drawn to sit with the microphone: a rounded triangle and square.
const playIcon = () => svg("svg", { viewBox: "0 0 24 24", class: "play-icon", "aria-hidden": "true" },
  svg("path", { d: "M8 5.5v13l10.5-6.5z", fill: "currentColor", stroke: "currentColor", "stroke-width": 1.8, "stroke-linejoin": "round" }));
const stopIcon = () => svg("svg", { viewBox: "0 0 24 24", class: "stop-icon", "aria-hidden": "true" },
  svg("rect", { x: 6.5, y: 6.5, width: 11, height: 11, rx: 1.5, fill: "currentColor" }));
const canListen = () => !!navigator.mediaDevices?.getUserMedia && "AudioContext" in window;

// ---- The notes page: find a tune by its notes (?page=notes&q=D E F# G A) ----------

const PREVIEWS = 5;  // results shown with their opening bars

// The opening of a tune, as a small score with a play button: its header and first
// line of music (chords hidden). Enough to recognise it by eye or by ear.
function tunePreview(tune) {
  const lines = tune.abc.split("\n");
  const k = lines.findIndex((l) => l.startsWith("K:"));
  const head = lines.slice(0, k + 1).filter((l) => /^[XMLK]:/.test(l));
  const first = lines.slice(k + 1).find((l) => l.trim() && !/^(%|[A-Za-z]:)/.test(l)) ?? "";
  const abc = setTempo([...head, first.replace(/\s*(:\||\|)?\s*$/, " |]")].join("\n"), tune.beat, tune.bpm);
  const paper = el("div", { class: "preview-score hide-chords" });
  const button = el("button", { type: "button", class: "preview-play", "aria-label": tr(`Play the opening of ${tune.base}`, `Chwarae dechrau ${tune.base}`), "data-playing": "false" }, playIcon());
  const box = el("div", { class: "preview" }, button, paper);
  requestAnimationFrame(() => {
    const visualObj = ABCJS.renderAbc(paper, abc, { responsive: "resize", paddingtop: 0, paddingbottom: 0, add_classes: true })[0];
    nameScore(paper);
    // Play plays the opening; while it plays the button is a stop button.
    let playing = null;
    const done = () => {
      playing = null;
      button.replaceChildren(playIcon());
      button.dataset.playing = "false";
      button.setAttribute("aria-label", tr(`Play the opening of ${tune.base}`, `Chwarae dechrau ${tune.base}`));
    };
    button.onclick = () => {
      if (playing) { playing.stop(); return; }
      state.keyNote?.stop();
      const synth = new ABCJS.synth.CreateSynth();
      let timer = 0;
      // Stopped by this button, another preview, a key of the keyboard or leaving the
      // page. (A handle, not the synth's own stop, which abcjs also calls while priming.)
      const preview = { stop() { clearTimeout(timer); synth.stop(); if (playing === preview) done(); } };
      state.keyNote = preview;  // one sound at a time, like the keyboard
      playing = preview;
      button.replaceChildren(stopIcon());
      button.dataset.playing = "true";
      button.setAttribute("aria-label", tr(`Stop the opening of ${tune.base}`, `Stopio dechrau ${tune.base}`));
      synth.init({ visualObj, options: AUDIO_PARAMS }).then(() => synth.prime()).then(({ duration }) => {
        if (state.keyNote !== preview || playing !== preview) return;
        synth.start();
        timer = setTimeout(() => { if (playing === preview) done(); }, duration * 1000 + 200);
      }).catch(() => { if (playing === preview) done(); });
    };
  });
  return box;
}

function renderNotesPage(main) {
  document.title = tr("Find a tune by its notes · Y Sesiwn", "Canfod alaw o'i nodau · Y Sesiwn");
  const autoListen = state.autoListen;
  state.autoListen = false;
  const how = state.lang === "cy" ? [
    [el("strong", {}, "Chwaraewch hi i mi"), " sy'n gwrando ar ffidil, chwisl, ffliwt neu gitâr drwy'ch meicroffon ",
      "ac yn ysgrifennu'r nodau wrth i chi chwarae (dyw e ddim yn gweithio i hymian). Does dim yn cael ei recordio na'i anfon i unman."],
    ["Mae chwech i wyth nodyn fel arfer yn ddigon. Gallwch adael nodau arwain alaw allan, neu eu chwarae; ",
      "y naill ffordd neu'r llall, caiff ei chanfod."],
    ["Mae nodyn anghywir, coll neu ychwanegol yn dal i ganfod yr alaw, ymhlith y cyfatebiaethau ", el("em", {}, "agos"),
      ". Os nad oes dim yn cyfateb, dangosir yr alawon agosaf."],
    ["Mae cyfeiriad y dudalen hon yn cadw'ch nodau, felly gallwch roi nod tudalen ar chwiliad neu ei anfon at rywun."],
  ] : [
    [el("strong", {}, "Play it to me"), " listens to a fiddle, whistle, flute or guitar through your ",
      "microphone and writes down the notes as you play (it doesn't work for humming). Nothing is recorded or sent anywhere."],
    ["Six to eight notes is usually plenty. A tune's lead-in notes can be left out, or played; ",
      "either way it's found."],
    ["A wrong, missing or extra note still finds the tune, among the ", el("em", {}, "close"),
      " matches. If nothing matches, the nearest tunes are shown."],
    ["The address of this page keeps your notes, so you can bookmark a search or send it to someone."],
  ];
  main.replaceChildren(
    el("h1", {}, tr("Find a tune by its notes", "Canfod alaw o'i nodau")),
    el("p", { class: "lead" }, tr("Know how a tune goes but not what it's called? Play its first few notes on your "
      + "instrument, tap them on the keyboard or type them, in any key or octave.",
      "Gwybod sut mae alaw'n mynd ond nid beth yw ei henw? Chwaraewch ei hychydig nodau cyntaf ar eich offeryn, "
      + "tapiwch nhw ar y bysellfwrdd neu teipiwch nhw, mewn unrhyw gywair neu wythfed.")),
    notesSearch({ autoListen }),
    el("section", { class: "guide notes-how" },
      el("h2", {}, tr("How it works", "Sut mae'n gweithio")),
      el("ul", {}, how.map((parts) => el("li", {}, parts)))));
}

function notesSearch({ autoListen = false } = {}) {
  const input = el("input", {
    id: "notes-search", type: "text", autocomplete: "off", spellcheck: "false",
    placeholder: tr("e.g. D E F# G A (any key)", "e.e. D E F# G A (unrhyw gywair)"), "aria-describedby": "notes-help",
    value: new URLSearchParams(location.search).get("q") ?? "",
  });
  const results = el("ol", { class: "notes-results", "aria-live": "polite" });
  const help = el("p", { id: "notes-help", class: "caption" });
  const plural = (n) => `${n} tune${n > 1 ? "s" : ""}`;
  const update = () => {
    // The notes are kept in the address, so a search can be bookmarked or shared.
    const q = input.value.trim();
    history.replaceState(null, "", q ? `?page=notes&q=${encodeURIComponent(q)}` : "?page=notes");
    const found = searchByNotes(input.value);
    if (!found) {
      const n = collapse(parseNotes(input.value).map((x) => x.midi ?? x.pc)).length;
      help.textContent = n
        ? tr(`Keep going: ${MIN_NOTES - n} more note${MIN_NOTES - n > 1 ? "s" : ""}.`, `Daliwch ati: ${MIN_NOTES - n} nodyn arall.`)
        : "";
      results.replaceChildren();
      return;
    }
    const exact = found.filter((r) => !r.close).length;
    const closeOnes = found.filter((r) => r.how === "close").length;
    const many = found.length > 12;
    help.textContent = state.lang === "cy"
      ? exact
        ? `${exact} alaw gyda'r nodau hyn${closeOnes ? `, yna ${closeOnes} sy'n agos atynt` : ""}${many ? " (yn dangos y 12 gorau; ychwanegwch nodau i gyfyngu)" : ""}.`
        : closeOnes
          ? `Dim alawon gyda'r union nodau hyn, ond ${closeOnes} sy'n agos atynt${many ? " (yn dangos y 12 agosaf)" : ""}.`
          : "Dim alawon gyda'r nodau hyn, nac yn agos atynt. Dyma'r agosaf; gwiriwch nodyn neu ddau, neu rhowch gynnig ar lai o nodau."
      : exact
        ? `${plural(exact)} with these notes${closeOnes ? `, then ${plural(closeOnes)} close to them` : ""}${many ? " (showing the best 12; add notes to narrow it down)" : ""}.`
        : closeOnes
          ? `No tunes with exactly these notes, but ${plural(closeOnes)} close to them${many ? " (showing the closest 12)" : ""}.`
          : "No tunes with these notes, or close to them. These are the nearest; check a note or two, or try fewer notes.";
    // No previews while listening: drawing them would hold up the listening and miss
    // notes. They're drawn when it stops.
    const previews = state.listening ? 0 : PREVIEWS;
    results.replaceChildren(...found.slice(0, 12).map((result, i) => {
      const { tune } = result;
      const several = state.groups.get(tune.group).versions.length > 1;
      return el("li", {},
        el("a", { href: tuneUrl(tune.group, tune.version), "data-route": true }, tuneName(tune.group, tune.base)),
        el("span", { class: "caption" }, `${several ? tr(` (version ${tune.version})`, ` (fersiwn ${tune.version})`) : ""} · ${matchText(result)}`),
        i < previews ? tunePreview(tune) : null);
    }));
  };
  input.addEventListener("input", update);
  const press = (name) => { input.value = `${input.value.trimEnd()} ${name}`.trimStart(); update(); };
  const piano = keyboard(press);
  const listenStatus = el("p", { class: "listen-status", "aria-live": "polite", hidden: true });
  const listenButton = el("button", { type: "button", class: "listen", onclick: () => toggleListening() });
  const showListening = (on) => {
    listenButton.replaceChildren(on ? stopIcon() : micIcon(), on ? tr(" Stop listening", " Stopio gwrando") : tr(" Play it to me", " Chwaraewch hi i mi"));
    listenButton.classList.toggle("on", on);
  };
  const light = (midi) => {
    // The heard note's key, or (if it's outside the keyboard) the same note in range.
    piano.querySelectorAll(".heard").forEach((k) => k.classList.remove("heard"));
    if (midi === null) return;
    let m = midi;
    while (m < KEYBOARD.from) m += 12;
    while (m > KEYBOARD.to) m -= 12;
    piano.querySelector(`[data-midi="${m}"]`)?.classList.add("heard");
  };
  const toggleListening = async () => {
    if (state.listening) { state.listening.stop("stopped"); return; }
    input.value = ""; update();
    showListening(true);
    listenStatus.hidden = false;
    listenStatus.textContent = tr("Listening… play the first few notes of the tune on your instrument.",
      "Yn gwrando… chwaraewch ychydig nodau cyntaf yr alaw ar eich offeryn.");
    try {
      await startListening({
        onNote: (midi) => { press(NOTE_NAMES[midi % 12]); },
        onHear: light,
        onStop: (reason) => {
          showListening(false);
          light(null);
          if (reason !== "left") update();  // now with the previews
          listenStatus.textContent = reason === "done" && input.value
            ? tr("Stopped listening. Play it again, or add notes on the keyboard.",
              "Wedi stopio gwrando. Chwaraewch hi eto, neu ychwanegwch nodau ar y bysellfwrdd.") : "";
          listenStatus.hidden = !listenStatus.textContent;
        },
      });
    } catch (error) {
      showListening(false);
      listenStatus.textContent = error.name === "NotAllowedError"
        ? tr("The microphone isn't allowed. Allow it for this site in your browser's settings, then try again.",
          "Dyw'r meicroffon ddim wedi'i ganiatáu. Caniatewch ef i'r wefan hon yng ngosodiadau eich porwr, yna rhowch gynnig arall arni.")
        : tr("Couldn't use the microphone on this device.", "Methu defnyddio'r meicroffon ar y ddyfais hon.");
    }
  };
  showListening(false);
  const edit = el("div", { class: "note-edit" },
    el("button", { type: "button", "aria-label": tr("Delete last note", "Dileu'r nodyn olaf"), onclick: () => {
      input.value = input.value.trimEnd().replace(/\s*\S+$/, ""); update(); } }, tr("Delete", "Dileu")),
    el("button", { type: "button", onclick: () => { input.value = ""; update(); } }, tr("Clear", "Clirio")));
  update();
  // From the home page's "Play it to me": start listening straight away.
  if (autoListen && canListen()) toggleListening();
  return el("section", { class: "notes-search", id: "find-by-notes" },
    el("label", { for: "notes-search", class: "visually-hidden" }, tr("First notes of the tune", "Nodau cyntaf yr alaw")),
    canListen() ? listenButton : null,
    input, el("div", { class: "piano-wrap" }, piano), edit, listenStatus, help, results);
}

// ---- Routing ----------------------------------------------------------------

// A tune's own page: a real one (build_site.py writes it, for link previews and search
// engines), which the app shows like any other.
// A tune's name, marked as Welsh or English so screen readers say it in the right voice
// (whichever language the page is in). The Welsh names are those with a pronunciation in
// pronunciation.json; the rest are English ("Gower Reel").
const nameLang = (group) => (state.data.say?.[group] ? "cy" : "en");
const tuneName = (group, text) => el("span", { lang: nameLang(group) }, text);

function tuneUrl(group, version = 1) {
  return `alaw/${encodeURIComponent(group)}/${version > 1 ? `?v=${version}` : ""}`;
}

// A tune's link with the key chosen on its page, so "the jig in A" can be shared:
// alaw/glandyfi/?key=A (the key by name, in the tune's own mode).
function tuneLink(group, tune, settings) {
  const query = new URLSearchParams();
  if (tune.version > 1) query.set("v", tune.version);
  if (settings?.transpose && tune.key) query.set("key", NOTES[(tune.key.pitch + settings.transpose + 12) % 12]);
  return `alaw/${encodeURIComponent(group.slug)}/${query.size ? `?${query}` : ""}`;
}

// ?key=A (or A#, Bb, Bs for B sharp…): the shift in semitones, nearest way (-5 … +6).
function keyShift(tune, name) {
  const m = /^([A-Ga-g])(#|s|b)?$/.exec(name ?? "");
  if (!m || !tune.key) return null;
  const pc = (LETTER_PITCH[m[1].toUpperCase()] + ({ "#": 1, s: 1, b: -1 }[m[2]] ?? 0) + 12) % 12;
  const up = (pc - tune.key.pitch + 12) % 12;
  return up > 6 ? up - 12 : up;
}

// The page's address within the site (after <base href>), decoded. A link pasted with
// something stuck to its end (a space or non-breaking space, a full stop or bracket from
// the sentence around it: …/alaw/glandyfi/%C2%A0) still opens its page; render() then
// puts the address right.
const ADDRESS_JUNK = /[\s\u00a0\u200b.,;:!?'"’”)\]>]+$/u;
function rawPath() {
  const path = location.pathname.slice(new URL(document.baseURI).pathname.length);
  try { return decodeURIComponent(path); } catch { return path; }
}
const sitePath = () => rawPath().replace(ADDRESS_JUNK, "");

// The tune in the address: alaw/<folder>/, or an older link's ?tune=<folder>.
function addressTune() {
  const match = sitePath().match(/^alaw\/([^/]+)\/?$/);
  return match ? match[1] : new URLSearchParams(location.search).get("tune")?.replace(ADDRESS_JUNK, "") ?? null;
}

// A tune renamed since (moved.json): its new folder name. Anything else as it is.
const movedTo = (slug) => state.moved.get(slug) ?? slug;

// A type's own page, math/<slug>/ (build_site.py, for search engines): the browse
// page with that type chosen.
const typeSlug = (name) => normalize(name).replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");  // build_site.py's slugify
function addressType() {
  const match = sitePath().match(/^math\/([^/]+)\/?$/);
  return match ? state.data.types.find((t) => typeSlug(t.name) === match[1])?.name ?? null : null;
}

// Moving to another page cross-fades the old one into the new (View Transitions, where
// the browser has them), unless the reader's device asks for less motion.
function navigate(url) {
  history.pushState(null, "", url);
  const change = () => { render(); window.scrollTo(0, 0); focusHeading(); };
  if (document.startViewTransition && !matchMedia("(prefers-reduced-motion: reduce)").matches) {
    document.startViewTransition(change);
  } else change();
}

// Phones: the sidebar's links fold away behind the Menu button (style.css); opening a
// page closes it again.
function setMenu(open) {
  document.querySelector(".sidebar").classList.toggle("menu-open", open);
  document.getElementById("menu-button").setAttribute("aria-expanded", String(open));
}

function openRandomTune() {
  if (!state.complete) { state.loaded.then(openRandomTune, () => {}); return; }  // a tune's page, before the rest have come
  const current = addressTune();
  const choices = state.groupList.filter((g) => g.slug !== current);
  navigate(tuneUrl(choices[Math.floor(Math.random() * choices.length)].slug));
}

document.addEventListener("click", (event) => {
  const link = event.target.closest("a[data-route]");
  if (!link || event.metaKey || event.ctrlKey || event.shiftKey || event.button !== 0) return;
  event.preventDefault();
  navigate(link.getAttribute("href"));
});
window.addEventListener("popstate", () => { render(); focusHeading(); });

// After moving to another page, focus goes to its heading, so a screen reader says where
// you are (as it would on a new page) and Tab carries on from the top of it. Some pages
// draw their heading a moment later (fetched guides, the sessions): wait for it.
function focusHeading() {
  const main = document.getElementById("main");
  const focus = () => {
    const h1 = main.querySelector("h1");
    if (!h1) return false;
    h1.tabIndex = -1;
    h1.focus({ preventScroll: true });
    return true;
  };
  if (focus()) return;
  const watch = new MutationObserver(() => { if (focus()) watch.disconnect(); });
  watch.observe(main, { childList: true, subtree: true });
  setTimeout(() => watch.disconnect(), 5000);
}

// "?" lists the keyboard shortcuts (as does the footer's link, on a computer).
function showShortcuts() {
  if (document.querySelector("dialog.shortcuts")) return;
  const keys = (...k) => k.map((x, i) => [i ? " " : "", el("kbd", {}, x)]);
  const rows = [
    [keys("/"), tr("Search for a tune by name", "Chwilio am alaw yn ôl ei henw")],
    [keys(tr("Space", "Bylchwr")), tr("Play or pause the tune (on a tune's page)", "Chwarae neu oedi'r alaw (ar dudalen alaw)")],
    [keys("←", "→"), tr("The tune before or after (in a set)", "Yr alaw o'r blaen neu nesaf (mewn set)")],
    [keys("+", "−", "0"), tr("Zoom in, out, or show all of Wales (on a map; the arrow keys move it)", "Chwyddo i mewn, allan, neu ddangos Cymru gyfan (ar fap; mae'r bysellau saeth yn ei symud)")],
    [keys("Esc"), tr("Close a list or this box; leave full screen", "Cau rhestr neu'r blwch hwn; gadael y sgrin lawn")],
    [keys("?"), tr("This list", "Y rhestr hon")],
  ];
  const dialog = el("dialog", { class: "shortcuts", "aria-labelledby": "shortcuts-title" },
    el("h2", { id: "shortcuts-title" }, tr("Keyboard shortcuts", "Llwybrau byr y bysellfwrdd")),
    el("table", {}, el("tbody", {}, rows.map(([k, what]) => el("tr", {}, el("th", { scope: "row" }, k), el("td", {}, what))))),
    el("p", { class: "caption" }, tr("You can also tap or click a note in the sheet music to play from there.",
      "Gallwch hefyd dapio neu glicio nodyn yn y sgôr i chwarae o'r fan honno.")),
    el("form", { method: "dialog" }, el("button", { class: "primary" }, tr("Close", "Cau"))));
  dialog.addEventListener("close", () => dialog.remove());
  dialog.addEventListener("click", (e) => { if (e.target === dialog) dialog.close(); });
  document.body.append(dialog);
  dialog.showModal();
}
document.addEventListener("keydown", (event) => {
  if (event.key !== "?" || event.ctrlKey || event.metaKey || event.altKey) return;
  if (event.target.closest("input, textarea, select, [contenteditable]")) return;
  event.preventDefault();
  showShortcuts();
});

// "/" jumps to search from anywhere (the big box on the home page, else the sidebar's).
document.addEventListener("keydown", (event) => {
  if (event.key !== "/" || event.ctrlKey || event.metaKey || event.altKey) return;
  if (event.target.closest("input, textarea, select, [contenteditable]")) return;
  event.preventDefault();
  const box = document.getElementById("hero-search") ?? document.getElementById("search-input");
  if (document.body.classList.contains("practice")) setPractice(false);
  box.focus();
});

// Space plays or pauses the tune (hands on the instrument), unless a control has the
// focus: then it's that control's.
document.addEventListener("keydown", (event) => {
  if (event.key !== " " || event.ctrlKey || event.metaKey || event.altKey) return;
  if (event.target.closest("input, textarea, select, button, a, summary, [contenteditable], [role='button'], [tabindex]:not(#main)")) return;
  const play = document.querySelector(".score .abcjs-midi-start");
  if (!play) return;
  event.preventDefault();
  play.click();
});

function render() {
  // Something stuck to the end of the address (see sitePath): take it off.
  if (rawPath() !== sitePath()) history.replaceState(null, "", (encodeURI(sitePath()) || "./") + location.search);
  stopPlayback();
  stopListening();
  state.keyNote?.stop();
  const params = new URLSearchParams(location.search);
  const slug = movedTo(addressTune());
  // A tune's own page starts with only that tune (see start()): anything else waits for the rest.
  if (!state.complete && !state.groups.has(slug) && !state.bySlug.has(slug)) {
    state.loaded.then(render, (error) => {
      document.getElementById("main").replaceChildren(el("p", {}, `${tr("Couldn't load the tunes", "Methu llwytho'r alawon")}: ${error}`));
    });
    return;
  }
  let group = state.groups.get(slug);
  let version = Number(params.get("v")) || 1;
  const file = state.bySlug.get(slug);
  if (!group && file) [group, version] = [state.groups.get(file.group), file.version];  // a version's own folder
  // Older links (?tune=…) and a version's folder move to the tune's own address; an
  // unknown tune (removed, renamed, mistyped) gets a page saying so.
  if (group && (params.has("tune") || !location.pathname.endsWith(`/alaw/${group.slug}/`))) {
    const keep = new URLSearchParams([...params].filter(([name]) => name === "key"));
    history.replaceState(null, "", tuneUrl(group.slug, version) + (keep.size ? `${version > 1 ? "&" : "?"}${keep}` : ""));
  }
  const lost = slug && !group;
  const tune = group ? group.versions.find((v) => v.version === version) ?? group.versions[0] : null;
  const page = params.get("page");
  const guide = PAGES[page] ? page : null;
  const map = page === "map";
  const offline = page === "offline";
  const notes = page === "notes";
  const browse = page === "browse" || addressType() !== null;
  const contact = page === "contact";
  const setPage = page === "set" || params.has("set");
  const setsPage = page === "sets";
  const sessions = /^sesiynau\/?$/.test(sitePath());
  const main = document.getElementById("main");
  // abcjs (the sheet music and playback, 140 KB) isn't needed for the home page, so it
  // isn't loaded before it: a page with music waits for it (see loadAbcjs).
  if ((tune || notes || setPage || page === "add") && !window.ABCJS) {
    loadAbcjs().then(render, () => main.replaceChildren(el("p", {}, tr("Couldn't load the sheet music. Check your connection and reload the page.",
      "Methu llwytho'r gerddoriaeth. Gwiriwch eich cysylltiad ac ail-lwytho'r dudalen."))));
    return;
  }
  if (!tune) setPractice(false);
  main.style.animation = "none"; void main.offsetWidth; main.style.animation = "";  // replay fade-in
  const home = !tune && !lost && !guide && !map && !offline && !notes && !browse && !contact && !setPage && !setsPage && !sessions;
  document.body.dataset.page = home ? "home" : "other";  // the home page has its own search box
  setMenu(false);
  main.lang = state.lang;
  keepAwake(Boolean(tune || setPage));
  if (tune) renderTune(main, group, tune);
  else if (lost) renderNotFound(main, slug);
  else if (guide) renderGuide(main, guide);
  else if (map) renderMap(main);
  else if (offline) renderOffline(main);
  else if (notes) renderNotesPage(main);
  else if (browse) renderBrowse(main);
  else if (contact) renderContact(main);
  else if (setPage) renderSet(main);
  else if (setsPage) renderSets(main);
  else if (sessions) renderSessions(main);
  else renderHome(main);
  countView();
}

// abcjs: in a tune's own page from the start (build_site.py), otherwise fetched when a
// page needs it, or once the first page is shown, so the next is quick.
let abcjsLoading = null;
function loadAbcjs() {
  if (window.ABCJS) return Promise.resolve();
  abcjsLoading ??= new Promise((resolve, reject) => {
    document.head.append(el("script", { src: "static/abcjs/abcjs-basic-min.js", onload: resolve,
      onerror: (e) => { abcjsLoading = null; reject(e); } }));
  });
  return abcjsLoading;
}

// A quiet picture for a page with nothing on it yet: a Welsh instrument (the triple harp,
// crwth or pibgorn) or a lovespoon, over a scrap of carthen.
const emptyArt = (instrument = "harp") => el("div", { class: "empty-art", "aria-hidden": "true" },
  el("img", { src: `static/${instrument}.svg`, alt: "", width: 64, height: 64 }));

// A link to a tune the site doesn't have (any more): the tunes with the nearest names,
// since it has most likely been renamed or merged into another tune's versions.
function renderNotFound(main, slug) {
  document.title = tr("Tune not found · Y Sesiwn", "Alaw heb ei chanfod · Y Sesiwn");
  const words = slug.replace(/-version-\d+$/, "").replace(/-/g, " ");
  const near = search(words).slice(0, 5);
  main.replaceChildren(...[
    el("h1", {}, tr("Tune not found", "Alaw heb ei chanfod")),
    emptyArt("crwth"),
    el("p", { class: "lead" }, tr(`There's no tune at this address (“${slug}”). It may have been renamed, or joined to another tune as one of its versions.`,
      `Does dim alaw yn y cyfeiriad hwn (“${slug}”). Efallai iddi gael enw newydd, neu ei hychwanegu at alaw arall fel un o'i fersiynau.`)),
    near.length ? el("p", {}, tr("Were you looking for:", "Oeddech chi'n chwilio am:")) : null,
    near.length ? el("ul", { class: "not-found" }, near.map((g) => el("li", {}, el("a", { href: tuneUrl(g.slug), "data-route": true }, tuneName(g.slug, g.title))))) : null,
    heroSearch(state.groupList.length),
  ].filter(Boolean));
}

// Phones dim and lock after a minute or so, mid-tune. With music showing (a tune or a
// set) the screen stays on while the page is in front; anywhere else it's let go.
let wakeLock = null;
async function keepAwake(on) {
  state.awake = on;
  if (!on) { wakeLock?.release().catch(() => {}); wakeLock = null; return; }
  if (wakeLock || !navigator.wakeLock || document.visibilityState !== "visible") return;
  try {
    const lock = await navigator.wakeLock.request("screen");
    if (!state.awake || wakeLock) { lock.release().catch(() => {}); return; }  // left the page meanwhile
    wakeLock = lock;
    lock.addEventListener("release", () => { if (wakeLock === lock) wakeLock = null; });
  } catch {}  // not allowed (low battery, a frame): the screen dims as usual
}
document.addEventListener("visibilitychange", () => { if (state.awake) keepAwake(true); });  // let go when hidden

// ---- Home page -----------------------------------------------------------------

// The three instruments of Welsh traditional music, on a scrap of Welsh quilt.
const instruments = (where = "") => el("div", { class: `instruments${where}`, role: "img",
  "aria-label": tr("A Welsh triple harp, a crwth and a pibgorn", "Telyn deires, crwth a phibgorn") },
  ...["harp", "crwth", "pibgorn"].map((name) => el("img", { src: `static/${name}.svg`, alt: "", width: 72, height: 72 })));

function renderHome(main) {
  document.title = "Y Sesiwn";
  const count = state.groupList.length;  // one entry per tune, whatever its number of versions
  main.replaceChildren(...[
    el("div", { class: "home-intro" },
      el("h1", {}, tr("Croeso! Welcome to Y Sesiwn", "Croeso i'r Sesiwn!")),
      el("p", { class: "lead" }, ...tr(
        [el("strong", {}, "Free and open source"), `: sheet music for ${count} Welsh folk tunes, to learn, play and share.`],
        [el("strong", {}, "Am ddim a chod agored"), `: sgorau ${count} o alawon gwerin Cymru, i'w dysgu, eu chwarae a'u rhannu.`])),
      instruments(" at-top")),
    heroSearch(count),
    el("div", { class: "home-actions" },
      el("button", { type: "button", onclick: openRandomTune }, tr("Surprise me", "Alaw ar hap")),  // the search comes first
      el("a", { href: "?page=browse", "data-route": true, class: "button-link" },
        tr(`Browse all ${count} tunes`, `Pori'r ${count} alaw`))),
    recentTunes(),  // nothing yet on a first visit
    notesInvite(),
    upcomingSessions(),
    features(),
    instruments(" at-end"),  // phones: the picture here instead, by the offline card
    offlineCard(),
  ].filter(Boolean));
}

// The last few tunes opened on this device (localStorage), for the home page: at a
// session you often go back to the same ones.
const RECENT = 5;
function recentList() {
  let list;
  try { list = JSON.parse(localStorage.getItem("recent")); } catch { return []; }
  return Array.isArray(list) ? list.filter((r) => typeof r?.group === "string") : [];
}
function rememberTune(group, tune) {
  const list = recentList().filter((r) => r.group !== group.slug);
  list.unshift({ group: group.slug, version: tune.version });
  try { localStorage.setItem("recent", JSON.stringify(list.slice(0, RECENT))); } catch {}
}
function recentTunes() {
  const tunes = recentList().map((r) => {  // a tune may have been renamed…
    const moved = state.moved.has(r.group) && state.bySlug.get(movedTo(r.group));
    return moved ? { group: moved.group, version: moved.version } : r;
  }).filter((r) => state.groups.has(r.group));  // …or removed
  if (!tunes.length) return null;
  return el("p", { class: "recent" }, el("span", { class: "recent-label" }, tr("Recently opened:", "Agorwyd yn ddiweddar:")), " ",
    tunes.map((r, i) => [i ? " · " : "", el("a", { href: tuneUrl(r.group, r.version), "data-route": true }, tuneName(r.group, state.groups.get(r.group).title))]));
}

// ---- Browse page -------------------------------------------------------------------

// Every tune, narrowed down by types and keys. The choice is kept in the address
// (?page=browse&type=Jig&type=Polca&key=D%20major), so "the jigs and polkas in D" can be shared.
function renderBrowse(main) {
  document.title = tr("Browse · Y Sesiwn", "Pori · Y Sesiwn");
  const { types } = state.data;
  const tunes = state.groupList;
  const colour = Object.fromEntries(types.map((t) => [t.name, t.colour]));

  const list = el("ul", { class: "tune-list" });
  const caption = el("p", { class: "caption" });
  const pills = el("div", { class: "pills", role: "group", "aria-label": tr("Tune type", "Math o alaw") });
  const keyPills = el("div", { class: "pills keys", role: "group", "aria-label": tr("Key", "Cywair") });
  // The key a tune is filed under: its first version's, spelled out ("E Dorian").
  const keyOf = (t) => (t.versions[0].key ? `${t.versions[0].key.root} ${t.versions[0].key.modeName}` : null);
  const keyCounts = new Map();
  for (const t of tunes) if (keyOf(t)) keyCounts.set(keyOf(t), (keyCounts.get(keyOf(t)) ?? 0) + 1);
  // Any number of types and keys: nothing chosen lists every tune; clicking a chosen one
  // again takes just that one off. Types add up (the jigs and the polkas), as do keys, and
  // a type and a key together narrow it down (the jigs and polkas in D or G).
  const params = new URLSearchParams(location.search);
  const typeNames = types.map((t) => t.name);
  const chosenTypes = new Set(params.getAll("type").filter((t) => typeNames.includes(t)));
  if (!chosenTypes.size && addressType()) chosenTypes.add(addressType());
  const chosenKeys = new Set(params.getAll("key").filter((k) => keyCounts.has(k)));
  const inOrder = (set, order) => order.filter((x) => set.has(x));  // as the buttons are
  const keyOrder = [...keyCounts].sort((a, b) => b[1] - a[1]).map(([k]) => k);
  const andList = (items, word) => (items.length < 2 ? items.join("") : `${items.slice(0, -1).join(", ")} ${word} ${items.at(-1)}`);
  const show = (first = false) => {
    const url = new URLSearchParams({ page: "browse" });
    for (const t of inOrder(chosenTypes, typeNames)) url.append("type", t);
    for (const k of inOrder(chosenKeys, keyOrder)) url.append("key", k);
    if (!first) history.replaceState(null, "", `?${url}`);  // a type's own page keeps its address at first
    const typeOk = (t) => !chosenTypes.size || chosenTypes.has(t.type);
    const keyOk = (t) => !chosenKeys.size || chosenKeys.has(keyOf(t));
    for (const pill of pills.children) pill.setAttribute("aria-pressed", chosenTypes.has(pill.dataset.type));
    for (const pill of keyPills.children) {
      // Each key's count among the tunes of the chosen types; keys they have none in are greyed out.
      const n = tunes.filter((t) => typeOk(t) && keyOf(t) === pill.dataset.key).length;
      const on = chosenKeys.has(pill.dataset.key);
      pill.setAttribute("aria-pressed", on);
      pill.lastChild.textContent = String(n);
      pill.disabled = n === 0 && !on;
    }
    const listed = tunes.filter((t) => typeOk(t) && keyOk(t));
    const n = listed.length;
    const ts = inOrder(chosenTypes, typeNames).map((name) => types.find((t) => t.name === name));
    const ks = inOrder(chosenKeys, keyOrder);
    if (state.lang === "cy") {
      const what = !ts.length ? "alaw" : ts.length === 1 ? CY_TYPE[ts[0].name] : `alaw (${ts.map((t) => CY_TYPE[t.name]).join(", ")})`;
      caption.textContent = ts.length || ks.length
        ? `${n} ${what}${ks.length ? ` yn ${ks.map(keyLabel).join(" neu ")}` : ""}` : `Y ${tunes.length} alaw i gyd`;
    } else {
      const plural = (t) => (t.name === "Other" && ts.length > 1 ? "other tunes" : t.english);
      const what = n === 1 ? (ts.length === 1 ? ts[0].name.toLowerCase() : "tune")
        : !ts.length ? "tunes" : andList(ts.map(plural), "and");
      caption.textContent = ts.length || ks.length
        ? `${n} ${what}${ks.length ? ` in ${andList(ks, "or")}` : ""}` : `All ${tunes.length} tunes`;
    }
    list.replaceChildren(...listed.map((t) =>
      el("li", { style: `--c: ${colour[t.type]}` },
        el("span", { class: "swatch", title: typeName(t.type) }),
        el("a", { href: tuneUrl(t.slug), "data-route": true }, tuneName(t.slug, t.title)))));
  };
  const toggle = (set, item) => { if (!set.delete(item)) set.add(item); show(); };
  for (const type of types) {
    pills.append(el("button", {
      type: "button", "data-type": type.name, style: `--c: ${type.colour}`,
      onclick: () => toggle(chosenTypes, type.name),
    }, el("span", { class: "swatch" }), `${typeName(type.name)} · ${type.count}`));
  }
  for (const key of keyOrder) {
    keyPills.append(el("button", {
      type: "button", "data-key": key, onclick: () => toggle(chosenKeys, key),
    }, `${keyLabel(key)} ·\u00a0`, el("span", {}, String(keyCounts.get(key)))));  // no-break: flex drops a plain trailing space
  }

  main.replaceChildren(
    el("h1", {}, tr("Browse by type and key", "Pori yn ôl math a chywair")),
    el("p", { class: "lead" }, tr("Pick any types and keys: the jigs and reels in D, say.",
      "Dewiswch unrhyw fathau a chyweiriau: y jigiau yn D, dyweder.")),
    el("p", { class: "pills-label" }, tr("Type", "Math")), pills,
    el("p", { class: "pills-label" }, tr("Key", "Cywair")), keyPills, caption, list,
  );
  show(true);
}

// On the home page, the way into the notes page: "Play it to me" goes there and starts
// listening at once (the tap is still the go-ahead for the microphone and sound).
// One line under the search: finding a tune by its notes, played to the microphone or tapped.
function notesInvite() {
  const notes = (text) => el("a", { href: "?page=notes", "data-route": true }, text);
  return el("p", { class: "notes-invite" }, el("strong", {}, tr("Know the tune but not its name?", "Gwybod yr alaw ond nid ei henw?")), " ",
    ...(canListen() ? [
      el("button", { type: "button", class: "link-button listen-start",
        onclick: () => { state.autoListen = true; navigate("?page=notes"); } }, micIcon(), tr("Play it to me", "Chwaraewch hi i mi")),
      tr(" or ", " neu "), notes(tr("tap the notes", "tapiwch y nodau")),
    ] : [notes(tr("Tap or type the notes", "Tapio neu deipio'r nodau"))]));
}

function features() {
  // A few things worth knowing before opening a tune; the sidebar has the rest.
  const withChords = state.groupList.filter((g) => g.versions.some((v) => v.chords != null)).length;
  const items = state.lang === "cy" ? [
    [["Unrhyw gywair, unrhyw dempo"], ": trawsgyweiriwch alaw i siwtio'ch offeryn neu'ch llais, a gwrandewch arni gyda'r nodau'n goleuo."],
    [["Ymarfer"], ": ailadroddwch yr alaw neu un rhan gan gyflymu bob tro, gyda thablatur ar gyfer mandolin, ffidil neu gitâr."],
    [["Cordiau"], `: cyfeiliant awgrymedig ar gyfer gitâr, piano neu delyn (${withChords} o alawon hyd yma).`],
    [["Setiau"], ": casglwch alawon i'w chwarae gyda'i gilydd, yn eich cyweiriau chi, a'u rhannu fel dolen neu god QR."],
  ] : [
    [["Any key, any tempo"], ": transpose a tune for your instrument or voice, and hear it with the notes lit up."],
    [["Practise"], ": repeat the tune or a part, speeding up each time, with tablature for mandolin, fiddle or guitar."],
    [["Chords"], `: suggested accompaniment for guitar, piano or harp (${withChords} tunes so far).`],
    [["Sets"], ": gather tunes to play together, in your keys, and share them as a link or a QR code."],
  ];
  // [["words"]] is the bold lead-in; plain strings follow it.
  const bold = (part) => Array.isArray(part) ? el("strong", {}, part) : part;
  return el("section", { class: "features" },
    el("h2", { class: "section-heading" }, tr("What you can do", "Beth allwch chi ei wneud")),
    el("ul", {}, items.map((parts) => el("li", {}, parts.map(bold)))));
}

function heroSearch(count) {
  const input = el("input", {
    id: "hero-search", type: "search", autocomplete: "off", spellcheck: "false",
    placeholder: tr(`Search ${count} tunes by name…`, `Chwilio'r ${count} alaw yn ôl enw…`), role: "combobox", "aria-expanded": "false",
    "aria-controls": "hero-suggestions", "aria-autocomplete": "list",
  });
  const list = el("ul", { id: "hero-suggestions", class: "suggestions", role: "listbox", hidden: true });
  // The list below already shows every tune, so only suggest once something is typed.
  attachSearch(input, list, { showAllOnFocus: false });
  return el("div", { class: "search hero-search" },
    el("label", { for: "hero-search", class: "visually-hidden" }, tr("Search tunes by name", "Chwilio am alawon yn ôl enw")),
    input, el("kbd", { class: "shortcut", title: tr("Press / to search", "Pwyswch / i chwilio") }, "/"), list);
}

// ---- Tune page -------------------------------------------------------------------

// The key menu (and a set's keys) say which key, -5 … +6 semitones from the tune's own;
// this says which octave. Of the two ways there, up or down, the one that keeps the
// tune's notes best on the treble stave (B below middle C to the A above it), and if
// both do, the shorter: so D minor to A minor goes up a fifth, not down a fourth, for a
// tune that's already low. The tune's own key never moves.
const STAVE = { low: 59, high: 81 };  // MIDI: B3 … A5

function melodyRange(tune) {
  if (!tune.range) {
    const pitches = melodyOf(tune);
    tune.range = pitches.length ? [Math.min(...pitches), Math.max(...pitches)] : null;
  }
  return tune.range;
}

function semitones(tune, key) {
  if (!key || !melodyRange(tune)) return key;
  const [low, high] = melodyRange(tune);
  const outside = (shift) => Math.max(0, STAVE.low - (low + shift)) + Math.max(0, high + shift - STAVE.high);
  const other = key > 0 ? key - 12 : key + 12;
  return outside(other) < outside(key) ? other : key;
}

function stripFields(abc, fields) {
  // Header fields to leave off the score (abcjs would print them); they stay in the ABC view.
  return abc.split("\n").filter((line) => !new RegExp(`^[${fields}]:`).test(line)).join("\n");
}

// A long credit (C:) on a narrow score would run into the rest of its line: there it's
// split over two lines (abcjs prints each C: line on its own), before "o alaw" (from a
// tune by) or the like, or else at the space nearest the middle.
function shortCredits(abc, layout) {
  if (!layout.staffwidth) return abc;
  const fits = Math.round(layout.staffwidth / 9);  // characters of credit text across the score
  return abc.replace(/^C:(.*)$/gm, (line, text) => {
    text = text.trim();
    if (text.length <= fits) return line;
    const words = text.split(" ");
    const cut = words.findIndex((w, i) => i > 0 && /^(o|gan|from|by|arr\.?)$/i.test(w));
    const at = cut > 0 ? cut : words.reduce((best, _, i) =>
      Math.abs(words.slice(0, i).join(" ").length - text.length / 2) < Math.abs(words.slice(0, best).join(" ").length - text.length / 2) ? i : best, 1);
    return `C:${words.slice(0, at).join(" ")}\nC:${words.slice(at).join(" ")}`;
  });
}

function setTempo(abc, beat, bpm) {
  const tempo = `Q:${beat}=${bpm}`;
  return /^Q:/m.test(abc) ? abc.replace(/^Q:.*$/m, tempo) : abc.replace(/^K:/m, `${tempo}\nK:`);
}

// abcjs names each score "Sheet Music for "<title>"" (its <title> and aria-label), in English.
// about (its key and time, say) is added on, for screen readers: the picture says nothing else.
function nameScore(paper, about = "") {
  const score = paper.querySelector("svg");
  if (!score) return;
  const name = (text) => (state.lang === "cy"
    ? text.replace(/^Sheet Music for /, "Sgôr ").replace(/^Sheet Music$/, "Sgôr") : text) + (about ? `: ${about}` : "");
  const title = score.querySelector("title");
  if (title) title.textContent = name(title.textContent);
  if (score.hasAttribute("aria-label")) score.setAttribute("aria-label", name(score.getAttribute("aria-label")));
}

class Cursor {  // highlights the notes as they play, and keeps playback inside a looped part
  constructor(loop = null) { this.loop = loop; }
  onEvent(event) {
    document.querySelectorAll(".abcjs-note_playing").forEach((n) => n.classList.remove("abcjs-note_playing"));
    if (event) event.elements.flat().forEach((n) => n.classList.add("abcjs-note_playing"));
    if (event && this.loop) this.loop.onEvent(event);
  }
  onFinished() { this.onEvent(null); }
}

// ---- Practice: loop a part, speed up, count-in, click, tablature -------------------------

// A tune's parts (A, B, …) as ranges of its ABC text: a part starts at a repeat sign or
// after a double bar line (as in the chord chart), and runs to the next.
function tuneParts(visualObj) {
  const starts = [0];
  let ended = false;
  for (const line of visualObj.lines) {
    for (const item of line.staff?.[0]?.voices?.[0] ?? []) {
      if (item.el_type !== "bar") continue;
      if ((REPEAT_START.has(item.type) || ended) && !item.startEnding) starts.push(item.startChar);
      ended = PART_END.has(item.type) && !REPEAT_START.has(item.type);
    }
  }
  const unique = [...new Set(starts)].sort((a, b) => a - b);
  // Only ranges with notes in them count (a final |] starts nothing).
  const notes = visualObj.lines.flatMap((l) => l.staff?.[0]?.voices?.[0] ?? []).filter((e) => e.el_type === "note");
  return unique.map((from, i) => ({ from, to: unique[i + 1] ?? Infinity }))
    .filter((p) => notes.some((n) => n.startChar >= p.from && n.startChar < p.to))
    .map((p, i) => ({ ...p, label: String.fromCharCode(65 + i) }));
}

// Repeating the whole tune or one part. The player's own loop brings playback round at
// the end of the tune; for a part, whenever playback reaches a note outside it, it jumps
// to the part's first note, played the way it's written (its repeat included). With
// speedUp, each time round is 5% (of the starting tempo) faster, up to speedTo bpm.
function repeatLoop(controller, part, settings, onSpeed) {
  let jumping = false, inside = false, last = -1;
  const firstNote = () => controller.timer.noteTimings.find((e) => e.type === "event" && e.startChar >= part.from && e.startChar < part.to);
  const cap = () => Math.round((100 * settings.speedTo) / settings.bpm);
  // Faster for the next time round, if speeding up (then, for a part, back to its start).
  const roundAgain = (then = () => {}) => {
    if (settings.speedUp && controller.warp < cap()) {
      const warp = Math.min(cap(), controller.warp + 5);
      onSpeed(warp, cap());
      controller.setWarp(warp).then(then);
    } else {
      then();
    }
  };
  return {
    onEvent(event) {
      if (event.startChar == null) return;  // a count-in click
      if (part.whole) {
        // Round again: playback has gone from late in the tune back to its start.
        const end = controller.timer.noteTimings.at(-1)?.milliseconds ?? 0;
        if (last > end / 2 && event.milliseconds + 1000 < last) roundAgain();
        last = event.milliseconds;
        return;
      }
      const within = event.startChar >= part.from && event.startChar < part.to;
      if (within) { jumping = false; inside = true; return; }
      if (jumping) return;
      jumping = true;
      const seek = () => controller.seek(firstNote().milliseconds / 1000, "seconds");
      if (inside) roundAgain(seek); else seek();
      inside = false;
    },
  };
}

// Whistle fingerings under the stave: the six holes of a tin whistle, top to bottom,
// for each note, and + for the second octave. They're written as six (and a seventh, +)
// lines of lyrics (w:), so abcjs lines them up under the notes, and they follow the key
// menu, since they're worked out from the notes as drawn. low: the whistle's lowest
// note (MIDI), all six holes covered.
const WHISTLES = {
  "whistle-D": { name: "D", low: 62 }, "whistle-C": { name: "C", low: 60 },
  "whistle-G": { name: "G", low: 67 }, "whistle-Bb": { name: "B♭", low: 70 },
};
// Holes for each semitone above the low note, in the first octave (● covered, ○ open,
// ◐ half-covered); the second octave is the same, blown harder.
const FINGERINGS = ["●●●●●●", "●●●●●◐", "●●●●●○", "●●●●◐○", "●●●●○○", "●●●○○○",
  "●●◐○○○", "●●○○○○", "●◐○○○○", "●○○○○○", "○●●○○○", "○○○○○○"];

function whistleFingering(midi, whistle) {
  const n = midi - whistle.low;
  if (n < 0 || n > 23) return null;  // not on this whistle
  return { holes: FINGERINGS[n % 12], high: n >= 12 };
}

function withFingerings(abc, whistle) {
  const lines = abc.split("\n").filter((line) => !/^w:/.test(line));  // a tune's own lyrics would clash
  abc = lines.join("\n");
  const tune = ABCJS.renderAbc("*", abc)[0];
  tune.setUpAudio();  // gives each note its MIDI pitch (midiPitches), key signature and accidentals included
  // Which line of the ABC each note is on, from where it starts in the text.
  const lineStarts = [];
  let at = 0;
  for (const line of lines) { lineStarts.push(at); at += line.length + 1; }
  const lineOf = (char) => { let i = 0; while (i + 1 < lineStarts.length && lineStarts[i + 1] <= char) i++; return i; };
  const perLine = new Map();
  for (const staffLine of tune.lines) {
    for (const note of staffLine.staff?.[0]?.voices?.[0] ?? []) {
      if (note.el_type !== "note" || note.rest) continue;
      const i = lineOf(note.startChar);
      if (!perLine.has(i)) perLine.set(i, []);
      // A tied note's continuation has no pitch of its own (it's one sound), but it does
      // take a lyric's place: leave that place empty so the rest stay under their notes.
      perLine.get(i).push(note.midiPitches?.length
        ? whistleFingering(Math.max(...note.midiPitches.map((m) => m.pitch)), whistle) : "tied");
    }
  }
  const out = ["%%vocalfont Helvetica 9"];
  lines.forEach((line, i) => {
    out.push(line);
    const notes = perLine.get(i);
    if (!notes) return;
    const cell = (f, row) => (f === "tied" ? "*" : f ? f.holes[row] : row === 0 ? "?" : "*");
    for (let row = 0; row < 6; row++) out.push(`w:${notes.map((f) => cell(f, row)).join(" ")}`);
    if (notes.some((f) => f?.high)) out.push(`w:${notes.map((f) => (f?.high ? "+" : "*")).join(" ")}`);
  });
  return out.join("\n");
}

// Swing: playback plays each pair of quavers long-short (SWING% of the pair for the
// first), as hornpipes are played. abcjs's player does it (its swing option), for
// time signatures counted in crotchets only (2/4, 3/4, 4/4, C); not the MIDI file.
const SWING = 62;
const canSwing = (tune) => /^M:\s*(C(?!\|)|[234]\/4)\s*$/m.test(tune.abc);

// Tablature under the stave. Mandolin and fiddle share their tuning (GDAE; the numbers
// are frets, or semitones above the open string).
const TABS = {
  mandolin: { instrument: "mandolin", label: () => tr("Mandolin / fiddle (%T)", "Mandolin / ffidil (%T)") },
  guitar: { instrument: "guitar", label: () => tr("Guitar (%T)", "Gitâr (%T)") },
};

// The click: a woodblock on every felt beat (the one the tempo slider counts), high on
// the first of the bar. abcjs's "drum" pattern is one d per click, then the notes
// (General MIDI 76/77: high/low woodblock) and loudnesses. The count-in is one bar of
// it before the tune; drumOff stops it after that when the click itself is off.
function clickParams(visualObj, tune) {
  const { countIn, click } = state.practice;
  if (!countIn && !click) return {};
  const { num, den } = visualObj.getMeterFraction();
  const [bn, bd] = tune.beat.split("/").map(Number);
  const beats = Math.max(1, Math.round((num / den) / (bn / (bd || 1))));
  const notes = [76, ...Array(beats - 1).fill(77)].join(" ");
  const loud = [110, ...Array(beats - 1).fill(80)].join(" ");
  return { drum: `${"d".repeat(beats)} ${notes} ${loud}`, drumBars: 1, drumIntro: countIn ? 1 : 0, drumOff: !click };
}

function stopPlayback() {
  if (state.synth) { state.synth.destroy(); state.synth = null; }
}

// On a narrow screen a tune's own lines (four bars or so, as in the books) shrink to fit
// it, too small to read; there abcjs lays the music out again in shorter lines, at a
// readable size. Wider screens keep the tune's own line breaks.
// The reader can make the music bigger or smaller (musicSize): it's laid out again in
// shorter or longer lines at that size.
const READABLE = 0.75;  // the music's size on a phone (1 is abcjs's own)
const SIZES = [0.8, 1, 1.25, 1.5, 2];  // the reader's choices, state.musicSize
function scoreLayout(paper) {
  const width = paper.clientWidth;
  const own = width / 740;  // the size of the tune's own lines (740: abcjs's line length)
  const zoom = SIZES[state.musicSize];
  if (!width || (own >= 0.6 && zoom === 1)) return {};
  const staffwidth = Math.round(width / ((own >= 0.6 ? own : READABLE) * zoom) / 20) * 20;
  return { staffwidth, wrap: { minSpacing: 1.8, maxSpacing: 2.7, preferredMeasuresPerLine: Math.max(1, Math.round(staffwidth / 200)) } };
}

// − and + for the music's size: for reading at a distance (a tablet on a music stand)
// or with poor sight. Kept on this device.
function musicSize(redraw) {
  const label = el("span", { class: "label", "aria-hidden": "true" }, tr("Size", "Maint"));
  const button = (step, text, name) => el("button", { type: "button", "aria-label": name, onclick: () => {
    state.musicSize = Math.max(0, Math.min(SIZES.length - 1, state.musicSize + step));
    try { localStorage.setItem("musicSize", state.musicSize); } catch {}
    smaller.disabled = state.musicSize === 0;
    bigger.disabled = state.musicSize === SIZES.length - 1;
    redraw();
  } }, text);
  const smaller = button(-1, "−", tr("Smaller music", "Cerddoriaeth lai"));
  const bigger = button(1, "+", tr("Bigger music", "Cerddoriaeth fwy"));
  smaller.disabled = state.musicSize === 0;
  bigger.disabled = state.musicSize === SIZES.length - 1;
  return el("div", { class: "music-size", role: "group", "aria-label": tr("Size of the music", "Maint y gerddoriaeth") }, label, smaller, bigger);
}

// Laying it out, abcjs measures the music in a 1px svg it leaves on the page, as an
// image without a name: screen readers can skip it.
function hideMeasuring() {
  document.querySelectorAll("body > svg[role='img']").forEach((s) => s.setAttribute("aria-hidden", "true"));
}

// Tapping (or clicking) a note plays the tune from there: to practise a passage, or find
// your place. A note in a repeated part starts from its first time round.
async function playFrom(abcElem) {
  const ms = [abcElem.currentTrackMilliseconds ?? []].flat()[0];
  const player = state.synth;
  if (ms == null || !player) return;
  if (!player.isStarted) await player.play();
  player.seek(ms / 1000, "seconds");
}

function drawScore(tune, paper, audio, chart, onSpeed = () => {}) {
  stopPlayback();
  const { transpose, bpm } = state.settings.get(tune.slug);
  // S:, Z:, B: (book), N: (notes), A: (area), H: (history) and R: (the tune type) are in
  // the Details box, so leave them off the score; the version tabs say which version it is.
  let abc = setTempo(stripFields(tune.abc, "SZBNAHR"), tune.beat, bpm).replace(/^(T:.*) \(version \d+\)$/m, "$1");
  if (transpose) {
    // strTranspose needs the whole array renderAbc returns, not its first tune.
    abc = ABCJS.strTranspose(abc, ABCJS.renderAbc("*", abc), semitones(tune, transpose));
  }
  const tab = TABS[state.practice.tab];
  const whistle = WHISTLES[state.practice.tab];
  if (whistle) abc = withFingerings(abc, whistle);
  const layout = scoreLayout(paper);
  paper.dataset.layout = JSON.stringify(layout);
  abc = shortCredits(abc, layout);
  const visualObj = ABCJS.renderAbc(paper, accompaniment(abc, state.chords.play === "both"),
    { responsive: "resize", add_classes: true, paddingtop: 0, ...layout, ...(tab ? { tablature: [{ ...tab, label: tab.label() }] } : {}),
      selectTypes: ["note"], clickListener: playFrom })[0];
  // abcjs makes each clickable note a Tab stop: hundreds, between the player and the rest
  // of the page. Keyboards have the space bar to play instead.
  paper.querySelectorAll("svg [tabindex]").forEach((n) => n.removeAttribute("tabindex"));
  hideMeasuring();
  const { num, den } = visualObj.getMeterFraction();
  nameScore(paper, [
    tune.key && `${NOTES[(tune.key.pitch + transpose + 12) % 12]} ${modeName(tune.key.modeName)}`,
    num && tr(`${num}/${den} time`, `amser ${num}/${den}`),
  ].filter(Boolean).join(", "));
  // Chords are always drawn (so playback has them), and hidden unless asked for.
  paper.classList.toggle("hide-chords", !state.chords.onScore);
  if (chart) {
    chart.replaceChildren(chordChart(visualObj));
    if (tune.key) {  // printed above the chart (print-only)
      const { pitch } = tune.key;
      chart.parentElement.querySelector(".print-key").textContent = `${tr("Key", "Cywair")}: ${NOTES[(pitch + transpose + 12) % 12]} ${modeName(tune.key.modeName)}`;
    }
  }
  const audioParams = { ...AUDIO_PARAMS, chordsOff: state.chords.play === "tune", voicesOff: state.chords.play === "chords",
    ...(state.settings.get(tune.slug).swing ? { swing: SWING } : {}),
    ...clickParams(visualObj, tune) };
  const settings = state.settings.get(tune.slug);
  const parts = tuneParts(visualObj);
  // The Repeat menu: -2 off, -1 the whole tune, 0… a part.
  const part = settings.loop === -1 ? { from: 0, to: Infinity, whole: true } : parts[settings.loop];

  audio.replaceChildren();
  if (!ABCJS.synth.supportsAudio()) {
    audio.textContent = tr("Audio is not supported in this browser.", "Dyw'r porwr hwn ddim yn gallu chwarae sain.");
    return { parts };
  }
  const controller = new ABCJS.synth.SynthController();
  const cursor = new Cursor();
  controller.load(audio, cursor, {
    displayLoop: false, displayRestart: true, displayPlay: true, displayProgress: true,
  });
  // load() doesn't pass abcjs's title options on, so set them here (its own say "Click to …").
  for (const [button, title] of [["reset", tr("Back to the start", "Yn ôl i'r dechrau")],
    ["start", tr("Play / pause (space bar)", "Chwarae / oedi (bylchwr)")], ["progress-background", tr("Move to another point in the tune", "Symud i fan arall yn yr alaw")]]) {
    audio.querySelector(`.abcjs-midi-${button}`)?.setAttribute("title", title);
    audio.querySelector(`.abcjs-midi-${button}`)?.setAttribute("aria-label", title);
  }
  controller.setTune(visualObj, false, audioParams);
  state.synth = controller;
  // setWarp (the speed-up) also updates abcjs's own tempo box, which isn't shown.
  if (controller.control) controller.control.setWarp = () => {};
  if (part) {
    // The player's own loop brings playback round again after the last part.
    cursor.loop = repeatLoop(controller, part, settings, onSpeed);
    if (!controller.isLooping) controller.toggleLoop();
  }
  // Fetch and decode this tune's notes now, so pressing play doesn't wait. The
  // audio stays paused until play is clicked; abcjs shares the decoded notes.
  new ABCJS.synth.CreateSynth().init({ visualObj, options: audioParams }).catch(() => {});
  return { parts };
}

// ---- Chord chart -------------------------------------------------------------------
// Chord symbols in the ABC ("G"d2 cd) are shown as a chart for accompanists: one
// cell per bar, four bars to a row, each part of the tune starting a new row. It's made from the drawn tune, so it
// follows the key drop-down. Within a bar, each chord takes up as much room as it
// lasts (| G  D | is G on beat 1 and D on beat 3). A bar that doesn't start with a
// chord of its own begins with the one still sounding, shown faintly; a pick-up
// bar without a chord is left out.

const REPEAT_START = new Set(["bar_left_repeat", "bar_dbl_repeat"]);  // drawn as |: and :| by style.css
const REPEAT_END = new Set(["bar_right_repeat", "bar_dbl_repeat"]);
const PART_END = new Set([...REPEAT_END, "bar_thin_thin", "bar_thin_thick"]);  // :| || |]

// How the chords are played. abcjs already voices them below most melodies (about
// A2-D4), but three piano notes at once drown the tune, so with the tune they're
// played more quietly than abcjs's default (chords 48, bass 64, out of 127; the
// melody plays at 85-105). On their own ("Chords only") they keep the default. abcjs's default for 6/8 is "boom · chick boom · chick" (bass, gap,
// chord), which sounds like a waltz in two. Guitars and bodhráns drive a jig with
// every quaver, "Down up down, Down up down": here each beat starts with the bass
// and the full chord (b), the middle quaver is a single light chord note (I), and
// the last quaver the full chord again (c). A tune's own %%MIDI lines win.
const CHORD_VOLUME = 32;
const BASS_VOLUME = 50;
const STRUMS = { "6/8": "bIcbIc", "9/8": "bIcbIcbIc", "12/8": "bIcbIcbIcbIc" };

function accompaniment(abc, withTune) {
  const lines = [];
  const has = (name) => new RegExp(`^%%MIDI\\s+${name}`, "m").test(abc);
  if (withTune && !has("chordvol")) lines.push(`%%MIDI chordvol ${CHORD_VOLUME}`);
  if (withTune && !has("bassvol")) lines.push(`%%MIDI bassvol ${BASS_VOLUME}`);
  const strum = STRUMS[abc.match(/^M:\s*(\S+)/m)?.[1]];
  if (strum && !has("gchord")) lines.push(`%%MIDI gchord ${strum}`);
  // Nothing to add: leave it as it is (an empty line before K: would end the tune).
  return lines.length ? abc.replace(/^K:/m, `${lines.join("\n")}\nK:`) : abc;
}

function chordChart(visualObj) {
  const { num, den } = visualObj.getMeterFraction();
  // Every bar of the tune, in order, with its chords and where each starts.
  const bars = [];
  let bar = { chords: [], length: 0 };
  let tuplet = 1;  // a triplet's notes last 2/3 of their written length
  for (const line of visualObj.lines) {
    for (const item of line.staff?.[0]?.voices?.[0] ?? []) {
      if (item.el_type === "note") {
        if (item.startTriplet) tuplet = item.tripletMultiplier ?? 1;
        for (const chord of item.chord ?? []) {
          // A second chord on the same note (rare) just joins the first.
          if (chord.position && chord.position !== "default") continue;
          const last = bar.chords.at(-1);
          if (last && last.at === bar.length) last.name += ` ${chord.name}`;
          else bar.chords.push({ name: chord.name, at: bar.length });
        }
        bar.length += (item.duration ?? 0) * tuplet;
        if (item.endTriplet) tuplet = 1;
      } else if (item.el_type === "bar") {
        if (bar.length) { bar.end = item.type; bars.push(bar); bar = { chords: [], length: 0 }; }
        bar.start = item.type;
        if (item.startEnding) bar.ending = item.startEnding;
      }
    }
  }
  if (bar.length) bars.push(bar);

  // One cell per bar, grouped into the tune's parts (a part starts at a repeat sign
  // or after a double bar line; a second-time ending stays with its part).
  const parts = [[]];
  let held = null, carry = null, partEnded = false;
  for (const b of bars) {
    if (carry) { if (!REPEAT_START.has(b.start)) b.start = carry.start; b.ending ??= carry.ending; carry = null; }
    if ((REPEAT_START.has(b.start) || partEnded) && !b.ending && parts.at(-1).length) parts.push([]);
    partEnded = PART_END.has(b.end);
    // A pick-up (a short bar leading into the next, without a chord) is left out;
    // its repeat sign or ending goes on the next bar. A short bar that closes a part
    // (the tune's last half-bar, say) stays.
    if (!b.chords.length && (held === null || (b.length < num / den - 1e-6 && !PART_END.has(b.end)))) {
      carry = b;
      continue;
    }
    const classes = ["bar",
      REPEAT_START.has(b.start) ? "repeat-start" : null, REPEAT_END.has(b.end) ? "repeat-end" : null];
    // Each chord gets the share of the bar it lasts for, in percent (fr values that add
    // up to less than 1 would leave part of the bar empty).
    const shares = b.chords.map((c, i) => ({ name: c.name, from: c.at, to: b.chords[i + 1]?.at ?? b.length }));
    if (!shares.length || shares[0].from > 1e-6) shares.unshift({ name: held, from: 0, to: shares[0]?.from ?? b.length, held: true });
    parts.at(-1).push(Object.assign(el("span", { class: classes.filter(Boolean).join(" ") },
      b.ending ? el("sup", {}, `${b.ending}.`) : null,
      el("span", { class: "beats", style: `grid-template-columns: ${shares.map((c) => `${(100 * (c.to - c.from)) / b.length}fr`).join(" ")}` },
        shares.map((c) => el("span", { class: c.held ? "held" : null }, c.name)))),
      { ending: b.ending, chords: shares.map((c) => `${c.name}:${(c.to - c.from) / b.length}`).join(" ") }));
    held = b.chords.at(-1)?.name ?? held;
  }

  // Rows of 4 bars (the usual phrase length), or 3 or 5 for a part that divides into
  // those but not 4; each part starts a new row. A second-time ending goes on a row
  // of its own, under the first-time ending, as in a printed chord chart.
  const rows = [];
  for (let cells of parts.filter((p) => p.length)) {
    let second = cells.findIndex((c) => c.ending && c.ending !== "1");
    // First- and second-time endings with the same chords (the melody differs, the
    // chords don't): one plain repeat is all a player needs.
    const first = cells.findIndex((c) => c.ending === "1");
    if (first >= 0 && second > first) {
      const one = cells.slice(first, second), two = cells.slice(second);
      if (one.length === two.length && one.every((c, i) => c.chords === two[i].chords)) {
        one[0].querySelector("sup")?.remove();
        one[0].ending = undefined;
        cells = cells.slice(0, second);
        second = -1;
      }
    }
    const main = second < 0 ? cells : cells.slice(0, second);
    const n = main.length % 4 === 0 ? 4 : main.length % 3 === 0 ? 3 : main.length % 5 === 0 ? 5 : 4;
    for (let i = 0; i < main.length; i += n) rows.push(el("div", { class: "chart-row" }, main.slice(i, i + n)));
    if (second >= 0) {
      const first = cells.findIndex((c) => c.ending === "1");
      const indent = first >= 0 ? first % n : 0;
      rows.push(el("div", { class: `chart-row${indent ? " indented" : ""}` },
        Array.from({ length: indent }, () => el("span", { class: "bar spacer", "aria-hidden": "true" })),
        cells.slice(second)));
    }
  }
  // As many columns as the longest row, so bars line up down the chart.
  const columns = Math.max(1, ...rows.map((row) => row.children.length));
  return el("div", { class: "chart", style: `--columns: ${columns}` }, rows);
}

// Where a tune's chords come from (its %%chords line), in Welsh.
const CY_CHORD_SOURCES = { "From the Alawon Cymru score": "O sgôr Alawon Cymru",
  "From the setting on The Session": "O'r gosodiad ar The Session", "Supplied by Neil Browning": "Gan Neil Browning" };

function chordCard(tune, redraw) {
  if (tune.chords == null) return null;
  const showOnScore = el("label", { class: "switch" },
    el("input", { type: "checkbox", checked: state.chords.onScore,
      onchange: (e) => { state.chords.onScore = e.target.checked; redraw(); } }), tr("Show on the sheet music", "Dangos ar y sgôr"));
  return el("section", { class: "card chords" },
    el("h2", {}, tr("Suggested chords", "Cordiau awgrymedig")),
    el("p", { class: "print-key" }),
    el("div", { class: "chart-box" }),
    el("div", { class: "chord-controls" }, showOnScore),
    el("p", { class: "caption" },
      tune.chords ? `${tr(tune.chords, CY_CHORD_SOURCES[tune.chords] ?? tune.chords)}. ` : "",
      tr("One way of accompanying it: use your ear, and your own.", "Un ffordd o gyfeilio iddi: defnyddiwch eich clust, a'ch syniadau eich hun.")));
}

// What the player plays, for a tune with chords: under the player, where it's used.
function chordPlayback(tune, redraw) {
  if (tune.chords == null) return null;
  const playback = el("div", { class: "segmented", role: "radiogroup", "aria-label": tr("Playback", "Chwarae") },
    [["tune", tr("Tune only", "Yr alaw yn unig")], ["both", tr("Tune and chords", "Alaw a chordiau")],
      ["chords", tr("Chords only", "Cordiau yn unig")]].map(([value, label]) =>
      el("label", {},
        el("input", { type: "radio", name: "chord-playback", value, checked: state.chords.play === value,
          onchange: () => { state.chords.play = value; redraw(); } }),
        el("span", {}, label))));
  return el("div", { class: "playback" }, el("span", { class: "label" }, tr("Play", "Chwarae")), playback);
}

// Printing: the sheet music, in the key chosen on the page. A tune with chords
// can also be printed with them above the stave, or as just its chord chart;
// body[data-print] tells the print styles (style.css) which, until it's printed.
function printAs(mode, paper) {
  document.body.dataset.print = mode;
  paper.classList.toggle("hide-chords", mode !== "with-chords");
  window.addEventListener("afterprint", () => {
    delete document.body.dataset.print;
    paper.classList.toggle("hide-chords", !state.chords.onScore);
  }, { once: true });
  window.print();
}

// A file for the reader to keep: made in the page, nothing is fetched.
function download(name, type, data) {
  const url = URL.createObjectURL(new Blob([data], { type }));
  const a = el("a", { href: url, download: name });
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

// Print (the sheet music; with chords or just the chart, for a tune that has them) or
// save the tune as an ABC or MIDI file, in the key (and for MIDI the tempo and Play
// choice) set on the page.
function printButton(tune, paper, settings) {
  const transposed = (abc) => (settings.transpose
    ? ABCJS.strTranspose(abc, ABCJS.renderAbc("*", abc), semitones(tune, settings.transpose)) : abc);
  const fileName = (ext) => {
    const key = settings.transpose && tune.key ? `-in-${NOTES[(tune.key.pitch + settings.transpose + 12) % 12].replace("#", "sharp")}` : "";
    return `${tune.slug}${key}.${ext}`;
  };
  const saveAbc = () => download(fileName("abc"), "text/vnd.abc", transposed(tune.abc));
  const saveMidi = () => {
    const abc = transposed(setTempo(stripFields(tune.abc, "SZBNAH"), tune.beat, settings.bpm));
    const [bytes] = ABCJS.synth.getMidiFile(accompaniment(abc, state.chords.play === "both"), {
      midiOutputType: "binary", ...AUDIO_PARAMS,
      chordsOff: tune.chords == null || state.chords.play === "tune", voicesOff: tune.chords != null && state.chords.play === "chords" });
    download(fileName("mid"), "audio/midi", bytes);
  };
  const items = [["music", tr("Print the sheet music", "Argraffu'r sgôr")]];
  if (tune.chords != null) {
    items.push(["with-chords", tr("Print with chords", "Argraffu gyda chordiau")], ["chart", tr("Print the chord chart", "Argraffu'r siart cordiau")]);
  }
  const menu = el("div", { class: "print-menu", role: "menu", hidden: true },
    items.map(([mode, label]) =>
      el("button", { type: "button", role: "menuitem", onclick: () => { menu.hidden = true; printAs(mode, paper); } }, label)),
    el("button", { type: "button", role: "menuitem", class: "menu-sep", onclick: () => { menu.hidden = true; saveAbc(); } },
      tr("Save as ABC", "Cadw fel ABC")),
    el("button", { type: "button", role: "menuitem", onclick: () => { menu.hidden = true; saveMidi(); } },
      tr("Save as MIDI", "Cadw fel MIDI")));
  const toggle = el("button", { type: "button", "aria-haspopup": "menu", "aria-expanded": "false", onclick: () => {
    menu.hidden = !menu.hidden;
    toggle.setAttribute("aria-expanded", String(!menu.hidden));
  } }, tr("Print / save", "Argraffu / cadw"), el("span", { class: "chevron", "aria-hidden": "true" }));
  // Clicking anywhere else closes it (and once the page has gone, stop listening).
  const close = (e) => {
    if (!wrap.isConnected) document.removeEventListener("pointerdown", close);
    else if (!wrap.contains(e.target)) { menu.hidden = true; toggle.setAttribute("aria-expanded", "false"); }
  };
  document.addEventListener("pointerdown", close);
  const wrap = el("div", { class: "print-wrap" }, toggle, menu);
  return wrap;
}

// The Details box's labels (from build_site.py's HEADER_LABELS), in Welsh.
const CY_DETAILS = { "Tune type": "Math o alaw", Key: "Cywair", "Time signature": "Amseriad",
  "Composer / arranger": "Cyfansoddwr / trefnydd", Area: "Ardal", Origin: "Tarddiad", Book: "Llyfr",
  Discography: "Disgograffi", History: "Hanes", Source: "Ffynhonnell" };

function detailValue(label, value) {
  if (label === "Key") return keyLabel(value);
  // A source that's a web address is a link, and any words after it (who added the tune
  // there) stay text; other sources (a recording, a book) are just text.
  const url = label === "Source" && value.match(/^(https?:\/\/\S+)(.*)$/);
  if (url) return [el("a", { href: url[1], target: "_blank", rel: "noopener" }, url[1]), url[2]];
  return value;
}

// The key someone plays each tune in, kept on this device (a whistle player who always
// plays Glandyfi in A): { tune folder: semitones from the written key }.
function savedKeys() {
  try {
    const keys = JSON.parse(localStorage.getItem("keys"));
    if (!keys || typeof keys !== "object") return {};
    // A tune renamed since its key was kept: under its new name (saved so next time it changes).
    const out = {};
    for (const [slug, shift] of Object.entries(keys)) if (!state.moved.has(slug)) out[slug] = shift;
    for (const [slug, shift] of Object.entries(keys)) if (state.moved.has(slug)) out[movedTo(slug)] ??= shift;
    return out;
  } catch { return {}; }
}
function saveKey(slug, shift) {
  try {
    const keys = savedKeys();
    if (shift) keys[slug] = shift; else delete keys[slug];
    localStorage.setItem("keys", JSON.stringify(keys));
  } catch {}
}

function renderTune(main, group, tune) {
  document.title = `${group.title} · Y Sesiwn`;
  rememberTune(group, tune);
  if (!state.settings.has(tune.slug)) {
    const usual = savedKeys()[tune.slug];
    state.settings.set(tune.slug, { transpose: Number.isInteger(usual) && usual >= -5 && usual <= 6 ? usual : 0, bpm: tune.bpm, loop: -2, speedUp: false, speedTo: tune.bpm,
      swing: canSwing(tune) && tune.type === "Pibddawns" });  // hornpipes are played swung
  }
  const settings = state.settings.get(tune.slug);
  // A shared link's key (?key=A)…
  const shift = keyShift(tune, new URLSearchParams(location.search).get("key"));
  if (shift !== null) settings.transpose = shift;
  // …and the address follows the page's key, so it can be copied as it is.
  const showInAddress = () => history.replaceState(null, "", tuneLink(group, tune, settings));
  showInAddress();  // a key chosen earlier (this visit) shows in the address too

  const paper = el("div");
  const audio = el("div", { class: "audio" });
  const chords = chordCard(tune, () => redraw());
  const speedNote = el("span", { class: "caption speed-note", "aria-live": "polite" });
  // Speeding up: how far there is to go, then a "da iawn" (well done) when the tune or
  // part has been worked up to speed, with a strip of carthen woven in under it.
  const onSpeed = (warp, cap) => {
    const bpm = Math.round((settings.bpm * warp) / 100), goal = settings.speedTo;
    const arrived = warp >= cap;
    speedNote.classList.toggle("arrived", arrived);
    speedNote.replaceChildren(arrived
      ? tr(`Reached ${bpm} bpm. `, `Wedi cyrraedd ${bpm} curiad y funud. `)
      : tr(`now ${bpm} of ${goal} bpm`, `nawr ${bpm} o ${goal} curiad y funud`));
    if (arrived) speedNote.append(el("strong", { lang: "cy" }, "Da iawn!"));
  };
  // Before it starts: a "to" no faster than the tempo has nothing to speed up to.
  const speedHint = () => {
    speedNote.classList.remove("arrived");
    speedNote.textContent = settings.speedUp && settings.loop >= -1 && settings.speedTo <= settings.bpm
      ? tr(`To speed up, start slower (the tempo above) or set a faster “to”.`, `I gyflymu, dechreuwch yn arafach (y tempo uchod) neu gosodwch “i” cyflymach.`)
      : "";
  };
  let drawn = { parts: [] };
  // Drawing it again (a new tempo or key, a phone turned on its side) makes a new player:
  // if the tune was playing, it carries on from the same point in it.
  const redraw = () => {
    speedHint();
    const playingAt = state.synth?.isStarted ? state.synth.percent ?? 0 : null;
    drawn = drawScore(tune, paper, audio, chords?.querySelector(".chart-box"), onSpeed);
    const player = state.synth;
    if (playingAt !== null && player) {
      player.play().then(() => { if (state.synth === player && player.isStarted) player.seek(playingAt); }).catch(() => {});
    }
  };

  const controls = el("div", { class: "controls" });
  if (tune.key) {
    const { pitch, root } = tune.key;
    const mode = modeName(tune.key.modeName);
    const usual = el("span", { class: "caption usual-key" });
    const showUsual = () => {
      usual.textContent = settings.transpose && savedKeys()[tune.slug] === settings.transpose
        ? tr(" · your usual key on this device", " · eich cywair arferol ar y ddyfais hon") : "";
    };
    const select = el("select", { id: "key-select", onchange: (e) => {
      settings.transpose = +e.target.value;
      saveKey(tune.slug, settings.transpose);
      showUsual(); showInAddress(); redraw();
    } });
    for (let shift = -5; shift <= 6; shift++) {  // semitones, nearest direction
      const label = shift === 0 ? `${root} ${mode} ${tr("(original)", "(gwreiddiol)")}` : `${NOTES[(pitch + shift + 12) % 12]} ${mode}`;
      select.append(el("option", { value: shift, selected: shift === settings.transpose }, label));
    }
    showUsual();
    controls.append(el("div", { class: "control" }, el("label", { for: "key-select" }, tr("Key", "Cywair"), usual), select));
  }
  const tempoLabel = el("label", { for: "tempo" });
  const speedFrom = el("span");
  const showTempo = () => {
    tempoLabel.textContent = tr(`Tempo: ${settings.bpm} bpm (${tune.beatName} beats)`,
      `Tempo: ${settings.bpm} curiad y funud (curiad ${CY_BEATS[tune.beatName] ?? tune.beatName})`);
    speedFrom.textContent = String(settings.bpm);
  };
  showTempo();
  const practice = el("button", { type: "button", class: "practice-toggle", onclick: () => setPractice(!document.body.classList.contains("practice")) });
  practice.textContent = practiceLabel(document.body.classList.contains("practice"));
  controls.append(...[el("div", { class: "control tempo" }, tempoLabel,
    el("input", {
      id: "tempo", type: "range", min: 30, max: 200, value: settings.bpm,
      oninput: (e) => { settings.bpm = +e.target.value; showTempo(); },
      onchange: redraw,
    })),
    // How the music is shown, at the end of the row: its size, and full screen.
    el("div", { class: "view-tools" }, musicSize(redraw), practice)]);
  // Under the music: taking it with you (sharing, printing, saving, a set).
  const actions = el("div", { class: "tune-actions", role: "group", "aria-label": tr("Take it with you", "Mynd â hi gyda chi") },
    shareButton(group.title, () => `https://ysesiwn.cymru/${tuneLink(group, tune, settings)}`),
    printButton(tune, paper, settings), qrButton(group, tune, settings), addToSetButton(tune, settings));

  const shownElsewhere = new Set(["Key", "Composer / arranger"]);  // the key menu; the score's credit
  const details = el("dl", {}, tune.details.filter(([label]) => !shownElsewhere.has(label)).map(([label, value]) =>
    [el("dt", {}, tr(label, CY_DETAILS[label] ?? label)), el("dd", {}, detailValue(label, value))]));
  // What the Welsh credit words mean (trefniant = arranged by, …), for English readers.
  const gloss = tune.gloss.length && state.lang !== "cy"
    ? el("p", { class: "caption" }, tune.gloss.flatMap(([word, meaning], i) =>
        [i ? " · " : "", el("em", {}, word), ` = ${meaning}`]))
    : null;

  const versions = group.versions.length > 1
    ? el("nav", { class: "versions", "aria-label": tr("Versions of this tune", "Fersiynau'r alaw hon") }, group.versions.map((v) =>
        el("a", {
          href: tuneUrl(group.slug, v.version), "data-route": true,
          class: v === tune ? "active" : null, "aria-current": v === tune ? "page" : null,
        }, el("span", {}, tr(`Version ${v.version}`, `Fersiwn ${v.version}`)), v.source ? el("small", {}, v.source) : null)))
    : null;

  // The practice tools, in three lines: repeat (and speed up each time round, from the
  // tempo to a faster one); count-in, click and swing; tablature.
  const loopSelect = el("select", { id: "loop-select", onchange: (e) => { settings.loop = +e.target.value; redraw(); } });
  const toggle = (label, checked, onchange, cls, title) => el("label", { class: `switch${cls ? ` ${cls}` : ""}`, title },
    el("input", { type: "checkbox", checked, onchange: (e) => { onchange(e.target.checked); redraw(); } }), label);
  const speedTo = el("input", { id: "speed-to", type: "number", min: 30, max: 240, step: 1, inputmode: "numeric", value: settings.speedTo,
    "aria-label": tr("Speed up to (bpm)", "Cyflymu i (curiad y funud)"),
    onchange: (e) => {
      const to = Math.round(+e.target.value);
      settings.speedTo = Number.isFinite(to) && to >= 30 ? Math.min(240, to) : tune.bpm;
      e.target.value = settings.speedTo;
      speedHint();
    } });
  const speedUp = el("div", { class: "speed-up" },
    toggle(tr("Speed up each time", "Cyflymu bob tro"), settings.speedUp, (on) => { settings.speedUp = on; }),
    el("span", { class: "speed-range" }, tr("from ", "o "), speedFrom, tr(" to ", " i "), speedTo, tr(" bpm", " curiad y funud")));
  const whistleKey = el("span", { class: "caption whistle-key", hidden: !WHISTLES[state.practice.tab] },
    tr("● covered · ○ open · ◐ half-covered · + blow harder · ? not on this whistle",
      "● ar gau · ○ ar agor · ◐ hanner ar gau · + chwythu'n galetach · ? ddim ar y chwisl hon"));
  const tabSelect = el("select", { id: "tab-select", onchange: (e) => {
    state.practice.tab = e.target.value;
    whistleKey.hidden = !WHISTLES[state.practice.tab];
    redraw();
  } },
    [["none", tr("No tablature", "Dim tablatur")], ["mandolin", tr("Mandolin / fiddle", "Mandolin / ffidil")],
      ["guitar", tr("Guitar", "Gitâr")],
      ...Object.entries(WHISTLES).map(([value, w]) => [value, tr(`Whistle in ${w.name}`, `Chwisl ${w.name}`)])].map(([value, label]) =>
      el("option", { value, selected: state.practice.tab === value }, label)));
  const practiceRow = el("div", { class: "practice-row" },
    el("div", { class: "practice-line" },
      el("div", { class: "control" }, el("label", { for: "loop-select" }, tr("Repeat", "Ailadrodd")), loopSelect), speedUp),
    speedNote,
    el("div", { class: "practice-line" },
      toggle(tr("Count-in", "Cyfrif i mewn"), state.practice.countIn, (on) => { state.practice.countIn = on; }),
      toggle(tr("Click", "Clic"), state.practice.click, (on) => { state.practice.click = on; }),
      canSwing(tune) ? toggle(tr("Swing", "Swing"), settings.swing, (on) => { settings.swing = on; }, "swing",
        tr("Play the quavers long-short, as hornpipes are played", "Chwarae'r cwafers yn hir-byr, fel y chwaraeir pibddawnsiau")) : null),
    el("div", { class: "practice-line" },
      el("div", { class: "control" }, el("label", { for: "tab-select" }, tr("Tablature", "Tablatur")), tabSelect), whistleKey));
  // Folded away on a phone (the music comes first), open on wider screens; then as left.
  const practiceTools = el("details", { class: "practice-tools fold", open: state.practice.open ?? !matchMedia("(max-width: 800px)").matches,
    ontoggle: (e) => { state.practice.open = e.target.open; } },
    el("summary", {}, el("span", {}, tr("Practice tools", "Offer ymarfer"),
      el("span", { class: "caption" }, tr(" · repeat, speed up, count-in, click, tablature", " · ailadrodd, cyflymu, cyfrif i mewn, clic, tablatur")))),
    practiceRow);
  const fillLoops = () => {
    loopSelect.replaceChildren(el("option", { value: -2 }, tr("Off", "Dim")),
      el("option", { value: -1, selected: settings.loop === -1 }, tr("The whole tune", "Yr alaw gyfan")),
      ...(drawn.parts.length > 1 ? drawn.parts : []).map((p, i) =>
        el("option", { value: i, selected: settings.loop === i }, tr(`Part ${p.label}`, `Rhan ${p.label}`))));
    speedUp.hidden = settings.loop < -1;
  };
  loopSelect.addEventListener("change", fillLoops);

  const report = el("a", { class: "report", href: `?page=contact&about=${tune.slug}`, "data-route": true },
    tr("Report a problem with this tune", "Rhoi gwybod am broblem gyda'r alaw hon"));

  main.replaceChildren(...[
    el("h1", { lang: nameLang(group.slug) }, group.title),
    sayIt(group),
    group.titles.length > 1 ? el("p", { class: "caption aka" }, `${tr("Also known as", "Enwau eraill")}: ${group.titles.slice(1).join(", ")}`) : null,
    versions,
    controls,
    el("div", { class: "tune-layout" },
      el("div", { class: "tune-main" }, el("div", { class: "score" }, audio, chordPlayback(tune, () => redraw()), paper),
        practiceTools, actions, chords),
      el("div", { class: "tune-side" },
        el("section", { class: "card" }, el("h2", {}, tr("Details", "Manylion")), details, gloss || null),
        placeCard(group),
        el("details", { class: "abc" }, el("summary", {}, tr("ABC notation", "Nodiant ABC")), el("pre", { tabindex: 0 }, stripFields(tune.abc, "Z"))),
        el("p", { class: "report-line" }, report))),
  ].filter(Boolean));
  redraw();
  fillLoops();
  // A phone turned on its side, or a window made narrower: lay the music out again
  // when its lines would change.
  const resized = new ResizeObserver(() => {
    if (!paper.isConnected) resized.disconnect();
    else if (JSON.stringify(scoreLayout(paper)) !== paper.dataset.layout) redraw();
  });
  resized.observe(paper);
}

// ---- QR code: this tune's link, for someone across the table to scan ----------------------
// The QR library (static/qrcode, 56 KB) is only loaded when it's first needed.

let qrLibrary = null;
function loadQr() {
  qrLibrary ??= new Promise((resolve, reject) => document.head.append(
    el("script", { src: "static/qrcode/qrcode.js", onload: () => resolve(window.qrcode), onerror: reject })));
  return qrLibrary;
}

// The QR code as an SVG: one square per dark module, drawn as a single path.
function qrSvg(text) {
  // Less error correction for a long link (a big set), so its squares stay big enough to scan.
  const qr = window.qrcode(0, text.length > 300 ? "L" : "M");
  qr.addData(text);
  qr.make();
  const n = qr.getModuleCount(), margin = 4;
  let d = "";
  for (let r = 0; r < n; r++) for (let c = 0; c < n; c++) if (qr.isDark(r, c)) d += `M${c + margin} ${r + margin}h1v1h-1z`;
  return svg("svg", { viewBox: `0 0 ${n + 2 * margin} ${n + 2 * margin}`, class: "qr", role: "img",
    "aria-label": tr(`QR code for ${text}`, `Cod QR ar gyfer ${text}`), "shape-rendering": "crispEdges" },
    svg("rect", { width: "100%", height: "100%", fill: "#fff" }), svg("path", { d, fill: "#000" }));
}

async function showQr(title, link, caption) {
  await loadQr();
  const dialog = el("dialog", { class: "qr-dialog", "aria-labelledby": "qr-title" },
    el("h2", { id: "qr-title" }, title),
    qrSvg(link),
    el("p", { class: "caption" }, caption),
    el("p", { class: "caption qr-link" }, link.length > 120 ? `${link.slice(0, 60)}…` : link),
    el("form", { method: "dialog" }, el("button", { class: "primary" }, tr("Close", "Cau"))));
  dialog.addEventListener("close", () => dialog.remove());
  // A click on the backdrop (outside the box) closes it too.
  dialog.addEventListener("click", (e) => { if (e.target === dialog) dialog.close(); });
  document.body.append(dialog);
  dialog.showModal();
}

// The device's own share sheet (WhatsApp, Messages, email, …), where it has one: most
// phones, and some computers. Elsewhere there's Copy link and the QR code.
function shareButton(title, link) {
  if (!navigator.share) return null;
  return el("button", { type: "button", class: "share", onclick: () => navigator.share({ title, url: link() }).catch(() => {}) },
    tr("Share", "Rhannu"));
}

function qrButton(group, tune, settings) {
  return el("button", { type: "button", class: "qr-button", onclick: () =>
    showQr(group.title, `https://ysesiwn.cymru/${tuneLink(group, tune, settings)}`,
      tr("Scan with a phone's camera to open this tune.", "Sganiwch gyda chamera ffôn i agor yr alaw hon.")),
  }, tr("QR code", "Cod QR"));
}

// Called Full screen on the page (what it does), so it isn't mixed up with the Practice tools.
const practiceLabel = (on) => (on ? tr("Exit full screen", "Gadael y sgrin lawn") : tr("Full screen", "Sgrin lawn"));

// How to say a Welsh tune name (pronunciation.json), for English readers.
function sayIt(group) {
  const say = state.data.say[group.slug];
  if (!say || state.lang === "cy") return null;
  return el("p", { class: "say" }, "Say it: ", el("span", { class: "say-words" }, say), " ",
    el("details", { class: "say-key" }, el("summary", {}, "How to read this"),
      el("p", {}, "Capitals: the stressed syllable. kh: ch in loch. dh: th in this. hl: Welsh ll (tongue as for l, ",
        "and breathe out). ai: as in eye. ay: as in day. ow: as in cow. oo: as in food. uh: the a in about. ",
        "r is rolled. A rough guide for English speakers.")));
}

// Practice mode: hide everything but the controls and the score, full screen if possible.
function setPractice(on) {
  if (document.body.classList.contains("practice") === on) return;
  document.body.classList.toggle("practice", on);
  const button = document.querySelector(".practice-toggle");
  if (button) button.textContent = practiceLabel(on);
  if (on) document.querySelector(".practice-tools")?.setAttribute("open", "");
  if (on && document.fullscreenEnabled) document.documentElement.requestFullscreen().catch(() => {});
  if (!on && document.fullscreenElement) document.exitFullscreen().catch(() => {});
}
// Leaving full screen (e.g. with Esc) also leaves practice mode.
document.addEventListener("fullscreenchange", () => { if (!document.fullscreenElement) setPractice(false); });

// ---- Map: the places named in tune titles (places.json) --------------------------------

function svg(tag, attrs = {}, ...children) {
  const node = document.createElementNS("http://www.w3.org/2000/svg", tag);
  for (const [name, value] of Object.entries(attrs)) if (value != null) node.setAttribute(name, value);
  node.append(...children.flat().filter((c) => c != null));
  return node;
}

function walesMap(current = null, places = state.data.places, label = null) {
  // wales.svg is only the outline, used as a mask so the land takes the page's
  // colours (also in dark mode); the places are dots in an SVG on top of it.
  // places: the tunes' places (places.json), or others with x and y (the sessions' towns).
  const [width, height] = state.data.mapSize;
  const dots = places.map((place) => svg("circle", {
    cx: place.x, cy: place.y, r: place === current ? 3.6 : 2.2,
    class: current ? (place === current ? "here" : "other") : null,
  }, current ? svg("title", {}, place.name) : null));
  if (current) dots.push(dots.splice(places.indexOf(current), 1)[0]);  // drawn on top
  // The full map gets bigger invisible targets over the small dots, for pointing and tapping.
  const targets = current ? [] : places.map((place, i) =>
    svg("circle", { cx: place.x, cy: place.y, r: 5, class: "target", "data-place": i }));
  // The view clips; the canvas inside it (land and dots) is what zooming moves and scales.
  return el("div", { class: "wales-map", style: `aspect-ratio: ${width} / ${height}` },
    el("div", { class: "map-view" }, el("div", { class: "map-canvas" },
      svg("svg", { viewBox: `0 0 ${width} ${height}`, role: "img",
        "aria-label": label ?? (current ? tr(`Map of Wales showing ${current.name}`, `Map o Gymru yn dangos ${current.name}`)
          : tr("Map of Wales with the places named in tune titles", "Map o Gymru gyda'r lleoedd a enwir yn nheitlau alawon")) },
        dots, targets))));
}

// Zooming the full map: the + and − buttons, double-click or double-tap, pinching (a
// trackpad pinch is a Ctrl + wheel), and dragging to move about once zoomed in. A plain
// wheel or a one-finger swipe still scrolls the page. The dots keep their size on screen
// (--z in style.css), so crowded places come apart. onChange: after every zoom or move.
function mapZoom(map, onChange) {
  const view = map.querySelector(".map-view"), canvas = map.querySelector(".map-canvas");
  const MAX = 8;
  let scale = 1, x = 0, y = 0;
  const button = (label, text, onclick) => el("button", { type: "button", "aria-label": label, title: label, onclick }, text);
  const zoomIn = button(tr("Zoom in", "Chwyddo i mewn"), "+", () => zoomCentre(1.8));
  const zoomOut = button(tr("Zoom out", "Chwyddo allan"), "−", () => zoomCentre(1 / 1.8));
  const reset = button(tr("Show all of Wales", "Dangos Cymru gyfan"), "⤢", () => { scale = 1; apply(); });
  map.append(el("div", { class: "map-zoom" }, zoomIn, zoomOut, reset));
  const box = () => view.getBoundingClientRect();
  const apply = () => {
    const { width, height } = box();
    scale = Math.min(MAX, Math.max(1, scale));
    x = Math.min(0, Math.max(width - width * scale, x));  // no gaps at the edges
    y = Math.min(0, Math.max(height - height * scale, y));
    view.scrollLeft = view.scrollTop = 0;  // older browsers, where the clipped view could still be scrolled
    canvas.style.transform = scale > 1 ? `translate(${x}px, ${y}px) scale(${scale})` : "";  // none unless zoomed: crisper on phones
    canvas.style.setProperty("--z", scale);
    view.classList.toggle("zoomed", scale > 1);
    zoomIn.disabled = scale >= MAX;
    zoomOut.disabled = reset.disabled = scale <= 1;
    onChange();
  };
  // Zoom by factor, keeping the point (px, py) of the view where it is.
  const zoomAt = (factor, px, py) => {
    const next = Math.min(MAX, Math.max(1, scale * factor));
    x = px - (px - x) * (next / scale);
    y = py - (py - y) * (next / scale);
    scale = next;
    apply();
  };
  const zoomCentre = (factor) => { const { width, height } = box(); zoomAt(factor, width / 2, height / 2); };
  const at = (e) => { const b = box(); return [e.clientX - b.left, e.clientY - b.top]; };

  view.addEventListener("wheel", (e) => {
    if (!e.ctrlKey && !e.metaKey) return;  // a plain wheel scrolls the page
    e.preventDefault();
    zoomAt(Math.exp(-e.deltaY / 200), ...at(e));
  }, { passive: false });
  let lastPointer = "mouse";
  view.addEventListener("dblclick", (e) => { if (lastPointer !== "touch") zoomAt(2, ...at(e)); });  // touch: the double-tap below

  // Dragging (one pointer, when zoomed in) and pinching (two).
  const pointers = new Map();
  let moved = 0, pinch = null, lastTap = null;
  const twoFingers = () => {
    const [a, b] = [...pointers.values()];
    const b0 = box();
    return { dist: Math.hypot(a.x - b.x, a.y - b.y), mx: (a.x + b.x) / 2 - b0.left, my: (a.y + b.y) / 2 - b0.top };
  };
  view.addEventListener("pointerdown", (e) => {
    lastPointer = e.pointerType;
    pointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
    if (pointers.size === 1) moved = 0;
    if (pointers.size === 2) pinch = twoFingers();
  });
  view.addEventListener("pointermove", (e) => {
    const last = pointers.get(e.pointerId);
    if (!last) return;
    const dx = e.clientX - last.x, dy = e.clientY - last.y;
    pointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
    if (pointers.size === 2 && pinch) {
      const now = twoFingers();
      x += now.mx - pinch.mx;
      y += now.my - pinch.my;
      zoomAt(now.dist / pinch.dist, now.mx, now.my);
      pinch = now;
      moved = Infinity;
    } else if (pointers.size === 1 && scale > 1) {
      moved += Math.abs(dx) + Math.abs(dy);
      if (moved > 4) {
        try { view.setPointerCapture(e.pointerId); } catch {}  // keep the drag if the pointer leaves the map
        x += dx;
        y += dy;
        apply();
      }
    }
  });
  const up = (e) => {
    if (!pointers.delete(e.pointerId)) return;
    if (pointers.size < 2) pinch = null;
    // A double-tap zooms in (touch screens don't all send dblclick).
    if (e.type === "pointerup" && e.pointerType === "touch" && moved <= 4 && !pointers.size) {
      const [px, py] = at(e);
      if (lastTap && e.timeStamp - lastTap.time < 300 && Math.hypot(px - lastTap.x, py - lastTap.y) < 30) {
        zoomAt(2, px, py);
        lastTap = null;
      } else {
        lastTap = { time: e.timeStamp, x: px, y: py };
      }
    }
  };
  view.addEventListener("pointerup", up);
  view.addEventListener("pointercancel", up);
  // A drag or pinch isn't a click on a dot.
  view.addEventListener("click", (e) => { if (moved > 4) e.stopPropagation(); }, true);

  // The keyboard: + and − zoom, 0 shows all of Wales, the arrow keys move about.
  view.tabIndex = 0;
  view.setAttribute("aria-label", tr("Map: + and − to zoom, arrow keys to move", "Map: + a − i chwyddo, bysellau saeth i symud"));
  view.addEventListener("keydown", (e) => {
    const step = 40;
    const keys = { "+": () => zoomCentre(1.8), "=": () => zoomCentre(1.8), "-": () => zoomCentre(1 / 1.8), "0": () => { scale = 1; apply(); },
      ArrowLeft: () => { x += step; apply(); }, ArrowRight: () => { x -= step; apply(); },
      ArrowUp: () => { y += step; apply(); }, ArrowDown: () => { y -= step; apply(); } };
    if (!keys[e.key] || (e.key.startsWith("Arrow") && scale <= 1)) return;
    e.preventDefault();
    keys[e.key]();
  });
  new ResizeObserver(() => apply()).observe(view);
  apply();
}

function placeCard(group) {
  const place = state.data.places.find((p) => p.tunes.includes(group.slug));
  if (!place) return null;
  const sameName = normalize(place.name) === normalize(group.title);
  return el("section", { class: "card place" },
    el("h2", {}, sameName ? tr("On the map", "Ar y map") : place.name),
    walesMap(place),
    el("p", { class: "caption" }, el("a", { href: "?page=map", "data-route": true }, tr("All tunes on the map", "Pob alaw ar y map"))));
}

function renderMap(main) {
  document.title = tr("Tunes on the map · Y Sesiwn", "Alawon ar y map · Y Sesiwn");
  const places = [...state.data.places].sort((a, b) => (normalize(a.name) < normalize(b.name) ? -1 : 1));
  const map = walesMap();
  const circles = [...map.querySelectorAll("circle:not(.target)")];
  // Pointing at a place in the list lights up its dot.
  const light = (place, on) => circles[state.data.places.indexOf(place)].classList.toggle("lit", on);

  // Pointing at (or tapping) a dot shows a popup with the place's tunes. It stays
  // open while the pointer is on it, so its links can be clicked.
  const popup = el("div", { class: "map-popup", hidden: true });
  map.append(popup);
  // Where a place's dot is drawn in the map now (it moves as the map zooms).
  const placePopup = (place) => {
    const b = map.getBoundingClientRect(), d = circles[state.data.places.indexOf(place)].getBoundingClientRect();
    const x = d.left + d.width / 2 - b.left, y = d.top + d.height / 2 - b.top;
    Object.assign(popup.style, { left: `${x}px`, top: `${y}px` });
    // Above the dot, or below it near the top; kept inside the map at the sides.
    popup.dataset.side = y < b.height * 0.3 ? "below" : "above";
    popup.dataset.align = x < b.width * 0.3 ? "left" : x > b.width * 0.7 ? "right" : "centre";
    popup.hidden = x < 0 || y < 0 || x > b.width || y > b.height;  // zoomed away from it
  };
  let shown = null, hideTimer = null;
  const hide = () => { if (shown) light(shown, false); shown = null; popup.hidden = true; };
  const hideSoon = () => { clearTimeout(hideTimer); hideTimer = setTimeout(hide, 250); };
  const show = (place) => {
    clearTimeout(hideTimer);
    if (shown === place) return;
    hide();
    shown = place;
    light(place, true);
    popup.replaceChildren(el("strong", {}, place.name), el("ul", {}, place.tunes.map((slug) =>
      el("li", {}, el("a", { href: tuneUrl(slug), "data-route": true }, tuneName(slug, state.groups.get(slug).title))))));
    placePopup(place);
  };
  const target = (event) => event.target.closest?.(".target");
  const place = (e) => state.data.places[target(e).dataset.place];
  mapZoom(map, () => { if (shown) placePopup(shown); });
  map.addEventListener("pointerover", (e) => { if (target(e) && e.pointerType !== "touch" && !e.buttons) show(place(e)); });
  // A touch "leaves" the dot as soon as the finger lifts: only a mouse closes it that way.
  map.addEventListener("pointerout", (e) => { if (target(e) && e.pointerType !== "touch") hideSoon(); });
  // Tapping (or clicking) a dot opens its popup, and it stays open until you tap elsewhere.
  map.addEventListener("click", (e) => { if (target(e)) show(place(e)); });
  popup.addEventListener("pointerenter", () => clearTimeout(hideTimer));
  popup.addEventListener("pointerleave", (e) => { if (e.pointerType !== "touch") hideSoon(); });
  // On a touchscreen, tapping elsewhere closes it.
  // (#main stays from page to page, so the listener goes once the map has.)
  const tapElsewhere = (e) => {
    if (!map.isConnected) main.removeEventListener("pointerdown", tapElsewhere);
    else if (!target(e) && !popup.contains(e.target)) hide();
  };
  main.addEventListener("pointerdown", tapElsewhere);
  const list = el("ul", { class: "place-list" }, places.map((place) =>
    el("li", { onmouseenter: () => light(place, true), onmouseleave: () => light(place, false) },
      el("strong", {}, place.name), " ",
      place.tunes.map((slug, i) => [i ? ", " : "", el("a", { href: tuneUrl(slug), "data-route": true }, tuneName(slug, state.groups.get(slug).title))]))));
  main.replaceChildren(
    el("h1", {}, tr("Tunes on the map", "Alawon ar y map")),
    el("p", { class: "lead" }, tr(`${places.length} places in Wales and just over the border that tunes are named after.`,
      `${places.length} lle yng Nghymru, a rhai dros y ffin, y mae alawon wedi'u henwi ar eu hôl.`)),
    el("div", { class: "map-layout" },
      el("figure", {}, map, el("figcaption", { class: "caption" },
        tr("Outline: Office for National Statistics, Open Government Licence. Contains OS data © Crown copyright and database right.",
          "Amlinell: Swyddfa Ystadegau Gwladol, Trwydded Llywodraeth Agored. Yn cynnwys data'r Arolwg Ordnans © Hawlfraint y Goron a hawl cronfa ddata."))),
      list));
}

// ---- Sessions: where Welsh tunes are played (sessions.json, from build_site.py) -----------
// A session runs every week, or on the nth (or last) weekday of the month, within its
// season if it has one; its next date is worked out here. Each shows when someone last
// confirmed it, and asks anyone who's been lately to say it's still as described.

const DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];
const CY_DAYS = { Monday: "Llun", Tuesday: "Mawrth", Wednesday: "Mercher", Thursday: "Iau", Friday: "Gwener",
  Saturday: "Sadwrn", Sunday: "Sul" };
const dateOf = (text) => new Date(`${text}T00:00`);
// Dates in Welsh are written here, not by the browser: many (Android's Chrome among them)
// have no Welsh dates and give English ones, in American order. In English, "en-GB".
const CY_MONTHS = ["Ionawr", "Chwefror", "Mawrth", "Ebrill", "Mai", "Mehefin", "Gorffennaf", "Awst", "Medi", "Hydref", "Tachwedd", "Rhagfyr"];
const CY_MONTHS_SHORT = ["Ion", "Chwef", "Maw", "Ebr", "Mai", "Meh", "Gorff", "Awst", "Medi", "Hyd", "Tach", "Rhag"];
const WEEKDAYS = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];
const dateLabel = (date, options) => {
  if (state.lang !== "cy") return date.toLocaleDateString("en-GB", options);
  return [  // "dydd Iau 22 Hydref 2026", "2 Hyd 2026"
    options.weekday && `dydd ${CY_DAYS[WEEKDAYS[date.getDay()]]}`,
    options.day && String(date.getDate()),
    options.month && (options.month === "short" ? CY_MONTHS_SHORT : CY_MONTHS)[date.getMonth()],
    options.year && String(date.getFullYear()),
  ].filter(Boolean).join(" ");
};

// A session on announced dates (repeat: "dates"): those still to come, today's included.
function upcomingDates(session, today = new Date()) {
  const day = new Date(today.getFullYear(), today.getMonth(), today.getDate());
  return (session.dates ?? []).map(dateOf).filter((d) => d >= day);
}

function nextSession(session, today = new Date()) {
  if (session.repeat === "dates") return upcomingDates(session, today)[0] ?? null;
  const weekday = (DAYS.indexOf(session.day) + 1) % 7;  // getDay(): Sunday is 0
  const day = new Date(today.getFullYear(), today.getMonth(), today.getDate());
  if (session.from && dateOf(session.from) > day) day.setTime(dateOf(session.from).getTime());
  const until = session.until ? dateOf(session.until) : null;
  for (let i = 0; i < 400; i++, day.setDate(day.getDate() + 1)) {
    if (until && day > until) return null;
    if (day.getDay() !== weekday) continue;
    if (session.repeat === "monthly") {
      const last = new Date(day.getFullYear(), day.getMonth(), day.getDate() + 7).getMonth() !== day.getMonth();
      if (session.nth === -1 ? !last : Math.ceil(day.getDate() / 7) !== session.nth) continue;
    }
    return day;
  }
  return null;
}

// "7–9pm", "8:30–11pm", "from 9pm" (Welsh: yh, the evening; yb, the morning).
function sessionTime({ start, end }) {
  const part = (time) => {
    const [h, m] = time.split(":").map(Number);
    return { text: `${h % 12 || 12}${m ? `:${String(m).padStart(2, "0")}` : ""}`, pm: h >= 12 };
  };
  const suffix = (pm) => (pm ? tr("pm", "yh") : tr("am", "yb"));
  const a = part(start);
  if (!end) return tr(`from ${a.text}${suffix(a.pm)}`, `o ${a.text}${suffix(a.pm)}`);
  const b = part(end);
  return `${a.text}${a.pm === b.pm ? "" : suffix(a.pm)}–${b.text}${suffix(b.pm)}`;
}

// "Every Tuesday", "2nd Friday of the month"; "Bob dydd Mawrth", "Ail ddydd Gwener y mis";
// for a session on announced dates, the next one ("Thursday 22 October").
function sessionDays(session, today = new Date()) {
  const { day, repeat, nth } = session;
  if (repeat === "dates") {
    const next = upcomingDates(session, today)[0];
    return next ? dateLabel(next, { weekday: "long", day: "numeric", month: "long" }).replace(/^./, (c) => c.toUpperCase())
      : tr("No date announced yet", "Dim dyddiad wedi'i gyhoeddi eto");
  }
  if (repeat === "weekly") return tr(`Every ${day}`, `Bob dydd ${CY_DAYS[day]}`);
  const en = { 1: "1st", 2: "2nd", 3: "3rd", 4: "4th", [-1]: "Last" }[nth];
  const cy = { 1: `Dydd ${CY_DAYS[day]} cyntaf y mis`, 2: `Ail ddydd ${CY_DAYS[day]} y mis`, 3: `Trydydd dydd ${CY_DAYS[day]} y mis`,
    4: `Pedwerydd dydd ${CY_DAYS[day]} y mis`, [-1]: `Dydd ${CY_DAYS[day]} olaf y mis` }[nth];
  return tr(`${en} ${day} of the month`, cy);
}

// Telling Y Sesiwn about a session: it's still on, something's changed, or it's stopped.
function sessionReport(session, place) {
  const choices = [["still", tr("It's still running as described", "Mae'n dal i gael ei chynnal fel y disgrifir")],
    ["changed", tr("Something has changed (day, time or place)", "Mae rhywbeth wedi newid (dydd, amser neu le)")],
    ["stopped", tr("It has stopped", "Mae wedi dod i ben")]];
  const name = `report-${session.id}`;
  const radios = choices.map(([value, label], i) => el("label", { class: "check" },
    el("input", { type: "radio", name, value, checked: i === 0 }), ` ${label}`));
  const message = el("textarea", { rows: 3 });
  const choice = () => choices.find(([value]) => value === radios.map((r) => r.querySelector("input")).find((r) => r.checked)?.value);
  // One quiet line: when it was last confirmed, and the way to tell us it's changed.
  const confirmed = dateLabel(dateOf(session.confirmed), { day: "numeric", month: "short", year: "numeric" });
  return el("details", { class: "session-report" },
    el("summary", {}, el("span", { class: "confirmed" }, tr(`Confirmed ${confirmed}`, `Cadarnhawyd ${confirmed}`)), " · ",
      el("span", { class: "tell" }, tr("Been lately? Tell us", "Wedi bod yn ddiweddar? Rhowch wybod"))),
    emailForm([el("fieldset", {}, el("legend", { class: "visually-hidden" }, tr("This session", "Y sesiwn hon")), radios),
      field(tr("Details (optional): the new time, say, or when you went", "Manylion (dewisol): yr amser newydd, er enghraifft, neu pryd aethoch chi"), message)], {
      subject: () => `Y Sesiwn: ${tr("session", "sesiwn")}, ${place} (${choice()[0]})`,
      body: () => `${choice()[1]}.\n\n${message.value.trim()}\n\n${tr("Session", "Sesiwn")}: ${session.id}\n`,
      send: tr("Write the email", "Ysgrifennu'r e-bost"),
    }));
}

// A calendar file for a session (.ics): it repeats as the session does, in Welsh time
// (with the clocks' changes), until its season ends if it has one.
const ICS_DAYS = { Monday: "MO", Tuesday: "TU", Wednesday: "WE", Thursday: "TH", Friday: "FR", Saturday: "SA", Sunday: "SU" };
const LONDON = ["BEGIN:VTIMEZONE", "TZID:Europe/London",
  "BEGIN:DAYLIGHT", "TZOFFSETFROM:+0000", "TZOFFSETTO:+0100", "TZNAME:BST", "DTSTART:19700329T010000",
  "RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=-1SU", "END:DAYLIGHT",
  "BEGIN:STANDARD", "TZOFFSETFROM:+0100", "TZOFFSETTO:+0000", "TZNAME:GMT", "DTSTART:19701025T020000",
  "RRULE:FREQ=YEARLY;BYMONTH=10;BYDAY=-1SU", "END:STANDARD", "END:VTIMEZONE"];
function sessionCalendar(session, first) {
  const text = (t) => t.replace(/[\\;,]/g, (c) => `\\${c}`).replace(/\n/g, "\\n");
  const stamp = (date, time) => `${date.getFullYear()}${String(date.getMonth() + 1).padStart(2, "0")}${String(date.getDate()).padStart(2, "0")}T${time.replace(":", "")}00`;
  const [h, m] = session.start.split(":").map(Number);
  let end = session.end;
  if (!end) end = `${String((h + 2) % 24).padStart(2, "0")}:${String(m).padStart(2, "0")}`;  // no end time: two hours
  const rule = session.repeat === "weekly" ? `FREQ=WEEKLY;BYDAY=${ICS_DAYS[session.day]}`
    : `FREQ=MONTHLY;BYDAY=${session.nth}${ICS_DAYS[session.day]}`;
  const until = session.until ? `;UNTIL=${session.until.replaceAll("-", "")}T235959Z` : "";
  // A session on announced dates: an event for each date to come, none repeating.
  const days = session.repeat === "dates" ? upcomingDates(session, first) : [first];
  const after = (day) => (end <= session.start ? new Date(day.getFullYear(), day.getMonth(), day.getDate() + 1) : day);  // past midnight
  const page = "https://ysesiwn.cymru/sesiynau/";
  const about = [session.music ? tr(session.music, session.music_cy ?? session.music) : null,
    tr("Times change: check before you go.", "Mae amseroedd yn newid: gwiriwch cyn mynd."),
    session.link, page].filter(Boolean).join("\n\n");
  const lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Y Sesiwn//Sessions//EN", "CALSCALE:GREGORIAN", ...LONDON,
    ...days.flatMap((day) => ["BEGIN:VEVENT",
      `UID:${session.id}${session.repeat === "dates" ? `-${stamp(day, "00:00").slice(0, 8)}` : ""}@ysesiwn.cymru`,
      `DTSTAMP:${new Date().toISOString().replace(/[-:]/g, "").slice(0, 15)}Z`,
      `DTSTART;TZID=Europe/London:${stamp(day, session.start)}`, `DTEND;TZID=Europe/London:${stamp(after(day), end)}`,
      session.repeat === "dates" ? null : `RRULE:${rule}${until}`,
      `SUMMARY:${text(session.name ?? `${tr("Session", "Sesiwn")}: ${session.venue}`)}`,
      `LOCATION:${text(`${session.venue}, ${session.address}`)}`, `DESCRIPTION:${text(about)}`, `URL:${session.link ?? page}`,
      "END:VEVENT"].filter(Boolean)),
    "END:VCALENDAR"];
  // Lines longer than 75 bytes are folded (a line break and a space), as the format asks.
  const fold = (line) => {
    const out = []; let cur = "";
    for (const ch of line) {
      if (new TextEncoder().encode(cur + ch).length > (out.length ? 74 : 75)) { out.push(cur); cur = ""; }
      cur += ch;
    }
    return [...out, cur].join("\r\n ");
  };
  return lines.map(fold).join("\r\n") + "\r\n";
}

function sessionCard(session) {
  const next = nextSession(session);
  const today = new Date().toDateString() === next?.toDateString();
  const place = `${session.venue}, ${tr(session.town, session.town_cy)}`;
  const map = `https://www.openstreetmap.org/?mlat=${session.lat}&mlon=${session.lon}#map=17/${session.lat}/${session.lon}`;
  const onDates = session.repeat === "dates";
  // A session on announced dates: its later ones, or (with none to come) how to find the next.
  const later = onDates ? upcomingDates(session).slice(1).map((d) => dateLabel(d, { day: "numeric", month: "long" })) : [];
  const and = (items) => (items.length < 2 ? items.join("") : `${items.slice(0, -1).join(", ")} ${tr("and", "a")} ${items.at(-1)}`);
  const season = onDates
    ? next ? (later.length ? tr(`Then ${and(later)}.`, `Yna ${and(later)}.`) : null)
      : session.link ? tr("It runs on dates announced as they come: see their page for the next one.",
        "Mae'n cael ei chynnal ar ddyddiadau a gyhoeddir fesul un: gwelwch eu tudalen am yr un nesaf.")
        : tr("It runs on dates announced as they come: if you hear of the next one, tell us below.",
          "Mae'n cael ei chynnal ar ddyddiadau a gyhoeddir fesul un: os clywch chi am yr un nesaf, rhowch wybod i ni isod.")
    : session.until && !next ? tr("This season has ended.", "Mae'r tymor wedi dod i ben.")
    : session.from && dateOf(session.from) > new Date()
      ? tr(`Starts ${dateLabel(dateOf(session.from), { day: "numeric", month: "long" })}`, `Yn dechrau ${dateLabel(dateOf(session.from), { day: "numeric", month: "long" })}`)
        + (session.until ? tr(`, until ${dateLabel(dateOf(session.until), { day: "numeric", month: "long", year: "numeric" })}.`,
          `, tan ${dateLabel(dateOf(session.until), { day: "numeric", month: "long", year: "numeric" })}.`) : ".")
      : session.until ? tr(`Until ${dateLabel(dateOf(session.until), { day: "numeric", month: "long", year: "numeric" })}.`,
        `Tan ${dateLabel(dateOf(session.until), { day: "numeric", month: "long", year: "numeric" })}.`) : null;
  return el("article", { class: "card session", id: `session-${session.id}`, tabindex: -1 },
    el("h3", {}, session.name ?? session.venue,
      session.kind === "tune club" ? el("span", { class: "badge" }, tr("Tune club", "Clwb alawon")) : null),
    el("p", { class: "when" }, el("strong", {}, `${sessionDays(session)}, ${sessionTime(session)}`),
      next && (today || !onDates) ? [" · ", today ? tr("today", "heddiw") : tr(`next: ${dateLabel(next, { weekday: "long", day: "numeric", month: "long" })}`,
        `nesaf: ${dateLabel(next, { weekday: "long", day: "numeric", month: "long" })}`)] : null),
    el("p", {}, session.name ? `${session.venue}, ` : "", session.address),
    session.music ? el("p", {}, tr(session.music, session.music_cy ?? session.music)) : null,
    season ? el("p", { class: "caption" }, season) : null,
    // What you'd do with it, as a row of buttons big enough for a thumb.
    el("div", { class: "session-links" },
      el("a", { class: "action", href: map, target: "_blank", rel: "noopener" }, tr("Map", "Map")),
      next ? el("button", { type: "button", onclick: () => download(`${session.id}.ics`, "text/calendar", sessionCalendar(session, next)) },
        tr("Add to calendar", "Ychwanegu at y calendr")) : null,
      session.link ? el("a", { class: "action", href: session.link, target: "_blank", rel: "noopener" }, tr("More about it", "Rhagor amdani")) : null),
    sessionReport(session, place));
}

// Sending a session that's missing.
function addSessionForm() {
  const input = (attrs = {}) => el("input", { type: "text", ...attrs });
  const venue = input({ required: true }), when = input({ required: true }), time = input(), music = input(), link = input({ type: "url" });
  const more = el("textarea", { rows: 4 });
  const rows = [[tr("Venue and town", "Lleoliad a thref"), venue], [tr("Day, and how often", "Dydd, a pha mor aml"), when],
    [tr("Time", "Amser"), time], [tr("What's played", "Beth sy'n cael ei chwarae"), music], [tr("Link (optional)", "Dolen (dewisol)"), link],
    [tr("Anything else (optional)", "Unrhyw beth arall (dewisol)"), more]];
  return emailForm([
    field(rows[0][0], venue, tr("e.g. The Red Lion, Llandeilo", "e.e. Y Llew Coch, Llandeilo")),
    field(rows[1][0], when, tr("e.g. every Wednesday, or the 1st Sunday of the month", "e.e. bob dydd Mercher, neu ddydd Sul cyntaf y mis")),
    field(rows[2][0], time, tr("e.g. 8–10:30pm", "e.e. 8–10:30yh")),
    field(rows[3][0], music, tr("e.g. mostly Welsh tunes; songs too", "e.e. alawon Cymreig gan fwyaf; caneuon hefyd")),
    field(rows[4][0], link, tr("The session's or venue's page, if it has one", "Tudalen y sesiwn neu'r lleoliad, os oes un")),
    field(rows[5][0], more),
  ], {
    subject: () => `Y Sesiwn: ${tr("a session", "sesiwn")}, ${venue.value.trim()}`,
    body: () => rows.map(([label, control]) => `${label}: ${control.value.trim()}`).join("\n") + "\n",
  });
}

function loadSessions() {
  state.sessionData ??= fetch("sessions.json").then((answer) => answer.json()).catch((error) => { state.sessionData = null; throw error; });
  return state.sessionData;
}

// Coming up: every session in the next seven days (counted from today, so on a Sunday
// that's Monday to Saturday too), soonest first; and, further ahead, a session on
// announced dates up to four weeks off (an occasional one is worth knowing about sooner).
const SOON_DAYS = 7, ANNOUNCED_DAYS = 28;
function comingUp(sessions) {
  const today = new Date(); today.setHours(0, 0, 0, 0);
  const all = sessions.map((s) => ({ s, next: nextSession(s) })).filter(({ next }) => next)
    .sort((a, b) => a.next - b.next || (a.s.start < b.s.start ? -1 : 1));
  const days = ({ next }) => (next - today) / 864e5;
  return { soon: all.filter((x) => days(x) < SOON_DAYS),
    later: all.filter((x) => days(x) >= SOON_DAYS && days(x) < ANNOUNCED_DAYS && x.s.repeat === "dates") };
}

// "Tonight", "Tomorrow", "Saturday" (within the week), "Thursday 22 October" (further on).
function soonDay(next, start) {
  const today = new Date(); today.setHours(0, 0, 0, 0);
  const days = Math.round((next - today) / 864e5);
  if (days === 0) return start >= "17:00" ? tr("Tonight", "Heno") : tr("Today", "Heddiw");
  if (days === 1) return tr("Tomorrow", "Yfory");
  const name = dateLabel(next, days < SOON_DAYS ? { weekday: "long" } : { weekday: "long", day: "numeric", month: "long" });
  return name[0].toUpperCase() + name.slice(1);
}

// One session in a coming-up list: when, what and where (its name, or link: its name as a link to its card).
const soonItem = ({ s, next }, link = null) => el("li", {}, el("strong", {}, soonDay(next, s.start)), " · ",
  ...(link ? [link, `, ${tr(s.town, s.town_cy)}, ${sessionTime(s)}`] : [`${s.name ?? s.venue}, ${tr(s.town, s.town_cy)}, ${sessionTime(s)}`]),
  s.kind === "tune club" && !/tune club|clwb alawon/i.test(s.name ?? "") ? el("span", { class: "caption" }, ` (${tr("tune club", "clwb alawon")})`) : null);

// On the home page: the next HOME_SOON sessions, in order; then, under "Also coming up", up to
// HOME_ALSO on announced dates that aren't among them (the occasional ones, easy to miss:
// the weekly ones are on next week too); then how many more there are in the next seven
// days, on the sessions page. Filled in once sessions.json has come (the page doesn't wait
// for it), and hidden when there are none.
const HOME_SOON = 3, HOME_ALSO = 2;
function upcomingSessions() {
  const box = el("section", { class: "coming-up", hidden: true });
  loadSessions().then(({ sessions }) => {
    const { soon, later } = comingUp(sessions);
    if (!(soon.length || later.length) || !box.isConnected) return;
    const first = soon.slice(0, HOME_SOON);
    const also = [...soon.slice(HOME_SOON), ...later].filter((x) => x.s.repeat === "dates").slice(0, HOME_ALSO);
    const more = soon.length - first.length - also.filter((x) => soon.includes(x)).length;
    // Each one links to its card on the sessions page (address, map, calendar).
    const item = (x) => soonItem(x, el("a", { href: `sesiynau/#session-${x.s.id}`, "data-route": true }, x.s.name ?? x.s.venue));
    box.replaceChildren(...[
      el("h2", { class: "section-heading" }, tr("Coming up", "I ddod")),
      first.length ? el("ul", {}, first.map(item)) : null,
      also.length ? el("p", { class: "also" }, tr("One-off dates:", "Dyddiadau arbennig:")) : null,
      also.length ? el("ul", {}, also.map(item)) : null,
      el("p", {}, el("a", { href: "sesiynau/", "data-route": true }, more
        ? tr(`And ${more} more in the next seven days: all sessions, on a map`, `A ${more} arall yn y saith diwrnod nesaf: pob sesiwn, ar fap`)
        : tr("All sessions, on a map", "Pob sesiwn, ar fap"))),
    ].filter(Boolean));
    box.hidden = false;
  }).catch(() => {});
  return box;
}

async function renderSessions(main) {
  document.title = tr("Active sessions · Y Sesiwn", "Sesiynau cyfredol · Y Sesiwn");
  let sessions;
  try { ({ sessions } = await loadSessions()); } catch {
    main.replaceChildren(el("h1", {}, tr("Active sessions", "Sesiynau cyfredol")),
      el("p", {}, tr("Couldn't load the sessions. Check your connection and try again.", "Methu llwytho'r sesiynau. Gwiriwch eich cysylltiad a rhoi cynnig arall arni.")),
      el("button", { type: "button", class: "primary", onclick: () => renderSessions(main) }, tr("Try again", "Rhoi cynnig arall arni")));
    return;
  }
  if (!/^sesiynau\/?$/.test(sitePath())) return;  // left while loading

  // One dot per town, where its sessions are; the list is in towns too.
  const towns = [];
  for (const session of sessions) {
    let town = towns.find((t) => t.name === session.town);
    if (!town) towns.push(town = { name: session.town, cy: session.town_cy, county: session.county, sessions: [] });
    town.sessions.push(session);
  }
  for (const town of towns) {
    const onMap = town.sessions.filter((s) => s.x != null);
    if (onMap.length) Object.assign(town, { x: onMap.reduce((t, s) => t + s.x, 0) / onMap.length, y: onMap.reduce((t, s) => t + s.y, 0) / onMap.length });
  }
  const mapped = towns.filter((t) => t.x != null);
  const map = walesMap(null, mapped.map((t) => ({ ...t, name: tr(t.name, t.cy) })),
    tr("Map of Wales with the towns that have sessions", "Map o Gymru gyda'r trefi sydd â sesiynau"));
  const circles = [...map.querySelectorAll("circle:not(.target)")];
  const targets = [...map.querySelectorAll("circle.target")];
  // Few dots, so each has its town's name beside it. The names are page text over the
  // map, not part of it, so they stay sharp however the map is zoomed (phones blur text
  // inside a scaled layer); placeLabels puts each beside its dot, to the right, or on
  // whichever side doesn't run into another name or dot.
  const labels = mapped.map((town) => el("span", { class: "town-label" }, tr(town.name, town.cy)));
  map.querySelector(".map-view").append(el("div", { class: "town-labels", "aria-hidden": "true" }, labels));
  const placeLabels = () => {
    const b = map.getBoundingClientRect();
    if (!b.width) return;  // not on the page yet
    const centres = circles.map((c) => {
      const d = c.getBoundingClientRect();
      return [d.left + d.width / 2 - b.left, d.top + d.height / 2 - b.top];
    });
    const taken = centres.filter((_, i) => !circles[i].classList.contains("off")).map(([x, y]) => [x - 5, x + 5, y - 5, y + 5]);
    const inside = ([x0, x1, y0, y1]) => x0 >= 0 && x1 <= b.width && y0 >= 0 && y1 <= b.height;
    const hits = (box, others) => others.some((t) => box[0] < t[1] && box[1] > t[0] && box[2] < t[3] && box[3] > t[2]);
    const overlap = ([x0, x1, y0, y1], others) => others.reduce((sum, t) =>
      sum + Math.max(0, Math.min(x1, t[1]) - Math.max(x0, t[0])) * Math.max(0, Math.min(y1, t[3]) - Math.max(y0, t[2])), 0);
    // Each shown name's places beside its dot, best first: right, left, above, below; then
    // the same a little higher or lower, for a crowded corner (the valleys).
    const shown = [];
    labels.forEach((label, i) => {
      const [x, y] = centres[i];
      label.hidden = circles[i].classList.contains("off") || x < 0 || y < 0 || x > b.width || y > b.height;
      if (label.hidden) return;
      const w = label.offsetWidth, h = label.offsetHeight, gap = 6;
      const sides = [[x + gap, y - h / 2], [x - gap - w, y - h / 2], [x - w / 2, y - gap - h], [x - w / 2, y + gap],
        [x + gap, y - h - 2], [x + gap, y + 2], [x - gap - w, y - h - 2], [x - gap - w, y + 2]]
        .map(([left, top]) => [left, left + w, top, top + h]).filter((box) => inside(box) && !hits(box, taken));
      shown.push({ label, sides });
    });
    // Placed one by one, a name with no clear place moves the ones before it (a search
    // that goes back, cut short in a hopeless tangle: then each takes whichever place runs
    // into the fewest names already placed).
    const placed = [];
    let steps = 0;
    const place = (k) => {
      if (k === shown.length) return true;
      for (const box of shown[k].sides) {
        if (++steps > 5000) return false;
        if (hits(box, placed)) continue;
        placed.push(box);
        if (place(k + 1)) return true;
        placed.pop();
      }
      return false;
    };
    if (!place(0)) {
      placed.length = 0;
      for (const { label, sides } of shown) {
        const w = label.offsetWidth, h = label.offsetHeight;
        const options = sides.length ? sides : [[0, w, 0, h]];
        placed.push(options.reduce((best, box) => (overlap(box, placed) < overlap(best, placed) ? box : best)));
      }
    }
    shown.forEach(({ label }, k) => Object.assign(label.style, { left: `${placed[k][0]}px`, top: `${placed[k][2]}px` }));
  };
  const light = (town, on) => circles[mapped.indexOf(town)]?.classList.toggle("lit", on);
  mapZoom(map, placeLabels);
  map.addEventListener("click", (e) => {
    const target = e.target.closest?.(".target");
    if (!target) return;
    const heading = document.getElementById(`town-${typeSlug(mapped[target.dataset.place].name)}`);
    heading?.scrollIntoView({ behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "start" });
    heading?.focus({ preventScroll: true });
  });

  // Filters: a day of the week, and a county (or outside Wales); choosing one again clears it.
  let chosenDay = null, chosenCounty = null;
  const dayPills = el("div", { class: "pills plain", role: "group", "aria-label": tr("Day of the week", "Dydd o'r wythnos") });
  // Areas are a drop-down, not buttons: there are more of them, and the list will grow.
  const countySelect = el("select", { id: "area-select", onchange: (e) => { chosenCounty = e.target.value || null; show(); } });
  const counties = [...new Set(sessions.map((s) => s.county))].sort((a, b) =>
    (a === "Outside Wales") - (b === "Outside Wales") || (normalize(a) < normalize(b) ? -1 : 1));
  const list = el("div", { class: "session-list" });
  const caption = el("p", { class: "caption", "aria-live": "polite" });
  const show = () => {
    const fits = (s, day = chosenDay, county = chosenCounty) => (!day || s.day === day) && (!county || s.county === county);
    for (const pill of dayPills.children) {
      const n = sessions.filter((s) => fits(s, pill.dataset.day)).length;
      pill.setAttribute("aria-pressed", pill.dataset.day === chosenDay);
      pill.lastChild.textContent = String(n);
      pill.disabled = n === 0 && pill.dataset.day !== chosenDay;
    }
    for (const option of countySelect.options) {
      const n = sessions.filter((s) => fits(s, chosenDay, option.value || null)).length;
      option.textContent = `${option.dataset.name} (${n})`;
      option.selected = option.value === (chosenCounty ?? "");
      option.disabled = n === 0 && option.value !== (chosenCounty ?? "");
    }
    const shown = sessions.filter((s) => fits(s));
    caption.textContent = tr(`${shown.length} session${shown.length === 1 ? "" : "s"}`, `${shown.length} sesiwn`);
    mapped.forEach((town, i) => {
      const any = town.sessions.some((s) => fits(s));
      for (const mark of [circles[i], targets[i]]) mark.classList.toggle("off", !any);
    });
    placeLabels();
    list.replaceChildren(...towns.filter((t) => t.sessions.some((s) => fits(s))).map((town) =>
      el("section", { class: "town", onmouseenter: () => light(town, true), onmouseleave: () => light(town, false) },
        el("h2", { id: `town-${typeSlug(town.name)}`, tabindex: -1 }, tr(town.name, town.cy),
          town.county !== town.name ? el("span", { class: "caption" }, ` · ${tr(town.county, town.sessions[0].county_cy)}`) : null),
        town.sessions.filter((s) => fits(s)).map(sessionCard))));
  };
  for (const day of DAYS.filter((d) => sessions.some((s) => s.day === d))) {  // only days with a session
    dayPills.append(el("button", { type: "button", "data-day": day, onclick: () => { chosenDay = chosenDay === day ? null : day; show(); } },
      `${tr(day, CY_DAYS[day])} ·\u00a0`, el("span", {})));
  }
  countySelect.append(el("option", { value: "", "data-name": tr("Everywhere", "Pob man") }));
  for (const county of counties) {
    const cy = sessions.find((s) => s.county === county).county_cy;
    countySelect.append(el("option", { value: county, "data-name": tr(county, cy) }));
  }

  // The form for a missing session is at the foot of the page: the introduction links to
  // it. (A plain #link would follow <base href> to the home page.)
  const addHeading = el("h2", { class: "section-heading", id: "add-session", tabindex: -1 }, tr("Missing a session?", "Sesiwn ar goll?"));
  const toForm = (text) => el("a", { href: "#add-session", onclick: (e) => {
    e.preventDefault();
    addHeading.scrollIntoView({ behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "start" });
    addHeading.focus({ preventScroll: true });
  } }, text);
  // Every session coming up (see comingUp), at the top: each a link down to its card
  // (shown again first, if the filters below have hidden it).
  const toCard = (session, text) => el("a", { href: `#session-${session.id}`, onclick: (e) => {
    e.preventDefault();
    if (!document.getElementById(`session-${session.id}`)) { chosenDay = chosenCounty = null; show(); }
    const card = document.getElementById(`session-${session.id}`);
    card?.scrollIntoView({ behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "start" });
    card?.focus({ preventScroll: true });
  } }, text);
  const { soon, later } = comingUp(sessions);
  const soonList = (items) => el("ul", {}, items.map((x) => soonItem(x, toCard(x.s, x.s.name ?? x.s.venue))));
  const upcoming = soon.length || later.length ? el("section", { class: "coming-up" }, ...[
    el("h2", { class: "section-heading" }, tr("Coming up", "I ddod")),
    soon.length ? [el("p", { class: "pills-label" }, tr("Next seven days", "Y saith diwrnod nesaf")), soonList(soon)] : null,
    later.length ? [el("p", { class: "pills-label" }, tr("Further ahead", "Ymhellach ymlaen")), soonList(later)] : null,
  ].filter(Boolean)) : null;
  main.replaceChildren(...[
    el("h1", {}, tr("Active sessions", "Sesiynau cyfredol")),
    el("p", { class: "lead" }, tr("Folk sessions and tune clubs with a strong focus on Welsh music: come along with an instrument, or just to listen.",
      "Sesiynau gwerin a chlybiau alawon sy'n canolbwyntio ar gerddoriaeth Gymreig: dewch ag offeryn, neu dim ond i wrando."),
      " ", toForm(tr("Know a session we're missing? Tell us about it.", "Gwybod am sesiwn sydd ar goll? Rhowch wybod i ni amdani."))),
    upcoming,
    el("h2", { class: "section-heading" }, tr("Every session, by town", "Pob sesiwn, fesul tref")),
    el("p", { class: "pills-label" }, tr("Day", "Dydd")), dayPills,
    el("div", { class: "control area-filter" }, el("label", { class: "pills-label", for: "area-select" }, tr("Area", "Ardal")), countySelect),
    caption,
    el("div", { class: "map-layout sessions-layout" },
      el("figure", {}, map, el("figcaption", { class: "caption" },
        tr("Outline: Office for National Statistics, Open Government Licence. Contains OS data © Crown copyright and database right.",
          "Amlinell: Swyddfa Ystadegau Gwladol, Trwydded Llywodraeth Agored. Yn cynnwys data'r Arolwg Ordnans © Hawlfraint y Goron a hawl cronfa ddata."))),
      list),
    el("section", { class: "add-session" },
      addHeading,
      el("p", {}, tr("If you know a session with a heavy focus on Welsh music, anywhere, tell us about it: this opens an email to Y Sesiwn, and we'll add it.",
        "Os ydych chi'n gwybod am sesiwn sy'n canolbwyntio'n drwm ar gerddoriaeth Gymreig, unrhyw le, rhowch wybod i ni: mae hyn yn agor e-bost i'r Sesiwn, a byddwn ni'n ei hychwanegu.")),
      addSessionForm()),
  ].filter(Boolean));
  show();  // now the map is on the page, its names can be placed
  // Come from a link to one session (sesiynau/#session-…, on the home page): its card,
  // after the page's own move to the top and its heading.
  const linked = location.hash.startsWith("#session-") && document.getElementById(decodeURIComponent(location.hash.slice(1)));
  if (linked) setTimeout(() => { linked.scrollIntoView({ block: "start" }); linked.focus({ preventScroll: true }); }, 0);
}

// ---- Installing the app ---------------------------------------------------------------
// Chrome and Edge (Android and desktop) say when the site can be installed, and let
// our own button open their install dialog. iPhones and iPads don't: there it's
// Share, then Add to Home Screen. Other browsers have it in their menu.

let installPrompt = null;
window.addEventListener("beforeinstallprompt", (event) => {
  event.preventDefault();  // no mini-infobar; our button asks instead
  installPrompt = event;
  refreshOfflineCards();
});
window.addEventListener("appinstalled", () => { installPrompt = null; askWorker("save-sounds"); refreshOfflineCards(); });

// A message for the service worker (sw.js), once it's running.
function askWorker(message) {
  navigator.serviceWorker?.ready.then((registration) => registration.active?.postMessage(message));
}

const isInstalled = () => matchMedia("(display-mode: standalone)").matches || navigator.standalone === true;
const isApple = () => /iPhone|iPad|iPod/.test(navigator.userAgent)
  || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);  // iPadOS says it's a Mac
const isPhone = () => isApple() || /Android|Mobi/.test(navigator.userAgent);  // phones and tablets
const isFirefox = () => /Firefox\//.test(navigator.userAgent);
const isMacSafari = () => /Macintosh/.test(navigator.userAgent) && /Version\/[\d.]+ Safari\//.test(navigator.userAgent)
  && !/Chrome|Chromium|Edg\//.test(navigator.userAgent) && !isApple();

// Browsers' own menus are rarely in Welsh, so their names stay in English.
const ui = (text) => el("strong", { lang: "en" }, text);

const SHARE_ICON = () => svg("svg", { viewBox: "0 0 24 24", class: "share-icon", "aria-label": "Share" },
  svg("path", { d: "M12 3v12M7.5 7.5 12 3l4.5 4.5M7 10.5H5.5v10h13v-10H17", fill: "none",
    stroke: "currentColor", "stroke-width": 1.8, "stroke-linecap": "round", "stroke-linejoin": "round" }));

function offlineCard({ full = false } = {}) {
  const card = el("section", { class: `offline-card${full ? " full" : ""}` });
  fillOfflineCard(card);
  return card;
}

function refreshOfflineCards() {
  document.querySelectorAll(".offline-card").forEach(fillOfflineCard);
}

function fillOfflineCard(card) {
  const full = card.classList.contains("full");
  const { saved, total } = state.sounds ?? {};
  const status = !("serviceWorker" in navigator) ? null
    : !state.offlineReady ? el("p", { class: "status" }, tr("Saving a copy for offline use…", "Wrthi'n cadw copi i'w ddefnyddio all-lein…"))
    : saved < total ? el("p", { class: "status" },
      tr("✓ Every tune is saved on this device. To play them back with no signal, save the piano sounds too (2 MB): ",
        "✓ Mae pob alaw wedi'i chadw ar y ddyfais hon. I'w chwarae heb signal, cadwch synau'r piano hefyd (2 MB): "),
      state.savingSounds ? tr("saving…", "wrthi'n cadw…")
        : el("button", { type: "button", class: "save-sounds", onclick: () => {
          state.savingSounds = true;
          askWorker("save-sounds");
          refreshOfflineCards();
        } }, tr("Save them now", "Eu cadw nawr")))
    : el("p", { class: "status" }, tr("✓ Saved on this device: works without a signal", "✓ Wedi'i chadw ar y ddyfais hon: mae'n gweithio heb signal"));
  // Already opened as an app: nothing to advertise on the home page.
  card.hidden = isInstalled() && !full;
  let how;
  if (isInstalled()) {
    how = el("p", {}, tr("You're using the app. Every tune, the playback and the map work offline.",
      "Rydych chi'n defnyddio'r ap. Mae pob alaw, y chwarae a'r map yn gweithio all-lein."));
  } else if (installPrompt) {
    how = el("button", { type: "button", class: "primary", onclick: async () => {
      installPrompt.prompt();
      await installPrompt.userChoice;
      installPrompt = null;
      refreshOfflineCards();
    } }, tr("Install the app", "Gosod yr ap"));
  } else if (isApple()) {
    how = el("ol", { class: "steps" },
      el("li", {}, tr("Tap ", "Tapiwch "), SHARE_ICON(), " ", ui("Share"),
        tr(" (at the bottom in Safari, or by the address bar).", " (ar y gwaelod yn Safari, neu wrth y bar cyfeiriad).")),
      el("li", {}, tr("Choose ", "Dewiswch "), ui("Add to Home Screen"), "."),
      el("li", {}, tr("Open Y Sesiwn from your home screen once while you have signal, so it can save its copy.",
        "Agorwch Y Sesiwn o'ch sgrin gartref unwaith tra bod gennych signal, er mwyn iddi gadw ei chopi.")));
  } else if (isPhone()) {
    how = el("p", {}, tr("In your browser's menu (", "Yn newislen eich porwr ("), el("strong", {}, "⋮"),
      tr("), choose ", "), dewiswch "), ui("Install app"), tr(" or ", " neu "), ui("Add to Home screen"), ".");
  } else if (isMacSafari()) {
    how = el("p", {}, tr("In Safari's menu bar, choose ", "Ym mar dewislen Safari, dewiswch "), ui("File → Add to Dock"),
      tr(" (macOS Sonoma or later). Y Sesiwn then opens from the Dock in its own window.",
        " (macOS Sonoma neu'n hwyrach). Wedyn mae Y Sesiwn yn agor o'r Doc yn ei ffenest ei hun."));
  } else if (isFirefox()) {
    how = el("p", {}, tr("Firefox can't install websites as apps, but you don't need to: once it's loaded, Y Sesiwn "
      + "works offline in this browser too. For an app with its own window, open it in Chrome, Edge or Safari.",
      "Ni all Firefox osod gwefannau fel apiau, ond does dim angen: unwaith y bydd wedi llwytho, mae Y Sesiwn yn "
      + "gweithio all-lein yn y porwr hwn hefyd. Am ap yn ei ffenest ei hun, agorwch hi yn Chrome, Edge neu Safari."));
  } else if (!full) {
    // Chrome or Edge on a computer when the browser doesn't offer our button (e.g. it's
    // already installed, or hasn't decided yet). The offline page's list says the same.
    how = el("p", {}, tr("Click the install icon at the right-hand end of the address bar, or open the browser's menu and look for ",
      "Cliciwch yr eicon gosod ym mhen draw'r bar cyfeiriad ar y dde, neu agorwch ddewislen y porwr a chwiliwch am "),
      ui("Install Y Sesiwn"), tr(" (in Chrome under ", " (yn Chrome o dan "), ui("Cast, save and share"),
      tr(", in Edge under ", ", yn Edge o dan "), ui("Apps"),
      tr("). It then opens in its own window, like any other program.", "). Wedyn mae'n agor yn ei ffenest ei hun, fel unrhyw raglen arall."));
  }
  card.replaceChildren(...[
    el("h2", {}, tr("Take it to the session", "Ewch â hi i'r sesiwn")),
    el("p", {}, isPhone() || isInstalled()
      ? tr("Add it to your home screen and every tune works in the pub, even with no signal.",
        "Ychwanegwch hi at eich sgrin gartref ac mae pob alaw'n gweithio yn y dafarn, hyd yn oed heb signal.")
      : tr("Install it and every tune works with no internet, like an app. On a phone, add it to your home screen.",
        "Gosodwch hi ac mae pob alaw'n gweithio heb y rhyngrwyd, fel ap. Ar ffôn, ychwanegwch hi at eich sgrin gartref.")),
    // The home page's card keeps to the browser's own install button; the steps are on the offline page.
    (full || installPrompt) && how ? how : null, status,
    full ? null : el("p", { class: "more" }, el("a", { href: "?page=offline", "data-route": true },
      tr("How to install it and use it offline", "Sut i'w gosod a'i defnyddio all-lein"))),
  ].filter(Boolean));
}

function renderOffline(main) {
  document.title = tr("Use it offline · Y Sesiwn", "Defnyddio all-lein · Y Sesiwn");
  const b = (text) => el("strong", {}, text);
  if (state.lang === "cy") {
    main.replaceChildren(
      el("h1", {}, "Defnyddio'r Sesiwn all-lein"),
      el("div", { class: "guide" },
        offlineCard({ full: true }),
        el("h2", {}, "Ar ffôn neu dabled"),
        el("ul", {},
          el("li", {}, b("iPhone neu iPad"), ": yn Safari (neu Chrome), ", ui("Share → Add to Home Screen"),
            "; yna agorwch hi o'r sgrin gartref unwaith tra bod gennych signal, i gadw ei chopi ei hun."),
          el("li", {}, b("Android"), ": y botwm ", b("Gosod yr ap"), " uchod, neu ddewislen y porwr (⋮) → ",
            ui("Install app"), " neu ", ui("Add to Home screen"), ".")),
        el("h2", {}, "Ar gyfrifiadur"),
        el("ul", {},
          el("li", {}, b("Chrome neu Edge"), " (Windows, Mac, Linux): y botwm ", b("Gosod yr ap"),
            " uchod, neu'r eicon gosod ym mhen draw'r bar cyfeiriad ar y dde."),
          el("li", {}, b("Safari ar Mac"), ": ", ui("File → Add to Dock"), " (macOS Sonoma neu'n hwyrach)."),
          el("li", {}, b("Firefox"), ": all e ddim gosod gwefannau fel apiau, ond mae'r Sesiwn yn dal i weithio all-lein yn y porwr unwaith y bydd wedi llwytho.")),
        el("h2", {}, "Sut mae'n gweithio"),
        el("p", {}, "Y tro cyntaf i chi agor y wefan, mae'n cadw copi ohoni'i hun yn dawel ar eich dyfais: pob alaw, ",
          "y map a'r tudalennau hyn, tua 1 MB. Wedi hynny mae'n gweithio heb gysylltiad, p'un a ydych chi'n ei gosod neu beidio."),
        el("p", {}, "Mae synau'r piano ar gyfer chwarae (2 MB arall) yn cael eu cadw i gyd ar gyfrifiadur ac yn yr ap wedi'i osod. ",
          "Mewn porwr ar ffôn, i arbed eich data, dim ond y nodau rydych chi wedi'u chwarae sy'n cael eu cadw, nes i chi ",
          "bwyso ", b("Eu cadw nawr"), " uchod."),
        el("p", {}, "Pan fydd alawon yn cael eu hychwanegu neu eu cywiro, fe'u gwelwch chi cyn gynted ag y byddwch chi ",
          "ar-lein, ac mae'ch copi ar y ddyfais yn cael ei ddiweddaru yn y cefndir.")));
    return;
  }
  main.replaceChildren(
    el("h1", {}, "Use Y Sesiwn offline"),
    el("div", { class: "guide" },
      offlineCard({ full: true }),
      el("h2", {}, "On a phone or tablet"),
      el("ul", {},
        el("li", {}, b("iPhone or iPad"), ": in Safari (or Chrome), ", b("Share → Add to Home Screen"),
          "; then open it from your home screen once while you have signal, so it keeps its own copy."),
        el("li", {}, b("Android"), ": the ", b("Install the app"), " button above, or the browser's menu (⋮) → ",
          b("Install app"), " or ", b("Add to Home screen"), ".")),
      el("h2", {}, "On a computer"),
      el("ul", {},
        el("li", {}, b("Chrome or Edge"), " (Windows, Mac, Linux): the ", b("Install the app"),
          " button above, or the install icon at the right-hand end of the address bar."),
        el("li", {}, b("Safari on a Mac"), ": ", b("File → Add to Dock"), " (macOS Sonoma or later)."),
        el("li", {}, b("Firefox"), ": it can't install websites as apps, but Y Sesiwn still works offline in the browser once it's loaded.")),
      el("h2", {}, "How it works"),
      el("p", {}, "The first time you open the site, it quietly saves a copy of itself on your ",
        "device: every tune, the map and these pages, about 1 MB. After that it works without a ",
        "connection, whether or not you install it."),
      el("p", {}, "The piano sounds for playback (another 2 MB) are all saved on a computer and in the installed ",
        "app. In a phone's browser, to spare your data, only the notes you've played are kept, until you press ",
        b("Save them now"), " above."),
      el("p", {}, "When tunes are added or corrected, you see them as soon as you're online, and the copy on your ",
        "device is brought up to date in the background.")));
}

// ---- Sets: tunes to play together, kept in the link --------------------------------------
// A set lives in its address: ?set=5A3V~g0b&n=Nos%20Iau. Each tune is its code from
// build_site.py: its number (tune_numbers.json, which never changes) in two characters
// of base 62, or "-" and three past 3,844 tunes, or, for a tune without a number yet,
// "." and its five-character short_id. "~" and a letter after one moves it (a -5 … l +6
// semitones; f would be none). A 100-tune set is a link of about 300 characters. Older
// links (?page=set&s=<short_id>.<short_id>~2&name=…) still open, in the new form.
// Your own sets are also kept in this browser (localStorage), with &my=<id> in their
// address; nothing is sent anywhere, and a shared link is the set itself.

const KEY_LETTERS = "abcdefghijkl";  // -5 … +6 semitones

const encodeSet = (items) => items.map(({ tune, key }) => tune.code + (key ? `~${KEY_LETTERS[key + 5]}` : "")).join("");

function decodeSet(text) {
  const items = [];
  let missing = 0;
  const codes = state.byCode;
  for (const m of (text ?? "").matchAll(/(\.[0-9a-z]{5}|-[0-9A-Za-z]{3}|[0-9A-Za-z]{2})(?:~([a-l]))?/g)) {
    // A tune without a number when the link was made may have one now: its short_id still finds it.
    const tune = codes.get(m[1]) ?? (m[1][0] === "." ? state.byId.get(m[1].slice(1)) : null);
    if (tune) items.push({ tune, key: m[2] ? KEY_LETTERS.indexOf(m[2]) - 5 : 0 });
    else missing++;
  }
  return { items, missing };
}

// The first form of set links, and of the sets kept in browsers: short_ids with dots.
function decodeLegacy(text) {
  const items = [];
  let missing = 0;
  for (const part of (text ?? "").split(".").filter(Boolean)) {
    const [id, key] = part.split("~");
    const tune = state.byId.get(id);
    if (tune) items.push({ tune, key: Math.max(-5, Math.min(6, Number(key) || 0)) });
    else missing++;
  }
  return { items, missing };
}

function setUrl(items, name, my = null) {
  let url = `?set=${encodeSet(items)}`;
  if (name) url += `&n=${encodeURIComponent(name)}`;
  if (my) url += `&my=${my}`;
  return url;
}

function loadSets() {
  let sets;
  try { sets = JSON.parse(localStorage.getItem("sets")); } catch { return []; }
  // Anything that isn't a set (edited by hand, an old bug) is left out, not let break the page.
  if (!Array.isArray(sets)) return [];
  sets = sets.filter((set) => typeof set?.id === "string" && (typeof set.c === "string" || typeof set.s === "string"));
  for (const set of sets) if (typeof set.name !== "string" || !set.name) set.name = defaultSetName();
  let changed = false;
  for (const set of sets) {  // kept in the first form: convert, once
    if (set.c == null) { set.c = encodeSet(decodeLegacy(set.s).items); delete set.s; changed = true; }
  }
  if (changed) saveSets(sets);
  return sets;
}
function saveSets(sets) {
  try { localStorage.setItem("sets", JSON.stringify(sets)); } catch {}
  keepStorage();
}
// Browsers may clear what a site keeps when space runs short (and Safari after a week
// without a visit); asking to keep it helps where it's granted without a question.
// Firefox would ask with a pop-up, so it isn't asked there: the links are the backup.
function keepStorage() {
  if (state.askedToKeep || /Firefox\//.test(navigator.userAgent)) return;
  state.askedToKeep = true;
  navigator.storage?.persist?.().catch(() => {});
}
function currentSetId() {
  try { return localStorage.getItem("currentSet"); } catch { return null; }
}
function setCurrentSet(id) {
  try { localStorage.setItem("currentSet", id); } catch {}
}
const newSetId = () => Math.random().toString(36).slice(2, 8);
const defaultSetName = () => tr("My set", "Fy set");
const tuneCount = (n) => tr(`${n} tune${n === 1 ? "" : "s"}`, `${n} alaw`);

// The tune page's button: adds this version, in the key chosen, to the set you're building.
function addToSetButton(tune, settings) {
  const status = el("span", { class: "caption add-status", "aria-live": "polite" });
  const button = el("button", { type: "button", class: "add-to-set", onclick: () => {
    const sets = loadSets();
    let set = sets.find((x) => x.id === currentSetId());
    if (!set) {
      set = { id: newSetId(), name: defaultSetName(), c: "" };
      sets.push(set);
      setCurrentSet(set.id);
    }
    const { items } = decodeSet(set.c);
    items.push({ tune, key: settings.transpose });
    set.c = encodeSet(items);
    set.updated = Date.now();
    saveSets(sets);
    status.replaceChildren(tr(`Added to ${set.name} (${tuneCount(items.length)}) · `, `Wedi'i hychwanegu at ${set.name} (${tuneCount(items.length)}) · `),
      el("a", { href: setUrl(items, set.name, set.id), "data-route": true }, tr("see the set", "gweld y set")));
  } }, tr("Add to set", "Ychwanegu at set"));
  return el("span", { class: "add-to-set-wrap" }, button, status);
}

// ?page=sets: the sets kept in this browser.
function renderSets(main) {
  document.title = tr("My sets · Y Sesiwn", "Fy setiau · Y Sesiwn");
  const draw = () => {
    const sets = loadSets().sort((a, b) => (b.updated ?? 0) - (a.updated ?? 0));
    const list = sets.length
      ? el("ul", { class: "set-list-mine" }, sets.map((set) => {
          const { items } = decodeSet(set.c);
          return el("li", {},
            el("a", { href: setUrl(items, set.name, set.id), "data-route": true, onclick: () => setCurrentSet(set.id) }, set.name),
            el("span", { class: "caption" }, ` · ${tuneCount(items.length)}${set.id === currentSetId() ? tr(" · adding to this one", " · yn ychwanegu at hon") : ""}`),
            el("button", { type: "button", class: "link-button", onclick: () => {
              if (!confirm(tr(`Delete “${set.name}”?`, `Dileu “${set.name}”?`))) return;
              saveSets(loadSets().filter((x) => x.id !== set.id));
              draw();
            } }, tr("Delete", "Dileu")));
        }))
      : el("div", {}, emptyArt("lovespoon"), el("p", {}, tr("No sets yet. Open a tune and press Add to set, or start one here.",
        "Dim setiau eto. Agorwch alaw a phwyso Ychwanegu at set, neu dechreuwch un yma.")));
    main.replaceChildren(...[
      el("h1", {}, tr("My sets", "Fy setiau")),
      el("p", { class: "lead" }, tr("Tunes to play together, in order and in the keys you choose: for a session, a workshop "
        + "or your practice. They're kept on this device; share one with its link or QR code.",
        "Alawon i'w chwarae gyda'i gilydd, yn eu trefn ac yn y cyweiriau a ddewiswch: ar gyfer sesiwn, gweithdy "
        + "neu eich ymarfer. Maen nhw'n cael eu cadw ar y ddyfais hon; rhannwch un gyda'i dolen neu ei god QR.")),
      el("p", { class: "sets-own" }, tr("Y Sesiwn doesn't come with ready-made sets, on purpose: finding which tunes sit well "
        + "together is part of the fun, so experiment and make your own.",
        "Does dim setiau parod ar Y Sesiwn, a hynny'n fwriadol: mae darganfod pa alawon sy'n mynd yn dda gyda'i gilydd "
        + "yn rhan o'r hwyl, felly arbrofwch a gwnewch rai eich hun.")),
      list,
      sets.length ? el("p", { class: "caption sets-backup" }, tr("Browsers sometimes clear what websites keep (Safari after a week "
        + "without a visit), and the sets stay on this device. Keep a copy of their links somewhere safe: open one to have it back. ",
        "Weithiau mae porwyr yn clirio'r hyn mae gwefannau'n ei gadw (Safari ar ôl wythnos heb ymweliad), ac mae'r setiau'n aros "
        + "ar y ddyfais hon. Cadwch gopi o'u dolenni yn rhywle diogel: agorwch un i'w chael yn ôl. "),
        el("button", { type: "button", class: "copy-all-sets", onclick: async (e) => {
          const text = loadSets().map((set) => `${set.name}\nhttps://ysesiwn.cymru/${setUrl(decodeSet(set.c).items, set.name)}`).join("\n\n");
          try { await navigator.clipboard.writeText(text); e.target.textContent = tr("✓ Links copied", "✓ Dolenni wedi'u copïo"); }
          catch { prompt(tr("Copy these links:", "Copïwch y dolenni hyn:"), text); }
        } }, tr("Copy all their links", "Copïo'u holl ddolenni"))) : null,
      el("p", {}, el("button", { type: "button", class: "primary", onclick: () => {
        const sets = loadSets();
        const set = { id: newSetId(), name: defaultSetName(), c: "", updated: Date.now() };
        saveSets([...sets, set]);
        setCurrentSet(set.id);
        navigate(setUrl([], set.name, set.id));
      } }, tr("New set", "Set newydd"))),
    ].filter(Boolean));
  };
  draw();
}

// A tune's music for a set: in its key, without chords; drawn when it's about to be seen.
function setScore(tune, key) {
  const paper = el("div", { class: "set-paper hide-chords" });
  paper.draw = () => {
    if (paper.drawn) return;
    paper.drawn = true;
    // The numbered heading above says which tune it is, so no title (T:) on the music.
    let abc = setTempo(stripFields(tune.abc, "SZBNAHTR"), tune.beat, tune.bpm);
    if (key) abc = ABCJS.strTranspose(abc, ABCJS.renderAbc("*", abc), semitones(tune, key));
    const layout = scoreLayout(paper);
    ABCJS.renderAbc(paper, shortCredits(abc, layout), { responsive: "resize", add_classes: true, paddingtop: 0, ...layout });
    hideMeasuring();
    nameScore(paper);
  };
  return paper;
}

function keyOptions(tune, key) {
  if (!tune.key) return [el("option", { value: 0, selected: true }, "—")];
  const { pitch, root } = tune.key;
  const mode = modeName(tune.key.modeName);
  return Array.from({ length: 12 }, (_, i) => i - 5).map((shift) => el("option", { value: shift, selected: shift === key },
    shift === 0 ? `${root} ${mode} ${tr("(original)", "(gwreiddiol)")}` : `${NOTES[(pitch + shift + 12) % 12]} ${mode}`));
}

// ?page=set: a set, from its link. Editing it changes the link (and, for your own
// sets, what's kept in this browser).
function renderSet(main) {
  const params = new URLSearchParams(location.search);
  const my = params.get("my");
  const mine = my && loadSets().find((x) => x.id === my);
  let { items, missing } = params.has("set") ? decodeSet(params.get("set")) : decodeLegacy(params.get("s"));
  let name = params.get("n") || params.get("name") || (mine ? mine.name : tr("A set", "Set"));
  // An older link (or a tune's longer code, from before it had a number): the address in
  // its shortest form, unless that would drop tunes the site doesn't have (any more).
  if (!params.has("set") || (!missing && params.get("set") !== encodeSet(items))) {
    history.replaceState(null, "", setUrl(items, name, mine ? my : null));
  }
  document.title = `${name} · Y Sesiwn`;
  const shareLink = () => `https://ysesiwn.cymru/${setUrl(items, name)}`;
  const save = () => {
    history.replaceState(null, "", setUrl(items, name, mine ? my : null));
    document.title = `${name} · Y Sesiwn`;
    if (!mine) return;
    const sets = loadSets();
    const set = sets.find((x) => x.id === my);
    if (set) Object.assign(set, { name, c: encodeSet(items), updated: Date.now() });
    saveSets(sets);
  };

  const list = el("ol", { class: "set-list" });
  const music = el("div", { class: "set-music" });
  const observer = new IntersectionObserver((entries) => {
    for (const e of entries) if (e.isIntersecting) { e.target.draw(); observer.unobserve(e.target); }
  }, { rootMargin: "800px" });
  const draw = () => {
    const move = (i, by) => { const [item] = items.splice(i, 1); items.splice(i + by, 0, item); save(); draw(); };
    list.replaceChildren(...items.map((item, i) => {
      const group = state.groups.get(item.tune.group);
      const several = group.versions.length > 1;
      const keySelect = el("select", { "aria-label": tr(`Key for ${item.tune.base}`, `Cywair ${item.tune.base}`),
        onchange: (e) => { item.key = +e.target.value; save(); draw(); } }, keyOptions(item.tune, item.key));
      return el("li", {},
        el("a", { href: tuneUrl(item.tune.group, item.tune.version), "data-route": true }, tuneName(item.tune.group, item.tune.base)),
        several ? el("span", { class: "caption" }, tr(` (version ${item.tune.version})`, ` (fersiwn ${item.tune.version})`)) : null,
        el("span", { class: "set-item-controls" }, keySelect,
          el("button", { type: "button", "aria-label": tr("Move up", "Symud i fyny"), disabled: i === 0, onclick: () => move(i, -1) }, "↑"),
          el("button", { type: "button", "aria-label": tr("Move down", "Symud i lawr"), disabled: i === items.length - 1, onclick: () => move(i, 1) }, "↓"),
          el("button", { type: "button", "aria-label": tr(`Remove ${item.tune.base}`, `Tynnu ${item.tune.base}`),
            onclick: () => { items.splice(i, 1); save(); draw(); } }, "✕")));
    }));
    observer.disconnect();
    music.replaceChildren(...items.map((item, i) => {
      const paper = setScore(item.tune, item.key);
      observer.observe(paper);
      return el("section", { class: "set-tune" }, el("h2", {}, `${i + 1}. `, tuneName(item.tune.group, item.tune.base)), paper);
    }));
    count.textContent = tuneCount(items.length);
    empty.hidden = items.length > 0;
    showPlace();
  };
  // Playing through a set: jump to the next tune's music, or back, without scrolling.
  const sections = () => [...music.children];
  // Which tune is at the top of the screen (-1: still above the first). The last ones may
  // be too short to scroll to the top: at the bottom of the page, the one jumped to.
  let jumped = -1;
  const below = () => {  // the top of the screen, under the bar that stays there on phones
    const bar = document.querySelector(".topbar");
    return (bar && getComputedStyle(bar).position === "sticky" ? bar.offsetHeight : 0) + 8;  // (stuck at the top: its height)
  };
  const place = () => {
    const line = below() + 40;
    const top = sections().filter((x) => x.getBoundingClientRect().top <= line).length - 1;
    const bottom = window.innerHeight + window.scrollY >= document.documentElement.scrollHeight - 2;
    return bottom ? Math.max(top, Math.min(jumped, items.length - 1)) : top;
  };
  const goTo = (i) => {
    const all = sections();
    if (!all[i]) return;
    for (const x of all.slice(0, i + 1)) x.querySelector(".set-paper").draw();  // so nothing above moves it later
    // And enough below for the page to scroll it to the top: stopped short at the bottom,
    // the music drawn there later would push it up and out of sight.
    for (const x of all.slice(i + 1)) {
      if (music.getBoundingClientRect().bottom - all[i].getBoundingClientRect().top >= window.innerHeight) break;
      x.querySelector(".set-paper").draw();
    }
    jumped = i;
    window.scrollTo({ top: window.scrollY + all[i].getBoundingClientRect().top - below() });
    showPlace();
  };
  const turn = (by) => goTo(Math.min(Math.max(place() + by, 0), items.length - 1));
  const where = el("span", { class: "set-nav-where", "aria-live": "polite" });
  const prev = el("button", { type: "button", "aria-label": tr("Previous tune", "Yr alaw flaenorol"), onclick: () => turn(-1) }, "‹");
  const next = el("button", { type: "button", "aria-label": tr("Next tune", "Yr alaw nesaf"), onclick: () => turn(1) }, "›");
  const nav = el("nav", { class: "set-nav", "aria-label": tr("Tunes in the set", "Alawon y set") }, prev, where, next);
  function showPlace() {
    const i = place();
    nav.hidden = items.length < 2;
    prev.disabled = i <= 0;
    next.disabled = i >= items.length - 1;
    where.textContent = i < 0 ? tuneCount(items.length) : `${i + 1} / ${items.length} · ${items[i].tune.base}`;
  }
  // Left and right arrows (what most page-turner pedals send), and swipes across the music.
  const onKey = (event) => {
    if (!music.isConnected) { document.removeEventListener("keydown", onKey); window.removeEventListener("scroll", onScroll); return; }
    if (event.ctrlKey || event.metaKey || event.altKey || event.target.closest("input, textarea, select, [contenteditable]")) return;
    if (event.key === "ArrowRight" || event.key === "ArrowLeft") { event.preventDefault(); turn(event.key === "ArrowRight" ? 1 : -1); }
  };
  let ticking = false;
  const onScroll = () => {
    if (!music.isConnected) { window.removeEventListener("scroll", onScroll); return; }
    if (!ticking) { ticking = true; requestAnimationFrame(() => { ticking = false; showPlace(); }); }
  };
  document.addEventListener("keydown", onKey);
  window.addEventListener("scroll", onScroll, { passive: true });
  let touch = null;
  music.addEventListener("touchstart", (e) => { touch = e.touches.length === 1 ? [e.touches[0].clientX, e.touches[0].clientY] : null; }, { passive: true });
  music.addEventListener("touchend", (e) => {
    if (!touch) return;
    const dx = e.changedTouches[0].clientX - touch[0], dy = e.changedTouches[0].clientY - touch[1];
    touch = null;
    if (Math.abs(dx) > 60 && Math.abs(dx) > 2 * Math.abs(dy)) turn(dx < 0 ? 1 : -1);
  });
  const count = el("span", { class: "caption" });
  const empty = el("div", { class: "set-empty" }, emptyArt("pibgorn"), el("p", { class: "caption" },
    tr("No tunes yet: add some with the box above, or with Add to set on a tune's page.",
      "Dim alawon eto: ychwanegwch rai gyda'r blwch uchod, neu gyda Ychwanegu at set ar dudalen alaw.")));
  // Adding tunes: type part of a name and press Enter (the arrow keys pick another
  // match); the box empties and stays ready for the next one.
  const added = el("p", { class: "caption set-added", "aria-live": "polite" });
  const addInput = el("input", { id: "set-add", type: "search", autocomplete: "off", spellcheck: "false",
    placeholder: tr("Add a tune: type its name, press Enter", "Ychwanegu alaw: teipiwch ei henw, pwyswch Enter"),
    role: "combobox", "aria-expanded": "false", "aria-controls": "set-add-list", "aria-autocomplete": "list" });
  const addList = el("ul", { id: "set-add-list", class: "suggestions", role: "listbox", hidden: true });
  attachSearch(addInput, addList, { showAllOnFocus: false, onPick: (group) => {
    items.push({ tune: group.versions[0], key: 0 });
    save();
    draw();
    added.textContent = tr(`Added ${group.title}.`, `Wedi ychwanegu ${group.title}.`);
  } });
  const addBox = el("div", { class: "search set-add" },
    el("label", { for: "set-add", class: "visually-hidden" }, tr("Add a tune to the set", "Ychwanegu alaw at y set")),
    addInput, addList);
  const title = mine
    ? el("input", { type: "text", class: "set-name", value: name, "aria-label": tr("Name of the set", "Enw'r set"),
        onchange: (e) => { name = e.target.value.trim() || defaultSetName(); save(); } })
    : el("h1", {}, name);
  const copy = el("button", { type: "button", onclick: async (e) => {
    try { await navigator.clipboard.writeText(shareLink()); e.target.textContent = tr("✓ Link copied", "✓ Dolen wedi'i chopïo"); }
    catch { prompt(tr("Copy this link:", "Copïwch y ddolen hon:"), shareLink()); }
  } }, tr("Copy link", "Copïo'r ddolen"));
  // The set as text to paste into a message or notes: its name, a bullet for each tune
  // (version and key), and the link.
  const asList = () => [name, ...items.map(({ tune, key }) => {
    const group = state.groups.get(tune.group);
    const version = group.versions.length > 1 ? tr(` (version ${tune.version})`, ` (fersiwn ${tune.version})`) : "";
    const keyName = tune.key ? `: ${NOTES[(tune.key.pitch + key + 12) % 12]} ${modeName(tune.key.modeName)}` : "";
    return `• ${tune.base}${version}${keyName}`;
  }), shareLink()].join("\n");
  const copyList = el("button", { type: "button", onclick: async (e) => {
    try { await navigator.clipboard.writeText(asList()); e.target.textContent = tr("✓ List copied", "✓ Rhestr wedi'i chopïo"); }
    catch { prompt(tr("Copy this list:", "Copïwch y rhestr hon:"), asList()); }
  } }, tr("Copy as a list", "Copïo fel rhestr"));
  const printAll = () => { for (const paper of music.querySelectorAll(".set-paper")) paper.draw(); window.print(); };
  // Printing with the browser's own menu: draw every score first. (Gone with the page.)
  const beforePrint = () => {
    if (!music.isConnected) { window.removeEventListener("beforeprint", beforePrint); return; }
    for (const paper of music.querySelectorAll(".set-paper")) paper.draw();
  };
  window.addEventListener("beforeprint", beforePrint);
  const saveButton = mine ? null : el("button", { type: "button", class: "primary", onclick: () => {
    const set = { id: newSetId(), name, c: encodeSet(items), updated: Date.now() };
    saveSets([...loadSets(), set]);
    setCurrentSet(set.id);
    navigate(setUrl(items, name, set.id));
  } }, tr("Save to my sets", "Cadw yn fy setiau"));

  main.replaceChildren(...[
    title,
    el("p", { class: "set-count" }, count, " · ", el("a", { href: "?page=sets", "data-route": true }, tr("My sets", "Fy setiau"))),
    missing ? el("p", { class: "caption" }, tr(missing === 1 ? "1 tune in this set isn't on the site any more."
      : `${missing} tunes in this set aren't on the site any more.`,
      `Dyw ${tuneCount(missing)} yn y set hon ddim ar y wefan bellach.`)) : null,
    el("div", { class: "set-actions" }, saveButton, shareButton(name, shareLink), copy, copyList,
      el("button", { type: "button", onclick: () => showQr(name, shareLink(),
        tr("Scan with a phone's camera to open this set.", "Sganiwch gyda chamera ffôn i agor y set hon.")) }, tr("QR code", "Cod QR")),
      el("button", { type: "button", onclick: printAll }, tr("Print", "Argraffu")),
      el("button", { type: "button", class: "practice-toggle", onclick: () => setPractice(!document.body.classList.contains("practice")) },
        practiceLabel(document.body.classList.contains("practice"))),
      musicSize(() => music.querySelectorAll(".set-paper").forEach((paper) => {
        if (paper.drawn) { paper.drawn = false; paper.draw(); }
      }))),
    addBox, added, empty, list,
    music, nav,
  ].filter(Boolean));
  if (mine) setCurrentSet(my);
  draw();
}

// ---- Writing to Y Sesiwn: sending a tune, the contact page ------------------------------

// The address is only put together when someone sends a message, so it never appears in
// the page, the HTML or the repository for address-collecting bots to find.
const MAILBOX = ["helo", "ysesiwn", "cymru"];
function mailAddress() {
  const [user, ...domain] = MAILBOX;
  return `${user}@${domain.join(".")}`;
}

function openMail(url) {  // its own function, so the tests can catch the email instead
  location.href = url;
}

// A form that opens the reader's email app with the message written out. Not everyone has
// an email app set up, so afterwards it also offers the message and address to copy.
function emailForm(fields, { subject, body, send = tr("Write the email", "Ysgrifennu'r e-bost") }) {
  const after = el("div", { class: "email-sent", role: "status" });
  const copyButton = (label, text) => el("button", { type: "button", onclick: async (e) => {
    try { await navigator.clipboard.writeText(text()); e.target.textContent = tr("✓ Copied", "✓ Wedi copïo"); }
    catch { e.target.textContent = tr("Couldn't copy", "Methu copïo"); }
  } }, label);
  const form = el("form", { class: "email-form", onsubmit: (e) => {
    e.preventDefault();
    const [to, s, b] = [mailAddress(), subject(), body()];
    openMail(`mailto:${to}?subject=${encodeURIComponent(s)}&body=${encodeURIComponent(b)}`);
    after.replaceChildren(
      el("p", {}, el("strong", {}, tr("Your email app should open with the message ready: just press send.",
        "Dylai eich ap e-bost agor gyda'r neges yn barod: dim ond pwyso anfon.")),
        tr(" Nothing opened, or the message is cut short? Copy it and send it from your email to ",
          " Dim byd wedi agor, neu mae'r neges wedi'i thorri'n fyr? Copïwch hi a'i hanfon o'ch e-bost i "),
        el("strong", { class: "address" }, to), "."),
      el("div", { class: "copy-actions" }, copyButton(tr("Copy the message", "Copïo'r neges"), () => `${s}\n\n${b}`),
        copyButton(tr("Copy the address", "Copïo'r cyfeiriad"), () => to)));
  } }, fields, el("button", { type: "submit", class: "primary" }, send));
  return el("div", {}, form, after);
}

function field(label, control, hint) {
  return el("label", { class: "field" }, el("span", { class: "field-label" }, label), control,
    hint ? el("span", { class: "caption" }, hint) : null);
}

// On "How to add a tune": send the tune by email, no GitHub needed.
function sendTuneForm() {
  const name = el("input", { type: "text", name: "name", required: true, autocomplete: "off" });
  const type = el("select", { name: "type" }, el("option", { value: "" }, tr("Not sure", "Ddim yn siŵr")),
    state.data.types.filter((t) => t.name !== "Other").map((t) => el("option", { value: t.name }, tr(`${t.name} (${t.english})`, t.name))),
    el("option", { value: "Other" }, typeName("Other")));
  const source = el("input", { type: "text", name: "source", required: true });
  const who = el("input", { type: "text", name: "who", autocomplete: "name" });
  const abc = el("textarea", { name: "abc", rows: 10, spellcheck: "false", class: "abc-input",
    placeholder: "X:1\nT:Llancesau Trefaldwyn\nR:jig\nM:6/8\nL:1/8\nK:D\nAG |: F2 F GFG | AFD DFA | …" });
  const permission = el("input", { type: "checkbox", name: "permission", required: true });
  const preview = el("div", { class: "score abc-preview", hidden: true });
  const problem = el("p", { class: "caption abc-problem" });
  let timer;
  abc.addEventListener("input", () => { clearTimeout(timer); timer = setTimeout(drawPreview, 300); });
  function drawPreview() {
    const text = abc.value.trim();
    preview.hidden = !text;
    problem.textContent = "";
    if (!text) return;
    const withHeader = /^X:/m.test(text) ? text : `X:1\n${text}`;
    const tune = ABCJS.renderAbc(preview, withHeader, { responsive: "resize", add_classes: true })[0];
    nameScore(preview);
    const notes = tune.lines.flatMap((l) => l.staff?.[0]?.voices?.[0] ?? []).filter((e) => e.el_type === "note");
    if (!/^K:/m.test(text)) {
      problem.textContent = tr("The ABC needs a K: line (the key) just before the notes.", "Mae angen llinell K: (y cywair) ar yr ABC yn union cyn y nodau.");
    } else if (!notes.length) {
      problem.textContent = tr("No notes found yet: they go on the lines after K:.", "Dim nodau eto: maen nhw'n mynd ar y llinellau ar ôl K:.");
    } else if (tune.warnings?.length) {  // abcjs's own messages are in English
      problem.textContent = `${tr("Something to check", "Rhywbeth i'w wirio")}: ${tune.warnings[0].replace(/<[^>]+>/g, "")}`;
    }
  }
  // The email is in the sender's language too; either way the subject starts with "Y Sesiwn".
  const form = emailForm([
    field(tr("Tune name", "Enw'r alaw"), name),
    field(tr("Type", "Math"), type),
    field(tr("Where it comes from", "O ble mae'n dod"), source, tr("A book, a recording, or who taught you it.", "Llyfr, recordiad, neu bwy a'i dysgodd i chi.")),
    field(tr("Your name (optional)", "Eich enw (dewisol)"), who, tr("To thank you on the tune's page, if you'd like.", "I ddiolch i chi ar dudalen yr alaw, os hoffech chi.")),
    field(tr("The tune in ABC notation (optional)", "Yr alaw mewn nodiant ABC (dewisol)"), abc,
      tr("No ABC? No problem: leave this empty and attach a photo of the sheet music or a recording to the email before you send it.",
        "Dim ABC? Dim problem: gadewch hwn yn wag ac atodwch lun o'r sgôr neu recordiad i'r e-bost cyn ei anfon.")),
    preview, problem,
    el("label", { class: "check" }, permission, tr(" It's a traditional tune, or I have permission to share it.",
      " Mae'n alaw draddodiadol, neu mae gen i ganiatâd i'w rhannu.")),
  ], {
    subject: () => tr(`Y Sesiwn tune: ${name.value.trim()}`, `Y Sesiwn, alaw: ${name.value.trim()}`),
    body: () => [
      `${tr("Tune", "Alaw")}: ${name.value.trim()}`,
      `${tr("Type", "Math")}: ${type.value || tr("not sure", "ddim yn siŵr")}`,
      `${tr("Where it comes from", "O ble mae'n dod")}: ${source.value.trim()}`,
      `${tr("From", "Gan")}: ${who.value.trim() || tr("(no name given)", "(dim enw)")}`,
      tr("Traditional, or shared with permission: yes", "Traddodiadol, neu wedi'i rhannu gyda chaniatâd: ydy"),
      "",
      abc.value.trim() ? `ABC:\n${abc.value.trim()}` : tr("No ABC: I've attached a photo or recording.", "Dim ABC: rwyf wedi atodi llun neu recordiad."),
      "",
    ].join("\n"),
  });
  return el("section", { class: "card send-tune" },
    el("h2", {}, tr("Send us a tune", "Anfonwch alaw aton ni")),
    el("p", {}, tr("The easiest way: fill this in and it opens an email to Y Sesiwn, ready to send. "
      + "We'll check the tune and add it to the site.",
      "Y ffordd hawsaf: llenwch hwn ac mae'n agor e-bost i'r Sesiwn, yn barod i'w anfon. "
      + "Byddwn ni'n gwirio'r alaw ac yn ei hychwanegu at y wefan.")),
    form);
}

// ?page=contact, and ?page=contact&about=<version's folder> from a tune's "Report a problem" link.
function renderContact(main) {
  document.title = tr("Contact · Y Sesiwn", "Cysylltu · Y Sesiwn");
  const tune = state.bySlug.get(movedTo(new URLSearchParams(location.search).get("about")));
  const group = tune && state.groups.get(tune.group);
  const about = tune ? `${group.title}${group.versions.length > 1 ? tr(` (version ${tune.version})`, ` (fersiwn ${tune.version})`) : ""}` : "";
  const subject = el("input", { type: "text", name: "subject", value: about ? tr(`About ${about}`, `Am ${about}`) : null });
  const message = el("textarea", { name: "message", rows: 8, required: true });
  const page = tune ? `https://ysesiwn.cymru/${tuneUrl(group.slug, tune.version)}` : null;
  main.replaceChildren(
    el("h1", {}, tr("Contact", "Cysylltu")),
    el("div", { class: "guide" },
      el("p", { class: "lead" }, tr("A question, an idea, a tune you're looking for, a mistake you've spotted, or just hello: "
        + "write it here and it opens an email to Y Sesiwn.",
        "Cwestiwn, syniad, alaw rydych chi'n chwilio amdani, camgymeriad rydych chi wedi sylwi arno, neu dim ond helo: "
        + "ysgrifennwch yma ac mae'n agor e-bost i'r Sesiwn.")),
      tune ? el("p", {}, tr("About ", "Am "), el("a", { href: tuneUrl(group.slug, tune.version), "data-route": true }, about),
        tr(": the tune's link goes in the message.", ": mae dolen yr alaw yn mynd yn y neges.")) : null,
      emailForm([field(tr("Subject (optional)", "Pwnc (dewisol)"), subject), field(tr("Your message", "Eich neges"), message)], {
        subject: () => `Y Sesiwn: ${subject.value.trim() || tr("a message", "neges")}`,
        body: () => [message.value.trim(), page ? `\n\n${tr("Tune", "Alaw")}: ${page}` : "", "\n"].join(""),
      }),
      el("p", { class: "caption" }, tr("Want to send a tune? ", "Eisiau anfon alaw? "),
        el("a", { href: "?page=add", "data-route": true }, tr("Use the tune form", "Defnyddiwch y ffurflen alawon")),
        tr(", which shows the sheet music as you type.", ", sy'n dangos y sgôr wrth i chi deipio."))));
}

// ---- Markdown pages: the guides (sections of CONTRIBUTING.md) and About -------------

function markdownSections(text) {
  // Split at "# " headings, but not at "# " lines inside ``` code blocks
  // (e.g. a shell comment in an example).
  const sections = [];
  let inCode = false;
  for (const line of text.split("\n")) {
    if (line.startsWith("```")) inCode = !inCode;
    if (!inCode && line.startsWith("# ")) sections.push([]);
    (sections.at(-1) ?? sections[sections.push([]) - 1]).push(line);
  }
  return sections.map((lines) => lines.join("\n"));
}

// The guides are Markdown from this repo, which anyone can suggest changes to: marked
// passes HTML in it through, so anything that could run (scripts, on… handlers,
// javascript: links, frames) is taken out before it goes on the page. A <template>'s
// contents are inert: nothing in them loads or runs while they're cleaned.
function cleanHtml(html) {
  const template = document.createElement("template");
  template.innerHTML = html;
  template.content.querySelectorAll("script, style, iframe, frame, object, embed, form, base, link, meta").forEach((n) => n.remove());
  for (const node of template.content.querySelectorAll("*")) {
    for (const { name, value } of [...node.attributes]) {
      if (/^on/i.test(name) || (/^(href|src|action|formaction|xlink:href)$/i.test(name) && /^\s*(javascript|data|vbscript):/i.test(value))) {
        node.removeAttribute(name);
      }
    }
  }
  return template.content;
}

// The Markdown reader (static/marked, 40 KB) is only needed for these pages, so it's
// loaded the first time one is opened.
let markedLibrary = null;
function loadMarked() {
  markedLibrary ??= new Promise((resolve, reject) => document.head.append(
    el("script", { src: "static/marked/marked.min.js", onload: resolve, onerror: reject })));
  return markedLibrary;
}

async function renderGuide(main, key) {
  const { className } = PAGES[key];
  const { file, heading } = state.lang === "cy" ? PAGES[key].cy : PAGES[key];
  document.title = `${heading} · Y Sesiwn`;
  main.replaceChildren(el("p", { class: "loading" }, tr("Loading…", "Yn llwytho…")));
  let html;
  try {
    if (!state.docs.has(file)) {
      const answer = await fetch(file);
      if (!answer.ok) throw new Error(`${file}: ${answer.status}`);
      state.docs.set(file, await answer.text());
    }
    const section = markdownSections(state.docs.get(file)).find((s) => s.startsWith(`# ${heading}\n`)) ?? "";
    await loadMarked();
    html = marked.parse(section.replaceAll("(#how-to-add-a-tune)", "(?page=add)"));
  } catch {
    if (new URLSearchParams(location.search).get("page") === key) {
      main.replaceChildren(el("h1", {}, heading), el("p", {}, tr("Couldn't load this page. Check your connection and try again.",
        "Methu llwytho'r dudalen hon. Gwiriwch eich cysylltiad a rhoi cynnig arall arni.")));
    }
    return;
  }
  const guide = el("article", { class: `guide ${className ?? ""}` });
  guide.append(cleanHtml(html));  // our own markdown, from this repo: still, nothing in it runs
  // CONTRIBUTING.md points GitHub readers to this form; here, it's right above.
  if (key === "add") guide.querySelector('a[href="https://ysesiwn.cymru/?page=add"]')?.closest("p").remove();
  // Links to the site itself (written in full for GitHub readers) stay on this copy of it.
  guide.querySelectorAll('a[href^="https://ysesiwn.cymru/?"]').forEach((a) => a.setAttribute("href", a.getAttribute("href").slice("https://ysesiwn.cymru/".length)));
  guide.querySelectorAll('a[href^="?"]').forEach((a) => a.setAttribute("data-route", ""));
  // Code examples scroll sideways on a phone; focusable, so the keyboard can scroll them too.
  guide.querySelectorAll("pre").forEach((pre) => pre.setAttribute("tabindex", "0"));
  if (key === "add") {  // the easy way first; the GitHub steps follow, folded away
    const steps = [...guide.children].slice(1);  // everything under the page's heading
    guide.querySelector("h1").after(sendTuneForm(),
      el("details", { class: "github-way" },
        el("summary", {}, el("h2", {}, tr("Or add it yourself on GitHub", "Neu ei hychwanegu eich hun ar GitHub"))), steps));
  }
  // Only show it if we're still on this page (the fetch may finish after leaving).
  if (new URLSearchParams(location.search).get("page") === key) main.replaceChildren(guide);
}

// ---- Sidebar search box ---------------------------------------------------------------

// onPick: what choosing a tune does (Enter, or a click); opening its page, unless the
// box is for something else (adding to a set), in which case it stays ready for the next.
// A name search that finds no tune is counted (the words only, once each per visit, after
// a pause in the typing), so the tunes people look for and don't find can be added.
// The privacy note on the About page says so.
const MISSED = new Set();
let missTimer = null;
function noteMiss(query, found) {
  clearTimeout(missTimer);
  const words = normalize(query).slice(0, 40);
  if (found || !state.complete || words.length < 3 || MISSED.has(words)) return;
  missTimer = setTimeout(() => {
    MISSED.add(words);
    countEvent(`search-miss/${words.replace(/ /g, "-")}`, `No tune found: ${words}`);
  }, 1500);
}

function attachSearch(input, list, { showAllOnFocus = true, onPick = null } = {}) {
  let results = [];
  let active = 0;
  // How many tunes the search finds, for screen readers (said once the typing pauses).
  const status = el("span", { class: "visually-hidden", role: "status" });
  list.after(status);
  let statusTimer = null;
  const say = (query) => {
    clearTimeout(statusTimer);
    statusTimer = setTimeout(() => {
      const n = results.length;
      status.textContent = !query.trim() ? ""
        : n === 0 ? tr("No tunes match that name.", "Does dim alaw â'r enw hwnnw.")
        : n >= 20 ? tr("20 tunes or more: keep typing to narrow it down.", "20 alaw neu fwy: daliwch ati i deipio i'w cyfyngu.")
        : tr(`${n} tune${n === 1 ? "" : "s"}: the arrow keys go through them.`, `${n} alaw: mae'r bysellau saeth yn mynd drwyddyn nhw.`);
    }, 500);
  };
  // Chrome makes a scrolling list a Tab stop; this one hides when the box loses focus,
  // which would drop focus onto the page. The arrow keys move through it instead.
  list.tabIndex = -1;

  const close = () => {
    list.hidden = true;
    input.setAttribute("aria-expanded", "false");
    input.removeAttribute("aria-activedescendant");
  };
  const open = (group) => {
    input.value = "";
    close();
    if (onPick) { onPick(group); return; }
    input.blur();
    navigate(tuneUrl(group.slug));
  };
  const show = () => {
    const query = input.value;
    if (!query.trim() && !showAllOnFocus) { results = []; close(); return; }
    results = query.trim() ? search(query).slice(0, 20) : state.groupList;
    noteMiss(query, results.length);
    say(query);
    active = 0;
    list.replaceChildren(...(results.length
      ? results.map((tune, i) => el("li", {
          role: "option", id: `${input.id}-option-${i}`, "aria-selected": String(i === active),
          onmousedown: (e) => { e.preventDefault(); open(tune); },
        }, tuneName(tune.slug, tune.title)))
      : [el("li", { class: "empty" }, state.complete ? tr("No tunes match that name.", "Does dim alaw â'r enw hwnnw.")
        : tr("Loading tunes…", "Yn llwytho'r alawon…"))]));
    list.hidden = false;
    input.setAttribute("aria-expanded", "true");
    // The first is picked already (Enter opens it), so a screen reader says it, and ↓ goes on to the second.
    if (results.length) input.setAttribute("aria-activedescendant", `${input.id}-option-0`);
    else input.removeAttribute("aria-activedescendant");
  };
  const highlight = (i) => {
    if (!results.length) return;
    active = (i + results.length) % results.length;
    [...list.children].forEach((li, j) => li.setAttribute("aria-selected", j === active));
    list.children[active].scrollIntoView({ block: "nearest" });
    input.setAttribute("aria-activedescendant", `${input.id}-option-${active}`);
  };

  input.addEventListener("input", show);
  input.addEventListener("focus", show);
  // Typed before every tune had come (on a tune's page): search again once they have.
  if (!state.complete) state.loaded?.then(() => { if (document.activeElement === input) show(); }, () => {});
  input.addEventListener("blur", close);
  input.addEventListener("keydown", (e) => {
    if (e.key === "ArrowDown") { e.preventDefault(); if (list.hidden) show(); else highlight(active + 1); }
    else if (e.key === "ArrowUp") { e.preventDefault(); highlight(active - 1); }
    else if (e.key === "Enter" && results.length && !list.hidden) { e.preventDefault(); open(results[active]); }
    else if (e.key === "Escape") close();
  });
}

// ---- Visit counts --------------------------------------------------------------------
// GoatCounter counts page views with no cookies and nothing that identifies anyone. Only
// the live site loads it (not a copy on your computer, or the tests), and pages change
// without reloading, so render() counts each one. Only these parts of the address are
// sent: never the notes typed into the notes search, or which tune a message is about.

const COUNTED_PARAMS = ["tune", "v", "page", "type", "key"];
let uncounted = null;  // a view before the counter has loaded

function viewPath() {
  const params = new URLSearchParams(location.search);
  const kept = new URLSearchParams([...params].filter(([name]) => COUNTED_PARAMS.includes(name)));
  if (params.has("set")) kept.set("page", "set");  // a set, but not which tunes
  return `${location.pathname}${kept.size ? `?${kept}` : ""}`;
}

function countView() {
  const view = { path: viewPath(), title: document.title };
  if (window.goatcounter?.count) window.goatcounter.count(view);
  else uncounted = view;
}

function countEvent(path, title) {
  window.goatcounter?.count?.({ path, title, event: true });
}

if (location.hostname === "ysesiwn.cymru") {
  document.head.append(el("script", {
    async: true, src: "https://gc.zgo.at/count.js",
    "data-goatcounter": "https://marcogorelli.goatcounter.com/count",
    "data-goatcounter-settings": JSON.stringify({ no_onload: true }),  // render() counts instead
    onload: () => { if (uncounted) window.goatcounter?.count?.(uncounted); uncounted = null; },
  }));
}

// ---- Start -----------------------------------------------------------------------------

const VERSION_SUFFIX = / \(version \d+\)$/;

function buildGroups() {
  // Versions of a tune ("Rheged", "Rheged (version 2)", …) share one page.
  for (const map of [state.bySlug, state.byId, state.byCode, state.groups, state.moved]) map.clear();  // built twice on a tune's page
  for (const tune of state.data.tunes) {
    tune.title = tune.titles[0];  // left out of tunes.json, as is the melody (melodyOf)
    tune.search = tune.titles.map(normalize);
    state.bySlug.set(tune.slug, tune);
    state.byId.set(tune.id, tune);
    state.byCode.set(tune.code, tune);
    if (!state.groups.has(tune.group)) state.groups.set(tune.group, { slug: tune.group, title: tune.base, versions: [] });
    state.groups.get(tune.group).versions.push(tune);
  }
  for (const group of state.groups.values()) {
    group.versions.sort((a, b) => a.version - b.version);
    group.type = group.versions[0].type;
    const titles = group.versions.flatMap((v) => v.titles.map((t) => t.replace(VERSION_SUFFIX, "")));
    group.titles = titles.filter((t, i) => titles.findIndex((u) => normalize(u) === normalize(t)) === i);
    group.search = group.titles.map(normalize);
  }
  state.groupList = [...state.groups.values()].sort((a, b) => (a.search[0] < b.search[0] ? -1 : 1));
  // A renamed tune: its old folder name, and its old codes in set links, find the new one.
  for (const move of state.data.moved ?? []) {
    state.moved.set(move.from, move.to);
    const tune = state.bySlug.get(move.to);
    if (!tune) continue;  // a tune's page, before the rest have come
    if (!state.byCode.has(move.code)) state.byCode.set(move.code, tune);
    if (!state.byId.has(move.id)) state.byId.set(move.id, tune);
  }
}

async function start() {
  // A tune's own page (alaw/<folder>/) comes with that tune's data, so its sheet music
  // can be drawn at once; every other tune (tunes.json, about 150 KB) follows.
  const own = document.getElementById("tune-data");
  state.loaded = (window.tunesJson ?? fetch("tunes.json")).then((answer) => {
    if (!answer.ok) throw new Error(`tunes.json: ${answer.status}`);
    return answer.json();
  });
  // The sidebar works from the start: on a tune's page, before every other tune has come
  // (its search finds more as they arrive).
  document.getElementById("surprise-sidebar").addEventListener("click", openRandomTune);
  document.getElementById("shortcuts-button").addEventListener("click", showShortcuts);
  document.getElementById("menu-button").addEventListener("click", () =>
    setMenu(!document.querySelector(".sidebar").classList.contains("menu-open")));
  for (const button of document.querySelectorAll(".lang-switch button")) {
    button.addEventListener("click", () => setLang(button.dataset.lang));
  }
  applyLang();
  document.querySelector(".skip-link").addEventListener("click", (e) => {
    e.preventDefault();
    document.getElementById("main").focus();
  });
  attachSearch(document.getElementById("search-input"), document.getElementById("suggestions"));
  if (own) {
    state.data = JSON.parse(own.textContent);
    buildGroups();
    render();
  }
  try {
    state.data = await state.loaded;
  } catch (error) {
    if (own) return;  // the tune is on the page already: keep it (other pages say so when opened)
    throw error;
  }
  state.complete = true;
  buildGroups();
  if (!own) render();
  (window.requestIdleCallback ?? setTimeout)(() => loadAbcjs().catch(() => {}));
}
// Offline use (sw.js): once the page has loaded, keep a copy of the whole site, so it
// works in a pub with no signal and can be added to the home screen as an app.
// The piano notes for playback (2 MB) are kept as they're played; all of them are saved
// at once in the installed app or on a computer, not on a phone's data unless asked.
if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => navigator.serviceWorker.register("sw.js").catch(() => {}));
  navigator.serviceWorker.addEventListener("message", (event) => {
    if (event.data?.sounds) { state.sounds = event.data.sounds; state.savingSounds = false; refreshOfflineCards(); }
  });
  // The worker only becomes active once every file is saved.
  navigator.serviceWorker.ready.then(() => {
    state.offlineReady = true;
    const allSounds = (isInstalled() || !isPhone()) && !navigator.connection?.saveData;
    askWorker(allSounds ? "save-sounds" : "sounds?");
    refreshOfflineCards();
  });
}

start().catch((error) => {
  document.getElementById("main").replaceChildren(el("p", {}, `${tr("Couldn't load the tunes", "Methu llwytho'r alawon")}: ${error}`));
});
