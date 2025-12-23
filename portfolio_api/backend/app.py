from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Literal, Optional, Tuple
from dataclasses import dataclass
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

# ---------- Config ----------
PACK_PATH = Path(__file__).parent / "analytics_pack.json"

Focus = Literal["Growth", "Dividend", "Stability", "Active returns"]

from typing import Literal

AgeRange = Literal["20-35", "36-50", "51-65", "65+"]
app = FastAPI(title="Portfolio Health API (v1)", version="0.1.0")


class LogBodyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path == "/portfolio/health":
            body = await request.body()
            print("RAW /portfolio/health body:", body.decode("utf-8", "ignore"))
        return await call_next(request)

app.add_middleware(LogBodyMiddleware)

class StarterPortfolioRequest(BaseModel):
    investmentStyle: Literal["Long-term", "Conservative", "Active"]
    assetInterest: Literal["Stocks", "ETFs", "Bonds", "All of the above", "I don’t know"]
    focus: Focus  # uses your existing Focus type: "Growth" | "Dividend" | "Stability" | "Active returns"
    involvement: Literal["Set & forget", "Monthly", "Tweak"]
    ageRange: AgeRange | None = None

class StarterAllocationOut(BaseModel):
    ticker: str
    type: str  # "etf" | "bond_etf" | "stock"
    weight: float
    reason: str

class StarterPortfolioResponse(BaseModel):
    asOf: Optional[str]
    name: str
    allocations: List[StarterAllocationOut]
    notes: List[str]


# ---------- Models ----------
class HoldingIn(BaseModel):
    ticker: str
    weight: float = Field(..., ge=0.0)


class PortfolioRequest(BaseModel):
    holdings: List[HoldingIn]
    focus: Focus


class SubScores(BaseModel):
    allocationEquality: int
    concentration: int
    sectorBalance: int
    goalAlignment: int


class HealthResponse(BaseModel):
    asOf: Optional[str]
    score: int
    subScores: SubScores
    topRisks: List[str]
    explainability: Dict[str, str]


class CorrPair(BaseModel):
    a: str
    b: str
    corr: float

class InsightsResponse(BaseModel):
    asOf: Optional[str] = None
    correlationWarnings: List[str] = []
    mostCorrelatedPairs: List[CorrPair] = []

@dataclass
class Alloc:
    ticker: str
    type: str         # "etf" | "bond_etf" | "stock"
    weight: float
    reason: str

def _normalize_allocs(allocs: List[Alloc]) -> List[Alloc]:
    s = sum(a.weight for a in allocs)
    if s <= 0:
        return allocs
    for a in allocs:
        a.weight = a.weight / s
    return allocs



def _split_overweight_allocations(
    allocs: List[Alloc],
    cap: float,
    replacement_pools: Dict[str, List[str]],
    tickers_available: set,
) -> List[Alloc]:
    """
    Ensure no holding exceeds `cap` by splitting overweight allocations into similar tickers.

    tickers_available: set of tickers present in your analytics_pack (TICKERS).
    """

    allocs = _normalize_allocs(allocs)

    # Helper: get substitutes for a ticker, filtered to those that exist in data pack
    def subs_for(t: str) -> List[str]:
        subs = replacement_pools.get(t, [])
        return [x for x in subs if x in tickers_available]

    # Build an index for quick lookup to avoid duplicate tickers in output
    def merge(out: List[Alloc], new_alloc: Alloc) -> None:
        for a in out:
            if a.ticker == new_alloc.ticker and a.type == new_alloc.type:
                a.weight += new_alloc.weight
                return
        out.append(new_alloc)

    out: List[Alloc] = []

    for a in allocs:
        if a.weight <= cap:
            merge(out, a)
            continue

        # Need to split a.weight into N chunks <= cap
        n = int(a.weight / cap) + (1 if (a.weight % cap) > 1e-12 else 0)
        n = max(2, n)  # at least 2 splits if overweight

        base = a.ticker
        subs = subs_for(base)

        # Choose up to n-1 substitutes + include base as first
        chosen = [base] + subs[: max(0, n - 1)]

        # If not enough substitutes, we still split among chosen (fewer parts),
        # ensuring each chunk <= cap by increasing chosen length if possible.
        # If chosen ends up short, chunk sizes might still exceed cap — so we clamp by increasing parts with same tickers.
        parts = len(chosen)
        chunk = a.weight / parts

        # If chunk still > cap, we need more parts; reuse substitutes cyclically (still fine for v1 starter).
        if chunk > cap:
            # compute required parts
            parts = int(a.weight / cap) + 1
            # expand chosen cyclically
            expanded = []
            pool = chosen[:] if chosen else [base]
            for i in range(parts):
                expanded.append(pool[i % len(pool)])
            chosen = expanded
            parts = len(chosen)
            chunk = a.weight / parts

        # Emit split allocations
        for t in chosen:
            merge(
                out,
                Alloc(
                    ticker=t,
                    type=a.type,
                    weight=chunk,
                    reason=f"{a.reason} (split for balance)",
                ),
            )

    # Final normalize + tidy rounding
    out = _normalize_allocs(out)
    for a in out:
        a.weight = float(round(a.weight, 4))

    # Normalize again after rounding drift
    out = _normalize_allocs(out)
    for a in out:
        a.weight = float(round(a.weight, 4))

    return out


# ---------- App ----------
PACK: Dict = {}
TICKERS: Dict[str, Dict] = {}          # "AAPL" -> metrics/metadata
CORR_TOP: Dict[str, List[Dict]] = {}   # "AAPL" -> [{"t":"MSFT","c":0.88}, ...]
AS_OF: Optional[str] = None


@app.on_event("startup")
def load_pack() -> None:
    global PACK, TICKERS, CORR_TOP, AS_OF
    if not PACK_PATH.exists():
        raise RuntimeError(f"analytics_pack.json not found at: {PACK_PATH}")

    PACK = json.loads(PACK_PATH.read_text(encoding="utf-8"))
    TICKERS = PACK.get("tickers", {}) or {}
    CORR_TOP = PACK.get("correlationTop", {}) or {}
    AS_OF = PACK.get("asOf")


@app.get("/health")
def health():
    return {"ok": True, "asOf": AS_OF, "tickers": len(TICKERS)}


def _normalize_weights(holdings: List[HoldingIn]) -> List[Tuple[str, float]]:
    cleaned = [(h.ticker.strip().upper(), float(h.weight)) for h in holdings if h.weight > 0]
    if not cleaned:
        raise HTTPException(status_code=400, detail="No holdings with weight > 0 provided.")

    weights = [w for _, w in cleaned]
    total = sum(weights)
    mx = max(weights)

    if mx > 1.0 or total > 1.5:
        cleaned = [(t, w / 100.0) for t, w in cleaned]

    total = sum(w for _, w in cleaned)
    if total <= 0:
        raise HTTPException(status_code=400, detail="Total weight must be > 0.")

    return [(t, w / total) for t, w in cleaned]


def _gini(weights: List[float]) -> float:
    # Standard Gini for non-negative values.
    w = [max(0.0, float(x)) for x in weights]
    if not w or sum(w) == 0:
        return 1.0
    w_sorted = sorted(w)
    n = len(w_sorted)
    cum = 0.0
    for i, x in enumerate(w_sorted, start=1):
        cum += i * x
    return (2 * cum) / (n * sum(w_sorted)) - (n + 1) / n


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def _linear_score(value: float, good_at_or_below: float, bad_at_or_above: float) -> int:
    """
    Maps value -> [25..0] linearly between good and bad thresholds.
    If value <= good -> 25
    If value >= bad -> 0
    else linear.
    """
    if value <= good_at_or_below:
        return 25
    if value >= bad_at_or_above:
        return 0
    # linearly decrease
    frac = (value - good_at_or_below) / (bad_at_or_above - good_at_or_below)
    return int(round(25 * (1.0 - frac)))


def _goal_alignment_score(weights_by_ticker: List[Tuple[str, float]], focus: Focus) -> Tuple[int, str]:
    """
    Explainable proxy: use price-derived CAGR + volatility.
    - Growth: want higher weighted CAGR
    - Stability: want lower weighted volatility
    - Dividend: we DON'T have yield; treat as "moderate volatility + moderate growth"
    - Active returns: accept higher vol & trend (proxy)
    Returns (score_0_25, explanation)
    """
    # Pull metrics; if missing, treat as neutral-ish.
    def get(t: str, key: str, default: float) -> float:
        v = TICKERS.get(t, {}).get(key, default)
        try:
            return float(v)
        except Exception:
            return default

    w_cagr = 0.0
    w_vol = 0.0
    w_trend = 0.0
    for t, w in weights_by_ticker:
        w_cagr += w * get(t, "cagr", 0.0)
        w_vol += w * get(t, "vol", 0.25)
        w_trend += w * get(t, "trend", 0.0)

    # These ranges are intentionally coarse for v1 explainability.
    if focus == "Growth":
        # 0% -> 0, 6% -> ~15, 12% -> ~25
        score = int(round(25 * _clamp01((w_cagr - 0.00) / 0.12)))
        expl = f"Weighted 1Y growth proxy (CAGR) ≈ {w_cagr*100:.1f}%."
        return score, expl

    if focus == "Stability":
        # vol <= 12% => 25, vol >= 35% => 0
        score = _linear_score(w_vol, good_at_or_below=0.12, bad_at_or_above=0.35)
        expl = f"Weighted volatility proxy ≈ {w_vol*100:.1f}% (lower is more stable)."
        return score, expl

    if focus == "Dividend":
        # With no dividend data, we approximate “dividend-friendly” as:
        # not-too-high vol AND not-negative growth.
        vol_score = _linear_score(w_vol, good_at_or_below=0.14, bad_at_or_above=0.40)
        cagr_score = int(round(25 * _clamp01((w_cagr + 0.02) / 0.10)))  # -2%..8% maps 0..25
        score = int(round(0.6 * vol_score + 0.4 * cagr_score))
        expl = (
            f"No yield data in v1; using proxies. "
            f"Vol ≈ {w_vol*100:.1f}%, growth proxy ≈ {w_cagr*100:.1f}%."
        )
        return score, expl

    # "Active returns"
    # Reward a bit of trend + allow higher vol (but not extreme).
    trend_score = int(round(25 * _clamp01((w_trend - 0.0000) / 0.0015)))
    vol_penalty = _linear_score(w_vol, good_at_or_below=0.18, bad_at_or_above=0.55)
    score = int(round(0.6 * trend_score + 0.4 * vol_penalty))
    expl = f"Using trend+vol proxies. Trend ≈ {w_trend:.5f} (log-slope/day), vol ≈ {w_vol*100:.1f}%."
    return score, expl


def _sector_balance_score(weights_by_ticker: List[Tuple[str, float]]) -> Tuple[int, str, Dict[str, float]]:
    """
    Sector Balance (v1):
      - max sector <= 20% -> 25
      - max sector >= 45% -> 0
      - linear between
    Requires ticker->sector metadata.
    If unknown sectors dominate, we still compute but explain.
    """
    sector_w: Dict[str, float] = {}
    for t, w in weights_by_ticker:
        sector = (TICKERS.get(t, {}).get("sector") or "unknown").strip()
        sector_w[sector] = sector_w.get(sector, 0.0) + w

    max_sector, max_w = max(sector_w.items(), key=lambda kv: kv[1])
    score = _linear_score(max_w, good_at_or_below=0.20, bad_at_or_above=0.45)

    expl = f"Largest sector is '{max_sector}' at {max_w*100:.1f}% (<=20% is ideal for full points)."
    return score, expl, sector_w


# ---------- Endpoints ----------
@app.get("/universe/search")
def universe_search(q: str = Query(..., min_length=1), limit: int = Query(10, ge=1, le=50)):
    q2 = q.strip().upper()
    matches = [t for t in TICKERS.keys() if q2 in t]
    matches = sorted(matches)[:limit]
    return {"query": q, "results": matches, "count": len(matches), "asOf": AS_OF}


@app.post("/portfolio/health", response_model=HealthResponse)
def portfolio_health(req: PortfolioRequest):
    print("PARSED holdings:", [(h.ticker, h.weight) for h in req.holdings])
    weights_by_ticker = _normalize_weights(req.holdings)

    # Validate tickers exist in pack (or allow unknown but warn)
    unknown = [t for t, _ in weights_by_ticker if t not in TICKERS]
    if unknown:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown tickers (not in analytics_pack): {unknown[:20]}",
        )

    weights = [w for _, w in weights_by_ticker]
    top_ticker, top_w = max(weights_by_ticker, key=lambda tw: tw[1])

    # 1) Allocation Equality
    g = _gini(weights)
    alloc_score = int(round(25 * (1.0 - max(0.0, min(1.0, g)))))

    # 2) Concentration (top holding)
    conc_score = _linear_score(top_w, good_at_or_below=0.10, bad_at_or_above=0.50)

    # 3) Sector balance
    sector_score, sector_expl, sector_w = _sector_balance_score(weights_by_ticker)

    # 4) Goal alignment (proxies)
    goal_score, goal_expl = _goal_alignment_score(weights_by_ticker, req.focus)

    total = alloc_score + conc_score + sector_score + goal_score
    total = int(max(0, min(100, total)))

    # Plain-English risks
    risks: List[str] = []

    if top_w >= 0.30:
        risks.append(f"Top holding {top_ticker} is {top_w*100:.1f}% of your portfolio (concentration risk).")
    elif top_w >= 0.20:
        risks.append(f"Top holding {top_ticker} is {top_w*100:.1f}% — consider trimming if you want more balance.")

    # Sector risk
    max_sector, max_w = max(sector_w.items(), key=lambda kv: kv[1])
    if max_w >= 0.45:
        risks.append(f"Sector overexposure: '{max_sector}' is {max_w*100:.1f}% (high).")
    elif max_w >= 0.30:
        risks.append(f"Sector tilt: '{max_sector}' is {max_w*100:.1f}% (moderate).")

    # Equality risk
    if alloc_score <= 10:
        risks.append("Your allocations are uneven across holdings (low allocation equality).")

    if not risks:
        risks.append("No major red flags detected based on v1 rules.")

    explain = {
        "allocationEquality": f"Gini(weights) ≈ {g:.2f} → {alloc_score}/25.",
        "concentration": f"Top holding {top_ticker} = {top_w*100:.1f}% → {conc_score}/25.",
        "sectorBalance": sector_expl + f" → {sector_score}/25.",
        "goalAlignment": goal_expl + f" → {goal_score}/25.",
    }

    return HealthResponse(
        asOf=AS_OF,
        score=total,
        subScores=SubScores(
            allocationEquality=alloc_score,
            concentration=conc_score,
            sectorBalance=sector_score,
            goalAlignment=goal_score,
        ),
        topRisks=risks[:5],
        explainability=explain,
    )


@app.post("/portfolio/insights", response_model=InsightsResponse)
def portfolio_insights(req: PortfolioRequest):
    weights_by_ticker = _normalize_weights(req.holdings)
    tickers = [t for t, _ in weights_by_ticker]

    unknown = [t for t in tickers if t not in TICKERS]
    if unknown:
        raise HTTPException(status_code=400, detail=f"Unknown tickers: {unknown[:20]}")

    # If correlationTop missing or wrong type, return graceful response
    if not isinstance(CORR_TOP, dict) or not CORR_TOP:
        return InsightsResponse(
            asOf=AS_OF,
            correlationWarnings=[
                "Correlation insights aren’t available (no correlationTop data in analytics pack)."
            ],
            mostCorrelatedPairs=[],
        )

    pairs: Dict[Tuple[str, str], float] = {}

    for a in tickers:
        items = CORR_TOP.get(a, [])
        if items is None:
            continue
        if not isinstance(items, list):
            # Sometimes it's a dict or something unexpected
            continue

        for item in items:
            if not isinstance(item, dict):
                continue

            b_raw = item.get("t") or item.get("ticker") or item.get("symbol")
            if not b_raw:
                continue
            b = str(b_raw).upper()

            # Correlation value may be under different keys or may be string/None
            c_raw = item.get("c")
            if c_raw is None:
                c_raw = item.get("corr")
            if c_raw is None:
                c_raw = item.get("value")

            try:
                c = float(c_raw)
            except Exception:
                continue

            if b in tickers and a != b:
                key = tuple(sorted((a, b)))
                prev = pairs.get(key)
                pairs[key] = c if prev is None else max(prev, c)

    sorted_pairs = sorted(pairs.items(), key=lambda kv: kv[1], reverse=True)
    top_pairs = [{"a": k[0], "b": k[1], "corr": float(v)} for k, v in sorted_pairs[:10]]

    warnings: List[str] = []
    for p in top_pairs[:5]:
        a, b, c = p["a"], p["b"], p["corr"]
        if c >= 0.90:
            warnings.append(
                f"{a} and {b} move very similarly (corr ≈ {c:.2f}). Diversification may be lower than it looks."
            )
        elif c >= 0.80:
            warnings.append(f"{a} and {b} are highly correlated (corr ≈ {c:.2f}).")
        elif c >= 0.70:
            warnings.append(f"{a} and {b} are moderately correlated (corr ≈ {c:.2f}).")

    if not warnings:
        warnings.append(
            "No strong correlation overlaps detected among your selected holdings (based on stored top correlations)."
        )

    return InsightsResponse(asOf=AS_OF, correlationWarnings=warnings, mostCorrelatedPairs=top_pairs)

@app.post("/starter-portfolio", response_model=StarterPortfolioResponse)
def starter_portfolio(req: StarterPortfolioRequest):
    def pick(options: List[str]) -> str:
        for t in options:
            if t in TICKERS:
                return t
        return options[0]

    # Common building blocks (prefer what exists in your analytics pack)
    us_core = pick(["VTI", "VOO", "SPY", "IVV"])
    us_growth = pick(["QQQ", "QQQM"])
    intl_core = pick(["VEA", "IEFA"])
    bonds_core = pick(["BND", "AGG", "IEF"])
    long_bonds = pick(["TLT", "EDV", "IEF"])
    short_bonds = pick(["SHY", "VGSH", "BIL"])

    age = req.ageRange or "36-50"

    # Age-based equity/bond targets (coarse, explainable)
    if age == "20-35":
        equity_target, bond_target = 0.90, 0.10
    elif age == "36-50":
        equity_target, bond_target = 0.80, 0.20
    elif age == "51-65":
        equity_target, bond_target = 0.65, 0.35
    else:  # 65+
        equity_target, bond_target = 0.55, 0.45

    # Style nudges
    if req.investmentStyle == "Conservative":
        bond_target = min(0.65, bond_target + 0.10)
        equity_target = 1.0 - bond_target
    elif req.investmentStyle == "Active":
        equity_target = min(0.95, equity_target + 0.05)
        bond_target = 1.0 - equity_target

    # Involvement controls number of holdings
    involvement = req.involvement
    want_simple = involvement == "Set & forget"
    want_mid = involvement == "Monthly"
    want_more = involvement == "Tweak"

    allocations: List[StarterAllocationOut] = []
    notes: List[str] = []

    # ---------- CASE 1: "I don't know" → simplest 3-fund (always changes clearly) ----------
    if req.assetInterest == "I don’t know":
        # 3-fund: US + Intl + Bonds
        w_us = equity_target * 0.70
        w_intl = equity_target * 0.30
        w_bonds = bond_target

        allocations = [
            StarterAllocationOut(ticker=us_core, type="etf", weight=round(w_us, 4),
                                 reason="Broad US market core (simple + diversified)."),
            StarterAllocationOut(ticker=intl_core, type="etf", weight=round(w_intl, 4),
                                 reason="International diversification (reduces single-country risk)."),
            StarterAllocationOut(ticker=bonds_core, type="bond_etf", weight=round(w_bonds, 4),
                                 reason="Bond buffer for stability (helps reduce drawdowns)."),
        ]
        notes = [
            "Kept intentionally simple: US + International + Bonds.",
            "Good default if you’re not sure where to start.",
            "This is a starting point, not trading advice. Adjust anytime.",
        ]

    # ---------- CASE 2: Bonds interest → bond-heavy ----------
    elif req.assetInterest == "Bonds":
        # Bond-heavy starter with small equity core
        # Conservative: more bonds, Active: slightly more equity
        equity = min(0.35, equity_target)  # cap equity if user picked bonds
        bonds = 1.0 - equity

        if want_simple:
            allocations = [
                StarterAllocationOut(ticker=bonds_core, type="bond_etf", weight=round(bonds, 4),
                                     reason="Core bond exposure."),
                StarterAllocationOut(ticker=us_core, type="etf", weight=round(equity, 4),
                                     reason="Small equity core for growth."),
            ]
        else:
            # split bonds across duration for explainability
            allocations = [
                StarterAllocationOut(ticker=short_bonds, type="bond_etf", weight=round(bonds * 0.40, 4),
                                     reason="Short-term bonds (typically less volatile)."),
                StarterAllocationOut(ticker=bonds_core, type="bond_etf", weight=round(bonds * 0.40, 4),
                                     reason="Intermediate bond core."),
                StarterAllocationOut(ticker=long_bonds, type="bond_etf", weight=round(bonds * 0.20, 4),
                                     reason="Longer duration bonds (more rate sensitivity)."),
                StarterAllocationOut(ticker=us_core, type="etf", weight=round(equity, 4),
                                     reason="Small equity core for growth."),
            ]

        notes = [
            "Bond-heavy starter portfolio (stability-focused).",
            "Equity allocation is intentionally small.",
            "This is a starting point, not trading advice. Adjust anytime.",
        ]

    # ---------- CASE 3: Stocks interest → stock basket + ETF core ----------
    elif req.assetInterest == "Stocks":
        # v1 explainable: keep ETF core + spread across sectors with stocks
        # If you don’t want to curate stocks yet, we still return ETF core + placeholder stocks.
        core_weight = 0.50 if want_simple else (0.40 if want_mid else 0.35)
        stock_weight = 1.0 - core_weight

        # Lightweight “sector spread” (you can swap these later for your own curated list)
        # We pick from your universe if present.
        stock_candidates = [
            pick(["AAPL"]),  # Tech
            pick(["MSFT"]),  # Tech (big cap)
            pick(["JNJ"]),   # Healthcare
            pick(["JPM"]),   # Financials
            pick(["XOM"]),   # Energy
            pick(["PG"]),    # Consumer staples
            pick(["COST", "WMT"]), # Consumer
            pick(["UNH"]),   # Healthcare
        ]

        # Choose number of stocks based on involvement
        k = 4 if want_simple else (6 if want_mid else 8)
        picks = stock_candidates[:k]
        each = stock_weight / len(picks)

        allocations = [
            StarterAllocationOut(ticker=us_core, type="etf", weight=round(core_weight, 4),
                                 reason="ETF core for broad diversification."),
        ] + [
            StarterAllocationOut(ticker=t, type="stock", weight=round(each, 4),
                                 reason="Stock pick to add sector variety (v1 simple basket).")
            for t in picks
        ]

        notes = [
            "Stock-focused starter uses an ETF core + a small diversified stock basket.",
            "Replace stock basket with your own holdings anytime.",
            "This is a starting point, not trading advice. Adjust anytime.",
        ]

    elif req.assetInterest == "All of the above":
        # ETF core + a few stocks + bonds
        # Complexity depends on involvement:
        #  - Set & forget: 1 ETF + 2 stocks + 1 bond ETF (4 holdings)
        #  - Monthly:      2 ETFs + 3 stocks + 1 bond ETF (6 holdings)
        #  - Tweak:        3 ETFs + 5 stocks + 2 bond ETFs (10 holdings)

        # Base split: equity_target vs bond_target already computed from age/style
        equity = equity_target
        bonds = bond_target

        # Within equity: split between ETF core and stocks
        if req.involvement == "Set & forget":
            etf_core_share = 0.75
            stock_share = 0.25
            stock_count = 2
            etf_count = 1
            bond_count = 1
        elif req.involvement == "Monthly":
            etf_core_share = 0.65
            stock_share = 0.35
            stock_count = 3
            etf_count = 2
            bond_count = 1
        else:  # Tweak
            etf_core_share = 0.55
            stock_share = 0.45
            stock_count = 5
            etf_count = 3
            bond_count = 2

        # Pick ETFs
        etfs = []
        # Focus affects ETF selection/tilt
        if req.focus in ["Growth", "Active returns"]:
            etfs = [us_core, us_growth, intl_core]
        elif req.focus == "Stability":
            etfs = [us_core, intl_core, bonds_core]
        else:  # Dividend (proxy)
            etfs = [us_core, intl_core, bonds_core]

        etfs = etfs[:etf_count]

        # Pick stocks (sector spread)
        stock_candidates = [
            pick(["AAPL"]),
            pick(["MSFT"]),
            pick(["JNJ"]),
            pick(["JPM"]),
            pick(["PG"]),
            pick(["XOM"]),
            pick(["COST", "WMT"]),
            pick(["UNH"]),
        ]
        stocks = stock_candidates[:stock_count]

        # Pick bonds (duration split for tweak mode)
        bond_etfs = [bonds_core]
        if bond_count == 2:
            bond_etfs = [short_bonds, long_bonds]

        # Allocate weights
        w_etfs_total = equity * etf_core_share
        w_stocks_total = equity * stock_share
        w_bonds_total = bonds

        each_etf = w_etfs_total / len(etfs) if etfs else 0.0
        each_stock = w_stocks_total / len(stocks) if stocks else 0.0
        each_bond = w_bonds_total / len(bond_etfs) if bond_etfs else 0.0

        allocations = []
        for t in etfs:
            allocations.append(
                StarterAllocationOut(
                    ticker=t, type="etf", weight=round(each_etf, 4),
                    reason="ETF core for broad diversification."
                )
            )
        for t in stocks:
            allocations.append(
                StarterAllocationOut(
                    ticker=t, type="stock", weight=round(each_stock, 4),
                    reason="Stock slice for added sector variety."
                )
            )
        for t in bond_etfs:
            allocations.append(
                StarterAllocationOut(
                    ticker=t, type="bond_etf", weight=round(each_bond, 4),
                    reason="Bond buffer to improve stability."
                )
            )

        notes = [
            "Balanced mix of ETFs + Stocks + Bonds (diversified baseline).",
            "Holdings count changes based on how hands-on you want to be.",
            "This is a starting point, not trading advice. Adjust anytime.",
        ]


    # ---------- CASE 4: ETFs interest → ETF-only with focus-based tilts ----------
    else:  # "ETFs"
        # Equity split changes by focus
        if req.focus == "Growth":
            w_us = equity_target * 0.55
            w_growth = equity_target * 0.35
            w_intl = equity_target * 0.10
        elif req.focus == "Stability":
            w_us = equity_target * 0.70
            w_growth = equity_target * 0.10
            w_intl = equity_target * 0.20
        elif req.focus == "Dividend":
            # v1: no yield data; proxy = less growth tilt, more broad + bonds
            w_us = equity_target * 0.75
            w_growth = equity_target * 0.05
            w_intl = equity_target * 0.20
        else:  # Active returns
            w_us = equity_target * 0.40
            w_growth = equity_target * 0.45
            w_intl = equity_target * 0.15

        if want_simple:
            allocations = [
                StarterAllocationOut(ticker=us_core, type="etf", weight=round(w_us + w_growth, 4),
                                     reason="Single US equity core (broad + growth tilt combined)."),
                StarterAllocationOut(ticker=intl_core, type="etf", weight=round(w_intl, 4),
                                     reason="International diversification."),
                StarterAllocationOut(ticker=bonds_core, type="bond_etf", weight=round(bond_target, 4),
                                     reason="Bond buffer for stability."),
            ]
            notes = ["Simple 3-holding ETF starter (easy to maintain)."]
        elif want_mid:
            allocations = [
                StarterAllocationOut(ticker=us_core, type="etf", weight=round(w_us, 4),
                                     reason="Broad US market core."),
                StarterAllocationOut(ticker=us_growth, type="etf", weight=round(w_growth, 4),
                                     reason="Growth tilt."),
                StarterAllocationOut(ticker=intl_core, type="etf", weight=round(w_intl, 4),
                                     reason="International diversification."),
                StarterAllocationOut(ticker=bonds_core, type="bond_etf", weight=round(bond_target, 4),
                                     reason="Bond buffer for stability."),
            ]
            notes = ["Balanced 4-holding ETF starter (monthly-friendly)."]
        else:  # tweak
            allocations = [
                StarterAllocationOut(ticker=us_core, type="etf", weight=round(w_us, 4),
                                     reason="Broad US market core."),
                StarterAllocationOut(ticker=us_growth, type="etf", weight=round(w_growth, 4),
                                     reason="Growth tilt."),
                StarterAllocationOut(ticker=intl_core, type="etf", weight=round(w_intl, 4),
                                     reason="International diversification."),
                StarterAllocationOut(ticker=short_bonds, type="bond_etf", weight=round(bond_target * 0.40, 4),
                                     reason="Short-term bonds (lower rate sensitivity)."),
                StarterAllocationOut(ticker=long_bonds, type="bond_etf", weight=round(bond_target * 0.60, 4),
                                     reason="Intermediate/long bonds (stability buffer)."),
            ]
            notes = ["More granular ETF starter (for people who like to tweak)."]

        notes.append("This is a starting point, not trading advice. Adjust anytime.")

    # Normalize weights to sum to 1 (handles rounding)
    total = sum(a.weight for a in allocations)
    if total > 0:
        for a in allocations:
            a.weight = round(a.weight / total, 4)

    # Make the response visibly different for debugging/review
    name = f"{req.investmentStyle} • {req.focus} • {req.assetInterest} • {req.involvement} • {age}"

    # Convert Pydantic allocations -> Alloc dataclass
    alloc_objs = [
        Alloc(ticker=a.ticker, type=a.type, weight=a.weight, reason=a.reason)
        for a in allocations
    ]

    replacement_pools = {
        # Bonds: split large bond weight across bond ETFs
        "BND": ["AGG", "IEF", "TLT", "SHY"],
        "AGG": ["BND", "IEF", "TLT", "SHY"],
        "IEF": ["BND", "AGG", "TLT", "SHY"],

        # US broad: split across similar US broad ETFs
        "VTI": ["VOO", "SPY", "IVV"],
        "VOO": ["VTI", "SPY", "IVV"],
        "SPY": ["VTI", "VOO", "IVV"],
        "IVV": ["VTI", "VOO", "SPY"],

        # Growth: split across similar growth-heavy funds
        "QQQ": ["QQQM", "VUG", "XLK"],
        "QQQM": ["QQQ", "VUG", "XLK"],

        # International: split across developed ex-US
        "VEA": ["IEFA"],
        "IEFA": ["VEA"],
    }

    # Cap can be 0.12 to allow 8-10 holdings to pass concentration threshold ~10%
    alloc_objs = _split_overweight_allocations(
        allocs=alloc_objs,
        cap=0.12,
        replacement_pools=replacement_pools,
        tickers_available=TICKERS,
    )

    # Back to your response model objects
    allocations = [
        StarterAllocationOut(
            ticker=a.ticker,
            type=a.type,
            weight=a.weight,
            reason=a.reason,
        )
        for a in alloc_objs
    ]


    return StarterPortfolioResponse(
        asOf=AS_OF,
        name=name,
        allocations=allocations,
        notes=notes,
    )
