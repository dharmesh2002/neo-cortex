"""Historical backtest of the decline-reversal-near-support rule, against
real market data (not synthetic) -- pulls ~2 years of actual daily history
for the 150-stock universe from yfinance, the same source every live
screener in this project uses, and finds every real historical occurrence
of the pattern: 3 real trading days each closing lower than the day before,
followed by a real green reversal candle (closes above its own open and
above the prior close), landing within 2% of a real, computed support level
(SMAs, swing lows, or the Bollinger lower band).

For every real historical occurrence, simulates a trade using the same
entry/stop/target methodology used across this project (entry at that
day's close, stop at entry - 0.75*ATR14, target at entry*1.03) and reports
a real win rate and average R-multiple for this exact rule -- the same
kind of validation already run for the support-zone strategy (which came
back break-even-to-negative across several variants) and the original
bounce rule (which came back positive, +0.1195R).
"""

import logging
import time
from dataclasses import dataclass
from typing import Dict, List

import pandas as pd
import yfinance as yf

from .indicators import atr, bollinger_bands
from .screener import ATR_STOP_MULTIPLE, TARGET_GAIN_PCT, fetch_price_history
from .universe import build_universe, is_excluded

logger = logging.getLogger(__name__)

DECLINE_STREAK_DAYS = 3
SUPPORT_TOLERANCE_PCT = 2.0
LIQUIDITY_THRESHOLD_INR = 20 * 1e7
SMA_WINDOWS = (20, 50, 100, 200)
SWING_LOW_WINDOWS = (20, 60, 120, 252)
BB_WINDOW = 20
ATR_PERIOD = 14
MAX_HOLDING_DAYS = 20
BACKTEST_PERIOD = "2y"
MIN_HISTORY_ROWS = 260  # need real history for the 252-day swing low / 200-day SMA


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
    pct_above_support: float


def _to_date_str(value) -> str:
    return str(value.date()) if hasattr(value, "date") else str(value)


def _nearest_support_series(close: pd.Series, low: pd.Series) -> pd.DataFrame:
    """Real support levels as of each historical day -- every level here is a
    trailing rolling computation (SMA / rolling min / Bollinger band), so a
    value at position i only ever uses data up to and including day i, the
    same no-lookahead guarantee pandas rolling windows give everywhere else
    in this project."""
    levels = pd.DataFrame(index=close.index)
    for window in SMA_WINDOWS:
        levels[f"sma_{window}"] = close.rolling(window=window).mean()
    for window in SWING_LOW_WINDOWS:
        levels[f"low_{window}d"] = low.rolling(window=window).min()
    _, _, bb_lower = bollinger_bands(close, window=BB_WINDOW)
    levels["bb_lower"] = bb_lower
    return levels


def _simulate_trades_for_ticker(ticker: str, df: pd.DataFrame) -> List[Trade]:
    df = df.dropna(subset=["Close", "Open", "High", "Low", "Volume"])
    if len(df) < MIN_HISTORY_ROWS:
        return []

    close, open_, high, low, volume = df["Close"], df["Open"], df["High"], df["Low"], df["Volume"]
    atr_series = atr(high, low, close, period=ATR_PERIOD)
    avg_daily_value_20d = (close * volume).rolling(window=20).mean()
    levels = _nearest_support_series(close, low)

    n = len(df)
    trades: List[Trade] = []
    for i in range(DECLINE_STREAK_DAYS + 1, n):
        # Real 3-day decline ending the day before today: each of the 3 days
        # right before today closed lower than the day before it.
        decline = True
        for k in range(0, DECLINE_STREAK_DAYS):
            if not (close.iloc[i - 1 - k] < close.iloc[i - 2 - k]):
                decline = False
                break
        if not decline:
            continue

        close_today, open_today, close_prev = float(close.iloc[i]), float(open_.iloc[i]), float(close.iloc[i - 1])
        if not (close_today > open_today and close_today > close_prev):
            continue

        if pd.isna(avg_daily_value_20d.iloc[i]) or avg_daily_value_20d.iloc[i] < LIQUIDITY_THRESHOLD_INR:
            continue
        if pd.isna(atr_series.iloc[i]) or atr_series.iloc[i] <= 0:
            continue

        row = levels.iloc[i]
        below = [v for v in row.values if pd.notna(v) and v < close_today]
        if not below:
            continue
        nearest_support = max(below)
        pct_above_support = (close_today - nearest_support) / nearest_support * 100
        if pct_above_support > SUPPORT_TOLERANCE_PCT:
            continue

        entry = close_today
        stop_loss = entry - ATR_STOP_MULTIPLE * float(atr_series.iloc[i])
        if stop_loss >= entry:
            continue
        target = entry * (1 + TARGET_GAIN_PCT)

        exit_reason, exit_price, exit_idx, resolved = "time", entry, i, False
        for j in range(i + 1, min(i + 1 + MAX_HOLDING_DAYS, n)):
            day_low, day_high = float(low.iloc[j]), float(high.iloc[j])
            hit_stop = day_low <= stop_loss
            hit_target = day_high >= target
            if hit_stop:
                # Conservative: assume the stop hit first if both trigger the
                # same day -- daily bars can't show the real intraday order.
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
            pct_above_support=pct_above_support,
        ))
    return trades


def run_backtest(csv_dir: str = None, info_sleep_seconds: float = 0.3,
                  period: str = BACKTEST_PERIOD) -> Dict:
    universe = build_universe(csv_dir=csv_dir)
    tickers = universe["Ticker"].tolist()

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
    logger.info("Fetched %s of real history for %d/%d tickers", period, len(history), len(tickers))

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
