"""Alternative strategy: quality stocks resting quietly near support, not
chasing an oversold bounce. Looks for stocks sitting between the Bollinger
lower and middle band, within 2% of their 50-day SMA, with strong
fundamentals, and no recent outsized single-day move.

There's no data feed for "affected by the US-Iran war" specifically -- an
unusually large recent single-day move (either direction) is used as the
practical stand-in, since that's how a macro/geopolitical shock typically
shows up in a stock's price. Combined with the existing Energy/Oil/Gas
exclusion list (which already screens out the names most directly exposed
to an oil-price shock), this is the closest computable proxy for "no
external impact."
"""

import logging
import time
from dataclasses import dataclass
from typing import Dict, List, Optional

import pandas as pd
import yfinance as yf

from .indicators import bollinger_bands
from .universe import is_excluded

logger = logging.getLogger(__name__)

SMA_SUPPORT_WINDOW = 50
SUPPORT_TOLERANCE_PCT = 0.02  # within 2% of the 50-day SMA
MAX_RECENT_MOVE_PCT = 3.0  # exclude if yesterday's or today's move exceeds this, either direction
MIN_ROE = 0.15
MAX_DEBT_TO_EQUITY = 100.0
BAD_RECOMMENDATIONS = {"sell", "underperform"}

# Banks/NBFCs run high leverage as their normal business model (deposits and
# borrowings ARE the business, not distress) -- a Debt/Equity ratio that would
# flag a manufacturer as overleveraged is routine for this sector. Applying
# the same MAX_DEBT_TO_EQUITY threshold there would reject nearly the entire
# sector regardless of actual financial health, so the low-debt check is
# skipped (treated as automatically satisfied) for these sectors.
DEBT_CHECK_EXEMPT_SECTORS = {"financial services", "financials"}
LIQUIDITY_THRESHOLD_INR = 20 * 1e7  # 20 crore, same liquidity bar as the bounce strategy
BB_WINDOW = 20
MIN_HISTORY_ROWS = 60


@dataclass
class PullbackCandidate:
    ticker: str
    close: float
    sma50: float
    sma20: float
    lower_band: float
    pct_change_today: float
    pct_change_yesterday: float
    avg_daily_value_20d: float
    near_support: bool
    in_bb_zone: bool
    quiet: bool
    liquidity_ok: bool

    @property
    def technical_ok(self) -> bool:
        return self.near_support and self.in_bb_zone and self.quiet and self.liquidity_ok


def evaluate_pullback_ticker(df: pd.DataFrame) -> Optional[PullbackCandidate]:
    """Cheap, price-only pre-filter -- no network calls. Fundamentals are only
    fetched for tickers that pass this technical gate."""
    df = df.dropna(subset=["Close", "Volume"])
    if len(df) < MIN_HISTORY_ROWS:
        return None

    close, volume = df["Close"], df["Volume"]
    sma20, _, lower = bollinger_bands(close, window=BB_WINDOW)
    sma50 = close.rolling(window=SMA_SUPPORT_WINDOW).mean()
    avg_daily_value_20d = (close * volume).rolling(window=20).mean()

    if pd.isna(sma50.iloc[-1]) or pd.isna(sma20.iloc[-1]) or pd.isna(lower.iloc[-1]):
        return None
    if len(close) < 3:
        return None

    close_today = close.iloc[-1]
    close_yday = close.iloc[-2]
    close_2d_ago = close.iloc[-3]

    pct_change_today = float((close_today / close_yday - 1) * 100) if close_yday else 0.0
    pct_change_yesterday = float((close_yday / close_2d_ago - 1) * 100) if close_2d_ago else 0.0

    near_support = bool(abs(close_today - sma50.iloc[-1]) / sma50.iloc[-1] <= SUPPORT_TOLERANCE_PCT)
    in_bb_zone = bool(lower.iloc[-1] < close_today < sma20.iloc[-1])
    quiet = bool(
        abs(pct_change_today) <= MAX_RECENT_MOVE_PCT
        and abs(pct_change_yesterday) <= MAX_RECENT_MOVE_PCT
    )
    liquidity_ok = bool(avg_daily_value_20d.iloc[-1] >= LIQUIDITY_THRESHOLD_INR)

    return PullbackCandidate(
        ticker="",
        close=float(close_today),
        sma50=float(sma50.iloc[-1]),
        sma20=float(sma20.iloc[-1]),
        lower_band=float(lower.iloc[-1]),
        pct_change_today=pct_change_today,
        pct_change_yesterday=pct_change_yesterday,
        avg_daily_value_20d=float(avg_daily_value_20d.iloc[-1]),
        near_support=near_support,
        in_bb_zone=in_bb_zone,
        quiet=quiet,
        liquidity_ok=liquidity_ok,
    )


def fetch_fundamentals(ticker: str, sleep_seconds: float = 0.0) -> Dict:
    """Only called for tickers that already passed the technical gate, since
    .info is a slow, individually-rate-limited call."""
    try:
        info = yf.Ticker(ticker).info or {}
    except Exception as exc:
        logger.warning("Could not fetch fundamentals for %s: %s", ticker, exc)
        info = {}
    finally:
        if sleep_seconds:
            time.sleep(sleep_seconds)
    return info


def fundamentals_ok(info: Dict, sector: str = "") -> Dict:
    earnings_growth = info.get("earningsGrowth")
    revenue_growth = info.get("revenueGrowth")
    roe = info.get("returnOnEquity")
    debt_to_equity = info.get("debtToEquity")
    recommendation = (info.get("recommendationKey") or "").lower()

    debt_check_exempt = (sector or "").strip().lower() in DEBT_CHECK_EXEMPT_SECTORS

    profitable_and_growing = bool(
        (earnings_growth is not None and earnings_growth > 0)
        or (revenue_growth is not None and revenue_growth > 0)
    )
    efficient = bool(roe is not None and roe > MIN_ROE)
    low_debt = debt_check_exempt or bool(debt_to_equity is not None and debt_to_equity < MAX_DEBT_TO_EQUITY)
    analyst_backed = bool(recommendation and recommendation not in BAD_RECOMMENDATIONS)

    return {
        "profitable_and_growing": profitable_and_growing,
        "efficient_roe": efficient,
        "low_debt": low_debt,
        "analyst_backed": analyst_backed,
        "debt_check_exempt": debt_check_exempt,
        "earnings_growth": earnings_growth,
        "revenue_growth": revenue_growth,
        "roe": roe,
        "debt_to_equity": debt_to_equity,
        "recommendation": recommendation,
    }


def check_fundamentals_for_tickers(tickers: List[str], sleep_seconds: float = 0.3) -> List[dict]:
    """Ad-hoc fundamentals check for an explicit ticker list, independent of
    any technical scan -- e.g. to annotate a shortlist that came from a pure
    price/RSI screen with real fundamentals data. Every ticker is reported,
    passing or not, so nothing is silently dropped."""
    rows: List[dict] = []
    for ticker in tickers:
        info = fetch_fundamentals(ticker, sleep_seconds)
        sector = info.get("sector", "")
        industry = info.get("industry", "")
        f = fundamentals_ok(info, sector=sector)
        overall_ok = bool(
            f["profitable_and_growing"] and f["efficient_roe"]
            and f["low_debt"] and f["analyst_backed"]
        )
        rows.append({
            "ticker": ticker,
            "sector": sector,
            "industry": industry,
            "roe_pct": (f["roe"] * 100) if f["roe"] is not None else None,
            "debt_to_equity": f["debt_to_equity"],
            "debt_check_exempt": f["debt_check_exempt"],
            "earnings_growth_pct": (f["earnings_growth"] * 100) if f["earnings_growth"] is not None else None,
            "revenue_growth_pct": (f["revenue_growth"] * 100) if f["revenue_growth"] is not None else None,
            "recommendation": f["recommendation"],
            "profitable_and_growing": f["profitable_and_growing"],
            "efficient_roe": f["efficient_roe"],
            "low_debt": f["low_debt"],
            "analyst_backed": f["analyst_backed"],
            "overall_ok": overall_ok,
        })
    return rows


def run_pullback_screen(csv_dir: str = None, info_sleep_seconds: float = 0.3) -> Dict:
    """Universe/price-history fetching is shared with the bounce strategy to
    avoid duplicating the niftyindices.com + yfinance plumbing."""
    from .screener import fetch_price_history
    from .universe import build_universe

    universe = build_universe(csv_dir=csv_dir)
    tickers = universe["Ticker"].tolist()
    ticker_to_company = dict(zip(universe["Ticker"], universe.get("Company Name", universe["Symbol"])))

    history = fetch_price_history(tickers)
    logger.info("Fetched history for %d/%d tickers", len(history), len(tickers))

    technical_candidates: List[PullbackCandidate] = []
    for ticker, df in history.items():
        result = evaluate_pullback_ticker(df)
        if result is None:
            continue
        result.ticker = ticker
        if result.technical_ok:
            technical_candidates.append(result)

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

        if failed_checks:
            rejected.append({
                "ticker": cand.ticker,
                "company": ticker_to_company.get(cand.ticker, cand.ticker),
                "sector": sector,
                "industry": industry,
                "reason": ", ".join(failed_checks),
                "roe_pct": (f["roe"] * 100) if f["roe"] is not None else None,
                "debt_to_equity": f["debt_to_equity"],
                "debt_check_exempt": f["debt_check_exempt"],
                "earnings_growth_pct": (f["earnings_growth"] * 100) if f["earnings_growth"] is not None else None,
                "revenue_growth_pct": (f["revenue_growth"] * 100) if f["revenue_growth"] is not None else None,
                "recommendation": f["recommendation"],
            })
            continue

        matches.append({
            "ticker": cand.ticker,
            "company": ticker_to_company.get(cand.ticker, cand.ticker),
            "sector": sector,
            "industry": industry,
            "close": cand.close,
            "sma50_support": cand.sma50,
            "bb_lower": cand.lower_band,
            "bb_mid": cand.sma20,
            "pct_change_today": cand.pct_change_today,
            "roe_pct": (f["roe"] or 0) * 100,
            "debt_to_equity": f["debt_to_equity"],
            "earnings_growth_pct": (f["earnings_growth"] * 100) if f["earnings_growth"] is not None else None,
            "recommendation": f["recommendation"],
            "avg_daily_value_cr": cand.avg_daily_value_20d / 1e7,
        })

    return {
        "matches": matches,
        "rejected": rejected,
        "universe_size": len(tickers),
        "history_fetched": len(history),
        "technical_candidates": len(technical_candidates),
    }
