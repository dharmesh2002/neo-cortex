"""One-off diagnostic on REAL data: confirms the most recent trading date
and close price for the top candidates from today's capitulation and
structure screener runs, to verify the report reflects today's actual
latest close rather than stale data. Not part of the package -- delete
after use.
"""
import logging
logging.disable(logging.CRITICAL)

from stock_screener.screener import fetch_price_history

TICKERS = [
    "BLS.NS", "ADANIPOWER.NS", "HINDCOPPER.NS", "GODREJCP.NS",
    "ADANIPORTS.NS", "APLAPOLLO.NS", "ANANDRATHI.NS", "CDSL.NS",
]

history = fetch_price_history(TICKERS)
print(f"Fetched history for {len(history)}/{len(TICKERS)} tickers\n")

print(f"{'ticker':16s} {'latest_date':12s} {'close':>10s} {'prev_close':>10s} {'day_chg':>9s}")
for ticker in TICKERS:
    df = history.get(ticker)
    if df is None:
        print(f"{ticker:16s} NO DATA")
        continue
    close = df["Close"].dropna()
    date = df.index[-1].date()
    last = close.iloc[-1]
    prev = close.iloc[-2] if len(close) >= 2 else None
    chg = f"{(last - prev) / prev * 100:+.2f}%" if prev else "n/a"
    prev_s = f"{prev:.2f}" if prev is not None else "n/a"
    print(f"{ticker:16s} {str(date):12s} {last:10.2f} {prev_s:>10s} {chg:>9s}")
