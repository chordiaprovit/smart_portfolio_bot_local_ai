# agent_runner.py
import pandas as pd
from tools_data import yf_prices, av_batch_prices, compute_metrics

class AgentLog(list):
    def log(self, msg):
        self.append(msg)

def portfolio_agent(tickers, *, prefer="yahoo", allow_fallback=True):
    log = AgentLog()
    prices = pd.DataFrame()

    source_plan = ["yahoo", "av"] if prefer == "yahoo" else ["av", "yahoo"]
    log.log(f"Plan: sources={source_plan}, fallback={allow_fallback}")

    # ACT
    for src in source_plan:
        try:
            if src == "yahoo":
                prices = yf_prices(tickers)
            else:
                prices = av_batch_prices(tickers)
            if not prices.empty:
                log.log(f"Fetched prices from {src}: shape={prices.shape}")
                break
            else:
                log.log(f"{src} returned empty.")
        except Exception as e:
            log.log(f"{src} error: {e}")
        if not allow_fallback:
            break

    metrics = compute_metrics(prices)
    tips = []
    if metrics["vol"] >= 0.25:
        tips.append("⚠️ High volatility (≥ 25%). Consider adding lower-beta assets.")
    elif metrics["vol"] <= 0.10:
        tips.append("✅ Low volatility — typically steadier returns.")
    else:
        tips.append("ℹ️ Moderate volatility — balanced risk/return.")

    corr = metrics["corr"]
    high_pairs = []
    if not corr.empty:
        cols = list(corr.columns)
        for i in range(len(cols)):
            for j in range(i+1, len(cols)):
                if pd.notna(corr.loc[cols[i], cols[j]]) and corr.loc[cols[i], cols[j]] >= 0.85:
                    high_pairs.append((cols[i], cols[j], float(corr.loc[cols[i], cols[j]])))
    if high_pairs:
        tips.append(f"⚠️ Diversification: {len(high_pairs)} pairs > 0.85.")
    else:
        tips.append("✅ Good diversification.")

    suggestions = {
        "message": "Consider reducing a high correlation holding and adding a defensive asset.",
        "high_corr_pairs": high_pairs
    }

    return {
        "prices": prices,
        "metrics": metrics,
        "tips": tips,
        "suggestions": suggestions,
        "log": list(log)
    }
