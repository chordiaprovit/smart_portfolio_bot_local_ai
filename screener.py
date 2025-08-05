# screener.py
import pandas as pd
import yfinance as yf
from functools import lru_cache

SNP500_FILE = "data/snp500.csv"

@lru_cache(maxsize=1)
def get_snp500_tickers():
    df = pd.read_csv(SNP500_FILE)
    return df["Ticker"].tolist()

def get_sector_for_ticker(ticker):
    try:
        info = yf.Ticker(ticker).info
        return info.get("sector", "Unknown")
    except:
        return "Unknown"

def get_sector_gainers_losers(min_price=0, max_price=1000):
    tickers = get_snp500_tickers()
    data = yf.download(tickers, period="1d", group_by="ticker", threads=True)

    sector_map = {}
    for ticker in tickers:
        try:
            price_data = data[ticker]
            prev_close = price_data["Close"].iloc[-2] if len(price_data) > 1 else price_data["Open"].iloc[-1]
            last_price = price_data["Close"].iloc[-1]
            change_pct = ((last_price - prev_close) / prev_close) * 100

            info = yf.Ticker(ticker).info
            sector = info.get("sector", "Unknown")

            if sector not in sector_map:
                sector_map[sector] = []

            if min_price <= last_price <= max_price:
                sector_map[sector].append({
                    "Ticker": ticker,
                    "Price": round(last_price, 2),
                    "% Change": round(change_pct, 2)
                })
        except Exception:
            continue

    sector_gainers = {}
    sector_losers = {}

    for sector, stocks in sector_map.items():
        sorted_stocks = sorted(stocks, key=lambda x: x["% Change"], reverse=True)
        if sorted_stocks:
            sector_gainers[sector] = sorted_stocks[:5]
            sector_losers[sector] = sorted_stocks[-5:]

    gain_df = {k: pd.DataFrame(v) for k, v in sector_gainers.items()}
    loss_df = {k: pd.DataFrame(v) for k, v in sector_losers.items()}

    return gain_df, loss_df
