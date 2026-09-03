"""One-off diagnostic on REAL data: ranks the universe by how often a
stock actually moves >=1% in a single day, plus ATR14 as % of price, to
answer "which liquid stock is volatile enough to plausibly give a 1%
day." Not part of the package -- delete after use.
"""
import logging
logging.disable(logging.CRITICAL)

import pandas as pd

from stock_screener.screener import fetch_price_history, fetch_sector_industry
from stock_screener.universe import build_universe, is_excluded
from stock_screener.indicators import atr

LIQUIDITY_THRESHOLD_INR = 20 * 1e7
LOOKBACK_DAYS = 20

universe = build_universe()
tickers = universe["Ticker"].tolist()
ticker_to_company = dict(zip(universe["Ticker"], universe.get("Company Name", universe["Symbol"])))

history = fetch_price_history(tickers)
print(f"Fetched history for {len(history)}/{len(tickers)} tickers\n")

rows = []
for ticker, df in history.items():
    df = df.dropna(subset=["Close", "High", "Low", "Volume"])
    if len(df) < 30:
        continue
    close, high, low, volume = df["Close"], df["High"], df["Low"], df["Volume"]

    avg_val = (close * volume).rolling(20).mean().iloc[-1]
    if pd.isna(avg_val) or avg_val < LIQUIDITY_THRESHOLD_INR:
        continue

    atr14 = atr(high, low, close, period=14)
    if pd.isna(atr14.iloc[-1]):
        continue
    atr_pct = float(atr14.iloc[-1] / close.iloc[-1] * 100)

    daily_pct_chg = close.pct_change().iloc[-LOOKBACK_DAYS:] * 100
    avg_abs_move = float(daily_pct_chg.abs().mean())
    pct_days_over_1pct = float((daily_pct_chg.abs() >= 1.0).mean() * 100)
    today_pct_chg = float(daily_pct_chg.iloc[-1])

    rows.append({
        "ticker": ticker,
        "close": round(float(close.iloc[-1]), 2),
        "atr_pct": round(atr_pct, 2),
        "avg_abs_daily_move_pct": round(avg_abs_move, 2),
        "pct_days_moved_1pct_plus": round(pct_days_over_1pct, 1),
        "today_pct_chg": round(today_pct_chg, 2),
        "avg_daily_value_cr": round(avg_val / 1e7, 1),
    })

rdf = pd.DataFrame(rows)
rdf = rdf.sort_values("pct_days_moved_1pct_plus", ascending=False)

# Only fetch sector/industry (slow) for the top 25 already-narrowed candidates
top = rdf.head(25).copy()
sectors = {}
for t in top["ticker"]:
    info = fetch_sector_industry(t, 0.2)
    sectors[t] = info
top["sector"] = top["ticker"].map(lambda t: sectors[t]["sector"])
top["industry"] = top["ticker"].map(lambda t: sectors[t]["industry"])
top["company"] = top["ticker"].map(lambda t: ticker_to_company.get(t, t))
top = top[~top.apply(lambda r: is_excluded(r["sector"], r["industry"]), axis=1)]

cols = ["ticker", "company", "sector", "close", "atr_pct", "avg_abs_daily_move_pct",
        "pct_days_moved_1pct_plus", "today_pct_chg", "avg_daily_value_cr"]
print(f"Top 25 by frequency of >=1% daily moves (last {LOOKBACK_DAYS} sessions), liquid names only:\n")
print(top[cols].to_string(index=False))
