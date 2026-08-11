"""One-off diagnostic: dump the FULL peak/valley zigzag sequence for
JSWSTEEL.NS (not just the last 2 of each, like the live report shows) so a
reversal_confirmed classification can be checked against the real recent
chart -- specifically, how big (or small) the pullback was that made the
July 10 peak count as a "lower high" in the first place. Not part of the
package -- delete after use.
"""
from stock_screener.screener import fetch_price_history
from stock_screener.trend_structure_strategy import _build_zigzag, _classify

history = fetch_price_history(["JSWSTEEL.NS", "RELIANCE.NS"])
df = history["JSWSTEEL.NS"].dropna(subset=["Close", "High", "Low", "Volume"])
high, low, close = df["High"], df["Low"], df["Close"]

zigzag = _build_zigzag(high, low)
print("Full zigzag sequence (all confirmed peaks/valleys):")
for idx, kind, price in zigzag:
    print(f"  {df.index[idx].date()}  {kind:7s}  {price:.2f}")

print("\nMost recent close:", float(close.iloc[-1]), df.index[-1].date())

result = _classify(zigzag)
print("\nClassification result:")
print(result)
