#!/usr/bin/env python3
"""Run every Due test suite. Exit code 0 = all green.

    python3 tests/run_tests.py
"""

import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SUITES = ["test_logic.py", "test_ui.py"]

if __name__ == "__main__":
    only = sys.argv[1:] or SUITES
    failures = []
    for suite in only:
        print("\n" + "=" * 62)
        print("RUN  " + suite)
        print("=" * 62)
        if subprocess.call([sys.executable, os.path.join(HERE, suite)], cwd=HERE) != 0:
            failures.append(suite)
    print("\n" + "=" * 62)
    if failures:
        print("FAILED: " + ", ".join(failures))
    else:
        print("All suites passed.")
    sys.exit(1 if failures else 0)
