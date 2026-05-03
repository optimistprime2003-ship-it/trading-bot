import requests
from datetime import datetime, timedelta

PAIRS = ["EURUSD", "GBPUSD", "USDJPY"]
API_KEY = "d93af08b103e43c99034dd6362a239d3"

# ===============================
# FETCH DATA
# ===============================
def fetch_data(symbol, interval):
    url = f"https://api.twelvedata.com/time_series?symbol={symbol}&interval={interval}&outputsize=200&apikey={API_KEY}"
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
# GET NY SESSION FIRST 4H RANGE
# ===============================
def get_ny_range(data_4h):

    for candle in data_4h:
        dt = datetime.fromisoformat(candle["datetime"])

        # New York 00:00 ≈ 04:00 UTC (approx)
        if dt.hour == 4:
            return float(candle["high"]), float(candle["low"])

    return None, None


# ===============================
# PIN BAR STRATEGY (UNCHANGED)
# ===============================
def generate_pinbar_signals():
    signals = []

    for pair in PAIRS:
        data = fetch_data(pair, "15min")
        if len(data) < 60:
            continue

        closes = [float(x["close"]) for x in data]
        highs = [float(x["high"]) for x in data]
        lows = [float(x["low"]) for x in data]
        opens = [float(x["open"]) for x in data]

        ema8 = ema(closes, 8)
        ema20 = ema(closes, 20)
        ema50 = ema(closes, 50)

        i = -1
        now = datetime.utcnow()

        open_p = opens[i]
        close_p = closes[i]
        high_p = highs[i]
        low_p = lows[i]

        body = abs(close_p - open_p)
        candle = high_p - low_p

        if candle == 0:
            continue

        bullish_pin = max(open_p, close_p) < low_p + candle * 0.3
        bearish_pin = min(open_p, close_p) > high_p - candle * 0.3

        # BUY
        if ema8[i] > ema20[i] > ema50[i] and bullish_pin:
            entry = high_p + 0.0002
            sl = low_p - 0.0002
            tp = entry + (entry - sl)

            signals.append({
                "pair": pair,
                "strategy": "PinBar",
                "signal": "BUY",
                "type": "BUY STOP",
                "entry": round(entry, 5),
                "sl": round(sl, 5),
                "tp": round(tp, 5),
                "time": str(now),
                "expiry": str(now + timedelta(days=1)),
                "status": "ACTIVE"
            })

        # SELL
        elif ema8[i] < ema20[i] < ema50[i] and bearish_pin:
            entry = low_p - 0.0002
            sl = high_p + 0.0002
            tp = entry - (sl - entry)

            signals.append({
                "pair": pair,
                "strategy": "PinBar",
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
# FAKE BREAKOUT (CORRECT NY RANGE)
# ===============================
def generate_fake_breakout_signals():
    signals = []

    for pair in PAIRS:

        data_4h = fetch_data(pair, "4h")
        data_5m = fetch_data(pair, "5min")

        if len(data_4h) < 10 or len(data_5m) < 10:
            continue

        range_high, range_low = get_ny_range(data_4h)

        if range_high is None:
            continue

        last = data_5m[-1]
        prev = data_5m[-2]

        last_close = float(last["close"])
        prev_close = float(prev["close"])

        high = float(last["high"])
        low = float(last["low"])

        now = datetime.utcnow()

        # SELL (fake breakout above range)
        if prev_close > range_high and last_close < range_high:
            entry = low
            sl = high
            tp = entry - (sl - entry) * 2

            signals.append({
                "pair": pair,
                "strategy": "FakeBreakout",
                "signal": "SELL",
                "type": "MARKET",
                "entry": round(entry, 5),
                "sl": round(sl, 5),
                "tp": round(tp, 5),
                "time": str(now),
                "expiry": str(now + timedelta(days=1)),
                "status": "ACTIVE"
            })

        # BUY (fake breakout below range)
        elif prev_close < range_low and last_close > range_low:
            entry = high
            sl = low
            tp = entry + (entry - sl) * 2

            signals.append({
                "pair": pair,
                "strategy": "FakeBreakout",
                "signal": "BUY",
                "type": "MARKET",
                "entry": round(entry, 5),
                "sl": round(sl, 5),
                "tp": round(tp, 5),
                "time": str(now),
                "expiry": str(now + timedelta(days=1)),
                "status": "ACTIVE"
            })

    return signals


# ===============================
# COMBINED SIGNALS
# ===============================
def generate_signals():
    signals = []
    signals += generate_pinbar_signals()
    signals += generate_fake_breakout_signals()
    return signals


# ===============================
# UPDATE STATUS
# ===============================
def update_signal_status(signals):
    updated = []

    for s in signals:
        data = fetch_data(s["pair"], "1min")

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
