"""
Shared test harness for Due.

Builds a testable copy of index.html (real Supabase CDN swapped for tests/stub.js),
serves it over http://127.0.0.1:<port>/ so service-worker and fetch behaviour match
production, and hands back a Playwright page with seed data already loaded.

Usage:
    from harness import App, check, summary
    with App(subscriptions=[...]) as app:
        check("thing works", app.eval("someFn()"), expected)
    raise SystemExit(summary())
"""

import http.server
import json
import os
import re
import shutil
import socketserver
import tempfile
import threading
from datetime import date, timedelta

from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TESTS = os.path.join(ROOT, "tests")
CHROMIUM = "/opt/pw-browsers/chromium"

# ---------------------------------------------------------------- assertions
_results = []


def check(label, got, want=None, predicate=None):
    """Record one assertion. Pass either an expected value or a predicate."""
    ok = predicate(got) if predicate else (got == want)
    _results.append((ok, label, got, want))
    print(("  PASS  " if ok else "  FAIL  ") + label)
    if not ok:
        print("          got:  %r" % (got,))
        if predicate is None:
            print("          want: %r" % (want,))
    return ok


def summary():
    failed = [r for r in _results if not r[0]]
    print("\n%d checks, %d failed" % (len(_results), len(failed)))
    if failed:
        print("\nFailures:")
        for _, label, got, want in failed:
            print("  - %s (got %r)" % (label, got))
    return 1 if failed else 0


def section(title):
    print("\n=== %s ===" % title)


# ---------------------------------------------------------------- date utils
def days_from_today(n):
    return (date.today() + timedelta(days=n)).isoformat()


# ---------------------------------------------------------------- seed data
def sub(name, amount, due_offset=3, unit="month", count=1, method="Chase Visa", **extra):
    row = {
        "id": extra.pop("id", "sub-" + re.sub(r"\W+", "-", name.lower())),
        "user_id": "test-user",
        "name": name,
        "amount": amount,
        "currency": "USD",
        "billing_cycle": "monthly",
        "cycle_unit": unit,
        "cycle_count": None if unit == "once" else count,
        "next_due": None if due_offset is None else days_from_today(due_offset),
        "payment_method": method,
        "notes": None,
        "active": True,
        "deleted_at": None,
        "created_at": "2026-01-01T00:00:00Z",
    }
    row.update(extra)
    return row


def acct(name, active=True):
    return {"id": "acct-" + re.sub(r"\W+", "-", name.lower()), "user_id": "test-user",
            "name": name, "active": active, "created_at": "2026-01-01T00:00:00Z"}


DEFAULT_ACCOUNTS = [acct("Amex Gold"), acct("Chase Visa"), acct("Schwab Checking")]


# ---------------------------------------------------------------- http server
class _Handler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()


class _Server:
    def __init__(self, directory):
        handler = lambda *a, **kw: _Handler(*a, directory=directory, **kw)
        self.httpd = socketserver.TCPServer(("127.0.0.1", 0), handler)
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def stop(self):
        self.httpd.shutdown()
        self.httpd.server_close()


# ---------------------------------------------------------------- app fixture
class App:
    """A running instance of the app against stubbed Supabase data."""

    def __init__(self, subscriptions=None, accounts=None, payments=None,
                 delays=None, errors=None, rpc=None, width=390, height=844,
                 signed_in=True, console=False):
        self.seed = {
            "subscriptions": subscriptions if subscriptions is not None else [],
            "accounts": DEFAULT_ACCOUNTS if accounts is None else accounts,
            "payments": payments or [],
        }
        self.delays = delays or {}
        self.errors = errors or {}
        self.rpc = rpc or {}
        self.size = (width, height)
        self.signed_in = signed_in
        self.console = console
        self.errors_seen = []

    # -- build -------------------------------------------------------------
    def _build(self):
        self.tmp = tempfile.mkdtemp(prefix="due-test-")
        html = open(os.path.join(ROOT, "index.html"), encoding="utf-8").read()
        html = re.sub(
            r'<script src="https://cdn\.jsdelivr\.net/npm/@supabase/supabase-js@2"></script>',
            '<script src="stub.js"></script>', html)
        if '<script src="stub.js">' not in html:
            raise SystemExit("harness: could not swap the Supabase CDN tag — did the tag change?")
        # seed hooks must exist before the app script runs
        seed = ("<script>window.__db=%s;window.__delays=%s;window.__errors=%s;window.__session=%s;</script>"
                % (json.dumps(self.seed), json.dumps(self.delays), json.dumps(self.errors),
                   json.dumps({"user": {"id": "test-user"}} if self.signed_in else None)))
        html = html.replace('<script src="stub.js"></script>', '<script src="stub.js"></script>' + seed)
        open(os.path.join(self.tmp, "index.html"), "w", encoding="utf-8").write(html)
        shutil.copy(os.path.join(TESTS, "stub.js"), self.tmp)
        for extra in ("manifest.json", "sw.js"):
            src = os.path.join(ROOT, extra)
            if os.path.exists(src):
                shutil.copy(src, self.tmp)

    # -- lifecycle ---------------------------------------------------------
    def __enter__(self):
        self._build()
        self.server = _Server(self.tmp)
        self.pw = sync_playwright().start()
        self.browser = self.pw.chromium.launch(executable_path=CHROMIUM)
        self.ctx = self.browser.new_context(viewport={"width": self.size[0], "height": self.size[1]})
        self.page = self.ctx.new_page()
        self.page.on("pageerror", lambda e: self.errors_seen.append(str(e)))
        if self.console:
            self.page.on("console", lambda m: print("    [console:%s] %s" % (m.type, m.text)))
        self.page.goto("http://127.0.0.1:%d/index.html" % self.server.port)
        for name, body in self.rpc.items():
            self.page.evaluate("([n,src]) => { window.__rpc[n] = eval(src); }", [name, body])
        if self.signed_in:
            self.page.wait_for_selector("#appView", state="visible", timeout=8000)
            self.settle()
        return self

    def __exit__(self, *a):
        try:
            self.ctx.close(); self.browser.close(); self.pw.stop()
        finally:
            self.server.stop()
            shutil.rmtree(self.tmp, ignore_errors=True)

    # -- interaction -------------------------------------------------------
    def eval(self, js):
        return self.page.evaluate("() => (%s)" % js)

    def run(self, js):
        return self.page.evaluate("() => { %s }" % js)

    def settle(self, ms=250):
        self.page.wait_for_timeout(ms)

    def text(self, sel):
        el = self.page.query_selector(sel)
        return el.inner_text().strip() if el else None

    def names(self):
        return [t.strip() for t in self.page.eval_on_selector_all("#list .item .name", "els => els.map(e => e.textContent)")]

    def calls(self, table=None, op=None):
        out = self.eval("window.__calls")
        if table:
            out = [c for c in out if c.get("table") == table]
        if op:
            out = [c for c in out if c.get("op") == op]
        return out

    def db(self, table):
        return self.eval("window.__db.%s" % table)

    def shot(self, path):
        self.page.screenshot(path=path, full_page=True)
