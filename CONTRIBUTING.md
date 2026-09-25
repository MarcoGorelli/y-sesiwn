# How to add a tune

Every tune in Y Sesiwn is a single text file in
[ABC notation](https://abcnotation.com/): `tunes/<folder>/tune.abc` in the
[GitHub repository](https://github.com/MarcoGorelli/y-sesiwn). The sheet
music, playback and key changes are all made from that file. To add a tune,
you write its ABC file and propose it with a *pull request*. Once it's
accepted, the app updates by itself.

## 1. Write the tune in ABC

Here is a complete example:

```
X:1
T:Llancesau Trefaldwyn
R:jig
M:6/8
L:1/8
K:D
AG |: F2 F GFG | AFD DFA | B2 c dcB | ABG FGE |
F2 F GFG | AFD DFA | Bgf edc |1 d3 dAG :|
[2 d3 dcd || e2 c Ace | f2 d Adf | gfe fed |
ecA Acd | e2 c Ace | f2 d Adf | efd cdB
|: ABG FGE | F2 F GFG | AFD DFA |1 B2 c dcB :|
[2 Bgf edc || d3 d |]
```

The lines at the top are the *header*:

| Line | Needed? | What it is |
|---|---|---|
| `X:1` | yes | Always `X:1`. |
| `T:` | yes | The title, as printed on the sheet music. |
| `R:` | recommended | Tune type, e.g. `jig`, `rîl`, `polca`, `walts`, `pibddawns`. It sets the default tempo: jigs 112, reels 90, polcas 100, anything else 100 bpm. |
| `M:` | yes | Time signature, e.g. `6/8`, `4/4`, `3/4`. |
| `L:` | yes | Default note length, usually `1/8`. |
| `K:` | yes, **last** | Key, e.g. `D`, `Em`, `ADor`. The notes start on the next line. |
| `C:` | optional | Composer or arranger. |
| more `T:` lines | optional | Other names for the tune; they're searchable too. |
| `B:`, `N:`, `O:`, `S:` | optional | Book, notes, place of origin, source. Shown under Details. |

About titles:

- Use the name printed on the sheet music, without brackets.
- If a tune with the same name is already in the app, call yours
  `<Name> (version 2)` (or 3, 4, …). All versions of a tune share one page,
  with a tab for each; a `B:` line (the book it's from) labels your tab.
- Tempo lines (`Q:`) are ignored: the app's tempo slider decides.

If you're new to ABC, the [ABC notation primer](https://abcnotation.com/learn)
explains the notes and bar lines.

## 2. Check that it looks and sounds right

Paste your ABC into the [abcjs Quick Editor](https://editor.drawthedots.com/).
It uses the same library as Y Sesiwn, so if the sheet music looks right and
plays right there, it will in the app too.

## 3. Choose the folder name

The folder is named after the title: lowercase, accents removed, and anything
that isn't a letter or number turned into a hyphen.

| Title | Folder |
|---|---|
| Llancesau Trefaldwyn | `tunes/llancesau-trefaldwyn/` |
| Codi'r Hwyl | `tunes/codi-r-hwyl/` |
| Tŷ Coch Caerdydd (version 2) | `tunes/ty-coch-caerdydd-version-2/` |

## 4. Open a pull request

### In the browser (no installing anything)

1. Sign in to GitHub and open the
   [Y Sesiwn repository](https://github.com/MarcoGorelli/y-sesiwn).
2. Click **Add file → Create new file**. GitHub will offer to make your own
   copy (a *fork*) first; accept.
3. In the file name box, type the full path, e.g.
   `tunes/codi-r-hwyl/tune.abc`. Typing `/` creates the folders.
4. Paste your ABC into the editor.
5. Click **Commit changes…**, then **Propose changes**, then
   **Create pull request**. Say in the description where the tune comes from.

### With git

```bash
git clone https://github.com/<your-username>/y-sesiwn.git   # after forking
cd y-sesiwn
git switch -c add-codi-r-hwyl
mkdir tunes/codi-r-hwyl
# write tunes/codi-r-hwyl/tune.abc
git add tunes/codi-r-hwyl/tune.abc
git commit -m "Add Codi'r Hwyl"
git push -u origin add-codi-r-hwyl
```

Then open the pull request from your fork on GitHub.

To see it in the app before proposing it, run Y Sesiwn locally:

```bash
python build_site.py
python -m http.server -d _site 8000
```

and open http://localhost:8000.

## What happens next

The maintainer reviews the pull request and may suggest changes. Once it's
merged, the [live app](https://ysesiwn.cymru/) redeploys and the tune
appears in search.

Only `tune.abc` is needed: no score image or MIDI file.

# How to submit corrections

Spotted a wrong note, a misspelt title, the wrong key or tune type, or know
who composed a tune? There are two ways to fix it.

## Tell us about it

[Open an issue](https://github.com/MarcoGorelli/y-sesiwn/issues/new) on
GitHub (you'll need a free GitHub account). Say:

- which tune, with its title as shown in the app;
- what's wrong and what it should be (for example "bar 5 should be
  `B2 AB`", or "the title should be *Y Gaseg Felen*");
- where the correct version comes from, if you know (a book, a recording,
  a website).

## Fix it yourself with a pull request

1. Find the tune's file. Each tune is `tunes/<folder>/tune.abc`, and the folder
   is named after the title (lowercase, accents removed, hyphens between
   words), so *Sawdl y Fuwch* is `tunes/sawdl-y-fuwch/tune.abc`. On the
   [repository page](https://github.com/MarcoGorelli/y-sesiwn), press `t` and
   type part of the name to find it.
2. Open the file and click the pencil icon (**Edit this file**). GitHub will
   offer to make your own copy (a *fork*) first; accept.
3. Make your change. The notes follow the `K:` line; the header lines above it
   hold the title (`T:`), tune type (`R:`), key (`K:`) and so on; see
   [How to add a tune](#how-to-add-a-tune) for what each line means. You can
   add a composer (`C:`) or another name for the tune (an extra `T:` line).
   Leave the `%%alawon ...` line as it is.
4. Paste the whole file into the
   [abcjs Quick Editor](https://editor.drawthedots.com/) to check it still
   looks and plays right.
5. Click **Commit changes…**, then **Propose changes**, then
   **Create pull request**. Say what you changed and why.

If you change the first `T:` title, the folder name should change to match.
You can do that in the same edit by changing the path in the file name box
(e.g. `tunes/old-name/tune.abc` to `tunes/new-name/tune.abc`), or just mention
it in the pull request and the maintainer will rename it.

Once the pull request is merged, the
[live app](https://ysesiwn.cymru/) shows the corrected tune.
