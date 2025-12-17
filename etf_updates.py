import time
import pandas as pd
from polygon import RESTClient
from datetime import datetime, timedelta
import logging
import sys

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")

client = RESTClient("plDhfpfV12E0qcxoJqhnsCvKl2Axwtgp")

TICKERS_FILE = "etf_symbols.txt"
CSV_FILE = "data/etf_prices.csv"

# Load tickers
try:
    Tickers = pd.read_csv(TICKERS_FILE, header=None)[0].tolist()
except Exception as e:
    logging.error(f"Failed to load tickers: {e}")
    sys.exit(1)

try:
    df_existing = pd.read_csv(CSV_FILE, index_col=0, parse_dates=True)
except FileNotFoundError:
    df_existing = pd.DataFrame()
except Exception as e:
    logging.error(f"Failed to load existing data: {e}")
    sys.exit(1)

today = datetime.now().date()
fetch_date = today
if today.weekday() >= 5:  
    fetch_date = today - timedelta(days=today.weekday() - 4)
fetch_date_str = fetch_date.strftime("%Y-%m-%d")

all_data = {}

for ticker in Tickers:
    try:
        aggs = list(client.list_aggs(
            ticker,
            1,
            "day",
            fetch_date_str,
            fetch_date_str,
            limit=1,
        ))
        if aggs:
            close = aggs[0].close
            date_str = str(pd.to_datetime(aggs[0].timestamp, unit="ms").date())
            all_data[ticker] = pd.Series([close], index=[date_str])
        else:
            logging.warning(f"No data for {ticker} on {fetch_date_str}")
    except Exception as e:
        logging.error(f"Error fetching {ticker}: {e}")
        if "429" in str(e):
            logging.warning("Rate limit hit. Sleeping for 65 seconds...")
            time.sleep(65)
    time.sleep(1)  

# Combine new data into a DataFrame
if all_data:
    df_new = pd.DataFrame(all_data)
    df_new.index.name = "Date"
    df_new = df_new.sort_index()

    # Append to existing, avoiding duplicate dates
    if not df_existing.empty:
        df_combined = pd.concat([df_existing, df_new])
        df_combined = df_combined[~df_combined.index.duplicated(keep='last')]
    else:
        df_combined = df_new

    df_combined = df_combined.sort_index()
    df_combined.to_csv(CSV_FILE)
    logging.info(f"Appended new data for {fetch_date_str} and saved to {CSV_FILE}")
else:
    logging.info("No new data fetched.")