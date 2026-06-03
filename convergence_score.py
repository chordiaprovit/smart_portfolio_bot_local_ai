"""
convergence_score.py — Smart Money Convergence Score

Combines 4 signals per ticker into a single 0-10 score:
  1. News sentiment    (25%) — from news_fetcher.py
  2. Insider signal    (35%) — from insider_tracker.py (Form 4 P-buys)
  3. Price momentum    (20%) — yfinance 5-day + 1-day % change
  4. ETF pressure      (20%) — ETFs holding this ticker with volume spike

Verdict thresholds: 8-10 STRONG BUY | 6-7 BUY | 4-5 WATCH | 2-3 NEUTRAL | 0-1 AVOID

CLI:
  python convergence_score.py --tickers NVDA AAPL MSFT DELL MU
  python convergence_score.py --top 10
"""

from __future__ import annotations

import argparse
import json
import logging
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

import yfinance as yf

from news_fetcher import get_news_signals, get_ticker_news_score
from insider_tracker import get_insider_signals
from etf_holdings_fetcher import _load_cache as _load_etf_cache

SCORES_PATH = Path("data/convergence_scores.json")
LOOKBACK_DAYS = 90
ETF_VOLUME_SPIKE_THRESHOLD = 1.4   # ETF volume > 1.4× 20-day avg = "spike"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# ── Signal sub-scorers (all return 0-10) ──────────────────────────────────────

def _news_score(ticker: str, all_signals: List[Dict]) -> float:
    return get_ticker_news_score(ticker, all_signals)


def _insider_score(ticker: str, insider_signals: List[Dict]) -> float:
    """Map insider signal strength → 0-10."""
    relevant = [s for s in insider_signals if s.get("ticker", "").upper() == ticker.upper()]
    if not relevant:
        return 5.0  # neutral
    # Take the strongest signal for this ticker
    strengths = {s["signal_strength"] for s in relevant}
    if "HIGH" in strengths:
        return 10.0
    if "MEDIUM" in strengths:
        return 7.5
    return 6.0  # LOW


def _momentum_score(ticker: str) -> tuple[float, str]:
    """
    Fetch 10 days of prices, compute 1d and 5d returns.
    Returns (score 0-10, reason string).
    """
    try:
        hist = yf.Ticker(ticker).history(period="10d")
        if hist.empty or len(hist) < 2:
            return 5.0, "insufficient price data"
        closes = hist["Close"].dropna()
        ret_1d = float((closes.iloc[-1] - closes.iloc[-2]) / closes.iloc[-2] * 100)
        ret_5d = float((closes.iloc[-1] - closes.iloc[max(0, len(closes) - 6)]) / closes.iloc[max(0, len(closes) - 6)] * 100)

        # Scale: 0% → 5, +10% → 10, -10% → 0  (capped)
        score = 5.0 + (ret_5d * 0.25) + (ret_1d * 0.25)
        score = max(0.0, min(10.0, score))
        reason = f"5d={ret_5d:+.1f}%, 1d={ret_1d:+.1f}%"
        return round(score, 2), reason
    except Exception as e:
        log.debug(f"[{ticker}] momentum error: {e}")
        return 5.0, "price fetch failed"


def _etf_pressure_score(ticker: str, etf_cache: dict) -> tuple[float, str]:
    """
    Check if any ETF that holds this ticker had a volume spike today.
    Returns (score 0-10, reason).
    """
    holding_etfs = [
        sym for sym, entry in etf_cache.items()
        if any(h.get("ticker", "").upper() == ticker.upper() for h in entry.get("holdings", []))
    ]
    if not holding_etfs:
        return 5.0, "not in any cached ETF"

    spiking = []
    for etf_sym in holding_etfs[:10]:  # cap at 10 to avoid too many requests
        try:
            hist = yf.Ticker(etf_sym).history(period="25d")
            if hist.empty or len(hist) < 5:
                continue
            avg_vol = float(hist["Volume"].iloc[:-1].mean())
            today_vol = float(hist["Volume"].iloc[-1])
            if avg_vol > 0 and today_vol / avg_vol >= ETF_VOLUME_SPIKE_THRESHOLD:
                spiking.append(etf_sym)
        except Exception:
            continue
        time.sleep(0.1)

    if not spiking:
        reason = f"in {len(holding_etfs)} ETF(s), no volume spike"
        return 5.0, reason

    score = min(10.0, 5.0 + len(spiking) * 1.5)
    reason = f"volume spike in {', '.join(spiking[:3])}"
    return round(score, 2), reason


# ── Verdict mapping ───────────────────────────────────────────────────────────
def _verdict(score: float) -> str:
    if score >= 8:
        return "STRONG BUY"
    if score >= 6:
        return "BUY"
    if score >= 4:
        return "WATCH"
    if score >= 2:
        return "NEUTRAL"
    return "AVOID"


# ── Core scoring ──────────────────────────────────────────────────────────────
def score_ticker(
    ticker: str,
    news_signals: Optional[List[Dict]] = None,
    insider_signals: Optional[List[Dict]] = None,
    etf_cache: Optional[dict] = None,
) -> Dict:
    """Score a single ticker across all 4 signals. Returns a result dict."""
    ticker = ticker.upper().strip()
    log.info(f"[{ticker}] scoring...")

    if news_signals is None:
        news_signals = get_news_signals([ticker])
    if insider_signals is None:
        insider_signals = get_insider_signals([ticker], lookback_days=LOOKBACK_DAYS)
    if etf_cache is None:
        etf_cache = _load_etf_cache()

    ns = _news_score(ticker, news_signals)
    ins = _insider_score(ticker, insider_signals)
    mom, mom_reason = _momentum_score(ticker)
    etf, etf_reason = _etf_pressure_score(ticker, etf_cache)

    convergence = round(ns * 0.25 + ins * 0.35 + mom * 0.20 + etf * 0.20, 2)
    fired = sum([ns > 6, ins > 6, mom > 6, etf > 6])

    reasons: List[str] = []
    if ins >= 10:
        reasons.append("HIGH conviction insider open-market buy detected")
    elif ins >= 7.5:
        reasons.append("MEDIUM conviction insider buy detected")
    if ns >= 7:
        reasons.append(f"Bullish news sentiment (score {ns:.1f}/10)")
    elif ns <= 3:
        reasons.append(f"Bearish news sentiment (score {ns:.1f}/10)")
    reasons.append(f"Price momentum: {mom_reason}")
    if etf > 5:
        reasons.append(f"ETF pressure: {etf_reason}")

    return {
        "ticker": ticker,
        "convergence_score": convergence,
        "signal_count": fired,
        "news_score": ns,
        "insider_signal": ins,
        "price_momentum": mom,
        "etf_pressure": etf,
        "verdict": _verdict(convergence),
        "reasons": reasons,
        "scored_at": datetime.utcnow().isoformat(timespec="seconds"),
    }


def score_tickers(tickers: List[str]) -> List[Dict]:
    """
    Score all tickers. Shares pre-fetched signal data across calls.
    Returns list sorted by convergence_score descending.
    """
    tickers = [t.upper().strip() for t in tickers]
    log.info(f"Pre-fetching news signals for {tickers}...")
    news_signals = get_news_signals(tickers, use_cache=False)

    log.info("Pre-fetching insider signals...")
    insider_signals = get_insider_signals(tickers, lookback_days=LOOKBACK_DAYS)

    etf_cache = _load_etf_cache()

    results: List[Dict] = []
    for ticker in tickers:
        try:
            r = score_ticker(ticker, news_signals=news_signals,
                             insider_signals=insider_signals, etf_cache=etf_cache)
            results.append(r)
        except Exception as e:
            log.error(f"[{ticker}] scoring failed: {e}")
        time.sleep(0.2)

    results.sort(key=lambda r: r["convergence_score"], reverse=True)
    _save_scores(results)
    return results


def get_top_opportunities(n: int = 10) -> List[Dict]:
    """Score a sample of S&P 500 tickers and return top N."""
    import pandas as pd
    try:
        snp = pd.read_csv("data/snp500.csv")
        tickers = snp["Ticker"].dropna().str.strip().str.replace(".", "-", regex=False).tolist()
    except Exception:
        tickers = ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "JPM", "V", "JNJ"]
    sample = tickers[:50]  # scan first 50 to keep runtime reasonable
    results = score_tickers(sample)
    return results[:n]


# ── Persistence ────────────────────────────────────────────────────────────────
def _save_scores(results: List[Dict]) -> None:
    SCORES_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": datetime.utcnow().isoformat(timespec="seconds"),
        "count": len(results),
        "scores": results,
    }
    SCORES_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    log.info(f"Saved {len(results)} scores to {SCORES_PATH}")


# ── CLI ────────────────────────────────────────────────────────────────────────
_VERDICT_ICON = {
    "STRONG BUY": "🟢🟢",
    "BUY":        "🟢",
    "WATCH":      "🟡",
    "NEUTRAL":    "⚪",
    "AVOID":      "🔴",
}


def _print_results(results: List[Dict]) -> None:
    if not results:
        print("  No results.")
        return
    header = f"{'':4} {'Ticker':<7} {'Score':>6}  {'News':>5}  {'Insider':>7}  {'Momentum':>8}  {'ETF':>5}  {'Sigs':>4}  Verdict"
    print(header)
    print("─" * len(header))
    for r in results:
        icon = _VERDICT_ICON.get(r["verdict"], "  ")
        print(
            f"{icon}  {r['ticker']:<7} {r['convergence_score']:>6.2f}  "
            f"{r['news_score']:>5.1f}  {r['insider_signal']:>7.1f}  "
            f"{r['price_momentum']:>8.1f}  {r['etf_pressure']:>5.1f}  "
            f"{r['signal_count']:>4}  {r['verdict']}"
        )
        for reason in r["reasons"]:
            print(f"          → {reason}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Smart Money Convergence Scorer")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--tickers", nargs="+", metavar="SYMBOL")
    group.add_argument("--top", type=int, metavar="N", help="Top N from S&P 500 sample")
    args = parser.parse_args()

    if args.tickers:
        results = score_tickers(args.tickers)
    else:
        results = get_top_opportunities(args.top)

    print(f"\n{'═'*90}")
    print(f"  Smart Money Convergence Scores  |  {len(results)} ticker(s)")
    print(f"{'═'*90}\n")
    _print_results(results)
    print(f"\n  Results saved → {SCORES_PATH}")


if __name__ == "__main__":
    main()
