"""Tests for CGT period splitting functionality."""

from __future__ import annotations

import datetime
from decimal import Decimal
from pathlib import Path
import tempfile

import jinja2

from cgt_calc.const import LATEX_TEMPLATE_RESOURCE, PACKAGE_NAME
from cgt_calc.currency_converter import CurrencyConverter
from cgt_calc.current_price_fetcher import CurrentPriceFetcher
from cgt_calc.dates import get_tax_year_periods
from cgt_calc.initial_prices import InitialPrices
from cgt_calc.isin_converter import IsinConverter
from cgt_calc.main import CapitalGainsCalculator
from cgt_calc.model import ActionType, BrokerTransaction
from cgt_calc.spin_off_handler import SpinOffHandler
from cgt_calc.util import round_decimal, strip_zeros


def test_get_tax_year_periods_no_change() -> None:
    """Test that tax years without rate changes return a single period."""
    periods = get_tax_year_periods(2023)
    assert len(periods) == 1
    assert periods[0].start_date == datetime.date(2023, 4, 6)
    assert periods[0].end_date == datetime.date(2024, 4, 5)
    assert "2023/2024" in periods[0].label


def test_get_tax_year_periods_2024_split() -> None:
    """Test that 2024/25 tax year is split at 30 Oct 2024."""
    periods = get_tax_year_periods(2024)
    assert len(periods) == 2

    # First period: 6 Apr 2024 - 29 Oct 2024
    assert periods[0].start_date == datetime.date(2024, 4, 6)
    assert periods[0].end_date == datetime.date(2024, 10, 29)
    assert "Pre 30 Oct 2024" in periods[0].label

    # Second period: 30 Oct 2024 - 5 Apr 2025
    assert periods[1].start_date == datetime.date(2024, 10, 30)
    assert periods[1].end_date == datetime.date(2025, 4, 5)
    assert "Post 30 Oct 2024" in periods[1].label


def test_sub_period_summaries_2024() -> None:
    """Test that disposals are correctly split by period for 2024/25."""
    # Setup calculator for 2024/25 tax year
    tax_year = 2024
    broker_transactions = [
        # Buy 100 shares before the period
        BrokerTransaction(
            date=datetime.date(2024, 4, 10),
            action=ActionType.BUY,
            symbol="TEST",
            description="Buy",
            quantity=Decimal(100),
            price=Decimal(10),
            fees=Decimal(0),
            amount=Decimal(-1000),
            currency="GBP",
            broker="test",
        ),
        # Sell 30 shares in first period (before 30 Oct)
        BrokerTransaction(
            date=datetime.date(2024, 9, 15),
            action=ActionType.SELL,
            symbol="TEST",
            description="Sell",
            quantity=Decimal(30),
            price=Decimal(15),
            fees=Decimal(0),
            amount=Decimal(450),
            currency="GBP",
            broker="test",
        ),
        # Sell 40 shares in second period (after 30 Oct)
        BrokerTransaction(
            date=datetime.date(2024, 11, 20),
            action=ActionType.SELL,
            symbol="TEST",
            description="Sell",
            quantity=Decimal(40),
            price=Decimal(20),
            fees=Decimal(0),
            amount=Decimal(800),
            currency="GBP",
            broker="test",
        ),
    ]

    gbp_prices = {t.date: {"GBP": Decimal(1)} for t in broker_transactions}
    currency_converter = CurrencyConverter(None, gbp_prices)
    isin_converter = IsinConverter()
    price_fetcher = CurrentPriceFetcher(currency_converter, None, {})
    spin_off_handler = SpinOffHandler()
    initial_prices = InitialPrices()

    calculator = CapitalGainsCalculator(
        tax_year,
        currency_converter,
        isin_converter,
        price_fetcher,
        spin_off_handler,
        initial_prices,
        [],
        balance_check=False,
        calc_unrealized_gains=False,
    )

    calculator.convert_to_hmrc_transactions(broker_transactions)
    report = calculator.calculate_capital_gain()

    # Check overall totals
    assert report.disposal_count == 2
    assert report.disposal_proceeds == Decimal(1250)  # 450 + 800

    # Check period summaries
    summaries = report.sub_period_summaries()
    assert len(summaries) == 2

    # First period (pre 30 Oct): 1 disposal of 30 shares at £15
    pre_oct = summaries[0]
    assert pre_oct.disposal_count == 1
    assert pre_oct.disposal_proceeds == Decimal(450)
    assert pre_oct.allowable_costs == Decimal(300)  # 30 * 10
    assert pre_oct.capital_gain == Decimal(150)  # 450 - 300

    # Second period (post 30 Oct): 1 disposal of 40 shares at £20
    post_oct = summaries[1]
    assert post_oct.disposal_count == 1
    assert post_oct.disposal_proceeds == Decimal(800)
    assert post_oct.allowable_costs == Decimal(400)  # 40 * 10
    assert post_oct.capital_gain == Decimal(400)  # 800 - 400

    # Verify sum of periods equals total
    assert pre_oct.disposal_count + post_oct.disposal_count == report.disposal_count
    assert (
        pre_oct.disposal_proceeds + post_oct.disposal_proceeds
        == report.disposal_proceeds
    )
    assert pre_oct.allowable_costs + post_oct.allowable_costs == report.allowable_costs
    assert pre_oct.total_gain() + post_oct.total_gain() == report.total_gain()


def test_sub_period_summaries_single_period() -> None:
    """Test that years without rate changes have single-period summaries."""
    # Setup calculator for 2023/24 tax year (no rate change)
    tax_year = 2023
    broker_transactions = [
        BrokerTransaction(
            date=datetime.date(2023, 5, 1),
            action=ActionType.BUY,
            symbol="TEST",
            description="Buy",
            quantity=Decimal(50),
            price=Decimal(10),
            fees=Decimal(0),
            amount=Decimal(-500),
            currency="GBP",
            broker="test",
        ),
        BrokerTransaction(
            date=datetime.date(2023, 10, 15),
            action=ActionType.SELL,
            symbol="TEST",
            description="Sell",
            quantity=Decimal(50),
            price=Decimal(15),
            fees=Decimal(0),
            amount=Decimal(750),
            currency="GBP",
            broker="test",
        ),
    ]

    gbp_prices = {t.date: {"GBP": Decimal(1)} for t in broker_transactions}
    currency_converter = CurrencyConverter(None, gbp_prices)
    isin_converter = IsinConverter()
    price_fetcher = CurrentPriceFetcher(currency_converter, None, {})
    spin_off_handler = SpinOffHandler()
    initial_prices = InitialPrices()

    calculator = CapitalGainsCalculator(
        tax_year,
        currency_converter,
        isin_converter,
        price_fetcher,
        spin_off_handler,
        initial_prices,
        [],
        balance_check=False,
        calc_unrealized_gains=False,
    )

    calculator.convert_to_hmrc_transactions(broker_transactions)
    report = calculator.calculate_capital_gain()

    # Should have only one period
    summaries = report.sub_period_summaries()
    assert len(summaries) == 1
    assert summaries[0].disposal_count == report.disposal_count
    assert summaries[0].disposal_proceeds == report.disposal_proceeds


def test_latex_template_renders_with_periods() -> None:
    """Test that the LaTeX template renders correctly with period breakdowns."""
    # Setup calculator for 2024/25 tax year
    tax_year = 2024
    broker_transactions = [
        BrokerTransaction(
            date=datetime.date(2024, 4, 10),
            action=ActionType.BUY,
            symbol="TEST",
            description="Buy",
            quantity=Decimal(100),
            price=Decimal(10),
            fees=Decimal(0),
            amount=Decimal(-1000),
            currency="GBP",
            broker="test",
        ),
        BrokerTransaction(
            date=datetime.date(2024, 9, 15),
            action=ActionType.SELL,
            symbol="TEST",
            description="Sell",
            quantity=Decimal(30),
            price=Decimal(15),
            fees=Decimal(0),
            amount=Decimal(450),
            currency="GBP",
            broker="test",
        ),
        BrokerTransaction(
            date=datetime.date(2024, 11, 20),
            action=ActionType.SELL,
            symbol="TEST",
            description="Sell",
            quantity=Decimal(40),
            price=Decimal(20),
            fees=Decimal(0),
            amount=Decimal(800),
            currency="GBP",
            broker="test",
        ),
    ]

    gbp_prices = {t.date: {"GBP": Decimal(1)} for t in broker_transactions}
    currency_converter = CurrencyConverter(None, gbp_prices)
    isin_converter = IsinConverter()
    price_fetcher = CurrentPriceFetcher(currency_converter, None, {})
    spin_off_handler = SpinOffHandler()
    initial_prices = InitialPrices()

    calculator = CapitalGainsCalculator(
        tax_year,
        currency_converter,
        isin_converter,
        price_fetcher,
        spin_off_handler,
        initial_prices,
        [],
        balance_check=False,
        calc_unrealized_gains=False,
    )

    calculator.convert_to_hmrc_transactions(broker_transactions)
    report = calculator.calculate_capital_gain()

    # Render the LaTeX template
    latex_template_env = jinja2.Environment(
        block_start_string="\\BLOCK{",
        block_end_string="}",
        variable_start_string="\\VAR{",
        variable_end_string="}",
        comment_start_string="\\#{",
        comment_end_string="}",
        line_statement_prefix="%%",
        line_comment_prefix="%#",
        trim_blocks=True,
        autoescape=False,
        loader=jinja2.PackageLoader(PACKAGE_NAME, "resources"),
        extensions=["jinja2.ext.loopcontrols"],
    )
    template = latex_template_env.get_template(LATEX_TEMPLATE_RESOURCE)
    output_text = template.render(
        report=report,
        round_decimal=round_decimal,
        strip_zeros=strip_zeros,
        Decimal=Decimal,
    )

    # Verify the output contains period breakdown section
    assert "Breakdown by CGT Regime" in output_text
    assert "Pre 30 Oct 2024 CGT regime" in output_text
    assert "Post 30 Oct 2024 CGT regime" in output_text
    assert "06/04/2024" in output_text  # Start of first period
    assert "29/10/2024" in output_text  # End of first period
    assert "30/10/2024" in output_text  # Start of second period
    assert "05/04/2025" in output_text  # End of second period

    # Write to temp file to verify it's valid LaTeX (syntax-wise)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", suffix=".tex", delete=True
    ) as tmp:
        tmp.write(output_text)
        tmp.flush()
        # Just verify we can write it; actual pdflatex compilation is optional
        assert Path(tmp.name).exists()
