import streamlit as st
import os
import csv
from datetime import datetime, timezone
import threading
import pandas as pd
import numpy as np
import plotly.express as px
from agent import agent_portfolio_recommendation
from portfolio_simulator import simulate_portfolio
from chat import query_local_model
from screener import get_sector_for_ticker
from investor import  evaluate_virtual_portfolio
from portfolio_analyzer import build_portfolio_analysis_prompt
from data_saver import save_user_simulation, get_last_simulation
from agent_runner import portfolio_agent
from sector_snapshot import get_sector_performance_from_snapshot, get_tickers_by_sector
from dotenv import load_dotenv
import plotly.graph_objects as go
from statsmodels.tsa.arima.model import ARIMA
from investor import suggest_diversificatio_corr


FONT_SIZE = "15px"
FONT_SIZE_LARGE = "18px"
st.set_page_config(page_title="SmartPortfolioBot", layout="wide")
load_dotenv()

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

st.markdown("""
    <style>
    /* Target the tab labels */
    button[data-baseweb="tab"] {
        font-size: 20px !important;  /* Increase font size */
        font-weight: bold;           /* Optional: make it bold */
    }
    </style>
""", unsafe_allow_html=True)

tab1, tab3, tab4, tab5 = st.tabs(["ℹ️ About", "📈 Sector Performance", "💰 Portfolio Simulator", "Macro Simulator"])

with tab1:
    # --- Lightweight CSS polish ---
    st.markdown("""
    <style>
      .about-card {
        border: 1px solid rgba(128,128,128,0.2);
        padding: 1rem 1.2rem;
        border-radius: 14px;
        background: rgba(250,250,250,0.6);
      }
      .about-h1 {
        font-size: 1.4rem; margin: 0 0 .5rem 0; font-weight: 700;
      }
      .about-muted { color: #666; font-size: .95rem; }
      .kpi {
        border: 1px solid rgba(128,128,128,0.18);
        border-radius: 12px; padding: .75rem 1rem; background: white;
      }
      .kpi h3 { margin: 0 0 .25rem 0; font-size: .95rem; }
      .bullets ul { margin-top: .35rem; }
      .step {
        display:flex; gap:.6rem; align-items:flex-start; margin-bottom:.6rem;
      }
      .step-num {
        width: 26px; height: 26px; border-radius: 50%;
        background: #eee; display:flex; align-items:center; justify-content:center;
        font-weight:700;
      }
    </style>
    """, unsafe_allow_html=True)

    # --- Title & subtitle ---
    st.markdown("<div class='about-h1'>Smart Portfolio Simulator</div>", unsafe_allow_html=True)
    st.markdown("<div class='about-muted'>Test strategies with real market data and AI insights—before risking capital.</div>", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

    st.divider()

    # --- Quick KPIs / value props ---
    c1, c2, c3 = st.columns(3)

    with c1:
        st.markdown("🧠 AI Insights")
        st.markdown("Detect high correlations and suggest diversification.")

    with c2:
        st.markdown("📈 Sector View")
        st.markdown("Track daily gainers and losers by sector.")

    with c3:
        st.markdown("💾 Save & Revisit")
        st.markdown("Store portfolios and compare runs over time.")

    st.markdown("</div>", unsafe_allow_html=True)

    # --- What it does / How it works ---
    left, right = st.columns([1.05, 1])
    with left:
        st.markdown("**What it does**")
        st.markdown("""
        - Simulate portfolios with real market data  
        - AI-based diversification insights  
        - Track sector gainers/losers  
        - Save & revisit simulations  
        """)
    with right:
        st.markdown("**How it works**")
        st.markdown("""
        - Select tickers
        - Choose timeframe
        - Run simulation
        - Read AI insights & adjust
        """, unsafe_allow_html=True)

    # --- Optional: collapsible tips ---
    with st.expander("Tips for best results"):
        st.markdown("""
        - Keep weights normalized (sum to 1.0) for clean comparisons.  
        - Avoid over-concentration: watch for **corr > 0.85** across holdings.  
        - Compare multiple runs (e.g., growth vs. value vs. defensive).  
        - Past performance isn’t predictive — use this as a learning tool.
        """)

    st.info("Educational use only — not financial advice.")

    
with tab3:
    st.markdown("<h3 class='custom-font'>📈 Sector Performance (Past 30 Days)</h3>", unsafe_allow_html=True)

    sector_gainers, sector_losers, gain_df, loss_df, merged = get_sector_performance_from_snapshot(
        "data/snp500_30day_wide.csv", "data/snp500.csv"
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

    with st.expander("### 🔍 Explore a Sector", expanded=False):
        all_sectors = sorted(set(merged["GICS Sector"].dropna()))
        selected_sector = st.selectbox("Select Sector", options=all_sectors)
        if selected_sector:
            st.dataframe(get_tickers_by_sector(selected_sector, merged), hide_index=True)
        


       # --- New: Ticker details & full price history ---
    with st.expander("🔎 Ticker details & price history", expanded=False):
        try:
            available_tickers = sorted(hist_df["Ticker"].dropna().unique().tolist())
        except Exception:
            available_tickers = []

        if not available_tickers:
            st.warning("No tickers found in the loaded price history.")
        else:
            default_idx = available_tickers.index("AAPL") if "AAPL" in available_tickers else 0
            sel_t = st.selectbox("Select a ticker", options=available_tickers, index=default_idx, key="sector_perf_ticker")
            sel_security = merged.loc[merged['Ticker'] == sel_t, 'Security'].values

            # Find sector using merged snapshot mapping if available, else fallback
            sector_name = None
            try:
                if 'Sector' in merged.columns and 'Ticker' in merged.columns:
                    row = merged.loc[merged['Security'].astype(str).str.upper() == str(sel_t).upper()]
                    if not row.empty:
                        sector_name = str(row.iloc[0]['Sector'])
            except Exception:
                pass
            if not sector_name:
                try:
                    sector_name = get_sector_for_ticker(str(sel_t))
                except Exception:
                    sector_name = None

            if sector_name:
                st.markdown(f"**Sector:** {sector_name}")
            else:
                st.markdown("**Sector:** _Unknown_")

            # Filter history for selected ticker and plot
            tdf = hist_df.loc[hist_df["Ticker"].astype(str).str.upper() == str(sel_t).upper()].copy()
            if tdf.empty:
                st.info("No price history found for the selected ticker in the loaded file.")
            else:
                # Ensure proper dtypes and sorting
                tdf["Date"] = pd.to_datetime(tdf["Date"], errors="coerce")
                tdf = tdf.dropna(subset=["Date", "Close"]).sort_values("Date")
                # Title reflects length (e.g., 30 vs 300)
                n_days = tdf["Date"].nunique()
                title = f"{sel_t} Price History ({n_days} days)"
                fig_line = px.line(tdf, x="Date", y="Close", title=title)
                fig_line.update_layout(margin=dict(t=50, b=10, l=10, r=10))
                st.plotly_chart(fig_line, use_container_width=True, theme="streamlit")
    
with tab4:
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
    st.session_state.setdefault("sim_new_tickers", "")
    st.session_state.setdefault("sim_new_allocs", None)

    def _normalize_to_1000(values):
        s = sum(values)
        if s <= 0:
            return [1000.0/3.0]*3
        return [v * (1000.0 / s) for v in values]

    def _run_simulation(tickers, allocations):
        try:
            
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

        #simulate_portfolio
        result = simulate_portfolio(tickers, investment=1000.0, start_date=None, high_corr_threshold=0.85, risk_free_rate=0.0)

        def interpret_sharpe(sharpe_ratio: float) -> tuple[str, str]:
            if sharpe_ratio < 1.0:
                return "Low Risk", "❌ Poor Return"
            elif 1.0 <= sharpe_ratio < 2.0:
                return "Moderate Risk", "✅ Good Return"
            elif 2.0 <= sharpe_ratio < 3.0:
                return "High Risk", "🌟 Great Return"
            else:
                return "Very High Risk", "🚀 Excellent Return"
        
        col1, col2, col3 = st.columns(3)
        col1.metric("Annualized Return", f"{result['return_annualized']:.2%}")
        col2.metric("Annualized Volatility", f"{result['volatility_annualized']:.2%}")
        sharpe = result['sharpe_ratio']
        risk_level, verdict = interpret_sharpe(sharpe)
        col3.metric(
            "Sharpe Ratio",
            f"{sharpe:.2f}",
            help=f" {risk_level} , {verdict}"
        )

        with st.expander("📈 Correlation Matrix"):

            corr_matrix = result['corr_matrix']
            fig = go.Figure(
                data=go.Heatmap(
                    z=corr_matrix.values,
                    x=corr_matrix.columns,
                    y=corr_matrix.index,
                    colorscale='RdBu',
                    zmin=-1, zmax=1,
                    colorbar=dict(title="Correlation")
                )
            )
            fig.update_layout(
                title="Correlation Matrix Heatmap",
                xaxis_title="Ticker",
                yaxis_title="Ticker",
                width=500,
                height=500
            )
            st.plotly_chart(fig, use_container_width=True)

        if result['high_corr_pairs']:
            st.warning(
                "⚠️ Highly correlated pairs (> 0.85): " +
                ", ".join([f"{a}-{b} ({c:.2f})" for a,b,c in result['high_corr_pairs']])
            )

        # 5) AI analysis
        st.markdown("### 🤖 Analysis")
        use_agent = st.toggle("Use Agentic suggestions (Yahoo→AV fallback, tips, correlation)", value=True)

        if use_agent:
            try:
                with st.spinner("Agent is planning, fetching and analyzing..."):
                    out = portfolio_agent(tickers, prefer="yahoo", allow_fallback=True)

                st.markdown("#### 📋 Tip Sheet")
                for t in out["tips"]:
                    st.markdown(f"- {t}")

                st.markdown("#### 💡 Suggestions (view-only)")
                st.info(out["suggestions"]["message"])
                if out["suggestions"]["high_corr_pairs"]:
                    st.caption(
                        "High-corr pairs: " +
                        ", ".join([f"{a}-{b} ({c:.2f})" for a,b,c in out["suggestions"]["high_corr_pairs"]])
                    )

                with st.expander("🧠 Agent Log"):
                    # Show only lines that start with "Fetched prices from "
                    filtered_log = [line for line in out["log"] if line.strip().startswith("Fetched prices from ")]
                    if filtered_log:
                        st.code("\n".join(filtered_log))
                    else:
                        st.code("No price fetch log found.")
            except Exception as e:
                st.warning(f"Agent failed: {e}")
                st.caption("Falling back to LLM analysis…")
                try:
                    prompt = build_portfolio_analysis_prompt(tickers, allocations, sectors)
                    ai_response = query_local_model(prompt)
                    st.markdown("#### LLM Portfolio Analysis")
                    st.markdown(ai_response)
                except Exception as e2:
                    st.warning(f"LLM analysis failed: {e2}")
        else:
            try:
                prompt = build_portfolio_analysis_prompt(tickers, allocations, sectors)
                ai_response = query_local_model(prompt)
                st.markdown("#### LLM Portfolio Analysis")
                st.markdown(ai_response)
            except Exception as e:
                st.warning(f"LLM analysis failed: {e}")

        st.text("You can edit the form above to change your portfolio and re-run the simulation.")        
            # ---------- UI (no forms so it updates as you type) ----------

    # Build your $1,000 portfolio with a form
    st.markdown('#### Simulate $1,000 portfolio')
    with st.expander("Your Portfolio", expanded=False):
        with st.form("sim_form", clear_on_submit=False):
            df0 = st.session_state.sim_df

            st.markdown("##### Enter your portfolio tickers and allocations (must total $1,000):")

            col1, col2, col3 = st.columns(3)
            with col1:
                t1 = st.text_input("Ticker 1", value=df0.loc[0, "Ticker"], key="t1")
                a1 = st.number_input("Allocation 1", value=float(df0.loc[0, "Allocation"]),
                                     min_value=0.0, step=10.0, format="%.2f", key="a1")
            with col2:
                t2 = st.text_input("Ticker 2", value=df0.loc[1, "Ticker"], key="t2")
                a2 = st.number_input("Allocation 2", value=float(df0.loc[1, "Allocation"]),
                                     min_value=0.0, step=10.0, format="%.2f", key="a2")
            with col3:
                t3 = st.text_input("Ticker 3", value=df0.loc[2, "Ticker"], key="t3")
                a3 = st.number_input("Allocation 3", value=float(df0.loc[2, "Allocation"]),
                                     min_value=0.0, step=10.0, format="%.2f", key="a3")

            st.markdown("---")
            run_clicked = st.form_submit_button("Run Simulation")
            total_alloc = a1 + a2 + a3
            if run_clicked:
                if abs(total_alloc - 1000.0) > 0.01:
                    st.markdown(
                    f"<span class='custom-font'>⚠️ Total allocation must be exactly 1,000. Current total: ${total_alloc:,.2f}. Please adjust your allocations.</span>",
                    unsafe_allow_html=True
                )               
                else:
                    df_new = pd.DataFrame({
                        "Ticker":     [t1.strip().upper(), t2.strip().upper(), t3.strip().upper()],
                        "Allocation": [a1, a2, a3]
                    })
                    st.session_state.sim_df = df_new
                    _run_simulation(df_new["Ticker"].tolist(), [a1, a2, a3])


        # Suggest using AI-suggested portfolio
        if st.session_state.sim_new_tickers and st.session_state.sim_new_allocs:
            if st.button('Use Suggested Portfolio'):
                st.session_state.sim_df = pd.DataFrame({
                    'Ticker': st.session_state.sim_new_tickers[:3],
                    'Allocation': [float(x) for x in st.session_state.sim_new_allocs[:3]]
                })
                st.rerun()

                # )
            # --- Ask for email before Save Portfolio ---
            email = st.text_input("Enter your email", key="sim_email")
            st.text("💾 Save your portfolio to monitor progress over 1 month.")
            if st.button("💾 Save Portfolio Now"):
                if not email or email.strip() == "":
                    st.warning("Please enter your email before saving your portfolio.")
                else:
                    try:
                        success, msg = save_user_simulation(
                            email.strip(),
                            st.session_state.sim_df["Ticker"].tolist(),
                            st.session_state.sim_df["Allocation"].tolist(),
                            st.session_state.sim_total_val
                        )
                        (st.success if success else st.error)(msg)
                    except Exception as e:
                        st.warning(f"⚠️ Unable to save simulation: {e}")

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

    if st.button("🔄 Reset Simulation & Data", key="reset_simulation"):
        try:
            st.cache_data.clear()
        except Exception:
            pass
        # Clear simulation-related session_state keys
        for k in list(st.session_state.keys()):
            if k.startswith("sim_") or k in ["tickers", "allocations", "simulation_results"]:
                del st.session_state[k]
        st.toast("Simulation inputs & data cleared. Reloading…")
        st.rerun()

def append_feedback(row: list[str]):
    os.makedirs(os.path.dirname(FEEDBACK_CSV_PATH), exist_ok=True)
    is_new = not os.path.exists(FEEDBACK_CSV_PATH)
    with open(FEEDBACK_CSV_PATH, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if is_new:
            w.writerow(["timestamp", "email", "rating", "feedback"])
        w.writerow(row)

FEEDBACK_CSV_PATH = "data/feedback.csv"

with st.sidebar.expander("💬 Feedback"):
    email_default = st.session_state.get("user_email", "")
    email = st.text_input("Email (optional)", value=email_default, placeholder="you@example.com", key="feedback_email")
    rating = st.select_slider("How satisfied are you?", options=[1,2,3,4,5], value=4, key="feedback_rating")
    feedback = st.text_area("What should we improve?", height=120, placeholder="Be as specific as possible…", key="feedback_text")

    if st.button("Submit feedback", use_container_width=True):
        if not feedback.strip():
            st.warning("Please add a short note before submitting.")
        else:
            append_feedback([
                datetime.now().isoformat(timespec="seconds"),
                email.strip(),
                str(rating),
                feedback.strip()
            ])
            st.success("Thanks! Your feedback was saved.")

            # 🔹 Clear fields after submit
            st.session_state.feedback_email = ""
            st.session_state.feedback_rating = 4
            st.session_state.feedback_text = ""

@st.cache_data
def load_wide_data(path="data/snp500_30day_wide.csv"):
    df = pd.read_csv(path)
    df["Date"] = pd.to_datetime(df["Date"], format="%m/%d/%y", errors="coerce")
    df = df.set_index("Date")
    return df

def sslider(label, min_v, max_v, default, step, help_text, key=None):
    return st.slider(
        label,
        min_value=min_v, max_value=max_v, value=default, step=step,
        help=help_text, key=key
    )

with tab5:
    st.markdown("<h3 class='custom-font'>🌐 Macro Economic Scenario Simulator</h3>", unsafe_allow_html=True)
    st.info("Simulate how economic shocks might affect S&P 500 prices with macro factor shocks and compare to ARIMA.")

    df_wide = load_wide_data()
    tickers = list(df_wide.columns)
    selected_ticker = st.selectbox(
        "Select ticker to simulate",
        options=tickers,
        index=tickers.index("AAPL") if "AAPL" in tickers else 0
    )

    st.markdown("#### Adjust Economic Factors")

    c1, c2, c3, c4 = st.columns(4)

    with c1:
        interest_rate = sslider(
            "Interest Rate Δ (pp)", -2.0, 2.0, 0.0, 0.1,
            "Fed policy rate. Higher = costlier loans; lower = cheaper borrowing."
        )
        unemployment = sslider(
            "Unemployment Δ (pp)", -2.0, 2.0, 0.0, 0.1,
            "Share of people out of work. Higher unemployment usually slows spending."
        )
        credit_spread = sslider(
            "Credit Spreads Δ (pp)", -2.0, 3.0, 0.0, 0.1,
            "Gap between risky and safe bonds. Wider gap = more financial stress."
        )

    with c2:
        inflation = sslider(
            "Inflation (CPI) Shock (%)", -3.0, 5.0, 0.0, 0.1,
            "Rising prices of goods/services. High inflation erodes purchasing power."
        )
        retail_sales = sslider(
            "Retail Sales Shock (%)", -5.0, 10.0, 0.0, 0.5,
            "How much consumers are buying. Growth shows confidence."
        )
        usd = sslider(
            "USD Index Shock (%)", -10.0, 10.0, 0.0, 0.5,
            "Strength of the dollar vs other currencies. Strong USD can hurt exporters."
        )

    with c3:
        pmi_manu = sslider(
            "PMI Manufacturing Δ (pts)", -10.0, 10.0, 0.0, 0.5,
            "Survey of manufacturers. Above 50 = expansion; below 50 = contraction."
        )
        pmi_serv = sslider(
            "PMI Services Δ (pts)", -10.0, 10.0, 0.0, 0.5,
            "Survey of services firms. Above 50 = expansion; below 50 = slowdown."
        )
        curve_slope = sslider(
            "Yield Curve (10y–2y) Δ (pp)", -2.0, 2.0, 0.0, 0.1,
            "Difference between long- and short-term rates. Inversion can signal recession."
        )

    with c4:
        sentiment = sslider(
            "Sentiment Δ (pts)", -30.0, 30.0, 0.0, 1.0,
            "How optimistic/pessimistic consumers and investors feel."
        )
        vix = sslider(
            "VIX Δ (pts)", -10.0, 20.0, 0.0, 0.5,
            "Market’s “fear index”. Higher = more expected volatility."
        )
        user_vol_mult = sslider(
            "Base Volatility Multiplier", 0.5, 2.0, 1.0, 0.05,
            "Scales overall market volatility to test calm vs turbulent conditions."
        )

    n_sim = st.number_input("Number of Monte Carlo Simulations", min_value=100, max_value=10000, value=500, step=100)

    st.markdown("---")

    if st.button("Run Simulation"):
        with st.spinner("Running Monte Carlo + ARIMA..."):
            # --- Pull price series
            px_series = df_wide[selected_ticker].dropna()

            # === Monte Carlo with macro-adjusted drift/vol ===
            rets = px_series.pct_change().dropna()
            logrets = np.log1p(rets)
            mu_hist = logrets.mean()
            resid = logrets - mu_hist

            # Drift betas (monthly % impact per unit; see notes)
            drift_betas = {
                "interest_rate": -0.40, "inflation": -0.30, "unemployment": -0.35,
                "retail_sales": 0.25, "pmi_manu": 0.05, "pmi_serv": 0.04,
                "credit_spread": -0.50, "usd": -0.10, "curve_slope": 0.10, "sentiment": 0.02,
            }
            vol_betas = {
                "vix": 0.03, "credit_spread": 0.10, "usd": 0.01, "inflation": 0.02,
                "pmi_manu": -0.005, "pmi_serv": -0.004,
            }

            factors = {
                "interest_rate": interest_rate, "inflation": inflation, "unemployment": unemployment,
                "retail_sales": retail_sales, "pmi_manu": pmi_manu, "pmi_serv": pmi_serv,
                "credit_spread": credit_spread, "usd": usd, "curve_slope": curve_slope,
                "sentiment": sentiment, "vix": vix
            }

            # Monthly → daily drift (fraction/day)
            monthly_drift_pct = sum(drift_betas[k] * v for k, v in factors.items() if k in drift_betas)
            drift_adj_daily = (monthly_drift_pct / 100.0) / 21.0

            # Volatility multiplier
            vol_influence = sum(vol_betas[k] * v for k, v in factors.items() if k in vol_betas)
            vol_mult = float(np.clip(user_vol_mult * (1.0 + vol_influence), 0.25, 3.0))

            # Vectorized bootstrap
            rng = np.random.default_rng(42)
            horizon = 30  
            resid_draws = rng.choice(resid.values, size=(horizon, int(n_sim)), replace=True)
            step_logrets = (mu_hist + drift_adj_daily) + vol_mult * resid_draws

            last_price = float(px_series.iloc[-1])
            cum_logrets = step_logrets.cumsum(axis=0)
            sim_prices = last_price * np.exp(cum_logrets)  # (horizon, n_sim)
            sim_index = pd.bdate_range(px_series.index[-1] + pd.Timedelta(days=1), periods=horizon)

            # Fan chart quantiles
            quantiles = [5, 25, 50, 75, 95]
            bands = np.percentile(sim_prices, quantiles, axis=1)  # (5, horizon)

            log_px = np.log(px_series)
            best_aic, best_order, best_model = np.inf, None, None
            for p in range(0, 3):
                for d in range(0, 2):
                    for q in range(0, 3):
                        try:
                            m = ARIMA(log_px, order=(p, d, q)).fit(method_kwargs={"warn_convergence":False})
                            if m.aic < best_aic:
                                best_aic, best_order, best_model = m.aic, (p, d, q), m
                        except Exception:
                            pass

            if best_model is None:
                # fallback simple ARIMA(1,1,1)
                best_model = ARIMA(log_px, order=(1, 1, 1)).fit(method_kwargs={"warn_convergence":False})
                best_order = (1, 1, 1)

            arima_fc = best_model.get_forecast(steps=horizon)
            arima_mean_log = arima_fc.predicted_mean
            arima_ci = arima_fc.conf_int(alpha=0.10)  

            # Convert to price space
            arima_mean = np.exp(arima_mean_log)
            arima_lower = np.exp(arima_ci.iloc[:, 0])
            arima_upper = np.exp(arima_ci.iloc[:, 1])
            arima_index = pd.bdate_range(px_series.index[-1] + pd.Timedelta(days=1), periods=horizon)

            fig = go.Figure()

            # MC 50% band
            fig.add_trace(go.Scatter(
                x=list(sim_index) + list(sim_index[::-1]),
                y=list(bands[3]) + list(bands[1][::-1]),
                fill='toself', fillcolor="rgba(0, 100, 255, 0.20)",
                line=dict(color="rgba(0,0,0,0)"), name="MC 50% CI"
            ))
            # MC 90% band
            fig.add_trace(go.Scatter(
                x=list(sim_index) + list(sim_index[::-1]),
                y=list(bands[4]) + list(bands[0][::-1]),
                fill='toself', fillcolor="rgba(0, 100, 255, 0.10)",
                line=dict(color="rgba(0,0,0,0)"), name="MC 90% CI"
            ))
            # MC Median
            fig.add_trace(go.Scatter(
                x=sim_index, y=bands[2], mode='lines', line=dict(width=2),
                name="MC Median"
            ))
            # ARIMA mean
            fig.add_trace(go.Scatter(
                x=arima_index, y=arima_mean, mode='lines', line=dict(width=2),
                name=f"ARIMA mean {best_order}"
            ))

            fig.update_layout(
                title=f"{selected_ticker} — Monte Carlo vs. ARIMA (Next {horizon} Business Days)",
                xaxis_title="Date", yaxis_title="Price", showlegend=True
            )
            st.plotly_chart(fig, use_container_width=True)

            with st.expander("ℹ️ What do these forecasts mean?"):
                st.markdown("""
                - **Trend Projection (ARIMA):** Extends the recent price trend forward. Good for short-term signals.
                - **Range of Outcomes (Monte Carlo):** Runs hundreds of random scenarios based on historical patterns. Good for seeing uncertainty and possible swings.
                
                Together, they show both the *most likely trend* and the *range of possible futures*.
                """)

            final_mc = sim_prices[-1, :]
            mc_p5, mc_p50, mc_p95 = np.percentile(final_mc, [5, 50, 95])
            mc_mean = final_mc.mean()

            last_price_val = float(px_series.iloc[-1])
            comp_df = pd.DataFrame({
                "Metric": ["Start Price", "MC Mean Final", "ARIMA Final (mean)"],
                "Value": [
                    f"${last_price_val:,.2f}",
                    f"${mc_mean:,.2f}",
                    f"${float(np.asarray(arima_mean)[-1]):,.2f}",
                ]
            })
            st.markdown("#### Model Comparison (End of Horizon)")
            st.dataframe(comp_df, hide_index=True, use_container_width=True)

            st.caption(
                "Notes: Monte Carlo uses macro‑adjusted drift and volatility (residual bootstrap). "
                "ARIMA is a univariate time‑series baseline (price‑only)."
            )
