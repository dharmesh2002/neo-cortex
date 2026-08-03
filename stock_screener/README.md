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

## Support Zone strategy backtest

Answers the question the live `support-zone` scan always leaves open ("no
backtest exists for this scan"): pulls ~2 years of daily history for the
150-stock universe, finds every day a stock freshly enters the zone (RSI(14)
between 30-45 AND close between the Bollinger lower/mid band -- a fresh
entry only, so a multi-day stay in the zone counts once), and simulates a
trade using the same entry/stop/target rule used elsewhere in this project
(entry at that day's close, stop at entry - 0.75x ATR14, target at
entry x 1.03, closed at whichever is hit first within 20 trading days).
Reports a real win rate and average R-multiple for this exact rule.

Caveats: uses the *current* 150-stock universe applied backward (not actual
historical index membership -- survivorship bias tilts results optimistic),
no transaction costs/slippage modeled, and if a single day's range touches
both the stop and target the stop is conservatively assumed to hit first
(daily bars can't show the real intraday order).

```bash
python -m stock_screener --strategy backtest-support-zone
```

## Support Zone strategy backtest (multi-timeframe + volume)

A variant of the plain support-zone backtest that adds three conditions on
top of the daily RSI 30-45 + Bollinger lower/mid band zone, to test whether
they improve the (roughly break-even, -0.030R) plain rule:

1. **Weekly RSI(14) > 50** and **Monthly RSI(14) > 50** -- the idea being a
   stock dipping into the daily zone while its higher-timeframe trend is
   still constructive is a healthy pullback within a strong trend, not a
   stock genuinely breaking down. Both are computed on resampled
   weekly/monthly closes and forward-filled onto the daily calendar with no
   lookahead into an in-progress week/month (each resampled label is that
   period's own last trading day, so a day still inside an unfinished
   week/month can only ever see the last *completed* period's value).
2. **Volume today > the prior 20-day average volume** -- a pickup in volume
   on the bounce day itself, meant to confirm real buying interest rather
   than a low-conviction drift back into the zone.

Pulls 5 years of history (to properly warm up weekly/monthly RSI, which each
need ~14 of their own periods before Wilder's smoothing stops returning
NaN) but only counts signals within the most recent 2 years, the same
window as the plain support-zone backtest, so the two are comparable.

```bash
python -m stock_screener --strategy backtest-support-zone-mtf
```

## Support Zone strategy backtest (fixed risk-reward)

Isolates one specific fix to the plain support-zone backtest's mediocre
result (-0.030R average): the stop-loss already scales with each stock's
own volatility (entry - 0.75x ATR14), but the target was a fixed +3% for
every stock regardless of volatility -- so a volatile stock could end up
with a stop nearly as wide as the target, giving poor payout math even on
a winning trade. This version makes the target scale the same way as the
stop: target = entry + 2x the stop distance, so every trade has the same
built-in 2:1 reward-to-risk ratio. Everything else (the zone definition,
the stop-loss itself, holding-period rules) is identical to the plain
backtest, so the two results isolate the effect of this one change.

```bash
python -m stock_screener --strategy backtest-support-zone-rr
```

## Bullish RSI divergence screener

Finds stocks where price made a lower swing low but RSI(14) made a higher (or
equal) low at the same time -- the classic reading is that downward momentum
is fading even though price is still falling, which is sometimes an early
sign a reversal is near. Requires: two distinct swing lows at least 5 trading
days apart within the last 90 sessions, the more recent one within the last
12 days, both lows' RSI at or below 50 (so it's a real dip, not noise near
the highs), price making a lower low while RSI makes a higher low. This is a
pattern-recognition heuristic, not a guarantee -- divergences can and do fail
to produce a reversal, and no backtest exists for this screen.

```bash
python -m stock_screener --strategy divergence
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
python -m stock_screener --strategy divergence               # bullish RSI divergence screener
python -m stock_screener --strategy backtest-support-zone    # ~2yr backtest of the support-zone rule
python -m stock_screener --strategy backtest-support-zone-mtf # + weekly/monthly RSI>50 + volume confirmation
python -m stock_screener --strategy backtest-support-zone-rr  # fixed 2:1 target-to-stop ratio
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
