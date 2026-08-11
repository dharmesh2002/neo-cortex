"""Warren Buffett-style quality/value screener.

Unlike every other strategy in this project, this one has no technical
price-action trigger at all -- it's a pure business-quality + valuation
filter across the whole universe, checking:

1. High, real ROE (> 15%) -- Buffett's own commonly-cited bar for a
   quality business.
2. Low debt (Debt/Equity < 50 -- stricter than the pullback strategy's
   <100, since Buffett strongly prefers businesses that don't lean on
   leverage to generate returns; exempt for Financial Services, whose
   business model runs on leverage by design).
3. Genuinely growing, not just "growing or shrinking-but-ok" -- both
   earnings growth AND revenue growth must be positive (pullback strategy
   only requires one of the two; this is the stricter Buffett-style bar).
4. Real free cash flow generation (positive FCF, not just paper profit).
5. Healthy profit margins (> 10%) as a rough, computable proxy for
   "durable competitive advantage" / pricing power -- an economic moat
   isn't something a screener can verify directly, but a business that
   consistently converts a large share of revenue into profit is at
   least consistent with having one.
6. Reasonable valuation -- trailing P/E under 25, the commonly-cited
   Buffett-style "margin of safety" proxy.
7. Analyst recommendation not Sell/Underperform (same bar used elsewhere
   in this project).

No backtest exists for this combination -- it's a business-quality
snapshot, not a trading signal, and should be read as a research
starting point rather than a validated strategy.
"""

import logging
from typing import Dict, List

from .pullback_strategy import fetch_fundamentals
from .universe import is_excluded

logger = logging.getLogger(__name__)

MIN_ROE = 0.15
MAX_DEBT_TO_EQUITY = 50.0
MIN_PROFIT_MARGIN = 0.10
MAX_TRAILING_PE = 25.0
BAD_RECOMMENDATIONS = {"sell", "underperform"}
DEBT_CHECK_EXEMPT_SECTORS = {"financial services", "financials"}


def _buffett_checks(info: Dict, sector: str = "") -> Dict:
    roe = info.get("returnOnEquity")
    debt_to_equity = info.get("debtToEquity")
    earnings_growth = info.get("earningsGrowth")
    revenue_growth = info.get("revenueGrowth")
    free_cash_flow = info.get("freeCashflow")
    profit_margin = info.get("profitMargins")
    trailing_pe = info.get("trailingPE")
    recommendation = (info.get("recommendationKey") or "").lower()

    debt_check_exempt = (sector or "").strip().lower() in DEBT_CHECK_EXEMPT_SECTORS

    high_roe = bool(roe is not None and roe > MIN_ROE)
    low_debt = debt_check_exempt or bool(debt_to_equity is not None and debt_to_equity < MAX_DEBT_TO_EQUITY)
    genuinely_growing = bool(
        earnings_growth is not None and earnings_growth > 0
        and revenue_growth is not None and revenue_growth > 0
    )
    positive_fcf = bool(free_cash_flow is not None and free_cash_flow > 0)
    healthy_margin = bool(profit_margin is not None and profit_margin > MIN_PROFIT_MARGIN)
    reasonable_valuation = bool(trailing_pe is not None and 0 < trailing_pe < MAX_TRAILING_PE)
    analyst_backed = bool(recommendation and recommendation not in BAD_RECOMMENDATIONS)

    return {
        "roe": roe,
        "debt_to_equity": debt_to_equity,
        "debt_check_exempt": debt_check_exempt,
        "earnings_growth": earnings_growth,
        "revenue_growth": revenue_growth,
        "free_cash_flow": free_cash_flow,
        "profit_margin": profit_margin,
        "trailing_pe": trailing_pe,
        "recommendation": recommendation,
        "high_roe": high_roe,
        "low_debt": low_debt,
        "genuinely_growing": genuinely_growing,
        "positive_fcf": positive_fcf,
        "healthy_margin": healthy_margin,
        "reasonable_valuation": reasonable_valuation,
        "analyst_backed": analyst_backed,
    }


def run_buffett_screen(csv_dir: str = None, info_sleep_seconds: float = 0.3) -> Dict:
    from .universe import build_universe

    universe = build_universe(csv_dir=csv_dir)
    tickers = universe["Ticker"].tolist()
    ticker_to_company = dict(zip(universe["Ticker"], universe.get("Company Name", universe["Symbol"])))

    matches: List[dict] = []
    checked = 0
    for ticker in tickers:
        info = fetch_fundamentals(ticker, info_sleep_seconds)
        checked += 1
        sector = info.get("sector", "")
        industry = info.get("industry", "")
        if is_excluded(sector, industry):
            continue

        c = _buffett_checks(info, sector=sector)
        overall_ok = bool(
            c["high_roe"] and c["low_debt"] and c["genuinely_growing"]
            and c["positive_fcf"] and c["healthy_margin"] and c["reasonable_valuation"]
            and c["analyst_backed"]
        )
        if not overall_ok:
            continue

        matches.append({
            "ticker": ticker,
            "company": ticker_to_company.get(ticker, ticker),
            "sector": sector,
            "industry": industry,
            "roe_pct": (c["roe"] * 100) if c["roe"] is not None else None,
            "debt_to_equity": c["debt_to_equity"],
            "debt_check_exempt": c["debt_check_exempt"],
            "earnings_growth_pct": (c["earnings_growth"] * 100) if c["earnings_growth"] is not None else None,
            "revenue_growth_pct": (c["revenue_growth"] * 100) if c["revenue_growth"] is not None else None,
            "profit_margin_pct": (c["profit_margin"] * 100) if c["profit_margin"] is not None else None,
            "free_cash_flow_cr": (c["free_cash_flow"] / 1e7) if c["free_cash_flow"] is not None else None,
            "trailing_pe": c["trailing_pe"],
            "recommendation": c["recommendation"],
        })

    matches.sort(key=lambda r: r["roe_pct"] if r["roe_pct"] is not None else 0, reverse=True)

    return {
        "matches": matches,
        "universe_size": len(tickers),
        "checked": checked,
    }
