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
    # 2. H4 RANGE + 5M HYBRID FAKE BREAKOUT STRATEGY
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

                    "breakout_state": None,

                    "breakout_index": None
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

            breakout_index = daily_ranges[symbol].get(
                "breakout_index",
                None
            )

            # =============================================
            # CHECK RECENT 5M CANDLES
            # =============================================

            recent_candles = df_5m.tail(20)

            for i in range(len(recent_candles)):

                candle = recent_candles.iloc[i]

                # =========================================
                # HYBRID BODY BREAKOUT DETECTION
                # SMALL FAKEOUTS ACCEPTED
                # =========================================

                bullish_body_break = (
                    candle['close'] > range_high
                )

                bearish_body_break = (
                    candle['close'] < range_low
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

                    daily_ranges[symbol][
                        "breakout_index"
                    ] = i

                    continue

                elif bearish_body_break:

                    breakout_state = "outside_below"

                    daily_ranges[symbol][
                        "breakout_state"
                    ] = breakout_state

                    daily_ranges[symbol][
                        "breakout_index"
                    ] = i

                    continue

                # =========================================
                # IGNORE WICK-ONLY BREAKOUTS
                # =========================================

                elif wick_break_high or wick_break_low:

                    continue

                # =========================================
                # INSTANT RECLAIM ONLY
                # MUST RECLAIM NEXT CANDLE
                # =========================================

                sell_reentry = (

                    breakout_state == "outside_above"

                    and breakout_index is not None

                    and i == breakout_index + 1

                    and candle['close'] < range_high
                )

                buy_reentry = (

                    breakout_state == "outside_below"

                    and breakout_index is not None

                    and i == breakout_index + 1

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

                        "strat": "Hybrid Fake Breakout",

                        "time": candle['datetime']
                    })

                    daily_ranges[symbol][
                        "breakout_state"
                    ] = None

                    daily_ranges[symbol][
                        "breakout_index"
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

                        "strat": "Hybrid Fake Breakout",

                        "time": candle['datetime']
                    })

                    daily_ranges[symbol][
                        "breakout_state"
                    ] = None

                    daily_ranges[symbol][
                        "breakout_index"
                    ] = None

                    break

        except Exception as e:

            logging.error(f"{symbol} Strategy Error: {e}")

    return signals
    # =========================================================
# GLOBAL STORAGE (Keeps track of trades across cycles)
# =========================================================
active_trades = []
trade_history = []

def monitor_active_trades():
    """
    Loops through all open trades, fetches fresh data, checks if TP/SL 
    was hit, and updates the global trade_history.
    """
    global active_trades, trade_history
    remaining_trades = []

    for trade in active_trades:
        symbol = trade["symbol"]
        # Determine interval based on strategy type
        interval = "5min" if trade["strat"] == "Hybrid Fake Breakout" else "1day"
        
        # Fetch the most recent data row
        df = get_data(symbol, interval, outputsize=2)
        if df is None or df.empty:
            remaining_trades.append(trade)
            continue
            
        last_candle = df.iloc[-1]
        current_close = last_candle['close']
        high = last_candle['high']
        low = last_candle['low']

        was_hit = False
        result_status = "PENDING"

        # Check BUY trade conditions
        if trade["type"] == "BUY":
            if high >= trade["tp"]:
                was_hit = True
                result_status = "WIN"
            elif low <= trade["sl"]:
                was_hit = True
                result_status = "LOSS"

        # Check SELL trade conditions
        elif trade["type"] == "SELL":
            if low <= trade["tp"]:
                was_hit = True
                result_status = "WIN"
            elif high >= trade["sl"]:
                was_hit = True
                result_status = "LOSS"

        if was_hit:
            # Move to history with final details
            trade["result"] = result_status
            trade["close_time"] = last_candle['datetime']
            trade_history.append(trade)
        else:
            # Still open, keep tracking it
            remaining_trades.append(trade)

    active_trades = remaining_trades

# =========================================================
# METRICS CALCULATOR
# =========================================================
def calculate_metrics():
    """
    Computes real-time stats from the trade_history list for your frontend.
    """
    global trade_history
    
    total_signals = len(trade_history) + len(active_trades)
    closed_trades = len(trade_history)
    
    if closed_trades == 0:
        win_rate = "0%"
    else:
        wins = sum(1 for t in trade_history if t["result"] == "WIN")
        win_rate = f"{round((wins / closed_trades) * 100, 1)}%"
        
    return {
        "TOTAL": total_signals,
        "WINRATE": win_rate,
        "LAST_SCAN": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
                
