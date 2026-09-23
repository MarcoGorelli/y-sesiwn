#!/usr/bin/env python3
"""MIDI -> ABC for the alawoncymru.com tunes (NoteWorthy Composer exports), plus
a checker that proves an ABC file still plays exactly what the MIDI plays.

    abctool.py convert tune.mid [-o tune.abc] [--pickup 1/8] [--no-fold]
                       [--bars-per-line 4] [--track N] [--title ...] [--key Em]
    abctool.py check tune.abc tune.mid [--track N]
    abctool.py bars tune.mid [--pickup 1/4] [--transpose N]   # numbered bar listing
    abctool.py batch DIR [--force]     # every DIR/*/tune.mid -> tune.abc + check
    abctool.py status DIR              # converted / reviewed / failing
    abctool.py collect DIR -o book.abc [--reviewed-only]

`convert` quantises the melody, puts bar lines where the time signature says
(after an optional pickup, auto-detected unless --pickup is given), splits and
ties notes across bar lines, and folds the MIDI's played-out repeats back into
|: :| and [1 [2 endings.

A tune.abc containing the line "%%alawon-reviewed" has been checked against
its score by hand; `batch --force` never overwrites it.

`check` parses the ABC (repeats, endings, ties, tuplets, broken rhythm,
accidentals, key/meter changes), plays it out and compares it event by event
with the MIDI, and lists bars whose length does not match the meter. Run it
after every hand edit of an .abc file.
"""
import argparse
import difflib
import json
import re
import sys
from fractions import Fraction as F
from pathlib import Path

import mido

# ----------------------------------------------------------------- music data

SHARP_ORDER = "FCGDAEB"
MAJOR_SIG = {  # tonic -> number of sharps (negative = flats)
    "C": 0, "G": 1, "D": 2, "A": 3, "E": 4, "B": 5, "F#": 6, "C#": 7,
    "F": -1, "Bb": -2, "Eb": -3, "Ab": -4, "Db": -5, "Gb": -6, "Cb": -7,
}
MODES = ["Maj", "Dor", "Phr", "Lyd", "Mix", "Min", "Loc"]  # degrees of the major scale
MODE_ALIASES = {"": 0, "maj": 0, "ion": 0, "major": 0, "m": 5, "min": 5, "aeo": 5,
                "minor": 5, "dor": 1, "phr": 2, "lyd": 3, "mix": 4, "loc": 6}
LETTER_PC = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
LETTERS = "CDEFGAB"
PC_NAME = ["C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"]


def sig_accidentals(nsharps):
    """{letter: alteration} for a key signature."""
    acc = {c: 0 for c in LETTERS}
    if nsharps > 0:
        for c in SHARP_ORDER[:nsharps]:
            acc[c] = 1
    else:
        for c in SHARP_ORDER[::-1][:-nsharps]:
            acc[c] = -1
    return acc


def major_scale(nsharps):
    tonic = [k for k, v in MAJOR_SIG.items() if v == nsharps][0]
    pcs = [(PC_NAME.index(tonic) if tonic in PC_NAME else
            (LETTER_PC[tonic[0]] + (1 if "#" in tonic else -1 if "b" in tonic else 0)) % 12)]
    for step in [2, 2, 1, 2, 2, 2]:
        pcs.append((pcs[-1] + step) % 12)
    return pcs


def parse_key(k):
    """'Em', 'DMix', 'G', 'Bb', 'F#m', 'ADor', 'none' -> (nsharps, label)."""
    k = k.strip().split()[0] if k.strip() else "C"
    if k.lower() in ("none", "hp", "hp"):
        return 0, k
    m = re.match(r"([A-G])([#b]?)(.*)", k)
    if not m:
        raise ValueError(f"bad key {k!r}")
    tonic = m.group(1) + m.group(2)
    mode = MODE_ALIASES.get(m.group(3)[:3].lower(), None)
    if mode is None:
        raise ValueError(f"bad mode in key {k!r}")
    tonic_pc = (LETTER_PC[m.group(1)] + {"#": 1, "b": -1, "": 0}[m.group(2)]) % 12
    for major, ns in MAJOR_SIG.items():
        if major_scale(ns)[mode] == tonic_pc and abs(ns) <= 7:
            # prefer the spelling whose tonic letter matches
            scale_letters = LETTERS[LETTERS.index(major[0]):] + LETTERS[:LETTERS.index(major[0])]
            if scale_letters[mode] == m.group(1):
                return ns, k
    raise ValueError(f"cannot resolve key {k!r}")


def key_label(nsharps, tonic_pc=None, minorish=None):
    """ABC K: value for a signature, choosing the mode whose tonic is tonic_pc."""
    major = [k for k, v in MAJOR_SIG.items() if v == nsharps][0]
    if tonic_pc is None:
        return major
    scale = major_scale(nsharps)
    if tonic_pc not in scale:
        return major
    deg = scale.index(tonic_pc)
    if minorish is not None and (deg in (1, 2, 5, 6)) != minorish:
        return major
    letters = LETTERS[LETTERS.index(major[0]):] + LETTERS[:LETTERS.index(major[0])]
    letter = letters[deg]
    alt = sig_accidentals(nsharps)[letter]
    name = letter + {1: "#", -1: "b", 0: ""}[alt]
    return name + {0: "", 5: "m"}.get(deg, MODES[deg])


# ---------------------------------------------------------------- MIDI input

class Tune:
    """Melody from a MIDI file as a list of events (onset, dur, pitches|None)."""

    def __init__(self, path, track=None, transpose=0):
        mid = mido.MidiFile(path)
        self.tpb = mid.ticks_per_beat
        self.tempo = 500000
        self.key = None
        tracks = []
        for ti, t in enumerate(mid.tracks):
            a, on, notes, meta = 0, {}, [], []
            for msg in t:
                a += msg.time
                if msg.type == "time_signature":
                    meta.append((a, "ts", (msg.numerator, msg.denominator)))
                elif msg.type == "key_signature" and self.key is None:
                    self.key = msg.key
                elif msg.type == "set_tempo" and a == 0:
                    self.tempo = msg.tempo
                elif msg.type == "note_on" and msg.velocity > 0:
                    on.setdefault((msg.channel, msg.note), []).append(a)
                elif msg.type in ("note_off", "note_on"):
                    k = (msg.channel, msg.note)
                    if on.get(k):
                        notes.append((on[k].pop(0), a, msg.note))
            tracks.append((ti, sorted(notes), meta))
        with_notes = [t for t in tracks if t[1]]
        if not with_notes:
            raise ValueError("no notes in MIDI")
        self.note_tracks = [t[0] for t in with_notes]
        chosen = with_notes[0] if track is None else next(t for t in tracks if t[0] == track)
        self.track = chosen[0]
        # time signatures: prefer the melody track's own, else any track's
        ts = chosen[2] or [m for t in tracks for m in t[2]]
        seen = {}
        for a, _, v in sorted(ts):
            seen[a] = v
        self.meters = sorted(seen.items()) or [(0, (4, 4))]
        if self.meters[0][0] != 0:
            self.meters.insert(0, (0, self.meters[0][1]))
        self.events = self._events(chosen[1])
        if transpose:
            self.events = [(on, d, [p + transpose for p in ps] if ps else ps)
                           for on, d, ps in self.events]
            self.key = transpose_key(self.key or "C", transpose)

    def fit_final_note(self, pickup):
        """With a pickup the last bar is usually short (bar - pickup): end the
        final note there if it was rounded past it."""
        if not pickup or not self.events:
            return
        lines = barlines(self, pickup)
        on, dur, ps = self.events[-1]
        if not ps or not lines:
            return
        last_line = max([0] + [x for x in lines if x <= on])
        target = last_line + self.bar_ticks(self.meter_at(last_line)) - pickup
        if on < target < on + dur and target - on >= 0.75 * dur:
            self.events[-1] = (on, target - on, ps)

    def select_bars(self, first, last, pickup):
        """Keep only played bars first..last (1-based, as `bars` numbers them).
        Returns the pickup to use for the selection."""
        lines = [0] + barlines(self, pickup) + [self.end]
        start, stop = lines[first - 1], lines[min(last, len(lines) - 1)]
        self.events = [(on - start, d, ps) for on, d, ps in self.events if start <= on < stop]
        self.meters = [(max(0, a - start), m) for a, m in self.meters if a < stop]
        keep = {}
        for a, m in self.meters:
            keep[a] = m
        self.meters = sorted(keep.items())
        return pickup if first == 1 else 0

    def _events(self, notes):
        """Group chords, derive notated lengths and rests from played lengths."""
        groups = []
        for on, off, p in notes:
            if groups and groups[-1][0] == on:
                groups[-1][1] = max(groups[-1][1], off)
                groups[-1][2].append(p)
            else:
                groups.append([on, off, [p]])
        unit = self.tpb // 4  # semiquaver
        events = []
        t = 0
        for i, (on, off, ps) in enumerate(groups):
            if on > t:
                events.append((t, on - t, None))
            played = off - on
            ioi = groups[i + 1][0] - on if i + 1 < len(groups) else None
            # NoteWorthy sounds a note for 83-98% of its written length (crotchet
            # 160/192, minim 336/384 ...) and a staccato note for a third of it:
            # round up to a plain or dotted value; a semiquaver or more left
            # before the next note is a rest
            std = sorted(v for v in (unit * 2 ** k * f // 4 for k in range(-1, 7) for f in (4, 6))
                         if v >= unit)
            dur = next((v for v in std if v >= played), -(-played // unit) * unit)
            if played < 0.75 * dur:  # staccato
                dur = next((v for v in std if v >= 2.7 * played), dur)
            if ioi is not None and (dur > ioi or ioi - dur < unit):
                dur = ioi
            events.append((on, dur, sorted(ps)))
            t = on + dur
            if ioi is not None and dur < ioi:
                events.append((t, ioi - dur, None))
                t = on + ioi
        return events

    @property
    def end(self):
        on, dur, _ = self.events[-1]
        return on + dur

    def meter_at(self, tick):
        m = self.meters[0][1]
        for a, v in self.meters:
            if a <= tick:
                m = v
        return m

    def bar_ticks(self, meter):
        n, d = meter
        return self.tpb * 4 * n // d


def transpose_key(key, semis):
    """Major-key signature name after transposing (for spelling notes)."""
    try:
        ns, _ = parse_key(key)
    except ValueError:
        ns = 0
    pc = (major_scale(ns)[0] + semis) % 12
    cands = [(abs(v), k) for k, v in MAJOR_SIG.items() if major_scale(v)[0] == pc]
    return min(cands)[1]


def played_events(tune):
    """(onset, dur, pitches) with rests dropped and ties merged, for comparing."""
    return [(on, d, tuple(p)) for on, d, p in tune.events if p]


# ---------------------------------------------------------------- bar layout

def barlines(tune, pickup):
    """Tick positions of bar lines (excluding 0), honouring meter changes."""
    lines = []
    t = pickup if pickup else 0
    if pickup:
        lines.append(pickup)
    changes = [a for a, _ in tune.meters if a > 0]
    end = tune.end
    while t < end:
        nxt = t + tune.bar_ticks(tune.meter_at(t))
        c = next((a for a in changes if t < a < nxt), None)
        t = c if c else nxt
        if t < end:
            lines.append(t)
    return lines


def guess_pickup(tune):
    """Choose the anacrusis length that puts long notes on strong beats."""
    bar0 = tune.bar_ticks(tune.meters[0][1])
    n, d = tune.meters[0][1]
    compound = d == 8 and n % 3 == 0
    beat = tune.tpb * 4 // d * (3 if compound else 1)
    beats = bar0 // beat
    half = bar0 // 2 if beats % 2 == 0 else None
    step = tune.tpb // 2 if compound else tune.tpb // 4
    total = sum(min(d, bar0) / tune.tpb for on, d, ps in tune.events if ps) or 1
    best = (0, None)
    for o in range(0, bar0, step):
        # prefer short pickups: half-bar shifts in 4/4 score almost the same
        # (a half-bar shift in 4/4 or 6/8 swaps beats 1 and 3, so it needs more)
        score = -(0.1 + 0.25 * o / bar0 + (0.4 if half and o >= half else 0)) * total if o else 0.0
        for on, dur, ps in tune.events:
            if ps is None:
                continue
            ph = (on - o) % bar0
            w = min(dur, bar0) / tune.tpb
            if ph == 0:
                score += 4 * w
            elif half and ph % half == 0:
                score += 2 * w
            elif ph % beat == 0:
                score += 1 * w
            else:
                score -= 0.5 * w
        if best[1] is None or score > best[1]:
            best = (o, score)
    return best[0]


def standard_lengths(tpb):
    return {tpb * 4 * f // 64 for f in (4, 6, 8, 12, 16, 24, 32, 48, 64, 96)}


def split_odd_lengths(events, meter, tpb):
    """Write lengths that are not a plain or dotted note (e.g. 5 quavers) as tied
    notes split at the beat, as a score would: B5 -> B3-B2 in 6/8."""
    n, d = meter
    beat = tpb * 4 // d * (3 if d == 8 and n % 3 == 0 else 1)
    std = standard_lengths(tpb)
    out = []
    for on, dur, ps, tie in events:
        while dur not in std and dur % (tpb // 4) == 0:
            cut = (on // beat + 1) * beat - on
            if cut >= dur:
                break
            out.append((on, cut, ps, ps is not None))
            on, dur = on + cut, dur - cut
        out.append((on, dur, ps, tie))
    return out


def split_bars(tune, pickup, extra_cuts=()):
    """Cut the events into bars at the bar lines (plus any extra cut points,
    e.g. where a section ends mid-bar). Each bar: {start, len, meter, events}
    with events (onset, dur, pitches|None, tie_to_next) whose onsets are
    positions in the metric bar (a pickup bar starts part-way through)."""
    real = barlines(tune, pickup)
    cuts = sorted(set(real) | {c for c in extra_cuts if 0 < c < tune.end})
    bar_starts = [pickup - tune.bar_ticks(tune.meters[0][1]) if pickup else 0] + real
    edges = [0] + cuts + [tune.end]
    bars, ev, i = [], list(tune.events), 0
    for start, stop in zip(edges, edges[1:]):
        origin = max(b for b in bar_starts if b <= start)
        cur = []
        while i < len(ev):
            on, dur, ps = ev[i]
            if on >= stop:
                break
            if on + dur > stop:  # crosses the bar line: split and tie
                cur.append((on - origin, stop - on, ps, ps is not None))
                ev[i] = (stop, on + dur - stop, ps)
                break
            cur.append((on - origin, dur, ps, False))
            i += 1
        meter = tune.meter_at(start)
        bars.append({"start": start, "len": stop - start, "meter": meter,
                     "events": split_odd_lengths(cur, meter, tune.tpb)})
    # the MIDI stops at the last note: fill the final bar up to where it should end
    last = bars[-1]
    origin = max(b for b in bar_starts if b <= last["start"])
    ends = [origin + tune.bar_ticks(last["meter"])]
    if pickup:
        bar0 = tune.bar_ticks(tune.meters[0][1])
        ends.append(-(-tune.end // bar0) * bar0)  # section end (bar - pickup)
    target = min(e for e in ends if e >= tune.end)
    if last["events"] and target > tune.end:
        used = tune.end - origin
        last["events"].append((used, target - tune.end, None, False))
    return bars


# ------------------------------------------------------------------ ABC text

def spell(pitch, nsharps):
    """MIDI pitch -> (letter, octave, alteration) using the key to pick names."""
    pc = pitch % 12
    sig = sig_accidentals(nsharps)
    # a scale note first (including naturals of the letters)
    for letter in LETTERS:
        if (LETTER_PC[letter] + sig[letter]) % 12 == pc:
            alt = sig[letter]
            break
    else:
        white = [l for l in LETTERS if LETTER_PC[l] == pc]
        if white:
            letter, alt = white[0], 0
        else:
            use_flat = nsharps < 0 and pc not in (1, 6) or nsharps >= 0 and pc == 10 and nsharps <= 1
            if use_flat:
                letter, alt = [l for l in LETTERS if LETTER_PC[l] == (pc + 1) % 12][0], -1
            else:
                letter, alt = [l for l in LETTERS if LETTER_PC[l] == (pc - 1) % 12][0], 1
    octave = (pitch - LETTER_PC[letter] - alt) // 12 - 1  # C4 = middle C = 60
    return letter, octave, alt


def pitch_text(letter, octave, alt_text):
    if octave >= 5:
        s = letter.lower() + "'" * (octave - 5)
    else:
        s = letter + "," * (4 - octave)
    return alt_text + s


def dur_text(ticks, unit):
    f = F(ticks, unit)
    if f == 1:
        return ""
    if f.denominator == 1:
        return str(f.numerator)
    if f.numerator == 1:
        return "/" if f.denominator == 2 else f"/{f.denominator}"
    return f"{f.numerator}/{f.denominator}"


def bar_text(bar, nsharps, unit, tpb):
    """ABC for one bar's events: accidentals, beaming, tuplets, broken rhythm."""
    sig = sig_accidentals(nsharps)
    acc = {}
    n, d = bar["meter"]
    beat = tpb * 4 // d
    if d == 8 and n % 3 == 0:
        beat *= 3
    elif d == 2:
        beat //= 2

    def note(ps, ticks, tie):
        parts = []
        for p in ps:
            letter, octv, alt = spell(p, nsharps)
            cur = acc.get((letter, octv), sig[letter])
            a = ""
            if alt != cur:
                a = {1: "^", -1: "_", 0: "=", 2: "^^", -2: "__"}[alt]
                acc[(letter, octv)] = alt
            parts.append(pitch_text(letter, octv, a))
        body = parts[0] if len(parts) == 1 else "[" + "".join(parts) + "]"
        return body + dur_text(ticks, unit) + ("-" if tie else "")

    evs = bar["events"]
    toks = []  # (onset, length, text, beamable)
    i = 0
    grid = tpb // 4
    while i < len(evs):
        on, dur, ps, tie = evs[i]
        if on % grid or dur % grid:
            # tuplet: gather until back on the semiquaver grid
            j, total = i, 0
            while j < len(evs):
                total += evs[j][1]
                j += 1
                if (on + total) % grid == 0:
                    break
            group = evs[i:j]
            if all((e[1] * 3) % 2 == 0 for e in group) and (on + total) % grid == 0:
                inner = "".join(
                    note(e[2], e[1] * 3 // 2, e[3]) if e[2] else "z" + dur_text(e[1] * 3 // 2, unit)
                    for e in group)
                pre = "(3" if len(group) == 3 else f"(3:2:{len(group)}"
                toks.append((on, total, pre + inner, total <= beat))
                i = j
                continue
        # broken rhythm: dotted quaver + semiquaver (or reverse) on a crotchet beat
        if (d in (2, 4) and i + 1 < len(evs) and ps and evs[i + 1][2] and not tie
                and on % tpb == 0 and dur in (3 * tpb // 4, tpb // 4)
                and evs[i + 1][1] == tpb - dur):
            nxt = evs[i + 1]
            mark = ">" if dur > nxt[1] else "<"
            txt = note(ps, tpb // 2, False) + mark + note(nxt[2], tpb // 2, nxt[3])
            toks.append((on, tpb, txt, True))
            i += 2
            continue
        if ps:
            toks.append((on, dur, note(ps, dur, tie), dur < tpb))
        else:
            toks.append((on, dur, "z" + dur_text(dur, unit), False))
        i += 1

    out = ""
    for k, (on, ln, txt, beam) in enumerate(toks):
        if k:
            prev = toks[k - 1]
            same_beat = prev[0] // beat == on // beat and on % beat != 0
            if not (beam and prev[3] and same_beat):
                out += " "
        out += txt
    return out


def fold_repeats(bars_txt, min_len=4, max_len=16):
    """Collapse played-out repeats. Returns list of layout items:
    ('bar', idx) ('start',) ('end',) ('ending', n)."""
    n = len(bars_txt)
    items = []
    i = 0
    while i < n:
        found = None
        for L in range(min(max_len, (n - i) // 2), min_len - 1, -1):
            a, b = bars_txt[i:i + L], bars_txt[i + L:i + 2 * L]
            if a == b:
                found = (L, 0)
                break
            for k in range(1, max(1, L // 4) + 1):  # endings: short vs the section
                if a[:L - k] == b[:L - k] and a[L - k:] != b[L - k:]:
                    found = (L, k)
                    break
            if found:
                break
        if not found:
            items.append(("bar", i))
            i += 1
            continue
        L, k = found
        items.append(("start",))
        items += [("bar", j) for j in range(i, i + L - k)]
        if k:
            items.append(("ending", 1))
            items += [("bar", j) for j in range(i + L - k, i + L)]
            items.append(("end",))
            items.append(("ending", 2))
            items += [("bar", j) for j in range(i + 2 * L - k, i + 2 * L)]
            items.append(("close",))
        else:
            items.append(("end",))
        i += 2 * L
    return items


def whole_tune_repeats(bars_txt):
    n = len(bars_txt)
    for times in range(4, 1, -1):
        if n % times == 0:
            L = n // times
            if all(bars_txt[j * L:(j + 1) * L] == bars_txt[:L] for j in range(times)):
                return times, L
    return 1, n


SPLIT_SEP = {  # bar line -> (end of this line, start of next line) at a line break
    "|": ("|", ""), "||": ("||", ""), "|:": ("", "|:"), ":|": (":|", ""),
    "::": (":|", "|:"), "|1": ("|", "[1"), ":|2": (":|", "[2"), "||2": ("||", "[2"),
}


def render(bars, items, bars_per_line, nsharps, unit, tpb):
    """Layout items -> ABC body text with bar lines and line breaks."""
    toks = []  # alternating separator / bar text
    sep = ""
    meter = bars[0]["meter"] if bars else None
    for it in items:
        kind = it[0]
        if kind == "start":
            sep = "::" if sep == ":|" else "|:"
        elif kind == "end":
            sep = ":|"
        elif kind == "ending":
            sep = (sep or "|") + str(it[1])
        elif kind == "close":
            sep = "||"
        else:
            b = bars[it[1]]
            toks.append(sep)
            prefix = ""
            if b["meter"] != meter:
                prefix = f"[M:{b['meter'][0]}/{b['meter'][1]}] "
                meter = b["meter"]
            toks.append((prefix, it[1]))
            sep = "|"
    toks.append({"|": "|]", "||": "|]", "": "|]"}.get(sep, sep))

    def counts(k):  # short bars (pickups) ride along with the line they are on
        return k < len(toks) and isinstance(toks[k], tuple) and \
            2 * bars[toks[k][1]]["len"] >= tpb * 4 * bars[toks[k][1]]["meter"][0] // bars[toks[k][1]]["meter"][1]

    lines, cur, nbars = [], "", 0
    for k, t in enumerate(toks):
        if isinstance(t, tuple):
            cur += t[0] + bar_text(bars[t[1]], nsharps, unit, tpb) + " "
            nbars += counts(k)
            continue
        if k == 0:
            cur = (t + " ") if t else ""
        elif nbars and nbars % bars_per_line == 0 and counts(k + 1):
            end, start = SPLIT_SEP.get(t, (t, ""))
            lines.append((cur + end).strip())
            cur = (start + " ") if start else ""
        else:
            cur += t + " "
    lines.append(cur.strip())
    return "\n".join(l for l in lines if l)


def to_abc(tune, *, pickup=None, fold=True, bars_per_line=4, title="Untitled",
           aliases=(), rhythm="", key=None, source="", unit_len=8, directive=""):
    tpb = tune.tpb
    unit = tpb * 4 // unit_len
    if pickup is None:
        pickup = guess_pickup(tune)
    # signature from the MIDI; mode from --key/index hint or the final note
    ks = tune.key or "C"
    try:
        nsharps, _ = parse_key(ks)
    except ValueError:
        nsharps = 0
    if key:
        nsharps, klabel = parse_key(key)
    else:
        last = next(ps for on, d, ps in reversed(tune.events) if ps)
        klabel = key_label(nsharps, min(last) % 12)
    comments = []
    times = 1
    layouts = [layout(tune, pickup, 0, fold, nsharps, unit)]
    if pickup and fold:
        # sections may begin with their pickup: then parts end on a short bar
        # and repeat marks sit before each pickup, as NoteWorthy scores do
        layouts.append(layout(tune, pickup, pickup, fold, nsharps, unit))
    # fewest written bars wins; on a tie the pickup-first layout, which is how
    # the alawoncymru.com scores are written
    bars, items, times, _ = min(layouts, key=lambda l: (l[3], -layouts.index(l)))
    if times > 1:
        comments.append(f"% the MIDI plays the whole tune {times} times")
    n, d = tune.meters[0][1]
    qbpm = round(60_000_000 / tune.tempo)
    if d == 8 and n % 3 == 0:
        q = f"3/8={round(qbpm / 1.5)}"
    elif d == 2:
        q = f"1/2={round(qbpm / 2)}"
    else:
        q = f"1/4={qbpm}"
    head = ["X:1", f"T:{title}"] + [f"T:{a}" for a in aliases]
    if rhythm:
        head.append(f"R:{rhythm}")
    if source:
        head.append(f"S:{source}")
    head += ["Z:MIDI transcribed with alawon-abc"]
    if directive:
        head.append(f"%%alawon {directive}")
    head += [f"M:{n}/{d}", f"L:1/{unit_len}", f"Q:{q}", f"K:{klabel}"]
    body = render(bars, items, bars_per_line, nsharps, unit, tpb)
    nbars = sum(1 for it in items if it[0] == "bar")
    return "\n".join(head + comments + [body]) + "\n", {
        "pickup": pickup, "bars": nbars, "times": times, "key": klabel}


def layout(tune, pickup, shift, fold, nsharps, unit):
    """Fold repeats on units of one bar starting `shift` ticks before each bar
    line (0: sections start at bar lines; pickup: sections start with their
    pickup), then cut the written units into bars.
    -> (bars, items, times, number of units written)"""
    tpb = tune.tpb
    unit_pk = (pickup - shift) if pickup - shift > 0 else 0
    units = split_bars(tune, unit_pk)
    txt = [bar_text(u, nsharps, unit, tpb) for u in units]
    times = 1
    if fold:
        times, L = whole_tune_repeats(txt)
        units, txt = units[:L], txt[:L]
        items = fold_repeats(txt)
    else:
        items = [("bar", i) for i in range(len(units))]
    written = sum(1 for it in items if it[0] == "bar")
    if shift == 0:
        return units, items, times, written
    # cut the written units at the real bar lines and at section edges
    edges = set()
    prev = None
    for it in items + [("end",)]:
        if it[0] == "bar":
            u = units[it[1]]
            if prev is None or prev["start"] + prev["len"] != u["start"]:
                edges.add(u["start"])
                if prev is not None:
                    edges.add(prev["start"] + prev["len"])
            prev = u
        else:
            if prev is not None:
                edges.add(prev["start"] + prev["len"])
            prev = None
    pieces = split_bars(tune, pickup, edges)
    new_items = []
    for it in items:
        if it[0] != "bar":
            new_items.append(it)
            continue
        u = units[it[1]]
        new_items += [("bar", k) for k, pc in enumerate(pieces)
                      if u["start"] <= pc["start"] < u["start"] + u["len"]]
    return pieces, new_items, times, written



# ---------------------------------------------------------------- ABC parser

NOTE_RE = re.compile(r"(\^\^|\^|__|_|=)?([A-Ga-g])([,']*)(\d*)(/*)(\d*)")


def parse_len(num, slashes, den):
    n = int(num) if num else 1
    if not slashes:
        return F(n)
    d = int(den) if den else 2 ** len(slashes)
    return F(n, d)


def parse_abc(text):
    """ABC (one tune) -> list of bars as played, each bar a dict with events
    [(dur_in_whole_notes, (midi pitches) | None, tie)] and meter. Handles the
    notation the converter writes plus the usual hand edits."""
    header, body = {}, []
    in_body = False
    for raw in text.splitlines():
        line = raw.split("%", 1)[0].rstrip() if not raw.startswith("%%") else ""
        if not line.strip():
            continue
        m = re.match(r"^([A-Za-z]):\s*(.*)$", line)
        if m and (not in_body or m.group(1) in "MLKQPTWwNR"):
            f, v = m.groups()
            if not in_body:
                header.setdefault(f, v)
                if f == "K":
                    in_body = True
            else:
                if f in "MLK":
                    body.append(f"[{f}:{v}]")
            continue
        if in_body:
            body.append(line.rstrip("\\"))
    meter = header.get("M", "4/4")
    unit = header.get("L")
    s = " ".join(body)

    def meter_len(m):
        if m in ("C", "C|"):
            return F(1) if m == "C" else F(1)
        a, b = m.split("/")
        return F(int(a), int(b))

    cur_meter = meter_len(meter)
    unit = F(unit) if unit else (F(1, 16) if cur_meter < F(3, 4) else F(1, 8))
    nsharps, _ = parse_key(header.get("K", "C"))
    sig = sig_accidentals(nsharps)

    # tokenise into bars / structural marks
    items = []  # ('ev', dur, pitches, tie) ('bar', kind, ending_numbers)
    acc = {}
    i = 0
    tuplet = None  # [notes_left, factor]
    broken = None  # pending factor for the next note
    grace = False
    while i < len(s):
        c = s[i]
        if s.startswith("[M:", i) or s.startswith("[K:", i) or s.startswith("[L:", i):
            j = s.index("]", i)
            f, v = s[i + 1], s[i + 3:j].strip()
            if f == "M":
                cur_meter = meter_len(v)
                items.append(("meter", cur_meter))
            elif f == "L":
                unit = F(v)
            elif f == "K":
                nsharps, _ = parse_key(v)
                sig = sig_accidentals(nsharps)
            i = j + 1
            continue
        if c == '"':
            i = s.index('"', i + 1) + 1
            continue
        if c == "!" or c == "+" and s.find("+", i + 1) > i:
            i = s.index(c, i + 1) + 1
            continue
        if c == "{":
            i = s.index("}", i) + 1  # grace notes are not played in the MIDI
            continue
        # bar lines, repeats, endings
        m = re.match(r"(:*\|\]|:*\|\||:*\|:*|\[\||::|:+)(\s*\[?\d[\d,\-]*)?", s[i:])
        if m and (c in "|:" or s.startswith("[|", i)):
            bl, end = m.group(1), m.group(2)
            nums = None
            if end:
                nums = set()
                for part in end.strip(" [").split(","):
                    if "-" in part:
                        a, b = part.split("-")
                        nums |= set(range(int(a), int(b) + 1))
                    else:
                        nums.add(int(part))
            items.append(("bar", bl, nums))
            acc = {}
            i += m.end()
            continue
        m = re.match(r"\[(\d[\d,\-]*)", s[i:])
        if m and c == "[" and (i + 1 < len(s) and s[i + 1].isdigit()):
            nums = set()
            for part in m.group(1).split(","):
                if "-" in part:
                    a, b = part.split("-")
                    nums |= set(range(int(a), int(b) + 1))
                elif part:
                    nums.add(int(part))
            items.append(("bar", "", nums))
            i += m.end()
            continue
        if c == "(" and i + 1 < len(s) and s[i + 1].isdigit():
            m = re.match(r"\((\d)(?::(\d*))?(?::(\d*))?", s[i:])
            p = int(m.group(1))
            q = int(m.group(2)) if m.group(2) else {2: 3, 3: 2, 4: 3, 6: 2, 8: 3}.get(p, 2)
            r = int(m.group(3)) if m.group(3) else p
            tuplet = [r, F(q, p)]
            i += m.end()
            continue
        if c in ">" "<":
            k = 1
            while i + k < len(s) and s[i + k] == c:
                k += 1
            last = next(j for j in range(len(items) - 1, -1, -1) if items[j][0] == "ev")
            _, dur, ps, tie = items[last]
            f = F(2 ** (k + 1) - 1, 2 ** k) if c == ">" else F(1, 2 ** k)
            items[last] = ("ev", dur * f, ps, tie)
            broken = (2 - f)  # next note gets the complement
            i += k
            continue
        if c == "[":  # chord
            j = s.index("]", i)
            inner = s[i + 1:j]
            m2 = re.match(r"(\d*)(/*)(\d*)", s[j + 1:])
            ps, first_len = [], None
            for nm in NOTE_RE.finditer(inner):
                ps.append(note_pitch(nm, sig, acc))
                if first_len is None:
                    first_len = parse_len(nm.group(4), nm.group(5), nm.group(6))
            ln = (first_len or F(1)) * parse_len(m2.group(1), m2.group(2), m2.group(3))
            i = j + 1 + m2.end()
            tie = i < len(s) and s[i] == "-"
            if tie:
                i += 1
            items.append(("ev", apply_mods(ln * unit, tuplet, broken), tuple(sorted(ps)), tie))
            broken = None
            if tuplet:
                tuplet[0] -= 1
                if tuplet[0] <= 0:
                    tuplet = None
            continue
        m = NOTE_RE.match(s, i)
        rest = re.match(r"([zx])(\d*)(/*)(\d*)", s[i:])
        if m or rest:
            if m:
                ln = parse_len(m.group(4), m.group(5), m.group(6))
                ps = (note_pitch(m, sig, acc),)
                i = m.end()
            else:
                ln = parse_len(rest.group(2), rest.group(3), rest.group(4))
                ps = None
                i += rest.end()
            tie = i < len(s) and s[i] == "-"
            if tie:
                i += 1
            items.append(("ev", apply_mods(ln * unit, tuplet, broken), ps, tie))
            broken = None
            if tuplet:
                tuplet[0] -= 1
                if tuplet[0] <= 0:
                    tuplet = None
            continue
        if c == "Z":
            raise ValueError("multi-bar rests (Z) are not supported by the checker")
        i += 1  # spaces, slurs, decorations like ~ . T H, backticks, etc.
    return expand(items, meter_len(meter)), written_bars(items, meter_len(meter))


def apply_mods(dur, tuplet, broken):
    if tuplet:
        dur *= tuplet[1]
    if broken:
        dur *= broken
    return dur


def note_pitch(m, sig, acc):
    accs, letter, octs = m.group(1), m.group(2), m.group(3)
    up = letter.upper()
    octave = 5 if letter.islower() else 4
    octave += octs.count("'") - octs.count(",")
    if accs:
        alt = {"^": 1, "^^": 2, "_": -1, "__": -2, "=": 0}[accs]
        acc[(up, octave)] = alt
    else:
        alt = acc.get((up, octave), sig[up])
    return 12 * (octave + 1) + LETTER_PC[up] + alt


def bar_sequence(items, meter):
    seq = []  # ('bar', data) ('mark', kind, nums)
    cur, cur_meter = [], meter
    for it in items:
        if it[0] == "ev":
            cur.append(it[1:])
        elif it[0] == "meter":
            cur_meter = it[1]
        else:
            if cur:
                seq.append(("bar", {"events": cur, "meter": cur_meter}))
                cur = []
            seq.append(("mark", it[1], it[2]))
    if cur:
        seq.append(("bar", {"events": cur, "meter": cur_meter}))
    return seq


def written_bars(items, meter):
    """Bars in the order they are written (repeats not expanded)."""
    return [x[1] for x in bar_sequence(items, meter) if x[0] == "bar"]


def expand(items, meter):
    """Play out repeats and endings -> list of bars (each: meter, events)."""
    seq = bar_sequence(items, meter)
    out = []
    start, pass_no, i, guard = 0, 1, 0, 0
    while i < len(seq):
        guard += 1
        if guard > 100000:
            raise ValueError("repeat structure does not terminate")
        if seq[i][0] == "bar":
            out.append(seq[i][1])
            i += 1
            continue
        _, bl, nums = seq[i]
        if bl.startswith(":"):  # end of a repeat (":|", "::", ":|:", ":||")
            if pass_no == 1:
                pass_no = 2
                i = start
                continue
            pass_no = 1
            start = i + 1
        if bl.endswith(":"):  # start of a repeat ("|:", "::", ":|:")
            start, pass_no = i + 1, 1
        if nums is not None and pass_no not in nums:
            # skip to the ending for this pass; entering it finishes the repeat
            j = i + 1
            while j < len(seq) and not (seq[j][0] == "mark" and seq[j][2]
                                        and pass_no in seq[j][2]):
                j += 1
            i, start, pass_no = j + 1, j + 1, 1
            continue
        i += 1
    return out


def abc_played(text):
    """Flatten parsed bars -> [(onset, dur, pitches)] in whole notes, ties merged,
    rests dropped; plus bar info for reporting."""
    bars, _ = parse_abc(text)
    ev, t, info = [], F(0), []
    tie_open = None
    for bi, b in enumerate(bars):
        info.append((t, sum((e[0] for e in b["events"]), F(0)), b["meter"]))
        for dur, ps, tie in b["events"]:
            if ps is not None and tie_open is not None and ev[tie_open][2] == ps:
                on, d0, p0 = ev[tie_open]
                ev[tie_open] = (on, d0 + dur, p0)
            elif ps is not None:
                ev.append((t, dur, ps))
            tie_open = (len(ev) - 1) if (tie and ps is not None) else None
            t += dur
    return ev, info


def check(abc_text, tune):
    """Compare ABC playback with the MIDI; returns (ok, messages)."""
    msgs = []
    try:
        ev, info = abc_played(abc_text)
    except Exception as e:  # noqa: BLE001
        return False, [f"could not parse ABC: {e}"]
    whole = tune.tpb * 4
    mid = [(F(on, whole), F(d, whole), p) for on, d, p in played_events(tune)]
    # align start: ABC may begin at the same time as MIDI (no leading rest in both)
    off_a = ev[0][0] if ev else 0
    off_m = mid[0][0] if mid else 0

    def bar_of(t):
        k = 0
        for j, (st, ln, m) in enumerate(info):
            if st <= t:
                k = j
        return k + 1

    ok = True
    if ev and len(mid) > len(ev) and len(mid) % len(ev) == 0:
        # the MIDI may play the whole tune several times; compare one pass
        k, n = len(mid) // len(ev), len(ev)
        span = mid[n][0] - mid[0][0]
        if all((mid[j][0] - mid[j % n][0], mid[j][1:]) == (span * (j // n), mid[j % n][1:])
               for j in range(len(mid))):
            msgs.append(f"note: the MIDI plays the tune {k} times; compared one pass")
            mid = mid[:n]
    for j in range(max(len(ev), len(mid))):
        a = ev[j] if j < len(ev) else None
        m = mid[j] if j < len(mid) else None
        if a is None or m is None:
            ok = False
            msgs.append(f"note count differs: ABC plays {len(ev)} notes, MIDI {len(mid)}")
            break
        at, ad, ap = a[0] - off_a, a[1], a[2]
        mt, md, mp = m[0] - off_m, m[1], tuple(m[2])
        if (at, ad, ap) != (mt, md, mp):
            ok = False
            msgs.append(
                f"first difference at played note {j + 1} (played bar {bar_of(a[0])}): "
                f"ABC {fmt_ev(at, ad, ap)} vs MIDI {fmt_ev(mt, md, mp)}")
            break
    # bar lengths
    odd = []
    for j, (st, ln, meter) in enumerate(info):
        if ln != meter:
            odd.append(f"{j + 1}:{ln}")
    if odd:
        msgs.append("played bars not matching the meter (bar:length in whole notes; "
                    "a pickup and its complementary last bar are normal): " + ", ".join(odd[:20])
                    + (" ..." if len(odd) > 20 else ""))
    return ok, msgs


def check_loose(abc_text, tune):
    """For when the ABC follows the score's repeat marks but the MIDI plays a
    different number of passes: align the two note streams and accept only
    differences that are a whole passage played one extra time on one side."""
    ev, _ = abc_played(abc_text)
    whole = tune.tpb * 4
    a = [(d, p) for t, d, p in ev]
    b = [(F(d, whole), tuple(p)) for on, d, p in played_events(tune)]
    extra = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if tag == "equal":
            continue
        if tag == "replace":
            return False, f"ABC notes {i1 + 1}-{i2} differ from MIDI notes {j1 + 1}-{j2}"
        seq, x1, x2, who = (b, j1, j2, "MIDI") if tag == "insert" else (a, i1, i2, "ABC")
        n = x2 - x1
        if seq[x1:x2] not in (seq[x1 - n:x1], seq[x2:x2 + n]):
            return False, f"{who} notes {x1 + 1}-{x2} are extra and are not a repeat"
        extra.append(f"{who} plays notes {x1 + 1}-{x2} one extra time")
    return True, "; ".join(extra)


def fmt_ev(t, d, p):
    names = "+".join(PC_NAME[x % 12] + str(x // 12 - 1) for x in p)
    return f"{names} at {t} len {d}"


# ------------------------------------------------------------------------ CLI

def load_info(mid_path):
    p = Path(mid_path).with_name("info.json")
    if p.exists():
        return json.loads(p.read_text())
    return {}


def hint_to_key(hint, tune):
    """Index key hints like 'Em~', 'D^', 'Am*' -> ABC key with the MIDI's signature."""
    m = re.match(r"([A-G][#b]?)(m?)", hint or "")
    if not m or not tune.key:
        return None, None
    try:
        nsharps, _ = parse_key(tune.key)
    except ValueError:
        return None, None
    tonic = m.group(1)
    pc = (LETTER_PC[tonic[0]] + (1 if "#" in tonic else -1 if "b" in tonic else 0)) % 12
    lab = key_label(nsharps, pc, minorish=bool(m.group(2)))
    if lab[0] != tonic[0] or lab.endswith(("Phr", "Lyd", "Loc")):
        return None, (f"WARNING: the index says the tune is in {tonic}{m.group(2)} but the "
                      f"MIDI's key signature is {tune.key}: the MIDI may be transposed from "
                      f"the score (see --transpose), or the MIDI's key signature is wrong")
    return lab, None


def parse_pickup(s, tpb):
    if s is None:
        return None
    if "/" in s:
        return int(F(s) * tpb * 4)
    return int(s)


def read_directive(abc_text):
    """Options the ABC was made with: '%%alawon track=1 transpose=-5 pickup=1/8 bars=1-16'."""
    m = re.search(r"^%%alawon\s+(.*)$", abc_text, re.M)
    return dict(kv.split("=", 1) for kv in m.group(1).split()) if m else {}


def load_tune(midi, track=None, transpose=0, bars=None, pickup=None):
    """Tune with the given options applied; returns (tune, pickup, directive)."""
    tune = Tune(midi, track, transpose)
    pk = parse_pickup(pickup, tune.tpb)
    if pk is None:
        pk = guess_pickup(tune)
    opts = [f"track={tune.track}"]
    if transpose:
        opts.append(f"transpose={transpose}")
    if bars:
        first, _, last = bars.partition("-")
        opts.append(f"pickup={F(pk, tune.tpb * 4)}")
        opts.append(f"bars={bars}")
        pk = tune.select_bars(int(first), int(last or 10**6), pk)
    tune.fit_final_note(pk)
    return tune, pk, " ".join(opts)


def cmd_convert(a):
    tune, pickup, directive = load_tune(a.midi, a.track, a.transpose, a.bars, a.pickup)
    info = load_info(a.midi)
    key, warning = (a.key, None) if a.key else hint_to_key(info.get("key_hint"), tune)
    text, meta = to_abc(
        tune, pickup=pickup, fold=not a.no_fold,
        bars_per_line=a.bars_per_line, title=a.title or info.get("name", Path(a.midi).stem),
        aliases=info.get("aliases", []), rhythm=info.get("type", ""), key=key,
        source=info.get("page_url", ""), directive=directive)
    out = Path(a.output) if a.output else Path(a.midi).with_suffix(".abc")
    out.write_text(text)
    ok, msgs = check(text, tune)
    if warning:
        msgs.insert(0, warning)
    extra = f", other note tracks: {tune.note_tracks}" if len(tune.note_tracks) > 1 else ""
    print(f"{out}: {meta['bars']} bars, pickup {F(meta['pickup'], tune.tpb * 4)}, "
          f"K:{meta['key']}, track {tune.track}{extra} -> check {'OK' if ok else 'FAILED'}")
    for m in msgs:
        print("  " + m)
    return 0 if ok else 1


def cmd_check(a):
    text = Path(a.abc).read_text()
    d = read_directive(text)
    tune, pickup, _ = load_tune(a.midi, int(d["track"]) if "track" in d else None,
                                int(d.get("transpose", 0)), d.get("bars"), d.get("pickup"))
    ok, msgs = check(text, tune)
    if ok:
        print("OK: ABC plays the same notes as the MIDI")
    else:
        bars_ok, why = check_loose(text, tune)
        print("REPEATS-DIFFER: same music, but " + why +
              " (fine if that is what the score's repeat marks say)"
              if bars_ok else "MISMATCH")
        if not bars_ok:
            msgs.append(why)
    for m in msgs:
        print("  " + m)
    return 0 if ok else 2 if bars_ok else 1


def cmd_bars(a):
    """Print the MIDI bar by bar (repeats written out) with played-bar numbers."""
    tune, pickup, _ = load_tune(a.midi, a.track, a.transpose, None, a.pickup)
    ks = tune.key or "C"
    nsharps = parse_key(ks)[0]
    unit = tune.tpb // 2
    print(f"track {tune.track} of note tracks {tune.note_tracks}; key signature {ks}; "
          f"meter {tune.meters}; pickup {F(pickup, tune.tpb * 4)}")
    for i, b in enumerate(split_bars(tune, pickup)):
        print(f"{i + 1:4d}  {bar_text(b, nsharps, unit, tune.tpb)}")
    return 0


REVIEWED = "%%alawon-reviewed"


def cmd_batch(a):
    root = Path(a.dir)
    failed = 0
    for mid in sorted(root.glob("*/tune.mid")):
        out = mid.with_suffix(".abc")
        if out.exists() and (not a.force or REVIEWED in out.read_text()):
            continue
        try:
            ns = argparse.Namespace(midi=str(mid), output=str(out), track=None, pickup=None,
                                    no_fold=False, bars_per_line=4, title=None, key=None,
                                    transpose=0, bars=None)
            failed += cmd_convert(ns) != 0
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"{mid}: ERROR {e}")
    print(f"done, {failed} failed")
    return 1 if failed else 0


def cmd_status(a):
    root = Path(a.dir)
    rows = {"reviewed": [], "converted": [], "no abc": [], "no midi": []}
    for d in sorted(p for p in root.iterdir() if p.is_dir()):
        abc, mid = d / "tune.abc", d / "tune.mid"
        if not mid.exists() or not mid.stat().st_size:
            rows["no midi"].append(d.name)
        elif not abc.exists():
            rows["no abc"].append(d.name)
        elif REVIEWED in abc.read_text():
            rows["reviewed"].append(d.name)
        else:
            rows["converted"].append(d.name)
    for k, v in rows.items():
        print(f"{k:10s} {len(v):4d}" + (f"  {', '.join(v[:12])}{' ...' if len(v) > 12 else ''}"
                                        if a.verbose or k in ("no abc", "no midi") else ""))
    return 0


def cmd_collect(a):
    root = Path(a.dir)
    out, n = [], 0
    for abc in sorted(root.glob("*/tune.abc")):
        text = abc.read_text()
        if a.reviewed_only and REVIEWED not in text:
            continue
        n += 1
        text = re.sub(r"^X:.*$", f"X:{n}", text, count=1, flags=re.M)
        out.append(text.strip() + "\n")
    Path(a.output).write_text("\n".join(out))
    print(f"wrote {n} tunes to {a.output}")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("convert")
    c.add_argument("midi")
    c.add_argument("-o", "--output")
    c.add_argument("--track", type=int, help="MIDI track with the melody (default: first with notes)")
    c.add_argument("--pickup", help="anacrusis length, e.g. 1/8, 1/4, 3/8, or 0 (default: guess)")
    c.add_argument("--no-fold", action="store_true", help="write repeats out in full")
    c.add_argument("--bars-per-line", type=int, default=4)
    c.add_argument("--title")
    c.add_argument("--key", help="ABC key, e.g. Em, DMix, ADor (default: index hint / final note)")
    c.add_argument("--transpose", type=int, default=0,
                   help="semitones, when the MIDI is in a different key from the score")
    c.add_argument("--bars", help="only these played bars of the MIDI, e.g. 1-16 (see `bars`)")
    c.set_defaults(func=cmd_convert)
    s_ = sub.add_parser("bars", help="list the MIDI bar by bar with numbers")
    s_.add_argument("midi")
    s_.add_argument("--track", type=int)
    s_.add_argument("--transpose", type=int, default=0)
    s_.add_argument("--pickup")
    s_.set_defaults(func=cmd_bars)
    k = sub.add_parser("check")
    k.add_argument("abc")
    k.add_argument("midi")
    k.set_defaults(func=cmd_check)
    b = sub.add_parser("batch")
    b.add_argument("dir")
    b.add_argument("--force", action="store_true",
                   help="reconvert existing tune.abc files (never reviewed ones)")
    b.set_defaults(func=cmd_batch)
    st = sub.add_parser("status")
    st.add_argument("dir")
    st.add_argument("-v", "--verbose", action="store_true")
    st.set_defaults(func=cmd_status)
    co = sub.add_parser("collect", help="concatenate tune.abc files into one tunebook")
    co.add_argument("dir")
    co.add_argument("-o", "--output", required=True)
    co.add_argument("--reviewed-only", action="store_true")
    co.set_defaults(func=cmd_collect)
    a = ap.parse_args()
    sys.exit(a.func(a))


if __name__ == "__main__":
    main()
