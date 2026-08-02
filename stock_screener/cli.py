"""Command-line entry point for the NSE Bollinger/RSI/Volume screener."""

import argparse
import logging
import os
from datetime import date

import pandas as pd

from .gap_fill_strategy import run_gap_fill_screen
from .nifty50_scan import run_nifty50_scan
from .pullback_strategy import check_fundamentals_for_tickers, run_pullback_screen
from .screener import run_screen
from .support_levels import check_support_levels_for_tickers
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


def _format_fundamentals_check(rows: list) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df = df[[
        "ticker", "sector", "industry", "roe_pct", "debt_to_equity",
        "debt_check_exempt", "earnings_growth_pct", "revenue_growth_pct",
        "recommendation", "profitable_and_growing", "efficient_roe",
        "low_debt", "analyst_backed", "overall_ok",
    ]]
    for col in ["roe_pct", "debt_to_equity", "earnings_growth_pct", "revenue_growth_pct"]:
        df[col] = df[col].astype(float).round(2)
    return df


def _build_fundamentals_markdown_report(df: pd.DataFrame) -> str:
    today = date.today().isoformat()
    lines = [
        f"# Fundamentals Check — {today}",
        "",
        f"Checked {len(df)} ticker(s). Same bar as the pullback strategy: positive "
        "earnings/revenue growth, ROE > 15%, Debt/Equity < 100 (exempt for Financial "
        "Services), analyst recommendation not Sell/Underperform. `overall_ok` is True "
        "only if all four pass -- every ticker is shown regardless, nothing is filtered "
        "out.",
        "",
    ]
    if df.empty:
        lines.append("No tickers provided.")
    else:
        lines.append(df.to_markdown(index=False))
    lines += [
        "",
        "---",
        "Not investment advice.",
    ]
    return "\n".join(lines) + "\n"


_LEVEL_COLS = [
    "bollinger_lower", "sma_20", "sma_50", "sma_100", "sma_200",
    "low_20d", "low_60d", "low_120d", "low_252d", "week_52_low",
]


def _format_support_levels(rows: list) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    if "error" in df.columns:
        # rows with an error only have ticker+error; keep them visible rather
        # than silently dropping.
        pass

    def nearest_support(row):
        below = [row[c] for c in _LEVEL_COLS if c in row and pd.notna(row[c]) and row[c] < row.get("close", float("inf"))]
        return max(below) if below else None

    def nearest_resistance(row):
        above_cols = _LEVEL_COLS + ["week_52_high"]
        above = [row[c] for c in above_cols if c in row and pd.notna(row[c]) and row[c] > row.get("close", float("-inf"))]
        return min(above) if above else None

    if "close" in df.columns:
        df["nearest_support"] = df.apply(nearest_support, axis=1)
        df["nearest_resistance"] = df.apply(nearest_resistance, axis=1)

    cols = ["ticker", "close", "nearest_support", "nearest_resistance"] + _LEVEL_COLS + ["week_52_high", "error"]
    cols = [c for c in cols if c in df.columns]
    df = df[cols]
    for col in df.columns:
        if col not in ("ticker", "error"):
            df[col] = df[col].astype(float).round(2)
    return df


def _build_support_levels_markdown_report(df: pd.DataFrame) -> str:
    today = date.today().isoformat()
    lines = [
        f"# Support Levels — {today}",
        "",
        f"Checked {len(df)} ticker(s). `nearest_support` is the highest level below "
        "today's close among the 20/50/100/200-day SMAs, recent swing lows "
        "(20/60/120/252-day), and the 52-week low; `nearest_resistance` is the lowest "
        "level above close among the same set plus the 52-week high. These are the "
        "standard technical reference points, not a guarantee price will hold or reverse "
        "there.",
        "",
    ]
    if df.empty:
        lines.append("No tickers provided.")
    else:
        lines.append(df.to_markdown(index=False))
    lines += [
        "",
        "---",
        "Not investment advice.",
    ]
    return "\n".join(lines) + "\n"


def _format_nifty50_scan(rows: list) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df = df[[
        "ticker", "company", "sector", "industry", "close", "rsi14", "zone",
        "roe_pct", "debt_to_equity", "debt_check_exempt", "earnings_growth_pct",
        "revenue_growth_pct", "recommendation", "overall_ok",
    ]]
    for col in ["close", "rsi14", "roe_pct", "debt_to_equity", "earnings_growth_pct", "revenue_growth_pct"]:
        df[col] = df[col].astype(float).round(2)
    return df


def _build_nifty50_scan_markdown_report(df: pd.DataFrame, universe_size: int, history_fetched: int) -> str:
    today = date.today().isoformat()
    better_df = df[(df["zone"] == "pullback zone (lower-mid)") & (df["overall_ok"])] if not df.empty else df
    lines = [
        f"# Nifty 50 Combined Scan — {today}",
        "",
        f"Universe: {universe_size} Nifty 50 tickers (price history fetched for "
        f"{history_fetched}). Ranked so stocks in the pullback zone (technically near "
        "support, not overbought) with clean fundamentals come first, sorted by RSI "
        "ascending within that group.",
        "",
        f"## \"Better\" candidates: pullback zone + fundamentals clear ({len(better_df)})",
        "",
    ]
    if better_df.empty:
        lines.append("None today -- no stock is both in the pullback zone and passing all "
                      "four fundamentals checks.")
    else:
        lines.append(better_df.to_markdown(index=False))
    lines += [
        "",
        f"## Full ranked list, all {len(df)} Nifty 50 stocks",
        "",
    ]
    if df.empty:
        lines.append("No data.")
    else:
        lines.append(df.to_markdown(index=False))
    lines += [
        "",
        "---",
        "\"zone\" is the stock's current position relative to its own 20-day Bollinger "
        "Bands: 'pullback zone (lower-mid)' = between the lower and middle band (a dip, "
        "not a crash); 'at/below lower band' = at or past the extreme; 'upper-mid zone' / "
        "'at/above upper band' = neutral to strong, not a dip at all. Fundamentals use the "
        "same bar as the pullback strategy (positive earnings/revenue growth, ROE > 15%, "
        "Debt/Equity < 100 -- exempt for Financial Services, analyst recommendation not "
        "Sell/Underperform). A blank roe_pct means Yahoo Finance had no ROE data for that "
        "ticker, not that ROE is known to be bad -- efficient_roe fails by default on "
        "missing data. This is a new, untested combined view -- no backtest exists for it. "
        "Not investment advice.",
    ]
    return "\n".join(lines) + "\n"


def _format_gap_fill(matches: list) -> pd.DataFrame:
    if not matches:
        return pd.DataFrame()
    df = pd.DataFrame(matches)
    df = df[[
        "ticker", "company", "sector", "industry", "close", "gap_pct",
        "pre_gap_close", "pct_to_fill", "days_since_gap", "avg_daily_value_cr",
    ]]
    for col in ["close", "gap_pct", "pre_gap_close", "pct_to_fill", "avg_daily_value_cr"]:
        df[col] = df[col].astype(float).round(2)
    return df


def _build_gap_fill_markdown_report(df: pd.DataFrame, universe_size: int, history_fetched: int) -> str:
    today = date.today().isoformat()
    lines = [
        f"# Unfilled Gap-Down Screener — {today}",
        "",
        f"Universe: {universe_size} tickers (price history fetched for {history_fetched}).",
        "",
        f"## Matches ({len(df)})",
        "",
    ]
    if df.empty:
        lines.append("No unfilled gap-downs found in the last 60 trading days.")
    else:
        lines.append(df.to_markdown(index=False))
    lines += [
        "",
        "---",
        "Finds the most recent day (within the last 60 sessions) each stock opened at "
        "least 2% below the prior close (a gap-down), and reports it only if price hasn't "
        "since closed back up to that pre-gap level. `pct_to_fill` is how far today's "
        "close is from that level. A gap being unfilled does NOT mean it's likely to fill "
        "-- some gaps (especially on genuine bad news) never do. No backtest exists for "
        "this pattern on this universe. Not investment advice.",
    ]
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(
        description="NSE screener: Bollinger Band bounce + RSI bounce + volume confirmation "
                    "over Nifty 50 + Nifty Next 50 + Nifty Midcap 50."
    )
    parser.add_argument("--strategy",
                        choices=["bounce", "pullback", "support-zone", "fundamentals", "levels",
                                 "nifty50-scan", "gap-fill"],
                        default="bounce",
                        help="'bounce' (default): Bollinger/RSI/Volume/RelativeStrength bounce "
                             "signals. 'pullback': quality stocks resting near 50-day support "
                             "with strong fundamentals and no recent outsized move. "
                             "'support-zone': plain technical scan, no fundamentals -- RSI(14) "
                             "between 30-45 and close between the Bollinger lower/mid band. "
                             "'fundamentals': check ROE/debt/growth/rating for an explicit "
                             "--tickers list, no technical scan. "
                             "'levels': moving averages + recent swing lows/highs (support/"
                             "resistance reference points) for an explicit --tickers list. "
                             "'nifty50-scan': combined technical zone + fundamentals across all "
                             "Nifty 50 stocks, ranked by pullback-zone + clean-fundamentals first. "
                             "'gap-fill': stocks with a recent unfilled gap-down (opened >=2% "
                             "below prior close and haven't closed back up to that level yet).")
    parser.add_argument("--tickers", type=str, default="",
                        help="Comma-separated NSE tickers (with .NS suffix) for "
                             "--strategy fundamentals or levels, e.g. 'INFY.NS,TCS.NS'.")
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

    if args.strategy == "gap-fill":
        result = run_gap_fill_screen(csv_dir=args.csv_dir, info_sleep_seconds=args.info_sleep)
        df = _format_gap_fill(result["matches"])

        print(f"\nUniverse: {result['universe_size']} tickers "
              f"(price history fetched for {result['history_fetched']})\n")
        print(f"=== UNFILLED GAP-DOWNS ({len(df)}) ===")
        print(df.to_string(index=False) if not df.empty else "No unfilled gap-downs found.")

        out_path = os.path.join(args.output_dir, f"gap_fill_{today}.csv")
        report_path = os.path.join(args.output_dir, f"gap_fill_report_{today}.md")
        df.to_csv(out_path, index=False)
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(_build_gap_fill_markdown_report(df, result["universe_size"], result["history_fetched"]))
        print(f"\nSaved: {out_path}")
        print(f"Saved: {report_path}")
        return

    if args.strategy == "nifty50-scan":
        result = run_nifty50_scan(csv_dir=args.csv_dir, info_sleep_seconds=args.info_sleep)
        df = _format_nifty50_scan(result["rows"])

        print(f"\nNifty 50: {result['universe_size']} tickers "
              f"(price history fetched for {result['history_fetched']})\n")
        print(f"=== COMBINED SCAN ({len(df)} ticker(s), ranked) ===")
        print(df.to_string(index=False) if not df.empty else "No data.")

        out_path = os.path.join(args.output_dir, f"nifty50_scan_{today}.csv")
        report_path = os.path.join(args.output_dir, f"nifty50_scan_report_{today}.md")
        df.to_csv(out_path, index=False)
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(_build_nifty50_scan_markdown_report(
                df, result["universe_size"], result["history_fetched"]))
        print(f"\nSaved: {out_path}")
        print(f"Saved: {report_path}")
        return

    if args.strategy == "levels":
        tickers = [t.strip() for t in args.tickers.split(",") if t.strip()]
        if not tickers:
            parser.error("--strategy levels requires --tickers, e.g. --tickers ADANIPORTS.NS")

        rows = check_support_levels_for_tickers(tickers)
        df = _format_support_levels(rows)

        print(f"\n=== SUPPORT LEVELS ({len(df)} ticker(s)) ===")
        print(df.to_string(index=False) if not df.empty else "No tickers provided.")

        out_path = os.path.join(args.output_dir, f"levels_{today}.csv")
        report_path = os.path.join(args.output_dir, f"levels_report_{today}.md")
        df.to_csv(out_path, index=False)
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(_build_support_levels_markdown_report(df))
        print(f"\nSaved: {out_path}")
        print(f"Saved: {report_path}")
        return

    if args.strategy == "fundamentals":
        tickers = [t.strip() for t in args.tickers.split(",") if t.strip()]
        if not tickers:
            parser.error("--strategy fundamentals requires --tickers, e.g. --tickers INFY.NS,TCS.NS")

        rows = check_fundamentals_for_tickers(tickers, sleep_seconds=args.info_sleep)
        df = _format_fundamentals_check(rows)

        print(f"\n=== FUNDAMENTALS CHECK ({len(df)} ticker(s)) ===")
        print(df.to_string(index=False) if not df.empty else "No tickers provided.")

        out_path = os.path.join(args.output_dir, f"fundamentals_{today}.csv")
        report_path = os.path.join(args.output_dir, f"fundamentals_report_{today}.md")
        df.to_csv(out_path, index=False)
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(_build_fundamentals_markdown_report(df))
        print(f"\nSaved: {out_path}")
        print(f"Saved: {report_path}")
        return

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
