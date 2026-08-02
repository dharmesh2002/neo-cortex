"""Command-line entry point for the NSE Bollinger/RSI/Volume screener."""

import argparse
import logging
import os
from datetime import date

import pandas as pd

from .pullback_strategy import run_pullback_screen
from .screener import run_screen
from .support_zone_strategy import run_support_zone_screen

logger = logging.getLogger(__name__)


def _format_signals(signals: list) -> pd.DataFrame:
    if not signals:
        return pd.DataFrame()
    df = pd.DataFrame(signals)
    df = df[[
        "ticker", "company", "sector", "industry", "close", "pct_change",
        "excess_return_pct", "atr14", "avg_daily_value_cr", "entry",
        "stop_loss", "target", "shares", "capital_deployed", "risk_amount",
    ]]
    df = df.rename(columns={
        "pct_change": "day_pct_chg",
        "excess_return_pct": "vs_universe_pct",
    })
    for col in ["close", "day_pct_chg", "vs_universe_pct", "atr14", "avg_daily_value_cr",
                "entry", "stop_loss", "target", "capital_deployed", "risk_amount"]:
        df[col] = df[col].round(2)
    return df


def _format_near_miss(near_miss: list) -> pd.DataFrame:
    if not near_miss:
        return pd.DataFrame()
    df = pd.DataFrame(near_miss)
    df = df[[
        "ticker", "company", "sector", "industry", "close", "missing",
        "rsi_today", "rsi_min_5d", "pct_change", "excess_return_pct",
        "avg_daily_value_cr",
    ]]
    df = df.rename(columns={
        "pct_change": "day_pct_chg",
        "excess_return_pct": "vs_universe_pct",
    })
    for col in ["close", "rsi_today", "rsi_min_5d", "day_pct_chg", "vs_universe_pct",
                "avg_daily_value_cr"]:
        df[col] = df[col].round(2)
    return df


def _build_markdown_report(signals_df: pd.DataFrame, near_miss_df: pd.DataFrame,
                            universe_size: int, history_fetched: int,
                            universe_avg_pct_change: float) -> str:
    today = date.today().isoformat()
    lines = [
        f"# Stock Screener — {today}",
        "",
        f"Universe: {universe_size} tickers (price history fetched for {history_fetched}). "
        f"Universe average day change: {universe_avg_pct_change:.2f}% "
        "(the tailwind benchmark `vs_universe_pct` is measured against).",
        "",
        f"## Buy signals ({len(signals_df)})",
        "",
    ]
    if signals_df.empty:
        lines.append("No signals today.")
    else:
        lines.append(signals_df.to_markdown(index=False))
    lines += [
        "",
        f"## Near-miss watchlist ({len(near_miss_df)})",
        "",
    ]
    if near_miss_df.empty:
        lines.append("No near-misses today.")
    else:
        lines.append(near_miss_df.to_markdown(index=False))
    lines += [
        "",
        "---",
        "Bollinger Band bounce + RSI(14) turning up (no fixed oversold floor) + volume "
        "confirmation + Relative Strength vs. the screened universe (positive "
        "`vs_universe_pct` means the stock is outperforming the average move across the "
        "universe today, i.e. moving on its own strength rather than riding a sector/market "
        "tailwind), on Nifty 50 + Nifty Next 50 + Nifty Midcap 50. The original 3-condition "
        "rule (with a fixed RSI<=35 oversold floor) was backtested over 2yr/~482 signals at "
        "36.1% win rate, +0.1195 R average expectancy, 86.3% of winners resolving within 2 "
        "trading days -- this 4-condition version (RSI floor dropped, Relative Strength "
        "added) has NOT been re-backtested, treat it as unproven until validated. "
        "Not investment advice.",
    ]
    return "\n".join(lines) + "\n"


def _format_pullback(matches: list) -> pd.DataFrame:
    if not matches:
        return pd.DataFrame()
    df = pd.DataFrame(matches)
    df = df[[
        "ticker", "company", "sector", "industry", "close", "sma50_support",
        "bb_lower", "bb_mid", "pct_change_today", "roe_pct", "debt_to_equity",
        "earnings_growth_pct", "recommendation", "avg_daily_value_cr",
    ]]
    for col in ["close", "sma50_support", "bb_lower", "bb_mid", "pct_change_today",
                "roe_pct", "debt_to_equity", "earnings_growth_pct", "avg_daily_value_cr"]:
        df[col] = df[col].astype(float).round(2)
    return df


def _format_rejected(rejected: list) -> pd.DataFrame:
    if not rejected:
        return pd.DataFrame()
    df = pd.DataFrame(rejected)
    preferred_cols = [
        "ticker", "company", "sector", "industry", "reason", "roe_pct",
        "debt_to_equity", "debt_check_exempt", "earnings_growth_pct",
        "revenue_growth_pct", "recommendation",
    ]
    cols = [c for c in preferred_cols if c in df.columns]
    df = df[cols]
    for col in ["roe_pct", "debt_to_equity", "earnings_growth_pct", "revenue_growth_pct"]:
        if col in df.columns:
            df[col] = df[col].astype(float).round(2)
    return df


def _build_pullback_markdown_report(matches_df: pd.DataFrame, rejected_df: pd.DataFrame,
                                     universe_size: int, history_fetched: int,
                                     technical_candidates: int) -> str:
    today = date.today().isoformat()
    lines = [
        f"# Quality Pullback Screener — {today}",
        "",
        f"Universe: {universe_size} tickers (price history fetched for {history_fetched}). "
        f"{technical_candidates} passed the technical gate (near 50-day support, between "
        "Bollinger lower/mid band, no outsized recent move); fundamentals were checked only "
        "for those.",
        "",
        f"## Matches ({len(matches_df)})",
        "",
    ]
    if matches_df.empty:
        lines.append("No matches today.")
    else:
        lines.append(matches_df.to_markdown(index=False))
    lines += [
        "",
        f"## Rejected on fundamentals/sector ({len(rejected_df)})",
        "",
        "Shows exactly which check(s) each technical candidate failed, so a low match count "
        "is verifiable rather than a black box.",
        "",
    ]
    if rejected_df.empty:
        lines.append("None.")
    else:
        lines.append(rejected_df.to_markdown(index=False))
    lines += [
        "",
        "---",
        "Quality-pullback strategy: close within 2% of the 50-day SMA AND between the "
        "Bollinger lower and middle band AND no single-day move over 3% in the last 2 "
        "sessions (the practical stand-in for \"no external/geopolitical shock\" -- there's "
        "no direct data feed for that), combined with fundamentals (positive earnings/revenue "
        "growth, ROE > 15%, Debt/Equity < 100 -- exempted for Financial Services, whose normal "
        "business model runs much higher leverage than a non-financial company -- and analyst "
        "recommendation not Sell/Underperform), on Nifty 50 + Nifty Next 50 + Nifty Midcap 50. "
        "This is a new, untested strategy -- no backtest exists for it yet. Not investment "
        "advice.",
    ]
    return "\n".join(lines) + "\n"


def _format_support_zone(matches: list) -> pd.DataFrame:
    if not matches:
        return pd.DataFrame()
    df = pd.DataFrame(matches)
    df = df[[
        "ticker", "company", "sector", "industry", "close", "rsi14",
        "bb_lower", "bb_mid", "bb_upper", "avg_daily_value_cr",
    ]]
    for col in ["close", "rsi14", "bb_lower", "bb_mid", "bb_upper", "avg_daily_value_cr"]:
        df[col] = df[col].astype(float).round(2)
    return df


def _build_support_zone_markdown_report(matches_df: pd.DataFrame, universe_size: int,
                                         history_fetched: int) -> str:
    today = date.today().isoformat()
    lines = [
        f"# Support Zone Screener — {today}",
        "",
        f"Universe: {universe_size} tickers (price history fetched for {history_fetched}).",
        "",
        f"## Matches ({len(matches_df)})",
        "",
    ]
    if matches_df.empty:
        lines.append("No matches today.")
    else:
        lines.append(matches_df.to_markdown(index=False))
    lines += [
        "",
        "---",
        "Plain technical scan, daily chart, no fundamentals and no extra conditions beyond "
        "this tool's standing liquidity (>= Rs 20cr/day) and sector-exclusion rules: "
        "RSI(14) between 30 and 45, AND close between the Bollinger lower and middle band "
        "(20-day SMA +/- 2 std dev). No backtest exists for this scan. Not investment advice.",
    ]
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(
        description="NSE screener: Bollinger Band bounce + RSI bounce + volume confirmation "
                    "over Nifty 50 + Nifty Next 50 + Nifty Midcap 50."
    )
    parser.add_argument("--strategy", choices=["bounce", "pullback", "support-zone"], default="bounce",
                        help="'bounce' (default): Bollinger/RSI/Volume/RelativeStrength bounce "
                             "signals. 'pullback': quality stocks resting near 50-day support "
                             "with strong fundamentals and no recent outsized move. "
                             "'support-zone': plain technical scan, no fundamentals -- RSI(14) "
                             "between 30-45 and close between the Bollinger lower/mid band.")
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

    os.makedirs(args.output_dir, exist_ok=True)
    today = date.today().isoformat()

    if args.strategy == "support-zone":
        result = run_support_zone_screen(csv_dir=args.csv_dir)
        matches_df = _format_support_zone(result["matches"])

        print(f"\nUniverse: {result['universe_size']} tickers "
              f"(price history fetched for {result['history_fetched']})\n")

        print(f"=== SUPPORT ZONE MATCHES ({len(matches_df)}) ===")
        print(matches_df.to_string(index=False) if not matches_df.empty else "No matches today.")

        matches_path = os.path.join(args.output_dir, f"support_zone_{today}.csv")
        report_path = os.path.join(args.output_dir, f"support_zone_report_{today}.md")
        matches_df.to_csv(matches_path, index=False)
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(_build_support_zone_markdown_report(
                matches_df, result["universe_size"], result["history_fetched"]))
        print(f"\nSaved: {matches_path}")
        print(f"Saved: {report_path}")
        return

    if args.strategy == "pullback":
        result = run_pullback_screen(csv_dir=args.csv_dir, info_sleep_seconds=args.info_sleep)
        matches_df = _format_pullback(result["matches"])
        rejected_df = _format_rejected(result["rejected"])

        print(f"\nUniverse: {result['universe_size']} tickers "
              f"(price history fetched for {result['history_fetched']}), "
              f"{result['technical_candidates']} passed the technical gate\n")

        print(f"=== QUALITY PULLBACK MATCHES ({len(matches_df)}) ===")
        print(matches_df.to_string(index=False) if not matches_df.empty else "No matches today.")

        print(f"\n=== REJECTED ON FUNDAMENTALS/SECTOR ({len(rejected_df)}) ===")
        print(rejected_df.to_string(index=False) if not rejected_df.empty else "None.")

        matches_path = os.path.join(args.output_dir, f"pullback_{today}.csv")
        rejected_path = os.path.join(args.output_dir, f"pullback_rejected_{today}.csv")
        report_path = os.path.join(args.output_dir, f"pullback_report_{today}.md")
        matches_df.to_csv(matches_path, index=False)
        rejected_df.to_csv(rejected_path, index=False)
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(_build_pullback_markdown_report(
                matches_df, rejected_df, result["universe_size"], result["history_fetched"],
                result["technical_candidates"]))
        print(f"\nSaved: {matches_path}")
        print(f"Saved: {rejected_path}")
        print(f"Saved: {report_path}")
        return

    result = run_screen(capital=args.capital, csv_dir=args.csv_dir, info_sleep_seconds=args.info_sleep)

    signals_df = _format_signals(result["signals"])
    near_miss_df = _format_near_miss(result["near_miss"])

    print(f"\nUniverse: {result['universe_size']} tickers "
          f"(price history fetched for {result['history_fetched']}), "
          f"universe average day change: {result['universe_avg_pct_change']:.2f}%\n")

    print(f"=== BUY SIGNALS ({len(signals_df)}) ===")
    print(signals_df.to_string(index=False) if not signals_df.empty else "No signals today.")

    print(f"\n=== NEAR-MISS WATCHLIST ({len(near_miss_df)}) ===")
    print(near_miss_df.to_string(index=False) if not near_miss_df.empty else "No near-misses today.")

    signals_path = os.path.join(args.output_dir, f"signals_{today}.csv")
    near_miss_path = os.path.join(args.output_dir, f"near_miss_{today}.csv")
    report_path = os.path.join(args.output_dir, f"report_{today}.md")
    signals_df.to_csv(signals_path, index=False)
    near_miss_df.to_csv(near_miss_path, index=False)
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(_build_markdown_report(signals_df, near_miss_df,
                                        result["universe_size"], result["history_fetched"],
                                        result["universe_avg_pct_change"]))
    print(f"\nSaved: {signals_path}")
    print(f"Saved: {near_miss_path}")
    print(f"Saved: {report_path}")


if __name__ == "__main__":
    main()
