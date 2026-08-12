"""One-off diagnostic: for an explicit ticker list (passed as sys.argv[1],
comma-separated), fetch real price history and filter to only those
currently AT OR BELOW their 20-day SMA (middle Bollinger Band) -- i.e.
exclude anything that's already run up past the mid band. Prints close,
SMA20, band position, and RSI for context. Not part of the package --
delete after use.
"""
import sys

import pandas as pd

from stock_screener.screener import fetch_price_history
from stock_screener.indicators import bollinger_bands, rsi

tickers = sys.argv[1].split(",") if len(sys.argv) > 1 else []
history = fetch_price_history(tickers)
print(f"Fetched history for {len(history)}/{len(tickers)} tickers\n")

rows = []
for ticker, df in history.items():
    df = df.dropna(subset=["Close", "High", "Low", "Volume"])
    if len(df) < 30:
        continue
    close = df["Close"]
    sma, upper, lower = bollinger_bands(close, window=20)
    r = rsi(close, period=14)
    if pd.isna(sma.iloc[-1]):
        continue
    close_today = float(close.iloc[-1])
    sma_today = float(sma.iloc[-1])
    lower_today = float(lower.iloc[-1])
    band_position_pct = (
        (close_today - lower_today) / (sma_today - lower_today) * 100
        if sma_today != lower_today else 50.0
    )
    rows.append({
        "ticker": ticker,
        "close": round(close_today, 2),
        "sma_20_mid_band": round(sma_today, 2),
        "below_mid_band": close_today <= sma_today,
        "pct_vs_mid_band": round((close_today - sma_today) / sma_today * 100, 2),
        "band_position_pct": round(band_position_pct, 1),
        "rsi": round(float(r.iloc[-1]), 1) if pd.notna(r.iloc[-1]) else None,
    })

rdf = pd.DataFrame(rows).sort_values("pct_vs_mid_band")
print("=== FULL LIST (sorted by distance from mid band) ===")
print(rdf.to_string(index=False))

below = rdf[rdf["below_mid_band"]]
above = rdf[~rdf["below_mid_band"]]
print(f"\n{len(below)} at/below mid band, {len(above)} above mid band (excluded)")
print("\n=== EXCLUDED (above mid band) ===")
print(above[["ticker", "close", "sma_20_mid_band", "pct_vs_mid_band"]].to_string(index=False))
