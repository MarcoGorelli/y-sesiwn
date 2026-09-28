"use strict";
// Y Sesiwn: everything runs in the browser from tunes.json (see build_site.py).
// Pages: ./ (home), ?tune=<folder> (a tune), ?page=add / ?page=fix (guides), ?page=contact, …

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
  data: null,
  bySlug: new Map(),    // every tune file ("version"), by folder name
  groups: new Map(),    // one page per tune: its versions, by the first version's folder
  groupList: [],        // groups sorted by title
  settings: new Map(),  // per tune: { transpose, bpm }, kept while the page is open
  synth: null,          // the playing SynthController, stopped when leaving a tune
  keyNote: null,        // the note sounding from the search-by-notes keyboard
  listening: null,      // the microphone, while "Play it to me" listens
  autoListen: false,    // start listening when the notes page opens (from the home page)
  docs: new Map(),      // markdown files, fetched on first use
  chords: { onScore: false, play: "tune" },  // the chord box's settings, for every tune; play: tune, both or chords
  practice: { countIn: false, click: false, tab: "none" },  // the practice row, for every tune
  lang: savedLang(),    // "cy" or "en", for the whole site (tune names and the tunes' own notes stay as written)
};

// ---- Welsh or English --------------------------------------------------------------

function savedLang() {
  try {
    const saved = localStorage.getItem("lang");
    if (saved === "cy" || saved === "en") return saved;
  } catch {}
  return (navigator.languages ?? [navigator.language]).some((l) => /^cy\b/i.test(l)) ? "cy" : "en";
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

function tuneSteps(tune) {
  const midis = [...tune.melody].map((c) => c.charCodeAt(0) - 160);  // see melody_string()
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
  return el("div", { class: "piano", role: "group", "aria-label": tr("Piano keyboard, G3 to A5", "Bysellfwrdd piano, G3 i A5"), style: `--whites: ${whites.length}` },
    whites, blacks);
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
  const analyser = context.createAnalyser();
  analyser.fftSize = 2048;  // ~45 ms of sound: two periods of the lowest note
  context.createMediaStreamSource(stream).connect(analyser);
  const samples = new Float32Array(analyser.fftSize);
  const started = performance.now();
  let candidate = null, since = 0, last = null, lastSound = started, heardAny = false, frame = 0;
  const listening = {
    stop(reason) {
      cancelAnimationFrame(frame);
      stream.getTracks().forEach((t) => t.stop());
      context.close().catch(() => {});
      if ("audioSession" in navigator) navigator.audioSession.type = "playback";
      if (state.listening === listening) state.listening = null;
      onStop(reason);
    },
  };
  state.listening = listening;
  const tick = (now) => {
    frame = requestAnimationFrame(tick);
    analyser.getFloatTimeDomainData(samples);
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
    if ((heardAny && now - lastSound > LISTEN.silence) || now - started > LISTEN.maxTime) {
      listening.stop("done");
    }
  };
  frame = requestAnimationFrame(tick);
}

function stopListening() {
  state.listening?.stop("left");
}

const micIcon = () => svg("svg", { viewBox: "0 0 24 24", class: "mic-icon", "aria-hidden": "true" },
  svg("rect", { x: 9, y: 3, width: 6, height: 11, rx: 3, fill: "currentColor" }),
  svg("path", { d: "M5.5 11a6.5 6.5 0 0 0 13 0M12 17.5V21M8.5 21h7", fill: "none", stroke: "currentColor",
    "stroke-width": 1.8, "stroke-linecap": "round" }));
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
  const button = el("button", { type: "button", class: "preview-play", "aria-label": tr(`Play the opening of ${tune.base}`, `Chwarae dechrau ${tune.base}`) }, "▶");
  const box = el("div", { class: "preview" }, button, paper);
  requestAnimationFrame(() => {
    const visualObj = ABCJS.renderAbc(paper, abc, { responsive: "resize", paddingtop: 0, paddingbottom: 0, add_classes: true })[0];
    nameScore(paper);
    // ▶ plays the opening; while it plays the button is ■, which stops it.
    let playing = null;
    const done = () => {
      playing = null;
      button.textContent = "▶";
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
      button.textContent = "■";
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
    ["Does dim ots am y cywair na'r wythfed: mae'r chwilio'n cymharu'r camau rhwng y nodau."],
    ["Mae nodyn anghywir, coll neu ychwanegol yn dal i ganfod yr alaw, ymhlith y cyfatebiaethau ", el("em", {}, "agos"),
      ". Os nad oes dim yn cyfateb, dangosir yr alawon agosaf."],
    ["Mae cyfeiriad y dudalen hon yn cadw'ch nodau, felly gallwch roi nod tudalen ar chwiliad neu ei anfon at rywun."],
  ] : [
    [el("strong", {}, "Play it to me"), " listens to a fiddle, whistle, flute or guitar through your ",
      "microphone and writes down the notes as you play (it doesn't work for humming). Nothing is recorded or sent anywhere."],
    ["Six to eight notes is usually plenty. A tune's lead-in notes can be left out, or played; ",
      "either way it's found."],
    ["The key and the octave don't matter: the search compares the steps between the notes."],
    ["A wrong, missing or extra note still finds the tune, among the ", el("em", {}, "close"),
      " matches. If nothing matches, the nearest tunes are shown."],
    ["The address of this page keeps your notes, so you can bookmark a search or send it to someone."],
  ];
  main.replaceChildren(
    el("h1", {}, tr("Find a tune by its notes", "Canfod alaw o'i nodau")),
    el("p", { class: "lead" }, tr("Know how a tune goes but not what it's called? Play its first few notes on your "
      + "instrument, tap them on the keyboard or type them. The key doesn't matter.",
      "Gwybod sut mae alaw'n mynd ond nid beth yw ei henw? Chwaraewch ei hychydig nodau cyntaf ar eich offeryn, "
      + "tapiwch nhw ar y bysellfwrdd neu teipiwch nhw. Does dim ots am y cywair.")),
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
        : tr("Type or play the first few notes of a tune. The key doesn't matter.",
          "Teipiwch neu chwaraewch ychydig nodau cyntaf alaw. Does dim ots am y cywair.");
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
        el("a", { href: tuneUrl(tune.group, tune.version), "data-route": true }, tune.base),
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
    listenButton.replaceChildren(on ? tr("■ Stop listening", "■ Stopio gwrando") : micIcon(), on ? "" : tr(" Play it to me", " Chwaraewch hi i mi"));
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
      input.value = input.value.trimEnd().replace(/\s*\S+$/, ""); update(); } }, tr("⌫ Delete", "⌫ Dileu")),
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

function tuneUrl(group, version = 1) {
  return `?tune=${encodeURIComponent(group)}${version > 1 ? `&v=${version}` : ""}`;
}

function navigate(url) {
  history.pushState(null, "", url);
  render();
  window.scrollTo(0, 0);
}

function openRandomTune() {
  const current = new URLSearchParams(location.search).get("tune");
  const choices = state.groupList.filter((g) => g.slug !== current);
  navigate(tuneUrl(choices[Math.floor(Math.random() * choices.length)].slug));
}

document.addEventListener("click", (event) => {
  const link = event.target.closest("a[data-route]");
  if (!link || event.metaKey || event.ctrlKey || event.shiftKey || event.button !== 0) return;
  event.preventDefault();
  navigate(link.getAttribute("href"));
});
window.addEventListener("popstate", render);

// "/" jumps to search from anywhere (the big box on the home page, else the sidebar's).
document.addEventListener("keydown", (event) => {
  if (event.key !== "/" || event.ctrlKey || event.metaKey || event.altKey) return;
  if (event.target.closest("input, textarea, select, [contenteditable]")) return;
  event.preventDefault();
  const box = document.getElementById("hero-search") ?? document.getElementById("search-input");
  if (document.body.classList.contains("practice")) setPractice(false);
  box.focus();
});

function render() {
  stopPlayback();
  stopListening();
  state.keyNote?.stop();
  const params = new URLSearchParams(location.search);
  let group = state.groups.get(params.get("tune"));
  let version = Number(params.get("v")) || 1;
  const file = state.bySlug.get(params.get("tune"));
  if (!group && file) {  // an old link to a version's own folder, e.g. ?tune=rheged-version-2
    [group, version] = [state.groups.get(file.group), file.version];
    history.replaceState(null, "", tuneUrl(group.slug, version));
  }
  const tune = group ? group.versions.find((v) => v.version === version) ?? group.versions[0] : null;
  const page = params.get("page");
  const guide = PAGES[page] ? page : null;
  const map = page === "map";
  const offline = page === "offline";
  const notes = page === "notes";
  const browse = page === "browse";
  const contact = page === "contact";
  const main = document.getElementById("main");
  if (!tune) setPractice(false);
  main.style.animation = "none"; void main.offsetWidth; main.style.animation = "";  // replay fade-in
  const home = !tune && !guide && !map && !offline && !notes && !browse && !contact;
  document.getElementById("home-button").disabled = home;
  main.lang = state.lang;
  if (tune) renderTune(main, group, tune);
  else if (guide) renderGuide(main, guide);
  else if (map) renderMap(main);
  else if (offline) renderOffline(main);
  else if (notes) renderNotesPage(main);
  else if (browse) renderBrowse(main);
  else if (contact) renderContact(main);
  else renderHome(main);
}

// ---- Home page -----------------------------------------------------------------

function renderHome(main) {
  document.title = "Y Sesiwn";
  const count = state.groupList.length;  // one entry per tune, whatever its number of versions
  main.replaceChildren(
    el("h1", {}, tr("Croeso! Welcome to Y Sesiwn", "Croeso i'r Sesiwn!")),
    el("p", { class: "lead" }, ...tr(
      ["Y Sesiwn is a ", el("strong", {}, "completely free and open-source"),
        ` resource to help you learn and share Welsh folk tunes: ${count} of them so far, `,
        "each with its sheet music. Search by name, browse by type and key, or let chance decide."],
      ["Mae'r Sesiwn yn adnodd ", el("strong", {}, "hollol am ddim a chod agored"),
        ` i'ch helpu i ddysgu a rhannu alawon gwerin Cymru: ${count} ohonyn nhw hyd yma, `,
        "pob un â'i sgôr. Chwiliwch yn ôl enw, porwch yn ôl math a chywair, neu gadewch i ffawd ddewis."])),
    heroSearch(count),
    el("div", { class: "home-actions" },
      el("button", { type: "button", class: "primary", onclick: openRandomTune }, tr("Surprise me", "Alaw ar hap")),
      el("a", { href: "?page=browse", "data-route": true, class: "button-link" },
        tr(`Browse all ${count} tunes`, `Pori'r ${count} alaw`))),
    notesInvite(),
    features(),
    offlineCard(),
  );
}

// ---- Browse page -------------------------------------------------------------------

// Every tune, narrowed down by type and key. The choice is kept in the address
// (?page=browse&type=Jig&key=D%20major), so "the jigs in D" can be shared.
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
  // Nothing selected (null) lists every tune; clicking the selected type or key again
  // clears it. A type and a key together list, say, the jigs in D major.
  const params = new URLSearchParams(location.search);
  let chosenType = types.some((t) => t.name === params.get("type")) ? params.get("type") : null;
  let chosenKey = keyCounts.has(params.get("key")) ? params.get("key") : null;
  const show = (name, key) => {
    [chosenType, chosenKey] = [name, key];
    const url = new URLSearchParams({ page: "browse" });
    if (name) url.set("type", name);
    if (key) url.set("key", key);
    history.replaceState(null, "", `?${url}`);
    const type = types.find((t) => t.name === name);
    for (const pill of pills.children) pill.setAttribute("aria-pressed", pill.dataset.type === name);
    for (const pill of keyPills.children) {
      // Each key's count among the tunes of the chosen type; keys it has none in are greyed out.
      const n = tunes.filter((t) => (!type || t.type === name) && keyOf(t) === pill.dataset.key).length;
      pill.setAttribute("aria-pressed", pill.dataset.key === key);
      pill.lastChild.textContent = String(n);
      pill.disabled = n === 0 && pill.dataset.key !== key;
    }
    const listed = tunes.filter((t) => (!type || t.type === name) && (!key || keyOf(t) === key));
    caption.textContent = state.lang === "cy"
      ? (type || key ? `${listed.length} ${type ? CY_TYPE[name] : "alaw"}${key ? ` yn ${keyLabel(key)}` : ""}` : `Y ${tunes.length} alaw i gyd`)
      : type || key
        ? `${listed.length} ${listed.length === 1 && type ? type.name.toLowerCase() : type ? type.english : listed.length === 1 ? "tune" : "tunes"}${key ? ` in ${key}` : ""}`
        : `All ${tunes.length} tunes`;
    list.replaceChildren(...listed.map((t) =>
      el("li", { style: `--c: ${colour[t.type]}` },
        el("span", { class: "swatch", title: typeName(t.type) }),
        el("a", { href: tuneUrl(t.slug), "data-route": true }, t.title))));
  };
  for (const type of types) {
    pills.append(el("button", {
      type: "button", "data-type": type.name, style: `--c: ${type.colour}`,
      onclick: () => show(chosenType === type.name ? null : type.name, chosenKey),
    }, el("span", { class: "swatch" }), `${typeName(type.name)} · ${type.count}`));
  }
  for (const [key, count] of [...keyCounts].sort((a, b) => b[1] - a[1])) {
    keyPills.append(el("button", {
      type: "button", "data-key": key, onclick: () => show(chosenType, chosenKey === key ? null : key),
    }, `${keyLabel(key)} ·\u00a0`, el("span", {}, String(count))));  // no-break: flex drops a plain trailing space
  }

  main.replaceChildren(
    el("h1", {}, tr("Browse by type and key", "Pori yn ôl math a chywair")),
    el("p", { class: "lead" }, tr("Pick a type of tune, a key, or both: the jigs in D, say, or everything in G.",
      "Dewiswch fath o alaw, cywair, neu'r ddau: y jigiau yn D, dyweder, neu bopeth yn G.")),
    el("p", { class: "pills-label" }, tr("Type", "Math")), pills,
    el("p", { class: "pills-label" }, tr("Key", "Cywair")), keyPills, caption, list,
  );
  show(chosenType, chosenKey);
}

// On the home page, the way into the notes page: "Play it to me" goes there and starts
// listening at once (the tap is still the go-ahead for the microphone and sound).
function notesInvite() {
  return el("section", { class: "notes-invite" },
    el("p", {}, el("strong", {}, tr("Know the tune but not its name?", "Gwybod yr alaw ond nid ei henw?")),
      tr(" Play it on your instrument, or tap the notes, and Y Sesiwn will find it.",
        " Chwaraewch hi ar eich offeryn, neu tapiwch y nodau, a daw'r Sesiwn o hyd iddi.")),
    el("div", { class: "invite-actions" },
      canListen() ? el("button", { type: "button", class: "primary listen-start",
        onclick: () => { state.autoListen = true; navigate("?page=notes"); } }, micIcon(), tr(" Play it to me", " Chwaraewch hi i mi")) : null,
      el("a", { href: "?page=notes", "data-route": true, class: "button-link" },
        tr("Tap or type the notes", "Tapio neu deipio'r nodau"))));
}

function features() {
  // What the site does, in one list: each item's first words say it, the rest how.
  const link = (href, text) => el("a", { href, "data-route": href.startsWith("?") ? true : null }, text);
  const withChords = state.groupList.filter((g) => g.versions.some((v) => v.chords != null)).length;
  const items = state.lang === "cy" ? [
    [["Canfod alaw wrth ei henw"], ": maddeuir gwallau teipio, acenion a sillafiadau eraill."],
    [[link("?page=notes", "Canfod alaw o'i nodau")], ": chwaraewch yr ychydig nodau cyntaf ar eich offeryn i'r meicroffon, tapiwch nhw ar y bysellfwrdd neu teipiwch nhw, mewn unrhyw gywair."],
    [["Sgôr"], " i bob alaw, gyda gwahanol fersiynau alaw ochr yn ochr."],
    [["Unrhyw gywair"], ": trawsgyweiriwch alaw i siwtio'ch offeryn, eich llais neu'r sesiwn."],
    [["Gwrandewch arni"], " ar unrhyw dempo, gyda'r nodau'n goleuo wrth iddyn nhw gael eu chwarae."],
    [["Ymarfer"], ": chwaraewch un rhan o alaw drosodd a throsodd gan gyflymu ychydig bob tro, gyda chyfrif i mewn a chlic os mynnwch, a ", ["thablatur"], " ar gyfer mandolin, ffidil neu gitâr."],
    [["Cyfeiliant"], `: cordiau awgrymedig fel siart ar gyfer gitâr, piano neu delyn, i'w chwarae gyda'r alaw neu hebddi (${withChords} o alawon hyd yma, a mwy i ddod).`],
    [["Modd ymarfer"], " sy'n llenwi'r sgrin â'r gerddoriaeth, ar gyfer llechen ar stand gerddoriaeth; neu ", ["argraffwch"], " hi."],
    [[link("?page=map", "Alawon ar y map")], ": y lleoedd yng Nghymru y mae alawon wedi'u henwi ar eu hôl."],
    [[link("?page=offline", "Gweithio all-lein")], ": gosodwch hi ar eich ffôn ac ewch â phob alaw i'r dafarn."],
    [[link("?page=browse", "Pori")], " yn ôl math a chywair: y jigiau yn D, dyweder, neu bopeth yn G."],
    [["Rhydd ac agored"], ": ", link("?page=add", "ychwanegwch alaw"), " neu ", link("?page=fix", "awgrymwch gywiriad"),
      "; mae popeth ", link(state.data.repo, "ar GitHub"), "."],
  ] : [
    [["Find a tune by name"], ": typos, accents and other spellings are forgiven."],
    [[link("?page=notes", "Find a tune by its notes")], ": play the first few notes on your instrument to the microphone, tap them on the keyboard or type them, in any key."],
    [["Sheet music"], " for every tune, with the versions of a tune side by side."],
    [["Any key"], ": transpose a tune to suit your instrument, your voice or the session."],
    [["Play it back"], " at any tempo, with the notes lit up as they play."],
    [["Practise"], ": loop one part of a tune and speed up a little each time round, with a count-in and a click if you like, and ", ["tablature"], " for mandolin, fiddle or guitar."],
    [["Accompaniment"], `: suggested chords as a chart for guitar, piano or harp, played with or without the tune (${withChords} tunes so far, and growing).`],
    [["Practice mode"], " fills the screen with the music, for a tablet on a music stand; or ", ["print"], " it."],
    [[link("?page=map", "Tunes on the map")], ": the places in Wales that tunes are named after."],
    [[link("?page=offline", "Works offline")], ": install it on your phone and take every tune to the pub."],
    [[link("?page=browse", "Browse")], " by type and key: the jigs in D, say, or everything in G."],
    [["Free and open"], ": ", link("?page=add", "add a tune"), " or ", link("?page=fix", "suggest a correction"),
      "; everything is ", link(state.data.repo, "on GitHub"), "."],
  ];
  // [["words"]] is the bold lead-in (possibly a link); plain strings and links follow it.
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

function stripFields(abc, fields) {
  // Header fields to leave off the score (abcjs would print them); they stay in the ABC view.
  return abc.split("\n").filter((line) => !new RegExp(`^[${fields}]:`).test(line)).join("\n");
}

function setTempo(abc, beat, bpm) {
  const tempo = `Q:${beat}=${bpm}`;
  return /^Q:/m.test(abc) ? abc.replace(/^Q:.*$/m, tempo) : abc.replace(/^K:/m, `${tempo}\nK:`);
}

// abcjs names each score "Sheet Music for "<title>"" (its <title> and aria-label), in English.
function nameScore(paper) {
  const score = paper.querySelector("svg");
  if (state.lang !== "cy" || !score) return;
  const welsh = (text) => text.replace(/^Sheet Music for /, "Sgôr ").replace(/^Sheet Music$/, "Sgôr");
  const title = score.querySelector("title");
  if (title) title.textContent = welsh(title.textContent);
  if (score.hasAttribute("aria-label")) score.setAttribute("aria-label", welsh(score.getAttribute("aria-label")));
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

// Looping one part: whenever playback reaches a note outside it (the player's own loop
// brings it back round at the end of the tune), jump to the part's first note, played
// the way it's written (its repeat included). With speedUp, each time round is 5%
// faster, up to the tune's usual tempo.
function partLoop(controller, part, tune, settings, onSpeed) {
  let jumping = false, inside = false;
  const firstNote = () => controller.timer.noteTimings.find((e) => e.type === "event" && e.startChar >= part.from && e.startChar < part.to);
  const jump = () => {
    jumping = true;
    const seek = () => controller.seek(firstNote().milliseconds / 1000, "seconds");
    const cap = Math.max(100, Math.round((100 * tune.bpm) / settings.bpm));
    if (settings.speedUp && inside && controller.warp < cap) {
      const warp = Math.min(cap, controller.warp + 5);
      onSpeed(warp);
      controller.setWarp(warp).then(seek);
    } else {
      seek();
    }
    inside = false;
  };
  return {
    onEvent(event) {
      if (event.startChar == null) return;  // a count-in click
      const within = event.startChar >= part.from && event.startChar < part.to;
      if (within) { jumping = false; inside = true; } else if (!jumping) jump();
    },
  };
}

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

function drawScore(tune, paper, audio, chart, onSpeed = () => {}) {
  stopPlayback();
  const { transpose, bpm } = state.settings.get(tune.slug);
  // S:, Z:, B: (book), N: (notes) and A: (area) are in the Details box, so leave
  // them off the score; the version tabs say which version it is.
  let abc = setTempo(stripFields(tune.abc, "SZBNA"), tune.beat, bpm).replace(/^(T:.*) \(version \d+\)$/m, "$1");
  if (transpose) {
    // strTranspose needs the whole array renderAbc returns, not its first tune.
    abc = ABCJS.strTranspose(abc, ABCJS.renderAbc("*", abc), transpose);
  }
  const tab = TABS[state.practice.tab];
  const visualObj = ABCJS.renderAbc(paper, accompaniment(abc, state.chords.play === "both"),
    { responsive: "resize", add_classes: true, paddingtop: 0, ...(tab ? { tablature: [{ ...tab, label: tab.label() }] } : {}) })[0];
  nameScore(paper);
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
    ...clickParams(visualObj, tune) };
  const settings = state.settings.get(tune.slug);
  const parts = tuneParts(visualObj);
  const part = parts[settings.loop];

  audio.replaceChildren();
  if (!ABCJS.synth.supportsAudio()) {
    audio.textContent = tr("Audio is not supported in this browser.", "Dyw'r porwr hwn ddim yn gallu chwarae sain.");
    return;
  }
  const controller = new ABCJS.synth.SynthController();
  const cursor = new Cursor();
  controller.load(audio, cursor, {
    displayLoop: true, displayRestart: true, displayPlay: true, displayProgress: true,
  });
  if (state.lang === "cy") {  // load() doesn't pass abcjs's title options on, so set them here
    for (const [button, title] of [["loop", "Chwarae unwaith neu drosodd a throsodd."], ["reset", "Yn ôl i'r dechrau."],
      ["start", "Chwarae / oedi."], ["progress-background", "Symud i fan arall yn yr alaw."]]) {
      audio.querySelector(`.abcjs-midi-${button}`)?.setAttribute("title", title);
      audio.querySelector(`.abcjs-midi-${button}`)?.setAttribute("aria-label", title);
    }
  }
  controller.setTune(visualObj, false, audioParams);
  state.synth = controller;
  // setWarp (the speed-up) also updates abcjs's own tempo box, which isn't shown.
  if (controller.control) controller.control.setWarp = () => {};
  if (part) {
    // The player's own loop brings playback round again after the last part.
    cursor.loop = partLoop(controller, part, tune, settings, onSpeed);
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
const CY_CHORD_SOURCES = { "From the Alawon Cymru score": "O sgôr Alawon Cymru" };

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

function printButton(tune, paper) {
  if (tune.chords == null) return el("button", { type: "button", onclick: () => printAs("music", paper) }, tr("Print", "Argraffu"));
  const menu = el("div", { class: "print-menu", role: "menu", hidden: true },
    [["music", tr("Sheet music", "Sgôr")], ["with-chords", tr("Sheet music with chords", "Sgôr gyda chordiau")],
      ["chart", tr("Chord chart", "Siart cordiau")]].map(([mode, label]) =>
      el("button", { type: "button", role: "menuitem", onclick: () => { menu.hidden = true; printAs(mode, paper); } }, label)));
  const toggle = el("button", { type: "button", "aria-haspopup": "menu", "aria-expanded": "false", onclick: () => {
    menu.hidden = !menu.hidden;
    toggle.setAttribute("aria-expanded", String(!menu.hidden));
  } }, tr("Print ▾", "Argraffu ▾"));
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
  Discography: "Disgograffi", History: "Hanes", Notes: "Nodiadau" };

function renderTune(main, group, tune) {
  document.title = `${group.title} · Y Sesiwn`;
  if (!state.settings.has(tune.slug)) state.settings.set(tune.slug, { transpose: 0, bpm: tune.bpm, loop: -1, speedUp: false });
  const settings = state.settings.get(tune.slug);

  const paper = el("div");
  const audio = el("div", { class: "audio" });
  const chords = chordCard(tune, () => redraw());
  const speedNote = el("span", { class: "caption speed-note", "aria-live": "polite" });
  const onSpeed = (warp) => {
    const bpm = Math.round((settings.bpm * warp) / 100);
    speedNote.textContent = tr(`now ${bpm} bpm`, `nawr ${bpm} curiad y funud`);
  };
  let drawn = { parts: [] };
  const redraw = () => {
    speedNote.textContent = "";
    drawn = drawScore(tune, paper, audio, chords?.querySelector(".chart-box"), onSpeed);
  };

  const controls = el("div", { class: "controls" });
  if (tune.key) {
    const { pitch, root } = tune.key;
    const mode = modeName(tune.key.modeName);
    const select = el("select", { id: "key-select", onchange: (e) => { settings.transpose = +e.target.value; redraw(); } });
    for (let shift = -5; shift <= 6; shift++) {  // semitones, nearest direction
      const label = shift === 0 ? `${root} ${mode} ${tr("(original)", "(gwreiddiol)")}` : `${NOTES[(pitch + shift + 12) % 12]} ${mode}`;
      select.append(el("option", { value: shift, selected: shift === settings.transpose }, label));
    }
    controls.append(el("div", { class: "control" }, el("label", { for: "key-select" }, tr("Key", "Cywair")), select));
  }
  const tempoLabel = el("label", { for: "tempo" });
  const showTempo = () => {
    tempoLabel.textContent = tr(`Tempo: ${settings.bpm} bpm (${tune.beatName} beats)`,
      `Tempo: ${settings.bpm} curiad y funud (curiad ${CY_BEATS[tune.beatName] ?? tune.beatName})`);
  };
  showTempo();
  const practice = el("button", { type: "button", class: "practice-toggle", onclick: () => setPractice(!document.body.classList.contains("practice")) });
  practice.textContent = practiceLabel(document.body.classList.contains("practice"));
  controls.append(el("div", { class: "control tempo" }, tempoLabel,
    el("input", {
      id: "tempo", type: "range", min: 30, max: 200, value: settings.bpm,
      oninput: (e) => { settings.bpm = +e.target.value; showTempo(); },
      onchange: redraw,
    })), el("div", { class: "tune-actions" },
      printButton(tune, paper), practice));

  const details = el("dl", {}, tune.details.map(([label, value]) =>
    [el("dt", {}, tr(label, CY_DETAILS[label] ?? label)), el("dd", {}, label === "Key" ? keyLabel(value) : value)]));
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

  // The practice row: loop a part (and speed up each time), count-in, click, tablature.
  const loopSelect = el("select", { id: "loop-select", onchange: (e) => { settings.loop = +e.target.value; redraw(); } });
  const toggle = (label, checked, onchange, cls) => el("label", { class: `switch${cls ? ` ${cls}` : ""}` },
    el("input", { type: "checkbox", checked, onchange: (e) => { onchange(e.target.checked); redraw(); } }), label);
  const tabSelect = el("select", { id: "tab-select", onchange: (e) => { state.practice.tab = e.target.value; redraw(); } },
    [["none", tr("No tablature", "Dim tablatur")], ["mandolin", tr("Mandolin / fiddle", "Mandolin / ffidil")],
      ["guitar", tr("Guitar", "Gitâr")]].map(([value, label]) =>
      el("option", { value, selected: state.practice.tab === value }, label)));
  const practiceRow = el("div", { class: "practice-row" },
    el("div", { class: "control" }, el("label", { for: "loop-select" }, tr("Loop", "Ailadrodd")), loopSelect),
    toggle(tr("Speed up each time", "Cyflymu bob tro"), settings.speedUp, (on) => { settings.speedUp = on; }, "speed-up"),
    speedNote,
    toggle(tr("Count-in", "Cyfrif i mewn"), state.practice.countIn, (on) => { state.practice.countIn = on; }),
    toggle(tr("Click", "Clic"), state.practice.click, (on) => { state.practice.click = on; }),
    el("div", { class: "control" }, el("label", { for: "tab-select" }, tr("Tablature", "Tablatur")), tabSelect));
  const fillLoops = () => {
    loopSelect.replaceChildren(el("option", { value: -1 }, tr("The whole tune", "Yr alaw gyfan")),
      ...drawn.parts.map((p, i) => el("option", { value: i, selected: settings.loop === i }, tr(`Part ${p.label}`, `Rhan ${p.label}`))));
    loopSelect.disabled = drawn.parts.length < 2;
    practiceRow.querySelector(".speed-up").hidden = settings.loop < 0;
  };
  loopSelect.addEventListener("change", fillLoops);

  const report = el("a", { class: "report", href: reportUrl(group, tune) }, tr("Report a problem with this tune", "Rhoi gwybod am broblem gyda'r alaw hon"));

  main.replaceChildren(...[
    el("h1", {}, group.title),
    group.titles.length > 1 ? el("p", { class: "caption aka" }, `${tr("Also known as", "Enwau eraill")}: ${group.titles.slice(1).join(", ")}`) : null,
    versions,
    controls,
    practiceRow,
    el("div", { class: "tune-layout" },
      el("div", { class: "tune-main" }, el("div", { class: "score" }, audio, chordPlayback(tune, () => redraw()), paper), chords),
      el("div", { class: "tune-side" },
        el("section", { class: "card" }, el("h2", {}, tr("Details", "Manylion")), details, gloss || null),
        placeCard(group),
        el("details", { class: "abc" }, el("summary", {}, tr("ABC notation", "Nodiant ABC")), el("pre", { tabindex: 0 }, stripFields(tune.abc, "Z"))),
        el("p", { class: "report-line" }, report, el("br"), el("span", { class: "caption" },
          tr("(needs a free GitHub account), or ", "(angen cyfrif GitHub am ddim), neu "),
          el("a", { href: `?page=contact&about=${tune.slug}`, "data-route": true }, tr("write to us", "ysgrifennwch aton ni")))))),
  ].filter(Boolean));
  redraw();
  fillLoops();
}

// A new GitHub issue about this tune, with its name, page and file filled in.
function reportUrl(group, tune) {
  const page = `https://ysesiwn.cymru/${tuneUrl(group.slug, tune.version)}`;
  const body = [
    `**Tune:** ${group.title}${group.versions.length > 1 ? ` (version ${tune.version})` : ""}`,
    `**Page:** ${page}`,
    `**File:** \`tunes/${tune.slug}/tune.abc\``,
    "",
    "**What's wrong?** (for example: a wrong note in bar 5 of part B, a missing repeat, the title)",
    "",
    "",
  ].join("\n");
  const title = `Problem with ${group.title}${group.versions.length > 1 ? ` (version ${tune.version})` : ""}`;
  return `${state.data.repo}/issues/new?title=${encodeURIComponent(title)}&body=${encodeURIComponent(body)}`;
}

const practiceLabel = (on) => (on ? tr("Exit practice mode", "Gadael y modd ymarfer") : tr("Practice mode", "Modd ymarfer"));

// Practice mode: hide everything but the controls and the score, full screen if possible.
function setPractice(on) {
  if (document.body.classList.contains("practice") === on) return;
  document.body.classList.toggle("practice", on);
  const button = document.querySelector(".practice-toggle");
  if (button) button.textContent = practiceLabel(on);
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

function walesMap(current = null) {
  // wales.svg is only the outline, used as a mask so the land takes the page's
  // colours (also in dark mode); the places are dots in an SVG on top of it.
  const [width, height] = state.data.mapSize;
  const { places } = state.data;
  const dots = places.map((place) => svg("circle", {
    cx: place.x, cy: place.y, r: place === current ? 3.6 : 2.2,
    class: current ? (place === current ? "here" : "other") : null,
  }, current ? svg("title", {}, place.name) : null));
  if (current) dots.push(dots.splice(places.indexOf(current), 1)[0]);  // drawn on top
  // The full map gets bigger invisible targets over the small dots, for pointing and tapping.
  const targets = current ? [] : places.map((place, i) =>
    svg("circle", { cx: place.x, cy: place.y, r: 5, class: "target", "data-place": i }));
  return el("div", { class: "wales-map", style: `aspect-ratio: ${width} / ${height}` },
    svg("svg", { viewBox: `0 0 ${width} ${height}`, role: "img",
      "aria-label": current ? tr(`Map of Wales showing ${current.name}`, `Map o Gymru yn dangos ${current.name}`)
        : tr("Map of Wales with the places named in tune titles", "Map o Gymru gyda'r lleoedd a enwir yn nheitlau alawon") },
      dots, targets));
}

function placeCard(group) {
  const place = state.data.places.find((p) => p.tunes.includes(group.slug));
  if (!place) return null;
  return el("section", { class: "card place" },
    el("h2", {}, place.name),
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
  let shown = null, hideTimer = null;
  const hide = () => { if (shown) light(shown, false); shown = null; popup.hidden = true; };
  const hideSoon = () => { clearTimeout(hideTimer); hideTimer = setTimeout(hide, 250); };
  const show = (place) => {
    clearTimeout(hideTimer);
    if (shown === place) return;
    hide();
    shown = place;
    light(place, true);
    const [width, height] = state.data.mapSize;
    const x = place.x / width, y = place.y / height;
    popup.replaceChildren(el("strong", {}, place.name), el("ul", {}, place.tunes.map((slug) =>
      el("li", {}, el("a", { href: tuneUrl(slug), "data-route": true }, state.groups.get(slug).title)))));
    // Above the dot, or below it near the top; kept inside the map at the sides.
    Object.assign(popup.style, { left: `${x * 100}%`, top: `${y * 100}%` });
    popup.dataset.side = y < 0.3 ? "below" : "above";
    popup.dataset.align = x < 0.3 ? "left" : x > 0.7 ? "right" : "centre";
    popup.hidden = false;
  };
  const target = (event) => event.target.closest?.(".target");
  const place = (e) => state.data.places[target(e).dataset.place];
  map.addEventListener("pointerover", (e) => { if (target(e) && e.pointerType !== "touch") show(place(e)); });
  // A touch "leaves" the dot as soon as the finger lifts: only a mouse closes it that way.
  map.addEventListener("pointerout", (e) => { if (target(e) && e.pointerType !== "touch") hideSoon(); });
  // Tapping (or clicking) a dot opens its popup, and it stays open until you tap elsewhere.
  map.addEventListener("click", (e) => { if (target(e)) show(place(e)); });
  popup.addEventListener("pointerenter", () => clearTimeout(hideTimer));
  popup.addEventListener("pointerleave", (e) => { if (e.pointerType !== "touch") hideSoon(); });
  // On a touchscreen, tapping elsewhere closes it.
  main.addEventListener("pointerdown", (e) => { if (!target(e) && !popup.contains(e.target)) hide(); });
  const list = el("ul", { class: "place-list" }, places.map((place) =>
    el("li", { onmouseenter: () => light(place, true), onmouseleave: () => light(place, false) },
      el("strong", {}, place.name), " ",
      place.tunes.map((slug, i) => [i ? ", " : "", el("a", { href: tuneUrl(slug), "data-route": true }, state.groups.get(slug).title)]))));
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
window.addEventListener("appinstalled", () => { installPrompt = null; refreshOfflineCards(); });

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
  const status = "serviceWorker" in navigator
    ? el("p", { class: "status" }, state.offlineReady
      ? tr("✓ Saved on this device: works without a signal", "✓ Wedi'i chadw ar y ddyfais hon: mae'n gweithio heb signal")
      : tr("Saving a copy for offline use…", "Wrthi'n cadw copi i'w ddefnyddio all-lein…"))
    : null;
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
  } else {
    // Chrome or Edge on a computer when the browser doesn't offer our button (e.g. it's
    // already installed, or hasn't decided yet).
    how = el("p", {}, tr("Click the install icon at the right-hand end of the address bar, or open the browser's menu and look for ",
      "Cliciwch yr eicon gosod ym mhen draw'r bar cyfeiriad ar y dde, neu agorwch ddewislen y porwr a chwiliwch am "),
      ui("Install Y Sesiwn"), tr(" (in Chrome under ", " (yn Chrome o dan "), ui("Cast, save and share"),
      tr(", in Edge under ", ", yn Edge o dan "), ui("Apps"),
      tr("). It then opens in its own window, like any other program.", "). Wedyn mae'n agor yn ei ffenest ei hun, fel unrhyw raglen arall."));
  }
  card.replaceChildren(...[
    el("h2", {}, tr("Take it to the session", "Ewch â hi i'r sesiwn")),
    el("p", {}, isPhone() || isInstalled()
      ? tr("Add Y Sesiwn to your home screen and it opens like an app, with every tune saved on your phone: it works in the pub even with no signal.",
        "Ychwanegwch Y Sesiwn at eich sgrin gartref ac mae'n agor fel ap, gyda phob alaw wedi'i chadw ar eich ffôn: mae'n gweithio yn y dafarn hyd yn oed heb signal.")
      : tr("Install Y Sesiwn on this computer and it opens like an app, in its own window, with every tune saved: it works even with no internet. (On a phone, add it to your home screen.)",
        "Gosodwch Y Sesiwn ar y cyfrifiadur hwn ac mae'n agor fel ap, yn ei ffenest ei hun, gyda phob alaw wedi'i chadw: mae'n gweithio hyd yn oed heb y rhyngrwyd. (Ar ffôn, ychwanegwch hi at eich sgrin gartref.)")),
    how, status,
    full ? null : el("p", { class: "more" }, el("a", { href: "?page=offline", "data-route": true },
      tr("More about using it offline", "Rhagor am ei defnyddio all-lein"))),
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
          el("li", {}, b("iPhone neu iPad"), ": yn Safari (neu Chrome), ", ui("Share → Add to Home Screen"), "."),
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
          "synau'r piano ar gyfer chwarae, y map a'r tudalennau hyn, tua 3 MB i gyd. Wedi hynny mae'n gweithio heb ",
          "gysylltiad, p'un a ydych chi'n ei gosod neu beidio."),
        el("p", {}, "Mae ei gosod yn rhoi ei heicon ei hun iddi ac yn ei hagor heb far cyfeiriad y porwr: sgrin lawn ",
          "ar ffôn (o'r sgrin gartref), yn ei ffenest ei hun ar gyfrifiadur (o'r Doc, y ddewislen Start neu'r bwrdd ",
          "gwaith). Ar iPhone neu iPad mae'r ap wedi'i osod yn cadw ei gopi ei hun, ar wahân i un Safari, felly ",
          "agorwch ef unwaith tra bod gennych signal."),
        el("p", {}, "Pan fydd alawon yn cael eu hychwanegu neu eu cywiro, mae'r fersiwn newydd yn llwytho i lawr yn y ",
          "cefndir y tro nesaf y byddwch chi ar-lein, ac fe'i gwelwch o'r tro nesaf y byddwch chi'n agor Y Sesiwn.")));
    return;
  }
  main.replaceChildren(
    el("h1", {}, "Use Y Sesiwn offline"),
    el("div", { class: "guide" },
      offlineCard({ full: true }),
      el("h2", {}, "On a phone or tablet"),
      el("ul", {},
        el("li", {}, b("iPhone or iPad"), ": in Safari (or Chrome), ", b("Share → Add to Home Screen"), "."),
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
        "device: every tune, the piano sounds for playback, the map and these pages, about 3 MB ",
        "in all. After that it works without a connection, whether or not you install it."),
      el("p", {}, "Installing it gives it its own icon and opens it without the browser's address bar: ",
        "full screen on a phone (from the home screen), in its own window on a computer (from the Dock, ",
        "Start menu or desktop). On an iPhone or iPad the installed app keeps its own copy, separate ",
        "from Safari's, so open it once while you have signal."),
      el("p", {}, "When tunes are added or corrected, the new version downloads in the background ",
        "the next time you're online, and you'll see it from the next time you open Y Sesiwn.")));
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

// ?page=contact, and ?page=contact&about=<version's folder> from a tune's "write to us" link.
function renderContact(main) {
  document.title = tr("Contact · Y Sesiwn", "Cysylltu · Y Sesiwn");
  const tune = state.bySlug.get(new URLSearchParams(location.search).get("about"));
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

async function renderGuide(main, key) {
  const { className } = PAGES[key];
  const { file, heading } = state.lang === "cy" ? PAGES[key].cy : PAGES[key];
  document.title = `${heading} · Y Sesiwn`;
  main.replaceChildren(el("p", { class: "loading" }, tr("Loading…", "Yn llwytho…")));
  if (!state.docs.has(file)) state.docs.set(file, await (await fetch(file)).text());
  const text = state.docs.get(file);
  const section = markdownSections(text).find((s) => s.startsWith(`# ${heading}\n`)) ?? "";
  const html = marked.parse(section.replaceAll("(#how-to-add-a-tune)", "(?page=add)"));
  const guide = el("article", { class: `guide ${className ?? ""}` });
  guide.innerHTML = html;  // our own markdown, from this repo
  // CONTRIBUTING.md points GitHub readers to this form; here, it's right above.
  if (key === "add") guide.querySelector('a[href="https://ysesiwn.cymru/?page=add"]')?.closest("p").remove();
  // Links to the site itself (written in full for GitHub readers) stay on this copy of it.
  guide.querySelectorAll('a[href^="https://ysesiwn.cymru/?"]').forEach((a) => a.setAttribute("href", a.getAttribute("href").slice("https://ysesiwn.cymru/".length)));
  guide.querySelectorAll('a[href^="?"]').forEach((a) => a.setAttribute("data-route", ""));
  // Code examples scroll sideways on a phone; focusable, so the keyboard can scroll them too.
  guide.querySelectorAll("pre").forEach((pre) => pre.setAttribute("tabindex", "0"));
  if (key === "add") {  // the easy way first; the GitHub steps follow
    guide.querySelector("h1").after(sendTuneForm(),
      el("h2", {}, tr("Or add it yourself on GitHub", "Neu ei hychwanegu eich hun ar GitHub")));
  }
  // Only show it if we're still on this page (the fetch may finish after leaving).
  if (new URLSearchParams(location.search).get("page") === key) main.replaceChildren(guide);
}

// ---- Sidebar search box ---------------------------------------------------------------

function attachSearch(input, list, { showAllOnFocus = true } = {}) {
  let results = [];
  let active = 0;

  const close = () => { list.hidden = true; input.setAttribute("aria-expanded", "false"); };
  const open = (group) => { input.value = ""; close(); input.blur(); navigate(tuneUrl(group.slug)); };
  const show = () => {
    const query = input.value;
    if (!query.trim() && !showAllOnFocus) { results = []; close(); return; }
    results = query.trim() ? search(query).slice(0, 20) : state.groupList;
    active = 0;
    list.replaceChildren(...(results.length
      ? results.map((tune, i) => el("li", {
          role: "option", id: `${input.id}-option-${i}`, "aria-selected": i === active,
          onmousedown: (e) => { e.preventDefault(); open(tune); },
        }, tune.title))
      : [el("li", { class: "empty" }, tr("No tunes match that name.", "Does dim alaw â'r enw hwnnw."))]));
    list.hidden = false;
    input.setAttribute("aria-expanded", "true");
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
  input.addEventListener("blur", close);
  input.addEventListener("keydown", (e) => {
    if (e.key === "ArrowDown") { e.preventDefault(); if (list.hidden) show(); else highlight(active + 1); }
    else if (e.key === "ArrowUp") { e.preventDefault(); highlight(active - 1); }
    else if (e.key === "Enter" && results.length && !list.hidden) { e.preventDefault(); open(results[active]); }
    else if (e.key === "Escape") close();
  });
}

// ---- Start -----------------------------------------------------------------------------

const VERSION_SUFFIX = / \(version \d+\)$/;

function buildGroups() {
  // Versions of a tune ("Rheged", "Rheged (version 2)", …) share one page.
  for (const tune of state.data.tunes) {
    state.bySlug.set(tune.slug, tune);
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
}

async function start() {
  state.data = await (await fetch("tunes.json")).json();
  buildGroups();
  document.getElementById("home-button").addEventListener("click", () => navigate("./"));
  document.getElementById("surprise-sidebar").addEventListener("click", openRandomTune);
  for (const button of document.querySelectorAll(".lang-switch button")) {
    button.addEventListener("click", () => setLang(button.dataset.lang));
  }
  applyLang();
  attachSearch(document.getElementById("search-input"), document.getElementById("suggestions"));
  render();
}
// Offline use (sw.js): once the page has loaded, keep a copy of the whole site, so it
// works in a pub with no signal and can be added to the home screen as an app.
if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => navigator.serviceWorker.register("sw.js").catch(() => {}));
  // The worker only becomes active once every file is saved.
  navigator.serviceWorker.ready.then(() => { state.offlineReady = true; refreshOfflineCards(); });
}

start().catch((error) => {
  document.getElementById("main").replaceChildren(el("p", {}, `${tr("Couldn't load the tunes", "Methu llwytho'r alawon")}: ${error}`));
});
