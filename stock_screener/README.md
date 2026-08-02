# NSE Stock Screener — Bollinger Band Bounce + RSI + Volume

Screens Nifty 50 + Nifty Next 50 + Nifty Midcap 50 (150 stocks) for a same-day
confluence of:

1. **Bollinger Band bounce** — low touches/dips below the lower 20-day ± 2σ
   band, close recovers above it, and closes higher than yesterday.
2. **RSI turning up** — RSI(14) is higher than yesterday. (As of 2026-07-30
   this no longer requires RSI to have dipped to a fixed oversold level first
   — see note below.)
3. **Volume confirmation** — today's volume exceeds the prior 20-day average.
4. **Relative Strength vs. universe** — the stock's % change today exceeds
   the average % change across the whole screened universe, i.e. it's
   outperforming rather than just riding a sector/market-wide tailwind.

Also requires 20-day average daily traded value ≥ ₹20 crore (liquidity), and
excludes Technology/Energy sector stocks and Airlines/Oil/Gas/Petroleum/
Chemicals/Paint industries.

For each signal it computes Entry (close), Stop-loss (Entry − 0.75×ATR14),
Target (Entry × 1.03), and position size (0.5% capital risk per trade, capped
by available capital). Stocks meeting exactly 3 of the 4 conditions are
reported separately as a near-miss watchlist, flagged with the missing
condition.

**Rule-change note:** the original design required RSI(14) to dip to ≤35
within the last 5 days before turning up. That fixed oversold floor was
dropped because a genuine bounce can happen with RSI never reaching classic
oversold (a healthy pullback in a strong stock, vs. a beaten-down reversal).
Relative Strength vs. the universe now does the job of filtering real moves
from tailwind-driven ones instead. **This changes what counts as a signal
from the version that was backtested** (2yr, ~482 signals, 36.1% win rate,
+0.1195 R average expectancy) — that backtest was run against the original
3-condition rule with the RSI floor. The current 4-condition version has not
been re-backtested; treat its output as unproven until validated against
history.

## Quality Pullback strategy (alternative mode)

A second, independent strategy for a different market condition: instead of
chasing an oversold bounce, it looks for fundamentally strong stocks resting
quietly near support, with no sign of a recent shock. A stock must pass all
of:

1. **Near 50-day support** — close within 2% of its 50-day SMA.
2. **Between Bollinger lower and middle band** — a pullback, not a crash.
3. **Quiet** — no single-day move over 3% in the last 2 sessions. There's no
   data feed for "affected by [some geopolitical event]" specifically, so an
   unusually large recent move (either direction) stands in as the closest
   computable proxy — combined with the existing Energy/Oil/Gas exclusions,
   which already remove the names most directly exposed to an oil-price
   shock.
4. **Fundamentally strong** — positive earnings or revenue growth, ROE > 15%,
   Debt/Equity < 100, and an analyst consensus that isn't Sell/Underperform.

Run it with `--strategy pullback`. This is a brand-new strategy with **no
backtest** behind it yet — treat its output as a starting watchlist to
research further, not a validated signal.

## Support Zone strategy (plain technical scan)

A minimal, literal technical scan with no fundamentals and no extra
conditions layered on top: RSI(14) daily between 30-45, AND close between
the Bollinger lower and middle band. Only this tool's standing liquidity
(≥ ₹20cr/day) and sector-exclusion rules are applied — nothing else. Run it
with `--strategy support-zone`. No backtest exists for this scan either.

## Fundamentals check (ad-hoc, no screen)

Check ROE, Debt/Equity, earnings/revenue growth, and analyst rating for an
explicit list of tickers — e.g. to annotate a shortlist that came from
another scan (like support-zone, which has no fundamentals filter of its
own). Uses the same bar as the pullback strategy, but reports every ticker
given, pass or fail, rather than filtering any out.

```bash
python -m stock_screener --strategy fundamentals --tickers INFY.NS,TCS.NS
```

## Support/resistance levels (ad-hoc, no screen)

Computes real reference levels for an explicit ticker list: 20/50/100/200-day
SMAs, recent swing lows (20/60/120/252-day), and the 52-week low/high.
`nearest_support` is the highest of these below today's close;
`nearest_resistance` is the lowest above it. These are standard technical
reference points computed from actual price history, not a promise that
price will hold or reverse there.

```bash
python -m stock_screener --strategy levels --tickers ADANIPORTS.NS
```

## Nifty 50 combined scan

Runs the same technical-zone classification and fundamentals check across
all 50 Nifty 50 constituents (no ticker list needed) and ranks them: stocks
sitting in the "pullback zone" (between the Bollinger lower and middle band
— a dip, not a crash, not overbought) with fundamentals fully clearing the
bar come first, sorted by RSI ascending within that group. Everything else
is still listed below for context. This is a new, untested combined view —
no backtest exists for it.

```bash
python -m stock_screener --strategy nifty50-scan
```

## Unfilled gap-down screener

Finds stocks that opened at least 2% below the prior day's close (a gap
down, often on news/results) within the last 60 sessions, and haven't since
closed back up to that pre-gap level. `pct_to_fill` shows how far the
current close is from filling it. Sorted by most recent gap first. A gap
being unfilled does **not** mean it's likely to fill — some gaps (especially
on genuine bad news) never do. No backtest exists for this pattern.

```bash
python -m stock_screener --strategy gap-fill
```

## Setup

```bash
pip install -r stock_screener/requirements.txt
```

## Usage

```bash
python -m stock_screener --capital 100000                 # default: bounce strategy
python -m stock_screener --strategy pullback               # quality pullback strategy
python -m stock_screener --strategy support-zone            # plain RSI 30-45 + BB zone scan
python -m stock_screener --strategy fundamentals --tickers TICKER1.NS,TICKER2.NS
python -m stock_screener --strategy levels --tickers TICKER1.NS,TICKER2.NS
python -m stock_screener --strategy nifty50-scan            # combined scan, all Nifty 50
python -m stock_screener --strategy gap-fill                # unfilled gap-down screener
```

Index constituent lists are always pulled fresh from niftyindices.com (they
change roughly every 6 months). If that site isn't reachable from your
network, download the three CSVs yourself the same day and pass:

```bash
python -m stock_screener --csv-dir /path/to/csvs
```

(expects `ind_nifty50list.csv`, `ind_niftynext50list.csv`,
`ind_nifty_midcap50list.csv` in that directory)

Results are printed to the console and saved as
`output/signals_<date>.csv` / `output/near_miss_<date>.csv`.
