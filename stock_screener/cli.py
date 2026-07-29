"""Command-line entry point for the NSE Bollinger/RSI/Volume screener."""

import argparse
import logging
import os
from datetime import date

import pandas as pd

from .screener import run_screen

logger = logging.getLogger(__name__)


def _format_signals(signals: list) -> pd.DataFrame:
    if not signals:
        return pd.DataFrame()
    df = pd.DataFrame(signals)
    df = df[[
        "ticker", "company", "sector", "industry", "close", "atr14",
        "avg_daily_value_cr", "entry", "stop_loss", "target", "shares",
        "capital_deployed", "risk_amount",
    ]]
    for col in ["close", "atr14", "avg_daily_value_cr", "entry", "stop_loss",
                "target", "capital_deployed", "risk_amount"]:
        df[col] = df[col].round(2)
    return df


def _format_near_miss(near_miss: list) -> pd.DataFrame:
    if not near_miss:
        return pd.DataFrame()
    df = pd.DataFrame(near_miss)
    df = df[[
        "ticker", "company", "sector", "industry", "close", "missing",
        "rsi_today", "rsi_min_5d", "avg_daily_value_cr",
    ]]
    for col in ["close", "rsi_today", "rsi_min_5d", "avg_daily_value_cr"]:
        df[col] = df[col].round(2)
    return df


def main():
    parser = argparse.ArgumentParser(
        description="NSE screener: Bollinger Band bounce + RSI bounce + volume confirmation "
                    "over Nifty 50 + Nifty Next 50 + Nifty Midcap 50."
    )
    parser.add_argument("--capital", type=float, default=100_000.0,
                        help="Trading capital in INR, used for position sizing (default: 100000).")
    parser.add_argument("--csv-dir", type=str, default=None,
                        help="Directory with freshly downloaded (same-day) index constituent CSVs, "
                             "used instead of hitting niftyindices.com directly.")
    parser.add_argument("--output-dir", type=str, default="output",
                        help="Directory to write signals/near-miss CSVs into (default: ./output).")
    parser.add_argument("--info-sleep", type=float, default=0.3,
                        help="Seconds to sleep between yfinance sector/industry lookups "
                             "(default: 0.3, to be gentle on rate limits).")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable debug logging.")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    result = run_screen(capital=args.capital, csv_dir=args.csv_dir, info_sleep_seconds=args.info_sleep)

    signals_df = _format_signals(result["signals"])
    near_miss_df = _format_near_miss(result["near_miss"])

    print(f"\nUniverse: {result['universe_size']} tickers "
          f"(price history fetched for {result['history_fetched']})\n")

    print(f"=== BUY SIGNALS ({len(signals_df)}) ===")
    print(signals_df.to_string(index=False) if not signals_df.empty else "No signals today.")

    print(f"\n=== NEAR-MISS WATCHLIST ({len(near_miss_df)}) ===")
    print(near_miss_df.to_string(index=False) if not near_miss_df.empty else "No near-misses today.")

    os.makedirs(args.output_dir, exist_ok=True)
    today = date.today().isoformat()
    signals_path = os.path.join(args.output_dir, f"signals_{today}.csv")
    near_miss_path = os.path.join(args.output_dir, f"near_miss_{today}.csv")
    signals_df.to_csv(signals_path, index=False)
    near_miss_df.to_csv(near_miss_path, index=False)
    print(f"\nSaved: {signals_path}")
    print(f"Saved: {near_miss_path}")


if __name__ == "__main__":
    main()
