"""Historical backtest of the BB Bounce Buy strategy: signal candle low touches
or crosses the lower Bollinger Band (20-period, 2 std) AND RSI(14) < 40 AND
volume spike (today > prior 20-day average) AND close above the 200-day SMA.

Entry  : signal candle close
Stop   : signal candle low  (the explicit stop level per the live strategy)
Target : middle band (20-day SMA) at signal time — same as the live strategy target
Hold   : up to MAX_HOLDING_DAYS; time-exit at that day's close if neither hit

A fresh entry is counted only when the stock transitions INTO the signal state,
so a stock that stays below the lower band for several days only counts once.
"""

import logging
import time
from dataclasses import dataclass
from typing import Dict, List

import pandas as pd
import yfinance as yf

from .indicators import bollinger_bands, rsi
from .screener import fetch_price_history
from .universe import build_universe, is_excluded

logger = logging.getLogger(__name__)

BB_WINDOW = 20
RSI_PERIOD = 14
RSI_OVERSOLD = 40.0
MIN_VOLUME_SHARES = 500_000
LIQUIDITY_THRESHOLD_INR = 20 * 1e7
MAX_HOLDING_DAYS = 20
BACKTEST_PERIOD = "2y"
MIN_HISTORY_ROWS = 60


@dataclass
class BBBuyTrade:
    ticker: str
    signal_date: str
    entry: float
    stop_loss: float       # signal candle low
    target: float          # mid band at signal time
    exit_date: str
    exit_reason: str       # "target", "stop", "time"
    exit_price: float
    days_held: int
    r_multiple: float
    pct_to_target: float   # % from entry to target at signal time
    pct_stop_dist: float   # % from entry down to stop


def _to_date_str(value) -> str:
    return str(value.date()) if hasattr(value, "date") else str(value)


def _simulate_trades_for_ticker(ticker: str, df: pd.DataFrame) -> List[BBBuyTrade]:
    df = df.dropna(subset=["Close", "High", "Low", "Volume"])
    if len(df) < MIN_HISTORY_ROWS:
        return []

    close = df["Close"]
    high = df["High"]
    low = df["Low"]
    volume = df["Volume"]

    mid, _, lower = bollinger_bands(close, window=BB_WINDOW)
    rsi_series = rsi(close, period=RSI_PERIOD)
    sma200 = close.rolling(window=200).mean()
    avg_volume_20d = volume.shift(1).rolling(window=20).mean()
    avg_daily_value_20d = (close * volume).rolling(window=20).mean()

    in_signal = (
        (low <= lower)
        & (rsi_series < RSI_OVERSOLD)
        & (volume > avg_volume_20d)
        & (close > sma200)
        & (avg_daily_value_20d >= LIQUIDITY_THRESHOLD_INR)
        & (avg_volume_20d >= MIN_VOLUME_SHARES)
    ).fillna(False)

    trades: List[BBBuyTrade] = []
    n = len(df)
    for i in range(1, n):
        # Fresh entry only: transitions from not-in-signal to in-signal
        if not in_signal.iloc[i] or in_signal.iloc[i - 1]:
            continue
        if pd.isna(mid.iloc[i]) or pd.isna(low.iloc[i]):
            continue

        entry = float(close.iloc[i])
        stop_loss = float(low.iloc[i])       # signal candle low
        target = float(mid.iloc[i])          # middle band at signal time
        if stop_loss >= entry or target <= entry:
            continue

        risk_per_share = entry - stop_loss

        exit_reason, exit_price, exit_idx, resolved = "time", entry, i, False
        for j in range(i + 1, min(i + 1 + MAX_HOLDING_DAYS, n)):
            day_low = float(low.iloc[j])
            day_high = float(high.iloc[j])
            hit_stop = day_low <= stop_loss
            hit_target = day_high >= target
            if hit_stop:
                exit_reason, exit_price, exit_idx, resolved = "stop", stop_loss, j, True
            elif hit_target:
                exit_reason, exit_price, exit_idx, resolved = "target", target, j, True
            else:
                continue
            break

        if not resolved:
            exit_idx = min(i + MAX_HOLDING_DAYS, n - 1)
            exit_reason = "time"
            exit_price = float(close.iloc[exit_idx])

        r_multiple = (exit_price - entry) / risk_per_share if risk_per_share > 0 else 0.0

        trades.append(BBBuyTrade(
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
            pct_to_target=(target - entry) / entry * 100,
            pct_stop_dist=(entry - stop_loss) / entry * 100,
        ))
    return trades


def run_backtest(csv_dir: str = None, info_sleep_seconds: float = 0.3,
                  period: str = BACKTEST_PERIOD, nifty100_only: bool = False) -> Dict:
    from .bb_buy_strategy import NIFTY100_INDICES

    universe = build_universe(csv_dir=csv_dir)
    if nifty100_only:
        universe = universe[universe["Index"].isin(NIFTY100_INDICES)].reset_index(drop=True)
    tickers = universe["Ticker"].tolist()

    excluded_tickers: set = set()
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

    all_trades: List[BBBuyTrade] = []
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
    avg_r = (sum(t.r_multiple for t in all_trades) / total) if total else 0.0
    avg_days_winners = (sum(t.days_held for t in wins) / len(wins)) if wins else 0.0
    avg_pct_to_target = (sum(t.pct_to_target for t in all_trades) / total) if total else 0.0
    avg_pct_stop = (sum(t.pct_stop_dist for t in all_trades) / total) if total else 0.0

    return {
        "trades": all_trades,
        "total_signals": total,
        "wins": len(wins),
        "losses": len(losses),
        "time_exits": len(time_exits),
        "time_exit_wins": len(time_exit_wins),
        "win_rate_pct": win_rate_pct,
        "avg_r_multiple": avg_r,
        "avg_days_held_winners": avg_days_winners,
        "avg_pct_to_target": avg_pct_to_target,
        "avg_pct_stop_dist": avg_pct_stop,
        "universe_size": len(tickers),
        "excluded_count": len(excluded_tickers),
        "history_fetched": len(history),
        "period": period,
        "nifty100_only": nifty100_only,
    }
