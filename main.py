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

app = FastAPI()

# =========================================================
# DATABASE FILE
# =========================================================

DB_FILE = "data.json"

# =========================================================
# SCANNER STATUS
# =========================================================

LAST_SCAN = "Waiting..."
SCAN_RESULT = "Scanner starting..."

# =========================================================
# LOAD DATA
# =========================================================

def load_data():

    if os.path.exists(DB_FILE):

        try:

            with open(DB_FILE, "r") as f:
                db = json.load(f)

            stats = {
                "wins": 0,
                "total": 0,
                "pairs": {}
            }

            history = db.get("history", [])

            for s in history:

                symbol = s.get("symbol", "UNKNOWN")

                strat = s.get("strat", "")

                stats["total"] += 1

                if symbol not in stats["pairs"]:

                    stats["pairs"][symbol] = {
                        "wins": 0,
                        "total": 0
                    }

                stats["pairs"][symbol]["total"] += 1

                if any(
                    x in strat
                    for x in [
                        "Daily",
                        "Pin Bar",
                        "H4",
                        "Breakout",
                        "5M"
                    ]
                ):

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

# =========================================================
# SAVE DATA
# =========================================================

def save_data(data):

    to_save = {
        "active": data.get("active", []),
        "history": data.get("history", [])
    }

    with open(DB_FILE, "w") as f:

        json.dump(to_save, f, indent=2)

# =========================================================
# BACKGROUND SCANNER
# =========================================================

def scanner_loop():

    global LAST_SCAN
    global SCAN_RESULT

    while True:

        try:

            db = load_data()

            new_found = engine.check_strategies()

            added = 0

            for s in new_found:

                duplicate = False

                for old in db["history"]:

                    if (
                        old.get("symbol") == s.get("symbol")
                        and old.get("type") == s.get("type")
                        and old.get("time") == s.get("time")
                    ):

                        duplicate = True
                        break

                if not duplicate:

                    db["history"].insert(0, s)

                    added += 1

            db["history"] = db["history"][:50]

            save_data(db)

            LAST_SCAN = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            if added > 0:
                SCAN_RESULT = f"{added} New Signal(s) Found"
            else:
                SCAN_RESULT = "No New Signals"

            logging.info(SCAN_RESULT)

        except Exception as e:

            logging.error(f"Scanner Error: {e}")

            SCAN_RESULT = "Scanner Error"

        time.sleep(300)

# =========================================================
# START BACKGROUND THREAD
# =========================================================

threading.Thread(
    target=scanner_loop,
    daemon=True
).start()

# =========================================================
# DASHBOARD
# =========================================================

@app.get("/", response_class=HTMLResponse)

def dashboard():

    db = load_data()

    try:

        with open("index.html", "r") as f:
            template = f.read()

    except:

        return "index.html not found"

    # =====================================================
    # SIGNAL ROWS
    # =====================================================

    rows = ""

    for s in db.get("history", [])[:15]:

        color = (
            "#10b981"
            if s.get("type") == "BUY"
            else "#f43f5e"
        )

        rows += f"""
<tr>
<td>{s.get('symbol', '-')}</td>

<td style='color:{color}; font-weight:700;'>
{s.get('type', '-')}
</td>

<td>{s.get('entry', '-')}</td>

<td>{s.get('sl', '-')}</td>

<td>{s.get('tp', '-')}</td>

<td>{s.get('rr', '-')}</td>
</tr>
"""

    # =====================================================
    # EMPTY STATE FIX
    # =====================================================

    if rows == "":

        rows = """
<tr>
<td colspan='6' style='text-align:center; padding:40px;'>

<div style='font-size:18px; font-weight:700; margin-bottom:10px;'>
No Active Signals
</div>

<div style='font-size:13px; color:#94a3b8; line-height:1.6;'>
The engine is scanning the market every 5 minutes.
Signals will appear automatically when conditions are met.
</div>

</td>
</tr>
"""

    # =====================================================
    # PAIR STATS
    # =====================================================

    pair_html = ""

    staffs = db["staffs"]

    for pair, p_data in staffs["pairs"].items():

        wr = (
            (p_data['wins'] / p_data['total']) * 100
            if p_data['total'] > 0
            else 0
        )

        pair_html += f"""
<div class="pair-card">

<div class="p-name">{pair}</div>

<div class="p-wr">{wr:.1f}%</div>

<div class="p-count">
{p_data['total']} Signals
</div>

</div>
"""

    global_wr = (
        (staffs['wins'] / staffs['total']) * 100
        if staffs['total'] > 0
        else 0
    )

    # =====================================================
    # HTML REPLACEMENTS
    # =====================================================

    html = template.replace(
        "{{TOTAL}}",
        str(staffs['total'])
    )

    html = html.replace(
        "{{WINRATE}}",
        f"{global_wr:.1f}%"
    )

    html = html.replace(
        "{{PAIR_STATS}}",
        pair_html
    )

    html = html.replace(
        "{{SIGNALS}}",
        rows
    )

    html = html.replace(
        "{{LAST_SCAN}}",
        LAST_SCAN
    )

    html = html.replace(
        "{{SCAN_RESULT}}",
        SCAN_RESULT
    )

    return html

# =========================================================
# MANUAL SCAN
# =========================================================

@app.get("/scan")

def run_scan():

    return {
        "status": "scanner active"
    }

# =========================================================
# HEALTH CHECK
# =========================================================

@app.get("/health")

def health():

    return {
        "status": "running",
        "last_scan": LAST_SCAN,
        "scan_result": SCAN_RESULT
    }

# =========================================================
# RUN SERVER
# =========================================================

if __name__ == "__main__":

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=10000
        )
