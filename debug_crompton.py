"""One-off diagnostic: dump the exact intermediate values the capitulation
screener used for CROMPTON.NS so a flagged rsi_divergence=False can be
checked against the raw price/RSI series. Not part of the package -- delete
after use.
"""
from stock_screener.screener import fetch_price_history
from stock_screener.capitulation_strategy import (
    _find_anchor, _find_swing_lows, MIN_GAP_BETWEEN_LOWS,
)
from stock_screener.indicators import rsi

history = fetch_price_history(["CROMPTON.NS", "RELIANCE.NS"])
df = history["CROMPTON.NS"].dropna(subset=["Close", "Open", "High", "Low", "Volume"])
close, open_, volume = df["Close"], df["Open"], df["Volume"]

idx = _find_anchor(close, open_, volume)
print("anchor idx:", idx, "date:", df.index[idx])
print("anchor close:", float(close.iloc[idx]), "anchor low:", float(df['Low'].iloc[idx]))

rsi_series = rsi(close, period=14)

print("\n--- last 20 days of Close / RSI up to and including the anchor ---")
window_start = max(0, idx - 19)
for i in range(window_start, idx + 1):
    print(df.index[i].date(), "close=%.2f" % close.iloc[i], "rsi=%.2f" % rsi_series.iloc[i])

swing_lows = _find_swing_lows(close)
print("\nall confirmed swing lows (close series):")
for i in swing_lows:
    print(" ", df.index[i].date(), "close=%.2f" % close.iloc[i], "rsi=%.2f" % rsi_series.iloc[i], "idx=", i)

prior_lows = [i for i in swing_lows if i <= idx - MIN_GAP_BETWEEN_LOWS]
print("\nprior_lows (candidates strictly before anchor by >=%d days):" % MIN_GAP_BETWEEN_LOWS)
for i in prior_lows:
    print(" ", df.index[i].date(), "close=%.2f" % close.iloc[i], "rsi=%.2f" % rsi_series.iloc[i], "idx=", i)

if prior_lows:
    prior_idx = max(prior_lows)
    print("\nchosen prior_idx:", df.index[prior_idx].date(), "idx=", prior_idx)
    print("prior close:", float(close.iloc[prior_idx]), "prior rsi:", float(rsi_series.iloc[prior_idx]))
    print("anchor close:", float(close.iloc[idx]), "anchor rsi:", float(rsi_series.iloc[idx]))
    print("price_lower_low:", float(close.iloc[idx]) < float(close.iloc[prior_idx]))
    print("rsi_higher_low:", float(rsi_series.iloc[idx]) > float(rsi_series.iloc[prior_idx]))
else:
    print("\nNo prior confirmed swing low found before the anchor -- rsi_divergence defaults False.")

print("\n--- last 15 days total (through today) for visual context ---")
for i in range(max(0, len(df) - 15), len(df)):
    print(df.index[i].date(), "close=%.2f" % close.iloc[i], "rsi=%.2f" % rsi_series.iloc[i])
