# NSE Stock Screener — Bollinger Band Bounce + RSI + Volume

Screens Nifty 50 + Nifty Next 50 + Nifty Midcap 50 + Nifty Midcap 150 +
Nifty Smallcap 100 (large/mid/small-cap coverage, duplicates across
overlapping indices removed) for a same-day confluence of:

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

## Screener names

Every mode below has a short name (its `--strategy` value) and a full
report title (what shows up as the GitHub issue title / markdown heading).
Quick reference:

| Name (`--strategy`) | Report title |
|---|---|
| `bounce` (default) | Stock Screener |
| `pullback` | Quality Pullback Screener |
| `support-zone` | Support Zone Screener |
| `fundamentals` | Fundamentals Check |
| `levels` | Support Levels |
| `nifty50-scan` | Nifty 50 Combined Scan |
| `gap-fill` | Unfilled Gap-Down Screener |
| `divergence` | Bullish RSI Divergence Screener |
| `backtest-support-zone` | Support Zone Strategy Backtest |
| `backtest-support-zone-mtf` | Support Zone Strategy Backtest (Multi-Timeframe + Volume) |
| `backtest-support-zone-rr` | Support Zone Strategy Backtest (Fixed Risk-Reward) |
| `bounce-fundamentals` | Bounce + Fundamentals Screener |
| `decline-reversal` | Decline-Reversal Near Support Screener |
| `backtest-decline-reversal` | Decline-Reversal Near Support Backtest |
| `buffett` | Warren Buffett Quality Screener |
| `buffett-relaxed` | Warren Buffett Quality Screener (Relaxed) |
| `breadth` | Market Breadth |
| `capitulation` | Capitulation Screener |
| `structure` | Peak/Valley Trend Structure Screener |

## Market Breadth (unfiltered baseline)

Every strategy above narrows the universe to a specific technical/fundamentals setup.
`breadth` deliberately does the opposite: no sector exclusions, no fundamentals gate, no
technical zone -- just advancers vs. decliners, average move by market-cap segment (Nifty
50 / Next 50 / Midcap 50 / Midcap 150 / Smallcap 100) and by Yahoo Finance sector, plus the
day's top 10 gainers and losers across the whole universe. Use it to answer "is today's
market actually moving, and where" independent of what any single screener is filtered to
show. Slower than most strategies here since it fetches sector data for every ticker with
price history, not just names that already passed another filter. Run it with `--strategy
breadth`.

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

### Reading bounce quality on a match

Every match also carries three read-only diagnostic columns — they don't
change which stocks make the list, they help judge how convincing a bounce
off support would be if/when one starts:

- **`close_position_pct`** — where today's close landed in today's
  high-low range. Close to 100% = closed near the day's high (buyers in
  control into the close); close to 0% = closed near the low (sellers
  still in control despite any intraday recovery). ≥65% counts as a
  strong close.
- **`volume_confirmed`** — today's volume vs. its trailing 20-day average.
  A move on below-average volume is a weaker signal than the same move on
  above-average volume.
- **`excess_return_pct`** / **`tailwind_risk`** — today's % change minus
  the average % change across the whole screened universe today. Positive
  means the stock is moving on its own strength; negative (`tailwind_risk
  = True`) means it's underperforming the broader tape even if its own
  candle looks fine — i.e. it's being carried by a market/sector-wide
  move rather than showing real relative strength.
- **`bounce_quality`** — tiers the three signals above: `strong` (all
  three agree), `moderate` (two), `developing` (one), `weak` (none).

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
screened universe, finds every day a stock freshly enters the zone (RSI(14)
between 30-45 AND close between the Bollinger lower/mid band -- a fresh
entry only, so a multi-day stay in the zone counts once), and simulates a
trade using the same entry/stop/target rule used elsewhere in this project
(entry at that day's close, stop at entry - 0.75x ATR14, target at
entry x 1.03, closed at whichever is hit first within 20 trading days).
Reports a real win rate and average R-multiple for this exact rule.

Caveats: uses the *current* universe applied backward (not actual
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

## Bounce + Fundamentals screener

Combines the price-action bounce *event* -- low touches/dips to the lower
Bollinger band, close recovers above it, and closes higher than yesterday --
with a loose RSI ceiling (RSI(14) < 45, not a fixed oversold floor), volume
confirmation (today's volume above the prior 20-day average), and the same
fundamentals bar as the pullback strategy (positive earnings/revenue
growth, ROE > 15%, Debt/Equity < 100 -- exempt for Financial Services,
analyst recommendation not Sell/Underperform).

This is deliberately built around the bounce *event* rather than a passive
"sitting in a zone" *state*: this project's backtests found the event-based
bounce condition was the one part of the original 3-condition rule with
positive expectancy (+0.1195R), while every passive state-based variant
tested (RSI 30-45 + between Bollinger bands, with and without multi-
timeframe/volume filters, with and without a fixed risk-reward target) came
back break-even-to-negative. That said, this *exact* combination (bounce
event + RSI<45 + volume + fundamentals) has not itself been backtested --
treat it as a new, unproven combination like every other new strategy in
this project until it's actually validated against history.

```bash
python -m stock_screener --strategy bounce-fundamentals
```

## Decline-Reversal near support screener

Finds stocks where the last 3 trading days each closed lower than the day
before (a genuine losing streak), followed by today's candle closing above
its own open (green) AND above yesterday's close (an actual reversal, not
just a smaller red candle) -- with today's close landing within 2% of a
real support level (the highest of the 20/50/100/200-day SMAs, the
20/60/120/252-day swing lows, or the Bollinger lower band, whichever sits
below today's close). Pure price-action pattern, no fundamentals filter --
only the standing liquidity and sector/industry exclusion rules apply.
Stocks with the same decline+reversal but sitting 2-5% above support
(instead of within 2%) show up separately in a near-miss watchlist.

```bash
python -m stock_screener --strategy decline-reversal
```

This is a new, untested strategy -- no backtest exists for it yet.

Every match also carries the same bounce-quality diagnostics as the pullback
strategy, renamed for this context: `close_position_pct` (did today's
reversal candle close strong, near its high, or weak, near its low?),
`volume_confirmed` (real participation vs. a thin print), and
`excess_return_pct` / `tailwind_risk` (is this stock genuinely bucking the
decline on its own, or just moving with a broader market recovery?),
rolled up into `reversal_quality` (strong/moderate/developing/weak). This is
the direct answer to "how do I know the sell-off is actually done, not a
dead-cat bounce."

## Decline-Reversal Near Support backtest

Backtests the exact rule behind the live `decline-reversal` strategy
against real historical data (not synthetic): 3 real trading days each
closing lower than the day before, followed by a real green reversal
candle, landing within 2% of a real, computed support level. Uses the same
entry/stop/target methodology as every other backtest in this project
(entry at the signal day's close, stop at entry - 0.75x ATR14, target at
entry x 1.03) so the resulting win rate/R-multiple is directly comparable
to the bounce rule (+0.1195R) and support-zone (-0.030R and its variants)
backtests already run.

```bash
python -m stock_screener --strategy backtest-decline-reversal
```

## Warren Buffett Quality Screener

The only strategy in this project with **no technical price trigger at
all** -- a pure business-quality + valuation snapshot, checking every
non-excluded stock in the universe against seven bars inspired by Warren
Buffett's own commonly-cited value-investing criteria:

1. **ROE > 15%** -- Buffett's own commonly-cited quality bar.
2. **Debt/Equity < 50** (exempt for Financial Services) -- stricter than
   the pullback strategy's <100, since Buffett strongly prefers businesses
   that don't lean on leverage.
3. **Both earnings growth AND revenue growth positive** -- stricter than
   the pullback strategy's either/or; a genuinely growing business, not
   just "not shrinking."
4. **Positive free cash flow** -- real cash generation, not just paper
   profit.
5. **Profit margin > 10%** -- a rough, computable proxy for pricing power
   / economic moat. Not a substitute for actually judging whether a moat
   is real, but at least consistent with one.
6. **Trailing P/E under 25** -- the commonly-cited "margin of safety"
   valuation proxy.
7. **Analyst recommendation not Sell/Underperform.**

All seven must pass. Since there's no technical pre-filter to cheaply
narrow the field first, every non-excluded ticker in the (now ~350-stock)
universe needs its own fundamentals lookup -- expect this to take longer
to run than the technical-gate-first strategies. No backtest exists for
this combination; it's a research starting point, not a trading signal.

```bash
python -m stock_screener --strategy buffett
```

**Relaxed variant**: the strict version above can plausibly return zero
matches on any given day -- a P/E under 25 with both earnings and revenue
growing at once is a genuinely rare combination, and returning nothing is
a real, meaningful result (it says something about the market, not a bug).
`--strategy buffett-relaxed` keeps the ROE, debt, free cash flow, margin,
and analyst-rating bars unchanged but raises the P/E ceiling to 40x and
relaxes growth to *either* earnings or revenue positive (matching the
pullback strategy's own either/or bar), to see what shows up once the two
strictest, most-likely-to-zero-out dimensions are loosened.

```bash
python -m stock_screener --strategy buffett-relaxed
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

## Capitulation screener

Looks for the classic "selling climax" sequence rather than any single
indicator: a **capitulation candle** -- a red candle closing down at least
5% on at least 2x its trailing 20-day average volume ("sellers throwing
everything at once") -- within the last 20 trading days, with price not
having closed more than 3% below that candle's own low since (it actually
**stabilized** instead of continuing to break down). A ticker either had a
candle like this recently or it didn't; this is a hard gate, not a scored
condition, and nothing without one shows up at all.

On top of the gate, seven independent signals -- grouped the same way this
pattern is usually talked about -- are scored 0-7 to judge how convincingly
selling pressure is actually fading:

**Price action**
1. **Lower-wick rejections** -- at least 2 days since the capitulation
   candle where the lower wick took up a large share of the day's range and
   it still closed in the upper half (price kept probing lower intraday but
   buyers defended the level).
2. **Higher lows forming** -- each confirmed swing-low close since the
   capitulation candle is higher than the one before it (starting from the
   candle's own close) -- each dip shallower, even if price is still down
   overall.

**Volume**
3. **Selling volume shrinking** -- every down day since the capitulation
   candle had less volume than the down day before it (a ticker with zero
   down days since then counts as trivially true -- no renewed selling at
   all to shrink from).
4. **Volume absorption** -- today's volume is back below its trailing
   20-day average, i.e. the panic has cooled off from the capitulation
   spike (supply getting absorbed without needing a big print to hold the
   level).

**Indicators**
5. **RSI(14) bullish divergence at the low** -- price made a lower low at
   the capitulation candle than at the last confirmed swing low before it,
   but RSI didn't -- selling momentum was already fading even at the worst
   print.
6. **MACD histogram shrinking** -- the histogram is still negative but
   smaller in magnitude over the last 3 days than the 3 days before that --
   bearish momentum fading, not yet flipped positive.
7. **Lower Bollinger Band walk stopping** -- price was closing at/below the
   lower band on multiple days into the capitulation candle (a "walk" down
   the band), and hasn't closed there since.

`price_action_score`/`volume_score`/`indicator_score` are out of 2/2/3;
`total_score` is their sum out of 7, and `capitulation_quality` tiers it:
strong (>=6), moderate (>=4), developing (>=2). Tickers scoring 4+ are
reported as matches; 2-3 as a near-miss watchlist (same gate, fewer
confirming signals); below 2 (or no qualifying candle at all) don't appear.
Only this project's standing liquidity (>= Rs 20cr/day) and sector/industry
exclusion rules apply on top -- no fundamentals filter.

This is a new, untested pattern -- no backtest exists for it yet. Treat its
output as a starting watchlist for further research, not a trading signal.

```bash
python -m stock_screener --strategy capitulation
```

## Peak/Valley Trend Structure screener

The purest screener in this project: no indicators at all -- no RSI, no
MACD, no Bollinger Bands, no volume. Just peaks (swing highs) and valleys
(swing lows) on the actual price chart, read the way the classic
"rising stairs / falling stairs" framework does:

- **Uptrend** -- each peak higher than the last (Higher High) AND each
  valley higher than the last (Higher Low). Buyers in control.
- **Downtrend** -- each peak lower than the last (Lower High) AND each
  valley lower than the last (Lower Low). Sellers in control.
- **`reversal_developing`** (the signal to watch) -- peaks are still
  making a Lower High, but the most recent valley just broke the streak
  of Lower Lows and came in *higher* than the one before it. This is
  literally "the moment a stock stops making a lower low" -- the first
  hint a downtrend is weakening, before it's confirmed.
- **`reversal_confirmed`** -- the leg right before this one was still a
  Lower High (a genuine downtrend was in place), the valley in between
  turned into a Higher Low, and now the newest peak has also pushed above
  the previous peak (Higher High) -- both conditions of an uptrend are
  now met for the first time.
- **`dead_cat_bounce`** (a warning, not a buy signal) -- a valley had
  turned into a Higher Low (a bounce attempt) but the very next valley
  broke back down into a Lower Low while peaks are still Lower Highs --
  the bounce failed and the downtrend has resumed. This is the "dead cat"
  case: a bounce that doesn't hold.

Swing points are found with a simple fractal method on the real daily
High (for peaks) and Low (for valleys): a bar counts as a peak/valley if
it's the highest/lowest within 3 trading days on each side, with
same-type runs merged down to their single most extreme point so peaks
and valleys strictly alternate over time. Because confirming a swing
needs 3 days on each side, the very latest few trading days can never yet
form a confirmed point -- an inherent lag of any swing-based method, not
a bug. Structure older than 15 trading days isn't reported as
"developing" right now, to keep results current. Only this project's
standing liquidity (>= Rs 20cr/day) and sector/industry exclusion rules
apply on top -- no fundamentals filter.

`reversal_developing` and `reversal_confirmed` are reported as matches
(ranked confirmed-first); `dead_cat_bounce` gets its own watchlist. This
is a new, untested pattern -- no backtest exists for it yet. Not a
substitute for looking at the actual chart.

```bash
python -m stock_screener --strategy structure
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
python -m stock_screener --strategy bounce-fundamentals       # bounce event + RSI<45 + volume + fundamentals
python -m stock_screener --strategy decline-reversal          # 3-day decline + green reversal near support
python -m stock_screener --strategy backtest-decline-reversal # ~2yr real-data backtest of that rule
python -m stock_screener --strategy buffett                   # Warren Buffett-style quality/value screener
python -m stock_screener --strategy buffett-relaxed            # same bar, P/E<40 + either growth line positive
python -m stock_screener --strategy capitulation               # selling-climax gate + 7 scored exhaustion signals
python -m stock_screener --strategy structure                  # pure peak/valley reversal structure, no indicators
```

Index constituent lists are always pulled fresh from niftyindices.com (they
change roughly every 6 months). If that site isn't reachable from your
network, download the three CSVs yourself the same day and pass:

```bash
python -m stock_screener --csv-dir /path/to/csvs
```

(expects `ind_nifty50list.csv`, `ind_niftynext50list.csv`,
`ind_nifty_midcap50list.csv`, `ind_niftymidcap150list.csv`,
`ind_niftysmallcap100list.csv` in that directory)

Results are printed to the console and saved as
`output/signals_<date>.csv` / `output/near_miss_<date>.csv`.
