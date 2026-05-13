from fastapi import FastAPI
from fastapi.responses import HTMLResponse
import engine
import uvicorn
import logging

app = FastAPI()
latest_signals = []

@app.get("/")
def heartbeat():
    logging.info("Cron heartbeat received.")
    return {"status": "online", "rotation": "active"}

@app.get("/scan")
def scan():
    global latest_signals
    new_found = engine.check_strategies()
    if new_found:
        latest_signals = new_found + latest_signals
    return {"found": len(new_found), "signals": new_found}

@app.get("/dashboard", response_class=HTMLResponse)
def show_dashboard():
    rows = "".join([f"<tr style='border-bottom: 1px solid #444;'><td>{s['symbol']}</td><td style='color:{'#00ff00' if s['type']=='BUY' else '#ff4444'}'>{s['type']}</td><td>{s['strat']}</td></tr>" for s in latest_signals[:15]])
    
    return f"""
    <html>
        <head>
            <meta http-equiv="refresh" content="30">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
        </head>
        <body style="background:#1a1a1a; color:white; font-family:sans-serif; padding:20px;">
            <h2 style="text-align:center;">Trading Bot Terminal</h2>
            <div style="background:#2a2a2a; border-radius:10px; padding:15px;">
                <table style="width:100%; text-align:left;">
                    <tr style="color:#aaa;"><th>PAIR</th><th>SIGNAL</th><th>STRATEGY</th></tr>
                    {rows if rows else "<tr><td colspan='3' style='text-align:center; padding:20px;'>Scanning markets...</td></tr>"}
                </table>
            </div>
            <p style="text-align:center; color:#00ff00; margin-top:20px;">● SERVER LIVE & ROTATING KEYS</p>
        </body>
    </html>
    """

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=10000)
