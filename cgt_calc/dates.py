"""Function to work with dates."""

from __future__ import annotations

from dataclasses import dataclass
import datetime

from .const import CGT_RATE_CHANGE_DATES, CGT_RATE_PERIOD_LABELS


def is_date(date: datetime.date) -> bool:
    """Check if date has only date but not time."""
    if not isinstance(date, datetime.date) or isinstance(date, datetime.datetime):
        raise TypeError(f'should be datetime.date: {type(date)} "{date}"')
    return True


def get_tax_year_start(tax_year: int) -> datetime.date:
    """Return tax year start date."""
    # 6 April
    return datetime.date(tax_year, 4, 6)


def get_tax_year_end(tax_year: int) -> datetime.date:
    """Return tax year end date."""
    # 5 April
    return datetime.date(tax_year + 1, 4, 5)


@dataclass(frozen=True)
class TaxRatePeriod:
    """Represents a CGT regime period within a tax year."""

    start_date: datetime.date
    end_date: datetime.date
    label: str


def get_tax_year_periods(tax_year: int) -> list[TaxRatePeriod]:
    """Return list of CGT regime periods for the given tax year.

    If no rate changes are configured for the tax year, returns a single
    period covering the entire tax year. Otherwise, splits the year into
    multiple periods based on the configured change dates.
    """
    start = get_tax_year_start(tax_year)
    end = get_tax_year_end(tax_year)

    # Get change dates for this tax year, filtering to only those within bounds
    change_dates = [
        d for d in sorted(CGT_RATE_CHANGE_DATES.get(tax_year, [])) if start <= d <= end
    ]

    # No change dates → single full-year regime
    if not change_dates:
        return [
            TaxRatePeriod(
                start_date=start,
                end_date=end,
                label=f"CGT regime {tax_year}/{tax_year + 1}",
            )
        ]

    # Get labels for the periods
    labels = CGT_RATE_PERIOD_LABELS.get(tax_year)
    expected_label_count = len(change_dates) + 1
    if labels is None:
        labels = [f"Regime {i + 1}" for i in range(expected_label_count)]

    assert len(labels) == expected_label_count, (
        f"Tax year {tax_year}: expected {expected_label_count} labels "
        f"for {len(change_dates)} change date(s), got {len(labels)}"
    )

    # Build periods
    periods: list[TaxRatePeriod] = []
    period_start = start

    for idx, change_date in enumerate(change_dates):
        periods.append(
            TaxRatePeriod(
                start_date=period_start,
                end_date=change_date - datetime.timedelta(days=1),
                label=labels[idx],
            )
        )
        period_start = change_date

    # Final period from last change date to tax year end
    periods.append(
        TaxRatePeriod(
            start_date=period_start,
            end_date=end,
            label=labels[-1],
        )
    )

    # Validate periods are contiguous and non-overlapping
    for i in range(len(periods) - 1):
        assert (
            periods[i].end_date + datetime.timedelta(days=1)
            == periods[i + 1].start_date
        ), (
            f"Gap or overlap between periods: {periods[i].end_date} and {periods[i + 1].start_date}"
        )
    assert periods[0].start_date == start, (
        "First period doesn't start at tax year start"
    )
    assert periods[-1].end_date == end, "Last period doesn't end at tax year end"

    return periods
