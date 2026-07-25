"""DOM and interaction tests: rendering, filters, mark-paid, delete/undo, offline.

Includes regression tests for the bugs fixed in v5.4 (empty account dropdown) and
v5.6 (month-end drift), so they cannot come back silently.
"""

from harness import App, check, section, summary, sub, acct, days_from_today, DEFAULT_ACCOUNTS


def basic_set():
    return [
        sub("Netflix", 15.99, due_offset=2, method="Chase Visa"),
        sub("iCloud", 2.99, due_offset=-3, method="Amex Gold"),
        sub("Gym", 40, due_offset=20, method="Chase Visa"),
        sub("Old Magazine", 9, due_offset=5, method="Amex Gold", active=False),
    ]


def run():
    # ---------------------------------------------------------------- render
    with App(subscriptions=basic_set()) as app:
        section("list rendering")
        app.run("setTab('all')")   # default tab is period-scoped; check the full list here
        check("no uncaught page errors", app.errors_seen, [])
        check("overdue first, then by due date, paused last",
              app.names(), ["iCloud", "Netflix", "Gym", "Old Magazine"])
        check("overdue row is flagged", app.text("#list .item:first-child .due"), "overdue 3d")
        check("paused row says so", app.text("#list .item:last-child .due"), "paused")
        check("paused row is dimmed",
              app.eval("document.querySelectorAll('#list .item')[3].classList.contains('inactive')"), True)
        check("meta line shows account and cycle",
              app.text("#list .item:first-child .meta"), "Amex Gold · monthly")

        section("hero total")
        # 15.99 + 2.99 + 40 = 58.98 (paused Old Magazine excluded)
        check("monthly total excludes paused subs", app.text("#totMonthly").split("\n")[0], "$58.98/ MONTH")
        check("due line counts overdue and upcoming (paused subs excluded)",
              app.text("#dueLine"), "1 overdue · 1 due in the next 7 days")

        section("tabs and account filter")
        app.run("setView('month'); setTab('this')")
        check("this month shows everything due before the 1st + overdue",
              sorted(app.names()), ["Netflix", "iCloud"])
        app.run("setTab('all')")
        check("All tab shows every subscription", len(app.names()), 4)
        app.run("setFilter('acct-chase-visa')")
        check("account chip filters the list", app.names(), ["Netflix", "Gym"])
        check("chips are built from the accounts table",
              app.page.eval_on_selector_all(".chip", "els => els.map(e => e.textContent)"),
              ["All accounts", "Amex Gold", "Chase Visa"])
        app.run("setFilter('all')")

        section("search")
        check("search box is visible on All", app.eval("getComputedStyle($('searchWrap')).display != 'none'"), True)
        app.run("setQuery('gym')")
        check("search matches by name", app.names(), ["Gym"])
        app.run("setQuery('amex')")
        check("search matches by account", sorted(app.names()), ["Old Magazine", "iCloud"])
        app.run("setFilter('acct-chase-visa')")
        check("an active search ignores the account chips", sorted(app.names()), ["Old Magazine", "iCloud"])
        app.run("setFilter('all'); setQuery('nothingmatches')")
        check("empty state for a bad search", "No matches" in app.text("#list .empty"), True)
        app.run("clearQuery()")
        check("clearing restores the list", len(app.names()), 4)
        app.run("setTab('this')")
        check("search box hides off the All tab", app.eval("getComputedStyle($('searchWrap')).display"), "none")

    # ------------------------------------------------------------- mark paid
    with App(subscriptions=[sub("Netflix", 15.99, due_offset=2, method="Chase Visa", due_day=15)]) as app:
        section("mark paid")
        app.run("setTab('all')")
        app.run("openPay('sub-netflix')")
        check("pay sheet prefills the planned amount", app.eval("$('p_amount').value"), "15.99")
        check("pay sheet prefills the due date", app.eval("$('p_date').value"), days_from_today(2))
        app.run("$('p_amount').value = '17.49'; confirmPay()")
        app.settle(400)
        payments = app.db("payments")
        check("one payment row written", len(payments), 1)
        check("payment records the actual amount", payments[0]["amount"], 17.49)
        check("due date advanced one month",
              app.db("subscriptions")[0]["next_due"] != days_from_today(2), True)
        check("ember glow applied to the paid row",
              app.eval("!!document.querySelector('#list .item.ember')"), True)
        app.run("render()")
        check("ember glow is one-shot", app.eval("!!document.querySelector('#list .item.ember')"), False)

    with App(subscriptions=[sub("Car registration", 220, due_offset=1, unit="once")]) as app:
        section("one-time bills")
        app.run("openPay('sub-car-registration'); confirmPay()")
        app.settle(400)
        check("a one-time bill deactivates after payment", app.db("subscriptions")[0]["active"], False)

    with App(subscriptions=[sub("Gas bill", 60, due_offset=-70, due_day=28)]) as app:
        section("overdue catch-up")
        app.run("openPay('sub-gas-bill'); confirmPay()")
        app.settle(400)
        nxt = app.db("subscriptions")[0]["next_due"]
        check("catch-up advances the due date into the future", nxt > days_from_today(0), True)
        check("catch-up keeps the anchor day", nxt.endswith("-28"), True)

    # ------------------------------------ v5.4 regression: account dropdown race
    with App(subscriptions=basic_set(), delays={"accounts": 1500}) as app:
        section("regression v5.4 — accounts arriving after the form opens")
        app.run("openForm()")
        early = app.eval("$('f_method').options.length")
        check("dropdown starts nearly empty while accounts load", early <= 2, True)
        app.settle(1800)
        check("dropdown fills itself once accounts arrive",
              app.eval("$('f_method').options.length"), len(DEFAULT_ACCOUNTS) + 2)
        app.run("$('f_method').value = 'acct-amex-gold'")
        app.run("load()")
        app.settle(1800)
        check("a refresh mid-edit preserves the chosen account", app.eval("$('f_method').value"), "acct-amex-gold")

    with App(subscriptions=basic_set(), errors={"accounts": {"message": "boom"}}) as app:
        section("regression v5.4 — a failed accounts query must not wipe the list")
        app.run("setTab('all')")
        app.run("window.__db.accounts = [{id:'a1',name:'Recovered',active:true}]; delete window.__errors.accounts; load()")
        app.settle(400)
        check("subscriptions still render despite the earlier account error", len(app.names()), 4)
        check("accounts recover on the next successful load",
              app.eval("accounts.map(a => a.name)"), ["Recovered"])
        check("no accounts are auto-inserted on load",
              [c for c in app.calls("accounts", "insert")], [])

    # ------------------------------------------------- v5.7 account_id linkage
    with App(subscriptions=basic_set()) as app:
        section("accounts are referenced by id (v5.7)")
        app.run("setTab('all')")
        app.page.on("dialog", lambda d: d.accept())
        app.run("openForm('sub-netflix')")
        check("the form preselects the linked account by id",
              app.eval("$('f_method').value"), "acct-chase-visa")
        app.run("closeForm()")

        before = len(app.calls("subscriptions", "update"))
        app.run("window.prompt = () => 'Chase Sapphire'; renameAcct('acct-chase-visa')")
        app.settle(500)
        check("renaming writes to accounts only, never to subscriptions",
              len(app.calls("subscriptions", "update")), before)
        check("the new name shows on the subscription row",
              "Chase Sapphire" in app.text("#list .item:nth-child(2) .meta"), True)
        check("the chip picks up the new name too",
              "Chase Sapphire" in app.text("#chips"), True)
        check("the subscription row itself was untouched",
              app.db("subscriptions")[0]["account_id"], "acct-chase-visa")

        app.run("setFilter('acct-chase-visa')")
        check("filtering survives a rename (it keys on the id)", app.names(), ["Netflix", "Gym"])
        app.run("setFilter('all')")

    with App(subscriptions=[sub("Legacy row", 5, method=None, payment_method="Old Bank", account_id=None)]) as app:
        section("pre-v5.7 rows without account_id")
        app.run("setTab('all')")
        check("an unlinked row falls back to its old text label",
              app.text("#list .item .meta").startswith("Old Bank"), True)

    # ------------------------------------------- v5.8 atomicity and load races
    with App(subscriptions=[sub("Netflix", 15.99, due_offset=2, due_day=15)]) as app:
        section("mark paid is a single atomic call (v5.8)")
        app.run("setTab('all'); openPay('sub-netflix'); confirmPay()")
        app.settle(400)
        check("payment goes through record_payment(), not a bare insert",
              [c.get("rpc") for c in app.calls() if c.get("rpc")], ["record_payment"])
        check("no direct write to the payments table", app.calls("payments"), [])
        check("no separate subscriptions update", app.calls("subscriptions", "update"), [])
        check("the payment landed", len(app.db("payments")), 1)
        check("the due date advanced", app.db("subscriptions")[0]["next_due"].endswith("-15"), True)

    with App(subscriptions=[sub("Netflix", 15.99, due_offset=2)],
             errors={"record_payment": {"message": "deadlock detected"}}) as app:
        section("a failed payment leaves nothing behind")
        app.run("setTab('all'); openPay('sub-netflix'); confirmPay()")
        app.settle(400)
        check("the error is shown in the sheet", "deadlock detected" in app.text("#p_err"), True)
        check("the pay sheet stays open so it can be retried",
              app.eval("$('paySheet').classList.contains('open')"), True)
        check("nothing was written", len(app.db("payments")), 0)
        check("the due date is untouched", app.db("subscriptions")[0]["next_due"], days_from_today(2))

    old_payments = [{"id": "p-old", "subscription_id": "sub-annual-thing", "amount": 99,
                     "paid_on": days_from_today(-400), "created_at": "2025-06-01T00:00:00Z"}]
    old_payments += [{"id": "p-%d" % i, "subscription_id": "sub-netflix", "amount": 15.99,
                      "paid_on": days_from_today(-i), "created_at": "2026-01-01T00:00:00Z"}
                     for i in range(1, 30)]
    with App(subscriptions=[sub("Annual thing", 99, unit="month", count=12), sub("Netflix", 15.99)],
             payments=old_payments) as app:
        section("last payment survives a long payment history (v5.8)")
        app.run("setTab('all'); openForm('sub-annual-thing')")
        check("an old payment is still found via the last_payments view",
              "Last paid: $99.00" in app.text("#f_lastpaid"), True)
        check("the query asks for no row limit",
              [c for c in app.calls("last_payments") if c.get("limitN")], [])

    with App(subscriptions=basic_set()) as app:
        section("concurrent loads can't clobber each other (v5.8)")
        app.run("setTab('all')")
        app.run("window.__delays.subscriptions = 900; load()")
        app.settle(50)
        app.run("window.__delays.subscriptions = 0;"
                "window.__db.subscriptions.push(Object.assign({}, window.__db.subscriptions[0],"
                "  {id: 'sub-new', name: 'Just Added'}));"
                "load()")
        app.settle(250)
        check("the newer load lands first", "Just Added" in app.names(), True)
        app.settle(1200)
        check("the older, slower response is discarded", "Just Added" in app.names(), True)
        check("the list is not rewound to the stale snapshot", len(app.names()), 5)

    with App(subscriptions=basic_set(), errors={"subscriptions": {"message": "permission denied for table"}}) as app:
        section("a query error is not reported as being offline (v5.8)")
        app.run("load()")
        app.settle(300)
        check("the real reason is shown", "permission denied" in app.text("#offbar"), True)
        check("it is styled as an error, not as the offline banner",
              app.eval("$('offbar').classList.contains('err')"), True)
        check("buttons are not disabled as if offline",
              app.eval("document.body.classList.contains('off')"), False)

    with App(subscriptions=basic_set()) as app:
        section("an expired session sends you back to sign-in (v5.8)")
        app.run("window.__errors.subscriptions = { message: 'JWT expired' }; load()")
        app.settle(500)
        check("the message says so", "session expired" in app.text("#offbar"), True)
        check("the app signs out", app.eval("getComputedStyle($('authView')).display != 'none'"), True)

    # ------------------------------------------------- soft delete, undo, trash
    with App(subscriptions=basic_set()) as app:
        section("soft delete, undo and Recently deleted")
        app.run("setTab('all')")
        app.page.on("dialog", lambda d: d.accept())
        app.run("openForm('sub-gym'); delItem()")
        app.settle(400)
        check("deleted row leaves the list", "Gym" in app.names(), False)
        check("row is soft-deleted, not erased", len(app.db("subscriptions")), 4)
        check("undo toast is showing", app.eval("$('undoBar').classList.contains('show')"), True)
        app.run("undoDelete()")
        app.settle(400)
        check("undo restores the row", "Gym" in app.names(), True)

        app.run("openForm('sub-gym'); delItem()")
        app.settle(400)
        app.run("hideUndo(); openTrash()")
        check("trash lists the deleted subscription", "Gym" in app.text("#trashList"), True)
        app.run("restoreItem('sub-gym')")
        app.settle(400)
        check("restore from trash works", "Gym" in app.names(), True)

        app.run("openForm('sub-gym'); delItem()")
        app.settle(400)
        app.run("hideUndo(); purgeItem('sub-gym')")
        app.settle(400)
        check("delete forever really removes the row", len(app.db("subscriptions")), 3)

    # ---------------------------------------------------------------- offline
    with App(subscriptions=basic_set()) as app:
        section("offline mode")
        app.run("setTab('all')")
        app.ctx.set_offline(True)
        app.run("window.dispatchEvent(new Event('offline'))")
        check("offline banner appears", app.eval("getComputedStyle($('offbar')).display != 'none'"), True)
        check("body gets the offline class", app.eval("document.body.classList.contains('off')"), True)
        check("adding is blocked while offline",
              app.eval("(openForm(), $('formSheet').classList.contains('open'))"), False)
        app.ctx.set_offline(False)
        app.run("window.dispatchEvent(new Event('online'))")
        app.settle(400)
        check("coming back online clears the banner", app.eval("document.body.classList.contains('off')"), False)
        check("list still intact after the round trip", len(app.names()), 4)

    return summary()


if __name__ == "__main__":
    raise SystemExit(run())
