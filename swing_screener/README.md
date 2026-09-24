# NSE Daily Swing-Trading Screener

Generates a next-session trade plan from Nifty 50 + Nifty Next 50 + Nifty
Midcap 50 (150 stocks). **It only produces a report — it never places,
modifies, or cancels any order.** Run it after market close (after 4 PM
IST) once the day's candle is final.

## What it does

1. Downloads fresh Nifty 50 / Next 50 / Midcap 50 constituent lists from
   niftyindices.com on every run (never reuses an old list), and excludes
   Technology/IT, Energy, Airlines, Oil, Gas, Petroleum, Chemicals and Paint
   names.
2. Pulls >=1 year of daily OHLCV via yfinance for the remaining names, Nifty
   50 and India VIX, caching locally so reruns only fetch missing days.
3. Refuses to run on stale data — if the latest candle isn't today's, it
   warns and stops rather than generating a report off old prices.
4. Flags a signal when a stock (with 20-day avg traded value >= Rs 20 crore)
   meets all three fixed conditions on the latest day:
   - **Bollinger bounce**: low touches/dips below the lower 20-day (2 SD)
     band, closes back above it, and closes higher than yesterday.
   - **RSI(14) bounce**: RSI dipped to <=35 at some point in the last 5
     sessions, and today's RSI is higher than yesterday's.
   - **Volume**: today's volume exceeds the prior-20-day average.
5. Builds a trade plan for each signal (Entry = close, Stop = Entry -
   0.75xATR(14), Target = Entry x 1.03) and sizes positions by risk
   (default 0.5% of capital per trade), capping total deployed capital
   across all of the day's signals at your available capital.
6. Runs 5 extra, non-filtering checks per signal (Relative Strength vs.
   Nifty, sector index vs. its 50-day SMA, Nifty's position in its 60-day
   range, stock ADX(14) < 25, and delivery % vs. its own 20-day average from
   the NSE bhavcopy) shown as check columns and rolled into a score used to
   sort signals.
7. Lists a near-miss watchlist: liquid, non-excluded stocks meeting exactly
   2 of the 3 core conditions, with a note on what's missing and how close.
8. Prints a report to the terminal and saves `report_YYYY-MM-DD.md` +
   `signals_YYYY-MM-DD.csv` to `swing_screener/reports/`, and appends every
   signal to `swing_screener/reports/signals_log.csv` for forward-test
   tracking.

## Setup

```bash
cd swing_screener
python3 -m venv .venv && source .venv/bin/activate   # optional but recommended
pip install -r requirements.txt
```

All strategy parameters (capital, risk %, indicator windows, exclusion
lists, sector-index map, etc.) live in `config.yaml` — edit that file
rather than the code to tune anything.

## Daily run (after 4 PM IST)

From the repo root:

```bash
python -m swing_screener.run_screener
```

Common overrides:

```bash
# Lower risk to 0.25% of capital in choppy markets
python -m swing_screener.run_screener --risk-pct 0.0025

# Different capital base
python -m swing_screener.run_screener --capital 500000

# Use a different config file
python -m swing_screener.run_screener --config /path/to/config.yaml
```

The script exits with an error and prints a clear warning (without
generating a report) if the latest downloaded candle isn't from today —
that usually means the market hasn't closed yet, it's a non-trading day, or
yfinance is serving delayed/cached data. `--allow-stale` overrides this for
testing only; don't use it to trade off old data.

## Updating forward-test results

Whenever you want a refreshed scorecard on past signals (their stop/target
hasn't been checked automatically — this is a separate, deliberate step):

```bash
python -m swing_screener.update_log
```

This walks forward from each open signal's entry date through the latest
cached/downloaded price data, marks it closed the first day its stop or
target is hit (if both are hit the same day, the stop is assumed first),
records the R-multiple, and prints running stats: total/closed/open trades,
win rate, average R, and expectancy.

## Notes and caveats

- **Delivery %** comes from NSE's `sec_bhavdata_full` bhavcopy, which
  requires session cookies from nseindia.com and can be flaky (rate
  limiting, bot protection, schema changes). If it can't be downloaded for
  a run, the Delivery column shows `n/a` and the terminal/report say so
  explicitly — it is never estimated.
- **Sector index mapping** is a keyword match from the constituent CSV's
  Industry column to an NSE sector-index yfinance ticker (see
  `sector_index_map` in `config.yaml`). Anything that doesn't match a
  keyword shows `n/a` rather than a guess.
- The 3 core signal conditions and the trade-plan formulas (stop/target/risk
  %) are fixed by design — don't change them without re-validating the
  strategy; everything else (liquidity threshold, exclusions, extra-check
  thresholds, sector mapping) is tunable in `config.yaml`.
- `swing_screener/cache/` (price + bhavcopy cache) and the dated
  `report_*.md` / `signals_*.csv` files are gitignored; `signals_log.csv`
  is intentionally **not** ignored so your forward-test history persists.

## Module layout

```
swing_screener/
  config.yaml         # every tunable parameter
  config.py           # loads config.yaml
  universe.py          # niftyindices.com constituent fetch + exclusions + sector-index mapping
  data.py              # yfinance download with local caching + staleness check
  bhavcopy.py          # NSE sec_bhavdata_full delivery % (cached per date)
  indicators.py        # SMA/EMA/Bollinger/RSI/ATR/ADX
  market_context.py    # Nifty/VIX snapshot + regime label
  signals.py            # core 3-condition signal, extra checks, near-miss
  sizing.py             # entry/stop/target + portfolio-capped position sizing
  report.py             # terminal + markdown/CSV output
  logbook.py            # append to signals_log.csv
  run_screener.py        # main entry point (daily run)
  update_log.py          # separate script: fills exits + prints forward-test stats
```
