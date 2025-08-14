
import pandas as pd
import numpy as np
from typing import Tuple, List
from trend_classifier import classify_trend, TrendResult

def load_sector_map(csv_path: str) -> pd.Series:
    df = pd.read_csv(csv_path)
    col_sym = "symbol" if "symbol" in df.columns else df.columns[0]
    col_sec = "sector" if "sector" in df.columns else df.columns[1]
    sym = df[col_sym].astype(str).str.strip().str.upper().replace({"BRK.B":"BRK-B"})
    sec = df[col_sec].astype(str).str.strip()
    return pd.Series(sec.values, index=sym.values)

def aggregate_by_sector(price_df: pd.DataFrame, sector_map: pd.Series, how: str = "mean") -> pd.DataFrame:
    # price_df columns are tickers
    cols = [c for c in price_df.columns if c.upper() in sector_map.index]
    if not cols:
        return pd.DataFrame()
    aligned = price_df[cols].copy()
    aligned.columns = [c.upper() for c in aligned.columns]
    groups = {}
    for t in aligned.columns:
        sec = sector_map.get(t)
        if pd.isna(sec): continue
        groups.setdefault(sec, []).append(t)
    sec_frames = {}
    for sec, members in groups.items():
        if how == "mean":
            sec_frames[sec] = aligned[members].mean(axis=1)
        else:
            sec_frames[sec] = aligned[members].mean(axis=1)
    if not sec_frames:
        return pd.DataFrame()
    out = pd.DataFrame(sec_frames).sort_index()
    return out

def sector_trend_predictions(price_df: pd.DataFrame, map_csv: str, horizon: int = 5) -> Tuple[pd.DataFrame, List[TrendResult]]:
    smap = load_sector_map(map_csv)
    sec_df = aggregate_by_sector(price_df, smap, how="mean")
    preds = classify_trend(sec_df, horizon=horizon) if not sec_df.empty else []
    return sec_df, preds
