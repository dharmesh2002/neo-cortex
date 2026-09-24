#!/usr/bin/env python3
"""Fills in exit_date/exit_price/exit_reason/R for open signals in
signals_log.csv from price data after the signal date, and prints running
forward-test stats (trades, win rate, average R, expectancy).

Run any time -- typically once a day, or whenever you want an updated
scorecard:

    python -m swing_screener.update_log
"""

import argparse
import logging

import pandas as pd

from . import data
from .config import load_config
from .logbook import LOG_COLUMNS, load_log

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("swing_screener.update_log")


def _resolve_exit(df: pd.DataFrame, entry_date: pd.Timestamp, entry: float, stop: float, target: float):
    """Walk forward day-by-day after entry_date; return
    (exit_date, exit_price, exit_reason) or (None, None, None) if still open.
    If both stop and target are hit on the same day, the stop is assumed hit
    first (worse case)."""
    future = df[df.index > entry_date]
    for ts, row in future.iterrows():
        hit_stop = row["Low"] <= stop
        hit_target = row["High"] >= target
        if hit_stop and hit_target:
            return ts.date().isoformat(), stop, "stop (same-day target also hit; stop assumed first)"
        if hit_stop:
            return ts.date().isoformat(), stop, "stop"
        if hit_target:
            return ts.date().isoformat(), target, "target"
    return None, None, None


def update_log(config) -> pd.DataFrame:
    log_df = load_log(config.signals_log_file)
    if log_df.empty:
        logger.info("signals_log.csv is empty or doesn't exist yet -- nothing to update.")
        return log_df

    # A fully-blank exit_date/exit_reason/exit_price/R column round-trips
    # through CSV as float64 NaN; force them back to a dtype that can hold
    # the string/float values update_log writes into open rows.
    log_df["exit_date"] = log_df["exit_date"].astype(object)
    log_df["exit_reason"] = log_df["exit_reason"].astype(object)
    log_df["exit_price"] = log_df["exit_price"].astype(float)
    log_df["R"] = log_df["R"].astype(float)

    open_mask = log_df["exit_date"].isna() | (log_df["exit_date"].astype(str).str.strip() == "")
    open_rows = log_df[open_mask]
    logger.info("%d open signal(s) to check against %d total logged", len(open_rows), len(log_df))

    updated = 0
    for idx, row in open_rows.iterrows():
        symbol = row["symbol"]
        entry_date = pd.Timestamp(row["date"])
        entry, stop, target = float(row["entry"]), float(row["stop"]), float(row["target"])

        df = data.fetch_one(symbol + ".NS", config)
        if df is None or df.empty:
            logger.warning("No price data for %s; leaving open.", symbol)
            continue

        exit_date, exit_price, exit_reason = _resolve_exit(df, entry_date, entry, stop, target)
        if exit_date is None:
            continue

        r_multiple = (exit_price - entry) / (entry - stop) if (entry - stop) else float("nan")
        log_df.loc[idx, "exit_date"] = exit_date
        log_df.loc[idx, "exit_price"] = exit_price
        log_df.loc[idx, "exit_reason"] = exit_reason
        log_df.loc[idx, "R"] = round(r_multiple, 3)
        updated += 1

    if updated:
        log_df.to_csv(config.signals_log_file, index=False, columns=LOG_COLUMNS)
        logger.info("Updated %d signal(s) with exit data.", updated)
    else:
        logger.info("No signals reached stop or target yet.")

    return log_df


def print_stats(log_df: pd.DataFrame) -> None:
    closed = log_df.dropna(subset=["R"])
    closed = closed[closed["R"].astype(str).str.strip() != ""]

    print("=" * 60)
    print("FORWARD-TEST STATS")
    print("=" * 60)
    print(f"Total signals logged : {len(log_df)}")
    print(f"Closed trades        : {len(closed)}")
    print(f"Open trades          : {len(log_df) - len(closed)}")

    if closed.empty:
        print("No closed trades yet -- stats will populate once signals hit stop or target.")
        print("=" * 60)
        return

    r_values = closed["R"].astype(float)
    wins = r_values[r_values > 0]
    win_rate = len(wins) / len(r_values) * 100
    avg_r = r_values.mean()

    print(f"Win rate             : {win_rate:.1f}%")
    print(f"Average R            : {avg_r:+.3f}")
    print(f"Expectancy (R/trade) : {avg_r:+.3f}")
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=None, help="Path to config.yaml")
    args = parser.parse_args()

    config = load_config(args.config)
    log_df = update_log(config)
    print_stats(log_df)


if __name__ == "__main__":
    main()
