"""Backtest of a multi-timeframe-confirmed version of the support-zone rule.

Adds two conditions on top of the plain daily support-zone rule (RSI(14)
30-45 AND close between the Bollinger lower/mid band, tested as-is in
backtest_support_zone.py):

- Weekly RSI(14) > 50 and Monthly RSI(14) > 50 -- the idea being tested is
  that a stock dipping into the daily zone while its *higher timeframe*
  trend is still constructive is a healthy pullback within a strong trend,
  not a stock that's genuinely breaking down.
- Volume on the signal day itself > the prior 20-day average volume -- a
  pickup in volume on the bounce day meant to confirm real buying interest
  rather than a low-conviction drift back into the zone.

Weekly/monthly RSI is computed on resampled closes and forward-filled back
onto the daily calendar. Because each resampled label is that period's own
last trading day, a forward-fill lookup for any day still inside an
in-progress week/month always resolves to the last *completed* period's
value -- there is no way for a day to see its own not-yet-finished
week/month's RSI ahead of time.
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
HIGHER_TF_RSI_MIN = 50.0
LIQUIDITY_THRESHOLD_INR = 20 * 1e7
BB_WINDOW = 20
RSI_PERIOD = 14
ATR_PERIOD = 14
MAX_HOLDING_DAYS = 20
# Extra history purely to warm up weekly/monthly RSI (each needs ~14 of its
# own periods before Wilder's smoothing stops returning NaN) -- fetching
# only "2y" would leave monthly RSI valid for just the last few months of
# the window instead of throughout it.
DOWNLOAD_PERIOD = "5y"
TEST_WINDOW_YEARS = 2  # signals are only counted within this recent window
MIN_HISTORY_ROWS = 100


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
    weekly_rsi: float
    monthly_rsi: float


def _to_date_str(value) -> str:
    return str(value.date()) if hasattr(value, "date") else str(value)


def _higher_timeframe_rsi(close: pd.Series, daily_index: pd.DatetimeIndex, rule: str) -> pd.Series:
    """Resample close to the given pandas offset rule (e.g. 'W-FRI', 'ME'),
    compute RSI(14) on that resampled series, then forward-fill it back onto
    the daily calendar."""
    resampled_close = close.resample(rule).last().dropna()
    resampled_rsi = rsi(resampled_close, period=RSI_PERIOD)
    return resampled_rsi.reindex(daily_index, method="ffill")


def _simulate_trades_for_ticker(ticker: str, df: pd.DataFrame) -> List[Trade]:
    df = df.dropna(subset=["Close", "High", "Low", "Volume"])
    if len(df) < MIN_HISTORY_ROWS:
        return []

    close, high, low, volume = df["Close"], df["High"], df["Low"], df["Volume"]
    mid_bb, _, lower_bb = bollinger_bands(close, window=BB_WINDOW)
    rsi_series = rsi(close, period=RSI_PERIOD)
    atr_series = atr(high, low, close, period=ATR_PERIOD)
    avg_daily_value_20d = (close * volume).rolling(window=20).mean()
    avg_volume_prior20 = volume.shift(1).rolling(window=20).mean()

    weekly_rsi_daily = _higher_timeframe_rsi(close, df.index, "W-FRI")
    monthly_rsi_daily = _higher_timeframe_rsi(close, df.index, "ME")

    in_zone = (
        (close >= lower_bb) & (close <= mid_bb)
        & (rsi_series >= RSI_MIN) & (rsi_series <= RSI_MAX)
        & (avg_daily_value_20d >= LIQUIDITY_THRESHOLD_INR)
        & (weekly_rsi_daily > HIGHER_TF_RSI_MIN)
        & (monthly_rsi_daily > HIGHER_TF_RSI_MIN)
        & (volume > avg_volume_prior20)
    ).fillna(False)

    cutoff_date = df.index.max() - pd.DateOffset(years=TEST_WINDOW_YEARS)

    trades: List[Trade] = []
    n = len(df)
    for i in range(1, n):
        # Only a fresh entry into the (now much narrower) zone counts as a
        # signal -- same dedup logic as the plain support-zone backtest.
        if not in_zone.iloc[i] or in_zone.iloc[i - 1]:
            continue
        if df.index[i] < cutoff_date:
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
            weekly_rsi=float(weekly_rsi_daily.iloc[i]),
            monthly_rsi=float(monthly_rsi_daily.iloc[i]),
        ))
    return trades


def run_backtest(csv_dir: str = None, info_sleep_seconds: float = 0.3,
                  period: str = DOWNLOAD_PERIOD) -> Dict:
    universe = build_universe(csv_dir=csv_dir)
    tickers = universe["Ticker"].tolist()

    # Sector/industry doesn't change day to day, so fetch it once per ticker
    # up front rather than per-signal.
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
        "test_window_years": TEST_WINDOW_YEARS,
    }
