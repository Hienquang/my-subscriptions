# Due — tests

Headless tests for `index.html`. No build step, no npm, no test framework: just
Python + Playwright driving Chromium against a stubbed Supabase.

## Running

```bash
python3 tests/run_tests.py            # everything
python3 tests/test_logic.py           # just the billing-cycle / formatting maths
python3 tests/test_ui.py              # just rendering and interaction
python3 tests/shot.py [outdir]        # screenshots for eyeballing visual changes
```

Requires `playwright` (Python) and a Chromium binary. `harness.py` points at
`/opt/pw-browsers/chromium`; change `CHROMIUM` there if yours lives elsewhere.

## How it works

`harness.py` copies `index.html` into a temp dir, swaps the Supabase CDN
`<script>` tag for `tests/stub.js`, injects seed data, and serves the result over
a local HTTP server (not `file://`, so `fetch` and service workers behave like
production). Tests then drive the real app functions — `addCycle`, `renderList`,
`confirmPay` — through `page.evaluate`.

Nothing here touches the live Supabase project.

## The stub

`stub.js` replaces `window.supabase` with an in-memory fake supporting the query
builder the app actually uses (`select/insert/update/delete/eq/order/limit/single`
plus `rpc`). Test hooks, all on `window`:

| Hook | Purpose |
| --- | --- |
| `__db` | seed rows, and the source of truth to assert against afterwards |
| `__delays` | per-table response delay in ms — how the v5.4 dropdown race is reproduced |
| `__errors` | per-table injected error, to test failure paths |
| `__calls` | log of every query issued, for "did it write once?" assertions |
| `__rpc` | handlers for `sb.rpc(name, args)` |
| `__session` | set falsy to test the signed-out view |

## Writing a test

```python
from harness import App, check, section, summary, sub

with App(subscriptions=[sub("Netflix", 15.99, due_offset=2)]) as app:
    section("mark paid")
    app.run("setTab('all'); openPay('sub-netflix'); confirmPay()")
    app.settle(400)
    check("payment written", len(app.db("payments")), 1)

raise SystemExit(summary())
```

`sub(...)` and `acct(...)` build seed rows with sane defaults; `due_offset` is in
days from today, so tests don't rot as the calendar moves.

Gotcha: the default tab is period-scoped ("this week"), so a subscription due next
month won't be in `app.names()` until you `setTab('all')`.

## What's covered

- **Billing maths** — month-end clamping (the v5.6 drift fix), leap years, week
  and multi-month cycles, legacy `billing_cycle` values, `monthlyEquiv`, labels,
  money formatting, HTML escaping.
- **Rendering** — sort order, overdue/paused states, hero total, tabs, account
  chips, search scoping.
- **Flows** — mark paid (incl. one-time bills and overdue catch-up), soft delete,
  undo, restore, purge, offline round trip.
- **Wiring** — the delegated `data-act` handlers, driven by real clicks rather than
  by calling functions directly, so a broken listener actually fails the suite.
- **Regressions** — v5.4 empty account dropdown (delayed accounts response), the
  failed-accounts-query wipe, and the v5.8 concurrent-load clobber.

Add a regression test whenever a bug is fixed; that is the point of this folder.
