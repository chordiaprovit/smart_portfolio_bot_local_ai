import streamlit as st
import threading
import pandas as pd
import numpy as np
import plotly.express as px
from agent import agent_portfolio_recommendation
from chat import query_local_model
from screener import get_sector_for_ticker
from investor import suggest_diversificatio_corr, evaluate_virtual_portfolio
from portfolio_analyzer import build_portfolio_analysis_prompt
from data_saver import save_user_simulation, get_last_simulation
from sector_snapshot import get_sector_performance_from_snapshot, get_tickers_by_sector

FONT_SIZE = "15px"
st.set_page_config(page_title="SmartPortfolioBot", layout="wide")

st.markdown(f"""
    <style>
    .custom-font {{
        font-size: {FONT_SIZE} !important;
    }}
    /* Make sliders compact */
    .stSlider > div[data-baseweb="slider"] {{
        margin-top: -10px;
    }}
    </style>
""", unsafe_allow_html=True)

st.sidebar.title("🧠 SmartPortfolioBot")
st.sidebar.markdown(f"<p class='custom-font'>AI Stock Screener + Chat + Simulator</p>", unsafe_allow_html=True)

if "ai_response" not in st.session_state:
    st.session_state.ai_response = ""
if "ai_running" not in st.session_state:
    st.session_state.ai_running = False

def fetch_ai_response(prompt):
    response = query_local_model(prompt)
    st.session_state.ai_response = response
    st.session_state.ai_running = False

st.sidebar.markdown("<p class='custom-font'><b>💬 Ask the AI Assistant</b></p>", unsafe_allow_html=True)
user_prompt = st.sidebar.text_area("Ask your question", key="user_input")

if st.sidebar.button("Ask") and not st.session_state.ai_running:
    st.session_state.ai_running = True
    st.session_state.ai_response = ""
    thread = threading.Thread(target=fetch_ai_response, args=(user_prompt,))
    thread.start()

if st.session_state.ai_running:
    st.sidebar.info("💭 Assistant is thinking...")
elif st.session_state.ai_response:
    st.sidebar.markdown("<p class='custom-font'><b>Assistant:</b></p>", unsafe_allow_html=True)
    st.sidebar.markdown(f"<p class='custom-font'>{st.session_state.ai_response}</p>", unsafe_allow_html=True)

st.markdown("<h3 class='custom-font'>📈 Sector Performance (Past 30 Days)</h3>", unsafe_allow_html=True)

sector_gainers, sector_losers, gain_df, loss_df, merged = get_sector_performance_from_snapshot(
    "data/snp500_30day.csv", "data/snp500.csv"
)

def _pick_col(df, candidates):
    """Return the first matching column name from candidates or None."""
    return next((c for c in candidates if c in df.columns), None)

# --- PIE CHARTS FOR SECTOR PERFORMANCE ---
col_pie1, col_pie2 = st.columns(2)

def plotly_pie_chart(df, title, gain=True):
    if df is None or df.empty:
        return st.info(f"No {'gaining' if gain else 'losing'} sectors to display.")
    
    col_name = next((col for col in ["% Gain", "ChangePct", "Change %", "PctGain"] if col in df.columns), None) if gain else \
               next((col for col in ["% Loss", "ChangePct", "Change %", "PctLoss"] if col in df.columns), None)
    
    if not col_name:
        return st.warning(f"No {'gain' if gain else 'loss'} percentage column found.")
    
    values = pd.to_numeric(df[col_name], errors="coerce").fillna(0.0)
    if not gain:
        values = np.abs(values)
    
    df = df[values > 0].copy()
    df[col_name] = values[values > 0]
    
    if len(df) == 0:
        return st.info(f"No {'positive' if gain else 'negative'} percentages to plot.")
    
    fig = px.pie(df, values=col_name, names="Sector",
                 color_discrete_sequence=px.colors.qualitative.Safe if gain else px.colors.qualitative.Pastel2,
                 hole=0.3)
    
    # Customize layout
    fig.update_layout(
        title_text=title,
        uniformtext_minsize=12,
        uniformtext_mode='hide',
        margin=dict(t=50, b=10, l=10, r=10)
    )
    
    st.plotly_chart(fig, use_container_width=True, theme="streamlit")

col1, col2 = st.columns(2)
with col1:
    plotly_pie_chart(gain_df, "🔼 Gaining Sectors", gain=True)
with col2:
    plotly_pie_chart(loss_df, "🔽 Losing Sectors", gain=False)


# --- EXISTING TABLES ---
with st.expander("🔍 View Sector Performance", expanded=False):
    col1, col2 = st.columns(2)

    with col1:
        st.markdown(
            "<p class='custom-font'><b>🔼 Top Gaining Sectors</b></p>",
            unsafe_allow_html=True
        )
        for sector in gain_df['Sector']:
            with st.expander(f"{sector}"):
                st.dataframe(
                    get_tickers_by_sector(sector, merged),
                    hide_index=True
                )

    with col2:
        st.markdown(
            "<p class='custom-font'><b>🔽 Top Losing Sectors</b></p>",
            unsafe_allow_html=True
        )
        for sector in loss_df['Sector']:
            with st.expander(f"{sector}"):
                st.dataframe(
                    get_tickers_by_sector(sector, merged),
                    hide_index=True
                )

# --- Sector Search Dropdown ---
st.sidebar.markdown("### 🔍 Explore a Sector")
all_sectors = sorted(set(merged["GICS Sector"].dropna()))
selected_sector = st.sidebar.selectbox("Select Sector", options=all_sectors)
if selected_sector:
    st.sidebar.dataframe(get_tickers_by_sector(selected_sector, merged), hide_index=True)

@st.cache_data(show_spinner=False)
def load_history(path="data/snp500_30day.csv"):
    df = pd.read_csv(path)
    # Handle common date formats robustly
    df["Date"] = pd.to_datetime(df["Date"], format="%m/%d/%y", errors="coerce")
    # Normalize column names if needed
    cols = {c: c.strip() for c in df.columns}
    df.rename(columns=cols, inplace=True)
    # Expect long format: Date, Ticker, Close
    if not set(["Date", "Ticker", "Close"]).issubset(df.columns):
        # If file is in wide format (Date + many tickers), melt it
        id_cols = ["Date"]
        value_cols = [c for c in df.columns if c not in id_cols]
        df = df.melt(id_vars="Date", value_vars=value_cols, var_name="Ticker", value_name="Close")
    df = df.dropna(subset=["Date", "Ticker", "Close"])
    df["Ticker"] = df["Ticker"].str.upper().str.strip()
    df = df.sort_values(["Ticker", "Date"]).reset_index(drop=True)
    return df

hist_df = load_history()

st.markdown("<h3 class='custom-font'>💰 Try Investing - Simulated $1000 Portfolio</h3>", unsafe_allow_html=True)

@st.cache_data(show_spinner=False)
def load_hist():
    df = pd.read_csv("data/snp500_30day.csv")
    # Use robust parsing without deprecated args
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    return df

hist_df = load_hist()

# ---------- session state (non-widget) ----------
st.session_state.setdefault(
    "sim_df",
    pd.DataFrame(
        {"Ticker": ["", "", ""], "Allocation": [400.0, 350.0, 250.0]}
    )
)
st.session_state.setdefault("sim_result_text", "")
st.session_state.setdefault("sim_total_val", None)
st.session_state.setdefault("sim_suggestion_msg", "")
st.session_state.setdefault("sim_new_tickers", None)
st.session_state.setdefault("sim_new_allocs", None)

def _normalize_to_1000(values):
    s = sum(values)
    if s <= 0:
        return [1000.0/3.0]*3
    return [v * (1000.0 / s) for v in values]

def _run_simulation(tickers, allocations):
    # 1) Diversification: correlation tips
    try:
        from investor import suggest_diversificatio_corr
        correlation_msg = suggest_diversificatio_corr(tickers)
        if correlation_msg:
            st.info(f"📊 Diversification Tip: {correlation_msg}")
    except Exception:
        pass

    # 2) Agentic suggestion
    try:
        sectors = [get_sector_for_ticker(t) for t in tickers]
        suggestion_msg, new_tickers, new_allocs = agent_portfolio_recommendation(tickers, allocations, sectors)
    except Exception:
        suggestion_msg, new_tickers, new_allocs = "", None, None

    st.session_state.sim_suggestion_msg = suggestion_msg or ""
    st.session_state.sim_new_tickers = new_tickers
    st.session_state.sim_new_allocs = new_allocs
    if suggestion_msg:
        st.info(f"🤖 Agentic Suggestion: {suggestion_msg}")

    # 3) Compute 30-day performance
    latest_date = hist_df["Date"].max()
    start_date  = hist_df["Date"].min()

    price_changes = {}
    for tk in tickers:
        try:
            price_start = hist_df[(hist_df["Ticker"] == tk) & (hist_df["Date"] == start_date)]["Close"].values[0]
            price_end   = hist_df[(hist_df["Ticker"] == tk) & (hist_df["Date"] == latest_date)]["Close"].values[0]
            pct_change  = ((price_end - price_start) / price_start) * 100.0
            price_changes[tk] = round(float(pct_change), 2)
        except Exception:
            price_changes[tk] = None

    lines, total_val = [], 0.0
    for i, tk in enumerate(tickers):
        alloc = allocations[i]
        line = f"{tk}: ${alloc:.2f} → "
        if price_changes[tk] is not None:
            growth = alloc * (1 + price_changes[tk]/100.0)
            line += f"${growth:.2f} ({price_changes[tk]}%)"
            total_val += growth
        else:
            line += "Data unavailable"
            total_val += alloc
        lines.append(line)

    st.session_state.sim_result_text = "\n".join(lines)
    st.session_state.sim_total_val = total_val

    # 4) Save result
    try:
        success, msg = save_user_simulation(email or "", tickers, allocations, total_val)
        (st.success if success else st.error)(msg)
    except Exception as e:
        st.warning(f"⚠️ Unable to save simulation: {e}")

    # 5) AI analysis
    try:
        prompt = build_portfolio_analysis_prompt(tickers, allocations, sectors)
        ai_response = query_local_model(prompt)
        st.markdown("### 🤖 AI Portfolio Analysis")
        st.markdown(ai_response)
    except Exception as e:
        st.warning(f"⚠️ AI analysis failed: {e}")

# ---------- UI (no forms so it updates as you type) ----------
email = st.text_input("Enter your email", key="sim_email")

# Build your $1,000 portfolio with a form
st.markdown('#### Simulate $1,000 portfolio')
with st.expander("Your Portfolio", expanded=False):
    with st.form("sim_form", clear_on_submit=False):
        df0 = st.session_state.sim_df
        t1 = st.text_input("Ticker 1", value=df0.loc[0, "Ticker"], key="t1")
        a1 = st.number_input("Allocation 1", value=float(df0.loc[0, "Allocation"]),
                              min_value=0.0, step=10.0, format="%.2f", key="a1")
        t2 = st.text_input("Ticker 2", value=df0.loc[1, "Ticker"], key="t2")
        a2 = st.number_input("Allocation 2", value=float(df0.loc[1, "Allocation"]),
                              min_value=0.0, step=10.0, format="%.2f", key="a2")
        t3 = st.text_input("Ticker 3", value=df0.loc[2, "Ticker"], key="t3")
        a3 = st.number_input("Allocation 3", value=float(df0.loc[2, "Allocation"]),
                              min_value=0.0, step=10.0, format="%.2f", key="a3")

        run_clicked = st.form_submit_button("Run Simulation")
        if run_clicked:
            df_new = pd.DataFrame({
                "Ticker":     [t1.strip().upper(), t2.strip().upper(), t3.strip().upper()],
                "Allocation": [a1, a2, a3]
            })
            st.session_state.sim_df = df_new
            allocations = _normalize_to_1000([a1, a2, a3])
            _run_simulation(df_new["Ticker"].tolist(), allocations)


# Suggest using AI-suggested portfolio
if st.session_state.sim_new_tickers and st.session_state.sim_new_allocs:
    if st.button('Use Suggested Portfolio'):
        st.session_state.sim_df = pd.DataFrame({
            'Ticker': st.session_state.sim_new_tickers[:3],
            'Allocation': [float(x) for x in st.session_state.sim_new_allocs[:3]]
        })
        st.rerun()

# Show last result persistently
if st.session_state.sim_result_text:
    st.text(st.session_state.sim_result_text)
    if st.session_state.sim_total_val is not None:
        st.markdown(
            f"<p class='custom-font'><b>Total Value:</b> ${st.session_state.sim_total_val:,.2f}</p>",
            unsafe_allow_html=True
        )

# --- RETRIEVE PREVIOUS SIMULATION (ALWAYS VISIBLE) ---
st.markdown("<h3 class='custom-font'>📩 Retrieve Previous Simulation</h3>", unsafe_allow_html=True)
email_to_fetch = st.text_input("Enter email to load your last simulation", key="fetch_email")
if st.button("Fetch Last Simulation", key="fetch_btn"):
    sim = get_last_simulation(email_to_fetch)
    if sim is not None:
        last = sim.iloc[0]
        try:
            tickers_last = [x.strip().upper() for x in last["tickers"].split(",")]
            allocations_last = [float(a) for a in last["allocations"].split(",")]

            # Fill the editor and show today’s performance
            st.session_state.sim_df = pd.DataFrame(
                {"Ticker": tickers_last[:3], "Allocation": allocations_last[:3]}
            )

            st.success("Previous simulation loaded! Table updated above.")

            result, total_val = evaluate_virtual_portfolio(tickers_last[:3], allocations_last[:3], last["date"])
            if result is not None:
                df_result = pd.DataFrame.from_dict(result, orient="index").reset_index().rename(columns={"index": "Ticker"})
                st.dataframe(df_result, use_container_width=True)
                st.markdown(
                    f"<p class='custom-font'><b>Total Value:</b> ${total_val:,.2f}</p>",
                    unsafe_allow_html=True
                )
            else:
                st.info("No portfolio evaluation available.")

            # AI analysis of fetched portfolio
            try:
                sectors_last = [get_sector_for_ticker(t) for t in tickers_last[:3]]
                prompt = build_portfolio_analysis_prompt(tickers_last[:3], allocations_last[:3], sectors_last)
                ai_response = query_local_model(prompt)
                st.markdown("### 🤖 AI Portfolio Analysis")
                st.markdown(ai_response)
            except Exception as e:
                st.warning(f"⚠️ AI analysis failed: {e}")

        except Exception as e:
            st.warning(f"⚠️ Unable to load previous simulation: {e}")
    else:
        st.warning("No previous simulation found for this email.")
