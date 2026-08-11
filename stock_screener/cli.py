"""Command-line entry point for the NSE Bollinger/RSI/Volume screener."""

import argparse
import logging
import os
from dataclasses import asdict
from datetime import date

import pandas as pd

from .backtest_support_zone import MAX_HOLDING_DAYS, run_backtest
from .backtest_support_zone_mtf import run_backtest as run_backtest_mtf
from .backtest_decline_reversal import run_backtest as run_backtest_decline_reversal
from .backtest_support_zone_rr import run_backtest as run_backtest_rr
from .bounce_fundamentals_strategy import run_bounce_fundamentals_screen
from .buffett_strategy import run_buffett_relaxed_screen, run_buffett_screen
from .decline_reversal_strategy import (
    NEAR_MISS_TOLERANCE_PCT as NEAR_MISS_TOLERANCE_PCT_DR,
    SUPPORT_TOLERANCE_PCT as SUPPORT_TOLERANCE_PCT_DR,
    run_decline_reversal_screen,
)
from .divergence_strategy import run_divergence_screen
from .gap_fill_strategy import run_gap_fill_screen
from .market_breadth import run_market_breadth
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
        "tailwind), on Nifty 50 + Nifty Next 50 + Nifty Midcap 50 + Nifty Midcap 150 + Nifty Smallcap 100. The original 3-condition "
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
        "close_position_pct", "volume_confirmed", "excess_return_pct",
        "bounce_quality", "tailwind_risk",
    ]]
    for col in ["close", "sma50_support", "bb_lower", "bb_mid", "pct_change_today",
                "roe_pct", "debt_to_equity", "earnings_growth_pct", "avg_daily_value_cr",
                "close_position_pct", "excess_return_pct"]:
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
        "recommendation not Sell/Underperform), on Nifty 50 + Nifty Next 50 + Nifty Midcap 50 + Nifty Midcap 150 + Nifty Smallcap 100. "
        "This is a new, untested strategy -- no backtest exists for it yet. Not investment "
        "advice.",
        "",
        "**Bounce-quality columns** (read-only diagnostics, don't affect who makes the "
        "list): `close_position_pct` is where today's close landed within today's "
        "high-low range (100% = closed at the day's high, buyers in full control; 0% = "
        "closed at the low) -- >=65% is counted as a strong close. `volume_confirmed` "
        "is today's volume vs. its trailing 20-day average. `excess_return_pct` is "
        "today's % change minus the average % change across the whole screened "
        "universe today -- positive means the stock is moving on its own strength, "
        "not just riding a market/sector-wide tailwind (`tailwind_risk` flags the "
        "opposite). `bounce_quality` tiers by how many of those three agree: "
        "strong (3/3), moderate (2/3), developing (1/3), weak (0/3).",
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


def _format_divergence(matches: list) -> pd.DataFrame:
    if not matches:
        return pd.DataFrame()
    df = pd.DataFrame(matches)
    df = df[[
        "ticker", "company", "sector", "industry", "close", "rsi_today",
        "low1_price", "low1_rsi", "low2_price", "low2_rsi",
        "price_change_pct", "rsi_change", "days_since_low2", "avg_daily_value_cr",
    ]]
    for col in ["close", "rsi_today", "low1_price", "low1_rsi", "low2_price",
                "low2_rsi", "price_change_pct", "rsi_change", "avg_daily_value_cr"]:
        df[col] = df[col].astype(float).round(2)
    return df


def _build_divergence_markdown_report(df: pd.DataFrame, universe_size: int, history_fetched: int) -> str:
    today = date.today().isoformat()
    lines = [
        f"# Bullish RSI Divergence Screener — {today}",
        "",
        f"Universe: {universe_size} tickers (price history fetched for {history_fetched}).",
        "",
        f"## Matches ({len(df)})",
        "",
    ]
    if df.empty:
        lines.append("No bullish divergence found in the last 90 trading days.")
    else:
        lines.append(df.to_markdown(index=False))
    lines += [
        "",
        "---",
        "Bullish RSI divergence: price makes a lower swing low (low2_price < low1_price) "
        "while RSI(14) makes a higher low at the same time (low2_rsi > low1_rsi) -- "
        "downward momentum fading even as price keeps falling, classically read as an "
        "early sign of a possible reversal. Both swing lows must have RSI <= 50 (a real "
        "dip, not noise near a strong trend) and the more recent one must be within the "
        "last 12 trading days. This is a pattern-recognition heuristic, not a guarantee -- "
        "divergence can persist for a while before (or without) any reversal. No backtest "
        "exists for this on this universe. Not investment advice.",
    ]
    return "\n".join(lines) + "\n"


def _format_backtest_trades(trades: list) -> pd.DataFrame:
    if not trades:
        return pd.DataFrame()
    df = pd.DataFrame([asdict(t) for t in trades])
    df = df[[
        "ticker", "signal_date", "entry", "stop_loss", "target", "exit_date",
        "exit_reason", "exit_price", "days_held", "r_multiple",
    ]]
    for col in ["entry", "stop_loss", "target", "exit_price", "r_multiple"]:
        df[col] = df[col].astype(float).round(4)
    return df.sort_values("signal_date", ascending=False).reset_index(drop=True)


def _build_backtest_markdown_report(result: dict) -> str:
    today = date.today().isoformat()
    total = result["total_signals"]
    lines = [
        f"# Support Zone Strategy Backtest — {today}",
        "",
        f"Backtests the exact rule behind the live `support-zone` strategy: RSI(14) between "
        f"30 and 45 AND close between the Bollinger lower and middle band, daily chart. "
        f"Universe: {result['universe_size']} tickers ({result['excluded_count']} excluded "
        f"by standing sector/industry rules, price history fetched for "
        f"{result['history_fetched']}), over the last {result['period']}.",
        "",
        "## Results",
        "",
        f"- **Total signals**: {total} (a fresh entry into the zone counts once, even if the "
        "stock stays in the zone for several days)",
        f"- **Win rate**: {result['win_rate_pct']:.1f}% "
        f"({result['wins']} target hits + {result['time_exit_wins']} of "
        f"{result['time_exits']} time-exits still net positive, out of {total})",
        f"- **Average R-multiple**: {result['avg_r_multiple']:+.3f}R per trade",
        f"- **Stop-outs**: {result['losses']}",
        f"- **Average days held for winners**: {result['avg_days_held_winners']:.1f}",
        "",
        "---",
        "**Methodology**: same entry/stop/target rule used across this project -- entry at "
        "the signal day's close, stop-loss at entry - 0.75x ATR14, target at entry x 1.03. A "
        "trade is closed at the target or the stop, whichever is hit first over the following "
        f"{MAX_HOLDING_DAYS} trading days; if neither is hit within that window it's closed "
        "at that day's close (a \"time exit\", counted as a win only if the R-multiple came "
        "out positive). If a single day's range touches both "
        "the stop and the target, the stop is assumed to have hit first -- daily bars can't "
        "show the real intraday sequence, and assuming the worse outcome avoids overstating "
        "the win rate.",
        "",
        "**Caveats**: this uses the *current* universe applied backward over the "
        "full lookback window, not the actual index membership on each historical date -- "
        "stocks that were added to Nifty 50/Next 50/Midcap 50 more recently (because they "
        "performed well) get backtested over the same window as long-standing members, which "
        "tilts results optimistic (survivorship bias). No transaction costs, slippage, or "
        "taxes are modeled. This is a real historical result for this exact rule, not a "
        "simulation of what a live trader would have captured. Not investment advice.",
    ]
    return "\n".join(lines) + "\n"


def _format_backtest_mtf_trades(trades: list) -> pd.DataFrame:
    if not trades:
        return pd.DataFrame()
    df = pd.DataFrame([asdict(t) for t in trades])
    df = df[[
        "ticker", "signal_date", "entry", "stop_loss", "target", "exit_date",
        "exit_reason", "exit_price", "days_held", "r_multiple", "weekly_rsi",
        "monthly_rsi",
    ]]
    for col in ["entry", "stop_loss", "target", "exit_price", "r_multiple",
                "weekly_rsi", "monthly_rsi"]:
        df[col] = df[col].astype(float).round(4)
    return df.sort_values("signal_date", ascending=False).reset_index(drop=True)


def _build_backtest_mtf_markdown_report(result: dict) -> str:
    today = date.today().isoformat()
    total = result["total_signals"]
    lines = [
        f"# Support Zone Strategy Backtest (Multi-Timeframe + Volume) — {today}",
        "",
        "Adds Weekly RSI(14) > 50 AND Monthly RSI(14) > 50 (both computed on resampled "
        "closes, forward-filled onto the daily calendar with no lookahead into an "
        "in-progress week/month) AND today's volume > the prior 20-day average volume, on "
        "top of the plain daily support-zone rule (RSI(14) 30-45 AND close between the "
        f"Bollinger lower/mid band). Universe: {result['universe_size']} tickers "
        f"({result['excluded_count']} excluded by standing sector/industry rules, price "
        f"history fetched for {result['history_fetched']}) -- {result['period']} of history "
        f"pulled to properly warm up weekly/monthly RSI, but signals are only counted in "
        f"the most recent {result['test_window_years']} years, the same window as the "
        "plain support-zone backtest.",
        "",
        "## Results",
        "",
        f"- **Total signals**: {total} (a fresh entry into the narrowed zone counts once, "
        "even if the stock stays in the zone for several days)",
        f"- **Win rate**: {result['win_rate_pct']:.1f}% "
        f"({result['wins']} target hits + {result['time_exit_wins']} of "
        f"{result['time_exits']} time-exits still net positive, out of {total})",
        f"- **Average R-multiple**: {result['avg_r_multiple']:+.3f}R per trade",
        f"- **Stop-outs**: {result['losses']}",
        f"- **Average days held for winners**: {result['avg_days_held_winners']:.1f}",
        "",
        "---",
        "**Methodology**: same entry/stop/target rule used across this project -- entry at "
        "the signal day's close, stop-loss at entry - 0.75x ATR14, target at entry x 1.03, "
        f"closed at whichever is hit first within {MAX_HOLDING_DAYS} trading days (a \"time "
        "exit\" otherwise, counted as a win only if the R-multiple came out positive). If a "
        "single day's range touches both the stop and the target, the stop is assumed to "
        "have hit first -- daily bars can't show the real intraday sequence, and assuming "
        "the worse outcome avoids overstating the win rate.",
        "",
        "**Caveats**: same as the plain support-zone backtest -- current universe applied "
        "backward (survivorship bias), no transaction costs/slippage modeled. Additionally: "
        "weekly/monthly RSI needs ~14 of its own periods (14 weeks / 14 months) to stop "
        "returning NaN under Wilder's smoothing, so a stock with less history than that "
        "before the test window starts won't produce any signals in this version even if it "
        "would have in the plain daily-only backtest. Not investment advice.",
    ]
    return "\n".join(lines) + "\n"


def _format_backtest_rr_trades(trades: list) -> pd.DataFrame:
    if not trades:
        return pd.DataFrame()
    df = pd.DataFrame([asdict(t) for t in trades])
    df = df[[
        "ticker", "signal_date", "entry", "stop_loss", "target", "exit_date",
        "exit_reason", "exit_price", "days_held", "r_multiple",
    ]]
    for col in ["entry", "stop_loss", "target", "exit_price", "r_multiple"]:
        df[col] = df[col].astype(float).round(4)
    return df.sort_values("signal_date", ascending=False).reset_index(drop=True)


def _build_backtest_rr_markdown_report(result: dict) -> str:
    today = date.today().isoformat()
    total = result["total_signals"]
    rr = result["risk_reward_multiple"]
    lines = [
        f"# Support Zone Strategy Backtest (Fixed {rr:.0f}:1 Risk-Reward) — {today}",
        "",
        "Same support-zone rule as the plain backtest (RSI(14) 30-45 AND close between the "
        "Bollinger lower/mid band) with one change: the target is no longer a fixed +3% for "
        f"every stock -- it's now entry + {rr:.0f}x the stop distance (entry - 0.75x ATR14), "
        "so every trade has the same built-in reward-to-risk ratio regardless of that "
        "stock's volatility. This isolates the effect of that one change against the plain "
        "backtest's -0.030R average. "
        f"Universe: {result['universe_size']} tickers ({result['excluded_count']} excluded "
        f"by standing sector/industry rules, price history fetched for "
        f"{result['history_fetched']}), over the last {result['period']}.",
        "",
        "## Results",
        "",
        f"- **Total signals**: {total} (a fresh entry into the zone counts once, even if the "
        "stock stays in the zone for several days)",
        f"- **Win rate**: {result['win_rate_pct']:.1f}% "
        f"({result['wins']} target hits + {result['time_exit_wins']} of "
        f"{result['time_exits']} time-exits still net positive, out of {total})",
        f"- **Average R-multiple**: {result['avg_r_multiple']:+.3f}R per trade",
        f"- **Stop-outs**: {result['losses']}",
        f"- **Average days held for winners**: {result['avg_days_held_winners']:.1f}",
        "",
        "---",
        "**Methodology**: entry at the signal day's close, stop-loss at entry - 0.75x ATR14 "
        f"(unchanged from the plain backtest), target at entry + {rr:.0f}x the stop distance "
        f"(the one change). Closed at whichever is hit first within {MAX_HOLDING_DAYS} "
        "trading days, or a time-exit otherwise (counted as a win only if the R-multiple came "
        "out positive). If a single day's range touches both the stop and the target, the "
        "stop is assumed to have hit first -- daily bars can't show the real intraday "
        "sequence, and assuming the worse outcome avoids overstating the win rate.",
        "",
        "**Caveats**: same as the plain support-zone backtest -- current universe applied "
        "backward (survivorship bias), no transaction costs/slippage modeled. A bigger fixed "
        "reward-to-risk ratio mechanically requires price to travel further to hit target, so "
        "expect the win rate to be lower than the plain backtest's 39.7% even if this version "
        "is more profitable overall -- win rate and expectancy need to be read together, not "
        "separately. Not investment advice.",
    ]
    return "\n".join(lines) + "\n"


def _format_bounce_fundamentals(matches: list) -> pd.DataFrame:
    if not matches:
        return pd.DataFrame()
    df = pd.DataFrame(matches)
    df = df[[
        "ticker", "company", "sector", "industry", "close", "rsi_today",
        "pct_above_lower_band", "volume_vs_avg_pct", "roe_pct", "debt_to_equity",
        "earnings_growth_pct", "recommendation", "avg_daily_value_cr",
    ]]
    for col in ["close", "rsi_today", "pct_above_lower_band", "volume_vs_avg_pct",
                "roe_pct", "debt_to_equity", "earnings_growth_pct", "avg_daily_value_cr"]:
        df[col] = df[col].astype(float).round(2)
    return df


def _build_bounce_fundamentals_markdown_report(matches_df: pd.DataFrame, rejected_df: pd.DataFrame,
                                                universe_size: int, history_fetched: int,
                                                technical_candidates: int) -> str:
    today = date.today().isoformat()
    lines = [
        f"# Bounce + Fundamentals Screener — {today}",
        "",
        f"Universe: {universe_size} tickers (price history fetched for {history_fetched}). "
        f"{technical_candidates} passed the technical gate (Bollinger bounce + RSI<45 + "
        "volume above 20-day average); fundamentals were checked only for those.",
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
        "Bollinger Band bounce (low touches/dips to the lower band, close recovers above it, "
        "and closes higher than yesterday) AND RSI(14) < 45 (a loose ceiling, not a fixed "
        "oversold floor) AND today's volume above the prior 20-day average, combined with "
        "fundamentals (positive earnings/revenue growth, ROE > 15%, Debt/Equity < 100 -- "
        "exempt for Financial Services, analyst recommendation not Sell/Underperform), on "
        "Nifty 50 + Nifty Next 50 + Nifty Midcap 50 + Nifty Midcap 150 + Nifty Smallcap 100. Built around the actual bounce *event* "
        "rather than a passive zone *state* -- this project's backtests found the "
        "event-based bounce condition was the one part of the original 3-condition rule with "
        "positive expectancy (+0.1195R), while passive state rules (RSI 30-45 + between the "
        "Bollinger bands, tested multiple ways) came back consistently break-even-to-negative. "
        "That said, this exact combination (bounce event + RSI<45 + volume + fundamentals) "
        "has NOT itself been backtested -- treat it as a new, unproven combination until "
        "validated against history. Not investment advice.",
    ]
    return "\n".join(lines) + "\n"


def _format_decline_reversal(matches: list) -> pd.DataFrame:
    if not matches:
        return pd.DataFrame()
    df = pd.DataFrame(matches)
    df = df[[
        "ticker", "company", "sector", "industry", "close", "open", "prev_close",
        "nearest_support", "pct_above_support", "decline_streak_days", "avg_daily_value_cr",
    ]]
    for col in ["close", "open", "prev_close", "nearest_support", "pct_above_support",
                "avg_daily_value_cr"]:
        df[col] = df[col].astype(float).round(2)
    return df


def _build_decline_reversal_markdown_report(matches_df: pd.DataFrame, near_miss_df: pd.DataFrame,
                                             universe_size: int, history_fetched: int) -> str:
    today = date.today().isoformat()
    lines = [
        f"# Decline-Reversal Near Support Screener — {today}",
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
        f"## Near-miss watchlist ({len(near_miss_df)})",
        "",
        "Same 3-day decline + green reversal candle, but sitting further from the nearest "
        f"support level -- between {SUPPORT_TOLERANCE_PCT_DR:.0f}% and "
        f"{NEAR_MISS_TOLERANCE_PCT_DR:.0f}% above it instead of within "
        f"{SUPPORT_TOLERANCE_PCT_DR:.0f}%. The reversal already happened; support is just a "
        "bit further away than the strict bar.",
        "",
    ]
    if near_miss_df.empty:
        lines.append("No near-misses today.")
    else:
        lines.append(near_miss_df.to_markdown(index=False))
    lines += [
        "",
        "---",
        "Finds stocks where the last 3 trading days each closed lower than the day before (a "
        "genuine losing streak), followed by today's candle closing above its own open (green) "
        "AND above yesterday's close (an actual reversal, not just a smaller red candle), with "
        "today's close landing near the nearest real support level below it (the highest of "
        "the 20/50/100/200-day SMAs, 20/60/120/252-day swing lows, and the Bollinger lower "
        "band that sits below today's close). Pure price-action pattern, no fundamentals "
        "filter -- only the standing liquidity (>= Rs 20cr/day) and sector/industry exclusion "
        "rules apply. This is a new, untested strategy -- no backtest exists for it yet. Not "
        "investment advice.",
    ]
    return "\n".join(lines) + "\n"


def _format_backtest_decline_reversal_trades(trades: list) -> pd.DataFrame:
    if not trades:
        return pd.DataFrame()
    df = pd.DataFrame([asdict(t) for t in trades])
    df = df[[
        "ticker", "signal_date", "entry", "stop_loss", "target", "exit_date",
        "exit_reason", "exit_price", "days_held", "r_multiple", "pct_above_support",
    ]]
    for col in ["entry", "stop_loss", "target", "exit_price", "r_multiple", "pct_above_support"]:
        df[col] = df[col].astype(float).round(4)
    return df.sort_values("signal_date", ascending=False).reset_index(drop=True)


def _build_backtest_decline_reversal_markdown_report(result: dict) -> str:
    today = date.today().isoformat()
    total = result["total_signals"]
    lines = [
        f"# Decline-Reversal Near Support Backtest — {today}",
        "",
        "Backtests the exact rule behind the live `decline-reversal` strategy against real "
        "historical data (not synthetic): 3 real trading days each closing lower than the day "
        "before, followed by a real green reversal candle (closes above its own open and above "
        "the prior close), landing within 2% of a real, computed support level (SMAs, swing "
        f"lows, or the Bollinger lower band). Universe: {result['universe_size']} tickers "
        f"({result['excluded_count']} excluded by standing sector/industry rules, real price "
        f"history fetched for {result['history_fetched']}), over the last {result['period']}.",
        "",
        "## Results",
        "",
        f"- **Total signals**: {total} (real historical occurrences of the exact pattern)",
        f"- **Win rate**: {result['win_rate_pct']:.1f}% "
        f"({result['wins']} target hits + {result['time_exit_wins']} of "
        f"{result['time_exits']} time-exits still net positive, out of {total})",
        f"- **Average R-multiple**: {result['avg_r_multiple']:+.3f}R per trade",
        f"- **Stop-outs**: {result['losses']}",
        f"- **Average days held for winners**: {result['avg_days_held_winners']:.1f}",
        "",
        "---",
        "**Methodology**: same entry/stop/target rule used across this project -- entry at "
        "the signal day's close, stop-loss at entry - 0.75x ATR14, target at entry x 1.03. A "
        "trade is closed at the target or the stop, whichever is hit first over the following "
        f"{MAX_HOLDING_DAYS} trading days; if neither is hit within that window it's closed "
        "at that day's close (a \"time exit\", counted as a win only if the R-multiple came "
        "out positive). If a single day's range touches both the stop and the target, the "
        "stop is assumed to have hit first -- daily bars can't show the real intraday "
        "sequence, and assuming the worse outcome avoids overstating the win rate.",
        "",
        "**Caveats**: this uses the *current* universe applied backward over the "
        "full lookback window, not the actual index membership on each historical date -- "
        "tilts results optimistic (survivorship bias). No transaction costs, slippage, or "
        "taxes are modeled. This is a real historical result computed from real market data "
        "for this exact rule, not a simulation against synthetic data. Not investment advice.",
    ]
    return "\n".join(lines) + "\n"


def _format_buffett(matches: list) -> pd.DataFrame:
    if not matches:
        return pd.DataFrame()
    df = pd.DataFrame(matches)
    df = df[[
        "ticker", "company", "sector", "industry", "roe_pct", "debt_to_equity",
        "debt_check_exempt", "earnings_growth_pct", "revenue_growth_pct",
        "profit_margin_pct", "free_cash_flow_cr", "trailing_pe", "recommendation",
    ]]
    for col in ["roe_pct", "debt_to_equity", "earnings_growth_pct", "revenue_growth_pct",
                "profit_margin_pct", "free_cash_flow_cr", "trailing_pe"]:
        df[col] = df[col].astype(float).round(2)
    return df


def _build_buffett_markdown_report(df: pd.DataFrame, universe_size: int, checked: int) -> str:
    today = date.today().isoformat()
    lines = [
        f"# Warren Buffett Quality Screener — {today}",
        "",
        f"Universe: {universe_size} tickers ({checked} checked for fundamentals -- this "
        "strategy has no technical price trigger, so every non-excluded ticker needs a "
        "fundamentals lookup, unlike the technical-gate-first strategies elsewhere in this "
        "project).",
        "",
        f"## Matches ({len(df)})",
        "",
    ]
    if df.empty:
        lines.append("No matches today.")
    else:
        lines.append(df.to_markdown(index=False))
    lines += [
        "",
        "---",
        "All seven must pass: ROE > 15%, Debt/Equity < 50 (exempt for Financial Services), "
        "BOTH earnings growth and revenue growth positive (stricter than the pullback "
        "strategy's either/or), positive free cash flow, profit margin > 10% (a rough, "
        "computable proxy for pricing power / economic moat -- not a real substitute for "
        "judging one), trailing P/E under 25 (margin-of-safety proxy), and analyst "
        "recommendation not Sell/Underperform. This is a pure business-quality + valuation "
        "snapshot, not a trading signal -- there's no price pattern or entry timing here at "
        "all. No backtest exists for this combination. Not investment advice.",
    ]
    return "\n".join(lines) + "\n"


def _build_buffett_relaxed_markdown_report(df: pd.DataFrame, universe_size: int, checked: int) -> str:
    today = date.today().isoformat()
    lines = [
        f"# Warren Buffett Quality Screener (Relaxed) — {today}",
        "",
        f"Same seven-check Buffett-style bar as the strict `buffett` strategy, with two "
        "dimensions loosened after the strict version returned zero matches: trailing P/E "
        "ceiling raised from 25x to 40x, and growth relaxed from \"both earnings AND revenue "
        "growth positive\" to \"at least one of the two\" (matching the pullback strategy's own "
        "either/or bar). ROE > 15%, Debt/Equity < 50 (exempt for Financial Services), positive "
        "free cash flow, profit margin > 10%, and analyst recommendation not Sell/Underperform "
        "are all unchanged from the strict version. "
        f"Universe: {universe_size} tickers ({checked} checked for fundamentals).",
        "",
        f"## Matches ({len(df)})",
        "",
    ]
    if df.empty:
        lines.append("No matches today, even with the relaxed bar.")
    else:
        lines.append(df.to_markdown(index=False))
    lines += [
        "",
        "---",
        "This is a pure business-quality + valuation snapshot, not a trading signal -- there's "
        "no price pattern or entry timing here at all. No backtest exists for this "
        "combination. Not investment advice.",
    ]
    return "\n".join(lines) + "\n"


def _format_breadth_table(stats_list: list, name_key: str) -> pd.DataFrame:
    if not stats_list:
        return pd.DataFrame()
    df = pd.DataFrame(stats_list)
    df = df[[name_key, "count", "advancers", "decliners", "unchanged", "avg_pct_change"]]
    df["avg_pct_change"] = df["avg_pct_change"].astype(float).round(3)
    return df


def _format_movers(rows: list) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df = df[["ticker", "company", "segment", "sector", "pct_change_today"]]
    df["pct_change_today"] = df["pct_change_today"].astype(float).round(2)
    return df


def _build_market_breadth_markdown_report(result: dict) -> str:
    today = date.today().isoformat()
    o = result["overall"]
    segment_df = _format_breadth_table(result["segment_breadth"], "segment")
    sector_df = _format_breadth_table(result["sector_breadth"], "sector")
    gainers_df = _format_movers(result["top_gainers"])
    losers_df = _format_movers(result["top_losers"])

    lines = [
        f"# Market Breadth — {today}",
        "",
        f"Universe: {result['universe_size']} tickers (price history fetched for "
        f"{result['history_fetched']}). Unfiltered -- no sector exclusions, no fundamentals "
        "gate, no technical zone. Every strategy in this project narrows to a specific setup; "
        "this one is the whole-market baseline they're all measured against.",
        "",
        "## Overall",
        "",
        f"- **Advancers**: {o['advancers']} &nbsp; **Decliners**: {o['decliners']} &nbsp; "
        f"**Unchanged**: {o['unchanged']} (of {o['count']})",
        f"- **Universe average move**: {o['avg_pct_change']:+.3f}%",
        "",
        "## By market-cap segment",
        "",
    ]
    if segment_df.empty:
        lines.append("No data.")
    else:
        lines.append(segment_df.to_markdown(index=False))
    lines += [
        "",
        "## By sector",
        "",
    ]
    if sector_df.empty:
        lines.append("No data.")
    else:
        lines.append(sector_df.to_markdown(index=False))
    lines += [
        "",
        "## Top 10 gainers",
        "",
    ]
    lines.append(gainers_df.to_markdown(index=False) if not gainers_df.empty else "No data.")
    lines += [
        "",
        "## Top 10 losers",
        "",
    ]
    lines.append(losers_df.to_markdown(index=False) if not losers_df.empty else "No data.")
    lines += [
        "",
        "---",
        "`avg_pct_change` is the simple average of each stock's today-vs-yesterday close "
        "change within that group (not cap-weighted, so a handful of small/illiquid names "
        "moving hard can skew a segment or sector's average more than they'd move a real "
        "cap-weighted index). Sector comes from Yahoo Finance's classification and is fetched "
        "for every ticker with usable price history, unlike every other strategy here which "
        "only fetches it for names that already passed a technical/fundamentals filter -- this "
        "run is slower for that reason. Not investment advice.",
    ]
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(
        description="NSE screener: Bollinger Band bounce + RSI bounce + volume confirmation "
                    "over Nifty 50 + Nifty Next 50 + Nifty Midcap 50 + Nifty Midcap 150 + Nifty Smallcap 100."
    )
    parser.add_argument("--strategy",
                        choices=["bounce", "pullback", "support-zone", "fundamentals", "levels",
                                 "nifty50-scan", "gap-fill", "divergence", "backtest-support-zone",
                                 "backtest-support-zone-mtf", "backtest-support-zone-rr",
                                 "bounce-fundamentals", "decline-reversal",
                                 "backtest-decline-reversal", "buffett", "buffett-relaxed",
                                 "breadth"],
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
                             "below prior close and haven't closed back up to that level yet). "
                             "'divergence': bullish RSI divergence -- price makes a lower swing "
                             "low while RSI(14) makes a higher low at the same time. "
                             "'backtest-support-zone': ~2yr historical backtest of the "
                             "support-zone rule (RSI 30-45 + between Bollinger lower/mid band), "
                             "reporting real win rate and R-multiple for that exact rule. "
                             "'backtest-support-zone-mtf': same backtest plus Weekly RSI>50, "
                             "Monthly RSI>50, and volume > 20-day average volume on the signal "
                             "day, to test whether higher-timeframe trend + volume confirmation "
                             "improves the plain rule. "
                             "'backtest-support-zone-rr': same backtest but with a fixed 2:1 "
                             "target-to-stop ratio (target = entry + 2x the ATR-based stop "
                             "distance) instead of a fixed +3% target, to test whether fixing "
                             "the reward-to-risk mismatch improves the plain rule's expectancy. "
                             "'bounce-fundamentals': Bollinger bounce event (low touches lower "
                             "band, close recovers above it and above yesterday's close) + "
                             "RSI(14)<45 + volume above 20-day average + fundamentals bar "
                             "(ROE>15%, D/E<100, growth, analyst not-Sell). "
                             "'decline-reversal': 3 consecutive down days followed by a green "
                             "reversal candle (closes above its own open and above yesterday's "
                             "close) landing within 2% of a real support level (SMAs, swing "
                             "lows, or Bollinger lower band). "
                             "'backtest-decline-reversal': ~2yr real-data historical backtest "
                             "of the decline-reversal rule, reporting real win rate and "
                             "R-multiple for that exact rule. "
                             "'buffett': Warren Buffett-style quality/value screener -- ROE>15%, "
                             "D/E<50, both earnings AND revenue growth positive, positive free "
                             "cash flow, profit margin>10%, trailing P/E<25, analyst not-Sell. "
                             "No technical trigger at all, pure business quality + valuation. "
                             "'buffett-relaxed': same bar with P/E ceiling raised to 40x and "
                             "growth relaxed to either earnings OR revenue positive. "
                             "'breadth': unfiltered market-breadth snapshot -- advancers vs. "
                             "decliners, average move by market-cap segment and by sector, "
                             "top 10 gainers/losers. No exclusions, no fundamentals gate, no "
                             "technical zone -- the whole-market baseline every other "
                             "strategy here is measured against.")
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

    if args.strategy == "breadth":
        result = run_market_breadth(csv_dir=args.csv_dir, info_sleep_seconds=args.info_sleep)
        o = result["overall"]

        print(f"\nUniverse: {result['universe_size']} tickers "
              f"(price history fetched for {result['history_fetched']})\n")
        print(f"=== MARKET BREADTH === advancers={o['advancers']} decliners={o['decliners']} "
              f"unchanged={o['unchanged']} avg_move={o['avg_pct_change']:+.3f}%")

        segment_df = _format_breadth_table(result["segment_breadth"], "segment")
        sector_df = _format_breadth_table(result["sector_breadth"], "sector")
        gainers_df = _format_movers(result["top_gainers"])
        losers_df = _format_movers(result["top_losers"])

        print("\n=== BY SEGMENT ===")
        print(segment_df.to_string(index=False) if not segment_df.empty else "No data.")
        print("\n=== BY SECTOR ===")
        print(sector_df.to_string(index=False) if not sector_df.empty else "No data.")
        print("\n=== TOP GAINERS ===")
        print(gainers_df.to_string(index=False) if not gainers_df.empty else "No data.")
        print("\n=== TOP LOSERS ===")
        print(losers_df.to_string(index=False) if not losers_df.empty else "No data.")

        segment_path = os.path.join(args.output_dir, f"breadth_segment_{today}.csv")
        sector_path = os.path.join(args.output_dir, f"breadth_sector_{today}.csv")
        report_path = os.path.join(args.output_dir, f"breadth_report_{today}.md")
        segment_df.to_csv(segment_path, index=False)
        sector_df.to_csv(sector_path, index=False)
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(_build_market_breadth_markdown_report(result))
        print(f"\nSaved: {segment_path}")
        print(f"Saved: {sector_path}")
        print(f"Saved: {report_path}")
        return

    if args.strategy == "buffett-relaxed":
        result = run_buffett_relaxed_screen(csv_dir=args.csv_dir, info_sleep_seconds=args.info_sleep)
        df = _format_buffett(result["matches"])

        print(f"\nUniverse: {result['universe_size']} tickers "
              f"({result['checked']} checked for fundamentals)\n")
        print(f"=== WARREN BUFFETT QUALITY SCREENER (RELAXED) ({len(df)}) ===")
        print(df.to_string(index=False) if not df.empty else "No matches today.")

        out_path = os.path.join(args.output_dir, f"buffett_relaxed_{today}.csv")
        report_path = os.path.join(args.output_dir, f"buffett_relaxed_report_{today}.md")
        df.to_csv(out_path, index=False)
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(_build_buffett_relaxed_markdown_report(df, result["universe_size"], result["checked"]))
        print(f"\nSaved: {out_path}")
        print(f"Saved: {report_path}")
        return

    if args.strategy == "buffett":
        result = run_buffett_screen(csv_dir=args.csv_dir, info_sleep_seconds=args.info_sleep)
        df = _format_buffett(result["matches"])

        print(f"\nUniverse: {result['universe_size']} tickers "
              f"({result['checked']} checked for fundamentals)\n")
        print(f"=== WARREN BUFFETT QUALITY SCREENER ({len(df)}) ===")
        print(df.to_string(index=False) if not df.empty else "No matches today.")

        out_path = os.path.join(args.output_dir, f"buffett_{today}.csv")
        report_path = os.path.join(args.output_dir, f"buffett_report_{today}.md")
        df.to_csv(out_path, index=False)
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(_build_buffett_markdown_report(df, result["universe_size"], result["checked"]))
        print(f"\nSaved: {out_path}")
        print(f"Saved: {report_path}")
        return

    if args.strategy == "backtest-decline-reversal":
        result = run_backtest_decline_reversal(csv_dir=args.csv_dir, info_sleep_seconds=args.info_sleep)
        trades_df = _format_backtest_decline_reversal_trades(result["trades"])

        print(f"\nUniverse: {result['universe_size']} tickers "
              f"({result['excluded_count']} excluded, price history fetched for "
              f"{result['history_fetched']}) over the last {result['period']}\n")
        print(f"=== BACKTEST RESULTS ({result['total_signals']} signals) ===")
        print(f"Win rate: {result['win_rate_pct']:.1f}%  "
              f"Avg R-multiple: {result['avg_r_multiple']:+.3f}  "
              f"Wins/Losses/TimeExits: {result['wins']}/{result['losses']}/{result['time_exits']}")

        trades_path = os.path.join(args.output_dir, f"backtest_decline_reversal_trades_{today}.csv")
        report_path = os.path.join(args.output_dir, f"backtest_decline_reversal_report_{today}.md")
        trades_df.to_csv(trades_path, index=False)
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(_build_backtest_decline_reversal_markdown_report(result))
        print(f"\nSaved: {trades_path}")
        print(f"Saved: {report_path}")
        return

    if args.strategy == "decline-reversal":
        result = run_decline_reversal_screen(csv_dir=args.csv_dir, info_sleep_seconds=args.info_sleep)
        matches_df = _format_decline_reversal(result["matches"])
        near_miss_df = _format_decline_reversal(result["near_miss"])

        print(f"\nUniverse: {result['universe_size']} tickers "
              f"(price history fetched for {result['history_fetched']})\n")
        print(f"=== DECLINE-REVERSAL NEAR SUPPORT ({len(matches_df)}) ===")
        print(matches_df.to_string(index=False) if not matches_df.empty else "No matches found.")
        print(f"\n=== NEAR-MISS WATCHLIST ({len(near_miss_df)}) ===")
        print(near_miss_df.to_string(index=False) if not near_miss_df.empty else "No near-misses found.")

        matches_path = os.path.join(args.output_dir, f"decline_reversal_{today}.csv")
        near_miss_path = os.path.join(args.output_dir, f"decline_reversal_near_miss_{today}.csv")
        report_path = os.path.join(args.output_dir, f"decline_reversal_report_{today}.md")
        matches_df.to_csv(matches_path, index=False)
        near_miss_df.to_csv(near_miss_path, index=False)
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(_build_decline_reversal_markdown_report(
                matches_df, near_miss_df, result["universe_size"], result["history_fetched"]))
        print(f"\nSaved: {matches_path}")
        print(f"Saved: {near_miss_path}")
        print(f"Saved: {report_path}")
        return

    if args.strategy == "bounce-fundamentals":
        result = run_bounce_fundamentals_screen(csv_dir=args.csv_dir, info_sleep_seconds=args.info_sleep)
        matches_df = _format_bounce_fundamentals(result["matches"])
        rejected_df = _format_rejected(result["rejected"])

        print(f"\nUniverse: {result['universe_size']} tickers "
              f"(price history fetched for {result['history_fetched']}), "
              f"{result['technical_candidates']} passed the technical gate\n")

        print(f"=== BOUNCE + FUNDAMENTALS MATCHES ({len(matches_df)}) ===")
        print(matches_df.to_string(index=False) if not matches_df.empty else "No matches today.")

        print(f"\n=== REJECTED ON FUNDAMENTALS/SECTOR ({len(rejected_df)}) ===")
        print(rejected_df.to_string(index=False) if not rejected_df.empty else "None.")

        matches_path = os.path.join(args.output_dir, f"bounce_fundamentals_{today}.csv")
        rejected_path = os.path.join(args.output_dir, f"bounce_fundamentals_rejected_{today}.csv")
        report_path = os.path.join(args.output_dir, f"bounce_fundamentals_report_{today}.md")
        matches_df.to_csv(matches_path, index=False)
        rejected_df.to_csv(rejected_path, index=False)
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(_build_bounce_fundamentals_markdown_report(
                matches_df, rejected_df, result["universe_size"], result["history_fetched"],
                result["technical_candidates"]))
        print(f"\nSaved: {matches_path}")
        print(f"Saved: {rejected_path}")
        print(f"Saved: {report_path}")
        return

    if args.strategy == "backtest-support-zone-rr":
        result = run_backtest_rr(csv_dir=args.csv_dir, info_sleep_seconds=args.info_sleep)
        trades_df = _format_backtest_rr_trades(result["trades"])

        print(f"\nUniverse: {result['universe_size']} tickers "
              f"({result['excluded_count']} excluded, price history fetched for "
              f"{result['history_fetched']}) over the last {result['period']}\n")
        print(f"=== BACKTEST RESULTS ({result['total_signals']} signals, "
              f"{result['risk_reward_multiple']:.0f}:1 fixed R:R) ===")
        print(f"Win rate: {result['win_rate_pct']:.1f}%  "
              f"Avg R-multiple: {result['avg_r_multiple']:+.3f}  "
              f"Wins/Losses/TimeExits: {result['wins']}/{result['losses']}/{result['time_exits']}")

        trades_path = os.path.join(args.output_dir, f"backtest_support_zone_rr_trades_{today}.csv")
        report_path = os.path.join(args.output_dir, f"backtest_support_zone_rr_report_{today}.md")
        trades_df.to_csv(trades_path, index=False)
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(_build_backtest_rr_markdown_report(result))
        print(f"\nSaved: {trades_path}")
        print(f"Saved: {report_path}")
        return

    if args.strategy == "backtest-support-zone-mtf":
        result = run_backtest_mtf(csv_dir=args.csv_dir, info_sleep_seconds=args.info_sleep)
        trades_df = _format_backtest_mtf_trades(result["trades"])

        print(f"\nUniverse: {result['universe_size']} tickers "
              f"({result['excluded_count']} excluded, price history fetched for "
              f"{result['history_fetched']}) over the last {result['period']} "
              f"(signals counted in the last {result['test_window_years']}y)\n")
        print(f"=== BACKTEST RESULTS ({result['total_signals']} signals) ===")
        print(f"Win rate: {result['win_rate_pct']:.1f}%  "
              f"Avg R-multiple: {result['avg_r_multiple']:+.3f}  "
              f"Wins/Losses/TimeExits: {result['wins']}/{result['losses']}/{result['time_exits']}")

        trades_path = os.path.join(args.output_dir, f"backtest_support_zone_mtf_trades_{today}.csv")
        report_path = os.path.join(args.output_dir, f"backtest_support_zone_mtf_report_{today}.md")
        trades_df.to_csv(trades_path, index=False)
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(_build_backtest_mtf_markdown_report(result))
        print(f"\nSaved: {trades_path}")
        print(f"Saved: {report_path}")
        return

    if args.strategy == "backtest-support-zone":
        result = run_backtest(csv_dir=args.csv_dir, info_sleep_seconds=args.info_sleep)
        trades_df = _format_backtest_trades(result["trades"])

        print(f"\nUniverse: {result['universe_size']} tickers "
              f"({result['excluded_count']} excluded, price history fetched for "
              f"{result['history_fetched']}) over the last {result['period']}\n")
        print(f"=== BACKTEST RESULTS ({result['total_signals']} signals) ===")
        print(f"Win rate: {result['win_rate_pct']:.1f}%  "
              f"Avg R-multiple: {result['avg_r_multiple']:+.3f}  "
              f"Wins/Losses/TimeExits: {result['wins']}/{result['losses']}/{result['time_exits']}")

        trades_path = os.path.join(args.output_dir, f"backtest_support_zone_trades_{today}.csv")
        report_path = os.path.join(args.output_dir, f"backtest_support_zone_report_{today}.md")
        trades_df.to_csv(trades_path, index=False)
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(_build_backtest_markdown_report(result))
        print(f"\nSaved: {trades_path}")
        print(f"Saved: {report_path}")
        return

    if args.strategy == "divergence":
        result = run_divergence_screen(csv_dir=args.csv_dir, info_sleep_seconds=args.info_sleep)
        df = _format_divergence(result["matches"])

        print(f"\nUniverse: {result['universe_size']} tickers "
              f"(price history fetched for {result['history_fetched']})\n")
        print(f"=== BULLISH RSI DIVERGENCE ({len(df)}) ===")
        print(df.to_string(index=False) if not df.empty else "No divergence found.")

        out_path = os.path.join(args.output_dir, f"divergence_{today}.csv")
        report_path = os.path.join(args.output_dir, f"divergence_report_{today}.md")
        df.to_csv(out_path, index=False)
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(_build_divergence_markdown_report(df, result["universe_size"], result["history_fetched"]))
        print(f"\nSaved: {out_path}")
        print(f"Saved: {report_path}")
        return

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
