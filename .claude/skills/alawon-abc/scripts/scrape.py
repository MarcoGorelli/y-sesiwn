#!/usr/bin/env python3
"""Download the tunes on alawoncymru.com: one MIDI file + score image per tune.

Usage:
    scrape.py [--out DIR] [--only SUBSTRING] [--refresh] [--no-download]

Writes DIR/manifest.json and, per tune, DIR/<slug>/ containing:
    tune.mid     the melody MIDI
    score.gif    the score image shown on the set page
    info.json    names, key/type from the index, source URLs, pairing confidence

The site is hand-edited HTML and its index often links to the wrong anchor, so
tunes are found page by page: each MIDI is paired with the score image whose
filename it abbreviates best (e.g. MympLlMS.mid <-> MympLlD.gif), helped by the
#aN anchors, and names come from the index entries pointing at that page.
Always glance at score.gif before trusting a pairing marked "low".
"""
import argparse
import html
import json
import re
import sys
import time
import unicodedata
import urllib.parse
import urllib.request
from collections import defaultdict
from pathlib import Path

INDEX_URL = "http://alawoncymru.com/alawon/Tunes/Tunesal.html"
UA = {"User-Agent": "Mozilla/5.0 (alawon-abc scraper)"}


def fetch(url, retries=3):
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read()
        except Exception:  # noqa: BLE001 - old server, just retry
            if attempt == retries - 1:
                raise
            time.sleep(1 + attempt)


def clean(s):
    s = re.sub(r"<[^>]+>", "", s)
    s = html.unescape(s)
    return re.sub(r"\s+", " ", s).strip()


def norm(s):
    s = urllib.parse.unquote(s)
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]", "", s)


def slugify(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    s = re.sub(r"[^A-Za-z0-9]+", "-", s).strip("-")
    return s or "tune"


def stem(url):
    return norm(Path(urllib.parse.urlparse(url).path).stem)


def abbrev_score(short, full):
    """How well `short` (e.g. filename stem 'mympllms') abbreviates `full`
    ('mympwyllwyd'): shared prefix plus fraction of chars matched in order."""
    if not short or not full:
        return 0.0
    pre = 0
    while pre < min(len(short), len(full)) and short[pre] == full[pre]:
        pre += 1
    j = matched = 0
    for ch in short:
        k = full.find(ch, j)
        if k >= 0:
            matched += 1
            j = k + 1
    return min(pre, 6) / 6 + matched / len(short)


def sim(a, b):
    return max(abbrev_score(a, b), abbrev_score(b, a))


def file_sim(a, b):
    """Similarity of a MIDI and an image filename stem."""
    s = sim(a, b)
    da, db = re.sub(r"\D", "", a), re.sub(r"\D", "", b)
    if da != db:  # version numbers must agree: HufMel32M.mid <-> HufenMel32.gif
        s -= 0.8
    elif da:
        s += 0.3
    return s


def name_keys(name):
    """Normalised name with and without a leading article: '(Y) Gog Lwydlas'."""
    n = re.sub(r"[()]", "", name)
    return {norm(n), norm(re.sub(r"^(y|yr|r)\s+", "", n, flags=re.I))} - {""}


# ---------------------------------------------------------------- index page

KEY_RE = re.compile(r"^(.*?)\s*\(\s*([A-G][#b]?m?\s*[~*^]?)\s*\)\s*(?:\((.*?)\))?", re.S)


def parse_index(page):
    """Index entries are <br>-separated lines like
    'Abergenni (Em~) (dawns llys)' with (possibly several, broken) links."""
    entries = []
    for chunk in re.split(r"<br\s*/?>", page, flags=re.I):
        hrefs = re.findall(r'href="([^"#:]+\.html?)(?:#(a\d+))?"', chunk, re.I)
        if not hrefs:
            continue
        m = KEY_RE.match(clean(chunk))
        if not m or not m.group(1) or len(m.group(1).split()) > 8:
            continue  # not a tune line (e.g. the page heading before the first tune)
        # the page most of the line's links point to; the first anchor seen for it
        pages = [h for h, a in hrefs]
        page_ref = max(pages, key=pages.count)  # first of the most common
        anchor = next((a for h, a in hrefs if h == page_ref and a), "")
        entries.append({"name": m.group(1).strip(" -"), "key_hint": m.group(2).strip(),
                        "type": (m.group(3) or "").strip(),
                        "page": page_ref, "anchor": anchor})
    return entries


# ------------------------------------------------------------------ set page

def parse_set_page(page):
    toks = []
    for m in re.finditer(r'href="((?!file:)[^"]+\.midi?)"', page, re.I):
        toks.append((m.start(), "mid", m.group(1)))
    for m in re.finditer(r'href="#(a\d+)"', page, re.I):
        toks.append((m.start(), "link", m.group(1)))
    for m in re.finditer(r'<a\s+name="(a\d+)"', page, re.I):
        toks.append((m.start(), "anchor", m.group(1)))
    for m in re.finditer(r'<img[^>]*src="([^"]+\.(?:gif|png|jpe?g))"', page, re.I):
        src = m.group(1)
        if not (src.startswith("..") or src.startswith("http")):  # skip site chrome
            toks.append((m.start(), "img", src))
    toks.sort()
    return toks


def page_pairs(toks):
    """Pair MIDIs with score images on one set page.
    Returns [(midi, image, anchor, score)], unpaired midis, unpaired images."""
    mids, midi_anchor, last = [], {}, None
    for pos, kind, val in toks:
        if kind == "mid":
            last = val
            if val not in mids:
                mids.append(val)
        elif kind == "link" and last and last not in midi_anchor:
            midi_anchor[last] = val  # first #aN link in the MIDI's table row
        elif kind == "img":
            last = None
    anchors = [(p, v) for p, k, v in toks if k == "anchor"]
    imgs, img_anchor = [], {}
    for p, k, v in toks:
        if k == "img" and v not in imgs:
            imgs.append(v)
            if anchors:
                img_anchor[v] = min(anchors, key=lambda a: abs(a[0] - p))[1]

    cand = []
    for mi in mids:
        for im in imgs:
            s = file_sim(stem(mi), stem(im))
            if midi_anchor.get(mi) and midi_anchor.get(mi) == img_anchor.get(im):
                s += 0.4
            cand.append((s, mi, im))
    cand.sort(reverse=True)
    used_m, used_i, pairs = set(), set(), []
    for s, mi, im in cand:
        if s < 1.0 or mi in used_m or im in used_i:
            continue
        used_m.add(mi)
        used_i.add(im)
        pairs.append((mi, im, img_anchor.get(im) or midi_anchor.get(mi, ""), s))
    # fallbacks for files named after something else: same anchor, then page order
    lone_m = [m for m in mids if m not in used_m]
    lone_i = [i for i in imgs if i not in used_i]
    for mi in list(lone_m):
        im = next((i for i in lone_i if midi_anchor.get(mi)
                   and img_anchor.get(i) == midi_anchor.get(mi)), None)
        if im:
            pairs.append((mi, im, midi_anchor[mi], 0.5))
            used_m.add(mi)
            used_i.add(im)
            lone_m.remove(mi)
            lone_i.remove(im)
    if lone_m and len(lone_m) == len(lone_i):
        for mi, im in zip(lone_m, lone_i):
            pairs.append((mi, im, img_anchor.get(im, ""), 0.0))
            used_m.add(mi)
            used_i.add(im)
    return pairs,[m for m in mids if m not in used_m], [i for i in imgs if i not in used_i]


def assign_names(pairs, entries):
    """Match this page's index entries to pairs -> {pair_idx: [(entry, score)]}."""
    cand = []
    for i, (mi, im, anc, _) in enumerate(pairs):
        for j, e in enumerate(entries):
            s = max((sim(stem(x), k) for x in (mi, im) for k in name_keys(e["name"])),
                    default=0.0)
            if e["anchor"] and e["anchor"] == anc:
                s += 0.3
            cand.append((s, i, j))
    cand.sort(reverse=True)
    out, used_p, used_e = defaultdict(list), set(), set()
    for s, i, j in cand:  # one confident name per pair
        if s >= 1.0 and i not in used_p and j not in used_e:
            out[i].append((entries[j], s))
            used_p.add(i)
            used_e.add(j)
    for j, e in enumerate(entries):  # aliases go to their best pair
        if j in used_e:
            continue
        best = max((c for c in cand if c[2] == j), default=None)
        if best and best[0] >= 1.0:
            out[best[1]].append((e, best[0]))
            used_e.add(j)
    for i, (mi, im, anc, _) in enumerate(pairs):  # anchor-only fallback
        if i in out:
            continue
        for j, e in enumerate(entries):
            if j not in used_e and e["anchor"] and e["anchor"] == anc:
                out[i].append((e, 0.0))
                used_e.add(j)
                break
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default="tunes")
    ap.add_argument("--only", help="only tunes whose name/set page contains this (case-insensitive)")
    ap.add_argument("--refresh", action="store_true", help="re-download existing files")
    ap.add_argument("--no-download", action="store_true", help="just write the manifest")
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    base = INDEX_URL.rsplit("/", 1)[0] + "/"
    entries = parse_index(fetch(INDEX_URL).decode("utf-8", "replace"))
    by_page = defaultdict(list)
    for e in entries:
        by_page[urllib.parse.urljoin(base, e["page"])].append(e)
    print(f"{len(entries)} index lines, {len(by_page)} set pages", file=sys.stderr)

    manifest, leftovers = [], []
    for page_url, page_entries in by_page.items():
        try:
            toks = parse_set_page(fetch(page_url).decode("utf-8", "replace"))
        except Exception as e:  # noqa: BLE001
            print(f"  ! {page_url}: {e}", file=sys.stderr)
            continue
        pairs, lone_mids, lone_imgs = page_pairs(toks)
        names = assign_names(pairs, page_entries)
        join = lambda v: urllib.parse.urljoin(page_url, v)  # noqa: E731
        for i, (mi, im, anc, pair_score) in enumerate(pairs):
            named = names.get(i, [])
            first = named[0][0] if named else {}
            name = first.get("name") or Path(urllib.parse.unquote(im)).stem
            aliases = []
            for e, _ in named[1:]:
                if e["name"] not in aliases and e["name"] != name:
                    aliases.append(e["name"])
            name_score = named[0][1] if named else 0.0
            manifest.append({
                "name": name, "aliases": aliases,
                "key_hint": first.get("key_hint", ""), "type": first.get("type", ""),
                "page_url": page_url, "anchor": anc,
                "midi_url": join(mi), "score_urls": [join(im)],
                "pairing": "high" if pair_score >= 1.4 and name_score >= 1.0 else "low",
            })
        if lone_mids or lone_imgs:
            leftovers.append({"page_url": page_url,
                              "unpaired_midis": [join(m) for m in lone_mids],
                              "unpaired_images": [join(i) for i in lone_imgs]})

    # the same tune can sit on several set pages; keep one copy
    seen, unique = {}, []
    for e in manifest:
        k = (Path(e["midi_url"]).name.lower(), norm(e["name"]))
        if k in seen:
            seen[k].setdefault("also_on", []).append(e["page_url"])
            continue
        seen[k] = e
        unique.append(e)
    manifest = unique
    slugs = set()
    for entry in manifest:
        base_slug = slugify(entry["name"])
        slug, n = base_slug, 2
        while slug in slugs:
            slug, n = f"{base_slug}-{n}", n + 1
        slugs.add(slug)
        entry["slug"] = slug

    todo = manifest
    if args.only:  # the manifest always lists every tune; --only limits downloads
        q = args.only.lower()
        todo = [e for e in manifest
                if q in e["name"].lower() or q in e["page_url"].lower() or q in e["slug"].lower()
                or any(q in a.lower() for a in e["aliases"])]
    for entry in [] if args.no_download else todo:
        d = out / entry["slug"]
        d.mkdir(exist_ok=True)
        files = [(entry["midi_url"], d / "tune.mid")]
        for i, s in enumerate(entry["score_urls"]):
            ext = Path(urllib.parse.urlparse(s).path).suffix.lower()
            files.append((s, d / f"score{i + 1 if i else ''}{ext}"))
        for url, dest in files:
            if dest.exists() and dest.stat().st_size and not args.refresh:
                continue
            try:
                data = fetch(url)
                if not data:
                    raise ValueError("empty file on the server")
                dest.write_bytes(data)
            except Exception as e:  # noqa: BLE001
                entry.setdefault("download_errors", []).append(f"{url}: {e}")
        (d / "info.json").write_text(json.dumps(entry, indent=1, ensure_ascii=False))
        if entry.get("download_errors"):
            print(f"  ! {entry['slug']}: {'; '.join(entry['download_errors'])}", file=sys.stderr)

    (out / "manifest.json").write_text(json.dumps(manifest, indent=1, ensure_ascii=False))
    (out / "unpaired.json").write_text(json.dumps(leftovers, indent=1, ensure_ascii=False))
    low = sum(1 for e in manifest if e["pairing"] == "low")
    print(f"wrote {out / 'manifest.json'}: {len(manifest)} tunes ({low} low-confidence "
          f"pairings); unpaired files per page in {out / 'unpaired.json'}", file=sys.stderr)


if __name__ == "__main__":
    main()
