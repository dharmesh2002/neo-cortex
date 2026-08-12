"""One-off diagnostic: fresh real-data check on an explicit ticker list --
today's % change, the last 5 days' trend (up/down day by day), and whether
the stock is net up or down over that window. Answers "is this actually
moving up right now" rather than just "does it meet a technical zone."
Ticker list via sys.argv[1], comma-separated. Not part of the package --
delete after use.
"""
import sys

from stock_screener.screener import fetch_price_history

tickers = sys.argv[1].split(",") if len(sys.argv) > 1 else []
history = fetch_price_history(tickers)
print(f"Fetched history for {len(history)}/{len(tickers)} tickers\n")

rows = []
for ticker, df in history.items():
    df = df.dropna(subset=["Close"])
    if len(df) < 6:
        continue
    close = df["Close"]
    last5 = close.iloc[-5:]
    dates = df.index[-5:]
    daily_moves = []
    for i in range(1, len(last5)):
        chg = (last5.iloc[i] - last5.iloc[i - 1]) / last5.iloc[i - 1] * 100
        daily_moves.append(f"{dates[i].date()}:{'+' if chg >= 0 else ''}{chg:.1f}%")
    pct_change_today = (close.iloc[-1] - close.iloc[-2]) / close.iloc[-2] * 100
    pct_change_5d = (close.iloc[-1] - close.iloc[-6]) / close.iloc[-6] * 100 if len(close) >= 6 else None
    up_days_last5 = sum(1 for i in range(1, len(last5)) if last5.iloc[i] > last5.iloc[i - 1])
    rows.append((ticker, close.iloc[-1], pct_change_today, pct_change_5d, up_days_last5, " ".join(daily_moves)))

rows.sort(key=lambda r: -(r[3] if r[3] is not None else -999))
print(f"{'ticker':15s} {'close':>10s} {'today':>8s} {'5d_chg':>8s} {'up_days/5':>10s}  daily moves (last 5 sessions)")
for ticker, close, today, chg5d, upd, moves in rows:
    chg5d_s = f"{chg5d:+.1f}%" if chg5d is not None else "n/a"
    print(f"{ticker:15s} {close:10.2f} {today:+7.1f}% {chg5d_s:>8s} {upd:>9d}/5  {moves}")
