def build_portfolio_analysis_prompt(tickers, allocations, sectors):
    description = "\n".join(
        [f"- {tickers[i]}: ${allocations[i]:.2f} in {sectors[i]}" for i in range(len(tickers))]
    )

    prompt = f"""You are an AI financial advisor.

    A user created this 3-stock portfolio:
    {description}

    Please analyze the portfolio and respond using markdown bullets.

    For each point, limit your response to 1–2 lines:
    1. Show sector allocation as percentages.
    2. Give a brief risk assessment (focus on diversification and sector exposure).

    Also suggest improvement with few tickers to balance the portfolio better (e.g., diversify sector or reduce overlap).
    """
    return prompt

