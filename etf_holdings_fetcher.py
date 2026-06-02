"""
etf_holdings_fetcher.py

Fetches ETF constituent holdings: ticker weights, ETF info (AUM, expense ratio, category).

Primary source:  etf-database.com (requests + BeautifulSoup, no API key)
Fallback:        yfinance .info['holdings']
Cache:           data/etf_holdings.json — refreshed after 24 hours per symbol.

CLI:
    python etf_holdings_fetcher.py --etf QQQ SPY XLK
    python etf_holdings_fetcher.py --all
"""

from __future__ import annotations

import argparse
import json
import logging
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List

import requests
from bs4 import BeautifulSoup
import yfinance as yf

# ── Config ─────────────────────────────────────────────────────────────────────
HOLDINGS_PATH = Path("data/etf_holdings.json")
ETF_SYMBOLS_FILE = Path("etf_symbols.txt")
CACHE_TTL_HOURS = 24
REQUEST_DELAY = 1.5  # polite delay between HTTP requests (seconds)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


# ── Cache helpers ──────────────────────────────────────────────────────────────
def _load_cache() -> Dict:
    if HOLDINGS_PATH.exists():
        try:
            return json.loads(HOLDINGS_PATH.read_text(encoding="utf-8"))
        except Exception as e:
            log.warning(f"Cache read error ({e}) — starting fresh.")
    return {}


def _save_cache(data: Dict) -> None:
    HOLDINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    HOLDINGS_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _is_stale(entry: Dict) -> bool:
    ts = entry.get("_fetched_at")
    if not ts:
        return True
    try:
        return datetime.utcnow() - datetime.fromisoformat(ts) > timedelta(hours=CACHE_TTL_HOURS)
    except Exception:
        return True


# ── Symbol list ────────────────────────────────────────────────────────────────
def read_etf_symbols(path: Path = ETF_SYMBOLS_FILE) -> List[str]:
    if not path.exists():
        raise FileNotFoundError(f"{path} not found.")
    return [
        line.strip().upper()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]


# ── yfinance helpers ───────────────────────────────────────────────────────────
def _fetch_yf_info(symbol: str) -> Dict:
    try:
        info = yf.Ticker(symbol).info
        aum = info.get("totalAssets") or info.get("netAssets")
        return {
            "short_name": info.get("shortName", ""),
            "long_name": info.get("longName", ""),
            "expense_ratio": info.get("annualReportExpenseRatio"),
            "aum": int(aum) if aum else None,
            "category": info.get("category"),
            "fund_family": info.get("fundFamily"),
            "nav": info.get("navPrice"),
            "exchange": info.get("exchange"),
        }
    except Exception as e:
        log.warning(f"[{symbol}] yfinance info error: {e}")
        return {}


def _yf_holdings_fallback(symbol: str) -> List[Dict]:
    """yfinance returns top ~10 holdings for some ETFs via .info['holdings']."""
    try:
        raw = yf.Ticker(symbol).info.get("holdings") or []
        return [
            {
                "ticker": h.get("symbol", ""),
                "name": h.get("holdingName", ""),
                "weight": round(float(h.get("holdingPercent", 0.0)), 6),
            }
            for h in raw
            if h.get("symbol")
        ]
    except Exception as e:
        log.warning(f"[{symbol}] yfinance holdings fallback error: {e}")
        return []


# ── etfdb.com scraper ──────────────────────────────────────────────────────────
def _scrape_etfdb(symbol: str) -> List[Dict]:
    """
    Scrape top holdings from etfdb.com (table id='etf-holdings').
    Returns [] on any failure — caller will use yfinance fallback.
    """
    url = f"https://etfdb.com/etf/{symbol}/"
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        table = soup.find("table", {"id": "etf-holdings"})
        if not table:
            log.debug(f"[{symbol}] etfdb.com: 'etf-holdings' table not found in page")
            return []

        tbody = table.find("tbody")
        if not tbody:
            return []

        holdings: List[Dict] = []
        for row in tbody.find_all("tr"):
            cells = [td.get_text(strip=True) for td in row.find_all("td")]
            if len(cells) < 3:
                continue
            ticker = cells[0].upper()
            name = cells[1]
            weight_str = cells[2].rstrip("%")
            try:
                weight = round(float(weight_str) / 100.0, 6)
            except ValueError:
                weight = 0.0
            if ticker:
                holdings.append({"ticker": ticker, "name": name, "weight": weight})

        log.info(f"[{symbol}] etfdb.com: scraped {len(holdings)} holdings")
        return holdings

    except requests.HTTPError as e:
        log.warning(f"[{symbol}] etfdb.com HTTP {e.response.status_code}: {e}")
        return []
    except Exception as e:
        log.warning(f"[{symbol}] etfdb.com scrape error: {e}")
        return []


# ── Core fetch ─────────────────────────────────────────────────────────────────
def fetch_one(symbol: str, cache: Dict) -> Dict:
    """Fetch one ETF entry. Returns cache hit if still fresh."""
    symbol = symbol.upper().strip()

    if symbol in cache and not _is_stale(cache[symbol]):
        log.info(f"[{symbol}] cache hit (age < {CACHE_TTL_HOURS}h)")
        return cache[symbol]

    log.info(f"[{symbol}] fetching from remote...")
    info = _fetch_yf_info(symbol)

    holdings = _scrape_etfdb(symbol)
    time.sleep(REQUEST_DELAY)

    source = "etfdb"
    if not holdings:
        log.info(f"[{symbol}] etfdb returned nothing — trying yfinance fallback")
        holdings = _yf_holdings_fallback(symbol)
        source = "yfinance" if holdings else "none"

    return {
        "info": info,
        "holdings": holdings,
        "holdings_source": source,
        "_fetched_at": datetime.utcnow().isoformat(timespec="seconds"),
    }


# ── Public API ─────────────────────────────────────────────────────────────────
def get_etf_holdings(symbol: str) -> Dict:
    """
    Return the holdings entry for a single ETF.
    Reads from cache if fresh; otherwise fetches and updates the cache.
    """
    symbol = symbol.upper().strip()
    cache = _load_cache()
    entry = fetch_one(symbol, cache)
    cache[symbol] = entry
    _save_cache(cache)
    return entry


def get_etf_overlap(portfolio_tickers: List[str]) -> Dict[str, Dict]:
    """
    For every ETF in the local cache, compute how much it overlaps with
    the given list of stock tickers.

    Returns a dict keyed by ETF symbol, sorted by overlap_weight descending:
        {
          "QQQ": {
              "overlap_tickers": ["AAPL", "MSFT"],
              "overlap_weight":  0.15,
              "overlap_count":   2,
              "total_holdings":  15,
          }, ...
        }
    """
    cache = _load_cache()
    needle = {t.upper().strip() for t in portfolio_tickers}
    result: Dict[str, Dict] = {}

    for etf_sym, entry in cache.items():
        holdings = entry.get("holdings", [])
        if not holdings:
            continue
        matched = [h for h in holdings if h.get("ticker", "").upper() in needle]
        if not matched:
            continue
        result[etf_sym] = {
            "overlap_tickers": [h["ticker"] for h in matched],
            "overlap_weight": round(sum(h.get("weight", 0.0) for h in matched), 4),
            "overlap_count": len(matched),
            "total_holdings": len(holdings),
        }

    return dict(sorted(result.items(), key=lambda x: x[1]["overlap_weight"], reverse=True))


# ── CLI ────────────────────────────────────────────────────────────────────────
def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fetch ETF constituent holdings from etfdb.com (yfinance fallback)."
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--etf", nargs="+", metavar="SYMBOL", help="One or more ETF symbols")
    group.add_argument("--all", action="store_true", help="Fetch all symbols from etf_symbols.txt")
    args = parser.parse_args()

    targets = read_etf_symbols() if args.all else [s.upper() for s in args.etf]
    log.info(f"Targets ({len(targets)}): {targets}")

    cache = _load_cache()
    ok, failed = 0, []

    for sym in targets:
        try:
            entry = fetch_one(sym, cache)
            cache[sym] = entry
            _save_cache(cache)

            n_holdings = len(entry.get("holdings", []))
            info = entry.get("info", {})
            aum = info.get("aum")
            aum_str = f"${aum / 1e9:.1f}B" if aum else "N/A"
            source = entry.get("holdings_source", "?")
            category = info.get("category") or "—"
            name = info.get("short_name") or info.get("long_name") or sym

            print(
                f"  {sym:<6}  {name:<35}  "
                f"AUM {aum_str:<10}  "
                f"Category: {category:<22}  "
                f"Holdings: {n_holdings:>3}  "
                f"[{source}]"
            )
            ok += 1
        except Exception as e:
            log.error(f"[{sym}] unexpected error: {e}")
            failed.append(sym)

    print(f"\n{'─'*60}")
    print(f"Fetched {ok}/{len(targets)} ETFs.  Cache: {HOLDINGS_PATH}")
    if failed:
        print(f"Failed: {failed}")


if __name__ == "__main__":
    main()
