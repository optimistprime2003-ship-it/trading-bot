import requests
import os
import math
from datetime import datetime, time, timedelta
import pytz

# ==============================================================================
# CONFIGURATION & RISK PARAMETERS
# ==============================================================================
PAIRS = ["EURUSD", "USDJPY", "GBPJPY", "AUDUSD", "EURJPY", "GBPUSD", "BTCUSD"]
ACCOUNT_BALANCE = 10000.0   
RISK_PER_TRADE = 0.01       
MAX_ALLOWED_SPREAD_PIPS = 3.0 
PRIMARY_API_KEY = os.environ.get("d93af08b103e43c99034dd6362a239d3", "YOUR_API_KEY_HERE")

NY_TZ = pytz.timezone("America/New_York")

# ==============================================================================
# UTILITIES
# ==============================================================================
def get_pip_value(pair):
    return 0.01 if "JPY" in pair else 0.0001

def get_current_spread(symbol):
    try:
        url = f"https://api.twelvedata.com/quotes?symbol={symbol}&apikey={PRIMARY_API_KEY}"
        res = requests.get(url).json()
        bid, ask = float(res.get('bid', 0)), float(res.get('ask', 0))
        if bid == 0 or ask == 0: return 999 
        pip_val = get_pip_value(symbol)
        return (ask - bid) / pip_val
    except: return 999

def is_news_safe(symbol):
    """STRICTLY for Pin Bar Strategy only."""
    try:
        url = f"https://api.twelvedata.com/economic_calendar?apikey={PRIMARY_API_KEY}"
        res = requests.get(url).json()
        events = res.get("events", [])
        now = datetime.now(pytz.UTC)
        currencies = [symbol[:3], symbol[3:]]
        for event in events:
            if event.get("importance") == "High" and event.get("currency") in currencies:
                event_time = datetime.fromisoformat(event.get("date").replace("Z", "+00:00"))
                if abs((event_time - now).total_seconds()) < 7200: return False
        return True
    except: return True

def calculate_position_size(pair, risk_usd, stop_loss_pips):
    if stop_loss_pips <= 0: return 0.01
    pip_val_usd = 10.0 if "JPY" not in pair else 9.0 
    size = round(risk_usd / (stop_loss_pips * pip_val_usd), 2)
    return max(size, 0.01)

def calculate_ema(prices, period):
    if len(prices) < period: return [prices[-1]]
    k = 2 / (period + 1)
    ema_values = [sum(prices[:period]) / period]
    for p in prices[period:]:
        ema_values.append(p * k + ema_values[-1] * (1 - k))
    return ema_values

def is_valid_pinbar(op, cl, hi, lo, bullish=True):
    rng = hi - lo
    if rng == 0: return False
    if bullish:
        return (max(op, cl) <= lo + (rng * 0.40)) and ((min(op, cl) - lo) > (hi - max(op, cl)) * 2)
    else:
        return (min(op, cl) >= hi - (rng * 0.40)) and ((hi - max(op, cl)) > (min(op, cl) - lo) * 2)

def fetch_data(symbol, interval, size=100):
    try:
        url = f"https://api.twelvedata.com/time_series?symbol={symbol}&interval={interval}&outputsize={size}&apikey={PRIMARY_API_KEY}"
        res = requests.get(url, timeout=15).json()
        return list(reversed(res["values"])) if "values" in res else []
    except: return []

# ==============================================================================
# MAIN ENGINE LOGIC
# ==============================================================================
def generate_signals():
    now_ny = datetime.now(NY_TZ)
    is_ny_active = time(8, 0) <= now_ny.time() <= time(16, 0)
    signals = []

    for pair in PAIRS:
        pip_unit = get_pip_value(pair)
        
        daily_data = fetch_data(pair, "1day", 55)
        h4_data = fetch_data(pair, "4h", 20)
        m5_data = fetch_data(pair, "5min", 20)
        
        if not daily_data or not h4_data or not m5_data: continue

        # --- STRATEGY A: DAILY PIN BAR (GUARDS: NEWS & EMA) ---
        if is_news_safe(pair):
            closes = [float(x["close"]) for x in daily_data]
            last_day = daily_data[-2]
            d_op, d_cl, d_hi, d_lo = float(last_day["open"]), float(last_day["close"]), float(last_day["high"]), float(last_day["low"])
            
            e8 = calculate_ema(closes[:-1], 8)[-1]
            e20 = calculate_ema(closes[:-1], 20)[-1]
            e50 = calculate_ema(closes[:-1], 50)[-1]
            
            if e8 > e20 > e50 and d_lo <= e8 and is_valid_pinbar(d_op, d_cl, d_hi, d_lo, bullish=True):
                entry, sl = d_hi + (2 * pip_unit), d_lo - (2 * pip_unit)
                sl_pips = abs(entry - sl) / pip_unit
                lots = calculate_position_size(pair, ACCOUNT_BALANCE * RISK_PER_TRADE, sl_pips)
                signals.append({"pair": pair, "strategy": "DailyPin", "side": "BUY", "entry": round(entry, 5), "sl": round(sl, 5), "tp": round(entry + (entry-sl), 5), "lots": lots})

            elif e8 < e20 < e50 and d_hi >= e8 and is_valid_pinbar(d_op, d_cl, d_hi, d_lo, bullish=False):
                entry, sl = d_lo - (2 * pip_unit), d_hi + (2 * pip_unit)
                sl_pips = abs(entry - sl) / pip_unit
                lots = calculate_position_size(pair, ACCOUNT_BALANCE * RISK_PER_TRADE, sl_pips)
                signals.append({"pair": pair, "strategy": "DailyPin", "side": "SELL", "entry": round(entry, 5), "sl": round(sl, 5), "tp": round(entry - (sl-entry), 5), "lots": lots})

        # --- STRATEGY B: FAKE BREAKOUT (INDEPENDENT) ---
        if is_ny_active:
            range_candle = next((c for c in h4_data if c["datetime"].startswith(now_ny.strftime("%Y-%m-%d"))), None)
            
            if range_candle:
                r_hi, r_lo = float(range_candle["high"]), float(range_candle["low"])
                
                # Check current 5m candle + 4 previous (Multi-candle window)
                lookback = m5_data[-5:]
                curr = lookback[-1]
                prev_set = lookback[:-1]
                
                # FAKE HIGH (SELL)
                if float(curr["close"]) < r_hi:
                    was_outside = any(float(c["close"]) > r_hi for c in prev_set)
                    if was_outside:
                        peak_hi = max(float(c["high"]) for c in lookback)
                        entry = float(curr["close"])
                        dist_pips = (peak_hi - entry) / pip_unit
                        
                        # 25-PIP THRESHOLD RULE
                        if dist_pips > 25:
                            sl = r_hi + (1 * pip_unit) # SL at S/R level
                        else:
                            sl = peak_hi + (2 * pip_unit) # SL 2 pips above peak
                            
                        sl_dist = abs(entry - sl) / pip_unit
                        signals.append({
                            "pair": pair, "strategy": "FakeBreakout", "side": "SELL",
                            "entry": round(entry, 5), "sl": round(sl, 5),
                            "tp": round(entry - (2 * (sl_dist * pip_unit)), 5), 
                            "lots": calculate_position_size(pair, ACCOUNT_BALANCE * RISK_PER_TRADE, sl_dist)
                        })

                # FAKE LOW (BUY)
                elif float(curr["close"]) > r_lo:
                    was_outside = any(float(c["close"]) < r_lo for c in prev_set)
                    if was_outside:
                        peak_lo = min(float(c["low"]) for c in lookback)
                        entry = float(curr["close"])
                        dist_pips = (entry - peak_lo) / pip_unit
                        
                        # 25-PIP THRESHOLD RULE
                        if dist_pips > 25:
                            sl = r_lo - (1 * pip_unit) # SL at S/R level
                        else:
                            sl = peak_lo - (2 * pip_unit) # SL 2 pips below peak
                            
                        sl_dist = abs(entry - sl) / pip_unit
                        signals.append({
                            "pair": pair, "strategy": "FakeBreakout", "side": "BUY",
                            "entry": round(entry, 5), "sl": round(sl, 5),
                            "tp": round(entry + (2 * (sl_dist * pip_unit)), 5),
                            "lots": calculate_position_size(pair, ACCOUNT_BALANCE * RISK_PER_TRADE, sl_dist)
                        })

    return signals

def update_signal_status(active_signals):
    updated_signals = []
    for s in active_signals:
        pair = s["pair"]
        price_data = fetch_data(pair, "1min", 2)
        if not price_data:
            updated_signals.append(s)
            continue
            
        curr_price = float(price_data[-1]["close"])
        side = s["side"]
        
        if side == "BUY":
            if curr_price >= s["tp"]: s["status"] = "TP HIT"
            elif curr_price <= s["sl"]: s["status"] = "SL HIT"
        else:
            if curr_price <= s["tp"]: s["status"] = "TP HIT"
            elif curr_price >= s["sl"]: s["status"] = "SL HIT"
            
        updated_signals.append(s)
    return updated_signals
