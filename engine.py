import requests
import datetime

API_KEY = "d93af08b103e43c99034dd6362a239d3"

PAIRS = ["EUR/USD", "GBP/USD", "USD/JPY", "GBP/JPY", "AUD/USD", "EUR/JPY"]

TIMEFRAME_ENTRY = "15min"
TIMEFRAME_TREND = "1h"


# 🔹 FETCH CANDLES
def get_candles(pair, interval, limit=100):
    url = f"https://api.twelvedata.com/time_series?symbol={pair}&interval={interval}&outputsize={limit}&apikey={API_KEY}"
    data = requests.get(url).json()

    if "values" not in data:
        return []

    candles = list(reversed(data["values"]))

    for c in candles:
        c["close"] = float(c["close"])
        c["open"] = float(c["open"])
        c["high"] = float(c["high"])
        c["low"] = float(c["low"])

    return candles


# 🔹 EMA CALCULATION
def calculate_ema(prices, period):
    ema = []
    k = 2 / (period + 1)

    for i in range(len(prices)):
        if i == 0:
            ema.append(prices[i])
        else:
            ema.append(prices[i] * k + ema[i-1] * (1 - k))

    return ema


# 🔹 PIN BAR DETECTION
def is_bullish_pin(c):
    body = abs(c["close"] - c["open"])
    lower_wick = min(c["open"], c["close"]) - c["low"]
    total = c["high"] - c["low"]

    return lower_wick >= 2 * body and (c["close"] > c["open"]) and (c["close"] > c["low"] + 0.7 * total)


def is_bearish_pin(c):
    body = abs(c["close"] - c["open"])
    upper_wick = c["high"] - max(c["open"], c["close"])
    total = c["high"] - c["low"]

    return upper_wick >= 2 * body and (c["close"] < c["open"]) and (c["close"] < c["low"] + 0.3 * total)


# 🔹 MAIN STRATEGY
def generate_signals():
    signals = []

    now = datetime.datetime.utcnow()
    expiry = now + datetime.timedelta(hours=4)

    for pair in PAIRS:
        try:
            m15 = get_candles(pair, TIMEFRAME_ENTRY)
            h1 = get_candles(pair, TIMEFRAME_TREND)

            if len(m15) < 60 or len(h1) < 60:
                continue

            closes_m15 = [c["close"] for c in m15]
            closes_h1 = [c["close"] for c in h1]

            ema8_m15 = calculate_ema(closes_m15, 8)
            ema20_m15 = calculate_ema(closes_m15, 20)
            ema50_m15 = calculate_ema(closes_m15, 50)

            ema8_h1 = calculate_ema(closes_h1, 8)
            ema20_h1 = calculate_ema(closes_h1, 20)
            ema50_h1 = calculate_ema(closes_h1, 50)

            last = m15[-1]
            ema_touch = (
    abs(last["low"] - ema8_m15[-1]) < 0.0005 or
    abs(last["low"] - ema20_m15[-1]) < 0.0005 or
    abs(last["high"] - ema8_m15[-1]) < 0.0005 or
    abs(last["high"] - ema20_m15[-1]) < 0.0005
            )

            # 🔥 TREND CONDITIONS
            buy_trend = (
                ema8_m15[-1] > ema20_m15[-1] > ema50_m15[-1] and
                ema8_h1[-1] > ema20_h1[-1] > ema50_h1[-1]
            )

            sell_trend = (
                ema8_m15[-1] < ema20_m15[-1] < ema50_m15[-1] and
                ema8_h1[-1] < ema20_h1[-1] < ema50_h1[-1]
            )

            # 🔥 TREND STRENGTH
            distance = abs(ema8_m15[-1] - ema50_m15[-1])

            if distance < 0.0010:
                continue

            # 🔥 PIN BAR
            if buy_trend and is_bullish_pin(last):
                entry = last["high"] + 0.0002
                sl = last["low"] - 0.0002
                tp = entry + (entry - sl) * 2

                signals.append({
                    "pair": pair,
                    "signal": "BUY",
                    "type": "BUY STOP",
                    "entry": round(entry, 5),
                    "sl": round(sl, 5),
                    "tp": round(tp, 5),
                    "time": now.strftime("%Y-%m-%d %H:%M"),
                    "expiry": expiry.strftime("%Y-%m-%d %H:%M"),
                    "status": "ACTIVE"
                })

            elif sell_trend and is_bearish_pin(last):
                entry = last["low"] - 0.0002
                sl = last["high"] + 0.0002
                tp = entry - (sl - entry) * 2

                signals.append({
                    "pair": pair,
                    "signal": "SELL",
                    "type": "SELL STOP",
                    "entry": round(entry, 5),
                    "sl": round(sl, 5),
                    "tp": round(tp, 5),
                    "time": now.strftime("%Y-%m-%d %H:%M"),
                    "expiry": expiry.strftime("%Y-%m-%d %H:%M"),
                    "status": "ACTIVE"
                })

        except:
            continue

    return signals
