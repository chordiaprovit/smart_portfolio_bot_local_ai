
# tracking_helpers.py
# Watchlist CSV + portfolio tracking snapshots (Parquet)
from __future__ import annotations
import os, csv
from typing import List, Dict
import pandas as pd

WATCHLIST_CSV = "data/watchlist.csv"
SNAP_DIR = "data/tracked_portfolios"

os.makedirs("data", exist_ok=True)
os.makedirs(SNAP_DIR, exist_ok=True)

# ---------- Watchlist ----------
def load_watchlist() -> List[str]:
    if not os.path.exists(WATCHLIST_CSV):
        return []
    with open(WATCHLIST_CSV, "r", encoding="utf-8") as f:
        items = [line.strip().upper() for line in f if line.strip()]
    # de-dup and sort
    return sorted(set(items))

def save_watchlist(tickers: List[str]) -> None:
    tickers = [t.upper().strip() for t in tickers if t.strip()]
    tickers = sorted(set(tickers))
    os.makedirs(os.path.dirname(WATCHLIST_CSV), exist_ok=True)
    with open(WATCHLIST_CSV, "w", encoding="utf-8") as f:
        f.write("\n".join(tickers))

# ---------- Portfolio tracking snapshots ----------
def append_snapshot(name: str, metrics: Dict, tickers: List[str], allocations: List[float]) -> str:
    """Append a daily snapshot row for the given portfolio name.
    Returns the path to the parquet file.
    metrics expects keys: return_annualized, volatility_annualized, sharpe_ratio
    """
    path = os.path.join(SNAP_DIR, f"{name}.parquet")
    row = pd.DataFrame([{
        "date": pd.Timestamp.utcnow().normalize(),
        "ret": float(metrics.get("return_annualized", 0.0)),
        "vol": float(metrics.get("volatility_annualized", 0.0)),
        "sharpe": float(metrics.get("sharpe_ratio", 0.0)),
        "tickers": ",".join(tickers),
        "allocs": ",".join(map(str, allocations)),
    }])
    if os.path.exists(path):
        try:
            df = pd.read_parquet(path)
            df = pd.concat([df, row]).drop_duplicates(["date"]).sort_values("date")
        except Exception:
            df = row
    else:
        df = row
    df.to_parquet(path, index=False)
    return path

def load_snapshots(name: str) -> pd.DataFrame:
    """Load snapshot history for a portfolio name. Returns empty DataFrame if none."""
    path = os.path.join(SNAP_DIR, f"{name}.parquet")
    if not os.path.exists(path):
        return pd.DataFrame()
    try:
        return pd.read_parquet(path)
    except Exception:
        return pd.DataFrame()
