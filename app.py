import streamlit as st
import threading
import pandas as pd
from agent import agent_portfolio_recommendation
from chat import query_local_model
from screener import get_sector_for_ticker
from investor import create_virtual_portfolio, evaluate_virtual_portfolio, suggest_diversification
from portfolio_analyzer import build_portfolio_analysis_prompt
from data_saver import save_user_simulation, get_last_simulation
from sector_snapshot import get_sector_performance_from_snapshot, get_tickers_by_sector  # updated

FONT_SIZE = "15px"
st.set_page_config(page_title="SmartPortfolioBot", layout="wide")

st.markdown(f"""
    <style>
    .custom-font {{
        font-size: {FONT_SIZE} !important;
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
    "data/snp500_30day.csv", "data/snp500.csv")

col1, col2 = st.columns(2)
with col1:
    st.markdown(f"<p class='custom-font'><b>🔼 Top Gaining Sectors</b></p>", unsafe_allow_html=True)
    for sector in gain_df['Sector']:
        with st.expander(f"{sector}"):
            st.dataframe(get_tickers_by_sector(sector, merged), hide_index=True)
with col2:
    st.markdown(f"<p class='custom-font'><b>🔽 Top Losing Sectors</b></p>", unsafe_allow_html=True)
    for sector in loss_df['Sector']:
        with st.expander(f"{sector}"):
            st.dataframe(get_tickers_by_sector(sector, merged), hide_index=True)

# --- Sector Search Dropdown ---
st.sidebar.markdown("### 🔍 Explore a Sector")
all_sectors = sorted(set(merged["GICS Sector"].dropna()))
selected_sector = st.sidebar.selectbox("Select Sector", options=all_sectors)

if selected_sector:
    st.sidebar.dataframe(get_tickers_by_sector(selected_sector, merged), hide_index=True)

# --- SIMULATOR USING S&P500 HISTORY ---
st.markdown("<h3 class='custom-font'>💰 Try Investing - Simulated $1000 Portfolio</h3>", unsafe_allow_html=True)

hist_df = pd.read_csv("data/snp500_30day.csv")
hist_df['Date'] = pd.to_datetime(hist_df['Date'], format="%m/%d/%y")

with st.form("simulator_form"):
    email = st.text_input("Enter your email")
    tickers_input = st.text_input("Enter 3 stock tickers (e.g. AAPL,MSFT,GOOGL)")

    equal_split = st.radio("How would you like to allocate $1000?", ("Split equally", "Manually specify (e.g. AAPL:300;MSFT:400;GOOGL:300)"))
    allocations_input = ""
    if equal_split == "Manually specify":
        allocations_input = st.text_input(
            "Enter allocations (e.g. AAPL:300;MSFT:400;GOOGL:300)",
            placeholder="AAPL:300;MSFT:400;GOOGL:300"
        )

    submitted = st.form_submit_button("Start Simulation")

    if submitted:
        tickers = [x.strip().upper() for x in tickers_input.split(",")]
        if len(tickers) != 3:
            st.error("Please enter exactly 3 tickers.")
        else:
            if equal_split == "Split equally":
                allocations = [1000 / 3] * 3
            else:
                try:
                    allocations = []
                    parts = allocations_input.split(";")
                    if len(parts) != 3:
                        raise ValueError("Must specify 3 allocations.")

                    for part in parts:
                        _, val = part.split(":")
                        allocations.append(float(val.strip()))
                    if sum(allocations) != 1000:
                        st.error("Allocations must sum to $1000.")
                        allocations = None
                except:
                    st.error("Invalid allocation input. Example: AAPL:300,MSFT:400,GOOGL:300")
                    allocations = None

            if allocations:
                sectors = [get_sector_for_ticker(ticker) for ticker in tickers]
                suggestion_msg, new_tickers, new_allocs = agent_portfolio_recommendation(tickers, allocations, sectors)
                if suggestion_msg:
                    st.info(f"🤖 Agentic Suggestion: {suggestion_msg}")
                    if st.button("Use suggested portfolio"):
                        tickers = new_tickers
                        allocations = new_allocs
                          
                latest_date = hist_df['Date'].max()
                start_date = hist_df['Date'].min()
                price_changes = {}
                for ticker in tickers:
                    try:
                        price_start = hist_df[(hist_df['Ticker'] == ticker) & (hist_df['Date'] == start_date)]["Close"].values[0]
                        price_end = hist_df[(hist_df['Ticker'] == ticker) & (hist_df['Date'] == latest_date)]["Close"].values[0]
                        pct_change = ((price_end - price_start) / price_start) * 100
                        price_changes[ticker] = round(pct_change, 2)
                    except:
                        price_changes[ticker] = None

                result_text = ""
                for i, ticker in enumerate(tickers):
                    result_text += f"{ticker}: ${allocations[i]} → "
                    if price_changes[ticker] is not None:
                        growth = allocations[i] * (1 + price_changes[ticker]/100)
                        result_text += f"${growth:.2f} ({price_changes[ticker]}%)\n"
                    else:
                        result_text += "Data unavailable\n"

                st.text(result_text)

                total_val = sum([
                    allocations[i] * (1 + (price_changes[ticker] or 0)/100)
                    for i, ticker in enumerate(tickers)
                ])
                success, msg = save_user_simulation(email, tickers, allocations, total_val)
                if success:
                    st.success(msg)
                else:
                    st.error(msg)

                prompt = build_portfolio_analysis_prompt(tickers, allocations, sectors)
                ai_response = query_local_model(prompt)
                st.markdown("### 🤖 AI Portfolio Analysis")
                st.markdown(ai_response)


# --- RETRIEVE PREVIOUS SIMULATION ---
st.markdown("<h3 class='custom-font'> ### 📩 Retrieve Previous Simulation", unsafe_allow_html=True)
email_to_fetch = st.text_input("Enter email to load your last simulation")
if st.button("Fetch Last Simulation"):
    sim = get_last_simulation(email_to_fetch)
    if sim is not None:
        last = sim.iloc[0]
        st.session_state.last_email = last["email"]
        st.session_state.last_tickers = last["tickers"]
        st.session_state.last_allocations = last["allocations"]
        start_date = last["date"]
        st.success("Previous simulation loaded!")

        # --- Show Portfolio Performance Today ---
        st.markdown("<h3 class='custom-font'>📈 Portfolio Performance Today</h3>", unsafe_allow_html=True)
        try:
            tickers = [x.strip().upper() for x in last["tickers"].split(",")]
            allocations = [float(a) for a in last["allocations"].split(",")]

            result, total = evaluate_virtual_portfolio(tickers, allocations, start_date)
            if result is not None:
                df_result = pd.DataFrame.from_dict(result, orient="index").reset_index().rename(columns={"index": "Ticker"})
                st.dataframe(df_result, use_container_width=True)
                st.markdown(f"<p class='custom-font'><b>Total Value:</b> ${total:.2f}</p>", unsafe_allow_html=True)
            else:
                st.info("No portfolio evaluation available.")

            # --- AI Portfolio Analysis ---
            sectors = [get_sector_for_ticker(t) for t in tickers]
            prompt = build_portfolio_analysis_prompt(tickers, allocations, sectors)
            ai_response = query_local_model(prompt)

            st.markdown("### 🤖 AI Portfolio Analysis")
            st.markdown(ai_response)

        except Exception as e:
            st.warning(f"⚠️ Unable to evaluate portfolio: {e}")

    else:
        st.warning("No previous simulation found for this email.")
