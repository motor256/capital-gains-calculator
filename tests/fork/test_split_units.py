"""FORK: inferring Schwab Equity Awards share units from market prices.

The rows mimic an export that leaves every NVDA row in the units of its own
day for the 2024 10:1 split, and restated for the 2021 4:1 one. Real dates and
prices, invented share counts, like upstream's NVDA fixture.
"""

from __future__ import annotations

import datetime
from decimal import Decimal
import json
from typing import TYPE_CHECKING

import pytest

from cgt_calc.exceptions import ParsingError
from cgt_calc.fork import split_units
from cgt_calc.fork.market_prices import MarketPriceError, MarketPrices
from cgt_calc.model import ActionType
from cgt_calc.parsers import schwab_equity_award_json

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

    from cgt_calc.model import BrokerTransaction
    from cgt_calc.parsers.schwab_equity_award_json import JsonRowType

NVDA_SPLITS = (
    (datetime.date(2021, 7, 20), 4),
    (datetime.date(2024, 6, 10), 10),
)

# Split-adjusted closes: what Yahoo reports today for those days.
MARKET = {
    datetime.date(2018, 2, 28): Decimal("6.05"),
    datetime.date(2021, 12, 8): Decimal("31.83"),
    datetime.date(2023, 2, 3): Decimal("21.12"),
    datetime.date(2023, 2, 28): Decimal("23.22"),
    datetime.date(2025, 5, 19): Decimal("135.00"),
}


class FakeMarket:
    """A price source that records which days were asked about."""

    def __init__(self) -> None:
        """Start with no questions asked."""
        self.asked: list[datetime.date] = []

    def closest_price(self, symbol: str, date: datetime.date) -> Decimal:
        """Return the canned close for `date`."""
        assert symbol == "NVDA"
        self.asked.append(date)
        return MARKET[date]


@pytest.fixture(name="market")
def market_fixture() -> Iterator[FakeMarket]:
    """Switch the feature on with a fake market, and off again afterwards."""
    market = FakeMarket()
    split_units.configure(market)
    yield market
    split_units.configure(None)


def deposit(
    date: str, description: str, quantity: int, price: str, details: dict[str, str]
) -> JsonRowType:
    """Return a Deposit row, priced in the field its kind of row uses."""
    price_field = (
        "PurchaseFairMarketValue" if description == "ESPP" else "VestFairMarketValue"
    )
    return {
        "Date": date,
        "Action": "Deposit",
        "Symbol": "NVDA",
        "Quantity": str(quantity),
        "Description": description,
        "FeesAndCommissions": None,
        "DisbursementElection": None,
        "Amount": None,
        "TransactionDetails": [{"Details": {**details, price_field: price}}],
    }


def export(tmp_path: Path, rows: list[JsonRowType]) -> Path:
    """Write `rows` as an Equity Awards JSON export."""
    path = tmp_path / "awards.json"
    path.write_text(
        json.dumps(
            {"FromDate": "01/01/2017", "ToDate": "12/31/2025", "Transactions": rows}
        ),
        encoding="utf-8",
    )
    return path


ESPP_2018 = deposit(
    "02/28/2018",
    "ESPP",
    72,
    "$60.50",
    {"PurchaseDate": "02/28/2018", "SubscriptionDate": "09/01/2017"},
)
RS_2021 = deposit(
    "12/08/2021",
    "RS",
    21,
    "$318.26",
    {"AwardDate": "08/10/2020", "AwardId": "1", "VestDate": "12/08/2021"},
)
ESPP_2023 = deposit(
    "02/28/2023",
    "ESPP",
    53,
    "$232.16",
    {"PurchaseDate": "02/28/2023", "SubscriptionDate": "09/01/2022"},
)
SALE_2023: JsonRowType = {
    "Date": "02/03/2023",
    "Action": "Sale",
    "Symbol": "NVDA",
    "Quantity": "123",
    "Description": "Share Sale",
    "FeesAndCommissions": "$0.59",
    "DisbursementElection": "Cash",
    "Amount": "$25,975.17",
    "TransactionDetails": [
        {
            "Details": {
                "Type": "RS",
                "Shares": "123",
                "SalePrice": "$211.185",
                "GrossProceeds": "$25,975.76",
                "VestDate": "12/08/2021",
                "VestFairMarketValue": "$318.26",
            }
        }
    ],
}


def parse(path: Path) -> list[BrokerTransaction]:
    """Parse an export the way the CLI does."""
    return list(
        schwab_equity_award_json.SchwabEquityAwardsParser().load_from_file(path)
    )


def on(
    transactions: list[BrokerTransaction], date: datetime.date, action: ActionType
) -> BrokerTransaction:
    """Return the single transaction of that kind on that date."""
    found = [t for t in transactions if t.date == date and t.action == action]
    assert len(found) == 1
    return found[0]


@pytest.mark.parametrize(
    ("on_date", "expected"),
    [
        (datetime.date(2018, 2, 28), [1, 10, 40]),
        (datetime.date(2021, 12, 8), [1, 10]),
        (datetime.date(2024, 6, 10), [1]),
        (datetime.date(2025, 5, 19), [1]),
    ],
)
def test_candidates_are_the_states_a_restatement_can_leave(
    on_date: datetime.date, expected: list[int]
) -> None:
    """A row is restated for every later split, or all but the latest ones."""
    assert split_units.candidate_multipliers(NVDA_SPLITS, on_date) == expected


def test_row_in_units_of_its_own_day_is_converted(
    tmp_path: Path,
    market: FakeMarket,
) -> None:
    """An export leaving the 2024 split unapplied is restated row by row."""
    transactions = parse(export(tmp_path, [ESPP_2018, RS_2021, ESPP_2023, SALE_2023]))

    # Restated for 4:1 only: needs 10 to reach current units.
    espp_2018 = on(transactions, datetime.date(2018, 2, 28), ActionType.STOCK_ACTIVITY)
    assert (espp_2018.quantity, espp_2018.price) == (Decimal(720), Decimal("6.05"))

    rs_2021 = on(transactions, datetime.date(2021, 12, 8), ActionType.STOCK_ACTIVITY)
    assert (rs_2021.quantity, rs_2021.price) == (Decimal(210), Decimal("31.826"))

    espp_2023 = on(transactions, datetime.date(2023, 2, 28), ActionType.STOCK_ACTIVITY)
    assert (espp_2023.quantity, espp_2023.price) == (Decimal(530), Decimal("23.216"))

    sale = on(transactions, datetime.date(2023, 2, 3), ActionType.SELL)
    assert sale.quantity == Decimal(1230)
    assert sale.price is not None
    assert sale.price == Decimal("21.118504")
    # The money does not change with the units.
    assert sale.amount == Decimal("25975.17")


def test_row_already_in_current_units_is_left_alone(
    tmp_path: Path,
    market: FakeMarket,
) -> None:
    """A row priced like the market needs no conversion, so mixed files work."""
    restated = deposit(
        "02/28/2023",
        "ESPP",
        530,
        "$23.216",
        {"PurchaseDate": "02/28/2023", "SubscriptionDate": "09/01/2022"},
    )
    transactions = parse(export(tmp_path, [restated]))

    acquisition = on(
        transactions, datetime.date(2023, 2, 28), ActionType.STOCK_ACTIVITY
    )
    assert (acquisition.quantity, acquisition.price) == (
        Decimal(530),
        Decimal("23.216"),
    )


def test_no_price_is_fetched_after_the_last_split(
    tmp_path: Path, market: FakeMarket
) -> None:
    """Nothing can be in the wrong units after the latest split."""
    late = deposit(
        "05/19/2025",
        "RS",
        100,
        "$135.00",
        {"AwardDate": "08/10/2020", "AwardId": "1", "VestDate": "05/19/2025"},
    )
    transactions = parse(export(tmp_path, [late]))

    assert market.asked == []
    assert transactions[0].quantity == Decimal(100)


def test_price_matching_no_unit_is_refused(
    tmp_path: Path,
    market: FakeMarket,
) -> None:
    """A price far from every possible reading is not guessed at."""
    wrong = deposit(
        "02/28/2023",
        "ESPP",
        53,
        "$80.00",  # 3.4 times the market price: neither 1 nor 10 times
        {"PurchaseDate": "02/28/2023", "SubscriptionDate": "09/01/2022"},
    )
    with pytest.raises(ParsingError, match="Cannot tell which share units"):
        parse(export(tmp_path, [wrong]))


def test_lapse_check_is_skipped_when_inferring(
    tmp_path: Path,
    market: FakeMarket,
) -> None:
    """Upstream's lapse check assumes the units this option replaces."""
    lapse: JsonRowType = {
        "Date": "03/20/2024",
        "Action": "Lapse",
        "Symbol": "NVDA",
        "Quantity": "880",
        "Description": "Restricted Stock Lapse",
        "FeesAndCommissions": None,
        "DisbursementElection": None,
        "Amount": None,
        "TransactionDetails": [
            {
                "Details": {
                    "AwardDate": "05/08/2020",
                    "AwardId": "156500",
                    "FairMarketValuePrice": "$90.37",
                    "SalePrice": "",
                    "SharesSoldWithheldForTaxes": "320",
                    "NetSharesDeposited": "560",
                    "Taxes": "$28,410.35",
                }
            }
        ],
    }
    assert parse(export(tmp_path, [lapse])) == []


def test_without_the_option_upstream_behaviour_is_unchanged(tmp_path: Path) -> None:
    """Off by default: acquisitions are read as recorded, disposals converted."""
    split_units.configure(None)
    transactions = parse(export(tmp_path, [ESPP_2023, SALE_2023]))

    acquisition = on(
        transactions, datetime.date(2023, 2, 28), ActionType.STOCK_ACTIVITY
    )
    assert acquisition.quantity == Decimal(53)
    sale = on(transactions, datetime.date(2023, 2, 3), ActionType.SELL)
    assert sale.quantity == Decimal(1230)


def test_market_prices_are_read_from_the_cache_file(tmp_path: Path) -> None:
    """Prices in the cache file need no network."""
    cache = tmp_path / "prices.csv"
    cache.write_text(
        "symbol,date,close_price\nNVDA,2023-02-27,23.10\nNVDA,2023-02-28,23.22\n",
        encoding="utf-8",
    )
    prices = MarketPrices(cache)

    assert prices.closest_price("NVDA", datetime.date(2023, 2, 28)) == Decimal("23.22")
    # A day without a close takes the nearest one.
    assert prices.closest_price("NVDA", datetime.date(2023, 3, 1)) == Decimal("23.22")


def test_missing_market_price_is_reported() -> None:
    """A symbol Yahoo has nothing for is a clear error, not a guess."""
    prices = MarketPrices(None)
    # Nothing cached, and every year already marked as asked: no network.
    for year in range(2022, 2025):
        prices._fetched_years.add(("NVDA", year))  # noqa: SLF001
    with pytest.raises(MarketPriceError, match="No market price for NVDA"):
        prices.closest_price("NVDA", datetime.date(2023, 2, 28))
