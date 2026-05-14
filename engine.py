import requests
import pandas as pd
import logging
import os
from itertools import cycle

# --- CONFIGURATION ---
PINBAR_PAIRS = ["EUR/USD", "AUD/USD", "USD/JPY", "GBP/USD"]
RANGE_PAIRS = ["BTC/USD", "XAU/USD"]
NY_SESSION_START = "08:00:00" # FIXED: New York Open

# --- API ROTATION ---
keys = [os.getenv(f"TD_API_KEY_{i}") for i in range(1, 4) if os.getenv(f"TD_API_KEY_{i}")]
key_cycle = cycle(keys) if keys else cycle(["DEMO_KEY"])

def get_data(symbol, interval, outputsize=50):
    current_key = next(key_cycle)
    # FORCE NEW YORK TIMEZONE
    url = f"https://api.twelvedata.com/time_series?symbol={symbol}&interval={interval}&outputsize={outputsize}&apikey={current_key}&timezone=America/New_York"
    
    try:
        res = requests.get(url).json()
        if 'values' not in res: return None
        df = pd.DataFrame(res['values'])
        df[['open', 'high', 'low', 'close']] = df[['open', 'high', 'low', 'close']].astype(float)
        return df.iloc[::-1] 
    except Exception as e:
        logging.error(f"Error: {e}")
        return None

def is_pin_bar(open_p, high, low, close):
    body = abs(open_p - close)
    total_range = high - low
    if total_range == 0: return False
    return (body / total_range) <= 0.30

def check_strategies():
    signals = []

    # 1. PIN BAR (1D - NY CLOSE)
    for symbol in PINBAR_PAIRS:
        df = get_data(symbol, "1day")
        if df is None or df.empty: continue
        
        df['ema8'] = df['close'].ewm(span=8, adjust=False).mean()
        df['ema20'] = df['close'].ewm(span=20, adjust=False).mean()
        df['ema50'] = df['close'].ewm(span=50, adjust=False).mean()
        
        last = df.iloc[-1]
        bullish_fan = last['ema8'] > last['ema20'] > last['ema50']
        bearish_fan = last['ema8'] < last['ema20'] < last['ema50']
        buffer = last['close'] * 0.0005 
        
        if is_pin_bar(last['open'], last['high'], last['low'], last['close']):
            if bullish_fan and last['low'] <= (last['ema8'] + buffer):
                signals.append({"symbol": symbol, "type": "BUY", "strat": "1D Pin Bar"})
            elif bearish_fan and last['high'] >= (last['ema8'] - buffer):
                signals.append({"symbol": symbol, "type": "SELL", "strat": "1D Pin Bar"})

    # 2. H4 RANGE FAKEOUT (BTC/XAU - NY OPEN)
    for symbol in RANGE_PAIRS:
        df_4h = get_data(symbol, "4h", outputsize=15) # Pull enough to find 08:00
        df_5m = get_data(symbol, "5min", outputsize=2)
        if df_4h is None or df_5m is None: continue

        # Find the 8:00 AM NY candle specifically
        session_data = df_4h[df_4h['datetime'].str.contains(NY_SESSION_START)]
        if session_data.empty: continue
            
        target = session_data.iloc[-1]
        r_high, r_low = target['high'], target['low']
        curr = df_5m.iloc[-1]

        if curr['low'] < r_low and curr['close'] > r_low:
            signals.append({"symbol": symbol, "type": "BUY", "strat": "H4 NY Fakeout"})
        elif curr['high'] > r_high and curr['close'] < r_high:
            signals.append({"symbol": symbol, "type": "SELL", "strat": "H4 NY Fakeout"})

    return signals
