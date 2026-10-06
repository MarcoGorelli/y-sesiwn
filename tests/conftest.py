"""Shared setup for the tests: build the site once, serve it, and open a browser.

    pip install -r requirements-dev.txt && python -m playwright install chromium
    python -m pytest            # everything (a few minutes)
    python -m pytest -m "not browser"   # just the quick build checks
"""
import functools
import http.server
import re
import sys
import threading
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

import build_site  # noqa: E402


SERVED = []  # every answer the test server gives: (path, status), for tests that count them


@pytest.fixture(scope="session")
def site():
    """Build _site/ and serve it on a free local port; yields the base URL."""
    build_site.main()
    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_request(self, code="-", size="-"):
            SERVED.append((self.path, int(code)))

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


TRACES = ROOT / "test-results"


@pytest.hookimpl(wrapper=True)
def pytest_runtest_makereport(item, call):
    report = yield
    if report.when == "call":
        item.call_failed = report.failed
    return report


@pytest.fixture(autouse=True)
def browser_contexts(request, monkeypatch):
    """Every browser context a test opens (the page fixture's, or its own): it fails
    fast, is closed afterwards even if the test fails, and on a failure keeps a trace
    in test-results/ (open it with `playwright show-trace`, or at trace.playwright.dev)."""
    if "browser" not in request.fixturenames:
        yield
        return
    browser = request.getfixturevalue("browser")
    new_context = browser.new_context
    opened, closed = [], []

    def traced(**kwargs):
        # No fade-in as each page opens: while it plays, things are still moving, and a
        # click's retries scroll the page (to a sticky bar's place at the bottom, say).
        kwargs.setdefault("reduced_motion", "reduce")
        context = new_context(**kwargs)
        context.set_default_timeout(10000)  # nothing should take this long
        context.tracing.start(screenshots=True)  # (DOM snapshots would change what <base href> resolves to)
        close = context.close

        def close_with_trace(**kwargs):
            if context in closed:
                return
            closed.append(context)
            if getattr(request.node, "call_failed", False):
                TRACES.mkdir(exist_ok=True)
                name = re.sub(r"[^\w.-]+", "_", request.node.name)
                context.tracing.stop(path=TRACES / f"{name}-{opened.index(context)}.zip")
            close(**kwargs)

        context.close = close_with_trace
        opened.append(context)
        return context

    monkeypatch.setattr(browser, "new_context", traced)
    yield
    for context in opened:
        context.close()  # (only if the test or page fixture hasn't already)


@pytest.fixture
def page(browser, site):
    """A fresh page (no service worker, so every test sees the latest build) that
    fails the test on any JavaScript error."""
    context = browser.new_context(viewport={"width": 1300, "height": 1000}, service_workers="block")
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    # abcjs comes after the first page (app.js loads it when the browser is idle).
    page.goto_site = lambda path="": (page.goto(site + path),
                                      page.wait_for_function("typeof state !== 'undefined' && state.data && window.ABCJS"))[0]
    yield page
    context.close()
    assert not errors, f"JavaScript errors: {errors}"
