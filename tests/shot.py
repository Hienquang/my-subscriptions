#!/usr/bin/env python3
"""Screenshot the app against sample data, for eyeballing visual changes.

    python3 tests/shot.py [outdir]

Writes phone (390px) and desktop (900px) shots of the main list, plus the add
form and the mark-paid sheet. Uses the same stubbed Supabase as the tests, so it
never touches live data.
"""

import os
import sys

from harness import App, sub, acct

OUT = sys.argv[1] if len(sys.argv) > 1 else "/tmp/due-shots"

SAMPLE = [
    sub("Mortgage", 2840.00, due_offset=-2, method="Schwab Checking"),
    sub("Netflix", 15.99, due_offset=0, method="Chase Visa"),
    sub("Spectrum — Internet", 89.99, due_offset=3, method="Chase Visa"),
    sub("iCloud Plus", 2.99, due_offset=5, method="Amex Gold"),
    sub("Car insurance", 142.50, due_offset=11, method="Schwab Checking"),
    sub("Cookidoo", 60.00, due_offset=66, unit="month", count=12, method="Amex Gold"),
    sub("Gym", 40.00, due_offset=18, method="Chase Visa", notes="cancel before renewal"),
    sub("Old Magazine", 9.00, due_offset=25, method="Amex Gold", active=False),
]

if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    for label, w, h in [("phone", 390, 844), ("desktop", 900, 1000)]:
        with App(subscriptions=SAMPLE, width=w, height=h) as app:
            app.run("setTab('all')")
            app.settle(150)
            app.shot(os.path.join(OUT, "%s-list.png" % label))

            app.run("openForm('sub-netflix')")
            app.settle(150)
            app.shot(os.path.join(OUT, "%s-form.png" % label))
            app.run("closeForm(); openPay('sub-netflix')")
            app.settle(150)
            app.shot(os.path.join(OUT, "%s-pay.png" % label))
            app.run("closePay(); openAccts()")
            app.settle(150)
            app.shot(os.path.join(OUT, "%s-accounts.png" % label))
    print("wrote shots to " + OUT)
