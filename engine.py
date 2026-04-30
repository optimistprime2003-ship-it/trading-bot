import requests
import datetime

API_KEY = "YOUR_TWELVEDATA_API_KEY"

PAIRS = ["EUR/USD", "GBP/USD", "USD/JPY", "GBP/JPY", "AUD/USD", "EUR/JPY"]

TIMEFRAME_ENTRY = "15min"
TIMEFRAME_TREND = "1h"


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


def calculate_ema(prices, period):
    ema = []
    k = 2 / (period + 1)

    for i in range(len(prices)):
        if i == 0:
            ema.append(prices[i])
        else:
            ema.append(prices[i] * k + ema[i-1] * (1 - k))

    return ema


def is_bullish_pin(c):
    body = abs(c["close"] - c["open"])
    lower_wick = min(c["open"], c["close"]) - c["low"]
    total = c["high"] - c["low"]
    return lower_wick >= 2 * body and c["close"] > c["open"]


def is_bearish_pin(c):
    body = abs(c["close"] - c["open"])
    upper_wick = c["high"] - max(c["open"], c["close"])
    total = c["high"] - c["low"]
    return upper_wick >= 2 * body and c["close"] < c["open"]


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

            # TREND
            buy_trend = ema8_m15[-1] > ema20_m15[-1] > ema50_m15[-1] and ema8_h1[-1] > ema20_h1[-1] > ema50_h1[-1]
            sell_trend = ema8_m15[-1] < ema20_m15[-1] < ema50_m15[-1] and ema8_h1[-1] < ema20_h1[-1] < ema50_h1[-1]

            # AVOID FLAT MARKET
            if abs(ema8_m15[-1] - ema20_m15[-1]) < 0.0003:
                continue

            # EMA TOUCH (PULLBACK)
            ema_touch = (
                abs(last["low"] - ema8_m15[-1]) < 0.0005 or
                abs(last["low"] - ema20_m15[-1]) < 0.0005 or
                abs(last["high"] - ema8_m15[-1]) < 0.0005 or
                abs(last["high"] - ema20_m15[-1]) < 0.0005
            )

            pip = 0.01 if "JPY" in pair else 0.0001

            # BUY
            if buy_trend and is_bullish_pin(last) and ema_touch:
                entry = last["high"] + 2 * pip
                sl = last["low"] - 2 * pip
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

            # SELL
            elif sell_trend and is_bearish_pin(last) and ema_touch:
                entry = last["low"] - 2 * pip
                sl = last["high"] + 2 * pip
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

        except Exception as e:
            print(f"Error on {pair}: {e}")
            continue

    return signals
