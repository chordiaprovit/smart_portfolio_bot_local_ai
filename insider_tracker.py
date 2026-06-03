"""
insider_tracker.py

Fetches SEC Form 4 insider trading signals via edgartools (SEC EDGAR).
Focuses on transaction code "P" (open market purchases) — highest-signal events.

Signal classification:
  HIGH   — C-suite (CEO/CFO/COO/President) buy > $500k
  MEDIUM — C-suite buy > $100k  OR  Director buy > $500k
  LOW    — any other open market purchase

Output functions:
  get_insider_signals(tickers)        -> all P-buy signals
  get_high_conviction_buys(tickers)   -> HIGH signals only

CLI:
  python insider_tracker.py --tickers NVDA AAPL MSFT DELL MU JPM
"""

from __future__ import annotations

import argparse
import json
import logging
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

import edgar

# ── Config ─────────────────────────────────────────────────────────────────────
SIGNALS_PATH = Path("data/insider_signals.json")
LOOKBACK_DAYS = 90          # how far back to scan Form 4 filings
REQUEST_DELAY = 0.5         # seconds between EDGAR requests
EDGAR_IDENTITY = "SmartPortfolioBot research@smartportfoliobot.com"

_CSUITE_KEYWORDS = {"ceo", "cfo", "coo", "president", "chief executive",
                    "chief financial", "chief operating", "chief"}
_DIRECTOR_KEYWORDS = {"director"}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# ── Role helpers ───────────────────────────────────────────────────────────────
def _is_csuite(position: str) -> bool:
    p = position.lower()
    return any(kw in p for kw in _CSUITE_KEYWORDS)


def _is_director(position: str) -> bool:
    p = position.lower()
    return any(kw in p for kw in _DIRECTOR_KEYWORDS)


def _classify_signal(position: str, total_value: float) -> str:
    if _is_csuite(position):
        if total_value >= 500_000:
            return "HIGH"
        if total_value >= 100_000:
            return "MEDIUM"
        return "LOW"
    if _is_director(position):
        if total_value >= 500_000:
            return "MEDIUM"
        return "LOW"
    return "LOW"


# ── Core fetch ─────────────────────────────────────────────────────────────────
def _fetch_signals_for_ticker(ticker: str, since: date) -> List[Dict]:
    """
    Return a list of signal dicts for open-market purchases (code='P')
    filed on or after `since`.
    """
    signals: List[Dict] = []
    ticker = ticker.upper().strip()

    try:
        company = edgar.Company(ticker)
    except Exception as e:
        log.warning(f"[{ticker}] Company lookup failed: {e}")
        return signals

    try:
        filings = company.get_filings(
            form="4",
            filing_date=(since.isoformat(), date.today().isoformat()),
        )
    except Exception as e:
        log.warning(f"[{ticker}] get_filings failed: {e}")
        return signals

    if not filings or len(filings) == 0:
        log.info(f"[{ticker}] no Form 4 filings in window")
        return signals

    log.info(f"[{ticker}] scanning {len(filings)} Form 4 filings since {since}...")

    for filing in filings:
        time.sleep(REQUEST_DELAY)
        try:
            form4 = filing.obj()
            if form4 is None:
                continue

            ndt = form4.non_derivative_table
            if ndt is None or ndt.empty:
                continue

            mt = ndt.market_trades
            if mt is None or mt.empty:
                continue

            p_rows = mt[mt["Code"] == "P"]
            if p_rows.empty:
                continue

            insider_name = form4.insider_name or "Unknown"
            position = form4.position or ""
            filing_date_str = filing.filing_date.isoformat() if filing.filing_date else ""

            # Aggregate multiple same-filing rows into one signal
            total_shares = float(p_rows["Shares"].sum())
            # weighted average price
            prices = p_rows["Price"].astype(float)
            shares = p_rows["Shares"].astype(float)
            avg_price = float((prices * shares).sum() / shares.sum()) if total_shares else 0.0
            total_value = total_shares * avg_price
            txn_date = str(p_rows["Date"].iloc[0]) if not p_rows.empty else filing_date_str

            signal = {
                "ticker": ticker,
                "insider_name": insider_name,
                "insider_role": position,
                "shares_bought": round(total_shares, 0),
                "price_per_share": round(avg_price, 4),
                "total_value": round(total_value, 2),
                "transaction_date": txn_date,
                "filing_date": filing_date_str,
                "signal_strength": _classify_signal(position, total_value),
            }
            signals.append(signal)
            log.info(
                f"[{ticker}] P-buy: {insider_name} ({position}) "
                f"${total_value:,.0f} on {txn_date} → {signal['signal_strength']}"
            )

        except Exception as e:
            log.debug(f"[{ticker}] filing parse error ({filing.filing_date}): {e}")
            continue

    return signals


# ── Public API ─────────────────────────────────────────────────────────────────
def get_insider_signals(tickers: List[str], lookback_days: int = LOOKBACK_DAYS) -> List[Dict]:
    """
    Fetch open-market purchase signals (Form 4, code='P') for all tickers.
    Saves results to data/insider_signals.json.
    Returns a flat list of signal dicts sorted by total_value descending.
    """
    edgar.set_identity(EDGAR_IDENTITY)
    since = date.today() - timedelta(days=lookback_days)

    all_signals: List[Dict] = []
    for ticker in tickers:
        try:
            sigs = _fetch_signals_for_ticker(ticker, since)
            all_signals.extend(sigs)
        except Exception as e:
            log.error(f"[{ticker}] unexpected error: {e}")
        time.sleep(REQUEST_DELAY)

    all_signals.sort(key=lambda s: s["total_value"], reverse=True)

    _save_signals(all_signals)
    return all_signals


def get_high_conviction_buys(tickers: List[str], lookback_days: int = LOOKBACK_DAYS) -> List[Dict]:
    """Return only HIGH-signal insider buys."""
    return [s for s in get_insider_signals(tickers, lookback_days) if s["signal_strength"] == "HIGH"]


# ── Persistence ────────────────────────────────────────────────────────────────
def _save_signals(signals: List[Dict]) -> None:
    SIGNALS_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": datetime.utcnow().isoformat(timespec="seconds"),
        "count": len(signals),
        "signals": signals,
    }
    SIGNALS_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    log.info(f"Saved {len(signals)} signals to {SIGNALS_PATH}")


# ── CLI ────────────────────────────────────────────────────────────────────────
_STRENGTH_ICON = {"HIGH": "🔴", "MEDIUM": "🟡", "LOW": "🟢"}


def _print_table(signals: List[Dict]) -> None:
    if not signals:
        print("  No open-market purchases found in the lookback window.")
        return

    header = f"{'':2} {'Ticker':<6} {'Insider':<26} {'Role':<24} {'Shares':>8} {'Price':>9} {'Total $':>12} {'Date':<12} {'Strength'}"
    print(header)
    print("─" * len(header))
    for s in signals:
        icon = _STRENGTH_ICON.get(s["signal_strength"], "  ")
        print(
            f"{icon}  {s['ticker']:<6} {s['insider_name']:<26} {s['insider_role']:<24} "
            f"{int(s['shares_bought']):>8,} {s['price_per_share']:>9.2f} "
            f"{s['total_value']:>12,.0f} {s['transaction_date']:<12} {s['signal_strength']}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fetch SEC Form 4 insider open-market purchase signals."
    )
    parser.add_argument(
        "--tickers", nargs="+", required=True, metavar="SYMBOL",
        help="Ticker symbols to scan"
    )
    parser.add_argument(
        "--days", type=int, default=LOOKBACK_DAYS,
        help=f"Lookback window in days (default: {LOOKBACK_DAYS})"
    )
    parser.add_argument(
        "--high-only", action="store_true",
        help="Print only HIGH conviction signals"
    )
    args = parser.parse_args()

    tickers = [t.upper() for t in args.tickers]
    print(f"\nScanning {len(tickers)} ticker(s) for Form 4 P-buys (last {args.days} days)...\n")

    signals = get_insider_signals(tickers, lookback_days=args.days)

    if args.high_only:
        signals = [s for s in signals if s["signal_strength"] == "HIGH"]

    strength_counts = {"HIGH": 0, "MEDIUM": 0, "LOW": 0}
    for s in signals:
        strength_counts[s["signal_strength"]] = strength_counts.get(s["signal_strength"], 0) + 1

    print(f"\n{'═'*100}")
    print(f"  Insider Open-Market Purchases  |  {len(signals)} signal(s) found")
    print(f"  🔴 HIGH: {strength_counts['HIGH']}   🟡 MEDIUM: {strength_counts['MEDIUM']}   🟢 LOW: {strength_counts['LOW']}")
    print(f"{'═'*100}\n")

    _print_table(signals)

    print(f"\n  Results saved → {SIGNALS_PATH}")


if __name__ == "__main__":
    main()
