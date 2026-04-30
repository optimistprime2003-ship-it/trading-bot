import datetime

def generate_signals():
    signals = []

    now = datetime.datetime.utcnow()
    expiry = now + datetime.timedelta(hours=4)

    # 🔥 SAMPLE SIGNAL (replace later with your strategy)
    signals.append({
        "pair": "EUR/USD",
        "signal": "BUY",
        "type": "BUY STOP",
        "entry": 1.1000,
        "sl": 1.0950,
        "tp": 1.1100,
        "time": now.strftime("%Y-%m-%d %H:%M"),
        "expiry": expiry.strftime("%Y-%m-%d %H:%M"),
        "status": "active"
    })

    return signals
