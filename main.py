import os
import json
import uvicorn
from fastapi import FastAPI

# --- DEFENSIVE IMPORT ---
# This prevents the whole app from crashing if engine.py has a syntax error
try:
    from engine import generate_signals, update_signal_status
except ImportError as e:
    print(f"CRITICAL ERROR: Could not import engine.py. Details: {e}")
    generate_signals = None
    update_signal_status = None

app = FastAPI()
DB_FILE = "db.json"

def load_db():
    if not os.path.exists(DB_FILE):
        initial_data = {"active": [], "history": []}
        save_db(initial_data)
        return initial_data
    try:
        with open(DB_FILE, "r") as f:
            return json.load(f)
    except:
        return {"active": [], "history": []}

def save_db(data):
    try:
        with open(DB_FILE, "w") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"Disk Write Error: {e}")

@app.get("/")
def home():
    status = "Online" if generate_signals else "Offline (Engine Error)"
    return {"status": "Bot running", "engine_status": status}

@app.get("/run")
def run_engine():
    if not generate_signals:
        return {"error": "Engine is not loaded correctly. Check Render logs."}
        
    db = load_db()
    active = db.get("active", [])
    history = db.get("history", [])

    # The updated engine uses Twelve Data + Alpha Vantage backup
    new_signals = generate_signals()

    if new_signals:
        for new in new_signals:
            if not any(s["pair"] == new["pair"] and s["strategy"] == new.get("strategy") and s["type"] == new.get("type") for s in active):
                active.append(new)

    if update_signal_status:
        updated = update_signal_status(active)
        still_active = []
        for s in updated:
            if s.get("status") in ["TP HIT", "SL HIT", "EXPIRED"]:
                history.append(s)
            else:
                still_active.append(s)
        
        db["active"], db["history"] = still_active, history
        save_db(db)

    return {"active": db["active"], "history_preview": db["history"][-5:]}

@app.get("/signals")
def get_signals():
    return load_db()["active"]

@app.get("/history")
def get_history():
    return load_db()["history"][-50:]

@app.get("/stats")
def get_stats():
    db = load_db()
    history = db["history"]
    wins = sum(1 for s in history if s.get("status") == "TP HIT")
    losses = sum(1 for s in history if s.get("status") == "SL HIT")
    total = wins + losses
    win_rate = (wins / total * 100) if total > 0 else 0

    strategy_stats = {}
    for s in history:
        strat = s.get("strategy", "Unknown")
        if strat not in strategy_stats:
            strategy_stats[strat] = {"wins": 0, "losses": 0, "total": 0}
        if s.get("status") == "TP HIT":
            strategy_stats[strat]["wins"] += 1
            strategy_stats[strat]["total"] += 1
        elif s.get("status") == "SL HIT":
            strategy_stats[strat]["losses"] += 1
            strategy_stats[strat]["total"] += 1

    for strat in strategy_stats:
        total_s = strategy_stats[strat]["total"]
        strategy_stats[strat]["win_rate"] = round((strategy_stats[strat]["wins"] / total_s * 100) if total_s > 0 else 0, 2)

    return {
        "overall": {"total_trades": total, "wins": wins, "losses": losses, "win_rate": round(win_rate, 2)},
        "by_strategy": strategy_stats
    }

# --- RENDER PORT BINDING ---
if __name__ == "__main__":
    # Render assigns a port dynamically via environment variables
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run(app, host="0.0.0.0", port=port)
