import os
import json
import logging
import uvicorn
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
import engine
from datetime import datetime

app = FastAPI()

DB_FILE = "data.json"


def load_data():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r") as f:
                db = json.load(f)

            if "active" not in db:
                db["active"] = []

            if "history" not in db:
                db["history"] = []

            stats = {
                "wins": 0,
                "total": 0,
                "pairs": {}
            }

            for s in db.get("history", []):
                symbol = s.get("symbol", "UNKNOWN")

                stats["total"] += 1

                if symbol not in stats["pairs"]:
                    stats["pairs"][symbol] = {
                        "wins": 0,
                        "total": 0
                    }

                stats["pairs"][symbol]["total"] += 1

                if s.get("result") == "WIN":
                    stats["wins"] += 1
                    stats["pairs"][symbol]["wins"] += 1

            db["staffs"] = stats
            return db

        except Exception as e:
            logging.error(f"Load error: {e}")

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
    to_save = {
        "active": data.get("active", []),
        "history": data.get("history", [])
    }

    with open(DB_FILE, "w") as f:
        json.dump(to_save, f, indent=2)


@app.get("/", response_class=HTMLResponse)
def dashboard():
    db = load_data()

    try:
        with open("index.html", "r") as f:
            template = f.read()
    except:
        return "index.html not found"

    history_rows = ""

    for s in db.get("history", [])[:20]:
        color = "#10b981" if s.get("type") == "BUY" else "#f43f5e"

        result_color = "#10b981" if s.get("result") == "WIN" else "#f43f5e"

        history_rows += f"""
        <tr>
            <td>{s.get('symbol')}</td>
            <td style='color:{color};font-weight:700'>{s.get('type')}</td>
            <td>{s.get('entry')}</td>
            <td>{s.get('sl')}</td>
            <td>{s.get('tp')}</td>
            <td>{s.get('rr')}</td>
            <td style='color:{result_color};font-weight:700'>{s.get('result', '-')}</td>
        </tr>
        """

    active_rows = ""

    for s in db.get("active", []):
        color = "#10b981" if s.get("type") == "BUY" else "#f43f5e"

        active_rows += f"""
        <tr>
            <td>{s.get('symbol')}</td>
            <td style='color:{color};font-weight:700'>{s.get('type')}</td>
            <td>{s.get('entry')}</td>
            <td>{s.get('sl')}</td>
            <td>{s.get('tp')}</td>
            <td>{s.get('rr')}</td>
            <td style='color:#38bdf8;font-weight:700'>ACTIVE</td>
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

    last_scan = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    html = template.replace("{{TOTAL}}", str(staffs['total']))
    html = html.replace("{{WINRATE}}", f"{global_wr:.1f}%")
    html = html.replace("{{PAIR_STATS}}", pair_html)
    html = html.replace("{{SIGNALS}}", history_rows or "<tr><td colspan='7'>No Closed Signals Yet</td></tr>")
    html = html.replace("{{ACTIVE_SIGNALS}}", active_rows or "<tr><td colspan='7'>No Active Signals</td></tr>")
    html = html.replace("{{LAST_SCAN}}", last_scan)

    return html


@app.get("/scan")
def run_scanner():
    db = load_data()

    new_found = engine.check_strategies()

    if new_found:
        for s in new_found:

            exists = any(
                x.get("symbol") == s.get("symbol") and
                x.get("entry") == s.get("entry") and
                x.get("type") == s.get("type")
                for x in db["active"]
            )

            if not exists:
                s["created"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                db["active"].insert(0, s)

        save_data(db)

    return {
        "status": "complete",
        "new": len(new_found)
    }


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=10000)
