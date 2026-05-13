import os
import json
import logging
import asyncio
from datetime import datetime, timedelta

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# Import the engine we built earlier
try:
    from engine import run_trading_bot, update_signal_status
except ImportError as e:
    logging.error(f"ENGINE IMPORT ERROR: {e}")
    run_trading_bot = None
    update_signal_status = None

app = FastAPI()
logging.basicConfig(level=logging.INFO)

# Database Setup
DB_FILE = "/opt/render/project/src/db.json" if os.path.exists("/opt/render/project/src/") else "db.json"
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
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except:
                self.disconnect(connection)

manager = ConnectionManager()

# =========================
# DATABASE HANDLERS
# =========================
def load_db():
    if not os.path.exists(DB_FILE):
        return {"active": [], "history": []}
    try:
        with open(DB_FILE, "r") as f:
            return json.load(f)
    except Exception:
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
    if not run_trading_bot: return

    logging.info("RUNNING SIGNAL SCAN")
    db = load_db()

    # 1. Update Existing
    if update_signal_status:
        db["active"] = update_signal_status(db.get("active", []))

    # 2. Get New Signals
    try:
        new_signals = run_trading_bot()
    except Exception as e:
        logging.error(f"SCAN ERROR: {e}")
        return

    # 3. Add New Signals
    for new in new_signals:
        exists = any(
            s.get("pair") == new.get("pair") and 
            s.get("strategy") == new.get("strategy") and 
            s.get("side") == new.get("side") 
            for s in db["active"]
        )

        if not exists:
            new["created_at"] = datetime.utcnow().isoformat()
            new["status"] = "PENDING"
            db["active"].append(new)
            await manager.broadcast({"type": "NEW_SIGNAL", "data": new})

    # 4. Handle Expiry and History
    now = datetime.utcnow()
    still_active = []
    
    for s in db["active"]:
        created = datetime.fromisoformat(s["created_at"])
        if s["status"] in ["TP HIT", "SL HIT"] or (now - created > timedelta(minutes=EXPIRY_MINUTES)):
            s["status"] = "EXPIRED" if s["status"] == "PENDING" else s["status"]
            db["history"].append(s)
            await manager.broadcast({"type": "SIGNAL_CLOSED", "data": s})
        else:
            still_active.append(s)

    db["active"] = still_active
    save_db(db)

# =========================
# SCHEDULER & STARTUP
# =========================
@app.on_event("startup")
async def startup_event():
    scheduler = AsyncIOScheduler()
    scheduler.add_job(execute_scan, "interval", minutes=5)
    scheduler.start()

# =========================
# ROUTES (API & FRONTEND)
# =========================
@app.get("/")
def serve_dashboard():
    """Serves the frontend dashboard from index.html"""
    try:
        with open("index.html", "r") as f:
            return HTMLResponse(content=f.read(), status_code=200)
    except FileNotFoundError:
        return HTMLResponse(content="<h1>Error: index.html not found!</h1>", status_code=404)

@app.get("/signals")
def get_signals():
    return load_db().get("active", [])

@app.get("/history")
def get_history():
    return load_db().get("history", [])

@app.get("/stats")
def get_stats():
    """Calculates win rates and performance metrics dynamically"""
    history = load_db().get("history", [])
    
    stats = {
        "overall": {"total_trades": 0, "wins": 0, "losses": 0, "win_rate": 0},
        "by_strategy": {}
    }
    
    for s in history:
        strat = s.get("strategy", "Unknown")
        status = s.get("status", "")
        
        if strat not in stats["by_strategy"]:
            stats["by_strategy"][strat] = {"total": 0, "wins": 0, "losses": 0, "win_rate": 0}
            
        if status in ["TP HIT", "SL HIT"]:
            stats["overall"]["total_trades"] += 1
            stats["by_strategy"][strat]["total"] += 1
            
            if status == "TP HIT":
                stats["overall"]["wins"] += 1
                stats["by_strategy"][strat]["wins"] += 1
            else:
                stats["overall"]["losses"] += 1
                stats["by_strategy"][strat]["losses"] += 1

    # Calculate Percentages
    if stats["overall"]["total_trades"] > 0:
        stats["overall"]["win_rate"] = round((stats["overall"]["wins"] / stats["overall"]["total_trades"]) * 100, 1)
        
    for k, v in stats["by_strategy"].items():
        if v["total"] > 0:
            v["win_rate"] = round((v["wins"] / v["total"]) * 100, 1)
            
    return stats

@app.websocket("/ws/signals")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run(app, host="0.0.0.0", port=port)
