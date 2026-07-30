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

## Setup

```bash
pip install -r stock_screener/requirements.txt
```

## Usage

```bash
python -m stock_screener --capital 100000
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
