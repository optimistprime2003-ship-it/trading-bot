import requests
import os
import math
from datetime import datetime, time, timedelta
import pytz

# ==============================================================================
# 1. CONFIGURATION
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
# 2. FAILOVER DATA FETCHING
# ==============================================================================
def fetch_data(symbol, interval, size=100):
    global CURRENT_KEY_INDEX
    for _ in range(len(API_KEYS)):
        current_key = API_KEYS[CURRENT_KEY_INDEX]
        url = f"https://api.twelvedata.com/time_series?symbol={symbol}&interval={interval}&outputsize={size}&apikey={current_key}"
        try:
            res = requests.get(url, timeout=15).json()
            if res.get("code") == 429 or "api_limit_reached" in str(res).lower():
                CURRENT_KEY_INDEX = (CURRENT_KEY_INDEX + 1) % len(API_KEYS)
                continue 
            return list(reversed(res["values"])) if "values" in res else []
        except: continue
    return []

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
            if e.get("importance") == "High" and e.get("currency") in curr:
                e_time = datetime.fromisoformat(e.get("date").replace("Z", "+00:00"))
                if abs((e_time - now).total_seconds()) < 7200: return False
        return True
    except: return True

# ==============================================================================
# 3. STRATEGY ENGINE
# ==============================================================================
def run_trading_bot():
    now_ny = datetime.now(NY_TZ)
    
    # TIMING WINDOWS
    is_ny_session = time(8, 0) <= now_ny.time() <= time(16, 0)
    is_pinbar_check_time = now_ny.minute < 10 # Only check Daily Pin Bar once per hour (at the top of the hour) during off-peak
    
    signals = []

    for pair in PAIRS:
        pip_unit = 0.01 if "JPY" in pair else 0.0001
        
        # --- STRATEGY A: DAILY PIN BAR ---
        # We check this during NY session OR once an hour during the night
        if is_ny_session or is_pinbar_check_time:
            daily = fetch_data(pair, "1day", 55)
            if daily and is_news_safe(pair):
                closes = [float(x["close"]) for x in daily]
                l_day = daily[-2]
                d_op, d_cl, d_hi, d_lo = float(l_day["open"]), float(l_day["close"]), float(l_day["high"]), float(l_day["low"])
                e8, e20, e50 = calculate_ema(closes[:-1], 8)[-1], calculate_ema(closes[:-1], 20)[-1], calculate_ema(closes[:-1], 50)[-1]
                
                # Bullish Pin
                if e8 > e20 > e50 and d_lo <= e8 and is_valid_pinbar(d_op, d_cl, d_hi, d_lo, bullish=True):
                    entry, sl = d_hi + (2 * pip_unit), d_lo - (2 * pip_unit)
                    sl_p = abs(entry - sl) / pip_unit
                    signals.append({"pair": pair, "strategy": "DailyPin", "side": "BUY", "entry": round(entry, 5), "sl": round(sl, 5), "tp": round(entry + (entry-sl), 5), "lots": calculate_position_size(pair, ACCOUNT_BALANCE * RISK_PER_TRADE, sl_p)})
                
                # Bearish Pin
                elif e8 < e20 < e50 and d_hi >= e8 and is_valid_pinbar(d_op, d_cl, d_hi, d_lo, bullish=False):
                    entry, sl = d_lo - (2 * pip_unit), d_hi + (2 * pip_unit)
                    sl_p = abs(entry - sl) / pip_unit
                    signals.append({"pair": pair, "strategy": "DailyPin", "side": "SELL", "entry": round(entry, 5), "sl": round(sl, 5), "tp": round(entry - (sl-entry), 5), "lots": calculate_position_size(pair, ACCOUNT_BALANCE * RISK_PER_TRADE, sl_p)})

        # --- STRATEGY B: FAKE BREAKOUT ---
        # ONLY runs during NY session to save credits
        if is_ny_session:
            h4 = fetch_data(pair, "4h", 20)
            m5 = fetch_data(pair, "5min", 20)
            if h4 and m5:
                range_c = next((c for c in h4 if c["datetime"].startswith(now_ny.strftime("%Y-%m-%d"))), None)
                if range_c:
                    r_hi, r_lo = float(range_c["high"]), float(range_c["low"])
                    lookback = m5[-5:]
                    curr = lookback[-1]
                    prev_set = lookback[:-1]
                    
                    if float(curr["close"]) < r_hi and any(float(c["close"]) > r_hi for c in prev_set):
                        peak_hi = max(float(c["high"]) for c in lookback)
                        entry = float(curr["close"])
                        sl = (r_hi + (1 * pip_unit)) if ((peak_hi - entry)/pip_unit > 25) else (peak_hi + (2 * pip_unit))
                        sl_d = abs(entry - sl) / pip_unit
                        signals.append({"pair": pair, "strategy": "FakeBreakout", "side": "SELL", "entry": round(entry, 5), "sl": round(sl, 5), "tp": round(entry - (2 * (sl_d * pip_unit)), 5), "lots": calculate_position_size(pair, ACCOUNT_BALANCE * RISK_PER_TRADE, sl_d)})

                    elif float(curr["close"]) > r_lo and any(float(c["close"]) < r_lo for c in prev_set):
                        peak_lo = min(float(c["low"]) for c in lookback)
                        entry = float(curr["close"])
                        sl = (r_lo - (1 * pip_unit)) if ((entry - peak_lo)/pip_unit > 25) else (peak_lo - (2 * pip_unit))
                        sl_d = abs(entry - sl) / pip_unit
                        signals.append({"pair": pair, "strategy": "FakeBreakout", "side": "BUY", "entry": round(entry, 5), "sl": round(sl, 5), "tp": round(entry + (2 * (sl_d * pip_unit)), 5), "lots": calculate_position_size(pair, ACCOUNT_BALANCE * RISK_PER_TRADE, sl_d)})
    return signals

def update_signal_status(active_signals):
    # This ALWAYS runs to ensure TP/SL are tracked
    updated_signals = []
    for s in active_signals:
        price_data = fetch_data(s["pair"], "1min", 2)
        if not price_data:
            updated_signals.append(s)
            continue
        curr_p = float(price_data[-1]["close"])
        if s["side"] == "BUY":
            if curr_p >= s["tp"]: s["status"] = "TP HIT"
            elif curr_p <= s["sl"]: s["status"] = "SL HIT"
        else:
            if curr_p <= s["tp"]: s["status"] = "TP HIT"
            elif curr_p >= s["sl"]: s["status"] = "SL HIT"
        updated_signals.append(s)
    return updated_signals

# (Keep the helper functions for EMA, Pinbar validity, etc. from previous code here)
