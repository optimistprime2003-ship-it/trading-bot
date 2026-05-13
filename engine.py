import requests
import pandas as pd
import logging
import os
from itertools import cycle

# --- API ROTATION SETUP ---
# Fetch keys from environment variables
keys = [os.getenv(f"TD_API_KEY_{i}") for i in range(1, 4) if os.getenv(f"TD_API_KEY_{i}")]
if not keys:
    logging.error("CRITICAL: No API keys found in environment variables!")
key_cycle = cycle(keys)

# --- CONFIGURATION ---
PINBAR_PAIRS = ["EUR/USD", "AUD/USD", "USD/JPY", "GBP/USD"]
RANGE_PAIRS = ["BTC/USD", "XAU/USD"]

def get_data(symbol, interval, outputsize=50):
    current_key = next(key_cycle)
    url = f"https://api.twelvedata.com/time_series?symbol={symbol}&interval={interval}&outputsize={outputsize}&apikey={current_key}"
    
    try:
        res = requests.get(url).json()
        if 'values' not in res:
            logging.warning(f"Key {current_key[-4:]} failed for {symbol}. Trying next...")
            return None
        df = pd.DataFrame(res['values']).astype(float)
        return df.iloc[::-1] # Chronological order
    except Exception as e:
        logging.error(f"Request error: {e}")
        return None

def is_pin_bar(open_p, high, low, close):
    body = abs(open_p - close)
    total_range = high - low
    if total_range == 0: return False
    return (body / total_range) <= 0.30 # Body is 30% or less of the candle

def check_strategies():
    signals = []

    # 1. PIN BAR STRATEGY (1-DAY TIME FRAME)
    for symbol in PINBAR_PAIRS:
        df = get_data(symbol, "1day")
        if df is None: continue
        
        # EMAs for Trend Filter
        df['ema8'] = df['close'].ewm(span=8, adjust=False).mean()
        df['ema20'] = df['close'].ewm(span=20, adjust=False).mean()
        df['ema50'] = df['close'].ewm(span=50, adjust=False).mean()
        
        last = df.iloc[-1]
        
        # Trend Fan: 8 > 20 > 50 (Buy) or 8 < 20 < 50 (Sell)
        bullish_fan = last['ema8'] > last['ema20'] > last['ema50']
        bearish_fan = last['ema8'] < last['ema20'] < last['ema50']
        
        # Proximity: 0.05% buffer (doesn't have to touch perfectly)
        buffer = last['close'] * 0.0005 
        
        if is_pin_bar(last['open'], last['high'], last['low'], last['close']):
            # Buy logic
            if bullish_fan and last['low'] <= (last['ema8'] + buffer):
                signals.append({"symbol": symbol, "type": "BUY", "strat": "1D Pin Bar"})
            # Sell logic
            elif bearish_fan and last['high'] >= (last['ema8'] - buffer):
                signals.append({"symbol": symbol, "type": "SELL", "strat": "1D Pin Bar"})

    # 2. 4H RANGE STRATEGY (4H FOR RANGE / 5M FOR SIGNAL)
    for symbol in RANGE_PAIRS:
        df_4h = get_data(symbol, "4h", outputsize=2)
        df_5m = get_data(symbol, "5min", outputsize=2)
        if df_4h is None or df_5m is None: continue

        range_high = df_4h.iloc[-2]['high'] # High of the previous 4H candle
        range_low = df_4h.iloc[-2]['low']   # Low of the previous 4H candle
        current_5m = df_5m.iloc[-1]

        # Fakeout Logic: Price broke the range but closed back inside
        if current_5m['low'] < range_low and current_5m['close'] > range_low:
            signals.append({"symbol": symbol, "type": "BUY", "strat": "4H Range Fakeout"})
        
        elif current_5m['high'] > range_high and current_5m['close'] < range_high:
            signals.append({"symbol": symbol, "type": "SELL", "strat": "4H Range Fakeout"})

    return signals
