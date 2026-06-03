"""
hedge_fund_mirror.py — 13F Hedge Fund Holdings Mirror

Fetches latest 13F filings for major hedge funds via edgartools.

Funds tracked:
  Berkshire Hathaway  CIK 0001067983
  Bridgewater         CIK 0001350694
  Duquesne            CIK 0001536411

Output: data/hedge_fund_holdings.json
Function: get_fund_holdings(fund_name) -> pd.DataFrame
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

import pandas as pd
import edgar

HOLDINGS_PATH = Path("data/hedge_fund_holdings.json")
CACHE_TTL_HOURS = 24
EDGAR_IDENTITY = "SmartPortfolioBot research@smartportfoliobot.com"

FUNDS = {
    "Berkshire Hathaway": "0001067983",
    "Bridgewater":        "0001350694",
    "Duquesne":           "0001536411",
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# ── Cache ──────────────────────────────────────────────────────────────────────
def _load_cache() -> dict:
    if HOLDINGS_PATH.exists():
        try:
            return json.loads(HOLDINGS_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _save_cache(data: dict) -> None:
    HOLDINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    HOLDINGS_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _is_stale(entry: dict) -> bool:
    ts = entry.get("_fetched_at")
    if not ts:
        return True
    try:
        age = datetime.utcnow() - datetime.fromisoformat(ts)
        from datetime import timedelta
        return age.total_seconds() > CACHE_TTL_HOURS * 3600
    except Exception:
        return True


# ── Fetch one fund ─────────────────────────────────────────────────────────────
def _fetch_fund(fund_name: str, cik: str) -> dict:
    edgar.set_identity(EDGAR_IDENTITY)
    entity = edgar.get_entity(cik)
    filings = entity.get_filings(form="13F-HR")

    if not filings or len(filings) == 0:
        raise RuntimeError(f"No 13F-HR filings found for {fund_name}")

    latest = filings[0]
    obj = latest.obj()
    holdings_df: pd.DataFrame = obj.holdings.copy()

    # Normalise columns
    holdings_df.columns = [c.strip() for c in holdings_df.columns]

    # Add % of portfolio by market value
    total_value = holdings_df["Value"].sum()
    holdings_df["pct_portfolio"] = (
        (holdings_df["Value"] / total_value * 100).round(4) if total_value else 0.0
    )
    holdings_df = holdings_df.sort_values("Value", ascending=False).reset_index(drop=True)
    holdings_df = holdings_df.head(50)  # top 50 positions

    # Serialise
    records = []
    for _, row in holdings_df.iterrows():
        records.append({
            "ticker":        str(row.get("Ticker", "") or ""),
            "issuer":        str(row.get("Issuer", "") or ""),
            "shares":        int(row.get("SharesPrnAmount", 0) or 0),
            "market_value":  int(row.get("Value", 0) or 0),
            "pct_portfolio": float(row.get("pct_portfolio", 0.0)),
        })

    return {
        "fund_name":    fund_name,
        "cik":          cik,
        "filing_date":  str(latest.filing_date),
        "holdings":     records,
        "_fetched_at":  datetime.utcnow().isoformat(timespec="seconds"),
    }


# ── Public API ─────────────────────────────────────────────────────────────────
def get_fund_holdings(fund_name: str) -> pd.DataFrame:
    """
    Return a DataFrame of top holdings for the named fund.
    Uses cache if fresh, otherwise fetches from EDGAR.
    """
    cache = _load_cache()
    if fund_name in cache and not _is_stale(cache[fund_name]):
        log.info(f"[{fund_name}] cache hit")
        return pd.DataFrame(cache[fund_name]["holdings"])

    cik = FUNDS.get(fund_name)
    if not cik:
        raise ValueError(f"Unknown fund '{fund_name}'. Available: {list(FUNDS)}")

    log.info(f"[{fund_name}] fetching 13F from EDGAR...")
    entry = _fetch_fund(fund_name, cik)
    cache[fund_name] = entry
    _save_cache(cache)
    return pd.DataFrame(entry["holdings"])


def fetch_all_funds() -> None:
    """Refresh all funds and save to cache."""
    cache = _load_cache()
    for name, cik in FUNDS.items():
        try:
            entry = _fetch_fund(name, cik)
            cache[name] = entry
            _save_cache(cache)
            log.info(f"[{name}] ✅ {len(entry['holdings'])} positions, filed {entry['filing_date']}")
        except Exception as e:
            log.error(f"[{name}] ❌ {e}")
        time.sleep(1.0)


# ── CLI ────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Fetch 13F hedge fund holdings.")
    parser.add_argument("--fund", choices=list(FUNDS), help="Single fund name")
    parser.add_argument("--all", action="store_true", help="Fetch all funds")
    parser.add_argument("--top", type=int, default=10, help="Top N positions to display")
    args = parser.parse_args()

    if args.all or not args.fund:
        fetch_all_funds()
        funds_to_show = list(FUNDS)
    else:
        get_fund_holdings(args.fund)
        funds_to_show = [args.fund]

    cache = _load_cache()
    for fname in funds_to_show:
        if fname not in cache:
            continue
        entry = cache[fname]
        print(f"\n{'═'*70}")
        print(f"  {fname}  |  Filed: {entry['filing_date']}  |  Top {args.top} positions")
        print(f"{'═'*70}")
        print(f"  {'Ticker':<8} {'Issuer':<35} {'Shares':>12} {'Mkt Value $':>14} {'% Port':>7}")
        print("  " + "─" * 80)
        for h in entry["holdings"][: args.top]:
            print(
                f"  {h['ticker']:<8} {h['issuer'][:34]:<35} "
                f"{h['shares']:>12,} {h['market_value']:>14,} {h['pct_portfolio']:>6.2f}%"
            )
