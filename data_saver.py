import os
import pandas as pd
from datetime import datetime
from os.path import exists, getsize

DATA_DIR = "data"
CSV_FILE = os.path.join(DATA_DIR, "portfolio_records.csv")
os.makedirs(DATA_DIR, exist_ok=True)

def save_user_simulation(email, tickers, allocations, total_value):
    today = datetime.today().strftime("%Y-%m-%d")
    new_entry = {
        "email": email,
        "date": today,
        "tickers": ','.join(tickers),
        "allocations": ','.join(str(a) for a in allocations),
        "total_value": round(total_value, 2)
    }

    if exists(CSV_FILE):
        df = pd.read_csv(CSV_FILE)
        # Check if an entry already exists for the email and today's date
        if ((df["email"] == email) & (df["date"] == today)).any():
            return False, "A simulation already exists for this email today. Please retrieve it instead."
        df = pd.concat([df, pd.DataFrame([new_entry])], ignore_index=True)
    else:
        df = pd.DataFrame([new_entry])

    df.to_csv(CSV_FILE, index=False)
    return True, "Simulation saved successfully."

def get_last_simulation(email):
    if os.path.exists(CSV_FILE):
        df = pd.read_csv(CSV_FILE)
        if "email" not in df.columns:
            return None  # or raise a clear error
        user_df = df[df["email"] == email]
        if not user_df.empty:
            return user_df.tail(1)
    return None
