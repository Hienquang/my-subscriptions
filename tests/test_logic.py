"""Pure-function tests: billing cycle maths, money, dates. No DOM interaction."""

from harness import App, check, section, summary


def chain(app, start, it, steps):
    """Advance `start` through `steps` billing cycles and return every date."""
    return app.page.evaluate(
        """([start, it, steps]) => {
             const out = []; let d = start;
             for (let i = 0; i < steps; i++) { d = addCycle(d, it); out.push(d); }
             return out;
           }""", [start, it, steps])


def run():
    monthly = {"cycle_unit": "month", "cycle_count": 1}
    with App() as app:
        section("addCycle — month-end clamping (the Jan-31 drift bug)")

        it31 = dict(monthly, due_day=31)
        check("Jan 31 + 1mo clamps to Feb 28 (2026 is not a leap year)",
              app.page.evaluate("it => addCycle('2026-01-31', it)", it31), "2026-02-28")
        check("a 31st bill re-anchors to Mar 31 after February",
              chain(app, "2026-01-31", it31, 5),
              ["2026-02-28", "2026-03-31", "2026-04-30", "2026-05-31", "2026-06-30"])
        check("leap year: Jan 31 + 1mo -> Feb 29",
              app.page.evaluate("it => addCycle('2028-01-31', it)", it31), "2028-02-29")

        it30 = dict(monthly, due_day=30)
        check("a 30th bill survives February and returns to the 30th",
              chain(app, "2026-01-30", it30, 3), ["2026-02-28", "2026-03-30", "2026-04-30"])

        check("year rolls over correctly",
              app.page.evaluate("it => addCycle('2026-12-15', it)", dict(monthly, due_day=15)), "2027-01-15")
        check("mid-month dates are untouched",
              chain(app, "2026-01-15", dict(monthly, due_day=15), 3),
              ["2026-02-15", "2026-03-15", "2026-04-15"])
        check("no due_day falls back to the date's own day",
              app.page.evaluate("it => addCycle('2026-03-15', it)", monthly), "2026-04-15")
        check("multi-month cycles clamp too (quarterly from Nov 30)",
              app.page.evaluate("it => addCycle('2026-11-30', it)", {"cycle_unit": "month", "cycle_count": 3, "due_day": 30}),
              "2027-02-28")
        check("yearly keeps the anchor",
              app.page.evaluate("it => addCycle('2026-02-29'.replace('2026','2028'), it)",
                                {"cycle_unit": "month", "cycle_count": 12, "due_day": 29}),
              "2029-02-28")

        section("addCycle — weeks and one-time bills")
        check("weekly", app.page.evaluate("it => addCycle('2026-07-25', it)", {"cycle_unit": "week", "cycle_count": 1}), "2026-08-01")
        check("every 2 weeks", app.page.evaluate("it => addCycle('2026-07-25', it)", {"cycle_unit": "week", "cycle_count": 2}), "2026-08-08")
        check("every 4 weeks crosses a month boundary",
              app.page.evaluate("it => addCycle('2026-07-25', it)", {"cycle_unit": "week", "cycle_count": 4}), "2026-08-22")
        check("one-time bills have no next date",
              app.page.evaluate("it => addCycle('2026-07-25', it)", {"cycle_unit": "once"}), None)

        section("legacy billing_cycle values still resolve")
        for legacy, want in [("weekly", "2026-08-01"), ("biweekly", "2026-08-08"),
                             ("fourweekly", "2026-08-22"), ("monthly", "2026-08-25"),
                             ("quarterly", "2026-10-25"), ("yearly", "2027-07-25")]:
            check("legacy %s" % legacy,
                  app.page.evaluate("c => addCycle('2026-07-25', { billing_cycle: c })", legacy), want)

        section("monthlyEquiv")
        eq = lambda it: app.page.evaluate("it => Math.round(monthlyEquiv(it) * 100) / 100", it)
        check("monthly passes through", eq({"amount": 15.99, "active": True, "cycle_unit": "month", "cycle_count": 1}), 15.99)
        check("quarterly divides by 3", eq({"amount": 30, "active": True, "cycle_unit": "month", "cycle_count": 3}), 10)
        check("yearly divides by 12", eq({"amount": 120, "active": True, "cycle_unit": "month", "cycle_count": 12}), 10)
        check("weekly uses 52/12", eq({"amount": 10, "active": True, "cycle_unit": "week", "cycle_count": 1}), 43.33)
        check("every 2 weeks halves that", eq({"amount": 10, "active": True, "cycle_unit": "week", "cycle_count": 2}), 21.67)
        check("one-time bills are excluded", eq({"amount": 500, "active": True, "cycle_unit": "once"}), 0)
        check("paused subs are excluded", eq({"amount": 15.99, "active": False, "cycle_unit": "month", "cycle_count": 1}), 0)
        check("missing amount is safe", eq({"amount": None, "active": True, "cycle_unit": "month", "cycle_count": 1}), 0)

        section("cycleLabel")
        lbl = lambda it: app.page.evaluate("it => cycleLabel(it)", it)
        check("weekly", lbl({"cycle_unit": "week", "cycle_count": 1}), "weekly")
        check("every 2 wks", lbl({"cycle_unit": "week", "cycle_count": 2}), "every 2 wks")
        check("monthly", lbl({"cycle_unit": "month", "cycle_count": 1}), "monthly")
        check("quarterly", lbl({"cycle_unit": "month", "cycle_count": 3}), "quarterly")
        check("yearly", lbl({"cycle_unit": "month", "cycle_count": 12}), "yearly")
        check("every 2 mo", lbl({"cycle_unit": "month", "cycle_count": 2}), "every 2 mo")
        check("one-time", lbl({"cycle_unit": "once"}), "one-time")

        section("money formatting")
        check("thousands separator + decimal span",
              app.eval("money(1234.5)"), '$1,234<span class="dec">.50</span>')
        check("plain text money", app.eval("moneyText(9.9)"), "$9.90")

        section("escaping")
        check("HTML in names is escaped",
              app.eval("esc('<img src=x onerror=alert(1)>')"),
              "&lt;img src=x onerror=alert(1)&gt;")
        check("quotes are escaped", app.eval("""esc('a"b\\'c&d')"""), "a&quot;b&#39;c&amp;d")

    return summary()


if __name__ == "__main__":
    raise SystemExit(run())
