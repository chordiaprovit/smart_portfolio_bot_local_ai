from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd


TRADING_DAYS = 252


def _read_wide_prices_csv(path: str) -> pd.DataFrame:
    """
    Expects: Date column + many ticker columns, wide format.
    Example:
        Date,VOO,SPY,IVV
        12/17/24,555.45,604.29,605.05
    """
    df = pd.read_csv(path)

    if "Date" not in df.columns:
        raise ValueError(f"{path}: Missing required column 'Date'.")

    df["Date"] = pd.to_datetime(df["Date"], errors="coerce", infer_datetime_format=True)
    df = df.dropna(subset=["Date"]).sort_values("Date").reset_index(drop=True)

    # Coerce all non-Date columns to numeric
    for c in df.columns:
        if c == "Date":
            continue
        df[c] = pd.to_numeric(df[c], errors="coerce")

    return df


def _merge_price_frames(frames: List[pd.DataFrame]) -> pd.DataFrame:
    """
    Outer-join on Date. If tickers overlap across frames, we keep the first non-null value row-wise.
    """
    if not frames:
        raise ValueError("No frames provided.")

    merged = frames[0]
    for nxt in frames[1:]:
        merged = pd.merge(merged, nxt, on="Date", how="outer", suffixes=("", "_dup"))

        # Resolve duplicate columns created by merge
        dup_cols = [c for c in merged.columns if c.endswith("_dup")]
        for dup in dup_cols:
            base = dup.replace("_dup", "")
            if base in merged.columns:
                merged[base] = merged[base].combine_first(merged[dup])
            else:
                merged.rename(columns={dup: base}, inplace=True)
            merged.drop(columns=[dup], inplace=True)

    merged = merged.sort_values("Date").reset_index(drop=True)
    return merged


def _daily_returns(prices: pd.DataFrame) -> pd.DataFrame:
    tickers = [c for c in prices.columns if c != "Date"]
    px = prices[tickers]
    rets = px.pct_change()
    rets.insert(0, "Date", prices["Date"])
    return rets


def _calc_trend_log_slope(series: pd.Series) -> float:
    """
    Trend proxy: slope of log(price) over time index.
    Returns slope per trading day (small number); explainable.
    """
    s = series.dropna()
    if len(s) < 20:
        return float("nan")
    y = np.log(s.values.astype(float))
    x = np.arange(len(y), dtype=float)
    # Linear regression slope
    slope = np.polyfit(x, y, 1)[0]
    return float(slope)


def _calc_cagr(first: float, last: float, n_days: int) -> float:
    if not (np.isfinite(first) and np.isfinite(last)) or first <= 0 or last <= 0:
        return float("nan")
    if n_days <= 1:
        return float("nan")
    years = n_days / TRADING_DAYS
    return float((last / first) ** (1.0 / years) - 1.0)


def _build_ticker_metrics(prices: pd.DataFrame) -> Dict[str, Dict]:
    # Load ETF symbols
    etf_symbols = set()
    try:
        with open("etf_symbols.txt", "r", encoding="utf-8") as f:
            etf_symbols = {line.strip().upper() for line in f if line.strip()}
    except FileNotFoundError:
        print("Warning: etf_symbols.txt not found, all tickers will be marked as 'stock'")
    
    # Load name mappings
    name_map = {}
    try:
        # For stocks: data/snp500.csv, first two columns (ticker, name)
        snp_df = pd.read_csv("data/snp500.csv")
        if len(snp_df.columns) >= 2:
            for _, row in snp_df.iterrows():
                ticker = str(row.iloc[0]).strip().upper()
                name = str(row.iloc[1]).strip()
                name_map[ticker] = name
    except Exception as e:
        print(f"Warning: Could not load stock names from data/snp500.csv: {e}")
    
    try:
        # For ETFs: etf_detail.csv, first two columns (ticker, name)
        etf_df = pd.read_csv("data/etf_detail.csv")
        if len(etf_df.columns) >= 2:
            for _, row in etf_df.iterrows():
                ticker = str(row.iloc[0]).strip().upper()
                name = str(row.iloc[1]).strip()
                name_map[ticker] = name
    except Exception as e:
        print(f"Warning: Could not load ETF names from data/etf_detail.csv: {e}")
    
    tickers = [c for c in prices.columns if c != "Date"]
    out: Dict[str, Dict] = {}

    for t in tickers:
        s = prices[t].dropna()
        if len(s) < 20:
            # too sparse, skip
            continue

        first = float(s.iloc[0])
        last = float(s.iloc[-1])
        n_days = len(s)

        # daily returns for vol
        r = s.pct_change().dropna()
        vol = float(r.std(ddof=1) * math.sqrt(TRADING_DAYS)) if len(r) >= 20 else float("nan")

        out[t] = {
            "last_price": last,
            "cagr": _calc_cagr(first, last, n_days),
            "vol": vol,
            "trend": _calc_trend_log_slope(s),
            # Metadata placeholders (fill later with your own mappings)
            "type": "etf" if t.upper() in etf_symbols else "stock",     # e.g., "stock" | "etf" | "bond_etf"
            "name": name_map.get(t.upper(), "unknown"),   # e.g., company or ETF name
        }

    return out


def _build_corr_top(rets: pd.DataFrame, top_n: int, min_obs: int = 60) -> Dict[str, List[Dict]]:
    """
    Build top-N correlated tickers for each ticker using daily returns.
    Uses pairwise complete observations; filters sparse tickers.
    """
    tickers = [c for c in rets.columns if c != "Date"]
    X = rets[tickers]

    # Keep tickers with enough data points
    valid = []
    for t in tickers:
        if X[t].notna().sum() >= min_obs:
            valid.append(t)

    Xv = X[valid].copy()
    if len(valid) < 2:
        return {}

    corr = Xv.corr(min_periods=min_obs)

    corr_top: Dict[str, List[Dict]] = {}
    for t in valid:
        if t not in corr.columns:
            continue
        s = corr[t].drop(labels=[t]).dropna()
        if s.empty:
            continue
        s = s.sort_values(ascending=False).head(top_n)
        corr_top[t] = [{"t": other, "c": float(val)} for other, val in s.items()]

    return corr_top


def main():
    parser = argparse.ArgumentParser(description="Build compact analytics_pack.json from wide price CSVs.")
    parser.add_argument("--etf_csv", type=str, required=True, help="Path to ETF wide prices CSV")
    parser.add_argument("--stocks_csv", type=str, required=True, help="Path to Stocks wide prices CSV")
    parser.add_argument("--out", type=str, default="analytics_pack.json", help="Output JSON path")
    parser.add_argument("--corr_top_n", type=int, default=8, help="Top N correlated tickers to store per ticker")
    parser.add_argument("--min_corr_obs", type=int, default=60, help="Min overlapping return observations for correlations")
    args = parser.parse_args()

    etf_df = _read_wide_prices_csv(args.etf_csv)
    stk_df = _read_wide_prices_csv(args.stocks_csv)

    prices = _merge_price_frames([etf_df, stk_df])

    # Compute returns
    rets = _daily_returns(prices)

    # Metrics + correlations
    ticker_metrics = _build_ticker_metrics(prices)
    corr_top = _build_corr_top(rets, top_n=args.corr_top_n, min_obs=args.min_corr_obs)

    as_of = prices["Date"].dropna().max()
    as_of_str = as_of.strftime("%Y-%m-%d") if pd.notna(as_of) else None

    pack = {
        "asOf": as_of_str,
        "source": {
            "etf_csv": args.etf_csv,
            "stocks_csv": args.stocks_csv,
            "tradingDaysAssumption": TRADING_DAYS,
        },
        "tickers": ticker_metrics,
        "correlationTop": corr_top,
    }

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(pack, f, indent=2)

    print(f"✅ Wrote: {args.out}")
    print(f"Tickers in pack: {len(ticker_metrics)}")
    print(f"Tickers with corrTop: {len(corr_top)}")
    print(f"asOf: {as_of_str}")


if __name__ == "__main__":
    main()
