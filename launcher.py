"""Local launcher script for cgt-calc.

This is a convenience entrypoint so you can run and debug the calculator
directly from your IDE without typing long command lines.

Edit the `ARG_LIST` below to point at your own broker export files and options.
"""

from __future__ import annotations

from cgt_calc.args_parser import create_parser
from cgt_calc.main import calculate_cgt

# Adjust this list to your own data/files.
# You can comment/uncomment lines as needed while iterating in the IDE.
ARG_LIST: list[str] = [
    "--year",
    "2025",
    "--schwab-equity-award-json",
    "in/EquityAwardsCenter_2017-2025-12-20.json",
    "--save-broker-transactions",
    # Example Schwab CSV (replace with your own):
    # "--schwab-file",
    # r"C:\path\to\schwab_transactions.csv",
    #
    # Example Trading 212 directory:
    # "--trading212-dir",
    # r"C:\path\to\trading212_data",
    #
    # Example RAW format file:
    # "--raw-file",
    # r"C:\path\to\raw_data.csv",
    #
    # Uncomment if you want to skip PDF generation while iterating:
    # "--no-report",
]


def main() -> None:
    """Parse hard-coded arguments and run the calculator."""
    parser = create_parser()
    args = parser.parse_args(ARG_LIST)
    calculate_cgt(args)


if __name__ == "__main__":
    main()
