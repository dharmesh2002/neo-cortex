"""Append every day's signals to signals_log.csv for forward-test tracking.
update_log.py later fills in the blank exit_date/exit_price/exit_reason/R
columns once a signal's stop or target is hit.
"""

import os
from typing import List

import pandas as pd

LOG_COLUMNS = [
    "date", "symbol", "sector", "entry", "stop", "target", "shares",
    "capital_required", "rupee_risk", "reward_risk_ratio",
    "rs_check", "sector_check", "nifty_range_check", "adx_check", "delivery_check", "score",
    "exit_date", "exit_price", "exit_reason", "R",
]


def append_signals(signal_rows: List[dict], log_path: str) -> None:
    """signal_rows: list of dicts with the LOG_COLUMNS keys (minus the exit
    columns, which are written blank)."""
    if not signal_rows:
        return

    rows = []
    for row in signal_rows:
        entry = {col: row.get(col, "") for col in LOG_COLUMNS}
        rows.append(entry)

    df = pd.DataFrame(rows, columns=LOG_COLUMNS)
    file_exists = os.path.exists(log_path)
    df.to_csv(log_path, mode="a", header=not file_exists, index=False)


def load_log(log_path: str) -> pd.DataFrame:
    if not os.path.exists(log_path):
        return pd.DataFrame(columns=LOG_COLUMNS)
    return pd.read_csv(log_path)
