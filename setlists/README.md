# Setlists

The tunes played at a session, night by night, as people send them in (the form on each
session's page writes the email). One file per session, named after its id in the
session's address: `sesiynau/chapter-cardiff-tuesday/` is `chapter-cardiff-tuesday.json`.

```json
{
  "setlists": [
    {"date": "2026-10-20", "tunes": [
      {"tune": "glandyfi", "key": "A major"},
      {"tune": "y-derwydd", "key": "G major"},
      {"name": "Drowsy Maggie"}
    ]}
  ]
}
```

- `date`: the night, which must be a day the session meets (from `sessions.json`).
- `tunes`: in the order played. Each is `{"tune": …, "key": …}`, or `{"name": "…"}` for a
  tune that isn't on the site.
- `tune`: the folder in `tunes/` of the version played (`glandyfi-version-2`, say). A
  folder that's been renamed since still works (through `moved.json`).
- `key`: the key it was played in, written like the key menu on the tune's page:
  `"A major"`, `"E minor"`, `"D Dorian"` (or just `"A"`), in that version's own mode.
  Every tune needs one; a night's page starts each tune's Play in it.
- Add each new night to the list. Their order doesn't matter: the site shows the newest first.

Each night gets its own page (`sesiynau/<id>/<date>/`), and the session's page lists them
all, with the tunes played most there once it has three nights' worth. They're only
fetched on those pages, so they don't make the rest of the site any heavier.

If a session stops, or moves to another day (which gives it a new id), the build will
say so. Add `"venue"` and `"town"` to its file (and `"name"`, `"town_cy"` or `"kind"` if
it had them) to keep its old nights. A session that moved starts a new file under its
new id.
