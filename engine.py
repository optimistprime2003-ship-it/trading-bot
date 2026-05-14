import requests
import pandas as pd
import logging
import os
from itertools import cycle
from datetime import datetime

# --- CONFIGURATION ---
PINBAR_PAIRS = ["EUR/USD", "AUD/USD", "USD/JPY", "GBP/USD"]
RANGE_PAIRS = ["BTC/USD", "XAU/USD"]

NY_SESSION_START = "08:00:00"

# --- API ROTATION ---
keys = [os.getenv(f"TD_API_KEY_{i}") for i in range(1, 4) if os.getenv(f"TD_API_KEY_{i}")]
key_cycle = cycle(keys) if keys else cycle(["DEMO_KEY"])

# --- DAILY RANGE STORAGE ---
daily_ranges = {}

# ----------------------------------------
# DATA FETCHER
# ----------------------------------------

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

# ----------------------------------------
# PIN BAR STRATEGY
# (UNCHANGED EXACTLY AS REQUESTED)
# ----------------------------------------

def is_pin_bar(open_p, high, low, close):

    body = abs(open_p - close)
    total_range = high - low

    if total_range == 0:
        return False

    return (body / total_range) <= 0.30

# ----------------------------------------
# MAIN STRATEGY ENGINE
# ----------------------------------------

def check_strategies():

    signals = []

    # ==================================================
    # 1. DAILY PIN BAR STRATEGY
    # (LEFT UNTOUCHED EXACTLY AS REQUESTED)
    # ==================================================

    for symbol in PINBAR_PAIRS:

        df = get_data(symbol, "1day")

        if df is None or df.empty:
            continue

        df['ema8'] = df['close'].ewm(span=8, adjust=False).mean()
        df['ema20'] = df['close'].ewm(span=20, adjust=False).mean()
        df['ema50'] = df['close'].ewm(span=50, adjust=False).mean()

        last = df.iloc[-1]

        bullish_fan = last['ema8'] > last['ema20'] > last['ema50']
        bearish_fan = last['ema8'] < last['ema20'] < last['ema50']

        buffer = last['close'] * 0.0005

        if is_pin_bar(last['open'], last['high'], last['low'], last['close']):

            if bullish_fan and last['low'] <= (last['ema8'] + buffer):

                signals.append({
                    "symbol": symbol,
                    "type": "BUY",
                    "strat": "1D Pin Bar"
                })

            elif bearish_fan and last['high'] >= (last['ema8'] - buffer):

                signals.append({
                    "symbol": symbol,
                    "type": "SELL",
                    "strat": "1D Pin Bar"
                })

    # ==================================================
    # 2. H4 RANGE + 5M ENTRY LOGIC
    # ==================================================

    for symbol in RANGE_PAIRS:

        try:

            # ------------------------------------------
            # GET DATA
            # ------------------------------------------

            df_4h = get_data(symbol, "4h", outputsize=20)
            df_5m = get_data(symbol, "5min", outputsize=100)

            if df_4h is None or df_5m is None:
                continue

            if df_4h.empty or df_5m.empty:
                continue

            # ------------------------------------------
            # GET TODAY DATE
            # ------------------------------------------

            today = datetime.now().strftime("%Y-%m-%d")

            # ------------------------------------------
            # CREATE DAILY RANGE ONLY ONCE
            # ------------------------------------------

            if symbol not in daily_ranges:

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
                    "low": target['low']
                }

                logging.info(
                    f"{symbol} Range Set | "
                    f"HIGH={target['high']} "
                    f"LOW={target['low']}"
                )

            # ------------------------------------------
            # RESET RANGE EACH NEW DAY
            # ------------------------------------------

            elif daily_ranges[symbol]["date"] != today:

                session_data = df_4h[
                    df_4h['datetime'].str.contains(NY_SESSION_START)
                ]

                if session_data.empty:
                    continue

                target = session_data.iloc[-1]

                daily_ranges[symbol] = {
                    "date": today,
                    "high": target['high'],
                    "low": target['low']
                }

                logging.info(
                    f"{symbol} New Daily Range | "
                    f"HIGH={target['high']} "
                    f"LOW={target['low']}"
                )

            # ------------------------------------------
            # USE FIXED DAILY RANGE
            # ------------------------------------------

            r_high = daily_ranges[symbol]["high"]
            r_low = daily_ranges[symbol]["low"]

            # ------------------------------------------
            # CHECK MULTIPLE 5M CANDLES
            # ENTIRE DAY
            # ------------------------------------------

            recent_candles = df_5m.tail(20)

            tolerance_high = r_high * 0.0015
            tolerance_low = r_low * 0.0015

            for i in range(1, len(recent_candles)):

                prev = recent_candles.iloc[i - 1]
                curr = recent_candles.iloc[i]

                # ======================================
                # BUY SETUP
                # ======================================

                breakout_low = (
                    prev['low'] < (r_low + tolerance_low)
                )

                reclaim_buy = (
                    curr['close'] >= (r_low - tolerance_low)
                )

                if breakout_low and reclaim_buy:

                    signals.append({
                        "symbol": symbol,
                        "type": "BUY",
                        "strat": "H4 NY Fakeout"
                    })

                    break

                # ======================================
                # SELL SETUP
                # ======================================

                breakout_high = (
                    prev['high'] > (r_high - tolerance_high)
                )

                reclaim_sell = (
                    curr['close'] <= (r_high + tolerance_high)
                )

                if breakout_high and reclaim_sell:

                    signals.append({
                        "symbol": symbol,
                        "type": "SELL",
                        "strat": "H4 NY Fakeout"
                    })

                    break

        except Exception as e:

            logging.error(f"{symbol} Strategy Error: {e}")

    return signals
