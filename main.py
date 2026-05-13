import os
import logging
import asyncio
import uvicorn
from fastapi import FastAPI
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from engine import run_trading_bot, update_signal_status

app = FastAPI()
logging.basicConfig(level=logging.INFO)

ACTIVE_SIGNALS = []

async def scan():
    global ACTIVE_SIGNALS
    logging.info("Starting Scan...")
    
    # Update Status
    ACTIVE_SIGNALS = update_signal_status(ACTIVE_SIGNALS)
    
    # Get New
    new_found = run_trading_bot()
    for n in new_found:
        if not any(s['pair'] == n['pair'] and s['strategy'] == n['strategy'] for s in ACTIVE_SIGNALS):
            n["status"] = "PENDING"
            ACTIVE_SIGNALS.append(n)
            logging.info(f"New Signal: {n}")

@app.on_event("startup")
async def startup():
    scheduler = AsyncIOScheduler()
    scheduler.add_job(scan, "interval", minutes=5)
    scheduler.start()

@app.get("/signals")
def get_signals():
    return ACTIVE_SIGNALS

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run(app, host="0.0.0.0", port=port)
