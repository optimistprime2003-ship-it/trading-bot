import requests
from datetime import datetime, timedelta
import pytz

PAIRS = ["EURUSD", "GBPUSD", "USDJPY"]
API_KEY = "my Api key" # Ensure your Twelve Data API key is here
NY_TZ = pytz.timezone("America/New_York")

# ===============================
# NEWS FILTER LOGIC
# ===============================
def is_market_volatile():
    """
    Checks for high-impact USD news. 
    Prevents signals 30 mins before/after events.
    """
    try:
        # Using Twelve Data's economic calendar endpoint
        url = f"https://api.twelvedata.com/economic_calendar?apikey={API_KEY}"
        res = requests.get(url).json()
        
        if "status" in res and res["status"] == "error":
            return False # Fallback to allow trading if API fails

        now_utc = datetime.utcnow().replace(tzinfo=pytz.utc)
        
        for event in res.get("notifications", []):
            # Focus on High Impact USD news (NFP, CPI, FED)
            if event.get("country") == "US" and event.get("importance") == "High":
                event_time = datetime.fromtimestamp(event["time"]).replace(tzinfo=pytz.utc)
                
                # Check 30 minute window
                if event_time - timedelta(minutes=30) <= now_utc <= event_time + timedelta(minutes=30):
                    return True
        return False
    except:
        return False

# ===============================
# CORE UTILITIES
# ===============================
def fetch_data(symbol, interval):
    url = f"https://api.twelvedata.com/time_series?symbol={symbol}&interval={interval}&outputsize=200&apikey={API_KEY}"
    res = requests.get(url).json()
    if "values" not in res:
        return []
    return list(reversed(res["values"]))

def ema(prices, period):
    k = 2 / (period + 1)
    result = []
    for i, p in enumerate(prices):
        p = float(p)
        if i == 0:
            result.append(p)
        else:
            result.append(p * k + result[i - 1] * (1 - k))
    return result

def get_ny_range(data_4h):
    for candle in data_4h:
        dt = datetime.fromisoformat(candle["datetime"])
        if dt.hour == 4:
            return float(candle["high"]), float(candle["low"])
    return None, None

def is_same_ny_day(dt1, dt2):
    if dt1.tzinfo is None: dt1 = pytz.utc.localize(dt1)
    if dt2.tzinfo is None: dt2 = pytz.utc.localize(dt2)
    return dt1.astimezone(NY_TZ).date() == dt2.astimezone(NY_TZ).date()

# ===============================
# SIGNAL GENERATION
# ===============================
def generate_signals():
    if is_market_volatile():
        print("High impact news detected. Skipping signal generation.")
        return []
    
    return generate_pinbar_signals() + generate_fake_breakout_signals()

def generate_pinbar_signals():
    signals = []
    for pair in PAIRS:
        data = fetch_data(pair, "15min")
        if len(data) < 60: continue
        
        closes = [float(x["close"]) for x in data]
        highs = [float(x["high"]) for x in data]
        lows = [float(x["low"]) for x in data]
        opens = [float(x["open"]) for x in data]

        ema8, ema20, ema50 = ema(closes, 8), ema(closes, 20), ema(closes, 50)
        i = -1
        now = datetime.utcnow()
        open_p, close_p, high_p, low_p = opens[i], closes[i], highs[i], lows[i]
        body, candle = abs(close_p - open_p), high_p - low_p
        if candle == 0: continue

        # --- FIXED INVERSE LOGIC ---
        # Bullish Pin: Rejection of LOWS (Long lower wick). Body is in the TOP 30%.
        bullish_pin = min(open_p, close_p) > high_p - (candle * 0.3)
        
        # Bearish Pin: Rejection of HIGHS (Long upper wick). Body is in the BOTTOM 30%.
        bearish_pin = max(open_p, close_p) < low_p + (candle * 0.3)

        if ema8[i] > ema20[i] > ema50[i] and bullish_pin:
            entry = high_p + 0.0002
            sl = low_p - 0.0002
            signals.append({
                "pair": pair, "strategy": "PinBar", "signal": "BUY", "type": "BUY STOP", 
                "entry": round(entry, 5), "sl": round(sl, 5), "tp": round(entry + (entry - sl), 5), 
                "time": str(now), "expiry": str(now + timedelta(days=1)), "status": "ACTIVE"
            })
        elif ema8[i] < ema20[i] < ema50[i] and bearish_pin:
            entry = low_p - 0.0002
            sl = high_p + 0.0002
            signals.append({
                "pair": pair, "strategy": "PinBar", "signal": "SELL", "type": "SELL STOP", 
                "entry": round(entry, 5), "sl": round(sl, 5), "tp": round(entry - (sl - entry), 5), 
                "time": str(now), "expiry": str(now + timedelta(days=1)), "status": "ACTIVE"
            })
    return signals

def generate_fake_breakout_signals():
    signals = []
    for pair in PAIRS:
        data_4h = fetch_data(pair, "4h")
        data_5m = fetch_data(pair, "5min")
        if len(data_4h) < 10 or len(data_5m) < 50: continue

        range_high, range_low = get_ny_range(data_4h)
        if range_high is None: continue

        breakout_active = False
        breakout_direction = None
        breakout_extreme = None

        for i in range(2, len(data_5m)):
            candle = data_5m[i]
            dt = datetime.fromisoformat(candle["datetime"])
            now = datetime.utcnow()
            if not is_same_ny_day(dt, now): continue

            close, high, low = float(candle["close"]), float(candle["high"]), float(candle["low"])
            prev_close = float(data_5m[i-1]["close"])

            if not breakout_active:
                if prev_close > range_high:
                    breakout_active, breakout_direction, breakout_extreme = True, "above", float(data_5m[i-1]["high"])
                elif prev_close < range_low:
                    breakout_active, breakout_direction, breakout_extreme = True, "below", float(data_5m[i-1]["low"])

            if breakout_active:
                if breakout_direction == "above": breakout_extreme = max(breakout_extreme, high)
                else: breakout_extreme = min(breakout_extreme, low)

                if breakout_direction == "above" and close < range_high:
                    entry = close
                    sl = breakout_extreme
                    signals.append({
                        "pair": pair, "strategy": "FakeBreakout", "signal": "SELL", "type": "MARKET", 
                        "entry": round(entry, 5), "sl": round(sl, 5), "tp": round(entry - (sl - entry) * 2, 5), 
                        "time": str(now), "expiry": str(now + timedelta(days=1)), "status": "ACTIVE"
                    })
                    breakout_active = False
                elif breakout_direction == "below" and close > range_low:
                    entry = close
                    sl = breakout_extreme
                    signals.append({
                        "pair": pair, "strategy": "FakeBreakout", "signal": "BUY", "type": "MARKET", 
                        "entry": round(entry, 5), "sl": round(sl, 5), "tp": round(entry + (entry - sl) * 2, 5), 
                        "time": str(now), "expiry": str(now + timedelta(days=1)), "status": "ACTIVE"
                    })
                    breakout_active = False
    return signals

def update_signal_status(active_signals):
    # This keeps signals active. You can add logic here to check if price hits TP/SL
    return active_signals
