"""One-off diagnostic on REAL data (not synthetic): scans the live universe
for stocks currently sitting between the lower and middle Bollinger Band
(the classic pullback zone) with RSI(14) < 55, then cross-references each
one against the capitulation screener (was there a real sell-off/anchor
candle, has it stabilized) and the structure screener (has price actually
formed a higher low / higher high yet) to separate:

  - "still completing" -- near the lower band, no reversal structure yet
  - "strong reversal already showing" -- capitulation score >=3 and/or
    structure says reversal_developing/reversal_confirmed

Re-run of the same check that classified CDSL as "Developing" earlier
(reversal_developing structure, high band position). Not part of the
package -- delete after use.
"""
import logging
logging.disable(logging.CRITICAL)

import pandas as pd

from stock_screener.screener import fetch_price_history, fetch_sector_industry
from stock_screener.universe import build_universe, is_excluded
from stock_screener.indicators import bollinger_bands, rsi
from stock_screener.capitulation_strategy import evaluate_ticker as eval_capitulation
from stock_screener.trend_structure_strategy import evaluate_ticker as eval_structure

BB_WINDOW = 20
RSI_PERIOD = 14
RSI_CEILING = 55
LIQUIDITY_THRESHOLD_INR = 20 * 1e7

universe = build_universe()
tickers = universe["Ticker"].tolist()
ticker_to_company = dict(zip(universe["Ticker"], universe.get("Company Name", universe["Symbol"])))

history = fetch_price_history(tickers)
print(f"Fetched history for {len(history)}/{len(tickers)} tickers\n")

rows = []
for ticker, df in history.items():
    df = df.dropna(subset=["Close", "High", "Low", "Volume"])
    if len(df) < 90:
        continue
    close, volume = df["Close"], df["Volume"]
    avg_val = (close * volume).rolling(20).mean().iloc[-1]
    if pd.isna(avg_val) or avg_val < LIQUIDITY_THRESHOLD_INR:
        continue

    sma, upper, lower = bollinger_bands(close, window=BB_WINDOW)
    r = rsi(close, period=RSI_PERIOD)
    if pd.isna(sma.iloc[-1]) or pd.isna(lower.iloc[-1]) or pd.isna(r.iloc[-1]):
        continue

    close_today = float(close.iloc[-1])
    sma_today = float(sma.iloc[-1])
    lower_today = float(lower.iloc[-1])
    rsi_today = float(r.iloc[-1])

    in_zone = lower_today <= close_today <= sma_today
    if not (in_zone and rsi_today < RSI_CEILING):
        continue

    band_position_pct = (
        (close_today - lower_today) / (sma_today - lower_today) * 100
        if sma_today != lower_today else 50.0
    )

    cap = eval_capitulation(df)
    struct = eval_structure(df)

    rows.append({
        "ticker": ticker,
        "close": close_today,
        "rsi": round(rsi_today, 1),
        "bb_lower": round(lower_today, 2),
        "bb_mid": round(sma_today, 2),
        "band_position_pct": round(band_position_pct, 1),
        "cap_quality": cap.capitulation_quality if cap else None,
        "cap_score": cap.total_score if cap else None,
        "days_since_anchor": cap.days_since_anchor if cap else None,
        "structure_stage": struct.stage if struct else None,
        "avg_daily_value_cr": round(avg_val / 1e7, 1),
    })

rdf = pd.DataFrame(rows)
print(f"{len(rdf)} tickers between lower/mid Bollinger band with RSI < {RSI_CEILING}\n")

# Only fetch sector/industry (slow) for this already-narrowed candidate set
sectors = {}
for t in rdf["ticker"]:
    info = fetch_sector_industry(t, 0.2)
    sectors[t] = info
rdf["sector"] = rdf["ticker"].map(lambda t: sectors[t]["sector"])
rdf["industry"] = rdf["ticker"].map(lambda t: sectors[t]["industry"])
rdf["company"] = rdf["ticker"].map(lambda t: ticker_to_company.get(t, t))
rdf = rdf[~rdf.apply(lambda r: is_excluded(r["sector"], r["industry"]), axis=1)]

strong = rdf[
    rdf["structure_stage"].isin(["reversal_developing", "reversal_confirmed"])
    | (rdf["cap_score"].fillna(0) >= 3)
].sort_values(["structure_stage", "cap_score"], ascending=[True, False], na_position="last")

verge = rdf[
    (rdf["band_position_pct"] <= 30)
    & ~rdf["ticker"].isin(strong["ticker"])
].sort_values("band_position_pct")

cols = ["ticker", "company", "close", "rsi", "band_position_pct", "cap_quality",
        "cap_score", "days_since_anchor", "structure_stage", "avg_daily_value_cr"]

print("=== STRONG REVERSAL ALREADY SHOWING (capitulation score>=3 or structure reversal) ===")
print(strong[cols].to_string(index=False) if not strong.empty else "None found.")

print("\n=== SELL-OFF STILL COMPLETING (near lower band, no reversal structure yet) ===")
print(verge[cols].to_string(index=False) if not verge.empty else "None found.")
