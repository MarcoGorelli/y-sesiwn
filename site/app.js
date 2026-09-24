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
const GUIDES = { add: "How to add a tune", fix: "How to submit corrections" };

const state = {
  data: null,
  bySlug: new Map(),
  browseType: null,
  settings: new Map(),  // per tune: { transpose, bpm }, kept while the page is open
  synth: null,          // the playing SynthController, stopped when leaving a tune
  guide: null,          // CONTRIBUTING.md, fetched on first use
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
  const q = normalize(query);
  if (!q) return state.data.tunes;
  return state.data.tunes
    .map((tune) => [score(q, tune), tune])
    .filter(([s]) => s >= 0.7)
    .sort((x, y) => y[0] - x[0] || (x[1].title < y[1].title ? -1 : 1))
    .map(([, tune]) => tune);
}

// ---- Routing ----------------------------------------------------------------

function tuneUrl(slug) { return `?tune=${encodeURIComponent(slug)}`; }

function navigate(url) {
  history.pushState(null, "", url);
  render();
  window.scrollTo(0, 0);
}

function openRandomTune() {
  const current = new URLSearchParams(location.search).get("tune");
  const choices = state.data.tunes.filter((t) => t.slug !== current);
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
  const tune = state.bySlug.get(params.get("tune"));
  const guide = GUIDES[params.get("page")];
  const main = document.getElementById("main");
  if (!tune) setPractice(false);
  main.style.animation = "none"; void main.offsetWidth; main.style.animation = "";  // replay fade-in
  document.getElementById("home-button").disabled = !tune && !guide;
  if (tune) renderTune(main, tune);
  else if (guide) renderGuide(main, guide);
  else renderHome(main);
}

// ---- Home page -----------------------------------------------------------------

function renderHome(main) {
  document.title = "Y Sesiwn";
  const { tunes, types, repo } = state.data;

  const list = el("ul", { class: "tune-list" });
  const caption = el("p", { class: "caption" });
  const pills = el("div", { class: "pills", role: "group", "aria-label": "Tune type" });
  // No type selected (null) lists every tune; clicking the selected type again clears it.
  const showType = (name) => {
    state.browseType = name;
    const type = types.find((t) => t.name === name);
    for (const pill of pills.children) pill.setAttribute("aria-pressed", pill.dataset.type === name);
    caption.textContent = type ? `${type.count} ${type.english}` : `All ${tunes.length} tunes`;
    const listed = tunes.filter((t) => !type || t.type === name)
      .sort((a, b) => (a.search[0] < b.search[0] ? -1 : 1));
    list.replaceChildren(...listed.map((t) =>
      el("li", {}, el("a", { href: tuneUrl(t.slug), "data-route": true }, t.title))));
  };
  for (const type of types) {
    pills.append(el("button", {
      type: "button", "data-type": type.name,
      onclick: () => showType(state.browseType === type.name ? null : type.name),
    }, `${type.name} · ${type.count}`));
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
    el("h2", {}, "Browse by type"),
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
  // abcjs prints S: and Z: under the score; the source stays in the ABC view.
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
  let abc = setTempo(stripFields(tune.abc, "SZ"), tune.beat, bpm);
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

function renderTune(main, tune) {
  document.title = `${tune.title} · Y Sesiwn`;
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

  main.replaceChildren(...[
    el("h1", {}, tune.title),
    tune.titles.length > 1 ? el("p", { class: "caption aka" }, `Also known as: ${tune.titles.slice(1).join(", ")}`) : null,
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

// ---- Guide pages (sections of CONTRIBUTING.md) --------------------------------------

async function renderGuide(main, heading) {
  document.title = `${heading} · Y Sesiwn`;
  main.replaceChildren(el("p", { class: "loading" }, "Loading…"));
  state.guide ??= await (await fetch("CONTRIBUTING.md")).text();
  const section = state.guide.split(/^(?=# )/m).find((s) => s.startsWith(`# ${heading}\n`)) ?? "";
  const html = marked.parse(section.replaceAll("(#how-to-add-a-tune)", "(?page=add)"));
  const guide = el("article", { class: "guide" });
  guide.innerHTML = html;  // our own CONTRIBUTING.md, from this repo
  guide.querySelectorAll('a[href^="?"]').forEach((a) => a.setAttribute("data-route", ""));
  // Only show it if we're still on this guide (the fetch may finish after leaving).
  if (GUIDES[new URLSearchParams(location.search).get("page")] === heading) main.replaceChildren(guide);
}

// ---- Sidebar search box ---------------------------------------------------------------

function attachSearch(input, list, { showAllOnFocus = true } = {}) {
  let results = [];
  let active = 0;

  const close = () => { list.hidden = true; input.setAttribute("aria-expanded", "false"); };
  const open = (tune) => { input.value = ""; close(); input.blur(); navigate(tuneUrl(tune.slug)); };
  const show = () => {
    const query = input.value;
    if (!query.trim() && !showAllOnFocus) { results = []; close(); return; }
    results = query.trim() ? search(query).slice(0, 20) : state.data.tunes;
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

async function start() {
  state.data = await (await fetch("tunes.json")).json();
  for (const tune of state.data.tunes) state.bySlug.set(tune.slug, tune);
  document.getElementById("home-button").addEventListener("click", () => navigate("./"));
  document.getElementById("surprise-sidebar").addEventListener("click", openRandomTune);
  attachSearch(document.getElementById("search-input"), document.getElementById("suggestions"));
  render();
}
start().catch((error) => {
  document.getElementById("main").replaceChildren(el("p", {}, `Couldn't load the tunes: ${error}`));
});
