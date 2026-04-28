from fastapi import FastAPI
from engine import get_data, generate_signal

# ✅ THIS MUST BE AT THE TOP
app = FastAPI()

signals = []

@app.get("/")
def home():
    return {"status": "Signal engine running"}

@app.get("/run")
def run_engine():
    try:
        df = get_data("EUR/USD", "15min", 50)

        if df is None:
            return {"error": "No market data"}

        signal = generate_signal(df)

        if signal:
            signals.append(signal)
            return {"new_signal": signal}

        return {"status": "no signal"}

    except Exception as e:
        return {"error": str(e)}

@app.get("/signals")
def get_signals():
    return signals
