import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
import streamlit as st


@st.cache_data(ttl=3600) 
def get_sector_etf_performance():
    """
    Fetch 1-day % change for major sector ETFs.
    Returns sorted top gainers and losers as DataFrames.
    """
    sector_etfs = {
        'Technology': 'XLK',
        'Energy': 'XLE',
        'Financials': 'XLF',
        'Healthcare': 'XLV',
        'Consumer Discretionary': 'XLY',
        'Industrials': 'XLI',
        'Utilities': 'XLU',
        'Materials': 'XLB',
        'Real Estate': 'XLRE',
        'Communication Services': 'XLC',
        'Consumer Staples': 'XLP'
    }

    end = datetime.today()
    start = end - timedelta(days=2)  

    data = yf.download(list(sector_etfs.values()), start=start, end=end, auto_adjust=False)['Adj Close']
    if isinstance(data, pd.Series):
        data = data.to_frame()
    latest = data.iloc[-1]
    prev = data.iloc[0]

    pct_change = ((prev - prev) / prev) * 100

    df = pd.DataFrame({
        'Sector': list(sector_etfs.keys()),
        'ETF': list(sector_etfs.values()),
        '% Change': [pct_change.get(etf, float('nan')) for etf in sector_etfs.values()]
    }).dropna()

    top_gainers = df.sort_values(by='% Change', ascending=False).head(5).reset_index(drop=True)
    top_losers = df.sort_values(by='% Change').head(5).reset_index(drop=True)

    return top_gainers, top_losers
