"""Core screening engine: signal detection, near-miss watchlist, and
entry/stop/target/position-sizing for the Bollinger Band bounce + RSI + volume
setup on the Nifty 50 / Next 50 / Midcap 50 / Midcap 150 / Smallcap 100
universe.
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import pandas as pd
import yfinance as yf

from .indicators import atr, bollinger_bands, rsi
from .universe import build_universe, is_excluded

logger = logging.getLogger(__name__)

# ── Fixed thresholds (backtested over 2 years, ~482 signals -- do not change
# without re-testing) ──
LIQUIDITY_THRESHOLD_INR = 20 * 1e7  # 20 crore
ATR_STOP_MULTIPLE = 0.75
TARGET_GAIN_PCT = 0.03
RISK_PER_TRADE_PCT = 0.005
RSI_LOOKBACK_DAYS = 5
BB_WINDOW = 20
RSI_PERIOD = 14
ATR_PERIOD = 14

# RSI condition: RSI(14) must be turning up (today > yesterday) AND below 45.
# The RSI < 45 floor was validated by a 2yr backtest (1483 signals, 45.4% win
# rate, -0.008R) -- tighter than the no-floor version (-0.019R) and needed to
# stay close to breakeven while the strategy is further tuned.

# Need enough history for the 20-day BB window, 20-day volume average, RSI/ATR
# warmup, and the 5-day RSI lookback with a comfortable safety margin.
MIN_HISTORY_ROWS = 60
DOWNLOAD_PERIOD = "9mo"


@dataclass
class TickerSignal:
    ticker: str
    close: float
    prev_close: float
    low: float
    upper_band: float
    lower_band: float
    rsi_today: float
    rsi_prev: float
    rsi_min_5d: float
    atr14: float
    volume_today: float
    avg_volume_prior20: float
    avg_daily_value_20d: float
    pct_change: float
    bb_condition: bool
    rsi_condition: bool
    volume_condition: bool
    liquidity_ok: bool
    excess_return_pct: float = 0.0
    rs_condition: bool = False

    @property
    def conditions_met(self) -> int:
        return sum([self.bb_condition, self.rsi_condition, self.volume_condition, self.rs_condition])

    @property
    def missing_conditions(self) -> List[str]:
        missing = []
        if not self.bb_condition:
            missing.append("Bollinger bounce")
        if not self.rsi_condition:
            missing.append("RSI turning up & < 45")
        if not self.volume_condition:
            missing.append("Volume confirmation")
        if not self.rs_condition:
            missing.append("Relative strength vs universe")
        return missing


@dataclass
class TradeSetup:
    entry: float
    stop_loss: float
    target: float
    shares: int
    capital_deployed: float
    risk_amount: float


def position_size(capital: float, entry: float, stop_loss: float,
                   risk_pct: float = RISK_PER_TRADE_PCT) -> TradeSetup:
    risk_amount = capital * risk_pct
    per_share_risk = entry - stop_loss
    if per_share_risk <= 0 or entry <= 0:
        return TradeSetup(entry, stop_loss, entry * (1 + TARGET_GAIN_PCT), 0, 0.0, risk_amount)

    shares_by_risk = int(risk_amount // per_share_risk)
    shares_by_capital = int(capital // entry)
    shares = max(min(shares_by_risk, shares_by_capital), 0)
    capital_deployed = shares * entry
    target = entry * (1 + TARGET_GAIN_PCT)
    return TradeSetup(entry, stop_loss, target, shares, capital_deployed, risk_amount)


def evaluate_ticker(df: pd.DataFrame) -> Optional[TickerSignal]:
    """Evaluate the 3 signal conditions + liquidity filter for one ticker's
    OHLCV history. Returns None if there isn't enough clean history."""
    df = df.dropna(subset=["Close", "High", "Low", "Volume"])
    if len(df) < MIN_HISTORY_ROWS:
        return None

    close, high, low, volume = df["Close"], df["High"], df["Low"], df["Volume"]

    _, upper, lower = bollinger_bands(close, window=BB_WINDOW)
    rsi_series = rsi(close, period=RSI_PERIOD)
    atr_series = atr(high, low, close, period=ATR_PERIOD)

    avg_volume_prior20 = volume.shift(1).rolling(window=20).mean()
    avg_daily_value_20d = (close * volume).rolling(window=20).mean()

    if pd.isna(upper.iloc[-1]) or pd.isna(rsi_series.iloc[-1]) or pd.isna(atr_series.iloc[-1]):
        return None
    if pd.isna(avg_volume_prior20.iloc[-1]) or len(rsi_series) < RSI_LOOKBACK_DAYS + 1:
        return None

    close_today, close_prev = close.iloc[-1], close.iloc[-2]
    low_today = low.iloc[-1]
    lower_today = lower.iloc[-1]
    rsi_today, rsi_prev = rsi_series.iloc[-1], rsi_series.iloc[-2]
    rsi_min_5d = rsi_series.iloc[-RSI_LOOKBACK_DAYS:].min()

    bb_condition = bool(
        low_today <= lower_today and close_today > lower_today and close_today > close_prev
    )
    rsi_condition = bool(rsi_today > rsi_prev and rsi_today < 45)
    volume_condition = bool(volume.iloc[-1] > avg_volume_prior20.iloc[-1])
    liquidity_ok = bool(avg_daily_value_20d.iloc[-1] >= LIQUIDITY_THRESHOLD_INR)
    pct_change = float((close_today / close_prev - 1) * 100) if close_prev else 0.0

    return TickerSignal(
        ticker="",
        close=float(close_today),
        prev_close=float(close_prev),
        low=float(low_today),
        upper_band=float(upper.iloc[-1]),
        lower_band=float(lower_today),
        rsi_today=float(rsi_today),
        rsi_prev=float(rsi_prev),
        rsi_min_5d=float(rsi_min_5d),
        atr14=float(atr_series.iloc[-1]),
        volume_today=float(volume.iloc[-1]),
        avg_volume_prior20=float(avg_volume_prior20.iloc[-1]),
        avg_daily_value_20d=float(avg_daily_value_20d.iloc[-1]),
        pct_change=pct_change,
        bb_condition=bb_condition,
        rsi_condition=rsi_condition,
        volume_condition=volume_condition,
        liquidity_ok=liquidity_ok,
    )


def fetch_price_history(tickers: List[str], period: str = DOWNLOAD_PERIOD) -> Dict[str, pd.DataFrame]:
    """Bulk-download OHLCV history for all tickers in one batched call."""
    logger.info("Downloading %d days of history for %d tickers...", 0, len(tickers))
    data = yf.download(
        tickers=tickers,
        period=period,
        interval="1d",
        group_by="ticker",
        auto_adjust=False,
        threads=True,
        progress=False,
    )

    result = {}
    if len(tickers) == 1:
        result[tickers[0]] = data
        return result

    for ticker in tickers:
        try:
            sub = data[ticker]
        except KeyError:
            continue
        if sub is not None and not sub.dropna(how="all").empty:
            result[ticker] = sub
    return result


def fetch_sector_industry(ticker: str, sleep_seconds: float = 0.0) -> Dict[str, str]:
    """Fetch sector/industry for a single ticker via yfinance .info.

    Called only for tickers that already produced a full signal or a
    near-miss, since .info is a slow, individually-rate-limited call and
    most of the universe won't need it on any given day.
    """
    try:
        info = yf.Ticker(ticker).info or {}
    except Exception as exc:
        logger.warning("Could not fetch sector/industry for %s: %s", ticker, exc)
        info = {}
    finally:
        if sleep_seconds:
            time.sleep(sleep_seconds)
    return {"sector": info.get("sector", ""), "industry": info.get("industry", "")}


def run_screen(capital: float = 100_000.0, csv_dir: str = None,
                info_sleep_seconds: float = 0.3) -> Dict[str, list]:
    """Run the full screen. Returns dict with 'signals', 'near_miss', and
    'universe_size' (post sector/industry exclusion isn't applied to the
    universe size, since exclusion only needs to run against candidates)."""
    universe = build_universe(csv_dir=csv_dir)
    tickers = universe["Ticker"].tolist()
    ticker_to_company = dict(zip(universe["Ticker"], universe.get("Company Name", universe["Symbol"])))

    history = fetch_price_history(tickers)
    logger.info("Fetched history for %d/%d tickers", len(history), len(tickers))

    # Pass 1: evaluate every ticker once, and use the whole universe's today's
    # % change as the market/sector-tailwind benchmark for Relative Strength.
    evaluated: Dict[str, TickerSignal] = {}
    for ticker, df in history.items():
        result = evaluate_ticker(df)
        if result is None:
            continue
        result.ticker = ticker
        evaluated[ticker] = result

    if evaluated:
        universe_avg_pct_change = sum(r.pct_change for r in evaluated.values()) / len(evaluated)
    else:
        universe_avg_pct_change = 0.0

    signals: List[dict] = []
    near_miss: List[dict] = []

    # Pass 2: apply the Relative Strength condition now that the benchmark is
    # known, then classify into signal / near-miss.
    for ticker, result in evaluated.items():
        result.excess_return_pct = result.pct_change - universe_avg_pct_change
        result.rs_condition = result.excess_return_pct > 0

        if not result.liquidity_ok:
            continue

        if result.conditions_met == 4:
            sector_info = fetch_sector_industry(ticker, info_sleep_seconds)
            if is_excluded(sector_info["sector"], sector_info["industry"]):
                continue

            setup = position_size(capital, result.close, result.close - ATR_STOP_MULTIPLE * result.atr14)
            signals.append({
                "ticker": ticker,
                "company": ticker_to_company.get(ticker, ticker),
                "sector": sector_info["sector"],
                "industry": sector_info["industry"],
                "close": result.close,
                "atr14": result.atr14,
                "pct_change": result.pct_change,
                "excess_return_pct": result.excess_return_pct,
                "avg_daily_value_cr": result.avg_daily_value_20d / 1e7,
                "entry": setup.entry,
                "stop_loss": setup.stop_loss,
                "target": setup.target,
                "shares": setup.shares,
                "capital_deployed": setup.capital_deployed,
                "risk_amount": setup.risk_amount,
            })

        elif result.conditions_met == 3:
            sector_info = fetch_sector_industry(ticker, info_sleep_seconds)
            if is_excluded(sector_info["sector"], sector_info["industry"]):
                continue

            near_miss.append({
                "ticker": ticker,
                "company": ticker_to_company.get(ticker, ticker),
                "sector": sector_info["sector"],
                "industry": sector_info["industry"],
                "close": result.close,
                "missing": ", ".join(result.missing_conditions),
                "rsi_today": result.rsi_today,
                "rsi_min_5d": result.rsi_min_5d,
                "pct_change": result.pct_change,
                "excess_return_pct": result.excess_return_pct,
                "avg_daily_value_cr": result.avg_daily_value_20d / 1e7,
            })

    return {
        "signals": signals,
        "near_miss": near_miss,
        "universe_size": len(tickers),
        "history_fetched": len(history),
        "universe_avg_pct_change": universe_avg_pct_change,
    }
