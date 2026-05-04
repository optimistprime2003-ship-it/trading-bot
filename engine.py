import requests
from datetime import datetime, timedelta

PAIRS = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD","XAUUSD"]
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
import pytz

NY_TZ = pytz.timezone("America/New_York")


def is_same_ny_day(dt1, dt2):
    return dt1.astimezone(NY_TZ).date() == dt2.astimezone(NY_TZ).date()


def generate_fake_breakout_signals():
    signals = []

    for pair in PAIRS:

        data_4h = fetch_data(pair, "4h")
        data_5m = fetch_data(pair, "5min")

        if len(data_4h) < 10 or len(data_5m) < 50:
            continue

        first_candle = get_ny_first_4h_candle(data_4h)
        if not first_candle:
            continue

        range_high = float(first_candle["high"])
        range_low = float(first_candle["low"])

        breakout_active = False
        breakout_direction = None
        breakout_extreme = None

        for i in range(2, len(data_5m)):

            candle = data_5m[i]
            prev = data_5m[i - 1]

            dt = datetime.fromisoformat(candle["datetime"])
            prev_dt = datetime.fromisoformat(prev["datetime"])

            # Only trade same NY day
            if not is_same_ny_day(dt, datetime.utcnow()):
                continue

            close = float(candle["close"])
            prev_close = float(prev["close"])
            high = float(candle["high"])
            low = float(candle["low"])

            # ===============================
            # STEP 1 — DETECT BREAKOUT
            # ===============================
            if not breakout_active:

                # Break above
                if prev_close > range_high:
                    breakout_active = True
                    breakout_direction = "above"
                    breakout_extreme = float(prev["high"])

                # Break below
                elif prev_close < range_low:
                    breakout_active = True
                    breakout_direction = "below"
                    breakout_extreme = float(prev["low"])

            # ===============================
            # STEP 2 — TRACK EXTREME
            # ===============================
            if breakout_active:

                if breakout_direction == "above":
                    breakout_extreme = max(breakout_extreme, high)

                elif breakout_direction == "below":
                    breakout_extreme = min(breakout_extreme, low)

            # ===============================
            # STEP 3 — RE-ENTRY CONFIRMATION
            # ===============================
            if breakout_active:

                now = datetime.utcnow()

                # SELL setup (break above → back inside)
                if breakout_direction == "above" and close < range_high:

                    entry = close
                    sl = breakout_extreme
                    tp = entry - (sl - entry) * 2

                    signals.append({
                        "pair": pair,
                        "strategy": "FakeBreakout",
                        "signal": "SELL",
                        "entry": round(entry, 5),
                        "sl": round(sl, 5),
                        "tp": round(tp, 5),
                        "time": str(now),
                        "status": "ACTIVE"
                    })

                    breakout_active = False

                # BUY setup (break below → back inside)
                elif breakout_direction == "below" and close > range_low:

                    entry = close
                    sl = breakout_extreme
                    tp = entry + (entry - sl) * 2

                    signals.append({
                        "pair": pair,
                        "strategy": "FakeBreakout",
                        "signal": "BUY",
                        "entry": round(entry, 5),
                        "sl": round(sl, 5),
                        "tp": round(tp, 5),
                        "time": str(now),
                        "status": "ACTIVE"
                    })

                    breakout_active = False

    return signals
