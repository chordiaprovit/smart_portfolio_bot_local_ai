"""
speech_backtest.py — Political Speech Signal Backtester

Maps keyword mention events (from cached news signals) to ticker forward returns,
using data/snp500_30day_wide.csv as the price source.

For each keyword+ticker pair: hit_rate, avg_return_1d/2d/5d, sample_size.
Requires sample_size >= 3 before reporting (avoids overfitting noise).

Data is sparse at first — framework strengthens as news cache accumulates.

CLI:
  python speech_backtest.py --run
  python speech_backtest.py --leaderboard
"""

from __future__ import annotations

import argparse
import json
import logging
import re
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd
import numpy as np

BACKTEST_PATH = Path("data/backtest_results.json")
NEWS_CACHE_PATH = Path("data/news_signals.json")
PRICE_CSV = Path("data/snp500_30day_wide.csv")
MIN_SAMPLE_SIZE = 3

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# Keyword → sector/ticker affinity map (used to expand signals to related tickers)
KEYWORD_TICKER_MAP: Dict[str, List[str]] = {
    "tariff":       ["AAPL", "NVDA", "MU", "INTC", "QCOM", "AMAT", "LRCX"],
    "tariffs":      ["AAPL", "NVDA", "MU", "INTC", "QCOM", "AMAT", "LRCX"],
    "trade war":    ["AAPL", "NVDA", "MU", "BA", "CAT", "DE"],
    "rate cut":     ["JPM", "BAC", "WFC", "GS", "MS", "V", "MA"],
    "rate hike":    ["JPM", "BAC", "WFC", "GS", "MS"],
    "inflation":    ["PG", "KO", "MCD", "WMT", "COST"],
    "oil":          ["XOM", "CVX", "OXY", "COP", "SLB"],
    "semiconductor":["NVDA", "AMD", "INTC", "MU", "QCOM", "AMAT", "ASML"],
    "ai":           ["NVDA", "MSFT", "GOOGL", "AMZN", "META", "AMD"],
    "layoffs":      ["MSFT", "AMZN", "META", "GOOGL", "INTC"],
    "layoff":       ["MSFT", "AMZN", "META", "GOOGL", "INTC"],
    "defense":      ["LMT", "RTX", "NOC", "GD", "BA"],
    "drug":         ["JNJ", "PFE", "MRK", "ABBV", "LLY"],
    "approval":     ["JNJ", "PFE", "MRK", "ABBV", "LLY"],
    "bankruptcy":   ["SPY", "IWM"],
    "recession":    ["GLD", "TLT", "WMT", "COST"],
    "deal":         ["MSFT", "GOOGL", "AMZN", "AAPL"],
    "acquisition":  ["MSFT", "GOOGL", "AMZN", "AAPL"],
    "fine":         ["JPM", "BAC", "WFC", "GS"],
    "fined":        ["JPM", "BAC", "WFC", "GS"],
    "upgrade":      ["AAPL", "MSFT", "NVDA", "AMZN"],
    "downgrade":    ["AAPL", "MSFT", "NVDA", "AMZN"],
    "earnings":     ["SPY"],
    "buyback":      ["AAPL", "MSFT", "META", "GOOGL"],
}


# ── Price data ─────────────────────────────────────────────────────────────────
def _load_prices() -> pd.DataFrame:
    """Load wide-format price CSV; returns DataFrame indexed by date (date only)."""
    if not PRICE_CSV.exists():
        raise FileNotFoundError(f"{PRICE_CSV} not found — run update_snp500_history.py first.")
    df = pd.read_csv(PRICE_CSV)
    df["Date"] = pd.to_datetime(df["Date"], format="%m/%d/%y", errors="coerce")
    df = df.dropna(subset=["Date"]).set_index("Date").sort_index()
    return df


def _forward_returns(prices: pd.DataFrame, ticker: str, event_date: datetime) -> Optional[Dict]:
    """
    Return forward returns for ticker at 1, 2, 5, 10 trading days after event_date.
    Returns None if ticker not in prices or insufficient future data.
    """
    if ticker not in prices.columns:
        return None

    series = prices[ticker].dropna()
    future = series[series.index > pd.Timestamp(event_date)]

    if future.empty:
        return None

    base = float(series[series.index <= pd.Timestamp(event_date)].iloc[-1]) if not series[series.index <= pd.Timestamp(event_date)].empty else float(future.iloc[0])

    def _ret(n: int) -> Optional[float]:
        if len(future) >= n:
            return round(float(future.iloc[n - 1] - base) / base * 100, 4)
        return None

    return {"r1d": _ret(1), "r2d": _ret(2), "r5d": _ret(5), "r10d": _ret(10)}


# ── Signal event loading ───────────────────────────────────────────────────────
def _load_news_events() -> List[Dict]:
    """
    Load cached news signals. Each entry: {ticker, keyword, direction, published}.
    Falls back to empty list (fresh install) — framework populates over time.
    """
    if not NEWS_CACHE_PATH.exists():
        return []
    try:
        data = json.loads(NEWS_CACHE_PATH.read_text(encoding="utf-8"))
        return data.get("signals", [])
    except Exception as e:
        log.warning(f"Could not load news cache: {e}")
        return []


def _parse_event_date(published_str: str) -> Optional[datetime]:
    """Parse RSS published string to datetime."""
    if not published_str:
        return None
    # Typical: "Wed, 03 Jun 2026 00:15:15 +0000"
    for fmt in ("%a, %d %b %Y %H:%M:%S %z", "%a, %d %b %Y %H:%M:%S +0000"):
        try:
            return datetime.strptime(published_str, fmt).replace(tzinfo=None)
        except ValueError:
            pass
    # Fallback: try pandas
    try:
        return pd.to_datetime(published_str, utc=True).tz_localize(None).to_pydatetime()
    except Exception:
        return None


def _build_event_table() -> List[Dict]:
    """
    Build a flat list of (keyword, ticker, direction, event_date) events by:
    1. Loading news cache signals (ticker-keyed events)
    2. Expanding via KEYWORD_TICKER_MAP for political/macro keywords
    """
    events: List[Dict] = []
    seen = set()

    news_events = _load_news_events()
    for sig in news_events:
        kw = sig.get("keyword", "")
        ticker = sig.get("ticker", "")
        direction = sig.get("direction", "→")
        dt = _parse_event_date(sig.get("published", ""))
        if not dt:
            dt = datetime.utcnow() - timedelta(days=1)  # treat as yesterday

        # Direct ticker signal
        key = (kw, ticker, dt.date().isoformat())
        if key not in seen:
            events.append({"keyword": kw, "ticker": ticker, "direction": direction, "event_date": dt})
            seen.add(key)

        # Expand keyword to related tickers via map
        for related in KEYWORD_TICKER_MAP.get(kw.lower(), []):
            ekey = (kw, related, dt.date().isoformat())
            if ekey not in seen:
                events.append({"keyword": kw, "ticker": related, "direction": direction, "event_date": dt})
                seen.add(ekey)

    return events


# ── Core backtester ───────────────────────────────────────────────────────────
def backtest_keyword(keyword: str, ticker: str, prices: Optional[pd.DataFrame] = None) -> Dict:
    """
    Backtest a keyword+ticker pair against historical price data.
    Returns a result dict including hit_rate and forward returns.
    """
    if prices is None:
        prices = _load_prices()

    events = [e for e in _build_event_table()
               if e["keyword"].lower() == keyword.lower() and e["ticker"].upper() == ticker.upper()]

    if len(events) < MIN_SAMPLE_SIZE:
        return {
            "keyword": keyword, "ticker": ticker,
            "sample_size": len(events),
            "insufficient_data": True,
            "note": f"Need ≥{MIN_SAMPLE_SIZE} events; have {len(events)}."
        }

    returns_1d, returns_2d, returns_5d, returns_10d = [], [], [], []
    directions = []

    for e in events:
        fwd = _forward_returns(prices, ticker, e["event_date"])
        if fwd is None:
            continue
        if fwd["r1d"] is not None:
            returns_1d.append(fwd["r1d"])
        if fwd["r2d"] is not None:
            returns_2d.append(fwd["r2d"])
        if fwd["r5d"] is not None:
            returns_5d.append(fwd["r5d"])
            directions.append(e["direction"])
        if fwd["r10d"] is not None:
            returns_10d.append(fwd["r10d"])

    if not directions:
        return {
            "keyword": keyword, "ticker": ticker,
            "sample_size": len(events),
            "insufficient_data": True,
            "note": "Events found but no matching forward price data yet."
        }

    correct = sum(
        1 for d, r in zip(directions, returns_5d)
        if (d == "↑" and r > 0) or (d == "↓" and r < 0)
    )
    hit_rate = correct / len(directions) if directions else 0.0
    dominant_dir = max(set(directions), key=directions.count)

    def _safe_avg(lst):
        return round(float(np.mean(lst)), 4) if lst else None

    def _safe_median(lst):
        return round(float(np.median(lst)), 4) if lst else None

    return {
        "keyword": keyword,
        "ticker": ticker,
        "direction": dominant_dir,
        "hit_rate": round(hit_rate, 4),
        "avg_return_1d": _safe_avg(returns_1d),
        "avg_return_2d": _safe_avg(returns_2d),
        "avg_return_5d": _safe_avg(returns_5d),
        "median_return_5d": _safe_median(returns_5d),
        "avg_return_10d": _safe_avg(returns_10d),
        "sample_size": len(directions),
        "insufficient_data": False,
        "last_updated": datetime.utcnow().isoformat(timespec="seconds"),
    }


def backtest_all() -> Dict:
    """Run backtests for all keyword+ticker pairs in KEYWORD_TICKER_MAP."""
    log.info("Loading prices...")
    prices = _load_prices()
    available_tickers = set(prices.columns)

    results: List[Dict] = []
    for kw, tickers in KEYWORD_TICKER_MAP.items():
        for ticker in tickers:
            if ticker not in available_tickers:
                log.debug(f"[{ticker}] not in price data — skipping")
                continue
            r = backtest_keyword(kw, ticker, prices)
            results.append(r)

    payload = {
        "generated_at": datetime.utcnow().isoformat(timespec="seconds"),
        "total_pairs": len(results),
        "results": results,
    }
    BACKTEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    BACKTEST_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    log.info(f"Saved {len(results)} backtest entries to {BACKTEST_PATH}")
    return payload


# ── Public helpers ─────────────────────────────────────────────────────────────
def _load_results() -> List[Dict]:
    if not BACKTEST_PATH.exists():
        return []
    try:
        data = json.loads(BACKTEST_PATH.read_text(encoding="utf-8"))
        return data.get("results", [])
    except Exception:
        return []


def get_best_signals(min_hit_rate: float = 0.55, min_sample: int = MIN_SAMPLE_SIZE) -> List[Dict]:
    """Return keyword+ticker pairs with hit_rate > threshold and sufficient data."""
    return [
        r for r in _load_results()
        if not r.get("insufficient_data")
        and r.get("hit_rate", 0) >= min_hit_rate
        and r.get("sample_size", 0) >= min_sample
    ]


def get_signal_leaderboard() -> List[Dict]:
    """All valid results sorted by hit_rate descending."""
    valid = [r for r in _load_results() if not r.get("insufficient_data")]
    return sorted(valid, key=lambda r: r.get("hit_rate", 0), reverse=True)


# ── CLI ────────────────────────────────────────────────────────────────────────
def main() -> None:
    parser = argparse.ArgumentParser(description="Political Speech Signal Backtester")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--run", action="store_true", help="Run full backtest and save results")
    group.add_argument("--leaderboard", action="store_true", help="Print signal leaderboard from saved results")
    args = parser.parse_args()

    if args.run:
        payload = backtest_all()
        valid = [r for r in payload["results"] if not r.get("insufficient_data")]
        print(f"\n{'═'*80}")
        print(f"  Backtest complete  |  {payload['total_pairs']} pairs tested, {len(valid)} with sufficient data")
        print(f"  Results saved → {BACKTEST_PATH}")
        print(f"{'═'*80}\n")
        if valid:
            _print_leaderboard(sorted(valid, key=lambda r: r.get("hit_rate", 0), reverse=True))
        else:
            print("  ⚠️  No pairs have sufficient data (≥3 events) yet.")
            print("  Run get_news_signals() regularly to accumulate events — signals strengthen over time.")
    else:
        board = get_signal_leaderboard()
        print(f"\n{'═'*80}")
        print(f"  Signal Leaderboard  |  {len(board)} entries with sufficient data")
        print(f"{'═'*80}\n")
        if board:
            _print_leaderboard(board)
        else:
            print("  No leaderboard data yet. Run: python speech_backtest.py --run")


def _print_leaderboard(results: List[Dict]) -> None:
    header = f"  {'Keyword':<20} {'Ticker':<7} {'Dir':>3} {'HitRate':>8} {'Avg5d%':>8} {'Med5d%':>8} {'N':>4}"
    print(header)
    print("  " + "─" * (len(header) - 2))
    for r in results[:20]:
        avg5 = r.get("avg_return_5d")
        med5 = r.get("median_return_5d")
        print(
            f"  {r['keyword']:<20} {r['ticker']:<7} {r.get('direction','?'):>3} "
            f"{r['hit_rate']*100:>7.1f}%  "
            f"{avg5*100:>7.2f}%  " if avg5 is not None else f"{'N/A':>8}  "
            f"{med5*100:>7.2f}%  " if med5 is not None else f"{'N/A':>8}  "
            f"{r['sample_size']:>4}"
        )


if __name__ == "__main__":
    main()
