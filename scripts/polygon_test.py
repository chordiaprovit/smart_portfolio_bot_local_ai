import time
import pandas as pd
from polygon import RESTClient

client = RESTClient("plDhfpfV12E0qcxoJqhnsCvKl2Axwtgp")

Tickers = ["ADSK","BF-B","SW","UPS","XYZ","ZTS"]

start_date = "2024-04-01"
end_date = "2025-06-30"

all_data = {}

for ticker in Tickers:
    print(f"Fetching {ticker} ...")
    dates = []
    closes = []
    try:
        for a in client.list_aggs(
            ticker,
            1,
            "day",
            start_date,
            end_date,
            limit=50000,
        ):
            dates.append(str(pd.to_datetime(a.timestamp, unit="ms").date()))
            closes.append(a.close)
        all_data[ticker] = pd.Series(closes, index=dates)
    except Exception as e:
        print(f"Error fetching {ticker}: {e}")
        if "429" in str(e):
            print("Rate limit hit. Sleeping for 65 seconds...")
            # Write file before sleeping
            df = pd.DataFrame(all_data)
            df.index.name = "Date"
            df = df.sort_index()
            df.to_excel("polygon_prices_remaining.xlsx")
            print("Progress saved to polygon_prices.xlsx")
            time.sleep(65)
    # Always write after each ticker
    df = pd.DataFrame(all_data)
    df.index.name = "Date"
    df = df.sort_index()
    df.to_excel("polygon_prices.xlsx")
    print(f"Progress saved after {ticker}")

    time.sleep(3)

print("Final file saved to polygon_prices.xlsx")
