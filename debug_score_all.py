"""One-off diagnostic: run the capitulation screener's scoring (evaluate_
ticker) against an explicit ticker list, bypassing the normal near-miss
threshold so every ticker's real score is shown -- including tickers that
never had a qualifying capitulation candle at all (the gate fails and
evaluate_ticker returns None). Ticker list via sys.argv[1], comma-
separated. Not part of the package -- delete after use.
"""
import sys

from stock_screener.screener import fetch_price_history
from stock_screener.capitulation_strategy import evaluate_ticker

tickers = sys.argv[1].split(",") if len(sys.argv) > 1 else []
history = fetch_price_history(tickers)
print(f"Fetched history for {len(history)}/{len(tickers)} tickers\n")

for ticker in tickers:
    df = history.get(ticker)
    if df is None:
        print(f"{ticker}: no data")
        continue
    cand = evaluate_ticker(df)
    if cand is None:
        print(f"{ticker}: NO qualifying capitulation candle in the last 20 trading days -- gate fails, not scored")
        continue
    signals = {
        "lower_wick_rejection": cand.lower_wick_rejection,
        "higher_lows": cand.higher_lows,
        "selling_volume_shrinking": cand.selling_volume_shrinking,
        "volume_absorption": cand.volume_absorption,
        "volume_pickup_on_rally": cand.volume_pickup_on_rally,
        "rsi_divergence": cand.rsi_divergence,
        "macd_histogram_shrinking": cand.macd_histogram_shrinking,
        "bb_walk_stopped": cand.bb_walk_stopped,
    }
    passed = [k for k, v in signals.items() if v]
    print(f"{ticker}: {cand.total_score}/8 ({cand.capitulation_quality}) -- anchor {cand.anchor_date}, "
          f"passed: {', '.join(passed) if passed else 'none'}")
