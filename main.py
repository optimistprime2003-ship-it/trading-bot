from fastapi import FastAPI
from engine import generate_signals
import threading
import time
import requests

app = FastAPI()

signals = []

# 🔥 REPLACE THIS WITH YOUR REAL RENDER LINK
BASE_URL = "https://YOUR-APP-NAME.onrender.com"


@app.get("/")
def home():
    return {"status": "Auto bot running (advanced)"}


@app.get("/run")
def run_engine():
    try:
        new_signals = generate_signals()

        if new_signals:
            signals.extend(new_signals)
            return {"new_signals": new_signals}

        return {"status": "no signal"}

    except Exception as e:
        return {"error": str(e)}


@app.get("/signals")
def get_signals():
    return signals


# 🔥 AUTO BOT LOOP (runs every 5 minutes)
def auto_runner():
    while True:
        try:
            requests.get(BASE_URL + "/run")
        except:
            pass

        time.sleep(300)  # 5 minutes


# 🔥 START AUTO BOT
threading.Thread(target=auto_runner, daemon=True).start()
