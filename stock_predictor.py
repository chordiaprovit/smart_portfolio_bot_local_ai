import yfinance as yf
import pandas as pd
from sklearn.linear_model import LinearRegression
import numpy as np

def predict_next_price(ticker, days=7):
    data = yf.download(ticker, period="60d", interval="1d")["Adj Close"].dropna()
    if len(data) < 10:
        return None, "Not enough data to forecast."

    df = pd.DataFrame(data).reset_index()
    df["day"] = np.arange(len(df))
    
    model = LinearRegression()
    model.fit(df[["day"]], df["Adj Close"])
    
    next_day = len(df) + days - 1
    predicted_price = model.predict([[next_day]])[0]

    return round(predicted_price, 2), None
