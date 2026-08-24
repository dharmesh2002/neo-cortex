"""One-off diagnostic on REAL data: checks BSE.NS (BSE Ltd, the stock
exchange company) for bullish RSI divergence using the project's own
find_bullish_divergence() function, AND dumps the full raw swing-low
sequence (price + RSI at each detected local low) so a near-miss is
visible too, not just a strict pass/fail. Not part of the package --
delete after use.
"""
import logging
logging.disable(logging.CRITICAL)

from stock_screener.screener import fetch_price_history
from stock_screener.indicators import rsi
from stock_screener.divergence_strategy import find_bullish_divergence, _find_swing_lows

# Pad with a second ticker -- fetch_price_history's single-ticker fast path
# returns non-flat columns against the current yfinance version.
history = fetch_price_history(["BSE.NS", "RELIANCE.NS"])
print(f"Fetched history for {len(history)}/2 tickers\n")

df = history.get("BSE.NS")
if df is None:
    print("BSE.NS: no data fetched.")
else:
    df = df.dropna(subset=["Close", "Volume"])
    close = df["Close"]
    r = rsi(close, period=14)

    print(f"BSE.NS: {len(df)} rows, last close {close.iloc[-1]:.2f}, RSI today {r.iloc[-1]:.1f}\n")

    cand = find_bullish_divergence(df)
    if cand:
        print("=== STRICT bullish divergence MATCH ===")
        print(f"  low1: price={cand.low1_price:.2f} rsi={cand.low1_rsi:.1f}")
        print(f"  low2: price={cand.low2_price:.2f} rsi={cand.low2_rsi:.1f} (days_since={cand.days_since_low2})")
        print(f"  price change low1->low2: {cand.price_change_pct:+.2f}%   rsi change: {cand.rsi_change:+.1f}")
    else:
        print("No STRICT match (fails one of: RSI<50 at both lows, price lower low + RSI higher low, "
              "recency <=12 days, liquidity, or <2 swing lows found).")

    print("\n=== All detected swing lows in the last 90 trading days (price + RSI) ===")
    n = len(close)
    lookback_start = max(0, n - 90)
    recent_close = close.iloc[lookback_start:]
    recent_rsi = r.iloc[lookback_start:]
    recent_dates = df.index[lookback_start:]
    swing_positions = sorted(_find_swing_lows(recent_close))
    for pos in swing_positions:
        date = recent_dates[pos].date()
        days_ago = (len(recent_close) - 1) - pos
        print(f"  {date}  price={recent_close.iloc[pos]:.2f}  rsi={recent_rsi.iloc[pos]:.1f}  ({days_ago} days ago)")

    print(f"\nAvg daily traded value (20d): Rs {((close * df['Volume']).rolling(20).mean().iloc[-1]) / 1e7:.1f} cr")
