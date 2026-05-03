from fastapi import FastAPI
from engine import generate_signals, update_signal_status
import json
import os

app = FastAPI()

DB_FILE = "db.json"


# ===============================
# LOAD DATABASE
# ===============================
def load_db():
    if not os.path.exists(DB_FILE):
        return {"active": [], "history": []}

    with open(DB_FILE, "r") as f:
        return json.load(f)


# ===============================
# SAVE DATABASE
# ===============================
def save_db(data):
    with open(DB_FILE, "w") as f:
        json.dump(data, f, indent=2)


# ===============================
# HOME
# ===============================
@app.get("/")
def home():
    return {"status": "Bot running"}


# ===============================
# RUN ENGINE
# ===============================
@app.get("/run")
def run_engine():

    db = load_db()
    active = db["active"]
    history = db["history"]

    new_signals = generate_signals()

    # Prevent duplicates
    for new in new_signals:
        if not any(
            s["pair"] == new["pair"]
            and s["strategy"] == new["strategy"]
            and s["time"] == new["time"]
            for s in active
        ):
            active.append(new)

    # Update signal status
    updated = update_signal_status(active)

    still_active = []

    for s in updated:
        if s["status"] in ["TP HIT", "SL HIT", "EXPIRED"]:
            history.append(s)
        else:
            still_active.append(s)

    db["active"] = still_active
    db["history"] = history

    save_db(db)

    return {
        "active": still_active,
        "history": history[-20:]
    }


# ===============================
# GET ACTIVE SIGNALS
# ===============================
@app.get("/signals")
def get_signals():
    db = load_db()
    return db["active"]


# ===============================
# GET HISTORY
# ===============================
@app.get("/history")
def get_history():
    db = load_db()
    return db["history"][-50:]


# ===============================
# STATS (OVERALL + PER STRATEGY)
# ===============================
@app.get("/stats")
def get_stats():
    db = load_db()
    history = db["history"]

    # ===============================
    # OVERALL STATS
    # ===============================
    wins = sum(1 for s in history if s["status"] == "TP HIT")
    losses = sum(1 for s in history if s["status"] == "SL HIT")
    total = wins + losses

    win_rate = (wins / total * 100) if total > 0 else 0

    overall = {
        "total_trades": total,
        "wins": wins,
        "losses": losses,
        "win_rate": round(win_rate, 2)
    }

    # ===============================
    # PER STRATEGY STATS
    # ===============================
    strategy_stats = {}

    for s in history:
        strat = s.get("strategy", "Unknown")

        if strat not in strategy_stats:
            strategy_stats[strat] = {
                "wins": 0,
                "losses": 0,
                "total": 0
            }

        if s["status"] == "TP HIT":
            strategy_stats[strat]["wins"] += 1
            strategy_stats[strat]["total"] += 1

        elif s["status"] == "SL HIT":
            strategy_stats[strat]["losses"] += 1
            strategy_stats[strat]["total"] += 1

    # Calculate win rate per strategy
    for strat in strategy_stats:
        wins_s = strategy_stats[strat]["wins"]
        total_s = strategy_stats[strat]["total"]

        strategy_stats[strat]["win_rate"] = round(
            (wins_s / total_s * 100) if total_s > 0 else 0, 2
        )

    return {
        "overall": overall,
        "by_strategy": strategy_stats
    }
