"""Export parsed broker transactions to CSV."""

from __future__ import annotations

import csv
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

    from .model import BrokerTransaction

LOGGER = logging.getLogger(__name__)

# Broker value used for non-broker transactions (e.g., ERI)
NON_BROKER_MARKER = "N/A"

# CSV column headers matching BrokerTransaction fields
BROKER_TRANSACTION_CSV_HEADERS = [
    "date",
    "action",
    "symbol",
    "description",
    "quantity",
    "price",
    "fees",
    "amount",
    "currency",
    "broker",
    "isin",
]


def save_broker_transactions(
    transactions: list[BrokerTransaction],
    output_path: Path,
) -> None:
    """Save broker transactions to a CSV file.

    Filters out non-broker transactions (e.g., ERI with broker="N/A").

    Args:
        transactions: List of parsed transactions (may include non-broker ones).
        output_path: Path to the output CSV file.

    """
    # Filter to only include actual broker transactions
    broker_transactions = [
        txn for txn in transactions if txn.broker != NON_BROKER_MARKER
    ]

    # Ensure output directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", newline="", encoding="utf-8") as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(BROKER_TRANSACTION_CSV_HEADERS)

        for txn in broker_transactions:
            writer.writerow(
                [
                    txn.date.isoformat(),
                    txn.action.name,
                    txn.symbol if txn.symbol is not None else "",
                    txn.description,
                    str(txn.quantity) if txn.quantity is not None else "",
                    str(txn.price) if txn.price is not None else "",
                    str(txn.fees),
                    str(txn.amount) if txn.amount is not None else "",
                    txn.currency,
                    txn.broker,
                    txn.isin if txn.isin is not None else "",
                ]
            )

    LOGGER.info(
        "Saved %d broker transactions to %s", len(broker_transactions), output_path
    )
    print(f"Broker transactions saved to {output_path}")
