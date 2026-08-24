"""One-off diagnostic on REAL data: sector/industry + today's % change for
the CDSL-profile candidate list (reversal_developing/reversal_confirmed
with high Bollinger Band position), to see which sectors are over-
represented (strong) vs. absent/weak among today's reversal candidates.
Not part of the package -- delete after use.
"""
import logging
logging.disable(logging.CRITICAL)

import pandas as pd

from stock_screener.screener import fetch_price_history, fetch_sector_industry

TICKERS = [
    "NTPCGREEN.NS", "BHEL.NS", "SUNDARMFIN.NS", "BHARTIARTL.NS", "ICICIGI.NS",
    "PATANJALI.NS", "APOLLOHOSP.NS", "TATACOMM.NS", "MARICO.NS", "BAJAJHFL.NS",
    "BANKBARODA.NS", "ABBOTINDIA.NS", "RVNL.NS", "TRENT.NS", "MARUTI.NS",
    "VBL.NS", "TATACAP.NS", "BALKRISIND.NS", "AIIL.NS", "DMART.NS", "CANBK.NS",
]

history = fetch_price_history(TICKERS)
print(f"Fetched history for {len(history)}/{len(TICKERS)} tickers\n")

rows = []
for ticker in TICKERS:
    df = history.get(ticker)
    info = fetch_sector_industry(ticker, 0.2)
    day_pct_chg = None
    if df is not None:
        close = df["Close"].dropna()
        if len(close) >= 2:
            day_pct_chg = float((close.iloc[-1] - close.iloc[-2]) / close.iloc[-2] * 100)
    rows.append({
        "ticker": ticker,
        "sector": info["sector"],
        "industry": info["industry"],
        "day_pct_chg": round(day_pct_chg, 2) if day_pct_chg is not None else None,
    })

rdf = pd.DataFrame(rows)
print(rdf.to_string(index=False))

print("\n=== By sector (count + avg today's % change within this candidate list) ===")
agg = rdf.groupby("sector").agg(count=("ticker", "count"), avg_day_pct_chg=("day_pct_chg", "mean")).sort_values("count", ascending=False)
print(agg.to_string())
