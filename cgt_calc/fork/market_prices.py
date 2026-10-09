"""FORK: historical closing prices from Yahoo Finance, cached in a CSV file.

Used to tell which share units a broker export is in, by comparing a recorded
price with what the share really cost on that day. Prices are split-adjusted,
so they are in today's units whatever the export did.

They are also adjusted for dividends, which moves an old price by a few
percent. That is far below the factor of a split, which is all they are
compared on.
"""

from __future__ import annotations

import csv
import datetime
from decimal import Decimal, InvalidOperation
import logging
from typing import TYPE_CHECKING, Final, Protocol

from cgt_calc.exceptions import CgtError, ParsingError
from cgt_calc.util import open_with_parents

if TYPE_CHECKING:
    from pathlib import Path

LOGGER = logging.getLogger(__name__)

CACHE_HEADER: Final = ["symbol", "date", "close_price"]

# The nearest trading day counts as the price of a day without one, such as a
# weekend or a holiday. Further away than this, the price is not the day's.
MAX_DATE_GAP_DAYS: Final = 5


class MarketPriceError(CgtError):
    """Raised when no market price could be found for a symbol and date."""

    def __init__(self, symbol: str, date: datetime.date) -> None:
        """Initialise."""
        super().__init__(
            f"No market price for {symbol} within {MAX_DATE_GAP_DAYS} days of "
            f"{date}. Yahoo Finance may list it under a different ticker, or "
            "it could not be reached. Without it the share units of the "
            "export cannot be checked."
        )


class PriceSource(Protocol):
    """Anything that can say what a share closed at on a day."""

    def closest_price(self, symbol: str, date: datetime.date) -> Decimal:
        """Return the split-adjusted close on `date` or the nearest trading day."""


class MarketPrices:
    """Split-adjusted closing prices, fetched a year at a time and cached."""

    def __init__(self, cache_file: Path | None = None) -> None:
        """Load the cache file, if there is one."""
        self.cache_file = cache_file
        self._prices: dict[str, dict[datetime.date, Decimal]] = {}
        # Years already asked Yahoo for, so a day without data is not asked again.
        self._fetched_years: set[tuple[str, int]] = set()
        self._read_cache()

    def closest_price(self, symbol: str, date: datetime.date) -> Decimal:
        """Return the close on `date` or the nearest trading day."""
        found = self._lookup(symbol, date)
        if found is None:
            gap = datetime.timedelta(days=MAX_DATE_GAP_DAYS)
            # The nearest trading day can be in the year before or after.
            for year in sorted({(date - gap).year, date.year, (date + gap).year}):
                self._fetch_year(symbol, year)
            found = self._lookup(symbol, date)
        if found is None:
            raise MarketPriceError(symbol, date)
        return found

    def _lookup(self, symbol: str, date: datetime.date) -> Decimal | None:
        by_date = self._prices.get(symbol)
        if not by_date:
            return None
        nearest = min(by_date, key=lambda day: abs((day - date).days))
        if abs((nearest - date).days) > MAX_DATE_GAP_DAYS:
            return None
        return by_date[nearest]

    def _fetch_year(self, symbol: str, year: int) -> None:
        if (symbol, year) in self._fetched_years:
            return
        self._fetched_years.add((symbol, year))
        today = datetime.datetime.now(tz=datetime.UTC).date()
        start = datetime.date(year, 1, 1)
        if start > today:
            return
        end = min(datetime.date(year + 1, 1, 1), today + datetime.timedelta(days=1))

        LOGGER.info(
            "Fetching %s closing prices for %s from Yahoo Finance", symbol, year
        )
        # Imported here because it loads pandas, and most runs fetch no price.
        import yfinance as yf  # type: ignore[import-untyped]  # noqa: PLC0415

        history = yf.Ticker(symbol).history(
            start=start.isoformat(), end=end.isoformat(), auto_adjust=True
        )
        by_date = self._prices.setdefault(symbol, {})
        for stamp, close in zip(history.index, history["Close"], strict=True):
            # A day Yahoo has no close for comes back as NaN.
            if close == close:  # noqa: PLR0124
                by_date[stamp.date()] = Decimal(format(close, ".15g"))
        self._write_cache()

    def _read_cache(self) -> None:
        if self.cache_file is None or not self.cache_file.is_file():
            return
        with self.cache_file.open(encoding="utf8", newline="") as file:
            reader = csv.reader(file)
            header = next(reader, None)
            if header is None:
                return
            if header != CACHE_HEADER:
                raise ParsingError(
                    self.cache_file,
                    f"Unexpected columns in market prices cache: found {header}, "
                    f"expected {CACHE_HEADER}. Delete the file to fetch the "
                    "prices again.",
                )
            for row_index, row in enumerate(reader, start=2):
                if not any(cell.strip() for cell in row):
                    continue
                try:
                    symbol, day, close = (cell.strip() for cell in row)
                    self._prices.setdefault(symbol, {})[
                        datetime.date.fromisoformat(day)
                    ] = Decimal(close)
                except (ValueError, InvalidOperation) as err:
                    raise ParsingError(
                        self.cache_file,
                        f"Cannot read market prices cache row {row_index}: {row}",
                        row_index=row_index,
                    ) from err

    def _write_cache(self) -> None:
        if self.cache_file is None:
            return
        with open_with_parents(self.cache_file) as file:
            writer = csv.writer(file)
            writer.writerow(CACHE_HEADER)
            for symbol, by_date in sorted(self._prices.items()):
                for day, close in sorted(by_date.items()):
                    writer.writerow([symbol, day.isoformat(), str(close)])
