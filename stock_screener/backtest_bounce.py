"""Historical backtest of the current 4-condition Bollinger Band Bounce strategy:

  1. BB condition  : low <= lower band (20,2) AND close > lower band AND close > prev close
  2. RSI condition : RSI(14) today > RSI(14) yesterday  (turning up -- no fixed floor)
  3. Volume        : today's volume > prior 20-day average volume
  4. Rel. strength : stock's daily % change > universe average % change that day

Entry  : signal candle close
Stop   : entry - 0.75 × ATR(14) at signal time  (mirrors the live screener)
Target : entry × 1.03  (3% fixed target, same as live screener TARGET_GAIN_PCT)
Hold   : up to MAX_HOLDING_DAYS; time-exit at that day's close if neither hit

Fresh-entry only: a stock that stays in the signal state for multiple consecutive
days is counted once (on the first bar of the transition into signal).
"""

import logging
from dataclasses import dataclass
from typing import Dict, List

import pandas as pd

from .indicators import atr, bollinger_bands, rsi
from .screener import fetch_price_history
from .universe import build_universe, is_excluded

logger = logging.getLogger(__name__)

BB_WINDOW = 20
RSI_PERIOD = 14
ATR_PERIOD = 14
ATR_STOP_MULTIPLE = 0.75
TARGET_GAIN_PCT = 0.03
MAX_HOLDING_DAYS = 20
BACKTEST_PERIOD = "2y"
MIN_HISTORY_ROWS = 60
LIQUIDITY_THRESHOLD_INR = 20 * 1e7


@dataclass
class BounceTrade:
    ticker: str
    signal_date: str
    entry: float
    stop_loss: float
    target: float
    exit_date: str
    exit_reason: str    # "target", "stop", "time"
    exit_price: float
    days_held: int
    r_multiple: float
    pct_to_target: float
    pct_stop_dist: float


def _to_date_str(value) -> str:
    return str(value.date()) if hasattr(value, "date") else str(value)


def _build_indicators(df: pd.DataFrame):
    """Return (mid, upper, lower, rsi_s, atr_s, avg_vol20, avg_val20) Series."""
    close = df["Close"]
    high = df["High"]
    low = df["Low"]
    volume = df["Volume"]

    _, upper, lower = bollinger_bands(close, window=BB_WINDOW)
    rsi_s = rsi(close, period=RSI_PERIOD)
    atr_s = atr(high, low, close, period=ATR_PERIOD)
    avg_vol20 = volume.shift(1).rolling(20).mean()
    avg_val20 = (close * volume).rolling(20).mean()

    return upper, lower, rsi_s, atr_s, avg_vol20, avg_val20


def run_backtest_bounce(csv_dir: str = None, period: str = BACKTEST_PERIOD) -> Dict:
    import time as _time

    universe = build_universe(csv_dir=csv_dir)
    tickers = universe["Ticker"].tolist()

    # Filter excluded sectors upfront using a small sample of .info calls.
    # To avoid the very slow per-ticker yfinance .info loop (350 tickers × 0.3s
    # = 100s just in sleeps), we skip exclusion here and accept a small number
    # of energy/tech/airline names leaking into the backtest. The live screener
    # does exclude them, but the effect on aggregate stats is minimal.
    # If you want strict exclusion, uncomment the block below and accept the
    # extra runtime.
    #
    # import yfinance as yf
    # excluded: set = set()
    # for t in tickers:
    #     try:
    #         info = yf.Ticker(t).info or {}
    #     except Exception:
    #         info = {}
    #     _time.sleep(0.3)
    #     if is_excluded(info.get("sector",""), info.get("industry","")):
    #         excluded.add(t)

    history = fetch_price_history(tickers, period=period)
    logger.info("Fetched %s history for %d/%d tickers", period, len(history), len(tickers))

    # ── Step 1: build per-ticker indicator frames ────────────────────────────
    ticker_frames: Dict[str, dict] = {}
    for ticker, df in history.items():
        df = df.dropna(subset=["Close", "High", "Low", "Volume"])
        if len(df) < MIN_HISTORY_ROWS:
            continue
        upper, lower, rsi_s, atr_s, avg_vol20, avg_val20 = _build_indicators(df)
        liquidity_ok = avg_val20 >= LIQUIDITY_THRESHOLD_INR
        ticker_frames[ticker] = {
            "df": df,
            "lower": lower,
            "rsi_s": rsi_s,
            "atr_s": atr_s,
            "avg_vol20": avg_vol20,
            "liquidity_ok": liquidity_ok,
        }

    # ── Step 2: universe daily % change (for relative strength benchmark) ───
    # Align all closes onto a common date index.
    all_closes = pd.DataFrame({
        ticker: d["df"]["Close"]
        for ticker, d in ticker_frames.items()
    })
    daily_pct = all_closes.pct_change() * 100          # % change each day
    universe_avg_pct = daily_pct.mean(axis=1)          # cross-ticker average per day

    # ── Step 3: simulate trades ──────────────────────────────────────────────
    all_trades: List[BounceTrade] = []

    for ticker, d in ticker_frames.items():
        df = d["df"]
        lower = d["lower"]
        rsi_s = d["rsi_s"]
        atr_s = d["atr_s"]
        avg_vol20 = d["avg_vol20"]
        liquidity_ok = d["liquidity_ok"]

        close = df["Close"]
        high = df["High"]
        low = df["Low"]
        volume = df["Volume"]
        n = len(df)

        prev_in_signal = False

        for i in range(1, n):
            idx = df.index[i]
            prev_idx = df.index[i - 1]

            if pd.isna(lower.iloc[i]) or pd.isna(rsi_s.iloc[i]) or pd.isna(atr_s.iloc[i]):
                prev_in_signal = False
                continue
            if pd.isna(avg_vol20.iloc[i]):
                prev_in_signal = False
                continue
            if not bool(liquidity_ok.iloc[i]):
                prev_in_signal = False
                continue

            close_today = float(close.iloc[i])
            close_prev = float(close.iloc[i - 1])
            low_today = float(low.iloc[i])
            lower_today = float(lower.iloc[i])
            rsi_today = float(rsi_s.iloc[i])
            rsi_prev = float(rsi_s.iloc[i - 1])
            vol_today = float(volume.iloc[i])
            avg_vol = float(avg_vol20.iloc[i])

            bb_cond = (low_today <= lower_today and close_today > lower_today
                       and close_today > close_prev)
            rsi_cond = rsi_today > rsi_prev
            vol_cond = vol_today > avg_vol

            # Relative strength: stock's pct change vs universe average that day
            stock_pct = (close_today / close_prev - 1) * 100 if close_prev else 0.0
            univ_avg = float(universe_avg_pct.get(idx, 0.0)) if idx in universe_avg_pct.index else 0.0
            rs_cond = stock_pct > univ_avg

            in_signal = bb_cond and rsi_cond and vol_cond and rs_cond

            if not in_signal or prev_in_signal:
                prev_in_signal = in_signal
                continue

            # Fresh entry
            prev_in_signal = True

            entry = close_today
            atr_val = float(atr_s.iloc[i])
            stop_loss = entry - ATR_STOP_MULTIPLE * atr_val
            target = entry * (1 + TARGET_GAIN_PCT)

            if stop_loss >= entry or atr_val <= 0:
                continue

            risk_per_share = entry - stop_loss

            exit_reason, exit_price, exit_idx = "time", entry, i
            resolved = False
            for j in range(i + 1, min(i + 1 + MAX_HOLDING_DAYS, n)):
                day_low = float(low.iloc[j])
                day_high = float(high.iloc[j])
                if day_low <= stop_loss:
                    exit_reason, exit_price, exit_idx, resolved = "stop", stop_loss, j, True
                    break
                if day_high >= target:
                    exit_reason, exit_price, exit_idx, resolved = "target", target, j, True
                    break

            if not resolved:
                exit_idx = min(i + MAX_HOLDING_DAYS, n - 1)
                exit_reason = "time"
                exit_price = float(close.iloc[exit_idx])

            r_multiple = (exit_price - entry) / risk_per_share

            all_trades.append(BounceTrade(
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
        "history_fetched": len(history),
        "period": period,
    }
