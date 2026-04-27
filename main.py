from fastapi import FastAPI

app = FastAPI()

signals = []

@app.post("/signal")
def add_signal(signal: dict):
    signals.append(signal)
    return {"status": "saved"}

@app.get("/signals")
def get_signals():
    return signals

@app.get("/")
def home():
    return {"status": "Trading bot is live"}
