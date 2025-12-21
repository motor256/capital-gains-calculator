"""Fetch historical stock prices for transaction normalization (e.g., stock splits)."""

from __future__ import annotations

import csv
import datetime
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING, Final

import pandas as pd
import yfinance as yf  # type: ignore[import-untyped]

from .const import CGT_TEST_MODE
from .exceptions import ParsingError
from .util import open_with_parents

if TYPE_CHECKING:
    from pathlib import Path

HISTORICAL_PRICES_HEADER: Final = ["symbol", "date", "close_price"]

# Known symbols that need broad historical ranges
BROAD_RANGE_SYMBOLS: Final[dict[str, tuple[str, str]]] = {
    "NVDA": ("2017-01-01", "2025-12-31"),  # Covers all historical NVDA splits
    # Add more as needed:
    # 'TSLA': ('2020-01-01', '2025-12-31'),
}

# Default date range for unknown symbols when fetching historical prices
DEFAULT_LOOKBACK_DAYS: Final = 365  # Look back 1 year
DEFAULT_LOOKAHEAD_DAYS: Final = 30  # Look ahead 30 days

# Maximum allowed deviation between target date and closest available market date
MAX_DATE_TOLERANCE_DAYS: Final = 5  # Must be within 5 days


class HistoricalPriceFetcher:
    """Fetch and cache historical stock prices."""

    def __init__(self, historical_prices_file: Path | None = None):
        """Load cached prices from file."""
        self.historical_prices_file = historical_prices_file
        # Cache structure: {symbol: {date: price}}
        self.cache: dict[str, dict[date, Decimal]] = {}
        self._read_historical_prices_file()

    def _read_historical_prices_file(self) -> None:
        """Read historical prices from CSV file into cache."""
        if (
            self.historical_prices_file is None
            or not self.historical_prices_file.is_file()
        ):
            return

        with self.historical_prices_file.open(encoding="utf8") as fin:
            csv_reader = csv.DictReader(fin)
            if csv_reader.fieldnames is None:
                # File is empty.
                return

            for row_number, line in enumerate(csv_reader, start=2):
                # Guard against schema drift before touching row contents.
                if sorted(HISTORICAL_PRICES_HEADER) != sorted(line.keys()):
                    raise ParsingError(
                        self.historical_prices_file,
                        "Unexpected columns in historical prices file: "
                        f"found {sorted(line.keys())}, "
                        f"expected {HISTORICAL_PRICES_HEADER}",
                    )

                # Trim values so that whitespace-only cells count as empty.
                normalized_values = {
                    field: (line[field].strip() if line[field] is not None else "")
                    for field in HISTORICAL_PRICES_HEADER
                }

                # Skip harmless blank lines left by editors or tooling.
                if not any(normalized_values.values()):
                    continue

                # Missing values mean we cannot trust the entry.
                missing_fields = [
                    field for field, value in normalized_values.items() if not value
                ]
                if missing_fields:
                    raise ParsingError(
                        self.historical_prices_file,
                        "Missing data in historical prices file at line "
                        f"{row_number}: {', '.join(sorted(missing_fields))}",
                    )

                symbol = normalized_values["symbol"]
                date_str = normalized_values["date"]
                price_str = normalized_values["close_price"]

                try:
                    price_date = datetime.date.fromisoformat(date_str)
                except ValueError as err:
                    raise ParsingError(
                        self.historical_prices_file,
                        f"Invalid date '{date_str}' at line {row_number}",
                    ) from err

                try:
                    price = Decimal(price_str)
                except (InvalidOperation, ValueError) as err:
                    raise ParsingError(
                        self.historical_prices_file,
                        f"Invalid price '{price_str}' at line {row_number}",
                    ) from err

                if symbol not in self.cache:
                    self.cache[symbol] = {}
                self.cache[symbol][price_date] = price

    def _write_historical_prices_file(self) -> None:
        """Write cache to CSV file."""
        if self.historical_prices_file is None or CGT_TEST_MODE:
            return

        with open_with_parents(self.historical_prices_file) as fout:
            data_rows = [
                [symbol, price_date.isoformat(), str(price)]
                for symbol, dates in sorted(self.cache.items())
                for price_date, price in sorted(dates.items())
            ]
            writer = csv.writer(fout)
            writer.writerows([HISTORICAL_PRICES_HEADER, *data_rows])

    def get_closest_price(self, symbol: str, target_date: str | date) -> Decimal:
        """Get closing price closest to target date, with automatic caching.

        First call for a symbol fetches and caches historical data.
        Subsequent calls use cached data for instant lookups.

        Args:
            symbol: Stock ticker symbol (e.g., 'NVDA')
            target_date: Target date as string 'YYYY-MM-DD' or date object

        Returns:
            Closing price as Decimal

        """
        if isinstance(target_date, str):
            target_date_obj = datetime.datetime.strptime(target_date, "%Y-%m-%d").date()
        else:
            target_date_obj = target_date

        # Check if we have cached data for this symbol
        if symbol in self.cache:
            # Try to find a price within tolerance
            price = self._find_closest_cached_price(symbol, target_date_obj)
            if price is not None:
                return price

        # Need to fetch from API
        self._fetch_and_cache_prices(symbol, target_date_obj)

        # Now try again from cache
        price = self._find_closest_cached_price(symbol, target_date_obj)
        if price is None:
            msg = f"Could not find price for {symbol} on {target_date_obj}"
            raise RuntimeError(msg)
        return price

    def _find_closest_cached_price(
        self, symbol: str, target_date: date
    ) -> Decimal | None:
        """Find closest price in cache within tolerance."""
        if symbol not in self.cache or not self.cache[symbol]:
            return None

        cached_dates = sorted(self.cache[symbol].keys())

        # Find the closest date
        closest_date = min(cached_dates, key=lambda d: abs((d - target_date).days))
        days_diff = abs((closest_date - target_date).days)

        if days_diff <= MAX_DATE_TOLERANCE_DAYS:
            return self.cache[symbol][closest_date]

        return None

    def _fetch_and_cache_prices(self, symbol: str, target_date: date) -> None:
        """Fetch prices from yfinance and add to cache."""
        if symbol in BROAD_RANGE_SYMBOLS:
            start_str, end_str = BROAD_RANGE_SYMBOLS[symbol]
            print(f"Fetching {symbol} historical prices ({start_str} to {end_str})...")
        else:
            # Dynamic range for unknown symbols
            start = target_date - timedelta(days=DEFAULT_LOOKBACK_DAYS)
            end = target_date + timedelta(days=DEFAULT_LOOKAHEAD_DAYS)
            start_str = start.strftime("%Y-%m-%d")
            end_str = end.strftime("%Y-%m-%d")
            print(f"Fetching {symbol} historical prices ({start_str} to {end_str})...")

        stock_data = yf.download(
            symbol,
            start=start_str,
            end=end_str,
            auto_adjust=True,
        )

        if stock_data.empty:
            msg = f"No data found for ticker '{symbol}' from {start_str} to {end_str}."
            raise RuntimeError(msg)

        # Add all fetched prices to cache
        if symbol not in self.cache:
            self.cache[symbol] = {}

        for idx in stock_data.index:
            price_date = idx.date()
            close_value = stock_data.loc[idx, "Close"]
            # Handle both single-ticker and multi-ticker DataFrame formats
            if hasattr(close_value, "iloc"):
                close_value = close_value.iloc[0]
            if close_value is not None and not pd.isna(close_value):
                self.cache[symbol][price_date] = Decimal(str(float(close_value)))

        # Persist to file
        self._write_historical_prices_file()

    def clear_cache(self) -> None:
        """Clear the price cache (useful for testing)."""
        self.cache.clear()


# Backwards compatibility: module-level instance and function
_default_fetcher: HistoricalPriceFetcher | None = None


def get_closest_price(symbol: str, target_date: str | date) -> Decimal:
    """Get closing price using default fetcher (backwards compatibility).

    Note: This function uses an in-memory-only cache. For persistent caching,
    create a HistoricalPriceFetcher instance with a file path.
    """
    global _default_fetcher
    if _default_fetcher is None:
        _default_fetcher = HistoricalPriceFetcher()
    return _default_fetcher.get_closest_price(symbol, target_date)


def clear_cache() -> None:
    """Clear the default fetcher's cache (useful for testing)."""
    global _default_fetcher
    if _default_fetcher is not None:
        _default_fetcher.clear_cache()
    _default_fetcher = None
