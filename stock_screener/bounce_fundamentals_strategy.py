"""Bollinger Band bounce + RSI<45 + Volume confirmation + Fundamentals screen.

Combines the price-action bounce EVENT -- low touches/dips to the lower
Bollinger band, close recovers above it, and closes higher than yesterday --
with a loose RSI ceiling (< 45, not a fixed oversold floor), volume
confirmation (today's volume above the prior 20-day average), and the same
fundamentals bar used by the pullback strategy (positive earnings/revenue
growth, ROE > 15%, Debt/Equity < 100 -- exempt for Financial Services,
analyst recommendation not Sell/Underperform).

This is deliberately built around the actual bounce *event* rather than a
static "sitting in a zone" state: across this project's backtests, the
event-based bounce condition (part of the original 3-condition rule) was
the one setup that came back with positive expectancy (+0.1195R); the
passive support-zone state rule tested consistently break-even-to-negative
regardless of how its stop/target or filters were adjusted. No backtest has
been run yet for this exact combination (bounce event + RSI<45 + volume +
fundamentals) -- treat it as a new, unproven combination like every other
new strategy in this project until it's actually validated against history.
"""

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional

import pandas as pd

from .indicators import bollinger_bands, rsi
from .pullback_strategy import fetch_fundamentals, fundamentals_ok
from .universe import is_excluded

logger = logging.getLogger(__name__)

RSI_CEILING = 45.0
LIQUIDITY_THRESHOLD_INR = 20 * 1e7
BB_WINDOW = 20
RSI_PERIOD = 14
MIN_HISTORY_ROWS = 60


@dataclass
class BounceCandidate:
    ticker: str
    close: float
    prev_close: float
    low: float
    lower_band: float
    rsi_today: float
    volume_today: float
    avg_volume_prior20: float
    avg_daily_value_20d: float


def evaluate_ticker(df: pd.DataFrame) -> Optional[BounceCandidate]:
    """Cheap, price-only pre-filter -- no network calls. Fundamentals are
    only fetched for tickers that pass this technical gate."""
    df = df.dropna(subset=["Close", "High", "Low", "Volume"])
    if len(df) < MIN_HISTORY_ROWS:
        return None

    close, low, volume = df["Close"], df["Low"], df["Volume"]
    _, _, lower_band = bollinger_bands(close, window=BB_WINDOW)
    rsi_series = rsi(close, period=RSI_PERIOD)
    avg_volume_prior20 = volume.shift(1).rolling(window=20).mean()
    avg_daily_value_20d = (close * volume).rolling(window=20).mean()

    if pd.isna(lower_band.iloc[-1]) or pd.isna(rsi_series.iloc[-1]) or pd.isna(avg_volume_prior20.iloc[-1]):
        return None
    if len(close) < 2:
        return None

    close_today, close_prev = float(close.iloc[-1]), float(close.iloc[-2])
    low_today, lower_today = float(low.iloc[-1]), float(lower_band.iloc[-1])
    rsi_today = float(rsi_series.iloc[-1])
    volume_today = float(volume.iloc[-1])
    avg_vol = float(avg_volume_prior20.iloc[-1])
    avg_val = float(avg_daily_value_20d.iloc[-1])

    bounce = low_today <= lower_today and close_today > lower_today and close_today > close_prev
    rsi_ok = rsi_today < RSI_CEILING
    volume_ok = volume_today > avg_vol
    liquidity_ok = avg_val >= LIQUIDITY_THRESHOLD_INR

    if not (bounce and rsi_ok and volume_ok and liquidity_ok):
        return None

    return BounceCandidate(
        ticker="",
        close=close_today,
        prev_close=close_prev,
        low=low_today,
        lower_band=lower_today,
        rsi_today=rsi_today,
        volume_today=volume_today,
        avg_volume_prior20=avg_vol,
        avg_daily_value_20d=avg_val,
    )


def run_bounce_fundamentals_screen(csv_dir: str = None, info_sleep_seconds: float = 0.3) -> Dict:
    """Universe/price-history fetching is shared with the other strategies to
    avoid duplicating the niftyindices.com + yfinance plumbing."""
    from .screener import fetch_price_history
    from .universe import build_universe

    universe = build_universe(csv_dir=csv_dir)
    tickers = universe["Ticker"].tolist()
    ticker_to_company = dict(zip(universe["Ticker"], universe.get("Company Name", universe["Symbol"])))

    history = fetch_price_history(tickers)
    logger.info("Fetched history for %d/%d tickers", len(history), len(tickers))

    technical_candidates: List[BounceCandidate] = []
    for ticker, df in history.items():
        cand = evaluate_ticker(df)
        if cand is None:
            continue
        cand.ticker = ticker
        technical_candidates.append(cand)

    matches: List[dict] = []
    rejected: List[dict] = []
    for cand in technical_candidates:
        info = fetch_fundamentals(cand.ticker, info_sleep_seconds)
        sector = info.get("sector", "")
        industry = info.get("industry", "")
        if is_excluded(sector, industry):
            rejected.append({
                "ticker": cand.ticker,
                "company": ticker_to_company.get(cand.ticker, cand.ticker),
                "sector": sector,
                "industry": industry,
                "reason": "excluded sector/industry",
            })
            continue

        f = fundamentals_ok(info, sector=sector)
        failed_checks = [
            name for name, ok in [
                ("profitable_and_growing", f["profitable_and_growing"]),
                ("efficient_roe", f["efficient_roe"]),
                ("low_debt", f["low_debt"]),
                ("analyst_backed", f["analyst_backed"]),
            ] if not ok
        ]

        row = {
            "ticker": cand.ticker,
            "company": ticker_to_company.get(cand.ticker, cand.ticker),
            "sector": sector,
            "industry": industry,
            "close": cand.close,
            "rsi_today": cand.rsi_today,
            "pct_above_lower_band": (cand.close - cand.lower_band) / cand.lower_band * 100,
            "volume_vs_avg_pct": (cand.volume_today / cand.avg_volume_prior20 - 1) * 100,
            "roe_pct": (f["roe"] * 100) if f["roe"] is not None else None,
            "debt_to_equity": f["debt_to_equity"],
            "debt_check_exempt": f["debt_check_exempt"],
            "earnings_growth_pct": (f["earnings_growth"] * 100) if f["earnings_growth"] is not None else None,
            "revenue_growth_pct": (f["revenue_growth"] * 100) if f["revenue_growth"] is not None else None,
            "recommendation": f["recommendation"],
            "avg_daily_value_cr": cand.avg_daily_value_20d / 1e7,
        }

        if failed_checks:
            rejected.append({**row, "reason": ", ".join(failed_checks)})
        else:
            matches.append(row)

    matches.sort(key=lambda r: r["rsi_today"])

    return {
        "matches": matches,
        "rejected": rejected,
        "universe_size": len(tickers),
        "history_fetched": len(history),
        "technical_candidates": len(technical_candidates),
    }
