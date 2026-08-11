"""One-off diagnostic: dump the FULL peak/valley zigzag sequence (not just
the last 2 of each, like the live report shows) plus RSI context for an
explicit ticker, so a structure classification can be checked against the
real recent chart. Ticker via sys.argv[1], defaults to JSWSTEEL.NS. Not
part of the package -- delete after use.
"""
import sys

from stock_screener.screener import fetch_price_history
from stock_screener.trend_structure_strategy import _build_zigzag, _classify
from stock_screener.indicators import rsi

ticker = sys.argv[1] if len(sys.argv) > 1 else "JSWSTEEL.NS"
pad_ticker = "RELIANCE.NS" if ticker != "RELIANCE.NS" else "TCS.NS"

history = fetch_price_history([ticker, pad_ticker])
df = history[ticker].dropna(subset=["Close", "High", "Low", "Volume"])
high, low, close, volume = df["High"], df["Low"], df["Close"], df["Volume"]
rsi_series = rsi(close, period=14)

zigzag = _build_zigzag(high, low)
print(f"Full zigzag sequence for {ticker} (all confirmed peaks/valleys):")
for idx, kind, price in zigzag:
    print(f"  {df.index[idx].date()}  {kind:7s}  {price:.2f}  rsi={rsi_series.iloc[idx]:.2f}")

print("\nMost recent close:", float(close.iloc[-1]), df.index[-1].date(),
      "rsi=%.2f" % rsi_series.iloc[-1])

avg_vol_20d = volume.rolling(20).mean()
print("\nLast 10 days volume vs 20d avg:")
for i in range(max(0, len(df) - 10), len(df)):
    print(f"  {df.index[i].date()}  vol={volume.iloc[i]:,.0f}  20d_avg={avg_vol_20d.iloc[i]:,.0f}")

result = _classify(zigzag)
print("\nClassification result:")
print(result)
