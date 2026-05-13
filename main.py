import os
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
import engine
import uvicorn
import logging

app = FastAPI()
latest_signals = []

# --- THE FIX: We move the Dashboard to the root "/" so the App sees it first ---
@app.get("/", response_class=HTMLResponse)
def serve_dashboard():
    global latest_signals
    
    # 1. Look for your index.html file
    if os.path.exists("index.html"):
        with open("index.html", "r") as f:
            html_template = f.read()
    else:
        return "<h1>Error: index.html not found! Ensure it is in your main GitHub folder.</h1>"

    # 2. Build the signal rows using your premium styling
    rows = ""
    for s in latest_signals[:15]:
        # Colors match your Buy/Sell indicators
        color = "#10b981" if s['type'] == "BUY" else "#f43f5e"
        rows += f"""
        <tr style="border-bottom: 1px solid rgba(255,255,255,0.05);">
            <td style="padding:15px; font-weight:700;">{s['symbol']}</td>
            <td style="padding:15px; color:{color}; font-weight:bold;">{s['type']}</td>
            <td style="padding:15px; color:#94a3b8; font-size:13px;">{s['strat']}</td>
        </tr>
        """

    if not rows:
        rows = "<tr><td colspan='3' style='text-align:center; padding:30px; color:#94a3b8;'>Scanning markets for Pin Bars and EMA Pullbacks...</td></tr>"

    # 3. "Sinking" the data into your HTML placeholder
    return html_template.replace("{{SIGNALS}}", rows)

@app.get("/scan")
def scan():
    global latest_signals
    logging.info("Cron heartbeat received. Starting Market Scan.")
    
    # This triggers your 1D and 5M strategy checks
    new_found = engine.check_strategies()
    if new_found:
        # Add new signals to the top of the list
        latest_signals = new_found + latest_signals
        # Keep only the last 20 to keep the dashboard fast
        latest_signals = latest_signals[:20]
        
    return {"found": len(new_found), "total_active": len(latest_signals)}

# Keep the JSON status here for your own troubleshooting
@app.get("/status")
def status():
    return {"status": "online", "rotation": "active", "cache_size": len(latest_signals)}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=10000)
