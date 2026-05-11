import requests
import os
import math
from datetime import datetime, time
import pytz

# ==============================================================================
# CONFIGURATION
# ==============================================================================
PAIRS = ["EURUSD", "USDJPY", "GBPJPY", "AUDUSD", "EURJPY", "GBPUSD", "BTCUSD"]

ACCOUNT_BALANCE = 10000.0
RISK_PER_TRADE = 0.01
MAX_ALLOWED_SPREAD_PIPS = 3.0

API_KEYS = [
    os.environ.get("KEY_ONE", "d93af08b103e43c99034dd6362a239d3"),
    os.environ.get("KEY_TWO", "738fd3d524944eadba4f533fe8832525")
]

CURRENT_KEY_INDEX = 0

NY_TZ = pytz.timezone("America/New_York")

# ==============================================================================
# FETCH DATA
# ==============================================================================
def fetch_data(symbol, interval, size=100):

    global CURRENT_KEY_INDEX

    for _ in range(len(API_KEYS)):

        current_key = API_KEYS[CURRENT_KEY_INDEX]

        url = (
            f"https://api.twelvedata.com/time_series?"
            f"symbol={symbol}&interval={interval}"
            f"&outputsize={size}&apikey={current_key}"
        )

        try:

            res = requests.get(url, timeout=15).json()

            if res.get("code") == 429:
                CURRENT_KEY_INDEX = (
                    CURRENT_KEY_INDEX + 1
                ) % len(API_KEYS)
                continue

            return list(reversed(res["values"])) if "values" in res else []

        except:
            continue

    return []

# ==============================================================================
# NEWS FILTER
# ==============================================================================
def is_news_safe(symbol):

    global CURRENT_KEY_INDEX

    key = API_KEYS[CURRENT_KEY_INDEX]

    try:

        url = f"https://api.twelvedata.com/economic_calendar?apikey={key}"

        res = requests.get(url).json()

        events = res.get("events", [])

        now = datetime.now(pytz.UTC)

        curr = [symbol[:3], symbol[3:]]

        for e in events:

            if (
                e.get("importance") == "High"
                and e.get("currency") in curr
            ):

                e_time = datetime.fromisoformat(
                    e.get("date").replace("Z", "+00:00")
                )

                if abs((e_time - now).total_seconds()) < 7200:
                    return False

        return True

    except:
        return True

# ==============================================================================
# EMA
# ==============================================================================
def calculate_ema(data, period):

    ema = []

    multiplier = 2 / (period + 1)

    for i, price in enumerate(data):

        if i == 0:
            ema.append(price)

        else:
            ema.append(
                ((price - ema[i - 1]) * multiplier)
                + ema[i - 1]
            )

    return ema

# ==============================================================================
# PINBAR VALIDATION
# ==============================================================================
def is_valid_pinbar(op, cl, hi, lo, bullish=True):

    body = abs(cl - op)

    upper_wick = hi - max(op, cl)

    lower_wick = min(op, cl) - lo

    candle_range = hi - lo

    if candle_range == 0:
        return False

    if bullish:
        return (
            lower_wick > body * 2
            and upper_wick < body
        )

    return (
        upper_wick > body * 2
        and lower_wick < body
    )

# ==============================================================================
# POSITION SIZE
# ==============================================================================
def calculate_position_size(pair, risk_amount, stop_loss_pips):

    pip_value = 10

    if "JPY" in pair:
        pip_value = 9.1

    lots = risk_amount / (stop_loss_pips * pip_value)

    return round(lots, 2)

# ==============================================================================
# MAIN ENGINE
# ==============================================================================
def run_trading_bot():

    now_ny = datetime.now(NY_TZ)

    is_ny_session = (
        time(8, 0)
        <= now_ny.time()
        <= time(16, 0)
    )

    is_pinbar_check_time = now_ny.minute < 10

    signals = []

    for pair in PAIRS:

        pip_unit = 0.01 if "JPY" in pair else 0.0001

        # ======================================================
        # DAILY PINBAR STRATEGY
        # ======================================================
        if is_ny_session or is_pinbar_check_time:

            daily = fetch_data(pair, "1day", 55)

            if daily and is_news_safe(pair):

                closes = [
                    float(x["close"])
                    for x in daily
                ]

                l_day = daily[-2]

                d_op = float(l_day["open"])
                d_cl = float(l_day["close"])
                d_hi = float(l_day["high"])
                d_lo = float(l_day["low"])

                e8 = calculate_ema(closes[:-1], 8)[-1]
                e20 = calculate_ema(closes[:-1], 20)[-1]
                e50 = calculate_ema(closes[:-1], 50)[-1]

                # BUY
                if (
                    e8 > e20 > e50
                    and d_lo <= e8
                    and is_valid_pinbar(
                        d_op,
                        d_cl,
                        d_hi,
                        d_lo,
                        bullish=True
                    )
                ):

                    entry = d_hi + (2 * pip_unit)
                    sl = d_lo - (2 * pip_unit)

                    sl_p = abs(entry - sl) / pip_unit

                    signals.append({
                        "pair": pair,
                        "strategy": "DailyPin",
                        "side": "BUY",
                        "entry": round(entry, 5),
                        "sl": round(sl, 5),
                        "tp": round(entry + (entry - sl), 5),
                        "lots": calculate_position_size(
                            pair,
                            ACCOUNT_BALANCE * RISK_PER_TRADE,
                            sl_p
                        )
                    })

                # SELL
                elif (
                    e8 < e20 < e50
                    and d_hi >= e8
                    and is_valid_pinbar(
                        d_op,
                        d_cl,
                        d_hi,
                        d_lo,
                        bullish=False
                    )
                ):

                    entry = d_lo - (2 * pip_unit)
                    sl = d_hi + (2 * pip_unit)

                    sl_p = abs(entry - sl) / pip_unit

                    signals.append({
                        "pair": pair,
                        "strategy": "DailyPin",
                        "side": "SELL",
                        "entry": round(entry, 5),
                        "sl": round(sl, 5),
                        "tp": round(entry - (sl - entry), 5),
                        "lots": calculate_position_size(
                            pair,
                            ACCOUNT_BALANCE * RISK_PER_TRADE,
                            sl_p
                        )
                    })

    return signals

# ==============================================================================
# SIGNAL STATUS UPDATE
# ==============================================================================
def update_signal_status(active_signals):

    updated_signals = []

    for s in active_signals:

        price_data = fetch_data(s["pair"], "1min", 2)

        if not price_data:
            updated_signals.append(s)
            continue

        curr_p = float(price_data[-1]["close"])

        if s["side"] == "BUY":

            if curr_p >= s["tp"]:
                s["status"] = "TP HIT"

            elif curr_p <= s["sl"]:
                s["status"] = "SL HIT"

        else:

            if curr_p <= s["tp"]:
                s["status"] = "TP HIT"

            elif curr_p >= s["sl"]:
                s["status"] = "SL HIT"

        updated_signals.append(s)

    return updated_signals
