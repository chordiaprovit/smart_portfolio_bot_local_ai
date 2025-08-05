import yfinance as yf
import pandas as pd
from datetime import datetime
from screener import get_snp500_tickers
import os

def append_latest_day():
    tickers = get_snp500_tickers()
    today = datetime.today().strftime("%Y-%m-%d")

    try:
        hist = yf.download(tickers, period="1d", interval="1d", group_by="ticker", threads=True)
        if not os.path.exists("data/snp500_30day.csv"):
            print("Snapshot file missing.")
            return

        existing = pd.read_csv("data/snp500_30day.csv")
        new_rows = []

        for ticker in tickers:
            try:
                df = hist[ticker]
                if not df.empty:
                    close = round(df["Close"].iloc[-1], 2)
                    new_rows.append({"Date": today, "Ticker": ticker, "Close": close})
            except:
                continue

        updated = pd.concat([existing, pd.DataFrame(new_rows)], ignore_index=True)

        updated["Date"] = pd.to_datetime(updated["Date"])
        updated = updated.sort_values("Date").groupby("Ticker").tail(30)

        updated.to_csv("data/snp500_30day.csv", index=False)
        print(f"✅ Appended new data for {today}")
    except Exception as e:
        print(f"Error during update: {e}")

append_latest_day()