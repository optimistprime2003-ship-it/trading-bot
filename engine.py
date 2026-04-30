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
    return lower_wick >= 2 * body and c["close"] > c["open"]


def is_bearish_pin(c):
    body = abs(c["close"] - c["open"])
    upper_wick = c["high"] - max(c["open"], c["close"])
    return upper_wick >= 2 * body and c["close"] < c["open"]


# 🔥 MAIN STRATEGY
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


# 🔥 TRACK TP / SL / EXPIRY
def update_signal_status(signals):
    updated = []

    for s in signals:
        try:
            url = f"https://api.twelvedata.com/price?symbol={s['pair']}&apikey={API_KEY}"
            price_data = requests.get(url).json()

            if "price" not in price_data:
                updated.append(s)
                continue

            price = float(price_data["price"])

            if s["status"] != "ACTIVE":
                updated.append(s)
                continue

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

            expiry_time = datetime.datetime.strptime(s["expiry"], "%Y-%m-%d %H:%M")
            if datetime.datetime.utcnow() > expiry_time and s["status"] == "ACTIVE":
                s["status"] = "EXPIRED"

            updated.append(s)

        except:
            updated.append(s)

    return updated
    def backtest_strategy(pair="EUR/USD"):
    results = []

    m15 = get_candles(pair, TIMEFRAME_ENTRY, 500)
    h1 = get_candles(pair, TIMEFRAME_TREND, 500)

    if len(m15) < 100 or len(h1) < 100:
        return {"error": "Not enough data"}

    closes_m15 = [c["close"] for c in m15]
    closes_h1 = [c["close"] for c in h1]

    ema8_m15 = calculate_ema(closes_m15, 8)
    ema20_m15 = calculate_ema(closes_m15, 20)
    ema50_m15 = calculate_ema(closes_m15, 50)

    ema8_h1 = calculate_ema(closes_h1, 8)
    ema20_h1 = calculate_ema(closes_h1, 20)
    ema50_h1 = calculate_ema(closes_h1, 50)

    pip = 0.01 if "JPY" in pair else 0.0001

    wins = 0
    losses = 0
    total_r = 0

    for i in range(60, len(m15) - 10):
        last = m15[i]

        buy_trend = ema8_m15[i] > ema20_m15[i] > ema50_m15[i] and ema8_h1[i] > ema20_h1[i] > ema50_h1[i]
        sell_trend = ema8_m15[i] < ema20_m15[i] < ema50_m15[i] and ema8_h1[i] < ema20_h1[i] < ema50_h1[i]

        if abs(ema8_m15[i] - ema20_m15[i]) < 0.0003:
            continue

        ema_touch = (
            abs(last["low"] - ema8_m15[i]) < 0.0005 or
            abs(last["low"] - ema20_m15[i]) < 0.0005 or
            abs(last["high"] - ema8_m15[i]) < 0.0005 or
            abs(last["high"] - ema20_m15[i]) < 0.0005
        )

        entry = None
        sl = None
        tp = None
        direction = None

        if buy_trend and is_bullish_pin(last) and ema_touch:
            entry = last["high"] + 2 * pip
            sl = last["low"] - 2 * pip
            tp = entry + (entry - sl) * 2
            direction = "BUY"

        elif sell_trend and is_bearish_pin(last) and ema_touch:
            entry = last["low"] - 2 * pip
            sl = last["high"] + 2 * pip
            tp = entry - (sl - entry) * 2
            direction = "SELL"

        if not entry:
            continue

        # 🔁 simulate forward candles
        outcome = None

        for j in range(i + 1, i + 10):
            candle = m15[j]

            if direction == "BUY":
                if candle["low"] <= sl:
                    outcome = "SL"
                    break
                if candle["high"] >= tp:
                    outcome = "TP"
                    break

            elif direction == "SELL":
                if candle["high"] >= sl:
                    outcome = "SL"
                    break
                if candle["low"] <= tp:
                    outcome = "TP"
                    break

        if outcome == "TP":
            wins += 1
            total_r += 2
            results.append("TP")

        elif outcome == "SL":
            losses += 1
            total_r -= 1
            results.append("SL")

    total = wins + losses
    win_rate = (wins / total * 100) if total > 0 else 0

    return {
        "pair": pair,
        "trades": total,
        "wins": wins,
        "losses": losses,
        "win_rate": round(win_rate, 2),
        "net_R": total_r
    }
