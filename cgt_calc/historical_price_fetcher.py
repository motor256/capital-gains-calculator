"""Fetch historical stock prices for transaction normalization (e.g., stock splits)."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal

import pandas as pd
import yfinance as yf  # type: ignore[import-untyped]

# Module-level cache for performance
_price_cache: dict[str, pd.DataFrame] = {}

# Known symbols that need broad historical ranges
BROAD_RANGE_SYMBOLS = {
    "NVDA": ("2017-01-01", "2025-12-31"),  # Covers all historical NVDA splits
    # Add more as needed:
    # 'TSLA': ('2020-01-01', '2025-12-31'),
}

# Default date range for unknown symbols when fetching historical prices
DEFAULT_LOOKBACK_DAYS = 365  # Look back 1 year
DEFAULT_LOOKAHEAD_DAYS = 30  # Look ahead 30 days

# Maximum allowed deviation between target date and closest available market date
MAX_DATE_TOLERANCE_DAYS = 5  # Must be within 5 days


def get_closest_price(symbol: str, target_date: str | date) -> Decimal:
    """Get closing price closest to target date, with automatic caching.

    First call for a symbol fetches and caches historical data.
    Subsequent calls use cached data for instant lookups.

    Args:
        symbol: Stock ticker symbol (e.g., 'NVDA')
        target_date: Target date as string 'YYYY-MM-DD' or date object

    Returns:
        Closing price as Decimal

    """
    if isinstance(target_date, date):
        target_date_str = target_date.strftime("%Y-%m-%d")
    else:
        target_date_str = target_date

    # Warm cache on first use of this symbol
    if symbol not in _price_cache:
        if symbol in BROAD_RANGE_SYMBOLS:
            start, end = BROAD_RANGE_SYMBOLS[symbol]
            print(f"Fetching {symbol} historical prices ({start} to {end})...")
        else:
            # Dynamic range for unknown symbols
            date_obj = datetime.strptime(target_date_str, "%Y-%m-%d").date()
            start = (date_obj - timedelta(days=DEFAULT_LOOKBACK_DAYS)).strftime(
                "%Y-%m-%d"
            )
            end = (date_obj + timedelta(days=DEFAULT_LOOKAHEAD_DAYS)).strftime(
                "%Y-%m-%d"
            )
            print(f"Fetching {symbol} historical prices ({start} to {end})...")

        _price_cache[symbol] = _fetch_price_data(symbol, start, end)

    # Use cached data
    price_float = _fetch_closest_close_price(_price_cache[symbol], target_date_str)
    return Decimal(str(price_float))


def _fetch_price_data(ticker: str, start_date: str, end_date: str) -> pd.DataFrame:
    """Fetch historical price data from yfinance."""
    stock_data: pd.DataFrame = yf.download(ticker, start=start_date, end=end_date)
    if stock_data.empty:
        msg = f"No data found for ticker '{ticker}' from {start_date} to {end_date}."
        raise RuntimeError(msg)
    return stock_data


def _fetch_closest_close_price(data: pd.DataFrame, target_date: str) -> float:
    """Fetch the market close price closest to a given date from the DataFrame.

    Args:
        data: DataFrame containing historical stock prices
        target_date: The target date in 'YYYY-MM-DD' format

    Returns:
        The close price closest to the target date

    Raises:
        Exception: If no suitable price data found or dates too far apart

    """
    target_date_obj = datetime.strptime(target_date, "%Y-%m-%d")
    data.index = pd.to_datetime(data.index)

    closest_date_idx = data.index.get_indexer([target_date_obj], method="nearest")[0]
    closest_date = data.index[closest_date_idx]

    # Ensure the closest date is within acceptable tolerance
    if abs((closest_date - target_date_obj).days) > MAX_DATE_TOLERANCE_DAYS:
        msg = (
            f"Closest available date {closest_date} is too far "
            f"from target {target_date_obj}"
        )
        raise RuntimeError(msg)

    closest_data_row = data.loc[closest_date]
    close_value = closest_data_row["Close"].iloc[0]

    # Check if value is missing/NaN before converting
    if pd.isna(close_value):
        msg = f"Could not find price for {target_date}"
        raise RuntimeError(msg)

    return float(close_value)


def clear_cache() -> None:
    """Clear the price cache (useful for testing)."""
    _price_cache.clear()
