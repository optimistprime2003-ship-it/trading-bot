import requests
from datetime import datetime, timedelta

PAIRS = ["EURUSD", "GBPUSD", "USDJPY"]

API_KEY = "YOUR_API_KEY"

# ===============================
# SESSION FILTER
# ===============================
def is_trading_session():
    now = datetime.utcnow()
    return 8 <= now.hour <= 21


# ===============================
# FETCH DATA
# ===============================
def fetch_data(symbol, interval="15min"):
    url = f"https://api.twelvedata.com/time_series?symbol={symbol}&interval={interval}&outputsize=100&apikey={API_KEY}"
    res = requests.get(url).json()

    if "values" not in res:
        return []

    return list(reversed(res["values"]))


# ===============================
# EMA
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
# PIN BAR DETECTION
# ===============================
def is_bullish_pin(open_p, close_p, high_p, low_p):
    body = abs(close_p - open_p)
    candle = high_p - low_p

    lower_part = min(open_p, close_p) - low_p
    upper_part = high_p - max(open_p, close_p)

    if candle == 0:
        return False

    # Open/close in lower 30%
    return (max(open_p, close_p) < low_p + candle * 0.3) and (upper_part < body)


def is_bearish_pin(open_p, close_p, high_p, low_p):
    body = abs(close_p - open_p)
    candle = high_p - low_p

    lower_part = min(open_p, close_p) - low_p
    upper_part = high_p - max(open_p, close_p)

    if candle == 0:
        return False

    # Open/close in upper 30%
    return (min(open_p, close_p) > high_p - candle * 0.3) and (lower_part < body)


# ===============================
# VOLATILITY FILTER (SOFT)
# ===============================
def is_volatile(highs, lows):
    return abs(highs[-1] - lows[-1]) >= 0.0008


# ===============================
# GENERATE SIGNALS
# ===============================
def generate_signals():

    if not is_trading_session():
        return []

    signals = []

    for pair in PAIRS:

        data = fetch_data(pair, "15min")

        if len(data) < 60:
            continue

        closes = [float(x["close"]) for x in data]
        highs = [float(x["high"]) for x in data]
        lows = [float(x["low"]) for x in data]
        opens = [float(x["open"]) for x in data]

        # Volatility check
        if not is_volatile(highs, lows):
            continue

        ema8 = ema(closes, 8)
        ema20 = ema(closes, 20)
        ema50 = ema(closes, 50)

        i = -1

        open_p = opens[i]
        close_p = closes[i]
        high_p = highs[i]
        low_p = lows[i]

        now = datetime.utcnow()

        # ================= BUY =================
        if (
            ema8[i] > ema20[i] > ema50[i]
            and is_bullish_pin(open_p, close_p, high_p, low_p)
            and low_p <= ema8[i]
        ):
            entry = high_p + 0.0002
            sl = low_p - 0.0002
            tp = entry + (entry - sl)  # 1:1

            signals.append({
                "pair": pair,
                "signal": "BUY",
                "type": "BUY STOP",
                "entry": round(entry, 5),
                "sl": round(sl, 5),
                "tp": round(tp, 5),
                "time": str(now),
                "expiry": str(now + timedelta(days=1)),
                "status": "ACTIVE"
            })

        # ================= SELL =================
        elif (
            ema8[i] < ema20[i] < ema50[i]
            and is_bearish_pin(open_p, close_p, high_p, low_p)
            and high_p >= ema8[i]
        ):
            entry = low_p - 0.0002
            sl = high_p + 0.0002
            tp = entry - (sl - entry)  # 1:1

            signals.append({
                "pair": pair,
                "signal": "SELL",
                "type": "SELL STOP",
                "entry": round(entry, 5),
                "sl": round(sl, 5),
                "tp": round(tp, 5),
                "time": str(now),
                "expiry": str(now + timedelta(days=1)),
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

            if s["signal"] == "BUY":
                if price >= s["tp"]:
                    s["status"] = "TP HIT"
                elif price <= s["sl"]:
                    s["status"] = "SL HIT"

            elif s["signal"] == "SELL":
                if price <= s["tp"]:
                    s["status"] = "TP HIT"
                elif price >= s["sl"]:
                    s["status"] = "SL HIT"

            elif now > datetime.fromisoformat(s["expiry"]):
                s["status"] = "EXPIRED"

        updated.append(s)

    return updated
