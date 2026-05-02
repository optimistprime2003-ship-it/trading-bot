from fastapi import FastAPI
from engine import generate_signals, update_signal_status
import datetime

app = FastAPI()

# 🔹 STORAGE
active_signals = []
history_signals = []


# 🔹 HOME
@app.get("/")
def home():
    return {"status": "Bot running"}


# 🔹 RUN ENGINE
@app.get("/run")
def run_engine():
    global active_signals, history_signals

    try:
        new_signals = generate_signals()

        # ✅ ADD ONLY NEW SIGNALS (avoid duplicates)
        for new in new_signals:
            if not any(
                s["pair"] == new["pair"] and s["time"] == new["time"]
                for s in active_signals
            ):
                active_signals.append(new)

        # 🔄 UPDATE STATUS (TP / SL / EXPIRED)
        updated = update_signal_status(active_signals)

        still_active = []

        for s in updated:
            if s["status"] in ["TP HIT", "SL HIT", "EXPIRED"]:
                history_signals.append(s)
            else:
                still_active.append(s)

        active_signals = still_active

        return {
            "active": active_signals,
            "history": history_signals[-20:]
        }

    except Exception as e:
        return {"error": str(e)}


# 🔹 GET ACTIVE SIGNALS
@app.get("/signals")
def get_signals():
    return active_signals


# 🔹 GET HISTORY
@app.get("/history")
def get_history():
    return history_signals[-50:]


# 🔹 GET STATS (REAL)
@app.get("/stats")
def get_stats():
    wins = sum(1 for s in history_signals if s["status"] == "TP HIT")
    losses = sum(1 for s in history_signals if s["status"] == "SL HIT")
    total = wins + losses

    win_rate = (wins / total * 100) if total > 0 else 0

    return {
        "total_trades": total,
        "wins": wins,
        "losses": losses,
        "win_rate": round(win_rate, 2)
    }
