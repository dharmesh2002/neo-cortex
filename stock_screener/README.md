# NSE Stock Screener — Bollinger Band Bounce + RSI + Volume

Screens Nifty 50 + Nifty Next 50 + Nifty Midcap 50 (150 stocks) for a same-day
confluence of:

1. **Bollinger Band bounce** — low touches/dips below the lower 20-day ± 2σ
   band, close recovers above it, and closes higher than yesterday.
2. **RSI bounce** — RSI(14) dipped to ≤35 within the last 5 trading days and
   is now turning up.
3. **Volume confirmation** — today's volume exceeds the prior 20-day average.

Also requires 20-day average daily traded value ≥ ₹20 crore (liquidity), and
excludes Technology/Energy sector stocks and Airlines/Oil/Gas/Petroleum/
Chemicals/Paint industries.

For each signal it computes Entry (close), Stop-loss (Entry − 0.75×ATR14),
Target (Entry × 1.03), and position size (0.5% capital risk per trade, capped
by available capital). Stocks meeting exactly 2 of the 3 conditions are
reported separately as a near-miss watchlist, flagged with the missing
condition.

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
