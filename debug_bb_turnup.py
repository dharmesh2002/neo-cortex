"""One-off diagnostic on REAL data: stocks whose close is still below the
lower Bollinger Band (20,2) but today's candle is green (today's close >
yesterday's close) -- the earliest possible sign of a bounce attempt,
still happening below the band rather than already back inside it.
Not part of the package -- delete after use.
"""
import logging
logging.disable(logging.CRITICAL)

import pandas as pd

from stock_screener.screener import fetch_price_history, fetch_sector_industry
from stock_screener.universe import build_universe, is_excluded
from stock_screener.indicators import bollinger_bands, rsi

LIQUIDITY_THRESHOLD_INR = 20 * 1e7

universe = build_universe()
tickers = universe["Ticker"].tolist()
ticker_to_company = dict(zip(universe["Ticker"], universe.get("Company Name", universe["Symbol"])))

history = fetch_price_history(tickers)
print(f"Fetched history for {len(history)}/{len(tickers)} tickers\n")

rows = []
for ticker, df in history.items():
    df = df.dropna(subset=["Close", "Volume"])
    if len(df) < 30:
        continue
    close, volume = df["Close"], df["Volume"]

    avg_val = (close * volume).rolling(20).mean().iloc[-1]
    if pd.isna(avg_val) or avg_val < LIQUIDITY_THRESHOLD_INR:
        continue

    sma, upper, lower = bollinger_bands(close, window=20)
    r = rsi(close, period=14)
    if pd.isna(lower.iloc[-1]) or pd.isna(r.iloc[-1]) or len(close) < 2:
        continue

    close_today = float(close.iloc[-1])
    close_prev = float(close.iloc[-2])
    lower_today = float(lower.iloc[-1])
    sma_today = float(sma.iloc[-1])

    below_lower_band = close_today < lower_today
    turned_up_today = close_today > close_prev
    if not (below_lower_band and turned_up_today):
        continue

    day_pct_chg = (close_today - close_prev) / close_prev * 100
    pct_below_lower = (close_today - lower_today) / lower_today * 100

    rows.append({
        "ticker": ticker,
        "close": round(close_today, 2),
        "lower_band": round(lower_today, 2),
        "mid_band": round(sma_today, 2),
        "pct_below_lower_band": round(pct_below_lower, 2),
        "day_pct_chg": round(day_pct_chg, 2),
        "rsi_today": round(float(r.iloc[-1]), 1),
        "avg_daily_value_cr": round(avg_val / 1e7, 1),
    })

rdf = pd.DataFrame(rows)
print(f"{len(rdf)} tickers below lower Bollinger Band but up today\n")

if not rdf.empty:
    rdf = rdf.sort_values("day_pct_chg", ascending=False)
    sectors = {}
    for t in rdf["ticker"]:
        info = fetch_sector_industry(t, 0.2)
        sectors[t] = info
    rdf["sector"] = rdf["ticker"].map(lambda t: sectors[t]["sector"])
    rdf["industry"] = rdf["ticker"].map(lambda t: sectors[t]["industry"])
    rdf["company"] = rdf["ticker"].map(lambda t: ticker_to_company.get(t, t))
    rdf = rdf[~rdf.apply(lambda r: is_excluded(r["sector"], r["industry"]), axis=1)]

    cols = ["ticker", "company", "sector", "close", "lower_band", "pct_below_lower_band",
            "day_pct_chg", "rsi_today", "avg_daily_value_cr"]
    print(rdf[cols].to_string(index=False))
else:
    print("None found.")
