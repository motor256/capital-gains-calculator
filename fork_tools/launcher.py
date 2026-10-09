"""FORK: local launcher for cgt-calc, to run and debug it from an IDE.

Edit `ARG_LIST` to point at your own broker export files and options. It runs
the same entry point as the `cgt-calc` command, so nothing differs from a
command-line run. Run it from the repository root, so the relative paths below
resolve.
"""

from __future__ import annotations

import sys

from cgt_calc.cli import main

ARG_LIST: list[str] = [
    "--year",
    "2025",
    "--schwab-award-file",
    "in/EquityAwardsCenter_2017-2025-12-20.json",
    "--infer-split-units",
    "--dump-transactions",
    "out/broker_transactions.csv",
    # Uncomment to skip PDF generation while iterating:
    # "--no-report",
]

if __name__ == "__main__":
    sys.argv = ["cgt-calc", *ARG_LIST]
    sys.exit(main())
