"use strict";
// Y Sesiwn: everything runs in the browser from tunes.json (see build_site.py).
// Pages: ./ (home), ?tune=<folder> (a tune), ?page=add / ?page=fix (guides).

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
const PAGES = {
  add: { file: "CONTRIBUTING.md", heading: "How to add a tune" },
  fix: { file: "CONTRIBUTING.md", heading: "How to submit corrections" },
  about: { file: "about.md", heading: "About Y Sesiwn", className: "about" },
};

const state = {
  data: null,
  bySlug: new Map(),    // every tune file ("version"), by folder name
  groups: new Map(),    // one page per tune: its versions, by the first version's folder
  groupList: [],        // groups sorted by title
  browseType: null,
  settings: new Map(),  // per tune: { transpose, bpm }, kept while the page is open
  synth: null,          // the playing SynthController, stopped when leaving a tune
  keyNote: null,        // the note sounding from the search-by-notes keyboard
  listening: null,      // the microphone, while "Play it to me" listens
  docs: new Map(),      // markdown files, fetched on first use
  chords: { onScore: false, play: "tune" },  // the chord box's settings, for every tune; play: tune, both or chords
};

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
      [score, how] = [6, "starts like this"];
    } else if (trimmed.some((q) => atStart(q) !== undefined)) {
      [score, how] = [5, "starts like this, after a different lead-in"];
    } else {
      const at = steps.indexOf(query);
      if (at >= 0) [score, where, how] = at <= 2 ? [4, at, "starts like this"] : [3, at, "later in the tune"];
    }
    if (score) { results.push({ tune, score, where, how }); continue; }
    // Not a match: how close is it? Near the start (with or without the tune's
    // lead-in) counts a note less than further in.
    const fromStart = Math.min(...[...starts].map((i) =>
      editDistance(query, steps.slice(i, i + query.length + 4), true, octaves)));
    const anywhere = editDistance(query, steps, false, octaves);
    const atStartToo = fromStart <= anywhere + 1;
    const off = atStartToo ? fromStart : anywhere;
    close.push({ tune, score: 0, where: atStartToo ? off : off + 1, close: true,
      how: `close: ${off} note${off > 1 ? "s" : ""} different${atStartToo ? ", near the start" : ""}` });
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
    .map((r) => ({ ...r, how: r.how.replace("close", "nearest") }));
  return [...found, ...near, ...more];
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
      type: "button", "aria-label": name.replace("#", " sharp "), title: name.replace("#", "♯"), "data-midi": midi,
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
  return el("div", { class: "piano", role: "group", "aria-label": "Piano keyboard, G3 to A5", style: `--whites: ${whites.length}` },
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
  // Raw sound: phone "voice" processing (echo and noise cancelling, level control) warps notes.
  const stream = await navigator.mediaDevices.getUserMedia({
    audio: { echoCancellation: false, noiseSuppression: false, autoGainControl: false },
  });
  const context = new AudioContext();
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

function notesSearch() {
  const input = el("input", {
    id: "notes-search", type: "text", autocomplete: "off", spellcheck: "false",
    placeholder: "e.g. D E F# G A (any key)", "aria-describedby": "notes-help",
  });
  const results = el("ol", { class: "notes-results", "aria-live": "polite" });
  const help = el("p", { id: "notes-help", class: "caption" });
  const update = () => {
    const found = searchByNotes(input.value);
    if (!found) {
      const n = collapse(parseNotes(input.value).map((x) => x.midi ?? x.pc)).length;
      help.textContent = n ? `Keep going: ${MIN_NOTES - n} more note${MIN_NOTES - n > 1 ? "s" : ""}.`
        : "Type or play the first few notes of a tune. The key doesn't matter.";
      results.replaceChildren();
      return;
    }
    const exact = found.filter((r) => !r.close).length;
    const closeOnes = found.filter((r) => r.how.startsWith("close")).length;
    const plural = (n) => `${n} tune${n > 1 ? "s" : ""}`;
    help.textContent = exact
      ? `${plural(exact)} with these notes${closeOnes ? `, then ${plural(closeOnes)} close to them` : ""}${found.length > 12 ? " (showing the best 12; add notes to narrow it down)" : ""}.`
      : closeOnes
        ? `No tunes with exactly these notes, but ${plural(closeOnes)} close to them${found.length > 12 ? " (showing the closest 12)" : ""}.`
        : "No tunes with these notes, or close to them. These are the nearest; check a note or two, or try fewer notes.";
    results.replaceChildren(...found.slice(0, 12).map(({ tune, how }) => {
      const several = state.groups.get(tune.group).versions.length > 1;
      return el("li", {},
        el("a", { href: tuneUrl(tune.group, tune.version), "data-route": true }, tune.base),
        el("span", { class: "caption" }, `${several ? ` (version ${tune.version})` : ""} · ${how}`));
    }));
  };
  input.addEventListener("input", update);
  const press = (name) => { input.value = `${input.value.trimEnd()} ${name}`.trimStart(); update(); };
  const piano = keyboard(press);
  const listenStatus = el("p", { class: "listen-status", "aria-live": "polite", hidden: true });
  const listenButton = el("button", { type: "button", class: "listen", onclick: () => toggleListening() });
  const micIcon = () => svg("svg", { viewBox: "0 0 24 24", class: "mic-icon", "aria-hidden": "true" },
    svg("rect", { x: 9, y: 3, width: 6, height: 11, rx: 3, fill: "currentColor" }),
    svg("path", { d: "M5.5 11a6.5 6.5 0 0 0 13 0M12 17.5V21M8.5 21h7", fill: "none", stroke: "currentColor",
      "stroke-width": 1.8, "stroke-linecap": "round" }));
  const showListening = (on) => {
    listenButton.replaceChildren(on ? "■ Stop listening" : micIcon(), on ? "" : " Play it to me");
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
    listenStatus.textContent = "Listening… play the first few notes of the tune on your instrument.";
    try {
      await startListening({
        onNote: (midi) => { press(NOTE_NAMES[midi % 12]); },
        onHear: light,
        onStop: (reason) => {
          showListening(false);
          light(null);
          listenStatus.textContent = reason === "done" && input.value ? "Stopped listening. Play it again, or add notes on the keyboard." : "";
          listenStatus.hidden = !listenStatus.textContent;
        },
      });
    } catch (error) {
      showListening(false);
      listenStatus.textContent = error.name === "NotAllowedError"
        ? "The microphone isn't allowed. Allow it for this site in your browser's settings, then try again."
        : "Couldn't use the microphone on this device.";
    }
  };
  showListening(false);
  const canListen = !!navigator.mediaDevices?.getUserMedia && "AudioContext" in window;
  const edit = el("div", { class: "note-edit" },
    canListen ? listenButton : null,
    el("button", { type: "button", "aria-label": "Delete last note", onclick: () => {
      input.value = input.value.trimEnd().replace(/\s*\S+$/, ""); update(); } }, "⌫ Delete"),
    el("button", { type: "button", onclick: () => { input.value = ""; update(); } }, "Clear"));
  update();
  return el("section", { class: "notes-search", id: "find-by-notes" },
    el("h2", { class: "section-heading" }, "Search by notes"),
    el("label", { for: "notes-search", class: "visually-hidden" }, "First notes of the tune"),
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
  const main = document.getElementById("main");
  if (!tune) setPractice(false);
  main.style.animation = "none"; void main.offsetWidth; main.style.animation = "";  // replay fade-in
  document.getElementById("home-button").disabled = !tune && !guide && !map && !offline;
  if (tune) renderTune(main, group, tune);
  else if (guide) renderGuide(main, guide);
  else if (map) renderMap(main);
  else if (offline) renderOffline(main);
  else renderHome(main);
}

// ---- Home page -----------------------------------------------------------------

function renderHome(main) {
  document.title = "Y Sesiwn";
  const { types, repo } = state.data;
  const tunes = state.groupList;  // one entry per tune, whatever its number of versions
  const colour = Object.fromEntries(types.map((t) => [t.name, t.colour]));

  const list = el("ul", { class: "tune-list" });
  const caption = el("p", { class: "caption" });
  const pills = el("div", { class: "pills", role: "group", "aria-label": "Tune type" });
  // No type selected (null) lists every tune; clicking the selected type again clears it.
  const showType = (name) => {
    state.browseType = name;
    const type = types.find((t) => t.name === name);
    for (const pill of pills.children) pill.setAttribute("aria-pressed", pill.dataset.type === name);
    caption.textContent = type ? `${type.count} ${type.english}` : `All ${tunes.length} tunes`;
    const listed = tunes.filter((t) => !type || t.type === name);
    list.replaceChildren(...listed.map((t) =>
      el("li", { style: `--c: ${colour[t.type]}` },
        el("span", { class: "swatch", title: t.type }),
        el("a", { href: tuneUrl(t.slug), "data-route": true }, t.title))));
  };
  for (const type of types) {
    pills.append(el("button", {
      type: "button", "data-type": type.name, style: `--c: ${type.colour}`,
      onclick: () => showType(state.browseType === type.name ? null : type.name),
    }, el("span", { class: "swatch" }), `${type.name} · ${type.count}`));
  }

  main.replaceChildren(
    el("h1", {}, "Croeso! Welcome to Y Sesiwn"),
    el("p", { class: "lead" },
      "Y Sesiwn is a ", el("strong", {}, "completely free and open-source"),
      ` resource to help you learn and share Welsh folk tunes: ${tunes.length} of them so far, `,
      "each with its sheet music. Search by name, browse by type below, or let chance decide."),
    heroSearch(tunes.length),
    el("button", { type: "button", class: "primary", onclick: openRandomTune }, "Surprise me"),
    features(),
    offlineCard(),
    notesSearch(),
    el("h2", { class: "section-heading" }, "Browse by type"),
    pills, caption, list,
  );
  showType(state.browseType);
}

function features() {
  // What the site does, in one list: each item's first words say it, the rest how.
  const link = (href, text) => el("a", { href, "data-route": href.startsWith("?") ? true : null }, text);
  const withChords = state.groupList.filter((g) => g.versions.some((v) => v.chords != null)).length;
  const items = [
    [["Find a tune by name"], ": typos, accents and other spellings are forgiven."],
    [[link("#find-by-notes", "Find a tune by its notes")], ": play the first few notes on the keyboard, type them, or play them on your instrument to the microphone, in any key."],
    [["Sheet music"], " for every tune, with the versions of a tune side by side."],
    [["Any key"], ": transpose a tune to suit your instrument, your voice or the session."],
    [["Play it back"], " at any tempo, with the notes lit up as they play, and loop it to practise."],
    [["Accompaniment"], `: suggested chords as a chart for guitar, piano or harp, played with or without the tune (${withChords} tunes so far, and growing).`],
    [["Practice mode"], " fills the screen with the music, for a tablet on a music stand; or ", ["print"], " it."],
    [[link("?page=map", "Tunes on the map")], ": the places in Wales that tunes are named after."],
    [[link("?page=offline", "Works offline")], ": install it on your phone and take every tune to the pub."],
    [["Free and open"], ": ", link("?page=add", "add a tune"), " or ", link("?page=fix", "suggest a correction"),
      "; everything is ", link(state.data.repo, "on GitHub"), "."],
  ];
  // [["words"]] is the bold lead-in (possibly a link); plain strings and links follow it.
  const bold = (part) => Array.isArray(part) ? el("strong", {}, part) : part;
  return el("section", { class: "features" },
    el("h2", { class: "section-heading" }, "What you can do"),
    el("ul", {}, items.map((parts) => el("li", {}, parts.map(bold)))));
}

function heroSearch(count) {
  const input = el("input", {
    id: "hero-search", type: "search", autocomplete: "off", spellcheck: "false",
    placeholder: `Search ${count} tunes by name…`, role: "combobox", "aria-expanded": "false",
    "aria-controls": "hero-suggestions", "aria-autocomplete": "list",
  });
  const list = el("ul", { id: "hero-suggestions", class: "suggestions", role: "listbox", hidden: true });
  // The list below already shows every tune, so only suggest once something is typed.
  attachSearch(input, list, { showAllOnFocus: false });
  return el("div", { class: "search hero-search" },
    el("label", { for: "hero-search", class: "visually-hidden" }, "Search tunes by name"),
    input, el("kbd", { class: "shortcut", title: "Press / to search" }, "/"), list);
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

class Cursor {  // highlights the notes as they play
  onEvent(event) {
    document.querySelectorAll(".abcjs-note_playing").forEach((n) => n.classList.remove("abcjs-note_playing"));
    if (event) event.elements.flat().forEach((n) => n.classList.add("abcjs-note_playing"));
  }
  onFinished() { this.onEvent(null); }
}

function stopPlayback() {
  if (state.synth) { state.synth.destroy(); state.synth = null; }
}

function drawScore(tune, paper, audio, chart) {
  stopPlayback();
  const { transpose, bpm } = state.settings.get(tune.slug);
  // S:, Z:, B: (book), N: (notes) and A: (area) are in the Details box, so leave
  // them off the score; the version tabs say which version it is.
  let abc = setTempo(stripFields(tune.abc, "SZBNA"), tune.beat, bpm).replace(/^(T:.*) \(version \d+\)$/m, "$1");
  if (transpose) {
    // strTranspose needs the whole array renderAbc returns, not its first tune.
    abc = ABCJS.strTranspose(abc, ABCJS.renderAbc("*", abc), transpose);
  }
  const visualObj = ABCJS.renderAbc(paper, accompaniment(abc, state.chords.play === "both"), { responsive: "resize", add_classes: true, paddingtop: 0 })[0];
  // Chords are always drawn (so playback has them), and hidden unless asked for.
  paper.classList.toggle("hide-chords", !state.chords.onScore);
  if (chart) chart.replaceChildren(chordChart(visualObj));
  const audioParams = { ...AUDIO_PARAMS, chordsOff: state.chords.play === "tune", voicesOff: state.chords.play === "chords" };

  audio.replaceChildren();
  if (!ABCJS.synth.supportsAudio()) {
    audio.textContent = "Audio is not supported in this browser.";
    return;
  }
  const controller = new ABCJS.synth.SynthController();
  controller.load(audio, new Cursor(), {
    displayLoop: true, displayRestart: true, displayPlay: true, displayProgress: true,
  });
  controller.setTune(visualObj, false, audioParams);
  state.synth = controller;
  // Fetch and decode this tune's notes now, so pressing play doesn't wait. The
  // audio stays paused until play is clicked; abcjs shares the decoded notes.
  new ABCJS.synth.CreateSynth().init({ visualObj, options: audioParams }).catch(() => {});
}

// ---- Chord chart -------------------------------------------------------------------
// Chord symbols in the ABC ("G"d2 cd) are shown as a chart for accompanists: one
// row per line of music, one cell per bar. It's made from the drawn tune, so it
// follows the key drop-down. Within a bar, each chord takes up as much room as it
// lasts (| G  D | is G on beat 1 and D on beat 3). A bar that doesn't start with a
// chord of its own begins with the one still sounding, shown faintly; a pick-up
// bar without a chord is left out.

const REPEAT_START = new Set(["bar_left_repeat", "bar_dbl_repeat"]);  // drawn as |: and :| by style.css
const REPEAT_END = new Set(["bar_right_repeat", "bar_dbl_repeat"]);

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
  return abc.replace(/^K:/m, `${lines.join("\n")}\nK:`);
}

function chordChart(visualObj) {
  const { num, den } = visualObj.getMeterFraction();
  let held = null, carry = null;
  const rows = [];
  for (const line of visualObj.lines) {
    const voice = line.staff?.[0]?.voices?.[0];
    if (!voice) continue;
    const bars = [];
    let bar = { chords: [], length: 0 };
    let tuplet = 1;  // a triplet's notes last 2/3 of their written length
    for (const item of voice) {
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
    if (bar.length) bars.push(bar);
    const cells = [];
    for (const b of bars) {
      if (carry) { if (!REPEAT_START.has(b.start)) b.start = carry.start; b.ending ??= carry.ending; carry = null; }
      if (!b.chords.length && (held === null || b.length < num / den - 1e-6)) {
        carry = b;  // a pick-up is left out; its repeat sign or ending goes on the next bar
        continue;
      }
      const classes = ["bar",
        REPEAT_START.has(b.start) ? "repeat-start" : null, REPEAT_END.has(b.end) ? "repeat-end" : null];
      // Each chord gets the share of the bar it lasts for, in percent (fr values that add
      // up to less than 1 would leave part of the bar empty).
      const parts = b.chords.map((c, i) => ({ name: c.name, from: c.at, to: b.chords[i + 1]?.at ?? b.length }));
      if (!parts.length || parts[0].from > 1e-6) parts.unshift({ name: held, from: 0, to: parts[0]?.from ?? b.length, held: true });
      cells.push(el("span", { class: classes.filter(Boolean).join(" ") },
        b.ending ? el("sup", {}, `${b.ending}.`) : null,
        el("span", { class: "beats", style: `grid-template-columns: ${parts.map((c) => `${(100 * (c.to - c.from)) / b.length}fr`).join(" ")}` },
          parts.map((c) => el("span", { class: c.held ? "held" : null }, c.name)))));
      held = b.chords.at(-1)?.name ?? held;
    }
    if (cells.length) rows.push(el("div", { class: "chart-row" }, cells));
  }
  // As many columns as the longest line has bars, so bars line up down the chart.
  const columns = Math.max(1, ...rows.map((row) => row.children.length));
  return el("div", { class: "chart", style: `--columns: ${columns}` }, rows);
}

function chordCard(tune, redraw) {
  if (tune.chords == null) return null;
  const showOnScore = el("label", { class: "switch" },
    el("input", { type: "checkbox", checked: state.chords.onScore,
      onchange: (e) => { state.chords.onScore = e.target.checked; redraw(); } }), "Show on the sheet music");
  const playback = el("div", { class: "segmented", role: "radiogroup", "aria-label": "Playback" },
    [["tune", "Tune only"], ["both", "Tune and chords"], ["chords", "Chords only"]].map(([value, label]) =>
      el("label", {},
        el("input", { type: "radio", name: "chord-playback", value, checked: state.chords.play === value,
          onchange: () => { state.chords.play = value; redraw(); } }),
        el("span", {}, label))));
  return el("section", { class: "card chords" },
    el("h2", {}, "Suggested chords"),
    el("div", { class: "chart-box" }),
    el("div", { class: "chord-controls" },
      el("div", { class: "playback" }, el("span", { class: "label" }, "Play"), playback), showOnScore),
    el("p", { class: "caption" },
      tune.chords ? `${tune.chords}. ` : "",
      "One way of accompanying it: use your ear, and your own."));
}

function renderTune(main, group, tune) {
  document.title = `${group.title} · Y Sesiwn`;
  if (!state.settings.has(tune.slug)) state.settings.set(tune.slug, { transpose: 0, bpm: tune.bpm });
  const settings = state.settings.get(tune.slug);

  const paper = el("div");
  const audio = el("div", { class: "audio" });
  const chords = chordCard(tune, () => redraw());
  const redraw = () => drawScore(tune, paper, audio, chords?.querySelector(".chart-box"));

  const controls = el("div", { class: "controls" });
  if (tune.key) {
    const { pitch, root, modeName } = tune.key;
    const select = el("select", { id: "key-select", onchange: (e) => { settings.transpose = +e.target.value; redraw(); } });
    for (let shift = -5; shift <= 6; shift++) {  // semitones, nearest direction
      const label = shift === 0 ? `${root} ${modeName} (original)` : `${NOTES[(pitch + shift + 12) % 12]} ${modeName}`;
      select.append(el("option", { value: shift, selected: shift === settings.transpose }, label));
    }
    controls.append(el("div", { class: "control" }, el("label", { for: "key-select" }, "Key"), select));
  }
  const tempoLabel = el("label", { for: "tempo" });
  const showTempo = () => { tempoLabel.textContent = `Tempo: ${settings.bpm} bpm (${tune.beatName} beats)`; };
  showTempo();
  const practice = el("button", { type: "button", class: "practice-toggle", onclick: () => setPractice(!document.body.classList.contains("practice")) });
  practice.textContent = document.body.classList.contains("practice") ? "Exit practice mode" : "Practice mode";
  controls.append(el("div", { class: "control tempo" }, tempoLabel,
    el("input", {
      id: "tempo", type: "range", min: 30, max: 200, value: settings.bpm,
      oninput: (e) => { settings.bpm = +e.target.value; showTempo(); },
      onchange: redraw,
    })), el("div", { class: "tune-actions" },
      el("button", { type: "button", onclick: () => window.print() }, "Print"), practice));

  const details = el("dl", {}, tune.details.map(([label, value]) => [el("dt", {}, label), el("dd", {}, value)]));
  const gloss = tune.gloss.length
    ? el("p", { class: "caption" }, tune.gloss.flatMap(([word, meaning], i) =>
        [i ? " · " : "", el("em", {}, word), ` = ${meaning}`]))
    : null;

  const versions = group.versions.length > 1
    ? el("nav", { class: "versions", "aria-label": "Versions of this tune" }, group.versions.map((v) =>
        el("a", {
          href: tuneUrl(group.slug, v.version), "data-route": true,
          class: v === tune ? "active" : null, "aria-current": v === tune ? "page" : null,
        }, el("span", {}, `Version ${v.version}`), v.source ? el("small", {}, v.source) : null)))
    : null;

  main.replaceChildren(...[
    el("h1", {}, group.title),
    group.titles.length > 1 ? el("p", { class: "caption aka" }, `Also known as: ${group.titles.slice(1).join(", ")}`) : null,
    versions,
    controls,
    el("div", { class: "tune-layout" },
      el("div", { class: "tune-main" }, el("div", { class: "score" }, audio, paper), chords),
      el("div", { class: "tune-side" },
        el("section", { class: "card" }, el("h2", {}, "Details"), details, gloss),
        placeCard(group),
        el("details", { class: "abc" }, el("summary", {}, "ABC notation"), el("pre", {}, stripFields(tune.abc, "Z"))))),
  ].filter(Boolean));
  redraw();
}

// Practice mode: hide everything but the controls and the score, full screen if possible.
function setPractice(on) {
  if (document.body.classList.contains("practice") === on) return;
  document.body.classList.toggle("practice", on);
  const button = document.querySelector(".practice-toggle");
  if (button) button.textContent = on ? "Exit practice mode" : "Practice mode";
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
      "aria-label": current ? `Map of Wales showing ${current.name}` : "Map of Wales with the places named in tune titles" },
      dots, targets));
}

function placeCard(group) {
  const place = state.data.places.find((p) => p.tunes.includes(group.slug));
  if (!place) return null;
  return el("section", { class: "card place" },
    el("h2", {}, place.name),
    walesMap(place),
    el("p", { class: "caption" }, el("a", { href: "?page=map", "data-route": true }, "All tunes on the map")));
}

function renderMap(main) {
  document.title = "Tunes on the map · Y Sesiwn";
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
  map.addEventListener("pointerover", (e) => { if (target(e)) show(state.data.places[target(e).dataset.place]); });
  map.addEventListener("pointerout", (e) => { if (target(e)) hideSoon(); });
  popup.addEventListener("pointerenter", () => clearTimeout(hideTimer));
  popup.addEventListener("pointerleave", hideSoon);
  // On a touchscreen, tapping elsewhere closes it.
  main.addEventListener("pointerdown", (e) => { if (!target(e) && !popup.contains(e.target)) hide(); });
  const list = el("ul", { class: "place-list" }, places.map((place) =>
    el("li", { onmouseenter: () => light(place, true), onmouseleave: () => light(place, false) },
      el("strong", {}, place.name), " ",
      place.tunes.map((slug, i) => [i ? ", " : "", el("a", { href: tuneUrl(slug), "data-route": true }, state.groups.get(slug).title)]))));
  main.replaceChildren(
    el("h1", {}, "Tunes on the map"),
    el("p", { class: "lead" }, `${places.length} places in Wales and just over the border that tunes are named after.`),
    el("div", { class: "map-layout" },
      el("figure", {}, map, el("figcaption", { class: "caption" },
        "Outline: Office for National Statistics, Open Government Licence. Contains OS data © Crown copyright and database right.")),
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
    ? el("p", { class: "status" }, state.offlineReady ? "✓ Saved on this device: works without a signal" : "Saving a copy for offline use…")
    : null;
  // Already opened as an app: nothing to advertise on the home page.
  card.hidden = isInstalled() && !full;
  let how;
  if (isInstalled()) {
    how = el("p", {}, "You're using the app. Every tune, the playback and the map work offline.");
  } else if (installPrompt) {
    how = el("button", { type: "button", class: "primary", onclick: async () => {
      installPrompt.prompt();
      await installPrompt.userChoice;
      installPrompt = null;
      refreshOfflineCards();
    } }, "Install the app");
  } else if (isApple()) {
    how = el("ol", { class: "steps" },
      el("li", {}, "Tap ", SHARE_ICON(), " ", el("strong", {}, "Share"), " (at the bottom in Safari, or by the address bar)."),
      el("li", {}, "Choose ", el("strong", {}, "Add to Home Screen"), "."),
      el("li", {}, "Open Y Sesiwn from your home screen once while you have signal, so it can save its copy."));
  } else {
    how = el("p", {}, "In your browser's menu, choose ", el("strong", {}, "Install app"), " or ",
      el("strong", {}, "Add to Home screen"), ". On a computer, look for the install icon in the address bar.");
  }
  card.replaceChildren(...[
    el("h2", {}, "Take it to the session"),
    el("p", {}, "Add Y Sesiwn to your home screen and it opens like an app, with every tune ",
      "saved on your phone: it works in the pub even with no signal."),
    how, status,
    full ? null : el("p", { class: "more" }, el("a", { href: "?page=offline", "data-route": true }, "More about using it offline")),
  ].filter(Boolean));
}

function renderOffline(main) {
  document.title = "Use it offline · Y Sesiwn";
  main.replaceChildren(
    el("h1", {}, "Use Y Sesiwn offline"),
    el("div", { class: "guide" },
      offlineCard({ full: true }),
      el("h2", {}, "How it works"),
      el("p", {}, "The first time you open the site, it quietly saves a copy of itself on your ",
        "device: every tune, the piano sounds for playback, the map and these pages, about 3 MB ",
        "in all. After that it works without a connection, whether or not you install it."),
      el("p", {}, "Installing it (adding it to your home screen) gives it its own icon and opens it ",
        "full screen, without the browser's address bar. On an iPhone or iPad the installed app ",
        "keeps its own copy, separate from Safari's, so open it once while you have signal."),
      el("p", {}, "When tunes are added or corrected, the new version downloads in the background ",
        "the next time you're online, and you'll see it from the next time you open Y Sesiwn.")));
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
  const { file, heading, className } = PAGES[key];
  document.title = `${heading} · Y Sesiwn`;
  main.replaceChildren(el("p", { class: "loading" }, "Loading…"));
  if (!state.docs.has(file)) state.docs.set(file, await (await fetch(file)).text());
  const text = state.docs.get(file);
  const section = markdownSections(text).find((s) => s.startsWith(`# ${heading}\n`)) ?? "";
  const html = marked.parse(section.replaceAll("(#how-to-add-a-tune)", "(?page=add)"));
  const guide = el("article", { class: `guide ${className ?? ""}` });
  guide.innerHTML = html;  // our own markdown, from this repo
  guide.querySelectorAll('a[href^="?"]').forEach((a) => a.setAttribute("data-route", ""));
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
      : [el("li", { class: "empty" }, "No tunes match that name.")]));
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
  document.getElementById("main").replaceChildren(el("p", {}, `Couldn't load the tunes: ${error}`));
});
