import os
import json
import logging
from datetime import datetime, timedelta

import uvicorn
from fastapi import FastAPI

# --- LOGGING SETUP ---
logging.basicConfig(level=logging.INFO)

# --- ALIGNED IMPORT ---
# We use 'run_trading_bot' to match your engine's logic
try:
    from engine import run_trading_bot
except ImportError as e:
    logging.error(f"CRITICAL ERROR: Could not import engine.py correctly. Details: {e}")
    run_trading_bot = None

app = FastAPI()
DB_FILE = "db.json"

# --- CONFIG ---
# Daily signals are valid for 24 hours (1440 mins) per strategy rules
EXPIRY_MINUTES = 1440  

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
    status = "Online" if run_trading_bot else "Offline (Import Error)"
    return {"status": "Bot running", "engine_status": status}

@app.get("/run")
def run_engine():
    if not run_trading_bot:
        return {"error": "Engine function 'run_trading_bot' not found. Check engine.py."}

    logging.info("Professional Scanner Triggered...")
    db = load_db()
    active = db.get("active", [])
    history = db.get("history", [])

    # ===============================
    # GENERATE SIGNALS (run_trading_bot)
    # ===============================
    try:
        # This executes your Daily Chore and 4H Fake Breakout logic
        new_signals = run_trading_bot() 
    except Exception as e:
        logging.error(f"ENGINE CRASH during scan: {e}")
        return {"error": f"Logic error: {e}"}

    # ===============================
    # ADD NEW SIGNALS (NO DUPLICATES)
    # ===============================
    if new_signals:
        for new in new_signals:
            # Prevent duplicate signals for the same pair/strategy combination
            exists = any(
                s["pair"] == new["pair"]
                and s.get("strategy") == new.get("strategy")
                and s.get("side") == new.get("side")
                for s in active
            )

            if not exists:
                new["created_at"] = datetime.utcnow().isoformat()
                new["status"] = "PENDING"
                active.append(new)

    # ===============================
    # CLEANUP & EXPIRY
    # ===============================
    now = datetime.utcnow()
    final_active = []

    for s in active:
        try:
            created = datetime.fromisoformat(s["created_at"])
        except:
            created = now

        # Expire signals after 24 hours per Strategy Rules
        if now - created > timedelta(minutes=EXPIRY_MINUTES):
            s["status"] = "EXPIRED"
            history.append(s)
        else:
            final_active.append(s)

    db["active"], db["history"] = final_active, history
    save_db(db)

    logging.info(f"Scan complete. Active Signals: {len(final_active)}")

    return {
        "active_signals": db["active"],
        "history_count": len(db["history"])
    }

@app.get("/signals")
def get_signals():
    return load_db()["active"]

@app.get("/health")
def health():
    db = load_db()
    return {
        "engine_ready": run_trading_bot is not None,
        "active_count": len(db.get("active", [])),
        "history_count": len(db.get("history", []))
    }

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=10000)
