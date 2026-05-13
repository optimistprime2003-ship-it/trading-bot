import requests
import os
import logging
from datetime import datetime, time
import pytz

# ==============================================================================
# CONFIGURATION
# ==============================================================================
# 6 Forex pairs + 2 Cryptos [cite: 75, 172]
PAIRS = ["EURUSD", "USDJPY", "GBPJPY", "AUDUSD", "EURJPY", "GBPUSD", "BTC/USD", "XAU/USD"]

# API Keys from Environment Variables for Render
API_KEYS = [
    os.environ.get("TWELVE_DATA_KEY_ONE", "d93af08b103e43c99034dd6362a239d3"),
    os.environ.get("TWELVE_DATA_KEY_TWO", "738fd3d524944eadba4f533fe8832525")
]
CURRENT_KEY_INDEX = 0

NY_TZ = pytz.timezone("America/New_York")

# ==============================================================================
# DATA FETCHING WITH API ROTATION
# ==============================================================================
def fetch_data(symbol, interval, size=100):
    global CURRENT_KEY_INDEX
    
    # Try each key once
    for _ in range(len(API_KEYS)):
        current_key = API_KEYS[CURRENT_KEY_INDEX]
        url = f"https://api.twelvedata.com/time_series?symbol={symbol}&interval={interval}&outputsize={size}&apikey={current_key}"
        
        try:
            res = requests.get(url, timeout=15).json()
            
            # Handle Rate Limit (429) by switching keys
            if res.get("code") == 429:
                logging.warning(f"API Key {CURRENT_KEY_INDEX} rate limited. Switching...")
                CURRENT_KEY_INDEX = (CURRENT_KEY_INDEX + 1) % len(API_KEYS)
                continue
            
            return list(reversed(res["values"])) if "values" in res else []
        except Exception as e:
            logging.error(f"Fetch Error: {e}")
            continue
            
    return []

# ==============================================================================
# STRATEGY 1: DAILY PINBAR (1:1 Target)
# ==============================================================================
def get_daily_pinbar_signals(pair, daily_data):
    """Rules from Sample Trading Plan [cite: 92-128]"""
    if len(daily_data) < 55: return None
    
    closes = [float(x["close"]) for x in daily_data]
    l_day = daily_data[-2] # Previous day's closed candle
    
    d_op, d_cl = float(l_day["open"]), float(l_day["close"])
    d_hi, d_lo = float(l_day["high"]), float(l_day["low"])
    candle_range = d_hi - d_lo
    if candle_range == 0: return None
    
    # Pips calculation (Handles Crypto and JPY)
    pip_unit = 1.0 if "USD" in pair and "/" in pair else (0.01 if "JPY" in pair else 0.0001)

    # EMA Trend [cite: 98, 115]
    e8 = calculate_ema(closes[:-1], 8)[-1]
    e20 = calculate_ema(closes[:-1], 20)[-1]
    e50 = calculate_ema(closes[:-1], 50)[-1]

    # SELL: Trend down, Price touches 8 EMA, Pinbar body in top 30% [cite: 94-104]
    if e8 < e20 < e50 and d_hi >= e8:
        if min(d_op, d_cl) >= (d_hi - (candle_range * 0.30)):
            entry = d_lo - (2 * pip_unit)
            sl = d_hi + (2 * pip_unit)
            return {"strategy": "DailyPin", "side": "SELL", "entry": entry, "sl": sl, "tp": entry - (sl - entry)}

    # BUY: Trend up, Price touches 8 EMA, Pinbar body in bottom 30% [cite: 111-122]
    elif e8 > e20 > e50 and d_lo <= e8:
        if max(d_op, d_cl) <= (d_lo + (candle_range * 0.30)):
            entry = d_hi + (2 * pip_unit)
            sl = d_lo - (2 * pip_unit)
            return {"strategy": "DailyPin", "side": "BUY", "entry": entry, "sl": sl, "tp": entry + (entry - sl)}
    
    return None

# ==============================================================================
# STRATEGY 2: 4H RANGE FAKE BREAKOUT (2:1 Target)
# ==============================================================================
def get_4h_range_signals(pair, h4_data, m5_data):
    """Rules from Complete 4-Hour Range Strategy [cite: 144-163]"""
    if not h4_data or len(m5_data) < 2: return None

    # Mark the high/low of the first 4H candle of the day [cite: 151]
    range_h = float(h4_data[0]["high"])
    range_l = float(h4_data[0]["low"])

    prev_m5_cl = float(m5_data[-2]["close"])
    curr_m5_cl = float(m5_data[-1]["close"])

    # SELL: Close outside high, then close back inside [cite: 157]
    if prev_m5_cl > range_h and curr_m5_cl < range_h:
        sl = range_h # Default SL at breakout high [cite: 160]
        risk = sl - curr_m5_cl
        return {"strategy": "4H_Range", "side": "SELL", "entry": curr_m5_cl, "sl": sl, "tp": curr_m5_cl - (2 * risk)}

    # BUY: Close outside low, then close back inside [cite: 158]
    if prev_m5_cl < range_l and curr_m5_cl > range_l:
        sl = range_l # Default SL at breakout low [cite: 160]
        risk = curr_m5_cl - sl
        return {"strategy": "4H_Range", "side": "BUY", "entry": curr_m5_cl, "sl": sl, "tp": curr_m5_cl + (2 * risk)}

    return None

def calculate_ema(data, period):
    ema = []
    m = 2 / (period + 1)
    for i, p in enumerate(data):
        if i == 0: ema.append(p)
        else: ema.append(((p - ema[i-1]) * m) + ema[i-1])
    return ema

def run_trading_bot():
    all_signals = []
    for pair in PAIRS:
        daily = fetch_data(pair, "1day", 60)
        h4 = fetch_data(pair, "4h", 10)
        m5 = fetch_data(pair, "5min", 20)
        
        s1 = get_daily_pinbar_signals(pair, daily)
        if s1: 
            s1["pair"] = pair
            all_signals.append(s1)
            
        s2 = get_4h_range_signals(pair, h4, m5)
        if s2: 
            s2["pair"] = pair
            all_signals.append(s2)
            
    return all_signals

def update_signal_status(active_signals):
    # Logic to check current price against TP/SL and update status
    for s in active_signals:
        price_data = fetch_data(s["pair"], "1min", 1)
        if not price_data: continue
        curr_p = float(price_data[-1]["close"])
        
        if s["side"] == "BUY":
            if curr_p >= s["tp"]: s["status"] = "TP HIT"
            elif curr_p <= s["sl"]: s["status"] = "SL HIT"
        else:
            if curr_p <= s["tp"]: s["status"] = "TP HIT"
            elif curr_p >= s["sl"]: s["status"] = "SL HIT"
    return active_signals
