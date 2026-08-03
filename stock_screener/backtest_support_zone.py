"""Historical backtest of the "support zone" rule: RSI(14) between 30 and 45
AND close between the Bollinger lower and middle band, on the daily chart --
the exact rule behind the live `support-zone` strategy, which has always been
reported with "no backtest exists for this scan" attached to it.

This module answers that question for real: for every day a stock freshly
enters the zone (transitions in from outside it, so a multi-day stay in the
zone only counts once) over the last ~2 years, simulate a trade using the
same entry/stop/target methodology used elsewhere in this project (entry at
that day's close, stop at entry - 0.75*ATR14, target at entry*1.03) and see
whether the target, the stop, or neither was hit first.
"""

import logging
import time
from dataclasses import dataclass
from typing import Dict, List

import pandas as pd
import yfinance as yf

from .indicators import atr, bollinger_bands, rsi
from .screener import ATR_STOP_MULTIPLE, TARGET_GAIN_PCT, fetch_price_history
from .universe import build_universe, is_excluded

logger = logging.getLogger(__name__)

RSI_MIN = 30.0
RSI_MAX = 45.0
LIQUIDITY_THRESHOLD_INR = 20 * 1e7
BB_WINDOW = 20
RSI_PERIOD = 14
ATR_PERIOD = 14
MAX_HOLDING_DAYS = 20
BACKTEST_PERIOD = "2y"
MIN_HISTORY_ROWS = 60


@dataclass
class Trade:
    ticker: str
    signal_date: str
    entry: float
    stop_loss: float
    target: float
    exit_date: str
    exit_reason: str  # "target", "stop", "time"
    exit_price: float
    days_held: int
    r_multiple: float


def _to_date_str(value) -> str:
    return str(value.date()) if hasattr(value, "date") else str(value)


def _simulate_trades_for_ticker(ticker: str, df: pd.DataFrame) -> List[Trade]:
    df = df.dropna(subset=["Close", "High", "Low", "Volume"])
    if len(df) < MIN_HISTORY_ROWS:
        return []

    close, high, low, volume = df["Close"], df["High"], df["Low"], df["Volume"]
    mid_bb, _, lower_bb = bollinger_bands(close, window=BB_WINDOW)
    rsi_series = rsi(close, period=RSI_PERIOD)
    atr_series = atr(high, low, close, period=ATR_PERIOD)
    avg_daily_value_20d = (close * volume).rolling(window=20).mean()

    in_zone = (
        (close >= lower_bb) & (close <= mid_bb)
        & (rsi_series >= RSI_MIN) & (rsi_series <= RSI_MAX)
        & (avg_daily_value_20d >= LIQUIDITY_THRESHOLD_INR)
    ).fillna(False)

    trades: List[Trade] = []
    n = len(df)
    for i in range(1, n):
        # Only a fresh entry into the zone counts as a signal -- otherwise a
        # stock sitting in the zone for a week gets counted as 5-7 separate
        # "trades" on the same underlying setup.
        if not in_zone.iloc[i] or in_zone.iloc[i - 1]:
            continue
        if pd.isna(atr_series.iloc[i]) or atr_series.iloc[i] <= 0:
            continue

        entry = float(close.iloc[i])
        stop_loss = entry - ATR_STOP_MULTIPLE * float(atr_series.iloc[i])
        target = entry * (1 + TARGET_GAIN_PCT)
        if stop_loss >= entry:
            continue

        exit_reason, exit_price, exit_idx, resolved = "time", entry, i, False
        for j in range(i + 1, min(i + 1 + MAX_HOLDING_DAYS, n)):
            day_low, day_high = float(low.iloc[j]), float(high.iloc[j])
            hit_stop = day_low <= stop_loss
            hit_target = day_high >= target
            if hit_stop:
                # Conservative: if both the stop and target are inside the
                # same day's range, assume the stop was hit first -- daily
                # bars can't tell us the real intraday sequence, and assuming
                # the worse outcome avoids overstating the win rate.
                exit_reason, exit_price, exit_idx, resolved = "stop", stop_loss, j, True
            elif hit_target:
                exit_reason, exit_price, exit_idx, resolved = "target", target, j, True
            else:
                continue
            break

        if not resolved:
            exit_idx = min(i + MAX_HOLDING_DAYS, n - 1)
            exit_reason, exit_price = "time", float(close.iloc[exit_idx])

        risk_per_share = entry - stop_loss
        r_multiple = (exit_price - entry) / risk_per_share if risk_per_share > 0 else 0.0

        trades.append(Trade(
            ticker=ticker,
            signal_date=_to_date_str(df.index[i]),
            entry=entry,
            stop_loss=stop_loss,
            target=target,
            exit_date=_to_date_str(df.index[exit_idx]),
            exit_reason=exit_reason,
            exit_price=exit_price,
            days_held=exit_idx - i,
            r_multiple=r_multiple,
        ))
    return trades


def run_backtest(csv_dir: str = None, info_sleep_seconds: float = 0.3,
                  period: str = BACKTEST_PERIOD) -> Dict:
    universe = build_universe(csv_dir=csv_dir)
    tickers = universe["Ticker"].tolist()

    # Sector/industry doesn't change day to day, so fetch it once per ticker
    # up front rather than per-signal -- lets exclusion apply across the
    # whole backtest without hundreds of redundant .info calls.
    excluded_tickers = set()
    for ticker in tickers:
        try:
            info = yf.Ticker(ticker).info or {}
        except Exception as exc:
            logger.warning("Could not fetch sector/industry for %s: %s", ticker, exc)
            info = {}
        time.sleep(info_sleep_seconds)
        if is_excluded(info.get("sector", ""), info.get("industry", "")):
            excluded_tickers.add(ticker)

    history = fetch_price_history(tickers, period=period)
    logger.info("Fetched %s history for %d/%d tickers", period, len(history), len(tickers))

    all_trades: List[Trade] = []
    for ticker, df in history.items():
        if ticker in excluded_tickers:
            continue
        all_trades.extend(_simulate_trades_for_ticker(ticker, df))

    wins = [t for t in all_trades if t.exit_reason == "target"]
    losses = [t for t in all_trades if t.exit_reason == "stop"]
    time_exits = [t for t in all_trades if t.exit_reason == "time"]
    time_exit_wins = [t for t in time_exits if t.r_multiple > 0]

    total = len(all_trades)
    win_count = len(wins) + len(time_exit_wins)
    win_rate_pct = (win_count / total * 100) if total else 0.0
    avg_r_multiple = (sum(t.r_multiple for t in all_trades) / total) if total else 0.0
    avg_days_held_winners = (sum(t.days_held for t in wins) / len(wins)) if wins else 0.0

    return {
        "trades": all_trades,
        "total_signals": total,
        "wins": len(wins),
        "losses": len(losses),
        "time_exits": len(time_exits),
        "time_exit_wins": len(time_exit_wins),
        "win_rate_pct": win_rate_pct,
        "avg_r_multiple": avg_r_multiple,
        "avg_days_held_winners": avg_days_held_winners,
        "universe_size": len(tickers),
        "excluded_count": len(excluded_tickers),
        "history_fetched": len(history),
        "period": period,
    }
