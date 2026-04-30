from engine import backtest_strategy
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from engine import generate_signals, update_signal_status
import threading
import time
import requests

app = FastAPI()

# ✅ CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

signals = []
history = []

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
                signals = [s for s in signals if s["pair"] != new["pair"]]
                signals.append(new)

            return {"new_signals": new_signals}

        return {"status": "no signal"}

    except Exception as e:
        return {"error": str(e)}


@app.get("/signals")
def get_signals():
    global signals, history

    updated = update_signal_status(signals)

    active = []
    for s in updated:
        if s["status"] == "ACTIVE":
            active.append(s)
        else:
            history.append(s)

    signals = active

    return sorted(signals, key=lambda x: x["pair"])


@app.get("/history")
def get_history():
    return history


@app.get("/stats")
def get_stats():
    wins = sum(1 for h in history if h["status"] == "TP HIT")
    losses = sum(1 for h in history if h["status"] == "SL HIT")

    total = wins + losses
    win_rate = (wins / total * 100) if total > 0 else 0

    return {
        "wins": wins,
        "losses": losses,
        "total": total,
        "win_rate": round(win_rate, 2)
    }


# 🔄 AUTO RUN
def auto_runner():
    while True:
        try:
            requests.get(BASE_URL + "/run")
        except:
            pass

        time.sleep(300)


threading.Thread(target=auto_runner, daemon=True).start()
@app.get("/backtest")
def run_backtest(pair: str = "EUR/USD"):
    return backtest_strategy(pair)


