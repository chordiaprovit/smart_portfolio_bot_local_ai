import os
import time
from datetime import datetime, timedelta
import random
import pandas as pd
import yfinance as yf


# ------------------------------
# 1) Load S&P 500 tickers
# ------------------------------
def load_sp500_tickers(filepath="data/snp500.csv"):
    df = pd.read_csv(filepath)
    tickers = (
        df["Ticker"]
        .dropna()
        .astype(str)
        .str.strip()
        .str.replace(".", "-", regex=False)  # yfinance-compatible
        .unique()
        .tolist()
    )
    return tickers


# ------------------------------
# 2) Robust Yahoo download
# ------------------------------
def _retry_sleep(attempt, base=0.8, cap=8.0):
    # jittered exponential backoff
    delay = min(cap, base * (2 ** attempt)) * (0.7 + 0.6 * random.random())
    time.sleep(delay)


def _download_multi(tickers, start_date, end_date, max_retries=4):
    """
    Try multi-ticker download with retries.
    Returns a tidy df (Date, Ticker, Close) and a set() of failed tickers.
    """
    end_plus_one = (pd.to_datetime(end_date) + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    last_err = None
    for attempt in range(max_retries):
        try:
            raw = yf.download(
                tickers=tickers,
                start=start_date,
                end=end_plus_one,  # yfinance end is exclusive
                progress=False,
                group_by="ticker",
                auto_adjust=False,
                threads=True,
            )
            if raw is None or len(raw) == 0:
                return pd.DataFrame(columns=["Date", "Ticker", "Close"]), set()
            # Normalize to long
            frames = []
            failed = set()
            if isinstance(raw.columns, pd.MultiIndex):
                # Multi-index per ticker
                for t in tickers:
                    col = (t, "Close")
                    if col in raw.columns:
                        sub = (
                            raw[col]
                            .rename("Close")
                            .to_frame()
                            .reset_index()
                            .rename(columns={"index": "Date"})
                        )
                        sub["Ticker"] = t
                        frames.append(sub)
                    else:
                        failed.add(t)
            else:
                # Could be single ticker frame or odd shape
                if "Close" in raw.columns:
                    sub = raw["Close"].to_frame().reset_index().rename(columns={"index": "Date"})
                    sub["Ticker"] = tickers[0]
                    frames.append(sub)
                else:
                    # no Close column — treat as failure for all
                    failed.update(tickers)

            if frames:
                out = pd.concat(frames, ignore_index=True)
                out["Date"] = pd.to_datetime(out["Date"]).dt.normalize()
                out = out.dropna(subset=["Close"])
                out = out[["Date", "Ticker", "Close"]]
            else:
                out = pd.DataFrame(columns=["Date", "Ticker", "Close"])

            return out, failed
        except Exception as e:
            last_err = e
            _retry_sleep(attempt)

    # total failure
    print(f"[multi] final failure for batch of {len(tickers)} tickers: {last_err}")
    return pd.DataFrame(columns=["Date", "Ticker", "Close"]), set(tickers)


def _download_single(ticker, start_date, end_date, max_retries=3):
    end_plus_one = (pd.to_datetime(end_date) + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    last_err = None
    for attempt in range(max_retries):
        try:
            df = yf.download(
                tickers=ticker,
                start=start_date,
                end=end_plus_one,
                progress=False,
                group_by="ticker",
                auto_adjust=False,
                threads=False,
            )
            if df is None or len(df) == 0 or "Close" not in df.columns:
                return pd.DataFrame(columns=["Date", "Ticker", "Close"])

            sub = df["Close"].to_frame().reset_index().rename(columns={"index": "Date", "Close": "Close"})
            sub["Date"] = pd.to_datetime(sub["Date"]).dt.normalize()
            sub["Ticker"] = ticker
            sub = sub.dropna(subset=["Close"])
            return sub[["Date", "Ticker", "Close"]]
        except Exception as e:
            last_err = e
            _retry_sleep(attempt)

    print(f"[single:{ticker}] final failure: {last_err}")
    return pd.DataFrame(columns=["Date", "Ticker", "Close"])



# ------------------------------
# 3) Save (long + wide)
# ------------------------------


def _save_outputs(df_long, output_long="data/snp500_30day.csv", also_wide=True):
    # m/d/yy to match your Streamlit parsing
    if os.name != "nt":
        fmt = "%-m/%-d/%y"
    else:
        fmt = "%#m/%#d/%y"

    # Normalize and prepare long data
    save_df = df_long.copy()
    save_df["Date"] = pd.to_datetime(save_df["Date"]).dt.normalize()

    # Merge with existing long CSV if present
    os.makedirs(os.path.dirname(output_long), exist_ok=True)
    if os.path.exists(output_long):
        try:
            old = pd.read_csv(output_long, parse_dates=["Date"])
        except Exception:
            old = pd.read_csv(output_long)
            if "Date" in old.columns:
                old["Date"] = pd.to_datetime(old["Date"], errors="coerce")
    else:
        old = pd.DataFrame(columns=save_df.columns)

    combined = pd.concat([old, save_df], ignore_index=True)
    # Dedup by Date+Ticker if available
    if set(["Date", "Ticker"]).issubset(combined.columns):
        combined = combined.drop_duplicates(subset=["Date", "Ticker"], keep="last")
    else:
        combined = combined.drop_duplicates(keep="last")

    # FINAL: sort strictly by Date (chronological), then Ticker
    if "Date" in combined.columns:
        combined["_Date_dt"] = pd.to_datetime(combined["Date"], errors="coerce")
        sort_cols = ["_Date_dt"] + (["Ticker"] if "Ticker" in combined.columns else [])
        combined = combined.sort_values(sort_cols)
        # Format for output
        combined["Date"] = combined["_Date_dt"].dt.strftime(fmt)
        combined = combined.drop(columns=["_Date_dt"])

    combined.to_csv(output_long, index=False)

    if also_wide:
        # Build wide table from the sorted combined (use datetime for index to keep order correct)
        tmp = combined.copy()
        tmp["_Date_dt"] = pd.to_datetime(tmp["Date"], errors="coerce")

        wide = (
            tmp.pivot(index="_Date_dt", columns="Ticker", values="Close")
            .sort_index()
            .reset_index()
        )
        # Add human-readable Date column but KEEP _Date_dt for reliable merge
        wide["Date"] = wide["_Date_dt"].dt.strftime(fmt)

        wide_out = output_long.replace(".csv", "_wide.csv")

        # Merge with existing wide CSV on true datetime to preserve order
        if os.path.exists(wide_out):
            try:
                wide_old = pd.read_csv(wide_out)
            except Exception:
                wide_old = pd.DataFrame()

            if not wide_old.empty:
                # Build _Date_dt in old from Date if needed
                if "_Date_dt" not in wide_old.columns:
                    if "Date" in wide_old.columns:
                        wide_old["_Date_dt"] = pd.to_datetime(wide_old["Date"], errors="coerce")
                    else:
                        wide_old = pd.DataFrame()

            if not wide_old.empty and "_Date_dt" in wide_old.columns:
                merged = pd.merge(wide_old, wide, on="_Date_dt", how="outer", suffixes=("_old", ""))

                # Resolve duplicate ticker columns, prefer NEW values
                for col in list(merged.columns):
                    if col.endswith("_old"):
                        base = col[:-4]
                        if base in merged.columns:
                            merged[base] = merged[base].combine_first(merged[col])
                            merged = merged.drop(columns=[col])
                # Ensure chronological order and rebuild Date
                merged = merged.sort_values("_Date_dt")
                merged["Date"] = merged["_Date_dt"].dt.strftime(fmt)
                # Put Date first
                cols = ["Date"] + [c for c in merged.columns if c not in {"Date"}]
                wide = merged[cols]

        # Ensure final wide is sorted by true datetime
        if "_Date_dt" not in wide.columns:
            wide["_Date_dt"] = pd.to_datetime(wide["Date"], errors="coerce")
        wide = wide.sort_values("_Date_dt")

        # Drop helper datetime col for CSV
        wide = wide.drop(columns=["_Date_dt"])

        wide.to_csv(wide_out, index=False)
def _trim_to_last_n_trading_days(df_long, n=30):
    df = df_long.copy()
    df = df.sort_values(["Date", "Ticker"])
    last_n = sorted(df["Date"].unique())[-n:]
    return df[df["Date"].isin(last_n)]


# ------------------------------
# 4) Main fetch/update
# ------------------------------
def fetch_or_update_price_history(
    tickers,
    output_long="data/snp500_30day.csv",
    lookback_days=45,
    batch_size=50,
):
    today = datetime.utcnow().date()

    # Load existing (if any)
    if os.path.exists(output_long):
        existing = pd.read_csv(output_long)
        if not existing.empty:
            existing["Date"] = pd.to_datetime(existing["Date"], format="%m/%d/%y").dt.normalize()
            existing = existing.drop_duplicates(subset=["Date", "Ticker"], keep="last")
            max_existing = existing["Date"].max().date()
        else:
            existing = pd.DataFrame(columns=["Date", "Ticker", "Close"])
            max_existing = None
    else:
        existing = pd.DataFrame(columns=["Date", "Ticker", "Close"])
        max_existing = None

    # Decide start/end
    if max_existing is None:
        start_date = (today - timedelta(days=lookback_days)).strftime("%Y-%m-%d")
    else:
        start_date = (max_existing + timedelta(days=1)).strftime("%Y-%m-%d")
    end_date = today.strftime("%Y-%m-%d")

    # Nothing new?
    if max_existing is not None and pd.to_datetime(start_date) > pd.to_datetime(end_date):
        df_long = _trim_to_last_n_trading_days(existing, n=400)
        _save_outputs(df_long, output_long)
        print(f"✅ Up-to-date: {output_long}")
        return

    # Download in batches using multi, then fallback to singles for failures
    new_parts = []
    failed_overall = []

    for i in range(0, len(tickers), batch_size):
        batch = tickers[i : i + batch_size]
        part, failed = _download_multi(batch, start_date, end_date, max_retries=4)
        if not part.empty:
            new_parts.append(part)

        # fallback for any failed in this batch (e.g., DNS hiccups)
        if failed:
            for t in failed:
                one = _download_single(t, start_date, end_date, max_retries=3)
                if one.empty:
                    failed_overall.append(t)
                else:
                    new_parts.append(one)

    new_data = (
        pd.concat(new_parts, ignore_index=True)
        if new_parts else pd.DataFrame(columns=["Date", "Ticker", "Close"])
    )

    # Combine, clean, trim
    combined = pd.concat([existing, new_data], ignore_index=True)
    combined["Date"] = pd.to_datetime(combined["Date"]).dt.normalize()
    combined = combined.dropna(subset=["Close"]).drop_duplicates(subset=["Date", "Ticker"], keep="last")

    df_long = _trim_to_last_n_trading_days(combined, n=400)
    _save_outputs(df_long, output_long)
    print(f"✅ Saved {len(df_long):,} rows to {output_long} (plus wide file).")

    if failed_overall:
        print(f"⚠️ Still failed after retries: {sorted(set(failed_overall))}")


# ------------------------------
# 5) Entry
# ------------------------------
if __name__ == "__main__":
    tickers = load_sp500_tickers("data/snp500.csv")
    fetch_or_update_price_history(
        tickers,
        output_long="data/snp500_30day.csv",
        lookback_days=400,   # gives headroom to ensure 30 trading days
        batch_size=50,
    )
    