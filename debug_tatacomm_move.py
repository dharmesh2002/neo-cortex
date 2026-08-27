"""One-off diagnostic on REAL data: TATACOMM.NS's day-by-day price action
over the last 10 sessions, plus volume vs. 20d average, to pin down
exactly which day(s) it fell and by how much. Not part of the package --
delete after use.
"""
import logging
logging.disable(logging.CRITICAL)

from stock_screener.screener import fetch_price_history

history = fetch_price_history(["TATACOMM.NS", "RELIANCE.NS"])
print(f"Fetched history for {len(history)}/2 tickers\n")

df = history.get("TATACOMM.NS")
if df is None:
    print("TATACOMM.NS: no data fetched.")
else:
    df = df.dropna(subset=["Close", "Volume"])
    last10 = df.iloc[-10:]
    avg_vol_20d = df["Volume"].rolling(20).mean()

    print(f"{'date':12s} {'close':>10s} {'day_chg':>9s} {'volume':>14s} {'vs_avg_vol':>10s}")
    prev_close = None
    for idx, row in last10.iterrows():
        date = idx.date()
        close = row["Close"]
        vol = row["Volume"]
        avg_vol = avg_vol_20d.loc[idx]
        chg = f"{(close - prev_close) / prev_close * 100:+.2f}%" if prev_close else "n/a"
        vs_avg = f"{vol / avg_vol:.2f}x" if avg_vol and avg_vol == avg_vol else "n/a"
        print(f"{str(date):12s} {close:10.2f} {chg:>9s} {vol:14,.0f} {vs_avg:>10s}")
        prev_close = close
