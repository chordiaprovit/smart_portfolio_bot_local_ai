import yfinance as yf
import pandas as pd
from screener import get_snp500_tickers

def download_last_30_days():
    tickers = get_snp500_tickers()
    hist = yf.download(tickers, period="30d", interval="1d", group_by="ticker", threads=True)

    rows = []
    for ticker in tickers:
        try:
            df = hist[ticker].dropna()
            for date, row in df.iterrows():
                rows.append({
                    "Date": date.strftime("%Y-%m-%d"),
                    "Ticker": ticker,
                    "Close": round(row["Close"], 2)
                })
        except Exception as e:
            print(f"Error with {ticker}: {e}")

    pd.DataFrame(rows).to_csv("data/snp500_30day.csv", index=False)
    print("✅ Saved 30-day snapshot to snp500_30day.csv")

download_last_30_days()