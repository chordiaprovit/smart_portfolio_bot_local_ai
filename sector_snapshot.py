import pandas as pd

def get_sector_performance_from_snapshot(price_csv, metadata_csv):
    # Load and prepare data
    price_df = pd.read_csv(price_csv)
    meta_df = pd.read_csv(metadata_csv)

    # Strip and rename columns
    price_df.columns = [col.strip() for col in price_df.columns]
    meta_df.columns = [col.strip() for col in meta_df.columns]

    if 'Symbol' in meta_df.columns and 'Ticker' not in meta_df.columns:
        meta_df.rename(columns={'Symbol': 'Ticker'}, inplace=True)

    # Melt price_df to long format
    melted = price_df.melt(id_vars=["Date"], var_name="Ticker", value_name="Close")
    melted['Date'] = pd.to_datetime(melted['Date'], format="%m/%d/%y")

    # Get start and end prices
    start_date = melted['Date'].min()
    end_date = melted['Date'].max()

    start_prices = melted[melted['Date'] == start_date][['Ticker', 'Close']].rename(columns={'Close': 'Close_Start'})
    end_prices = melted[melted['Date'] == end_date][['Ticker', 'Close']].rename(columns={'Close': 'Close_End'})

    # Merge to calculate % change
    price_change = pd.merge(start_prices, end_prices, on='Ticker')
    price_change['Pct_Change'] = ((price_change['Close_End'] - price_change['Close_Start']) / price_change['Close_Start']) * 100

    # Merge with sector info
    merged = price_change.merge(meta_df[['Ticker', 'GICS Sector']], on="Ticker", how="left")

    # Sector performance
    sector_perf = merged.groupby("GICS Sector")["Pct_Change"].mean().reset_index()
    sector_perf = sector_perf.sort_values("Pct_Change", ascending=False)

    top_gainers = sector_perf.head(5)
    top_losers = sector_perf.tail(5).sort_values("Pct_Change")

    return (
        top_gainers['GICS Sector'].tolist(),
        top_losers['GICS Sector'].tolist(),
        top_gainers.rename(columns={"GICS Sector": "Sector", "Pct_Change": "% Gain"}),
        top_losers.rename(columns={"GICS Sector": "Sector", "Pct_Change": "% Loss"}),
        merged
    )

def get_tickers_by_sector(sector, merged_df):
    return merged_df[merged_df["GICS Sector"] == sector][["Ticker", "Close_Start", "Close_End", "Pct_Change"]]
