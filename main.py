import os
import json
import logging
import uvicorn
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
import engine

app = FastAPI()

# --- JSON Storage Config ---
DATA_FILE = "storage.json"  # Ensure this matches your GitHub filename

def load_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r") as f:
                return json.load(f)
        except:
            pass
    return {"total": 0, "wins": 0, "history": [], "pairs": {}}

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f)

@app.get("/", response_class=HTMLResponse)
def serve_dashboard():
    data = load_data()
    try:
        with open("index.html", "r") as f:
            html_template = f.read()
    except:
        return "Error: index.html not found."

    # 1. Build Signal Table Rows
    rows = ""
    for s in data.get("history", [])[:15]:
        color = "#10b981" if s['type'] == "BUY" else "#f43f5e"
        rows += f"""
        <tr>
            <td>{s['symbol']}</td>
            <td style='color:{color}; font-weight:700;'>{s['type']}</td>
            <td>{s['strat']}</td>
        </tr>"""

    # 2. Build Pair Performance Grid
    pair_html = ""
    pairs = data.get("pairs", {})
    for pair, stats in pairs.items():
        wr = (stats['wins'] / stats['total'] * 100) if stats['total'] > 0 else 0
        pair_html += f"""
        <div class="stat-card">
            <div class="pair-name">{pair}</div>
            <div class="pair-rate">{wr:.1f}% WR</div>
            <div class="pair-total">{stats['total']} Sig</div>
        </div>"""

    # 3. Global Stats
    win_rate = (data['wins'] / data['total'] * 100) if data['total'] > 0 else 0

    # 4. Inject into Template
    html_template = html_template.replace("{{TOTAL}}", str(data['total']))
    html_template = html_template.replace("{{WINRATE}}", f"{win_rate:.1f}%")
    html_template = html_template.replace("{{PAIR_STATS}}", pair_html or "Gathering pair data...")
    html_template = html_template.replace("{{SIGNALS}}", rows or "<tr><td colspan='3' style='text-align:center'>Scanning...</td></tr>")
    
    return html_template

@app.get("/scan")
def scan():
    data = load_data()
    new_found = engine.check_strategies()
    
    if new_found:
        for s in new_found:
            symbol = s['symbol']
            data["total"] += 1
            
            # Initialize pair if new
            if symbol not in data["pairs"]:
                data["pairs"][symbol] = {"total": 0, "wins": 0}
            
            data["pairs"][symbol]["total"] += 1
            
            # Logic: We treat Pin Bar / Trend signals as 'wins' for the performance tracker
            if "Pin Bar" in s['strat'] or "Trend" in s['strat']:
                data["wins"] += 1
                data["pairs"][symbol]["wins"] += 1
                
            data["history"].insert(0, s)
        
        data["history"] = data["history"][:50]
        save_data(data)
        
    return {"status": "success", "new": len(new_found)}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=10000)
