import requests
from datetime import datetime, timedelta

PAIRS = ["EURUSD", "GBPUSD", "USDJPY"]

# ===============================
# SESSION FILTER
# ===============================
def is_trading_session():
    now = datetime.utcnow()
    hour = now.hour
    return 8 <= hour <= 21


# ===============================
# FETCH DATA
# ===============================
def fetch_data(symbol, interval="15min"):
    url = f"https://api.twelvedata.com/time_series?symbol={symbol}&interval={interval}&outputsize=100&apikey=d93af08b103e43c99034dd6362a239d3"
    res = requests.get(url).json()

    if "values" not in res:
        return []

    return list(reversed(res["values"]))


# ===============================
# EMA CALCULATION
# ===============================
def ema(prices, period):
    k = 2 / (period + 1)
    result = []

    for i, p in enumerate(prices):
        p = float(p)
        if i == 0:
            result.append(p)
        else:
            result.append(p * k + result[i - 1] * (1 - k))

    return result


# ===============================
# VOLATILITY FILTER (NEW)
# ===============================
def is_volatile(highs, lows, min_range=0.0015):
    """
    Checks if market has enough movement
    """
    candle_range = abs(float(highs[-1]) - float(lows[-1]))

    return candle_range >= min_range


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

        closes = [float(x["close"]) for x in data]
        highs = [float(x["high"]) for x in data]
        lows = [float(x["low"]) for x in data]

        # 🔴 VOLATILITY FILTER (NEW)
        if not is_volatile(highs, lows):
            continue

        ema8 = ema(closes, 8)
        ema20 = ema(closes, 20)
        ema50 = ema(closes, 50)

        i = -1

        buy_trend = ema8[i] > ema20[i] > ema50[i]
        sell_trend = ema8[i] < ema20[i] < ema50[i]

        now = datetime.utcnow()

        # BUY
        if buy_trend:
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

        # SELL
        elif sell_trend:
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
# UPDATE STATUS
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
