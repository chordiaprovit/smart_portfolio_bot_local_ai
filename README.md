# 📊 Smart Portfolio Bot (Local)

**Smart Portfolio Bot** is a local, agentic AI–powered stock portfolio simulator that helps investors analyze and optimize their investment strategies.  
It combines **financial data analysis**, **simulation models**, and **AI insights** to make portfolio management simple, interactive, and educational.  

---

## 🚀 Features

- **📈 Portfolio Simulation**
  - Monte Carlo simulation for return projections  
  - ARIMA-based price forecasting  
  - Scenario testing (e.g., “What if market stays the same?”)  

- **🤖 Agentic AI**
  - Conversational stock assistant (local LLM integration)  
  - Personalized insights (e.g., correlation > 0.85 triggers diversification suggestion)  
  - AI risk lab for identifying portfolio strengths/weaknesses  

- **📊 Market Analysis**
  - S&P 500 sector performance snapshots  
  - Gainers & losers analysis  
  - Historical price visualizations  

- **💾 Data Management**
  - Save & retrieve previous simulations  
  - Local data storage (`CSV` / `Parquet`)  
  - Daily updates via GitHub Actions  

- **🖥️ Interactive UI**
  - Built with [Streamlit](https://streamlit.io/)  
  - Sector explorer with expanders and line charts  
  - KPI cards (Sharpe Ratio, Returns, Risk Verdicts)  

---

## 🛠️ Tech Stack

- **Frontend/UI:** Streamlit, Plotly  
- **Data Analysis:** Pandas, NumPy, Scikit-learn, Statsmodels  
- **AI/LLM Integration:** LangChain, Local LLMs (Ollama, GPT4All)  
- **Backend/Automation:** Python, GitHub Actions  
- **Visualization:** Correlation heatmaps, diversification charts  

---

## 📂 Project Structure

```
smart_portfolio_bot_local/
│── app.py                     # Main Streamlit app
│── portfolio_simulator.py      # Monte Carlo & ARIMA simulations
│── portfolio_analyzer.py       # AI-powered analysis
│── agent_runner.py             # Agentic AI orchestration
│── screener.py                 # Sector/ticker screening utilities
│── sector_snapshot.py          # Sector performance snapshots
│── data_saver.py               # Save/retrieve user simulations
│── requirements.txt            # Python dependencies
│── data/                       # Historical market datasets
│── ui/                         # Streamlit UI components
│    └── tabs_ai_risk_lab.py    # Risk lab tab
```

---

## ⚡ Installation

```bash

# Create virtual environment
python -m venv venv
source venv/bin/activate   # (Linux/Mac)
venv\Scripts\activate      # (Windows)

# Install dependencies
pip install -r requirements.txt
```

---

## ▶️ Usage

Run the Streamlit app locally:

```bash
streamlit run app.py
```

Then open [http://localhost:8501](http://localhost:8501) in your browser.  

---

## 📌 Roadmap

- [ ] Add **real-time data fetch** (Yahoo Finance / Alpha Vantage APIs)  
- [ ] Integrate **economic indicator simulation** (GDP, CPI, Interest Rates)  
- [ ] Improve **AI explanations** with chain-of-thought agents  
- [ ] Support **multi-portfolio comparison**  
- [ ] Deploy to **Streamlit Cloud** for public demo  

---

## 🤝 Contributing

Contributions are welcome!  
1. Fork the repo  
2. Create a feature branch  
3. Submit a pull request  


