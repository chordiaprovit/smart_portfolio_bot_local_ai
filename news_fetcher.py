"""
news_fetcher.py

Fetches recent news headlines from Yahoo Finance RSS feeds and extracts
ticker-keyed signals by matching bullish/bearish keywords.

No API key required — uses public Yahoo Finance RSS.

Functions:
  get_news_signals(tickers=None)   -> list of signal dicts
  get_ticker_news_score(ticker)    -> float 0-10 (used by convergence_score)
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional

import feedparser

CACHE_PATH = Path("data/news_signals.json")
CACHE_TTL_MINUTES = 60
REQUEST_DELAY = 0.3

log = logging.getLogger(__name__)

# ── Keyword dictionaries ───────────────────────────────────────────────────────
BULLISH = {
    "beat", "beats", "upgrade", "upgraded", "raised", "raises", "record",
    "surge", "surges", "approval", "approved", "buyback", "dividend",
    "acquisition", "acquires", "growth", "strong", "outperform", "overweight",
    "buy rating", "partnership", "deal", "contract", "wins", "revenue up",
    "profit up", "guidance raised", "tops estimates", "exceeds", "bullish",
    "breakout", "recovery", "rebound",
}
BEARISH = {
    "miss", "misses", "downgrade", "downgraded", "cut", "cuts", "recall",
    "layoffs", "layoff", "lawsuit", "fine", "fined", "tariff", "tariffs",
    "trade war", "decline", "declines", "weak", "loss", "losses", "warning",
    "guidance cut", "below expectations", "shortfall", "underperform",
    "sell rating", "bankruptcy", "investigation", "probe", "fraud",
    "drop", "drops", "fell", "plunged", "crash", "bearish", "slump",
    "deficit", "miss estimates", "disappoints",
}

# ── RSS feed helpers ───────────────────────────────────────────────────────────
def _yahoo_rss_url(ticker: str) -> str:
    return f"https://feeds.finance.yahoo.com/rss/2.0/headline?s={ticker}&region=US&lang=en-US"


def _score_headline(headline: str) -> tuple[str, str, float]:
    """Return (direction ↑/↓/→, matched_keyword, score 0-10)."""
    h = headline.lower()
    bull_hits = [kw for kw in BULLISH if kw in h]
    bear_hits = [kw for kw in BEARISH if kw in h]
    net = len(bull_hits) - len(bear_hits)
    keyword = (bull_hits + bear_hits)[0] if (bull_hits or bear_hits) else ""

    if net > 0:
        score = min(10.0, 5.0 + net * 1.5)
        direction = "↑"
    elif net < 0:
        score = max(0.0, 5.0 + net * 1.5)
        direction = "↓"
    else:
        score = 5.0
        direction = "→"

    return direction, keyword, round(score, 2)


# ── Cache ──────────────────────────────────────────────────────────────────────
def _load_cache() -> Optional[dict]:
    if not CACHE_PATH.exists():
        return None
    try:
        data = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        fetched = datetime.fromisoformat(data.get("fetched_at", "2000-01-01"))
        age = datetime.utcnow() - fetched
        if age < timedelta(minutes=CACHE_TTL_MINUTES):
            return data
    except Exception:
        pass
    return None


def _save_cache(signals: List[Dict]) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(
        json.dumps({"fetched_at": datetime.utcnow().isoformat(timespec="seconds"), "signals": signals}, indent=2),
        encoding="utf-8",
    )


# ── Core fetch ─────────────────────────────────────────────────────────────────
def _fetch_for_ticker(ticker: str, max_items: int = 10) -> List[Dict]:
    url = _yahoo_rss_url(ticker)
    try:
        feed = feedparser.parse(url)
        signals: List[Dict] = []
        for entry in feed.entries[:max_items]:
            title = entry.get("title", "")
            direction, keyword, score = _score_headline(title)
            if not keyword:
                continue
            signals.append({
                "ticker": ticker.upper(),
                "headline": title,
                "keyword": keyword,
                "direction": direction,
                "score": score,
                "source": (entry.get("source") or {}).get("title", "Yahoo Finance"),
                "url": entry.get("link", ""),
                "published": entry.get("published", ""),
            })
        return signals
    except Exception as e:
        log.warning(f"[{ticker}] RSS fetch error: {e}")
        return []


# ── Public API ─────────────────────────────────────────────────────────────────
def get_news_signals(
    tickers: Optional[List[str]] = None,
    use_cache: bool = True,
    max_per_ticker: int = 10,
) -> List[Dict]:
    """
    Fetch and return keyword-matched news signals for all tickers.
    If tickers is None, returns cached signals (or empty list).
    Results are sorted by score descending.
    """
    if use_cache:
        cached = _load_cache()
        if cached:
            signals = cached["signals"]
            if tickers:
                upper = {t.upper() for t in tickers}
                signals = [s for s in signals if s["ticker"] in upper]
            return signals

    if not tickers:
        return []

    all_signals: List[Dict] = []
    for ticker in tickers:
        sigs = _fetch_for_ticker(ticker.upper(), max_items=max_per_ticker)
        all_signals.extend(sigs)
        time.sleep(REQUEST_DELAY)

    all_signals.sort(key=lambda s: s["score"], reverse=True)
    _save_cache(all_signals)
    return all_signals


def get_ticker_news_score(ticker: str, signals: Optional[List[Dict]] = None) -> float:
    """
    Return a 0-10 news sentiment score for a single ticker.
    Uses provided signals list if given; otherwise fetches fresh.
    Returns 5.0 (neutral) if no signals found.
    """
    if signals is None:
        signals = _fetch_for_ticker(ticker.upper())
    ticker_sigs = [s for s in signals if s["ticker"].upper() == ticker.upper()]
    if not ticker_sigs:
        return 5.0
    return round(sum(s["score"] for s in ticker_sigs) / len(ticker_sigs), 2)


# ── CLI ────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s", datefmt="%H:%M:%S")

    parser = argparse.ArgumentParser(description="Fetch news signals for tickers.")
    parser.add_argument("--tickers", nargs="+", required=True)
    args = parser.parse_args()

    sigs = get_news_signals(args.tickers, use_cache=False)
    print(f"\n{len(sigs)} signals found\n")
    for s in sigs:
        print(f"  {s['direction']} {s['ticker']:<6} [{s['score']:4.1f}]  {s['keyword']:<18}  {s['headline'][:80]}")
