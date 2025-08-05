def agent_portfolio_recommendation(tickers, allocations, sectors):
    """
    If portfolio has 2+ same-sector stocks or risky picks, suggest a diversified option.
    Returns a suggestion message and diversified tickers if needed.
    """
    from collections import Counter
    sector_count = Counter(sectors)
    overrepresented = [s for s, count in sector_count.items() if count > 1]

    if overrepresented:
        # simple suggestion: replace one of the repeated sector stocks with another sector
        replace_index = sectors.index(overrepresented[0])
        suggestion_msg = f"You selected 2+ stocks in the {overrepresented[0]} sector."

        # Replace with a top gainer from a different sector
        from sector_snapshot import get_top_tickers_from_sector
        replacement_sector = "Health Care" if overrepresented[0] != "Health Care" else "Industrials"
        new_ticker = get_top_tickers_from_sector(replacement_sector)[0]  # assumes this helper returns tickers

        new_tickers = tickers.copy()
        new_allocs = allocations.copy()
        new_tickers[replace_index] = new_ticker

        suggestion_msg += f" Consider replacing {tickers[replace_index]} with {new_ticker} from {replacement_sector}."

        return suggestion_msg, new_tickers, new_allocs
    return None, None, None
