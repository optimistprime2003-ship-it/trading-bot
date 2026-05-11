import os
import json
import logging
import asyncio
from datetime import datetime, timedelta

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from apscheduler.schedulers.background import BackgroundScheduler

# =========================
# IMPORT ENGINE
# =========================
try:
    from engine import run_trading_bot, update_signal_status
except ImportError as e:
    logging.error(f"IMPORT ERROR: {e}")
    run_trading_bot = None
    update_signal_status = None

# =========================
# APP SETUP
# =========================
app = FastAPI()
logging.basicConfig(level=logging.INFO)

DB_FILE = "db.json"
EXPIRY_MINUTES = 1440

# =========================
# WEBSOCKET MANAGER
# =========================
class ConnectionManager:
    def __init__(self):
        self.active_connections = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        disconnected = []

        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except:
                disconnected.append(connection)

        for d in disconnected:
            self.disconnect(d)

manager = ConnectionManager()

# =========================
# DATABASE
# =========================
def load_db():
    if not os.path.exists(DB_FILE):
        data = {"active": [], "history": []}
        save_db(data)
        return data

    try:
        with open(DB_FILE, "r") as f:
            return json.load(f)
    except Exception as e:
        logging.error(f"DB LOAD ERROR: {e}")
        return {"active": [], "history": []}

def save_db(data):
    try:
        with open(DB_FILE, "w") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        logging.error(f"DB SAVE ERROR: {e}")

# =========================
# ENGINE EXECUTION
# =========================
async def execute_scan():
    if not run_trading_bot:
        logging.error("ENGINE NOT AVAILABLE")
        return

    logging.info("RUNNING SIGNAL SCAN")

    db = load_db()
    active = db.get("active", [])
    history = db.get("history", [])

    # =========================
    # UPDATE EXISTING SIGNALS
    # =========================
    if update_signal_status:
        try:
            active = update_signal_status(active)
        except Exception as e:
            logging.error(f"STATUS UPDATE ERROR: {e}")

    # =========================
    # GENERATE NEW SIGNALS
    # =========================
    try:
        new_signals = run_trading_bot()
    except Exception as e:
        logging.error(f"SCAN ERROR: {e}")
        return

    # =========================
    # ADD SIGNALS
    # =========================
    for new in new_signals:

        exists = any(
            s.get("pair") == new.get("pair")
            and s.get("strategy") == new.get("strategy")
            and s.get("side") == new.get("side")
            and s.get("status") == "PENDING"
            for s in active
        )

        if not exists:

            new["created_at"] = datetime.utcnow().isoformat()
            new["status"] = "PENDING"

            active.append(new)

            # =========================
            # REALTIME SIGNAL DELIVERY
            # =========================
            await manager.broadcast({
                "type": "NEW_SIGNAL",
                "data": new
            })

            logging.info(f"NEW SIGNAL SENT: {new}")

    # =========================
    # EXPIRY HANDLER
    # =========================
    now = datetime.utcnow()
    final_active = []

    for s in active:

        try:
            created = datetime.fromisoformat(s["created_at"])
        except:
            created = now

        if now - created > timedelta(minutes=EXPIRY_MINUTES):
            s["status"] = "EXPIRED"
            history.append(s)

            await manager.broadcast({
                "type": "SIGNAL_EXPIRED",
                "data": s
            })

        elif s["status"] in ["TP HIT", "SL HIT"]:

            history.append(s)

            await manager.broadcast({
                "type": "SIGNAL_CLOSED",
                "data": s
            })

        else:
            final_active.append(s)

    db["active"] = final_active
    db["history"] = history

    save_db(db)

    logging.info(f"SCAN COMPLETE | ACTIVE: {len(final_active)}")

# =========================
# BACKGROUND SCHEDULER
# =========================
scheduler = BackgroundScheduler()

scheduler.add_job(
    lambda: asyncio.run(execute_scan()),
    "interval",
    minutes=5
)

scheduler.start()

# =========================
# ROUTES
# =========================
@app.get("/")
def home():
    return {
        "status": "online",
        "engine": run_trading_bot is not None
    }

@app.get("/signals")
def get_signals():
    return load_db()["active"]

@app.get("/history")
def get_history():
    return load_db()["history"]

@app.get("/health")
def health():
    db = load_db()

    return {
        "engine_ready": run_trading_bot is not None,
        "active_signals": len(db["active"]),
        "history_signals": len(db["history"]),
        "websocket_clients": len(manager.active_connections)
    }

@app.get("/run")
async def manual_run():
    await execute_scan()
    return {"message": "Scan completed"}

# =========================
# WEBSOCKET ENDPOINT
# =========================
@app.websocket("/ws/signals")
async def websocket_endpoint(websocket: WebSocket):

    await manager.connect(websocket)

    try:
        while True:
            await websocket.receive_text()

    except WebSocketDisconnect:
        manager.disconnect(websocket)

# =========================
# START SERVER
# =========================
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=10000)
