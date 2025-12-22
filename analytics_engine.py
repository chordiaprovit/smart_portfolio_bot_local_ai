import json
import streamlit as st
import pandas as pd
import numpy as np

ANALYTICS_PACK_PATH = "data/analytics_pack.json"  # or "data/analytics_pack.json" if you keep it there

@st.cache_data(show_spinner=False)
def load_analytics_pack(path: str = ANALYTICS_PACK_PATH) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def _coerce_onboarding(payload: dict) -> dict:
    """
    Accepts mobile JSON with keys:
      investmentStyle, assetInterest, focus, involvement, ageRange
    AssetInterest could be str or list[str].
    """
    out = dict(payload or {})
    # normalize keys
    out.setdefault("investmentStyle", out.get("investment_style", "Long-term"))
    out.setdefault("assetInterest", out.get("asset_interest", ["All of the above"]))
    out.setdefault("focus", out.get("Focus", out.get("focus", "Growth")))
    out.setdefault("involvement", out.get("involvement", "Set & forget"))
    out.setdefault("ageRange", out.get("ageRange", None))
    # normalize assetInterest to list
    ai = out.get("assetInterest")
    if isinstance(ai, str):
        out["assetInterest"] = [ai]
    elif ai is None:
        out["assetInterest"] = ["All of the above"]
    return out

def suggest_starter_from_pack(pack: dict, onboarding: dict, k: int = 8) -> tuple[list[dict], list[str]]:
    """
    Uses analytics_pack.json -> tickers[t] has cagr, vol, trend, last_price.
    Returns (tickers, weights_as_$, notes).
    """
    onboarding = _coerce_onboarding(onboarding)
    focus = str(onboarding.get("focus", "Growth"))
    style = str(onboarding.get("investmentStyle", "Long-term"))
    involvement = str(onboarding.get("involvement", "Set & forget"))

    tickers_map = pack.get("tickers", {})
    if not tickers_map:
        return [], [], ["analytics_pack.json has no 'tickers' entries."]

    # Build candidate frame
    rows = []
    for t, m in tickers_map.items():
        try:
            rows.append({
                "Ticker": str(t).upper(),
                "cagr": float(m.get("cagr", 0.0)),
                "vol": float(m.get("vol", 0.0)),
                "trend": float(m.get("trend", 0.0)),
                "last_price": float(m.get("last_price", 0.0)),
                "type": str(m.get("type", "unknown")),
                "name": str(m.get("name", "unknown")),
            })
        except Exception:
            continue

    df = pd.DataFrame(rows)
    if df.empty:
        return [], [], ["No usable rows in analytics_pack.json tickers."]

    # Filter by asset interest
    notes = []
    asset_interest = onboarding.get("assetInterest", [])
    allowed_types = set()
    if any(x.lower() in ["stocks", "all of the above", "i don't know"] for x in asset_interest):
        allowed_types.add("stock")
    if any(x.lower() in ["etfs", "all of the above", "i don't know"] for x in asset_interest):
        allowed_types.add("etf")
    
    if allowed_types:
        df = df[df["type"].isin(allowed_types)].copy()
        if df.empty:
            return [], [], ["No tickers match the selected asset interests."]
        notes.append(f"Filtered to {', '.join(sorted(allowed_types))} based on asset interests.")
    else:
        notes.append("No specific asset interests selected; including all types.")

    vol_cap = 10.0
    if style.lower().startswith("conservative"):
        vol_cap = 0.22
        notes.append("Conservative style: preferring lower volatility.")
    elif style.lower().startswith("long"):
        vol_cap = 0.30
    else:  # Active
        vol_cap = 10.0
        notes.append("Active style: allowing higher volatility candidates.")

    if involvement.lower().startswith("set"):
        k = min(k, 8)
        notes.append("Set & forget: recommending a compact diversified starter basket.")

    df = df[df["vol"].fillna(0) <= vol_cap].copy()
    if df.empty:
        # fallback: remove cap
        df = pd.DataFrame(rows)
        notes.append("Volatility cap was too strict; expanded candidate set.")

    # Scoring by focus
    # (No dividend yield field in pack, so Dividend focus uses low-vol + decent cagr as proxy.)
    if focus.lower().startswith("growth"):
        df["score"] = (df["cagr"] * 2.0) + (df["trend"] * 250.0) - (df["vol"] * 0.5)
    elif focus.lower().startswith("div"):
        df["score"] = (df["cagr"] * 1.0) - (df["vol"] * 1.0) + (df["trend"] * 100.0)
        notes.append("Dividend focus: pack has no yield; using low-vol + steady trend proxy.")
    elif focus.lower().startswith("stab"):
        df["score"] = -(df["vol"] * 2.0) + (df["trend"] * 50.0) + (df["cagr"] * 0.3)
    else:  # Active returns
        df["score"] = (df["trend"] * 350.0) + (df["cagr"] * 1.5) + (df["vol"] * 0.2)

    df = df.sort_values("score", ascending=False).head(k).copy()

    # --- score -> weights as fractions (sum to 1.0) ---
    min_s = float(df["score"].min())
    df["w_raw"] = df["score"] - min_s  # make non-negative (min becomes 0)

    if float(df["w_raw"].sum()) <= 1e-12:
        # fallback if all scores equal
        df["w"] = 1.0 / max(1, len(df))
        notes.append("All scores similar; used equal-weight fallback.")
    else:
        # optional shaping: >1 concentrates, <1 flattens
        power = 1.2
        df["w_raw"] = df["w_raw"] ** power
        df["w"] = df["w_raw"] / df["w_raw"].sum()

    cap = 0.25
    df["w"] = df["w"].clip(upper=cap)
    df["w"] = df["w"] / df["w"].sum()
    
    # use tickers weight greater than 0 and round weights to 2 decimals
    df = df[df["w"] > 0.01]
    picks_data = []
    for _, row in df.iterrows():
        picks_data.append({
            "ticker": row["Ticker"],
            "weight": round(float(row["w"]), 4),
            "name": row["name"]
        })

    notes.append("Weights derived from focus-based score (higher score ⇒ higher weight).")
    notes.append(f"Selected {len(picks_data)} tickers based on {focus} focus, {style} style, {involvement} involvement.")
    notes.append("Score formula: higher CAGR and trend increase score; higher volatility decreases score.")
    return picks_data, notes


