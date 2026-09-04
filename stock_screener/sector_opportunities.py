"""Sector-opportunities screen: finds stocks that are strongly correlated
with their sector historically but haven't moved yet today, in sectors that
are already up meaningfully.

Logic:
  1. Fetch price history and sector for every universe stock.
  2. For each sector that is up today (avg_pct_change > SECTOR_UP_THRESHOLD),
     compute the sector's daily return series over the last CORRELATION_WINDOW
     trading days.
  3. For each stock in that sector, compute the Pearson correlation between
     the stock's daily return and the sector's daily return over that window.
  4. Flag the stock as an opportunity if:
       - Correlation >= CORRELATION_MIN (historically moves with its sector)
       - Stock's today % change is <= sector's today avg × LAG_RATIO
         (hasn't caught up yet, or barely moved)
       - Liquidity >= 20cr/day
       - Not in the standing exclusion list

These are the laggards in a rising sector -- momentum has already started in
the sector, the individual stock just hasn't been picked up yet.

No backtest exists for this pattern. Not investment advice.
"""

import logging
import time
from typing import Dict, List

import numpy as np
import pandas as pd
import yfinance as yf

from .universe import build_universe, is_excluded

logger = logging.getLogger(__name__)

# ── Thresholds ────────────────────────────────────────────────────────────────
SECTOR_UP_THRESHOLD_PCT = 0.3      # sector avg must be at least +0.3% today
CORRELATION_MIN = 0.5              # min Pearson r between stock and sector returns
CORRELATION_WINDOW = 60            # trading days to compute correlation over
LAG_RATIO = 0.4                    # stock's move must be ≤ 40% of sector's move
LIQUIDITY_THRESHOLD_INR = 20 * 1e7 # 20 crore

DOWNLOAD_PERIOD = "6mo"
MIN_HISTORY_ROWS = CORRELATION_WINDOW + 10


def _pct_changes(df: pd.DataFrame) -> pd.Series:
    """Daily % return series (today excluded -- uses prior-day data only)."""
    close = df["Close"].dropna()
    return close.pct_change().dropna()


def _today_pct_change(df: pd.DataFrame) -> float | None:
    close = df["Close"].dropna()
    if len(close) < 2:
        return None
    prev = close.iloc[-2]
    if not prev:
        return None
    return float((close.iloc[-1] / prev - 1) * 100)


def _avg_daily_value_cr(df: pd.DataFrame) -> float:
    close = df["Close"].dropna()
    volume = df["Volume"].dropna()
    combined = (close * volume).rolling(window=20).mean()
    val = combined.iloc[-1] if not combined.empty else 0.0
    return float(val) / 1e7  # convert to crore


def run_sector_opportunities(csv_dir: str = None,
                              info_sleep_seconds: float = 0.15) -> Dict:
    """Run the sector-opportunity screen. Returns a dict with keys:
    'opportunities', 'sector_summary', 'universe_size', 'history_fetched'.
    """
    from .screener import fetch_price_history

    universe = build_universe(csv_dir=csv_dir)
    tickers = universe["Ticker"].tolist()
    ticker_to_company = dict(zip(universe["Ticker"], universe.get("Company Name", universe["Symbol"])))

    history = fetch_price_history(tickers, period=DOWNLOAD_PERIOD)
    logger.info("Fetched history for %d/%d tickers", len(history), len(tickers))

    # ── Step 1: fetch sector for every ticker ───────────────────────────────
    ticker_sector: Dict[str, str] = {}
    ticker_industry: Dict[str, str] = {}
    usable = [t for t, df in history.items() if len(df.dropna(subset=["Close"])) >= MIN_HISTORY_ROWS]

    logger.info("Fetching sector/industry for %d tickers (may be slow)...", len(usable))
    for i, ticker in enumerate(usable):
        try:
            info = yf.Ticker(ticker).info or {}
        except Exception as exc:
            logger.warning("sector fetch failed for %s: %s", ticker, exc)
            info = {}
        ticker_sector[ticker] = info.get("sector", "") or ""
        ticker_industry[ticker] = info.get("industry", "") or ""
        if info_sleep_seconds:
            time.sleep(info_sleep_seconds)
        if (i + 1) % 50 == 0:
            logger.info("  ... %d/%d done", i + 1, len(usable))

    # ── Step 2: build per-sector return series and today's pct change ────────
    sector_tickers: Dict[str, List[str]] = {}
    for ticker in usable:
        sec = ticker_sector.get(ticker, "") or "Unknown"
        sector_tickers.setdefault(sec, []).append(ticker)

    # For each sector, build a daily return matrix aligned on common dates
    sector_return_series: Dict[str, pd.Series] = {}
    sector_today_pct: Dict[str, float] = {}

    for sec, members in sector_tickers.items():
        closes = {}
        for t in members:
            df = history[t]
            close = df["Close"].dropna()
            if len(close) >= MIN_HISTORY_ROWS:
                closes[t] = close

        if not closes:
            continue

        combined = pd.DataFrame(closes)
        # use the last CORRELATION_WINDOW + 1 rows so pct_change gives CORRELATION_WINDOW returns
        combined = combined.tail(CORRELATION_WINDOW + 1)
        returns = combined.pct_change().iloc[1:]  # drop the first NaN row

        # sector return = simple average across members on each day
        sec_returns = returns.mean(axis=1)
        sector_return_series[sec] = sec_returns

        # sector today's move = mean of today's individual pct changes
        today_moves = []
        for t in members:
            pct = _today_pct_change(history[t])
            if pct is not None:
                today_moves.append(pct)
        sector_today_pct[sec] = float(np.mean(today_moves)) if today_moves else 0.0

    # ── Step 3: identify sectors up today ────────────────────────────────────
    up_sectors = {sec for sec, pct in sector_today_pct.items()
                  if pct >= SECTOR_UP_THRESHOLD_PCT}
    logger.info("Sectors up today (>= %.1f%%): %s",
                SECTOR_UP_THRESHOLD_PCT, sorted(up_sectors))

    # Build sector summary for all sectors, sorted best to worst
    sector_summary = []
    for sec, pct in sorted(sector_today_pct.items(), key=lambda x: x[1], reverse=True):
        members = sector_tickers.get(sec, [])
        advancers = sum(1 for t in members
                        if (_today_pct_change(history.get(t, pd.DataFrame())) or 0) > 0)
        sector_summary.append({
            "sector": sec,
            "avg_pct_change": round(pct, 3),
            "count": len(members),
            "advancers": advancers,
            "decliners": len(members) - advancers,
            "is_up": sec in up_sectors,
        })

    # ── Step 4: for each stock in an up sector, compute correlation & flag lag ─
    opportunities = []

    for ticker in usable:
        sec = ticker_sector.get(ticker, "") or "Unknown"
        ind = ticker_industry.get(ticker, "") or ""

        if sec not in up_sectors:
            continue

        if is_excluded(sec, ind):
            continue

        df = history[ticker]
        liq = _avg_daily_value_cr(df)
        if liq < LIQUIDITY_THRESHOLD_INR / 1e7:  # already in crore from helper
            continue

        today_pct = _today_pct_change(df)
        if today_pct is None:
            continue

        sector_pct = sector_today_pct[sec]

        # The stock must be lagging -- moved at most LAG_RATIO × sector's move
        lag_threshold = sector_pct * LAG_RATIO
        if today_pct > lag_threshold:
            continue  # already moved with / ahead of sector

        # Compute correlation against the sector's historical return series
        sec_returns = sector_return_series.get(sec)
        if sec_returns is None or len(sec_returns) < 20:
            continue

        close = df["Close"].dropna()
        stock_returns = close.pct_change().dropna()

        # Align on common index (dates), using the last CORRELATION_WINDOW rows
        common = sec_returns.index.intersection(stock_returns.index)
        if len(common) < 20:
            continue

        s_ret = stock_returns.loc[common].tail(CORRELATION_WINDOW)
        sec_ret = sec_returns.loc[common].tail(CORRELATION_WINDOW)

        if len(s_ret) < 20:
            continue

        corr = float(s_ret.corr(sec_ret))
        if np.isnan(corr) or corr < CORRELATION_MIN:
            continue

        lag_pct = sector_pct - today_pct  # how much the stock is lagging behind

        opportunities.append({
            "ticker": ticker,
            "company": ticker_to_company.get(ticker, ticker),
            "sector": sec,
            "industry": ind,
            "sector_pct_today": round(sector_pct, 3),
            "stock_pct_today": round(today_pct, 3),
            "lag_pct": round(lag_pct, 3),
            "sector_correlation": round(corr, 3),
            "avg_daily_value_cr": round(liq, 2),
        })

    # Sort: strongest sector move first, then highest correlation, then highest lag
    opportunities.sort(key=lambda x: (
        -x["sector_pct_today"],
        -x["sector_correlation"],
        -x["lag_pct"],
    ))

    return {
        "opportunities": opportunities,
        "sector_summary": sector_summary,
        "universe_size": len(tickers),
        "history_fetched": len(history),
        "up_sectors": sorted(up_sectors),
    }
