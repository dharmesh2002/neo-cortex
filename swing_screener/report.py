"""Terminal report + markdown/CSV output. Pure formatting -- no signal logic."""

import math
import os
from typing import List

import pandas as pd
from tabulate import tabulate

from .market_context import MarketContext

SIGNAL_COLUMNS = [
    "Score", "Symbol", "Sector", "Entry", "Stop", "Target", "Shares",
    "Capital (Rs)", "Risk (Rs)", "R:R", "RS", "Sector>SMA50", "NiftyRange", "ADX<25", "Delivery",
]

NEAR_MISS_COLUMNS = ["Symbol", "Sector", "Missing", "Detail"]


def market_context_lines(ctx: MarketContext) -> List[str]:
    lines = [
        "=" * 70,
        "MARKET CONTEXT",
        "=" * 70,
        f"Nifty 50 Close        : {ctx.nifty_close:,.2f}",
        f"Nifty 200 EMA          : {ctx.nifty_ema200:,.2f} "
        f"({'above' if ctx.above_ema200 else 'below'})",
        f"60-day range position : {ctx.range_position_pct:.1f}% "
        f"({'lower half' if ctx.in_lower_half_of_range else 'upper half'})",
        f"Nifty ADX(14)          : {ctx.nifty_adx:.1f}" if not math.isnan(ctx.nifty_adx) else "Nifty ADX(14)          : n/a",
        f"India VIX              : {ctx.vix:.2f}" if not math.isnan(ctx.vix) else "India VIX              : n/a",
        f"Regime                 : {ctx.regime}",
        "=" * 70,
    ]
    return lines


def signals_to_dataframe(signal_rows: List[dict]) -> pd.DataFrame:
    if not signal_rows:
        return pd.DataFrame(columns=SIGNAL_COLUMNS)
    df = pd.DataFrame(signal_rows)
    df = df[SIGNAL_COLUMNS]
    for col in ["Entry", "Stop", "Target", "Capital (Rs)", "Risk (Rs)"]:
        df[col] = df[col].round(2)
    df["R:R"] = df["R:R"].round(2)
    return df


def near_miss_to_dataframe(near_miss_rows: List[dict]) -> pd.DataFrame:
    if not near_miss_rows:
        return pd.DataFrame(columns=NEAR_MISS_COLUMNS)
    df = pd.DataFrame(near_miss_rows)
    return df[NEAR_MISS_COLUMNS]


def print_report(ctx: MarketContext, signals_df: pd.DataFrame, near_miss_df: pd.DataFrame,
                  universe_size: int, screened_count: int, run_date: str, capital: float, risk_pct: float) -> None:
    print()
    for line in market_context_lines(ctx):
        print(line)

    print()
    print(f"NSE Swing Screener -- {run_date}")
    print(f"Universe: {universe_size} names (post-exclusion) | History fetched for {screened_count}")
    print(f"Capital: Rs {capital:,.0f} | Risk per trade: {risk_pct * 100:.2f}%")
    print()
    print("-" * 70)
    print(f"SIGNALS ({len(signals_df)})")
    print("-" * 70)
    if signals_df.empty:
        print("No signals today.")
    else:
        print(tabulate(signals_df, headers="keys", tablefmt="github", showindex=False))

    print()
    print("-" * 70)
    print(f"NEAR-MISS WATCHLIST ({len(near_miss_df)}) -- exactly 2 of 3 core conditions met")
    print("-" * 70)
    if near_miss_df.empty:
        print("No near-misses today.")
    else:
        print(tabulate(near_miss_df, headers="keys", tablefmt="github", showindex=False))
    print()


def save_report(ctx: MarketContext, signals_df: pd.DataFrame, near_miss_df: pd.DataFrame,
                 universe_size: int, screened_count: int, run_date: str, capital: float,
                 risk_pct: float, reports_dir: str, delivery_note: str = "") -> None:
    os.makedirs(reports_dir, exist_ok=True)

    md_lines = [f"# NSE Swing Screener Report -- {run_date}", ""]
    md_lines += ["```"] + market_context_lines(ctx) + ["```", ""]
    md_lines += [
        f"Universe: {universe_size} names (post-exclusion) | History fetched for {screened_count}",
        f"Capital: Rs {capital:,.0f} | Risk per trade: {risk_pct * 100:.2f}%",
        "",
        f"## Signals ({len(signals_df)})",
        "",
    ]
    if signals_df.empty:
        md_lines.append("No signals today.")
    else:
        md_lines.append(tabulate(signals_df, headers="keys", tablefmt="github", showindex=False))
    md_lines += ["", f"## Near-miss watchlist ({len(near_miss_df)})", ""]
    if near_miss_df.empty:
        md_lines.append("No near-misses today.")
    else:
        md_lines.append(tabulate(near_miss_df, headers="keys", tablefmt="github", showindex=False))

    if delivery_note:
        md_lines += ["", f"> {delivery_note}"]

    md_path = os.path.join(reports_dir, f"report_{run_date}.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(md_lines) + "\n")

    csv_path = os.path.join(reports_dir, f"signals_{run_date}.csv")
    signals_df.to_csv(csv_path, index=False)

    return md_path, csv_path
