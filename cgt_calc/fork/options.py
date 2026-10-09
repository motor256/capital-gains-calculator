"""FORK: command-line options for the fork's extensions.

Upstream's `create_parser` and `calculate_cgt` each call one function here, so
the options, their defaults and what they switch on are all defined in this
file.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

import shtab

from cgt_calc.args_validators import set_completer
from cgt_calc.const import DEFAULT_OUTPUT_FOLDER

from . import split_units
from .market_prices import MarketPrices

if TYPE_CHECKING:
    import argparse

LOGGER = logging.getLogger(__name__)

DEFAULT_MARKET_PRICES_FILE = DEFAULT_OUTPUT_FOLDER / "historical_prices.csv"


def add_arguments(parser: argparse.ArgumentParser) -> None:
    """Add the fork's options to `parser`, in a group of their own."""
    group = parser.add_argument_group(
        "Fork extensions", description="Not in upstream cgt-calc."
    )
    group.add_argument(
        "--infer-split-units",
        action="store_true",
        help="work out whether each Schwab Equity Awards row is in pre- or "
        "post-split share units by comparing its price with the market price "
        "that day, instead of assuming the export restated acquisitions only "
        "(needs network access the first time, and only for symbols with a "
        "known stock split)",
    )
    set_completer(
        group.add_argument(
            "--market-prices-cache",
            type=Path,
            metavar="PATH",
            default=DEFAULT_MARKET_PRICES_FILE,
            help="where --infer-split-units keeps the market prices it fetched, "
            "in CSV format (default: %(default)s)",
        ),
        shtab.FILE,
    )


def apply_arguments(args: argparse.Namespace) -> None:
    """Switch on whichever extensions `args` asks for."""
    if not getattr(args, "infer_split_units", False):
        split_units.configure(None)
        return
    cache_file = getattr(args, "market_prices_cache", DEFAULT_MARKET_PRICES_FILE)
    LOGGER.info(
        "Inferring Schwab Equity Awards share units from market prices "
        "(--infer-split-units), cached in %s",
        cache_file,
    )
    split_units.configure(MarketPrices(cache_file))
