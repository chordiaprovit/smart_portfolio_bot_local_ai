"""
digest_mailer.py — Daily Portfolio Intelligence Email Digest

Sends at 6:30 AM ET (11:30 UTC) on weekdays via GitHub Actions.
Reads pre-cached data files — does NOT re-fetch live data.

Email sections:
  1. 📊 Market Pulse
  2. 🚨 Top Convergence Picks
  3. 🕵️ Insider Activity
  4. 🗞️ Political/News Signals
  5. 🐳 Hedge Fund Watch
  6. 📈 Proven Signals
  7. ⚠️ Disclaimer

CLI:
  python digest_mailer.py --preview   (saves HTML locally, does NOT send)
  python digest_mailer.py --send      (builds and sends to all recipients)
  python digest_mailer.py --test      (sends to first recipient only)
"""

from __future__ import annotations

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
def _build_etf_pulse_section(etf_data: dict) -> str:
    if not etf_data:
        return _section(
            "📊 ETF Pulse",
            "<p style='color:#6b7280;'>ETF data unavailable. Run <code>python3 etf_updates.py</code> to generate it.</p>",
        )

    changes = etf_data.get("changes", {})
    last_date = etf_data.get("last_date", "")
    sorted_changes = sorted(changes.items(), key=lambda x: x[1], reverse=True)
    gainers = sorted_changes[:3]
    losers = list(reversed(sorted_changes[-3:]))

    def _chg_cell(chg: float) -> str:
        color = "#16a34a" if chg >= 0 else "#dc2626"
        return f'<td style="padding:6px 10px;color:{color};font-weight:600;">{chg:+.2f}%</td>'

    # Benchmark table
    bench_rows = ""
    for tk in _BENCHMARK_ETFS:
        if tk in changes:
            bench_rows += f'<tr><td style="padding:6px 10px;font-weight:700;">{tk}</td>{_chg_cell(changes[tk])}</tr>'

    # Gainers / losers columns
    def _mover_rows(items):
        rows = ""
        for tk, chg in items:
            rows += f'<tr><td style="padding:5px 8px;font-weight:700;">{tk}</td>{_chg_cell(chg)}</tr>'
        return rows

    body = f"""
      <p style="color:#6b7280;font-size:13px;">As of {last_date}</p>
      <table style="width:100%;border-collapse:collapse;margin-bottom:14px;">
        <tr style="background:#e2e8f0;">
          <th style="padding:6px 10px;text-align:left;font-size:13px;">Benchmark</th>
          <th style="padding:6px 10px;text-align:left;font-size:13px;">1D %</th>
        </tr>
        {bench_rows}
      </table>
      <div style="display:flex;gap:24px;">
        <div style="flex:1;">
          <p style="margin:0 0 6px 0;font-weight:600;color:#16a34a;">Top 3 Gainers</p>
          <table style="width:100%;border-collapse:collapse;">{_mover_rows(gainers)}</table>
        </div>
        <div style="flex:1;">
          <p style="margin:0 0 6px 0;font-weight:600;color:#dc2626;">Top 3 Losers</p>
          <table style="width:100%;border-collapse:collapse;">{_mover_rows(losers)}</table>
        </div>
      </div>"""
    return _section("📊 ETF Pulse", body)


# ── HTML builder ───────────────────────────────────────────────────────────────
_VERDICT_COLOR = {"STRONG BUY": "#16a34a", "BUY": "#22c55e", "WATCH": "#d97706", "NEUTRAL": "#6b7280", "AVOID": "#dc2626"}


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

    # ── Section 1: Market Pulse ────────────────────────────────────────────────
    total_buy = len([s for s in convergence if s.get("verdict") in ("STRONG BUY", "BUY")])
    total_watch = len([s for s in convergence if s.get("verdict") == "WATCH"])
    pulse_body = f"""
      <p style="color:#374151;font-size:15px;">
        <strong>{date_str}</strong><br><br>
        📡 <strong>{total_buy}</strong> buy signal(s) &nbsp;|&nbsp;
        🟡 <strong>{total_watch}</strong> watch signal(s) &nbsp;|&nbsp;
        🕵️ <strong>{len(high_insider)}</strong> high-conviction insider buy(s)
      </p>"""
    pulse_section = _section("📊 Market Pulse", pulse_body)

    # ── Section 2: Top Convergence Picks ──────────────────────────────────────
    if strong_buys:
        rows = ""
        for s in strong_buys:
            color = _VERDICT_COLOR.get(s["verdict"], "#6b7280")
            pill = _pill(s["verdict"], color)
            reasons_html = "".join(f'<li style="color:#4b5563;font-size:13px;">{r}</li>' for r in s.get("reasons", [])[:2])
            rows += f"""
            <tr>
              <td style="padding:10px;font-weight:700;font-size:15px;">{s['ticker']}</td>
              <td style="padding:10px;">{pill}</td>
              <td style="padding:10px;color:#374151;">{s['convergence_score']:.1f}/10</td>
              <td style="padding:10px;"><ul style="margin:0;padding-left:16px;">{reasons_html}</ul></td>
            </tr>"""
        picks_body = f"""
          <table style="width:100%;border-collapse:collapse;">
            <tr style="background:#e2e8f0;">
              <th style="padding:8px;text-align:left;">Ticker</th>
              <th style="padding:8px;text-align:left;">Verdict</th>
              <th style="padding:8px;text-align:left;">Score</th>
              <th style="padding:8px;text-align:left;">Reasons</th>
            </tr>{rows}
          </table>"""
    else:
        picks_body = "<p style='color:#6b7280;'>No strong buy signals right now.</p>"
    picks_section = _section("🚨 Top Convergence Picks", picks_body)

    # ── Section 3: Insider Activity ───────────────────────────────────────────
    if high_insider:
        cutoff = (now - timedelta(hours=24)).isoformat(timespec="seconds")
        recent = [s for s in high_insider] or high_insider  # show all if none in 24h
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
          <table style="width:100%;border-collapse:collapse;">
            <tr style="background:#e2e8f0;">
              <th style="padding:8px;text-align:left;">Ticker</th><th style="padding:8px;text-align:left;">Insider</th>
              <th style="padding:8px;text-align:left;">Role</th><th style="padding:8px;text-align:left;">Amount</th>
              <th style="padding:8px;text-align:left;">Date</th>
            </tr>{rows}
          </table>"""
    else:
        insider_body = "<p style='color:#6b7280;'>No high-conviction insider buys in the current lookback window.</p>"
    insider_section = _section("🕵️ Insider Activity", insider_body)

    # ── Section 4: News Signals ────────────────────────────────────────────────
    if news_signals:
        rows = ""
        for s in news_signals[:5]:
            dir_color = "#16a34a" if s["direction"] == "↑" else ("#dc2626" if s["direction"] == "↓" else "#6b7280")
            headline_trunc = s["headline"][:100] + "…" if len(s["headline"]) > 100 else s["headline"]
            link = s.get("url", "#")
            rows += f"""
            <tr>
              <td style="padding:8px;font-weight:700;">{s['ticker']}</td>
              <td style="padding:8px;color:{dir_color};font-size:18px;">{s['direction']}</td>
              <td style="padding:8px;color:#6b7280;">{s['keyword']}</td>
              <td style="padding:8px;"><a href="{link}" style="color:#3b82f6;text-decoration:none;">{headline_trunc}</a></td>
              <td style="padding:8px;color:#9ca3af;font-size:12px;">{s['source']}</td>
            </tr>"""
        news_body = f"""
          <table style="width:100%;border-collapse:collapse;">
            <tr style="background:#e2e8f0;">
              <th style="padding:8px;text-align:left;">Ticker</th><th style="padding:8px;">Dir</th>
              <th style="padding:8px;text-align:left;">Keyword</th><th style="padding:8px;text-align:left;">Headline</th>
              <th style="padding:8px;text-align:left;">Source</th>
            </tr>{rows}
          </table>"""
    else:
        news_body = "<p style='color:#6b7280;'>No keyword-matched news signals today.</p>"
    news_section = _section("🗞️ Political/News Signals", news_body)

    # ── Section 5: Hedge Fund Watch ───────────────────────────────────────────
    if hedge_notable:
        hf_body = f"""
          <p style="color:#374151;font-size:15px;">
            <strong>{hedge_notable['fund']}</strong> largest holding:
            <strong>{hedge_notable['ticker']}</strong> ({hedge_notable['issuer']}) —
            <strong>{hedge_notable['pct']:.2f}%</strong> of portfolio
            (market value ${hedge_notable['value']:,.0f}).<br>
            <span style="color:#6b7280;font-size:13px;">As of {hedge_notable['filing_date']} 13F filing.</span>
          </p>"""
    else:
        hf_body = "<p style='color:#6b7280;'>Run hedge_fund_mirror.py to populate fund data.</p>"
    hedge_section = _section("🐳 Hedge Fund Watch", hf_body)

    # ── ETF Pulse ─────────────────────────────────────────────────────────────
    etf_pulse_section = _build_etf_pulse_section(etf_data)

    # ── Section 6: Proven Signals ─────────────────────────────────────────────
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
              <td style="padding:8px;color:#6b7280;">{r['sample_size']} events</td>
            </tr>"""
        bt_body = f"""
          <table style="width:100%;border-collapse:collapse;">
            <tr style="background:#e2e8f0;">
              <th style="padding:8px;text-align:left;">Keyword</th><th style="padding:8px;text-align:left;">Ticker</th>
              <th style="padding:8px;text-align:left;">Hit Rate</th><th style="padding:8px;text-align:left;">Avg 5d Return</th>
              <th style="padding:8px;text-align:left;">Samples</th>
            </tr>{rows}
          </table>"""
    else:
        bt_body = "<p style='color:#6b7280;'>Backtest signals accumulate daily — check back as news cache grows.</p>"
    bt_section = _section("📈 Proven Signals (Backtested)", bt_body)

    # ── Section 7: Disclaimer ─────────────────────────────────────────────────
    disc_section = _section(
        "⚠️ Disclaimer",
        "<p style='color:#6b7280;font-size:13px;'>This digest is for personal research and educational purposes only. "
        "It is <strong>not financial advice</strong>. Past signal performance does not guarantee future results. "
        "Always do your own research before making investment decisions.</p>"
    )

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Portfolio Digest — {date_str}</title>
</head>
<body style="margin:0;padding:0;background:#f1f5f9;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
  <div style="max-width:680px;margin:32px auto;background:white;border-radius:16px;overflow:hidden;box-shadow:0 4px 24px rgba(0,0,0,0.08);">
    <div style="background:linear-gradient(135deg,#1e3a5f,#2563eb);padding:28px 32px;">
      <h1 style="margin:0;color:white;font-size:22px;">📊 SmartPortfolioBot Digest</h1>
      <p style="margin:6px 0 0 0;color:#93c5fd;font-size:14px;">{date_str}</p>
    </div>
    <div style="padding:8px 24px 32px 24px;">
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
      SmartPortfolioBot · Educational use only ·
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
        parts.append(f"{strong} Strong Buy{'s' if strong > 1 else ''}")
    if high_ins:
        parts.append(f"{high_ins} Insider Alert{'s' if high_ins > 1 else ''}")
    suffix = " · ".join(parts) if parts else "Daily Update"
    return f"📊 Portfolio Digest — {now.strftime('%a %b %-d')} | {suffix}"


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
