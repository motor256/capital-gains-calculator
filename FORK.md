# Fork changes

This fork (`motor256/capital-gains-calculator`) tracks
[KapJI/capital-gains-calculator](https://github.com/KapJI/capital-gains-calculator). This file lists
everything that is **not** upstream, so a rebase has one place to look.

Find every touch point with `git grep "FORK"`.

## Rule

- Fork code lives in `cgt_calc/fork/`, its tests in `tests/fork/`, and local tooling in `fork_tools/`.
- An upstream file may only gain a one-line import or call into `cgt_calc/fork/`, marked
    `# FORK: see FORK.md`, plus a short `# FORK:` comment where it changes a branch.
- Every extension is off unless the user passes its option, so a run without them behaves exactly
    like upstream.

## Extensions

### `--infer-split-units`: Schwab Equity Awards share units from market prices

**Problem.** Upstream's Schwab Equity Awards parser assumes Schwab restates acquisitions for later
stock splits and leaves disposals in the units of their own day. A December 2025 NVDA export left
everything, acquisitions and lapses included, in the units of its own day for the 2024 10:1 split.
Read as upstream assumes, acquisitions come out ten times too small, the lapse check rejects the
file, and the run stops with a disposal larger than the holding. Whether other users' exports behave
like either is not known, so the option decides per row instead of assuming.

**How.** Each priced acquisition and disposal of a symbol with a known split is compared with the
split-adjusted market close that day. A price about equal to the market's means the row is in
current units. A price a split ratio above it means the row is that many times short of them. The
choice is refused if no reading is within 1.5 times the market price.

| What | Where |
| --- | --- |
| Unit inference | `cgt_calc/fork/split_units.py` |
| Yahoo Finance prices and the CSV cache | `cgt_calc/fork/market_prices.py` |
| Options and switching it on | `cgt_calc/fork/options.py` |
| Tests | `tests/fork/test_split_units.py` |

**Touch points in upstream files.**

| File | Change |
| --- | --- |
| `cgt_calc/args_parser.py` | import, and one call adding the options to the parser |
| `cgt_calc/cli.py` | import, and one call switching the extension on before any file is read |
| `cgt_calc/parsers/schwab_equity_award_json.py` | import; skips `_check_lapse_units` when on; in `SchwabAwardTransaction.__init__`, asks the fork for the multiplier before falling back to `_convert_disposal_to_current_units` |

**When to drop it.** If upstream's NVDA handling reads a current export correctly, delete
`cgt_calc/fork/`, `tests/fork/`, and the three touch points above. Compare with the rows in
"Evidence" below.

**Evidence.** In the December 2025 export, a 02/28/2023 ESPP purchase read `Quantity 53` at
`PurchaseFairMarketValue $232.16`, a 02/03/2023 sale read `Quantity 123` at `$211.185`, and a
03/20/2024 lapse read `Quantity 880` with `560` deposited plus `320` withheld inside it. All are in
units of the day, where upstream expects acquisitions and lapse quantities restated.

## Not ported from the old branch

The old `feat/my-work` branch also had these. Upstream now covers them, so they were dropped:

| Old feature | Use instead |
| --- | --- |
| `--save-broker-transactions` | `--dump-transactions PATH` |
| CGT regime breakdown for 2024/25 | `--from 2024-10-30 --to 2025-04-05` |
| NVDA and ESPP support, skipping Lapse and Tax Withholding | built in |

Not ported and not covered upstream: `--no-dividends`, which would touch the calculator and both
report renderers.
