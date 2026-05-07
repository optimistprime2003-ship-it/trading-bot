import requests
import os
import math
from datetime import datetime, time, timedelta
import pytz

# ==============================================================================
# CONFIGURATION & RISK PARAMETERS
# ==============================================================================
PAIRS = ["EURUSD", "USDJPY", "GBPJPY", "AUDUSD", "EURJPY", "GBPUSD","BTCUSD"]
ACCOUNT_BALANCE = 10000.0   
RISK_PER_TRADE = 0.01       
MAX_ALLOWED_SPREAD_PIPS = 3.0 # Block trades if spread is > 3 pips
PRIMARY_API_KEY = os.environ.get("d93af08b103e43c99034dd6362a239d3", "6KNLLPUP7JNEBI88")

NY_TZ = pytz.timezone("America/New_York")

# ==============================================================================
# SPREAD & NEWS UTILITIES (UPGRADED)
# ==============================================================================
def get_current_spread(symbol):
    """Fetches real-time spread to ensure we aren't trading in illiquid gaps."""
    try:
        url = f"https://api.twelvedata.com/quotes?symbol={symbol}&apikey={PRIMARY_API_KEY}"
        res = requests.get(url).json()
        # TwelveData provides bid/ask in the quote endpoint
        bid = float(res.get('bid', 0))
        ask = float(res.get('ask', 0))
        if bid == 0 or ask == 0: return 999 # Safety block
        
        pip_val = 0.01 if "JPY" in symbol else 0.0001
        spread_pips = (ask - bid) / pip_val
        return spread_pips
    except:
        return 999

def is_news_safe(symbol):
    """
    Checks for high-impact news. 
    Note: Real-time news APIs often require specialized keys. 
    This logic filters out pairs if a major event is within a 2-hour window.
    """
    try:
        # Using TwelveData Price Alerts/Events or a generic Economic Calendar
        url = f"https://api.twelvedata.com/economic_calendar?apikey={PRIMARY_API_KEY}"
        res = requests.get(url).json()
        events = res.get("events", [])
        
        now = datetime.now(pytz.UTC)
        relevant_currencies = [symbol[:3], symbol[3:]] # e.g. EUR and USD
        
        for event in events:
            # Only care about High Impact news
            if event.get("importance") == "High":
                event_currency = event.get("currency")
                if event_currency in relevant_currencies:
                    event_time = datetime.fromisoformat(event.get("date").replace("Z", "+00:00"))
                    # If news is within 2 hours (before or after)
                    if abs((event_time - now).total_seconds()) < 7200:
                        return False
        return True
    except:
        return True # Default to True if News API fails to not lock the bot

# ==============================================================================
# CORE MATH & LOGIC
# ==============================================================================
def get_pip_value(pair):
    return 0.01 if "JPY" in pair else 0.0001

def calculate_position_size(pair, risk_usd, stop_loss_pips):
    if stop_loss_pips <= 0: return 0
    pip_value_std_lot = 10.0 if "JPY" not in pair else 9.0 
    return round(risk_usd / (stop_loss_pips * pip_value_std_lot), 2)

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

# ==============================================================================
# MAIN SCANNER
# ==============================================================================
def fetch_data(symbol, interval, size=100):
    try:
        url = f"https://api.twelvedata.com/time_series?symbol={symbol}&interval={interval}&outputsize={size}&apikey={PRIMARY_API_KEY}"
        res = requests.get(url, timeout=15).json()
        return list(reversed(res["values"])) if "values" in res else []
    except: return []

def run_trading_bot():
    now_ny = datetime.now(NY_TZ)
    is_ny_active = time(8, 0) <= now_ny.time() <= time(16, 0)
    signals = []

    for pair in PAIRS:
        # UPGRADE: Check spread first
        current_spread = get_current_spread(pair)
        if current_spread > MAX_ALLOWED_SPREAD_PIPS:
            print(f"Skipping {pair}: Spread too high ({round(current_spread, 1)} pips)")
            continue
            
        # UPGRADE: Check News Impact
        if not is_news_safe(pair):
            print(f"Skipping {pair}: High impact news detected nearby.")
            continue

        daily = fetch_data(pair, "1day", 55)
        if not daily: continue
        
        closes = [float(x["close"]) for x in daily]
        last_closed = daily[-2]
        op, cl, hi, lo = float(last_closed["open"]), float(last_closed["close"]), float(last_closed["high"]), float(last_closed["low"])
        
        e8 = calculate_ema(closes[:-1], 8)[-1]
        e20 = calculate_ema(closes[:-1], 20)[-1]
        e50 = calculate_ema(closes[:-1], 50)[-1]
        pip_unit = get_pip_value(pair)
        
        is_trending = abs(e20 - e50) > (closes[-2] * 0.0015)

        if is_trending:
            if e8 > e20 > e50 and lo <= e8 and is_valid_pinbar(op, cl, hi, lo, bullish=True):
                entry, sl = hi + (2 * pip_unit), lo - (2 * pip_unit)
                lots = calculate_position_size(pair, ACCOUNT_BALANCE * RISK_PER_TRADE, abs(entry-sl)/pip_unit)
                signals.append({"pair": pair, "strategy": "DailyChore", "side": "BUY", "entry": round(entry, 5), "sl": round(sl, 5), "tp": round(entry + (entry-sl), 5), "lots": lots})
            
            elif e8 < e20 < e50 and hi >= e8 and is_valid_pinbar(op, cl, hi, lo, bullish=False):
                entry, sl = lo - (2 * pip_unit), hi + (2 * pip_unit)
                lots = calculate_position_size(pair, ACCOUNT_BALANCE * RISK_PER_TRADE, abs(entry-sl)/pip_unit)
                signals.append({"pair": pair, "strategy": "DailyChore", "side": "SELL", "entry": round(entry, 5), "sl": round(sl, 5), "tp": round(entry - (sl-entry), 5), "lots": lots})
        else:
            if not is_ny_active: continue
            data_4h, data_5m = fetch_data(pair, "4h", 15), fetch_data(pair, "5min", 5)
            range_candle = next((c for c in data_4h if c["datetime"].startswith(now_ny.strftime("%Y-%m-%d"))), None)
            
            if range_candle and len(data_5m) >= 2:
                r_hi, r_lo = float(range_candle["high"]), float(range_candle["low"])
                m5_prev, m5_curr = data_5m[-2], data_5m[-1]
                
                if float(m5_prev["close"]) > r_hi and float(m5_curr["close"]) < r_hi:
                    entry = float(m5_curr["close"])
                    sl = max(float(m5_prev["high"]), float(m5_curr["high"])) + pip_unit 
                    lots = calculate_position_size(pair, ACCOUNT_BALANCE * RISK_PER_TRADE, abs(entry-sl)/pip_unit)
                    signals.append({"pair": pair, "strategy": "FakeBreakout", "side": "SELL", "entry": round(entry, 5), "sl": round(sl, 5), "tp": round(entry - (2*(sl-entry)), 5), "lots": lots})
                
                elif float(m5_prev["close"]) < r_lo and float(m5_curr["close"]) > r_lo:
                    entry = float(m5_curr["close"])
                    sl = min(float(m5_prev["low"]), float(m5_curr["low"])) - pip_unit
                    lots = calculate_position_size(pair, ACCOUNT_BALANCE * RISK_PER_TRADE, abs(entry-sl)/pip_unit)
                    signals.append({"pair": pair, "strategy": "FakeBreakout", "side": "BUY", "entry": round(entry, 5), "sl": round(sl, 5), "tp": round(entry + (2*(entry-sl)), 5), "lots": lots})

    return signals

if __name__ == "__main__":
    print(f"Scanning Markets... (NY Time: {datetime.now(NY_TZ).strftime('%H:%M')})")
    results = run_trading_bot()
    for s in results: print(s)
