"""Combined technical + fundamentals scan across all Nifty 50 constituents,
to rank which ones present the "better" setup: sitting in a pullback zone
(technically near support) with fundamentals that actually hold up, rather
than screening for one narrow trigger. Reuses the same building blocks as
the other strategies -- nothing new is invented here, just combined across
the full Nifty 50 list instead of a hand-picked shortlist.
"""

import logging
from typing import Dict, List

from .pullback_strategy import fetch_fundamentals, fundamentals_ok
from .support_zone_strategy import evaluate_support_zone_ticker

logger = logging.getLogger(__name__)


def _technical_zone(rsi14: float, close: float, bb_lower: float, bb_mid: float, bb_upper: float) -> str:
    if close <= bb_lower:
        return "at/below lower band"
    if close < bb_mid:
        return "pullback zone (lower-mid)"
    if close < bb_upper:
        return "upper-mid zone"
    return "at/above upper band"


def run_nifty50_scan(csv_dir: str = None, info_sleep_seconds: float = 0.3) -> Dict:
    from .screener import fetch_price_history
    from .universe import build_universe

    universe = build_universe(csv_dir=csv_dir)
    nifty50 = universe[universe["Index"] == "NIFTY50"]
    tickers = nifty50["Ticker"].tolist()
    ticker_to_company = dict(zip(nifty50["Ticker"], nifty50.get("Company Name", nifty50["Symbol"])))

    history = fetch_price_history(tickers)
    logger.info("Fetched history for %d/%d Nifty 50 tickers", len(history), len(tickers))

    rows: List[dict] = []
    for ticker, df in history.items():
        tech = evaluate_support_zone_ticker(df)
        if tech is None:
            continue

        info = fetch_fundamentals(ticker, info_sleep_seconds)
        sector = info.get("sector", "")
        industry = info.get("industry", "")
        f = fundamentals_ok(info, sector=sector)

        zone = _technical_zone(tech.rsi14, tech.close, tech.lower_band, tech.mid_band, tech.upper_band)
        in_pullback_zone = zone == "pullback zone (lower-mid)"

        rows.append({
            "ticker": ticker,
            "company": ticker_to_company.get(ticker, ticker),
            "sector": sector,
            "industry": industry,
            "close": tech.close,
            "rsi14": tech.rsi14,
            "zone": zone,
            "in_pullback_zone": in_pullback_zone,
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
            "overall_ok": bool(
                f["profitable_and_growing"] and f["efficient_roe"]
                and f["low_debt"] and f["analyst_backed"]
            ),
        })

    # "Better" = in the pullback zone (technically near support, not overbought)
    # AND fundamentals fully clear. Ranked ahead of everything else; within
    # each bucket, sort by RSI ascending (closer to oversold = more room to
    # bounce) as a tiebreaker, not a claim of precision.
    rows.sort(key=lambda r: (not (r["in_pullback_zone"] and r["overall_ok"]), r["rsi14"]))

    return {
        "rows": rows,
        "universe_size": len(tickers),
        "history_fetched": len(history),
    }
