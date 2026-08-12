"""One-off diagnostic: dump GODFRYPHLP.NS's daily Close/Volume since its
capitulation anchor candle, to identify exactly which day triggered
volume_pickup_on_rally=True and what price has done since. Not part of the
package -- delete after use.
"""
import pandas as pd

from stock_screener.screener import fetch_price_history
from stock_screener.capitulation_strategy import _find_anchor

history = fetch_price_history(["GODFRYPHLP.NS", "RELIANCE.NS"])
df = history["GODFRYPHLP.NS"].dropna(subset=["Close", "Open", "High", "Low", "Volume"])
close, open_, volume = df["Close"], df["Open"], df["Volume"]

idx = _find_anchor(close, open_, volume)
print("anchor idx:", idx, "date:", df.index[idx].date(), "close:", float(close.iloc[idx]))

avg_vol_20d = volume.shift(1).rolling(20).mean()

print("\nDay-by-day since the anchor:")
for i in range(idx, len(df)):
    up_day = close.iloc[i] > close.iloc[i - 1]
    vol_above_avg = pd.isna(avg_vol_20d.iloc[i]) is False and volume.iloc[i] > avg_vol_20d.iloc[i]
    marker = ""
    if up_day and vol_above_avg:
        marker = "  <-- volume-backed rally day"
    print(f"  {df.index[i].date()}  close={close.iloc[i]:.2f}  "
          f"vol={volume.iloc[i]:,.0f}  20d_avg={avg_vol_20d.iloc[i]:,.0f}  "
          f"{'UP' if up_day else 'DOWN'}{marker}")
