import yfinance as yf
from datetime import datetime
import pandas as pd

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

def suggest_diversificatio_corr(tickers, file_path="data/snp500_30day.csv", threshold=0.85):
    # Load CSV
    df = pd.read_csv(file_path)

    # Check which tickers are actually in file
    available_cols = df.columns.tolist()
    missing = [t for t in tickers if t not in available_cols]
    if missing:
        return f"⚠️ Missing tickers in data: {', '.join(missing)}. Cannot compute correlation."

    # Keep only relevant columns
    df = df[["Date"] + tickers]
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    df = df.sort_values("Date").set_index("Date")

    # Handle NaNs — forward fill then drop remaining
    df = df.ffill().dropna()

    if df.empty:
        return "⚠️ Not enough historical data to compute correlation."

    # Calculate daily returns
    returns = df.pct_change().dropna()

    # Correlation matrix
    corr_matrix = returns.corr()

    # Identify highly correlated pairs
    high_corr_pairs = []
    for i in range(len(tickers)):
        for j in range(i + 1, len(tickers)):
            corr = corr_matrix.iloc[i, j]
            if abs(corr) > threshold:
                high_corr_pairs.append((tickers[i], tickers[j], corr))

    if high_corr_pairs:
        msg = "📊 Highly correlated pairs detected:\n"
        for t1, t2, c in high_corr_pairs:
            msg += f"- {t1} and {t2}: corr = {c:.2f}\n"
        msg += "✅ Consider diversifying into different sectors or less correlated assets."
        return msg

    return "No highly correlated pairs detected. Portfolio is reasonably diversified."
