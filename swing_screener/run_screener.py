#!/usr/bin/env python3
"""Daily NSE swing-trading screener.

Run after 4 PM IST, once the day's candle is final, to generate signals and
a trade plan for the next session. This script ONLY produces a report --
it never places, modifies, or cancels any order.

Usage:
    python -m swing_screener.run_screener [--capital 1000000] [--risk-pct 0.005]
"""

import argparse
import logging
import sys
from datetime import datetime

from . import bhavcopy, data, report, sizing
from .config import load_config
from .logbook import append_signals
from .market_context import compute_market_context
from .signals import (
    compute_extra_checks,
    evaluate_core,
    near_miss_detail,
    sector_index_above_sma,
)
from .universe import build_universe, is_excluded, map_sector_index

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("swing_screener")


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=None, help="Path to config.yaml")
    parser.add_argument("--capital", type=float, default=None, help="Override capital (Rs)")
    parser.add_argument("--risk-pct", type=float, default=None, help="Override risk per trade (e.g. 0.0025)")
    parser.add_argument("--allow-stale", action="store_true",
                         help="Proceed even if the latest candle isn't today's (for testing only)")
    return parser.parse_args()


def main():
    args = parse_args()
    config = load_config(args.config)
    capital = args.capital if args.capital is not None else config.capital
    risk_pct = args.risk_pct if args.risk_pct is not None else config.risk_per_trade_pct

    logger.info("Fetching fresh Nifty 50 + Next 50 + Midcap 50 constituent lists from niftyindices.com...")
    universe_df = build_universe(config)
    logger.info("Universe: %d names before exclusions", len(universe_df))

    screened_df = universe_df[~universe_df["Industry"].apply(lambda ind: is_excluded(ind, config))].reset_index(drop=True)
    logger.info("Universe: %d names after Technology/Energy/Airlines/Oil/Gas/Petroleum/Chemicals/Paint exclusions", len(screened_df))

    tickers = screened_df["Ticker"].tolist()
    symbol_to_industry = dict(zip(screened_df["Symbol"], screened_df["Industry"]))

    logger.info("Downloading price history (cached, incremental) for %d stocks + Nifty + VIX...", len(tickers))
    core_tickers = tickers + [config.nifty_symbol, config.vix_symbol]
    history = data.fetch_many(core_tickers, config)

    nifty_df = history.get(config.nifty_symbol)
    vix_df = history.get(config.vix_symbol)
    if nifty_df is None or nifty_df.empty:
        logger.error("Could not fetch Nifty 50 (%s) history -- cannot proceed.", config.nifty_symbol)
        sys.exit(1)

    latest = data.latest_trading_date(history)
    if not args.allow_stale and data.is_stale(latest):
        today_str = datetime.now().date().isoformat()
        latest_str = latest.date().isoformat() if latest is not None else "unknown"
        print("=" * 70)
        print("WARNING: PRICE DATA IS STALE -- STOPPING")
        print("=" * 70)
        print(f"Today's date        : {today_str}")
        print(f"Latest candle found : {latest_str}")
        print("This screener only runs on same-day, post-close data. Re-run after")
        print("market close (after 4 PM IST) on a trading day, or check your")
        print("internet connection / yfinance availability.")
        print("=" * 70)
        sys.exit(1)

    run_date = latest.date().isoformat()
    logger.info("Data confirmed fresh for %s", run_date)

    market_ctx = compute_market_context(nifty_df, vix_df, config)

    nifty_close = nifty_df["Close"].dropna()
    nifty_return_63d = None
    if len(nifty_close) > config.rs_lookback_days:
        base = float(nifty_close.iloc[-(config.rs_lookback_days + 1)])
        if base:
            nifty_return_63d = (float(nifty_close.iloc[-1]) / base - 1) * 100

    # ── Pass 1: core 3-condition evaluation + liquidity for every ticker ──
    core_evals = {}
    for symbol, industry in symbol_to_industry.items():
        df = history.get(symbol + ".NS")
        if df is None or df.empty:
            continue
        core = evaluate_core(df, symbol, industry, config)
        if core is None or not core.liquidity_ok:
            continue
        core_evals[symbol] = core

    signal_cores = {s: c for s, c in core_evals.items() if c.core_count == 3}
    near_miss_cores = {s: c for s, c in core_evals.items() if c.core_count == 2}
    logger.info("%d full signals, %d near-misses out of %d liquid names evaluated",
                len(signal_cores), len(near_miss_cores), len(core_evals))

    # ── Extra checks + trade plan: only for full (3/3) signals ──
    sector_tickers = {map_sector_index(c.industry, config) for c in signal_cores.values()}
    sector_tickers.discard("n/a")
    sector_history = data.fetch_many(list(sector_tickers), config) if sector_tickers else {}

    trading_dates = [ts.date() for ts in nifty_close.index[-21:]]
    delivery_by_symbol = {}
    if signal_cores:
        logger.info("Fetching NSE bhavcopy delivery %% for %d trading days (%d signals)...",
                    len(trading_dates), len(signal_cores))
        delivery_by_symbol = bhavcopy.get_delivery_data(
            list(signal_cores.keys()), trading_dates, config.bhavcopy_cache_dir,
            timeout=config.get("request_timeout_seconds", 30),
        )

    delivery_unavailable = bool(signal_cores) and all(
        v["today_pct"] is None for v in delivery_by_symbol.values()
    )

    signal_rows = []
    log_rows = []
    plans = []
    for symbol, core in signal_cores.items():
        sector_ticker = map_sector_index(core.industry, config)
        sector_df = sector_history.get(sector_ticker)
        sector_above = sector_index_above_sma(sector_df, config.sector_sma_window) if sector_ticker != "n/a" else None

        delivery_info = delivery_by_symbol.get(symbol, {"today_pct": None, "avg20_pct": None})
        extra = compute_extra_checks(
            core,
            nifty_return_63d,
            sector_above,
            market_ctx.in_lower_half_of_range,
            config.stock_adx_threshold,
            delivery_info["today_pct"],
            delivery_info["avg20_pct"],
        )

        plan = sizing.build_trade_plan(core, config)
        plan.score = extra.score
        plans.append((plan, extra))

    # Sort by score (highest first), then allocate capital sequentially so the
    # running total across ALL signals never exceeds available capital.
    plans.sort(key=lambda pe: pe[0].score, reverse=True)
    ordered_plans = [p for p, _ in plans]
    sizing.allocate_capital(ordered_plans, capital, risk_pct)

    for plan, extra in plans:
        marks = extra.as_marks()
        signal_rows.append({
            "Score": plan.score,
            "Symbol": plan.symbol,
            "Sector": plan.sector,
            "Entry": plan.entry,
            "Stop": plan.stop,
            "Target": plan.target,
            "Shares": plan.shares,
            "Capital (Rs)": plan.capital_required,
            "Risk (Rs)": plan.rupee_risk,
            "R:R": plan.reward_risk_ratio,
            "RS": marks["RS"],
            "Sector>SMA50": marks["Sector"],
            "NiftyRange": marks["NiftyRange"],
            "ADX<25": marks["ADX"],
            "Delivery": marks["Delivery"],
        })
        log_rows.append({
            "date": run_date,
            "symbol": plan.symbol,
            "sector": plan.sector,
            "entry": plan.entry,
            "stop": plan.stop,
            "target": plan.target,
            "shares": plan.shares,
            "capital_required": plan.capital_required,
            "rupee_risk": plan.rupee_risk,
            "reward_risk_ratio": plan.reward_risk_ratio,
            "rs_check": extra.rs,
            "sector_check": extra.sector,
            "nifty_range_check": extra.nifty_range,
            "adx_check": extra.adx,
            "delivery_check": extra.delivery,
            "score": plan.score,
        })

    near_miss_rows = []
    for symbol, core in near_miss_cores.items():
        missing = core.missing_core
        near_miss_rows.append({
            "Symbol": symbol,
            "Sector": core.industry,
            "Missing": missing[0] if missing else "",
            "Detail": near_miss_detail(core, config),
        })

    signals_df = report.signals_to_dataframe(signal_rows)
    near_miss_df = report.near_miss_to_dataframe(near_miss_rows)

    delivery_note = ""
    if delivery_unavailable:
        delivery_note = (
            "NSE bhavcopy (sec_bhavdata_full) could not be downloaded for any of the "
            "requested trading days -- Delivery %% shows 'n/a' for every signal this run."
        )
        print(f"NOTE: {delivery_note}")

    report.print_report(market_ctx, signals_df, near_miss_df, len(universe_df), len(history),
                         run_date, capital, risk_pct)

    md_path, csv_path = report.save_report(
        market_ctx, signals_df, near_miss_df, len(universe_df), len(history), run_date,
        capital, risk_pct, config.reports_dir, delivery_note,
    )
    logger.info("Saved report to %s and %s", md_path, csv_path)

    append_signals(log_rows, config.signals_log_file)
    logger.info("Appended %d signal(s) to %s", len(log_rows), config.signals_log_file)

    print("\nReminder: this tool only generates signals and a trade plan -- no orders were placed.")


if __name__ == "__main__":
    main()
