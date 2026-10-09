"""FORK: tell which share units a Schwab Equity Awards row is in, from its price.

Upstream's Schwab Equity Awards parser assumes Schwab restates acquisitions for
later stock splits and leaves disposals in the units of their own day. That is
what the exports it was written against did, but not every export does: one
downloaded in December 2025 held NVDA acquisitions, disposals and lapses all in
the units of their own day for the 2024 10:1 split. Read as upstream assumes,
its acquisitions come out ten times too small and the run stops with a
disposal larger than the holding.

Nothing in such a file says which units a row is in, but its price does. A
share's price on the day, restated for every later split, is known from market
data. A row priced about that is already restated; one priced a split ratio
above it is not. Comparing the two decides it per row, so a file that restates
some rows and not others is read correctly too.

Used only when the user passes `--infer-split-units`; see `options.py`.
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
import math
from typing import TYPE_CHECKING, Final

from cgt_calc.exceptions import ParsingError
from cgt_calc.model import ActionType

if TYPE_CHECKING:
    from collections.abc import Sequence
    import datetime
    from pathlib import Path

    from cgt_calc.model import BrokerTransaction

    from .market_prices import PriceSource

LOGGER = logging.getLogger(__name__)

# Rows with a price and a share count, which is all that can be compared.
PRICED_ACTIONS: Final = frozenset({ActionType.STOCK_ACTIVITY, ActionType.SELL})

# How far a recorded price may sit from the market's, after the units are
# chosen, before the choice is not trusted. Execution and fair market prices
# differ from a close by a few percent, and the closest wrong answer is a whole
# split ratio away, so this has a lot of room either side.
MAX_PRICE_DEVIATION: Final = 1.5


@dataclass
class _State:
    """The price source for this run, or None while the feature is off."""

    price_source: PriceSource | None = None


_STATE = _State()


def configure(price_source: PriceSource | None) -> None:
    """Switch the feature on with a price source, or off with None."""
    _STATE.price_source = price_source


def enabled() -> bool:
    """Whether this run infers share units from prices."""
    return _STATE.price_source is not None


def candidate_multipliers(
    splits: Sequence[tuple[datetime.date, int]], on: datetime.date
) -> list[int]:
    """Factors a share count printed on `on` may need to reach current units.

    1 if the row is restated for every later split, then the latest split's
    ratio if it is restated for all but that one, and so on back to the product
    of all of them if it is not restated at all. A restatement is applied
    split by split, so those are the only states a row can be in.
    """
    later = sorted((split for split in splits if split[0] > on), reverse=True)
    candidates = [1]
    for _, ratio in later:
        candidates.append(candidates[-1] * ratio)
    return candidates


def multiplier_for(
    transaction: BrokerTransaction,
    splits: Sequence[tuple[datetime.date, int]],
    file: Path,
) -> int | None:
    """Return the factor that restates `transaction` into current units.

    None when the feature is off or the row has nothing to compare, so the
    caller carries on as upstream does.
    """
    source = _STATE.price_source
    if (
        source is None
        or transaction.action not in PRICED_ACTIONS
        or not transaction.price
        or not transaction.quantity
        or transaction.symbol is None
    ):
        return None

    candidates = candidate_multipliers(splits, transaction.date)
    if len(candidates) == 1:
        # No split since: the units cannot be wrong, so no price is needed.
        return 1

    market = source.closest_price(transaction.symbol, transaction.date)
    ratio = float(transaction.price / market)
    chosen = min(candidates, key=lambda factor: abs(math.log(ratio / factor)))
    deviation = max(ratio / chosen, chosen / ratio)
    if deviation > MAX_PRICE_DEVIATION:
        raise ParsingError(
            file,
            f"Cannot tell which share units the {transaction.action.name} of "
            f"{transaction.symbol} on {transaction.date} is in: it is priced at "
            f"{transaction.price} and the market price that day was "
            f"{market:.4f}, which is {ratio:.2f} times that. The units it can "
            f"be in are {candidates} times the market price, and none is "
            "within range. Check the row against a broker statement.",
        )
    LOGGER.debug(
        "%s %s on %s: price %s is %.2f times the market price, so %s",
        transaction.action.name,
        transaction.symbol,
        transaction.date,
        transaction.price,
        ratio,
        "already in current units"
        if chosen == 1
        else f"multiplying the share count by {chosen}",
    )
    return chosen
