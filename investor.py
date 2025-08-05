import yfinance as yf
from datetime import datetime

virtual_portfolio = {}

def create_virtual_portfolio(tickers, allocations):
    today = datetime.today().strftime('%Y-%m-%d')
    prices = yf.download(tickers, period="1d", interval="1d", progress=False)["Close"].iloc[-1]
    portfolio = {}
    for ticker, amount in zip(tickers, allocations):
        price = prices[ticker]
        shares = amount / price
        portfolio[ticker] = {
            "allocation": amount,
            "buy_price": round(price, 2),
            "shares": round(shares, 4),
            "start_date": today
        }
    virtual_portfolio["$1000_sim"] = portfolio
    return portfolio

def evaluate_virtual_portfolio(tickers, allocations, start_date):
    import yfinance as yf
    import pandas as pd

    start_date = pd.to_datetime(start_date)
    end_date = pd.Timestamp.today()

    data = yf.download(tickers, start=start_date, end=end_date, interval="1d", progress=False)["Close"]

    result = {}
    total_value = 0
    for i, ticker in enumerate(tickers):
        try:
            price_start = data[ticker].iloc[0]
            price_now = data[ticker].iloc[-1]
            shares = allocations[i] / price_start
            value_now = shares * price_now
            pct_gain = ((price_now - price_start) / price_start) * 100

            result[ticker] = {
                "buy_price": round(price_start, 2),
                "current_price": round(price_now, 2),
                "allocation": allocations[i],
                "value_now": round(value_now, 2),
                "pct_gain": round(pct_gain, 2)
            }
            total_value += value_now
        except Exception as e:
            result[ticker] = {"error": str(e)}

    return result, round(total_value, 2)

def suggest_diversification(tickers, meta_df, merged_df, sector_perf_df):
    from collections import Counter

    # Map tickers to sectors
    ticker_to_sector = {
        row['Ticker']: row['GICS Sector']
        for _, row in meta_df.iterrows()
        if row['Ticker'] in tickers
    }

    sectors = [ticker_to_sector.get(t, "Unknown") for t in tickers]
    sector_counts = Counter(sectors)
    dominant_sector, count = sector_counts.most_common(1)[0]

    if count < 2:
        return None  # Portfolio looks diversified

    suggestions = {}
    # Get top 3 performing sectors excluding the dominant one
    top_sectors = sector_perf_df[sector_perf_df["GICS Sector"] != dominant_sector]
    top_sectors = top_sectors.sort_values("Pct_Change", ascending=False).head(3)

    for sector in top_sectors["GICS Sector"]:
        candidates = merged_df[merged_df["GICS Sector"] == sector]
        top_tickers = candidates.sort_values("Pct_Change", ascending=False)["Ticker"].unique()[:3]
        suggestions[sector] = list(top_tickers)

    return dominant_sector, suggestions

