import os
import json
import logging
import threading
import time
from datetime import datetime

import uvicorn
from fastapi import FastAPI
from fastapi.responses import HTMLResponse

import engine

logging.basicConfig(level=logging.INFO)

app = FastAPI()

# --- STORAGE ---
DB_FILE = "data.json"

# --- SCANNER SETTINGS ---
SCAN_INTERVAL = 300  # 5 minutes
last_scan_time = "Never"
last_scan_result = "No scans yet"


def load_data():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r") as f:
                db = json.load(f)

            stats = {"wins": 0, "total": 0, "pairs": {}}
            history = db.get("history", [])

            for s in history:
                symbol = s.get('symbol', 'UNKNOWN')
                strat = s.get('strat', '')

                stats["total"] += 1

                if symbol not in stats["pairs"]:
                    stats["pairs"][symbol] = {
                        "wins": 0,
                        "total": 0
                    }

                stats["pairs"][symbol]["total"] += 1

                if any(x in strat for x in ["Daily", "Pin Bar", "H4", "Breakout", "5M"]):
                    stats["wins"] += 1
                    stats["pairs"][symbol]["wins"] += 1

            db["staffs"] = stats
            return db

        except Exception as e:
            logging.error(f"Load Error: {e}")

    return {
        "active": [],
        "history": [],
        "staffs": {
            "wins": 0,
            "total": 0,
            "pairs": {}
        }
    }


def save_data(data):
    try:
        to_save = {
            "active": data.get("active", []),
            "history": data.get("history", [])
        }

        with open(DB_FILE, "w") as f:
            json.dump(to_save, f, indent=2)

    except Exception as e:
        logging.error(f"Save Error: {e}")


# --- AUTO SCANNER ---
def scanner_loop():
    global last_scan_time, last_scan_result

    while True:
        try:
            logging.info("Running market scan...")

            db = load_data()
            new_found = engine.check_strategies()

            added = 0

            if new_found:
                for s in new_found:
                    # Prevent duplicate signals
                    exists = any(
                        h.get('symbol') == s.get('symbol') and
                        h.get('type') == s.get('type') and
                        h.get('strat') == s.get('strat')
                        for h in db["history"][:10]
                    )

                    if not exists:
                        s['time'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        db["history"].insert(0, s)
                        added += 1

                db["history"] = db["history"][:50]
                save_data(db)

            last_scan_time = datetime.now().strftime("%H:%M:%S")
            last_scan_result = f"{added} signal(s) found"

            logging.info(last_scan_result)

        except Exception as e:
            logging.error(f"Scanner Error: {e}")
            last_scan_result = f"Scanner Error: {e}"

        time.sleep(SCAN_INTERVAL)


@app.on_event("startup")
def startup_event():
    thread = threading.Thread(target=scanner_loop, daemon=True)
    thread.start()
    logging.info("Scanner thread started")


@app.get("/", response_class=HTMLResponse)
def dashboard():
    db = load_data()

    try:
        with open("index.html", "r") as f:
            template = f.read()

    except:
        return "Error: index.html not found."

    rows = ""

    for s in db.get("history", [])[:15]:
        color = "#10b981" if s.get('type') == "BUY" else "#f43f5e"
        signal_time = s.get('time', '--')

        rows += f"""
        <tr>
            <td>{s['symbol']}</td>
            <td style='color:{color}; font-weight:700;'>
                {s['type']}
            </td>
            <td>{s['strat']}</td>
            <td>{signal_time}</td>
        </tr>
        """

    pair_html = ""
    staffs = db["staffs"]

    for pair, p_data in staffs["pairs"].items():
        wr = (p_data['wins'] / p_data['total'] * 100) if p_data['total'] > 0 else 0

        pair_html += f"""
        <div class="pair-card">
            <div class="p-name">{pair}</div>
            <div class="p-wr">{wr:.1f}%</div>
            <div class="p-count">{p_data['total']} Signals</div>
        </div>
        """

    global_wr = (staffs['wins'] / staffs['total'] * 100) if staffs['total'] > 0 else 0

    html = template.replace("{{TOTAL}}", str(staffs['total']))
    html = html.replace("{{WINRATE}}", f"{global_wr:.1f}%")
    html = html.replace("{{PAIR_STATS}}", pair_html or "<p>No history yet</p>")
    html = html.replace("{{SIGNALS}}", rows or "<tr><td colspan='4'>No Signals Yet</td></tr>")
    html = html.replace("{{LAST_SCAN}}", last_scan_time)
    html = html.replace("{{SCAN_RESULT}}", last_scan_result)

    return html


@app.get("/scan")
def manual_scan():
    try:
        db = load_data()
        new_found = engine.check_strategies()

        if new_found:
            for s in new_found:
                db["history"].insert(0, s)

            db["history"] = db["history"][:50]
            save_data(db)

        return {
            "status": "complete",
            "signals": new_found
        }

    except Exception as e:
        return {
            "status": "error",
            "message": str(e)
        }


@app.get("/health")
def health():
    return {
        "status": "running",
        "last_scan": last_scan_time,
        "result": last_scan_result
    }


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0",)
