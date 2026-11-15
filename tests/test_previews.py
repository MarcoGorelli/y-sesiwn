"""The link-preview pictures (previews.py, build_site.py --previews)."""
import struct
from concurrent.futures import ThreadPoolExecutor

import build_site as b
import previews


def draw(items):
    # In a thread of its own: the browser tests' Playwright keeps an event loop running in
    # this one, where Playwright's sync API (as build_site.py uses it) won't start.
    with ThreadPoolExecutor(1) as pool:
        return pool.submit(previews.draw_previews, items).result()


def size(png):
    return struct.unpack(">II", png.read_bytes()[16:24])


def test_pictures_drawn_once(tmp_path, monkeypatch):
    """Each tune gets a 1200x630 picture, named by what's in it: drawn again only when the tune changes."""
    monkeypatch.setattr(previews, "CACHE", tmp_path)
    abc = (b.ROOT / "tunes" / "y-gaseg-ddu" / "tune.abc").read_text(encoding="utf-8")
    item = {"name": "Y Gaseg Ddu", "type": "Cân", "colour": "#a3456a", "key": {"root": "G", "modeName": "major"}, "abc": abc}
    first = draw({"y-gaseg-ddu": item})["y-gaseg-ddu"]
    assert size(first) == (1200, 630)
    when = first.stat().st_mtime_ns
    assert draw({"y-gaseg-ddu": item})["y-gaseg-ddu"].stat().st_mtime_ns == when
    changed = draw({"y-gaseg-ddu": {**item, "abc": abc.replace("K:G", "K:A")}})["y-gaseg-ddu"]
    assert changed != first and not first.exists()  # the old one isn't kept


def test_opening_leaves_out_headers_chords_and_verses():
    abc = 'X:1\nT:Rhuban\nR:walts\nM:3/4\nL:1/8\nK:F\n"^Ad-libitum""F"f2e2d2|"Bb"c2B2A2|\nw: la la\nW:Verse two'
    head, music = previews.opening(abc).split("\n---\n")
    assert head == "X:1\nM:3/4\nL:1/8\nK:F"
    assert music == '"^Ad-libitum"f2e2d2|c2B2A2|\nw: la la'


def test_page_shows_its_picture():
    template = (b.ROOT / "site" / "index.html").read_text(encoding="utf-8")
    page = b.app_page(template, path="alaw/llwyn-onn/", title="Llwyn Onn", description="d", main="",
                      image=("alaw/llwyn-onn/preview-abc.png", "Dechrau sgôr Llwyn Onn"), lang="cy")
    assert f'<meta property="og:image" content="{b.SITE_URL}alaw/llwyn-onn/preview-abc.png">' in page
    assert '<meta property="og:image:alt" content="Dechrau sgôr Llwyn Onn">' in page
    # A page without a picture of its own keeps the site's.
    assert f'<meta property="og:image" content="{b.SITE_URL}og-image.png' in b.app_page(
        template, path="am/", title="About", description="d", main="")
