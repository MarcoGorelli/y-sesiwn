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
  docs: new Map(),      // markdown files, fetched on first use
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

function score(query, tune) {
  // 1 for a substring match, otherwise the average word-by-word similarity,
  // so small typos ("trefalwdyn") still match.
  let best = 0;
  for (const title of tune.search) {
    if (title.includes(query)) return 1;
    const titleWords = title.split(/\s+/).filter(Boolean);
    const queryWords = query.split(/\s+/).filter(Boolean);
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

function oneWrongNote(query, steps, at, base, octaves) {
  // Would the query match at `at` if exactly one of its notes were changed? A wrong
  // first or last note changes one step; a wrong note in between changes the step
  // into it and the step out of it, which together still span the same interval.
  const wrong = [];
  for (let j = 0; j < query.length && wrong.length < 3; j++) if (steps[at + j] !== query[j]) wrong.push(j);
  if (wrong.length === 1) return wrong[0] === 0 || wrong[0] === query.length - 1;
  if (wrong.length !== 2 || wrong[1] !== wrong[0] + 1) return false;
  const span = (s, j) => s.charCodeAt(j) + s.charCodeAt(j + 1) - 2 * base;  // semitones across two steps
  const diff = span(query, wrong[0]) - span(steps, at + wrong[0]);
  return octaves ? diff === 0 : diff % 12 === 0;
}

function searchByNotes(text) {
  const notes = parseNotes(text);
  const octaves = notes.length > 0 && notes.every((n) => n.midi !== null);
  const query = octaves ? exactSteps(collapse(notes.map((n) => n.midi))) : foldedSteps(collapse(notes.map((n) => n.pc)));
  if (query.length < MIN_NOTES - 1) return null;
  const results = [];
  for (const tune of state.data.tunes) {
    const steps = tuneSteps(tune)[octaves ? "exact" : "folded"];
    const at = steps.indexOf(query);
    let score = 0, where = at, how = "";
    if (at >= 0) {
      [score, how] = at <= 2 ? [4, "starts like this"] : [3, "later in the tune"];  // <= 2: allow pick-up notes
    } else if (query.length >= 4) {
      for (let i = 0; i + query.length <= steps.length; i++) {
        if (oneWrongNote(query, steps, i, octaves ? 80 : 70, octaves)) {
          [score, where, how] = [i <= 2 ? 2 : 1, i, "one note different"];
          break;
        }
      }
    }
    if (score) results.push({ tune, score, where, how });
  }
  results.sort((a, b) => b.score - a.score || a.where - b.where || (a.tune.title < b.tune.title ? -1 : 1));
  // One entry per tune: its best-matching version.
  const seen = new Set();
  return results.filter((r) => !seen.has(r.tune.group) && seen.add(r.tune.group));
}

function playNote(midi) {
  // Sound one keyboard note with the same piano (and volume) as the player.
  const sequence = new ABCJS.synth.SynthSequence();
  const track = sequence.addTrack();
  sequence.setInstrument(track, 0);
  sequence.appendNote(track, midi, 0.25, 100);
  const synth = new ABCJS.synth.CreateSynth();
  synth.init({ sequence, millisecondsPerMeasure: 2000, options: AUDIO_PARAMS })
    .then(() => synth.prime()).then(() => synth.start()).catch(() => {});
}

function keyboard(onPress) {
  // A piano keyboard from G3 to A5: white keys in a row, black keys laid over them.
  const whites = [], blacks = [];
  for (let midi = KEYBOARD.from; midi <= KEYBOARD.to; midi++) {
    const name = NOTE_NAMES[midi % 12] + (Math.floor(midi / 12) - 1);
    const key = el("button", {
      type: "button", "aria-label": name.replace("#", " sharp "), title: name.replace("#", "♯"),
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
    help.textContent = found.length
      ? `${found.length} tune${found.length > 1 ? "s" : ""} with these notes${found.length > 12 ? " (showing the best 12; add notes to narrow it down)" : ""}.`
      : "No tunes with these notes. Try fewer notes, or check a note or two.";
    results.replaceChildren(...found.slice(0, 12).map(({ tune, how }) => {
      const several = state.groups.get(tune.group).versions.length > 1;
      return el("li", {},
        el("a", { href: tuneUrl(tune.group, tune.version), "data-route": true }, tune.base),
        el("span", { class: "caption" }, `${several ? ` (version ${tune.version})` : ""} · ${how}`));
    }));
  };
  input.addEventListener("input", update);
  const press = (name) => { input.value = `${input.value.trimEnd()} ${name}`.trimStart(); update(); };
  const edit = el("div", { class: "note-edit" },
    el("button", { type: "button", "aria-label": "Delete last note", onclick: () => {
      input.value = input.value.trimEnd().replace(/\s*\S+$/, ""); update(); } }, "⌫ Delete"),
    el("button", { type: "button", onclick: () => { input.value = ""; update(); } }, "Clear"));
  update();
  return el("section", { class: "notes-search" },
    el("h2", { class: "section-heading" }, "Search by notes"),
    el("label", { for: "notes-search", class: "visually-hidden" }, "First notes of the tune"),
    input, el("div", { class: "piano-wrap" }, keyboard(press)), edit, help, results);
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
  const main = document.getElementById("main");
  if (!tune) setPractice(false);
  main.style.animation = "none"; void main.offsetWidth; main.style.animation = "";  // replay fade-in
  document.getElementById("home-button").disabled = !tune && !guide;
  if (tune) renderTune(main, group, tune);
  else if (guide) renderGuide(main, guide);
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
      ` resource to help you learn and share Welsh folk tunes. Each of its ${tunes.length} tunes `,
      "has its sheet music, which you can play back at any tempo and change to any key. ",
      "Search by name in the sidebar, browse by type below, or let chance decide. Everything is ",
      el("a", { href: repo }, "on GitHub"),
      ", and anyone can ", el("a", { href: "?page=add", "data-route": true }, "add a tune"),
      " or ", el("a", { href: "?page=fix", "data-route": true }, "suggest a correction"), "."),
    heroSearch(tunes.length),
    el("button", { type: "button", class: "primary", onclick: openRandomTune }, "Surprise me"),
    notesSearch(),
    el("h2", { class: "section-heading" }, "Browse by type"),
    pills, caption, list,
  );
  showType(state.browseType);
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

function drawScore(tune, paper, audio) {
  stopPlayback();
  const { transpose, bpm } = state.settings.get(tune.slug);
  // S:, Z:, B: (book), N: (notes) and A: (area) are in the Details box, so leave
  // them off the score; the version tabs say which version it is.
  let abc = setTempo(stripFields(tune.abc, "SZBNA"), tune.beat, bpm).replace(/^(T:.*) \(version \d+\)$/m, "$1");
  if (transpose) {
    // strTranspose needs the whole array renderAbc returns, not its first tune.
    abc = ABCJS.strTranspose(abc, ABCJS.renderAbc("*", abc), transpose);
  }
  const visualObj = ABCJS.renderAbc(paper, abc, { responsive: "resize", add_classes: true, paddingtop: 0 })[0];

  audio.replaceChildren();
  if (!ABCJS.synth.supportsAudio()) {
    audio.textContent = "Audio is not supported in this browser.";
    return;
  }
  const controller = new ABCJS.synth.SynthController();
  controller.load(audio, new Cursor(), {
    displayLoop: true, displayRestart: true, displayPlay: true, displayProgress: true,
  });
  controller.setTune(visualObj, false, AUDIO_PARAMS);
  state.synth = controller;
  // Fetch and decode this tune's notes now, so pressing play doesn't wait. The
  // audio stays paused until play is clicked; abcjs shares the decoded notes.
  new ABCJS.synth.CreateSynth().init({ visualObj, options: AUDIO_PARAMS }).catch(() => {});
}

function renderTune(main, group, tune) {
  document.title = `${group.title} · Y Sesiwn`;
  if (!state.settings.has(tune.slug)) state.settings.set(tune.slug, { transpose: 0, bpm: tune.bpm });
  const settings = state.settings.get(tune.slug);

  const paper = el("div");
  const audio = el("div", { class: "audio" });
  const redraw = () => drawScore(tune, paper, audio);

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
    })), practice);

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
      el("div", { class: "score" }, audio, paper),
      el("div", { class: "tune-side" },
        el("section", { class: "card" }, el("h2", {}, "Details"), details, gloss),
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
start().catch((error) => {
  document.getElementById("main").replaceChildren(el("p", {}, `Couldn't load the tunes: ${error}`));
});
