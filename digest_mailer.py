"""
digest_mailer.py — Daily Market Update Email

Sends at 9:00 PM ET on weekdays via GitHub Actions.
Reads pre-cached data files — does NOT re-fetch live data.

Email sections:
  1. 📊 What Happened Today
  2. 🔎 Stocks Worth Watching Tommorow
  3. 👀 Company Insiders Are Buying Their Own Stock
  4. 📰 News That Could Move Stocks
  5. 🐳 What Big Investors Are Doing
  6. 📊 How the Market Did Today
  7. ✅ Signals That Have Actually Worked
  8. ⚠️ Just So You Know

CLI:
  python digest_mailer.py --preview   (saves HTML locally, does NOT send)
  python digest_mailer.py --send      (builds and sends to all recipients)
  python digest_mailer.py --test      (sends to first recipient only)
"""

from __future__ import annotations

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import argparse
import json
import logging
import os
import smtplib
import ssl
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import List, Optional

import pandas as pd

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s", datefmt="%H:%M:%S")

RECIPIENTS_FILE = Path("data/digest_recipients.txt")
DIGESTS_DIR = Path("data/digests")

# Data file paths
CONVERGENCE_PATH = Path("data/convergence_scores.json")
INSIDER_PATH = Path("data/insider_signals.json")
BACKTEST_PATH = Path("data/backtest_results.json")
HEDGE_PATH = Path("data/hedge_fund_holdings.json")
NEWS_CACHE_PATH = Path("data/news_signals.json")
ETF_PRICES_PATH = Path("data/etf_prices_converted.csv")

_BENCHMARK_ETFS = ["SPY", "QQQ", "VTI", "GLD", "TLT"]


# ── Recipients ─────────────────────────────────────────────────────────────────
def read_recipients(path: Path = RECIPIENTS_FILE) -> List[str]:
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    emails: List[str] = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        for sep in [",", ";"]:
            line = line.replace(sep, "\n")
        for part in line.splitlines():
            part = part.strip()
            if "@" in part:
                emails.append(part)
    return list(dict.fromkeys(emails))  # deduplicate preserving order


# ── Data loaders ───────────────────────────────────────────────────────────────
def _load_json(path: Path, default=None):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        log.warning(f"Could not load {path}: {e}")
        return default


def _load_convergence() -> List[dict]:
    data = _load_json(CONVERGENCE_PATH, {})
    return data.get("scores", []) if data else []


def _load_insider() -> List[dict]:
    data = _load_json(INSIDER_PATH, {})
    return data.get("signals", []) if data else []


def _load_backtest() -> List[dict]:
    data = _load_json(BACKTEST_PATH, {})
    results = data.get("results", []) if data else []
    return sorted(
        [r for r in results if not r.get("insufficient_data") and r.get("hit_rate", 0) >= 0.55],
        key=lambda r: r.get("hit_rate", 0),
        reverse=True,
    )


def _load_hedge_notable() -> Optional[dict]:
    data = _load_json(HEDGE_PATH, {})
    if not data:
        return None
    for fund_name, entry in data.items():
        holdings = entry.get("holdings", [])
        if holdings:
            top = holdings[0]
            return {
                "fund": fund_name,
                "ticker": top.get("ticker", ""),
                "issuer": top.get("issuer", ""),
                "pct": top.get("pct_portfolio", 0),
                "value": top.get("market_value", 0),
                "filing_date": entry.get("filing_date", ""),
            }
    return None


def _load_news_signals() -> List[dict]:
    try:
        from news_fetcher import get_news_signals
        cached = _load_json(NEWS_CACHE_PATH, {})
        if cached:
            return cached.get("signals", [])[:5]
    except Exception:
        pass
    return []


def _load_etf_pulse() -> dict:
    if not ETF_PRICES_PATH.exists():
        return {}
    try:
        df = pd.read_csv(ETF_PRICES_PATH, index_col=0, parse_dates=True)
        df = df.sort_index()
        if len(df) < 2:
            return {}
        last = df.iloc[-1]
        prev = df.iloc[-2]
        changes = ((last - prev) / prev * 100).dropna()
        return {"changes": changes.to_dict(), "last_date": str(df.index[-1].date())}
    except Exception as e:
        log.warning(f"Could not load ETF prices: {e}")
        return {}


# ── ETF Pulse section builder ──────────────────────────────────────────────────
_ETF_LABELS = {
    "SPY": "S&P 500 (SPY) — most big US stocks",
    "QQQ": "Tech stocks (QQQ) — mostly big tech companies",
    "VTI": "All US stocks (VTI) — broad US market",
    "GLD": "Gold (GLD) — the metal as an investment",
    "TLT": "Long-term US bonds (TLT) — government debt",
}


def _build_etf_pulse_section(etf_data: dict) -> str:
    if not etf_data:
        return _section(
            "📊 How the Market Did Today",
            "<p style='color:#6b7280;'>Market data not loaded yet — it updates automatically each evening.</p>",
        )

    changes = etf_data.get("changes", {})
    last_date = etf_data.get("last_date", "")
    sorted_changes = sorted(changes.items(), key=lambda x: x[1], reverse=True)
    gainers = sorted_changes[:3]
    losers = list(reversed(sorted_changes[-3:]))

    def _chg_cell(chg: float) -> str:
        color = "#16a34a" if chg >= 0 else "#dc2626"
        arrow = "▲" if chg >= 0 else "▼"
        return f'<td style="padding:6px 10px;color:{color};font-weight:600;">{arrow} {abs(chg):.2f}%</td>'

    # Benchmark table with plain descriptions
    bench_rows = ""
    for tk in _BENCHMARK_ETFS:
        if tk in changes:
            chg = changes[tk]
            label = _ETF_LABELS.get(tk, tk)
            direction = "up" if chg >= 0 else "down"
            color = "#16a34a" if chg >= 0 else "#dc2626"
            bench_rows += (
                f'<tr>'
                f'<td style="padding:8px 10px;">{label}</td>'
                f'<td style="padding:8px 10px;color:{color};font-weight:600;">'
                f'{direction} {abs(chg):.2f}%</td>'
                f'</tr>'
            )

    # Gainers / losers columns
    def _mover_rows(items):
        rows = ""
        for tk, chg in items:
            color = "#16a34a" if chg >= 0 else "#dc2626"
            rows += (
                f'<tr>'
                f'<td style="padding:5px 8px;font-weight:700;">{tk}</td>'
                f'<td style="padding:5px 8px;color:{color};font-weight:600;">{chg:+.2f}%</td>'
                f'</tr>'
            )
        return rows

    body = f"""
      <p style="color:#374151;font-size:14px;">Here's how the main market groups moved today ({last_date}):</p>
      <table style="width:100%;border-collapse:collapse;margin-bottom:16px;">
        <tr style="background:#e2e8f0;">
          <th style="padding:8px 10px;text-align:left;font-size:13px;">What it tracks</th>
          <th style="padding:8px 10px;text-align:left;font-size:13px;">Today's change</th>
        </tr>
        {bench_rows}
      </table>
      <div style="display:flex;gap:24px;">
        <div style="flex:1;">
          <p style="margin:0 0 6px 0;font-weight:600;color:#16a34a;">Biggest winners today</p>
          <table style="width:100%;border-collapse:collapse;">{_mover_rows(gainers)}</table>
        </div>
        <div style="flex:1;">
          <p style="margin:0 0 6px 0;font-weight:600;color:#dc2626;">Biggest drops today</p>
          <table style="width:100%;border-collapse:collapse;">{_mover_rows(losers)}</table>
        </div>
      </div>"""
    return _section("📊 How the Market Did Today", body)


# ── HTML builder ───────────────────────────────────────────────────────────────
_VERDICT_COLOR = {"STRONG BUY": "#16a34a", "BUY": "#22c55e", "WATCH": "#d97706", "NEUTRAL": "#6b7280", "AVOID": "#dc2626"}

_JARGON = {
    "HIGH conviction insider open-market buy detected": "A top executive bought a large amount of their own company's stock with personal money",
    "MEDIUM conviction insider buy detected": "A company insider recently bought their own stock",
    "Bullish news sentiment": "News coverage looks positive",
    "Bearish news sentiment": "News coverage looks negative",
    "Price momentum:": "Recent price move:",
    "ETF pressure:": "Related funds are also moving:",
    "conviction": "confidence",
    "momentum": "price trend",
    "bullish": "positive",
    "bearish": "negative",
    "volatility": "price swings",
    "portfolio": "investments",
    "asset allocation": "how money is split",
    "macroeconomic": "big-picture economic",
}


def _dejargon(text: str) -> str:
    for term, replacement in _JARGON.items():
        text = text.replace(term, replacement)
    return text


def _section(title: str, body: str) -> str:
    return f"""
    <div style="margin:24px 0;padding:20px 24px;border-radius:12px;background:#f8fafc;border-left:4px solid #3b82f6;">
      <h2 style="margin:0 0 12px 0;font-size:18px;color:#1e293b;">{title}</h2>
      {body}
    </div>"""


def _pill(text: str, color: str = "#3b82f6") -> str:
    return f'<span style="background:{color};color:white;padding:2px 10px;border-radius:99px;font-size:12px;font-weight:600;">{text}</span>'


def build_email_html() -> str:
    now = datetime.utcnow()
    date_str = now.strftime("%A, %B %-d, %Y")

    convergence = _load_convergence()
    insider = _load_insider()
    backtest = _load_backtest()
    hedge_notable = _load_hedge_notable()
    news_signals = _load_news_signals()
    etf_data = _load_etf_pulse()

    strong_buys = [s for s in convergence if s.get("verdict") in ("STRONG BUY", "BUY")][:5]
    high_insider = [s for s in insider if s.get("signal_strength") == "HIGH"]

    # ── Section 1: What Happened Today ────────────────────────────────────
    total_buy = len([s for s in convergence if s.get("verdict") in ("STRONG BUY", "BUY")])
    total_watch = len([s for s in convergence if s.get("verdict") == "WATCH"])
    pulse_body = f"""
      <p style="color:#374151;font-size:15px;">
        <strong>{date_str}</strong><br><br>
        We looked at today's news, price moves, and what company insiders are doing. Here's the quick version:<br><br>
        📈 <strong>{total_buy}</strong> stock{'s' if total_buy != 1 else ''} look interesting to buy right now &nbsp;|&nbsp;
        👀 <strong>{total_watch}</strong> stock{'s' if total_watch != 1 else ''} we're keeping an eye on &nbsp;|&nbsp;
        🏢 <strong>{len(high_insider)}</strong> company executive{'s' if len(high_insider) != 1 else ''} bought their own company's stock recently
      </p>"""
    pulse_section = _section("📊 What Happened Today", pulse_body)

    # ── Section 2: Stocks Worth Watching Tomorrow ────────────────────────────────
    if strong_buys:
        rows = ""
        for s in strong_buys:
            color = _VERDICT_COLOR.get(s["verdict"], "#6b7280")
            pill = _pill(s["verdict"], color)
            reasons_html = "".join(f'<li style="color:#4b5563;font-size:13px;">{_dejargon(r)}</li>' for r in s.get("reasons", [])[:2])
            rows += f"""
            <tr>
              <td style="padding:10px;font-weight:700;font-size:15px;">{s['ticker']}</td>
              <td style="padding:10px;">{pill}</td>
              <td style="padding:10px;color:#374151;">{s['convergence_score']:.1f}/10</td>
              <td style="padding:10px;"><ul style="margin:0;padding-left:16px;">{reasons_html}</ul></td>
            </tr>"""
        picks_body = f"""
          <p style="color:#374151;font-size:14px;margin:0 0 12px 0;">
            These stocks have multiple good signs at once — news looks positive, insiders may be buying, and the price is moving in the right direction. The score shows how many good signs lined up (out of 10).
          </p>
          <table style="width:100%;border-collapse:collapse;">
            <tr style="background:#e2e8f0;">
              <th style="padding:8px;text-align:left;">Stock</th>
              <th style="padding:8px;text-align:left;">Our Take</th>
              <th style="padding:8px;text-align:left;">How confident (out of 10)</th>
              <th style="padding:8px;text-align:left;">Why we flagged it</th>
            </tr>{rows}
          </table>"""
    else:
        picks_body = "<p style='color:#6b7280;'>Nothing stands out today — check back tomorrow.</p>"
    picks_section = _section("🔎 Stocks Worth Watching Tomorrow", picks_body)

    # ── Section 3: Insider Buying ─────────────────────────────────────────────
    if high_insider:
        recent = [s for s in high_insider] or high_insider
        rows = ""
        for s in recent[:5]:
            rows += f"""
            <tr>
              <td style="padding:8px;font-weight:700;">{s['ticker']}</td>
              <td style="padding:8px;">{s['insider_name']}</td>
              <td style="padding:8px;color:#6b7280;">{s['insider_role']}</td>
              <td style="padding:8px;color:#16a34a;font-weight:600;">${s['total_value']:,.0f}</td>
              <td style="padding:8px;color:#6b7280;">{s['transaction_date']}</td>
            </tr>"""
        insider_body = f"""
          <p style="color:#374151;font-size:14px;margin:0 0 12px 0;">
            When a CEO or CFO buys their own company's stock with personal money, that's usually a good sign — they know the company better than anyone and they're betting on it with their own cash.
          </p>
          <table style="width:100%;border-collapse:collapse;">
            <tr style="background:#e2e8f0;">
              <th style="padding:8px;text-align:left;">Company</th><th style="padding:8px;text-align:left;">Who bought</th>
              <th style="padding:8px;text-align:left;">Their role</th><th style="padding:8px;text-align:left;">Amount they spent</th>
              <th style="padding:8px;text-align:left;">When</th>
            </tr>{rows}
          </table>"""
    else:
        insider_body = "<p style='color:#6b7280;'>No executives bought their own company's stock recently.</p>"
    insider_section = _section("👀 Company Insiders Are Buying Their Own Stock", insider_body)

    # ── Section 4: News That Could Move Stocks ────────────────────────────────
    if news_signals:
        rows = ""
        for s in news_signals[:5]:
            going_up = s["direction"] == "↑"
            going_down = s["direction"] == "↓"
            dir_color = "#16a34a" if going_up else ("#dc2626" if going_down else "#6b7280")
            dir_label = "might go up" if going_up else ("might drop" if going_down else "could be affected")
            headline_trunc = s["headline"][:100] + "…" if len(s["headline"]) > 100 else s["headline"]
            link = s.get("url", "#")
            rows += f"""
            <tr>
              <td style="padding:8px;font-weight:700;">{s['ticker']}</td>
              <td style="padding:8px;color:{dir_color};font-weight:600;">{dir_label}</td>
              <td style="padding:8px;color:#6b7280;">{s['keyword']}</td>
              <td style="padding:8px;"><a href="{link}" style="color:#3b82f6;text-decoration:none;">{headline_trunc}</a></td>
              <td style="padding:8px;color:#9ca3af;font-size:12px;">{s['source']}</td>
            </tr>"""
        news_body = f"""
          <table style="width:100%;border-collapse:collapse;">
            <tr style="background:#e2e8f0;">
              <th style="padding:8px;text-align:left;">Stock</th><th style="padding:8px;text-align:left;">What might happen</th>
              <th style="padding:8px;text-align:left;">Topic</th><th style="padding:8px;text-align:left;">Article</th>
              <th style="padding:8px;text-align:left;">Source</th>
            </tr>{rows}
          </table>"""
    else:
        news_body = "<p style='color:#6b7280;'>No news stories matched our watchlist today.</p>"
    news_section = _section("📰 News That Could Move Stocks", news_body)

    # ── Section 5: What Big Investors Are Doing ───────────────────────────────
    if hedge_notable:
        hf_body = f"""
          <p style="color:#374151;font-size:14px;margin:0 0 10px 0;">
            These are large firms that manage billions of dollars. When they put a lot of money into a single stock, it's worth paying attention.
          </p>
          <p style="color:#374151;font-size:15px;">
            <strong>{hedge_notable['fund']}</strong>'s biggest bet right now is
            <strong>{hedge_notable['ticker']}</strong> ({hedge_notable['issuer']}) —
            it makes up <strong>{hedge_notable['pct']:.2f}%</strong> of everything they own.
            They hold roughly <strong>${hedge_notable['value']:,.0f}</strong> worth of it.<br>
            <span style="color:#6b7280;font-size:13px;">From their most recent public filing, as of {hedge_notable['filing_date']}.</span>
          </p>"""
    else:
        hf_body = "<p style='color:#6b7280;'>No fund data yet — check back after the next data refresh.</p>"
    hedge_section = _section("🐳 What Big Investors Are Doing", hf_body)

    # ── ETF Pulse ─────────────────────────────────────────────────────────────
    etf_pulse_section = _build_etf_pulse_section(etf_data)

    # ── Section 6: Signals That Have Actually Worked ──────────────────────────
    if backtest[:3]:
        rows = ""
        for r in backtest[:3]:
            avg5 = r.get("avg_return_5d")
            avg5_str = f"{avg5*100:+.2f}%" if avg5 is not None else "N/A"
            rows += f"""
            <tr>
              <td style="padding:8px;">{r['keyword']}</td>
              <td style="padding:8px;font-weight:700;">{r['ticker']}</td>
              <td style="padding:8px;color:#16a34a;font-weight:600;">{r['hit_rate']*100:.0f}%</td>
              <td style="padding:8px;">{avg5_str}</td>
              <td style="padding:8px;color:#6b7280;">{r['sample_size']} times tracked</td>
            </tr>"""
        bt_body = f"""
          <p style="color:#374151;font-size:14px;margin:0 0 12px 0;">
            These are patterns we've tracked over time that have been right more often than not. Not a guarantee — just what the data actually shows.
          </p>
          <table style="width:100%;border-collapse:collapse;">
            <tr style="background:#e2e8f0;">
              <th style="padding:8px;text-align:left;">Pattern</th><th style="padding:8px;text-align:left;">Stock</th>
              <th style="padding:8px;text-align:left;">How often it worked</th><th style="padding:8px;text-align:left;">Avg gain in 5 days</th>
              <th style="padding:8px;text-align:left;">Times tracked</th>
            </tr>{rows}
          </table>"""
    else:
        bt_body = "<p style='color:#6b7280;'>Still collecting data — these patterns get more reliable over time as we track more news.</p>"
    bt_section = _section("✅ Signals That Have Actually Worked", bt_body)

    # ── Section 7: Just So You Know ───────────────────────────────────────────
    disc_section = _section(
        "⚠️ Just so you know",
        "<p style='color:#6b7280;font-size:13px;'>This is an automated summary built for personal learning. "
        "<strong>Nothing here is financial advice.</strong> "
        "Always do your own research before buying or selling anything.</p>"
    )

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Your Daily Market Update — {date_str}</title>
</head>
<body style="margin:0;padding:0;background:#f1f5f9;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
  <div style="max-width:680px;margin:32px auto;background:white;border-radius:16px;overflow:hidden;box-shadow:0 4px 24px rgba(0,0,0,0.08);">
    <div style="background:linear-gradient(135deg,#1e3a5f,#2563eb);padding:28px 32px;">
      <h1 style="margin:0;color:white;font-size:22px;">📊 Your Daily Market Update</h1>
      <p style="margin:6px 0 0 0;color:#93c5fd;font-size:14px;">{date_str}</p>
    </div>
    <div style="padding:8px 24px 32px 24px;">
      <p style="color:#374151;font-size:15px;margin:16px 0 0 0;">Here's today's market recap — what happened today and what to watch tomorrow.</p>
      {pulse_section}
      {picks_section}
      {insider_section}
      {news_section}
      {hedge_section}
      {etf_pulse_section}
      {bt_section}
      {disc_section}
    </div>
    <div style="background:#f8fafc;padding:16px 32px;text-align:center;color:#9ca3af;font-size:12px;">
      SmartPortfolioBot · For learning purposes only · Not financial advice ·
      <a href="https://trendiq.streamlit.app" style="color:#3b82f6;">Open App</a>
    </div>
  </div>
</body>
</html>"""
    return html


# ── Send ───────────────────────────────────────────────────────────────────────
def _build_subject() -> str:
    now = datetime.utcnow()
    convergence = _load_convergence()
    insider = _load_insider()
    strong = len([s for s in convergence if s.get("verdict") in ("STRONG BUY", "BUY")])
    high_ins = len([s for s in insider if s.get("signal_strength") == "HIGH"])
    parts = []
    if strong:
        parts.append(f"{strong} stock{'s' if strong > 1 else ''} worth watching tomorrow")
    if high_ins:
        parts.append(f"{high_ins} exec{'s' if high_ins > 1 else ''} bought their own stock")
    suffix = " · ".join(parts) if parts else "your daily update"
    return f"📊 Market Recap — {now.strftime('%a %b %-d')} | Tomorrow's watchlist inside"


def send_digest(recipients: List[str], html: str, subject: str) -> bool:
    sender = os.environ.get("DIGEST_SENDER_EMAIL", "")
    password = os.environ.get("DIGEST_SENDER_PASS", "")

    if not sender or not password:
        log.error("DIGEST_SENDER_EMAIL or DIGEST_SENDER_PASS not set in environment.")
        return False
    if not recipients:
        log.warning("No recipients found.")
        return False

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = ", ".join(recipients)
    msg.attach(MIMEText(html, "html"))

    try:
        ctx = ssl.create_default_context()
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ctx) as server:
            server.login(sender, password)
            server.sendmail(sender, recipients, msg.as_string())
        log.info(f"Digest sent to {len(recipients)} recipient(s).")
        return True
    except Exception as e:
        log.error(f"Send failed: {e}")
        return False


def _save_preview(html: str) -> Path:
    DIGESTS_DIR.mkdir(parents=True, exist_ok=True)
    fname = DIGESTS_DIR / f"digest_{datetime.utcnow().strftime('%Y%m%d')}.html"
    fname.write_text(html, encoding="utf-8")
    return fname


# ── Entry point ────────────────────────────────────────────────────────────────
def run_digest() -> None:
    """Main entry point — build and send to all recipients."""
    recipients = read_recipients()
    html = build_email_html()
    subject = _build_subject()
    _save_preview(html)
    send_digest(recipients, html, subject)


def main() -> None:
    parser = argparse.ArgumentParser(description="SmartPortfolioBot Daily Digest Mailer")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--preview", action="store_true", help="Build HTML and save locally, do NOT send")
    group.add_argument("--send", action="store_true", help="Build and send to all recipients")
    group.add_argument("--test", action="store_true", help="Send to first recipient only")
    args = parser.parse_args()

    html = build_email_html()
    subject = _build_subject()
    path = _save_preview(html)
    log.info(f"HTML saved to {path}")

    if args.preview:
        print(f"\n✅ Preview saved: {path}")
        print(f"   Subject: {subject}")
        recipients = read_recipients()
        print(f"   Recipients ({len(recipients)}): {recipients}")
        print("   Use --send to actually deliver.")
        return

    recipients = read_recipients()
    if args.test:
        recipients = recipients[:1]
        if not recipients:
            log.warning("No recipients in digest_recipients.txt — add at least one.")
            return

    ok = send_digest(recipients, html, subject)
    print(f"\n{'✅ Sent' if ok else '❌ Send failed'} to {len(recipients)} recipient(s).")


if __name__ == "__main__":
    main()
