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

def evaluate_virtual_portfolio(tickers, lookback_days: int = 365):
    """
    Return a wide price DataFrame with columns=tickers and rows=dates (daily).
    Uses a lookback period to avoid empty frames for 'today' and holidays.
    """
    # Use period instead of start/end to avoid empty data on same-day or holidays
    df = yf.download(
        tickers=tickers,
        period=f"{lookback_days}d",
        interval="1d",
        auto_adjust=False,      # be explicit (default changed upstream)
        actions=False,          # don’t include dividends/splits columns
        group_by="column",      # avoid MultiIndex columns
        progress=False,
        threads=True
    )

    # If yfinance returns a single column (single ticker), normalize to wide
    if isinstance(df.columns, pd.MultiIndex):
        # If MultiIndex still slipped in, try 'Close' level first
        if ("Close" in df.columns.get_level_values(0)):
            df = df["Close"].copy()
        else:
            # Last level as columns
            df.columns = df.columns.get_level_values(-1)

    # If we got the big OHLCV frame, pick Close explicitly
    if {"Open", "High", "Low", "Close"}.issubset(set(df.columns)):
        df = df[["Close"]].copy()
        df.columns = ["Close"]

    # If it's a single Close series (one ticker), make it a 1-column DataFrame
    if isinstance(df, pd.Series):
        df = df.to_frame()

    # Now, if df has columns for each ticker already, great; otherwise we try to
    # build the close matrix by refetching with column-per-ticker behavior:
    # yfinance with multiple tickers and group_by='column' usually returns
    # columns ['AAPL', 'MSFT', ...] already. If not, try to fix:
    if not all(t in df.columns for t in tickers):
        # Attempt to select only tickers columns if present
        present = [c for c in df.columns if c in tickers]
        if present:
            df = df[present]
        # If still missing, we’ll leave it—simulate layer will normalize.

    # Ensure sorted datetime index, drop empty rows
    if not isinstance(df.index, pd.DatetimeIndex):
        df.index = pd.to_datetime(df.index, errors="coerce")
    df = df.dropna(how="all")
    df = df.sort_index()

    return df

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
