"""Trade-plan construction: entry/stop/target and portfolio-level position
sizing that caps total deployed capital across ALL signals, not just each
one individually.
"""

import math
from dataclasses import dataclass
from typing import List

from .signals import CoreEval


@dataclass
class TradePlan:
    ticker: str
    symbol: str
    sector: str
    entry: float
    stop: float
    target: float
    shares: int
    capital_required: float
    rupee_risk: float
    reward_risk_ratio: float
    score: int


def build_trade_plan(core: CoreEval, config) -> TradePlan:
    """Entry/stop/target for one signal, before capital allocation (shares
    computed later, sequentially, against remaining capital)."""
    entry = core.close
    stop = entry - config.atr_stop_multiple * core.atr14
    target = entry * (1 + config.target_gain_pct)
    per_share_risk = entry - stop
    rr_ratio = (target - entry) / per_share_risk if per_share_risk > 0 else float("nan")

    return TradePlan(
        ticker=core.ticker,
        symbol=core.symbol,
        sector=core.industry,
        entry=entry,
        stop=stop,
        target=target,
        shares=0,
        capital_required=0.0,
        rupee_risk=0.0,
        reward_risk_ratio=rr_ratio,
        score=0,
    )


def allocate_capital(plans: List[TradePlan], capital: float, risk_pct: float) -> List[TradePlan]:
    """Size each plan's shares in the order given (already sorted by score,
    highest first), deducting deployed capital as it goes so the running
    total never exceeds `capital`."""
    risk_amount_per_trade = capital * risk_pct
    remaining_capital = capital

    for plan in plans:
        per_share_risk = plan.entry - plan.stop
        if per_share_risk <= 0 or plan.entry <= 0 or remaining_capital <= 0:
            plan.shares = 0
            plan.capital_required = 0.0
            plan.rupee_risk = 0.0
            continue

        shares_by_risk = math.floor(risk_amount_per_trade / per_share_risk)
        shares_by_capital = math.floor(remaining_capital / plan.entry)
        shares = max(min(shares_by_risk, shares_by_capital), 0)

        plan.shares = shares
        plan.capital_required = shares * plan.entry
        plan.rupee_risk = shares * per_share_risk
        remaining_capital -= plan.capital_required

    return plans
