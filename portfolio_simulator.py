# portfolio_simulator.py
# Simulate equal‑weight portfolio and compute annualized return, volatility, Sharpe, and correlation.

from __future__ import annotations
from datetime import datetime
import numpy as np
import pandas as pd

from portfolio_core import create_virtual_portfolio, evaluate_virtual_portfolio

TRADING_DAYS = 252

class SimulationError(Exception):
    """Raised when simulation inputs are invalid."""

def _normalize_prices(raw, tickers: list[str]) -> pd.DataFrame:
    """
    Normalize whatever evaluate_virtual_portfolio returns into a tidy price DataFrame:
      - Datetime index (sorted)
      - One column per ticker (no MultiIndex)
      - Numeric values only
    """
    if isinstance(raw, pd.DataFrame):
        df = raw.copy()
    elif isinstance(raw, pd.Series):
        df = raw.to_frame()
    elif isinstance(raw, dict):
        # Heuristic: if dict keys look like tickers, orient='columns'; otherwise orient='index'
        keys = list(raw.keys())
        if all(k in tickers for k in keys):
            df = pd.DataFrame(raw)  # columns=tickers
        else:
            df = pd.DataFrame.from_dict(raw, orient="index")
    elif isinstance(raw, list):
        # Likely list of dict rows -> DataFrame with orient='records'
        try:
            df = pd.DataFrame(raw)
        except Exception:
            # Last resort: try to map rows consistently
            df = pd.DataFrame([r for r in raw if isinstance(r, dict)])
    else:
        # Fallback to empty frame
        df = pd.DataFrame()

    # If MultiIndex columns (e.g., ('Close','AAPL')), try to pick the 'Close' level or last level
    if isinstance(df.columns, pd.MultiIndex):
        # If 'Close' in top level, select it
        top = [str(l) for l in df.columns.get_level_values(0)]
        if "Close" in top:
            df = df["Close"].copy()
        else:
            # take the last level as columns
            df.columns = df.columns.get_level_values(-1)

    # Try to coerce index to datetime if it looks like dates
    if not isinstance(df.index, pd.DatetimeIndex):
        try:
            df.index = pd.to_datetime(df.index, errors="ignore")
        except Exception:
            pass

    # If we ended up with a DatetimeIndex that includes NaT coercions, drop invalids
    if isinstance(df.index, pd.DatetimeIndex):
        # Drop rows with non-finite index and sort
        df = df[~pd.isna(df.index)]
        df = df.sort_index()

    # Keep only selected tickers if present
    present = [c for c in df.columns if c in tickers]
    if present:
        df = df[present]
    else:
        # Sometimes yfinance returns single-column frames when 1 ticker selected
        # If exactly one ticker, just rename that column to tickers[0]
        if df.shape[1] == 1 and len(tickers) == 1:
            df.columns = [tickers[0]]

    # Ensure numeric dtype
    for c in df.columns:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    # Drop rows where all prices are NaN, then forward/back fill small gaps
    df = df.dropna(how="all")
    if not df.empty:
        df = df.ffill().bfill()

    # As a final guard, keep only the requested tickers in the right order
    # (missing tickers will be added as NaN columns)
    for t in tickers:
        if t not in df.columns:
            df[t] = np.nan
    df = df[tickers]

    return df

def _annualized_metrics(price_df: pd.DataFrame, risk_free_rate: float = 0.0) -> dict:
    if price_df is None or price_df.empty:
        return {
            "return_annualized": 0.0,
            "volatility_annualized": 0.0,
            "sharpe_ratio": 0.0,
            "corr_matrix": pd.DataFrame(),
            "daily_returns": pd.DataFrame(),
        }

    daily_returns = price_df.pct_change().dropna(how="any")
    if daily_returns.empty:
        return {
            "return_annualized": 0.0,
            "volatility_annualized": 0.0,
            "sharpe_ratio": 0.0,
            "corr_matrix": pd.DataFrame(),
            "daily_returns": pd.DataFrame(),
        }

    n = daily_returns.shape[1]
    weights = np.full(n, 1.0 / n, dtype=float)

    port_daily = daily_returns.to_numpy() @ weights

    mean_daily = float(np.nanmean(port_daily))
    std_daily = float(np.nanstd(port_daily, ddof=1))

    return_annualized = mean_daily * TRADING_DAYS
    volatility_annualized = std_daily * np.sqrt(TRADING_DAYS)

    excess_return = return_annualized - risk_free_rate
    sharpe_ratio = (excess_return / volatility_annualized) if volatility_annualized else 0.0

    try:
        corr_matrix = daily_returns.corr()
    except Exception:
        corr_matrix = pd.DataFrame()

    return {
        "return_annualized": 0.0 if np.isnan(return_annualized) else float(return_annualized),
        "volatility_annualized": 0.0 if np.isnan(volatility_annualized) else float(volatility_annualized),
        "sharpe_ratio": 0.0 if np.isnan(sharpe_ratio) else float(sharpe_ratio),
        "corr_matrix": corr_matrix,
        "daily_returns": daily_returns,
    }

def _high_corr_pairs(corr_matrix: pd.DataFrame, threshold: float = 0.50) -> list[tuple[str, str, float]]:
    pairs: list[tuple[str, str, float]] = []
    if corr_matrix is None or corr_matrix.empty:
        return pairs
    cols = list(corr_matrix.columns)
    for i in range(len(cols)):
        for j in range(i + 1, len(cols)):
            a, b = cols[i], cols[j]
            val = corr_matrix.loc[a, b]
            if pd.notna(val) and float(val) >= threshold:
                pairs.append((a, b, float(val)))
    return pairs

def simulate_portfolio(
    tickers: list[str],
    investment: float = 1000.0,
    start_date: str | None = None,
    high_corr_threshold: float = 0.85,
    risk_free_rate: float = 0.0,
) -> dict:
    """
    Simulate an equal‑weight portfolio and compute metrics.
    Returns a dict with prices, daily returns, annualized return/vol, sharpe, corr matrix, and high‑corr pairs.
    """
    if not tickers:
        raise SimulationError("No tickers provided.")
    if investment <= 0:
        raise SimulationError("Investment must be positive.")

    per_asset = investment / len(tickers)
    allocations = [per_asset] * len(tickers)

    try:
        _ = create_virtual_portfolio(tickers, allocations)
    except Exception:
        pass

    if start_date is None:
        start_date = datetime.today().strftime("%Y-%m-%d")

    # raw = evaluate_virtual_portfolio(tickers, allocations, start_date)
    raw = evaluate_virtual_portfolio(tickers, lookback_days=365)
    df_prices = _normalize_prices(raw, tickers)

    metrics = _annualized_metrics(df_prices, risk_free_rate=risk_free_rate)
    pairs = _high_corr_pairs(metrics["corr_matrix"], threshold=high_corr_threshold)

    return {
        "tickers": tickers,
        "allocations": allocations,
        "df_prices": df_prices,
        "daily_returns": metrics["daily_returns"],
        "return_annualized": metrics["return_annualized"],
        "volatility_annualized": metrics["volatility_annualized"],
        "sharpe_ratio": metrics["sharpe_ratio"],
        "corr_matrix": metrics["corr_matrix"],
        "high_corr_pairs": pairs,
    }



