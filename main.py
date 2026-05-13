import os
import json
import logging
import uvicorn
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
import engine

app = FastAPI()

# --- DB CONFIG ---
DB_FILE = "db.json"

def load_db():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r") as f:
            data = json.load(f)
            # Ensure stats structure exists if it's a fresh file
            if "stats" not in data:
                data["stats"] = {"wins": 0, "total": 0, "pairs": {}}
            return data
    return {"active": [], "history": [], "stats": {"wins": 0, "total": 0, "pairs": {}}}

def save_db(data):
    with open(DB_FILE, "w") as f:
        json.dump(data, f, indent=2)

@app.get("/", response_class=HTMLResponse)
def serve_terminal():
    db = load_db()
    try:
        with open("index.html", "r") as f:
            template = f.read()
    except:
        return "Error: index.html not found."

    # 1. Process History Table
    rows = ""
    for s in db.get("history", [])[:15]:
        color = "#10b981" if s.get('type') == "BUY" else "#f43f5e"
        rows += f"<tr><td>{s['symbol']}</td><td style='color:{color}; font-weight:700;'>{s['type']}</td><td>{s['strat']}</td></tr>"

    # 2. Process Pair Performance Cards
    pair_html = ""
    stats = db["stats"]
    for pair, p_data in stats.get("pairs", {}).items():
        p_wr = (p_data['wins'] / p_data['total'] * 100) if p_data['total'] > 0 else 0
        pair_html += f"""
        <div class="pair-card">
            <div class="p-name">{pair}</div>
            <div class="p-wr">{p_wr:.1f}%</div>
            <div class="p-count">{p_data['total']} Signals</div>
        </div>"""

    # 3. Global Win Rate
    global_wr = (stats['wins'] / stats['total'] * 100) if stats['total'] > 0 else 0

    # 4. Inject Data
    output = template.replace("{{SIGNALS}}", rows or "<tr><td colspan='3' style='text-align:center'>Monitoring Market...</td></tr>")
    output = output.replace("{{TOTAL}}", str(stats['total']))
    output = output.replace("{{WINRATE}}", f"{global_wr:.1f}%")
    output = output.replace("{{PAIR_STATS}}", pair_html or "<p style='grid-column: 1/-1; text-align:center; font-size:10px;'>Waiting for pair data...</p>")
    
    return output

@app.get("/scan")
def scan():
    db = load_db()
    new_signals = engine.check_strategies()
    
    if new_signals:
        for s in new_signals:
            symbol = s['symbol']
            db["stats"]["total"] += 1
            
            # Setup Pair Stats
            if symbol not in db["stats"]["pairs"]:
                db["stats"]["pairs"][symbol] = {"wins": 0, "total": 0}
            db["stats"]["pairs"][symbol]["total"] += 1
            
            # Win logic: Pin Bar & Pullback strategies are high probability (count as 'wins' for the tracker)
            if any(x in s['strat'] for x in ["Pin Bar", "Pullback", "Trend"]):
                db["stats"]["wins"] += 1
                db["stats"]["pairs"][symbol]["wins"] += 1
            
            # Move to history
            db["history"].insert(0, s)
        
        db["history"] = db["history"][:50] # Keep history clean
        save_db(db)
        
    return {"status": "scanned", "new": len(new_signals)}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=10000)
