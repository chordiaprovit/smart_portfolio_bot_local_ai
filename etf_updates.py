import os
import socket
import time
import logging
from datetime import datetime, timedelta
import pandas as pd
from pathlib import Path
import yfinance as yf

CACHE_DIR = Path(".cache/py-yfinance")
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Direct yfinance timezone/cookie cache somewhere writable
yf.set_tz_cache_location(str(CACHE_DIR))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")

TICKERS_FILE = "etf_symbols.txt"
CSV_FILE = "data/etf_prices_converted.csv"

YAHOO_HOST = "query1.finance.yahoo.com"
MAX_RETRIES = 3
RETRY_SLEEP_SECONDS = 20


def read_tickers(path: str) -> list[str]:
    # Defensive: ticker files are ASCII; allow non-utf8 without crashing
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        tickers = [
            line.strip().upper()
            for line in f
            if line.strip() and not line.strip().startswith("#")
        ]
    # de-dupe while preserving order
    seen = set()
    out = []
    for t in tickers:
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out


def load_existing(csv_path: str) -> pd.DataFrame:
    if not os.path.exists(csv_path):
        return pd.DataFrame()
    # robust read for historical CSV
    df = pd.read_csv(
        csv_path,
        index_col=0,
        parse_dates=True,
        encoding="utf-8",
        engine="python",
        on_bad_lines="skip",
    )
    df.index.name = "Date"
    return df.sort_index()


def next_start_date(df_existing: pd.DataFrame) -> datetime:
    if df_existing.empty:
        return datetime.now() - timedelta(days=365 * 5)
    last_dt = pd.to_datetime(df_existing.index.max()).to_pydatetime()
    return last_dt + timedelta(days=1)


def can_resolve(host: str) -> bool:
    try:
        socket.gethostbyname(host)
        return True
    except Exception:
        return False


def yf_download_with_retries(tickers: list[str], start: str, end: str) -> pd.DataFrame:
    last_exc = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            logging.info(f"yfinance download attempt {attempt}/{MAX_RETRIES} ...")
            data = yf.download(
                tickers=tickers,
                start=start,
                end=end,
                interval="1d",
                auto_adjust=False,
                group_by="column",
                progress=False,
                threads=False,
            )
            return data
        except Exception as e:
            last_exc = e
            logging.error(f"yfinance download attempt {attempt} failed: {e}")
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_SLEEP_SECONDS)
    raise RuntimeError(f"yfinance download failed after {MAX_RETRIES} attempts: {last_exc}") from last_exc


def extract_close(data: pd.DataFrame, tickers: list[str]) -> pd.DataFrame | None:
    if data is None or data.empty:
        return None

    # MultiIndex case (multiple tickers)
    if isinstance(data.columns, pd.MultiIndex):
        if "Close" in data.columns.get_level_values(0):
            close = data["Close"]
        elif "Adj Close" in data.columns.get_level_values(0):
            close = data["Adj Close"]
        else:
            return None
    else:
        # single ticker case
        close = data[["Close"]].rename(columns={"Close": tickers[0]})

    if close is None or close.empty:
        return None

    close.index = pd.to_datetime(close.index.date)
    close.index.name = "Date"
    return close.sort_index()


def main():
    tickers = read_tickers(TICKERS_FILE)
    if not tickers:
        raise SystemExit(f"No tickers found in {TICKERS_FILE}")

    df_existing = load_existing(CSV_FILE)

    start_dt = next_start_date(df_existing)
    end_dt = datetime.now() + timedelta(days=1)  # yfinance end is exclusive

    start = start_dt.date().isoformat()
    end = end_dt.date().isoformat()

    logging.info(f"Updating ETF prices from {start_dt.date()} to {datetime.now().date()} for {len(tickers)} tickers")

    # 🔥 Critical: detect DNS problems BEFORE calling yfinance
    if not can_resolve(YAHOO_HOST):
        raise SystemExit(f"Network/DNS error: cannot resolve {YAHOO_HOST}. This is not 'up to date'—it's a network failure.")

    data = yf_download_with_retries(tickers=tickers, start=start, end=end)

    close = extract_close(data, tickers)
    if close is None or close.empty:
        # If we expected new data window but got none, treat it as failure
        # (prevents false “already up to date” when Yahoo is down)
        if start_dt.date() <= datetime.now().date():
            raise RuntimeError(
                "yfinance returned no usable Close/Adj Close data. "
                "This is often a Yahoo/network issue (DNS/blocked/temporary outage), not 'already up to date'."
            )
        logging.info("No new data fetched (already up to date).")
        return

    # append + de-dupe
    if not df_existing.empty:
        df_combined = pd.concat([df_existing, close], axis=0)
        df_combined = df_combined[~df_combined.index.duplicated(keep="last")]
    else:
        df_combined = close

    df_combined = df_combined.sort_index()

    os.makedirs(os.path.dirname(CSV_FILE), exist_ok=True)
    df_combined.to_csv(CSV_FILE, encoding="utf-8")

    logging.info(f"Saved updated ETF prices to {CSV_FILE} (rows={len(df_combined)})")


if __name__ == "__main__":
    main()
