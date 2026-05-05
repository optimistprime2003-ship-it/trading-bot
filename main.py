import os
import json
import logging
from datetime import datetime, timedelta

import uvicorn
from fastapi import FastAPI

# --- LOGGING SETUP ---
logging.basicConfig(level=logging.INFO)

# --- DEFENSIVE IMPORT ---
try:
    from engine import generate_signals, update_signal_status
except ImportError as e:
    logging.error(f"CRITICAL ERROR: Could not import engine.py. Details: {e}")
    generate_signals = None
    update_signal_status = None

app = FastAPI()
DB_FILE = "db.json"

# --- CONFIG ---
EXPIRY_MINUTES = 1440  # 3 hours expiry for trades

# ==========================================
# DATABASE FUNCTIONS
# ==========================================
def load_db():
    if not os.path.exists(DB_FILE):
        initial_data = {"active": [], "history": []}
        save_db(initial_data)
        return initial_data
    try:
        with open(DB_FILE, "r") as f:
            return json.load(f)
    except Exception as e:
        logging.error(f"DB Read Error: {e}")
        return {"active": [], "history": []}


def save_db(data):
    try:
        with open(DB_FILE, "w") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        logging.error(f"Disk Write Error: {e}")


# ==========================================
# ROUTES
# ==========================================

@app.get("/")
def home():
    status = "Online" if generate_signals else "Offline (Engine Error)"
    return {"status": "Bot running", "engine_status": status}


@app.get("/run")
def run_engine():
    if not generate_signals:
        return {"error": "Engine is not loaded correctly. Check logs."}

    logging.info("Engine triggered...")

    db = load_db()
    active = db.get("active", [])
    history = db.get("history", [])

    # ===============================
    # GENERATE SIGNALS (SAFE EXECUTION)
    # ===============================
    try:
        new_signals = generate_signals()
    except Exception as e:
        logging.error(f"ENGINE CRASH: {e}")
        return {"error": "Engine crashed. Check logs."}

    # ===============================
    # ADD NEW SIGNALS (NO DUPLICATES)
    # ===============================
    if new_signals:
        for new in new_signals:
            exists = any(
                s["pair"] == new["pair"]
                and s.get("strategy") == new.get("strategy")
                and s.get("type") == new.get("type")
                and s.get("entry") == new.get("entry")
                for s in active
            )

            if not exists:
                new["created_at"] = datetime.utcnow().isoformat()
                active.append(new)

    # ===============================
    # UPDATE SIGNAL STATUS
    # ===============================
    if update_signal_status:
        try:
            updated = update_signal_status(active)
        except Exception as e:
            logging.error(f"UPDATE ERROR: {e}")
            updated = active
    else:
        updated = active

    # ===============================
    # EXPIRY CHECK
    # ===============================
    now = datetime.utcnow()
    final_active = []

    for s in updated:
        try:
            created = datetime.fromisoformat(s["created_at"])
        except:
            created = now

        # Expire old trades
        if now - created > timedelta(minutes=EXPIRY_MINUTES):
            s["status"] = "EXPIRED"

        if s.get("status") in ["TP HIT", "SL HIT", "EXPIRED"]:
            history.append(s)
        else:
            final_active.append(s)

    db["active"], db["history"] = final_active, history
    save_db(db)

    logging.info(f"Run complete. Active: {len(final_active)} | History: {len(history)}")

    return {
        "active": db["active"],
        "history_preview": db["history"][-5:]
    }


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
            strategy_stats[strat] = {"wins": 0, "losses": 0}

        if s.get("status") == "TP HIT":
            strategy_stats[strat]["wins"] += 1
        elif s.get("status") == "SL HIT":
            strategy_stats[strat]["losses"] += 1

    return {
        "total_trades": total,
        "wins": wins,
        "losses": losses,
        "win_rate": round(win_rate, 2),
        "by_strategy": strategy_stats
    }


@app.get("/health")
def health():
    db = load_db()
    return {
        "engine_loaded": generate_signals is not None,
        "active_signals": len(db.get("active", [])),
        "history_count": len(db.get("history", []))
    }


# ==========================================
# RUN SERVER (LOCAL ONLY)
# ==========================================
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=10000)
