def build_portfolio_analysis_prompt(tickers, allocations, sectors):
    description = "\n".join(
        [f"- {tickers[i]}: ${allocations[i]:.2f} in {sectors[i]}" for i in range(len(tickers))]
    )

    prompt = f"""You are a helpful friend explaining stock investments in plain, everyday language.
A person put money into these stocks:
{description}

Please respond using short markdown bullets. Keep each point to 1–2 lines. Write like you're texting a smart friend — no Wall Street jargon.

Cover these points:
1. How much of their money is in each industry (as a percentage).
2. Whether they're too concentrated in one area — and why that could be a problem.
3. A few other stocks they could add to spread their money around more.
"""
    return prompt

