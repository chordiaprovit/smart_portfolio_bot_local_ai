# tools_data.py
import os, time
import pandas as pd
import numpy as np
import yfinance as yf
import requests

AV_KEY = os.environ.get("ALPHAVANTAGE_API_KEY")

def yf_prices(tickers, period="365d", interval="1d"):
    df = yf.download(
        tickers=tickers, period=period, interval=interval,
        auto_adjust=False, actions=False, group_by="column",
        progress=False, threads=True
    )
    if isinstance(df.columns, pd.MultiIndex):
        if ("Close" in df.columns.get_level_values(0)):
            df = df["Close"].copy()
        else:
            df.columns = df.columns.get_level_values(-1)
    if isinstance(df, pd.Series):
        df = df.to_frame()
    present = [c for c in df.columns if c in tickers]
    if present:
        df = df[present]
    return df.dropna(how="all").sort_index()

def av_daily_adjusted(ticker, outputsize="compact"):
    if not AV_KEY:
        return pd.DataFrame()
    url = "https://www.alphavantage.co/query"
    r = requests.get(url, params={
        "function": "TIME_SERIES_DAILY_ADJUSTED",
        "symbol": ticker,
        "outputsize": outputsize,
        "datatype": "json",
        "apikey": AV_KEY
    }, timeout=20)
    data = r.json().get("Time Series (Daily)", {})
    if not data:
        return pd.DataFrame()
    df = (pd.DataFrame(data).T
            .rename(columns={"5. adjusted close": "Adj Close"})
            .astype(float, errors="ignore")
            .sort_index())
    return df[["Adj Close"]].rename(columns={"Adj Close": ticker})

def av_batch_prices(tickers, sleep_sec=12):
    frames = []
    for t in tickers:
        frames.append(av_daily_adjusted(t))
        time.sleep(sleep_sec)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, axis=1)

def compute_metrics(price_df, trading_days=252):
    if price_df.empty:
        return {"ret": 0.0, "vol": 0.0, "sharpe": 0.0, "corr": pd.DataFrame(), "daily": pd.DataFrame()}
    daily = price_df.pct_change().dropna(how="any")
    if daily.empty:
        return {"ret": 0.0, "vol": 0.0, "sharpe": 0.0, "corr": pd.DataFrame(), "daily": pd.DataFrame()}
    w = np.full(daily.shape[1], 1.0 / daily.shape[1])
    port = daily.to_numpy() @ w
    ret = float(np.nanmean(port)) * trading_days
    vol = float(np.nanstd(port, ddof=1)) * np.sqrt(trading_days)
    sharpe = (ret / vol) if vol else 0.0
    return {"ret": ret, "vol": vol, "sharpe": sharpe, "corr": daily.corr(), "daily": daily}
