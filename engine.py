import requests
import pandas as pd
import logging
import os
from itertools import cycle
from datetime import datetime

# =========================================================
# CONFIGURATION
# =========================================================

PINBAR_PAIRS = ["EUR/USD", "AUD/USD", "USD/JPY", "GBP/USD"]
RANGE_PAIRS = ["BTC/USD", "ETH/USD"]

NY_SESSION_START = "08:00:00"

# =========================================================
# API ROTATION
# =========================================================

keys = [
    os.getenv(f"TD_API_KEY_{i}")
    for i in range(1, 5)
    if os.getenv(f"TD_API_KEY_{i}")
]

key_cycle = cycle(keys) if keys else cycle(["DEMO_KEY"])

# =========================================================
# DAILY RANGE STORAGE
# =========================================================

daily_ranges = {}

# =========================================================
# DATA FETCHER
# =========================================================

def get_data(symbol, interval, outputsize=50):

    current_key = next(key_cycle)

    url = (
        f"https://api.twelvedata.com/time_series?"
        f"symbol={symbol}"
        f"&interval={interval}"
        f"&outputsize={outputsize}"
        f"&apikey={current_key}"
        f"&timezone=America/New_York"
    )

    try:

        res = requests.get(url).json()

        if 'values' not in res:
            logging.error(f"No values returned for {symbol} {interval}")
            return None

        df = pd.DataFrame(res['values'])

        df[['open', 'high', 'low', 'close']] = (
            df[['open', 'high', 'low', 'close']].astype(float)
        )

        df = df.iloc[::-1].reset_index(drop=True)

        return df

    except Exception as e:

        logging.error(f"Data Error: {e}")

        return None

# =========================================================
# PIN BAR DETECTION
# =========================================================

def is_pin_bar(open_p, high, low, close):

    body = abs(open_p - close)

    total_range = high - low

    if total_range == 0:
        return False

    return (body / total_range) <= 0.30

# =========================================================
# MAIN STRATEGY ENGINE
# =========================================================

def check_strategies():

    signals = []

    # =====================================================
    # 1. DAILY PIN BAR STRATEGY
    # (UNCHANGED CORE LOGIC)
    # =====================================================

    for symbol in PINBAR_PAIRS:

        df = get_data(symbol, "1day")

        if df is None or df.empty:
            continue

        # EMA CALCULATIONS

        df['ema8'] = df['close'].ewm(span=8, adjust=False).mean()
        df['ema20'] = df['close'].ewm(span=20, adjust=False).mean()
        df['ema50'] = df['close'].ewm(span=50, adjust=False).mean()

        last = df.iloc[-1]

        bullish_fan = (
            last['ema8'] > last['ema20'] > last['ema50']
        )

        bearish_fan = (
            last['ema8'] < last['ema20'] < last['ema50']
        )

        buffer = last['close'] * 0.0005

        # =================================================
        # PIN BAR BUY
        # =================================================

        if is_pin_bar(
            last['open'],
            last['high'],
            last['low'],
            last['close']
        ):

            if bullish_fan and last['low'] <= (last['ema8'] + buffer):

                entry = last['close']

                sl = last['low']

                risk = abs(entry - sl)

                tp = entry + risk

                signals.append({

                    "symbol": symbol,
                    "type": "BUY",

                    "entry": round(entry, 5),
                    "sl": round(sl, 5),
                    "tp": round(tp, 5),

                    "rr": "1:1",

                    "strat": "1D Pin Bar",

                    "time": last['datetime']
                })

            # =============================================
            # PIN BAR SELL
            # =============================================

            elif bearish_fan and last['high'] >= (last['ema8'] - buffer):

                entry = last['close']

                sl = last['high']

                risk = abs(sl - entry)

                tp = entry - risk

                signals.append({

                    "symbol": symbol,
                    "type": "SELL",

                    "entry": round(entry, 5),
                    "sl": round(sl, 5),
                    "tp": round(tp, 5),

                    "rr": "1:1",

                    "strat": "1D Pin Bar",

                    "time": last['datetime']
                })

    # =====================================================
    # 2. H4 RANGE + 5M FAKE BREAKOUT RE-ENTRY STRATEGY
    # =====================================================

    for symbol in RANGE_PAIRS:

        try:

            # =============================================
            # FETCH DATA
            # =============================================

            df_4h = get_data(symbol, "4h", outputsize=20)

            df_5m = get_data(symbol, "5min", outputsize=100)

            if df_4h is None or df_5m is None:
                continue

            if df_4h.empty or df_5m.empty:
                continue

            # =============================================
            # TODAY DATE
            # =============================================

            today = datetime.now().strftime("%Y-%m-%d")

            # =============================================
            # CREATE / RESET DAILY RANGE
            # =============================================

            if (
                symbol not in daily_ranges
                or daily_ranges[symbol]["date"] != today
            ):

                session_data = df_4h[
                    df_4h['datetime'].str.contains(NY_SESSION_START)
                ]

                if session_data.empty:
                    logging.warning(f"No NY candle found for {symbol}")
                    continue

                target = session_data.iloc[-1]

                daily_ranges[symbol] = {

                    "date": today,

                    "high": target['high'],

                    "low": target['low'],

                    "breakout_state": None
                }

                logging.info(
                    f"{symbol} NY Range Set | "
                    f"HIGH={target['high']} "
                    f"LOW={target['low']}"
                )

            # =============================================
            # FIXED DAILY RANGE
            # =============================================

            range_high = daily_ranges[symbol]["high"]

            range_low = daily_ranges[symbol]["low"]

            breakout_state = daily_ranges[symbol].get(
                "breakout_state",
                None
            )

            # =============================================
            # CHECK RECENT 5M CANDLES
            # =============================================

            recent_candles = df_5m.tail(20)

            for i in range(len(recent_candles)):

                candle = recent_candles.iloc[i]

                # =========================================
                # VALID BODY BREAKOUT DETECTION
                # =========================================

                bullish_body_break = (
                    candle['close'] > range_high
                    and candle['open'] > range_high
                )

                bearish_body_break = (
                    candle['close'] < range_low
                    and candle['open'] < range_low
                )

                # =========================================
                # IGNORE WICK-ONLY BREAKOUTS
                # =========================================

                wick_break_high = (
                    candle['high'] > range_high
                    and candle['close'] <= range_high
                )

                wick_break_low = (
                    candle['low'] < range_low
                    and candle['close'] >= range_low
                )

                # =========================================
                # STORE BREAKOUT STATE
                # =========================================

                if bullish_body_break:

                    breakout_state = "outside_above"

                    daily_ranges[symbol][
                        "breakout_state"
                    ] = breakout_state

                    continue

                elif bearish_body_break:

                    breakout_state = "outside_below"

                    daily_ranges[symbol][
                        "breakout_state"
                    ] = breakout_state

                    continue

                # Ignore wick-only breakouts
                elif wick_break_high or wick_break_low:

                    continue

                # =========================================
                # VALID RE-ENTRY CONDITIONS
                # =========================================

                sell_reentry = (

                    breakout_state == "outside_above"

                    and candle['close'] < range_high
                )

                buy_reentry = (

                    breakout_state == "outside_below"

                    and candle['close'] > range_low
                )

                # =========================================
                # SELL SIGNAL
                # =========================================

                if sell_reentry:

                    entry = candle['close']

                    sl = range_high

                    risk = abs(sl - entry)

                    tp = entry - (risk * 2)

                    signals.append({

                        "symbol": symbol,

                        "type": "SELL",

                        "entry": round(entry, 2),

                        "sl": round(sl, 2),

                        "tp": round(tp, 2),

                        "rr": "1:2",

                        "strat": "Fake Breakout Re-entry",

                        "time": candle['datetime']
                    })

                    daily_ranges[symbol][
                        "breakout_state"
                    ] = None

                    break

                # =========================================
                # BUY SIGNAL
                # =========================================

                elif buy_reentry:

                    entry = candle['close']

                    sl = range_low

                    risk = abs(entry - sl)

                    tp = entry + (risk * 2)

                    signals.append({

                        "symbol": symbol,

                        "type": "BUY",

                        "entry": round(entry, 2),

                        "sl": round(sl, 2),

                        "tp": round(tp, 2),

                        "rr": "1:2",

                        "strat": "Fake Breakout Re-entry",

                        "time": candle['datetime']
                    })

                    daily_ranges[symbol][
                        "breakout_state"
                    ] = None

                    break

        except Exception as e:

            logging.error(f"{symbol} Strategy Error: {e}")

    return signals
