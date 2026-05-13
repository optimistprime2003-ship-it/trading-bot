import os
import logging
import uvicorn
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
import engine

app = FastAPI()
latest_signals = []

@app.get("/", response_class=HTMLResponse)
def serve_dashboard():
    global latest_signals
    
    # 1. Load your custom index.html file
    try:
        with open("index.html", "r") as f:
            html_template = f.read()
    except FileNotFoundError:
        return "<h1>Error: index.html not found in root directory.</h1>"

    # 2. Convert signal data into HTML rows for your table
    # Matches the 'Pair | Signal | Strategy' columns in your index.html
    rows = ""
    for s in latest_signals[:15]:
        # Using the exact hex colors from your CSS :root variables
        color = "#10b981" if s['type'] == "BUY" else "#f43f5e"
        rows += f"""
        <tr>
            <td>{s['symbol']}</td>
            <td style="color:{color}; font-weight:bold;">{s['type']}</td>
            <td>{s['strat']}</td>
        </tr>
        """

    if not rows:
        rows = "<tr><td colspan='3' style='text-align:center; padding:30px; color:#94a3b8;'>Scanning Market for Patterns...</td></tr>"

    # 3. Inject the rows into your {{SIGNALS}} placeholder
    return html_template.replace("{{SIGNALS}}", rows)

@app.get("/scan")
def scan():
    global latest_signals
    logging.info("Cron heartbeat received. Scanning markets...")
    
    # Calls your engine logic for EURUSD, GBPUSD, and BTC
    new_found = engine.check_strategies()
    if new_found:
        # Adds newest signals to the top of the list
        latest_signals = new_found + latest_signals
        latest_signals = latest_signals[:30] # Keep recent history
        
    return {"found": len(new_found), "signals": new_found}

# Keeps your rotation status accessible via /status
@app.get("/status")
def status():
    return {"status": "online", "rotation": "active", "signals_cached": len(latest_signals)}

if __name__ == "__main__":
    # Standard Render/Cloud deployment port
    uvicorn.run(app, host="0.0.0.0", port=10000)
