import requests
from datetime import datetime, timedelta

PAIRS = ["EURUSD", "GBPUSD", "USDJPY"]

# ===============================
# SESSION FILTER (London + New York)
# ===============================
def is_trading_session():
    now = datetime.utcnow()
    hour = now.hour

    # Trade only between 08:00 and 21:00 UTC
    return 8 <= hour <= 21


# ===============================
# FETCH MARKET DATA
# ===============================
def fetch_data(symbol, interval="15min"):
    url = f"https://api.twelvedata.com/time_series?symbol={symbol}&interval={interval}&outputsize=100&apikey=d93af08b103e43c99034dd6362a239d3"
    res = requests.get(url).json()

    if "values" not in res:
        return []

    return list(reversed(res["values"]))


# ===============================
# SIMPLE EMA CALCULATION
# ===============================
def calculate_ema(prices, period):
    ema = []
    k = 2 / (period + 1)

    for i, price in enumerate(prices):
        price = float(price)

        if i == 0:
            ema.append(price)
        else:
            ema.append(price * k + ema[i - 1] * (1 - k))

    return ema


# ===============================
# GENERATE SIGNALS
# ===============================
def generate_signals():
    if not is_trading_session():
        return []

    signals = []

    for pair in PAIRS:
        data = fetch_data(pair, "15min")

        if len(data) < 50:
            continue

        closes = [float(c["close"]) for c in data]
        highs = [float(c["high"]) for c in data]
        lows = [float(c["low"]) for c in data]

        ema8 = calculate_ema(closes, 8)
        ema20 = calculate_ema(closes, 20)
        ema50 = calculate_ema(closes, 50)

        i = -1

        # TREND
        buy_trend = ema8[i] > ema20[i] > ema50[i]
        sell_trend = ema8[i] < ema20[i] < ema50[i]

        # PULLBACK (touch EMA)
        ema_touch_buy = abs(lows[i] - ema8[i]) < 0.0015
        ema_touch_sell = abs(highs[i] - ema8[i]) < 0.0015

        now = datetime.utcnow()

        if buy_trend and ema_touch_buy:
            entry = highs[i] + 0.0002
            sl = lows[i] - 0.0002
            tp = entry + (entry - sl) * 2

            signals.append({
                "pair": pair,
                "signal": "BUY",
                "type": "BUY STOP",
                "entry": round(entry, 5),
                "sl": round(sl, 5),
                "tp": round(tp, 5),
                "time": str(now),
                "expiry": str(now + timedelta(hours=4)),
                "status": "ACTIVE"
            })

        elif sell_trend and ema_touch_sell:
            entry = lows[i] - 0.0002
            sl = highs[i] + 0.0002
            tp = entry - (sl - entry) * 2

            signals.append({
                "pair": pair,
                "signal": "SELL",
                "type": "SELL STOP",
                "entry": round(entry, 5),
                "sl": round(sl, 5),
                "tp": round(tp, 5),
                "time": str(now),
                "expiry": str(now + timedelta(hours=4)),
                "status": "ACTIVE"
            })

    return signals


# ===============================
# UPDATE SIGNAL STATUS
# ===============================
def update_signal_status(signals):
    updated = []

    for s in signals:
        pair = s["pair"]
        data = fetch_data(pair, "1min")

        if not data:
            updated.append(s)
            continue

        price = float(data[-1]["close"])
        now = datetime.utcnow()

        if s["status"] == "ACTIVE":
            if price >= s["tp"]:
                s["status"] = "TP HIT"
            elif price <= s["sl"]:
                s["status"] = "SL HIT"
            elif now > datetime.fromisoformat(s["expiry"]):
                s["status"] = "EXPIRED"

        updated.append(s)

    return updated
