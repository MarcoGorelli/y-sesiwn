"""Shared setup for the tests: build the site once, serve it, and open a browser.

    pip install -r requirements-dev.txt && python -m playwright install chromium
    python -m pytest            # everything (about a minute)
    python -m pytest -m "not browser"   # just the quick build checks
"""
import functools
import http.server
import sys
import threading
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

import build_site  # noqa: E402


@pytest.fixture(scope="session")
def site():
    """Build _site/ and serve it on a free local port; yields the base URL."""
    build_site.main()
    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *args):
            pass

    handler = functools.partial(Quiet, directory=str(build_site.OUT))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}/"
    server.shutdown()


@pytest.fixture(scope="session")
def playwright_instance():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        yield p


@pytest.fixture(scope="session")
def browser(playwright_instance):
    browser = playwright_instance.chromium.launch()
    yield browser
    browser.close()


@pytest.fixture
def page(browser, site):
    """A fresh page (no service worker, so every test sees the latest build) that
    fails the test on any JavaScript error."""
    context = browser.new_context(viewport={"width": 1300, "height": 1000}, service_workers="block")
    context.set_default_timeout(10000)  # fail fast: nothing should take this long
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto_site = lambda path="": (page.goto(site + path), page.wait_for_function("typeof state !== 'undefined' && state.data"))[0]
    yield page
    context.close()
    assert not errors, f"JavaScript errors: {errors}"
