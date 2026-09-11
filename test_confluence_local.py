"""Run confluence signal on a small hardcoded ticker list.
Usage (from repo root):
    python test_confluence_local.py
Requires: pip install yfinance pandas tabulate
"""
import logging
import pandas as pd
import yfinance as yf
from stock_screener.confluence_signal_strategy import evaluate_confluence_ticker

logging.basicConfig(level=logging.WARNING)

TICKERS = [
    "RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS", "ICICIBANK.NS",
    "KOTAKBANK.NS", "WIPRO.NS", "TATAMOTORS.NS", "SBIN.NS", "AXISBANK.NS",
    "ITC.NS", "LT.NS", "SUNPHARMA.NS", "MARUTI.NS", "BAJFINANCE.NS",
    "NTPC.NS", "POWERGRID.NS", "TITAN.NS", "ULTRACEMCO.NS", "ONGC.NS",
]

print(f"Downloading 18mo history for {len(TICKERS)} tickers...")
raw = yf.download(
    tickers=TICKERS, period="18mo", interval="1d",
    group_by="ticker", auto_adjust=False, threads=True, progress=False,
)

rows = []
for ticker in TICKERS:
    try:
        df = raw[ticker].dropna(how="all")
    except KeyError:
        continue
    result = evaluate_confluence_ticker(df)
    if result is None:
        continue
    result.ticker = ticker
    rows.append({
        "ticker":         ticker,
        "close":          round(result.close, 2),
        "sma200":         round(result.sma200, 2),
        "fib618":         round(result.fib618, 2),
        "h_support":      round(result.horizontal_support, 2),
        "rsi14":          round(result.rsi14, 2),
        "near_support":   result.near_support,
        "near_sma200":    result.near_sma200,
        "near_fib618":    result.near_fib618,
        "rsi_oversold":   result.rsi_oversold,
        "bull_engulf":    result.bullish_engulfing,
        "conditions_met": result.conditions_met,
        "signal":         result.is_signal,
        "missing":        ", ".join(result.missing_conditions) if not result.is_signal else "—",
    })

if not rows:
    print("No data returned — check your internet connection.")
else:
    df_out = pd.DataFrame(rows).sort_values("conditions_met", ascending=False)
    pd.set_option("display.max_columns", None)
    pd.set_option("display.width", 220)
    print(f"\nAll {len(df_out)} tickers evaluated (sorted by conditions_met):\n")
    print(df_out.to_string(index=False))

    signals   = df_out[df_out["signal"]]
    near_miss = df_out[df_out["conditions_met"] == 4]

    print(f"\n{'='*60}")
    print(f"FULL CONFLUENCE SIGNALS (5/5 conditions): {len(signals)}")
    print(signals[["ticker","close","rsi14","conditions_met"]].to_string(index=False)
          if not signals.empty else "  None today")

    print(f"\nNEAR-MISS (4/5 conditions): {len(near_miss)}")
    print(near_miss[["ticker","close","rsi14","missing"]].to_string(index=False)
          if not near_miss.empty else "  None today")
