from fastapi import FastAPI
from engine import get_data, generate_signal
import threading
import time
import requests

app = FastAPI()

signals = []

BASE_URL = " https://trading-signal-bot-7bb3.onrender.com" # 🔥 replace this

@app.get("/")
def home():
    return {"status": "Auto bot running"}

@app.get("/run")
def run_engine():
    try:
        df = get_data("EUR/USD", "15min", 50)

        if df is None:
            return {"error": "No market data"}

        signal = generate_signal(df)

        if signal:
            signals.append(signal)
            return {"new_signal": signal}

        return {"status": "no signal"}

    except Exception as e:
        return {"error": str(e)}

@app.get("/signals")
def get_signals():
    return signals


# 🔥 AUTO LOOP
def auto_runner():
    while True:
        try:
            requests.get(BASE_URL + "/run")
        except:
            pass

        time.sleep(300)  # runs every 5 minutes


# 🔥 START BACKGROUND THREAD
threading.Thread(target=auto_runner, daemon=True).start()
