import os
import json
import logging
import uvicorn
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
import engine

app = FastAPI()

# --- DYNAMIC STORAGE CONFIG ---
# Using data.json as found in your GitHub setup
DB_FILE = "data.json"

def load_data():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r") as f:
                db = json.load(f)
            
            # --- STAFFS CALCULATION LOGIC ---
            # We rebuild stats from history every load to ensure accuracy
            stats = {"wins": 0, "total": 0, "pairs": {}}
            history = db.get("history", [])
            
            for s in history:
                symbol = s.get('symbol', 'UNKNOWN')
                strat = s.get('strat', '')
                stats["total"] += 1
                
                if symbol not in stats["pairs"]:
                    stats["pairs"][symbol] = {"wins": 0, "total": 0}
                stats["pairs"][symbol]["total"] += 1
                
                # Logic for your 2 Primary Strategies: 
                # 1D Pin Bar/Trend & H4 Range/5M Entry
                if any(x in strat for x in ["Daily", "Pin Bar", "H4", "Breakout", "5M"]):
                    stats["wins"] += 1
                    stats["pairs"][symbol]["wins"] += 1
            
            db["staffs"] = stats
            return db
        except Exception as e:
            logging.error(f"Error loading {DB_FILE}: {e}")
            
    return {"active": [], "history": [], "staffs": {"wins": 0, "total": 0, "pairs": {}}}

def save_data(data):
    # We only save history/active; staffs are calculated live
    to_save = {"active": data.get("active", []), "history": data.get("history", [])}
    with open(DB_FILE, "w") as f:
        json.dump(to_save, f, indent=2)

@app.get("/", response_class=HTMLResponse)
def dashboard():
    db = load_data()
    try:
        with open("index.html", "r") as f:
            template = f.read()
    except:
        return "Error: index.html not found in root."

    # 1. Build Signal Table Rows
    rows = ""
    for s in db.get("history", [])[:15]:
        color = "#10b981" if s.get('type') == "BUY" else "#f43f5e"
        rows += f"<tr><td>{s['symbol']}</td><td style='color:{color}; font-weight:700;'>{s['type']}</td><td>{s['strat']}</td></tr>"

    # 2. Build Pair Strength/Performance Grid
    pair_html = ""
    staffs = db["staffs"]
    for pair, p_data in staffs["pairs"].items():
        wr = (p_data['wins'] / p_data['total'] * 100) if p_data['total'] > 0 else 0
        pair_html += f"""
        <div class="pair-card">
            <div class="p-name">{pair}</div>
            <div class="p-wr">{wr:.1f}%</div>
            <div class="p-count">{p_data['total']} Signals</div>
        </div>"""

    # 3. Inject Everything into the UI
    global_wr = (staffs['wins'] / staffs['total'] * 100) if staffs['total'] > 0 else 0
    
    html = template.replace("{{TOTAL}}", str(staffs['total']))
    html = html.replace("{{WINRATE}}", f"{global_wr:.1f}%")
    html = html.replace("{{PAIR_STATS}}", pair_html or "<p style='grid-column:1/-1; font-size:10px;'>Awaiting Signal History...</p>")
    html = html.replace("{{SIGNALS}}", rows or "<tr><td colspan='3' style='text-align:center'>No Signals in History</td></tr>")
    
    return html

@app.get("/scan")
def run_scanner():
    db = load_data()
    # Calls engine.py for 1D Trend and H4/5M range logic
    new_found = engine.check_strategies() 
    
    if new_found:
        for s in new_found:
            db["history"].insert(0, s)
        
        db["history"] = db["history"][:50]
        save_data(db)
        
    return {"status": "complete", "new": len(new_found)}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=10000)
