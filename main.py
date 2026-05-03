from fastapi import FastAPI
from engine import generate_signals, update_signal_status
import json
import os

app = FastAPI()

DB_FILE = "db.json"

def load_db():
    if not os.path.exists(DB_FILE):
        return {"active": [], "history": []}
    with open(DB_FILE, "r") as f:
        return json.load(f)

def save_db(data):
    with open(DB_FILE, "w") as f:
        json.dump(data, f)

@app.get("/")
def home():
    return {"status": "Bot running"}

@app.get("/run")
def run_engine():
    db = load_db()

    new_signals = generate_signals()
    db["active"].extend(new_signals)

    updated = update_signal_status(db["active"])

    active = []
    for s in updated:
        if s["status"] in ["TP HIT", "SL HIT", "EXPIRED"]:
            db["history"].append(s)
        else:
            active.append(s)

    db["active"] = active
    save_db(db)

    return db

@app.get("/signals")
def signals():
    return load_db()["active"]

@app.get("/history")
def history():
    return load_db()["history"]
