from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from engine import generate_signals
import threading
import time
import requests

app = FastAPI()

# ✅ FIX CORS (VERY IMPORTANT)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

signals = []

# 🔴 REPLACE WITH YOUR REAL RENDER URL
BASE_URL = "https://trading-signal-bot-7bb3.onrender.com"


@app.get("/")
def home():
    return {"status": "Bot running"}


@app.get("/run")
def run_engine():
    global signals

    try:
        new_signals = generate_signals()

        if new_signals:
            for new in new_signals:
                # remove old signal for same pair
                signals = [s for s in signals if s["pair"] != new["pair"]]
                signals.append(new)

            return {"new_signals": new_signals}

        return {"status": "no signal"}

    except Exception as e:
        return {"error": str(e)}


@app.get("/signals")
def get_signals():
    return signals if signals else []


# 🔄 AUTO RUN EVERY 5 MINUTES
def auto_runner():
    while True:
        try:
            requests.get(BASE_URL + "/run")
        except:
            pass

        time.sleep(300)


threading.Thread(target=auto_runner, daemon=True).start()
