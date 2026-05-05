import requests
from datetime import datetime, timedelta
import pytz

# --- CONFIGURATION ---
PAIRS = ["EURUSD", "GBPUSD", "USDJPY"]
PRIMARY_API_KEY = "d93af08b103e43c99034dd6362a239d3"  # Replace with your primary key
BACKUP_API_KEY = "6KNLLPUP7JNEBI88" # Replace with your Alpha Vantage key
NY_TZ = pytz.timezone("America/New_York")

# ==========================================
# RESILIENCE: DATA FETCH WITH FALLBACK
# ==========================================
def fetch_forex_data(symbol, interval):
    """
    Tries Twelve Data first. If it fails or times out, switches to Alpha Vantage.
    """
    # 1. Try Twelve Data (Primary)
    try:
        url = f"https://api.twelvedata.com/time_series?symbol={symbol}&interval={interval}&outputsize=200&apikey={PRIMARY_API_KEY}"
        res = requests.get(url, timeout=10).json()
        if "values" in res:
            return list(reversed(res["values"]))
    except Exception as e:
        print(f"⚠️ Primary API Failed for {symbol}: {e}")

    # 2. Try Alpha Vantage (Backup)
    try:
        print(f"🔄 Switching to Alpha Vantage Backup for {symbol}...")
        from_cur, to_cur = symbol[:3], symbol[3:]
        av_interval = interval if 'min' in interval else '15min'
        
        url = f"https://www.alphavantage.co/query?function=FX_INTRADAY&from_symbol={from_cur}&to_symbol={to_cur}&interval={av_interval}&apikey={BACKUP_API_KEY}"
        res = requests.get(url, timeout=10).json()
        
        time_series_key = f"Time Series FX ({av_interval})"
        if time_series_key in res:
            raw_data = res[time_series_key]
            formatted_data = []
            for ts, val in raw_data.items():
                formatted_data.append({
                    "datetime": ts,
                    "open": val["1. open"],
                    "high": val["2. high"],
                    "low": val["3. low"],
                    "close": val["4. close"]
                })
            return list(reversed(formatted_data))
    except Exception as e:
        print(f"❌ Backup API Failed for {symbol}: {e}")
    
    return []

# ==========================================
# MARKET MECHANICS: NEWS & VOLUME
# ==========================================
def is_market_volatile():
    """Blocks signals 30 mins before/after High Impact US News."""
    try:
        url = f"https://api.twelvedata.com/economic_calendar?apikey={PRIMARY_API_KEY}"
        res = requests.get(url).json()
        now_utc = datetime.utcnow().replace(tzinfo=pytz.utc)
        for event in res.get("notifications", []):
            if event.get("country") == "US" and event.get("importance") == "High":
                event_time = datetime.fromtimestamp(event["time"]).replace(tzinfo=pytz.utc)
                if event_time - timedelta(minutes=30) <= now_utc <= event_time + timedelta(minutes=30):
                    return True
        return False
    except: return False

def has_volume_confirmation(data_list):
    """Checks if current activity is >10% above the 10-period average."""
    if len(data_list) < 11: return True
    volumes = [float(x.get("volume", 0)) for x in data_list if x.get("volume")]
    if not volumes: return True # Bypass if backup source lacks volume data
    current_vol = volumes[-1]
    avg_vol = sum(volumes[-11:-1]) / 10
    return current_vol > (avg_vol * 1.1)

# ==========================================
# STRATEGY LOGIC
# ==========================================
def ema(prices, period):
    k = 2 / (period + 1)
    res = []
    for i, p in enumerate(prices):
        if i == 0: res.append(p)
        else: res.append(p * k + res[i-1] * (1-k))
    return res

def generate_pinbar_signals():
    signals = []
    for pair in PAIRS:
        data = fetch_forex_data(pair, "15min")
        if not data or len(data) < 60: continue
        
        # Apply Volume Filter
        if not has_volume_confirmation(data): continue

        closes = [float(x["close"]) for x in data]
        highs = [float(x["high"]) for x in data]
        lows = [float(x["low"]) for x in data]
        opens = [float(x["open"]) for x in data]

        ema8 = ema(closes, 8)
        ema20 = ema(closes, 20)
        ema50 = ema(closes, 50)
        
        i = -1
        op, cl, hi, lo = opens[i], closes[i], highs[i], lows[i]
        candle_range = hi - lo
        if candle_range == 0: continue

        # --- UPDATED INVERSE PIN BAR LOGIC ---
        # Bullish: Long lower wick (rejection of lows)
        bullish_pin = min(op, cl) > hi - (candle_range * 0.3)
        # Bearish: Long upper wick (rejection of highs)
        bearish_pin = max(op, cl) < lo + (candle_range * 0.3)

        now = datetime.utcnow()
        # Uptrend + Bullish Rejection
        if ema8[i] > ema20[i] > ema50[i] and bullish_pin:
            entry = hi + 0.0002
            sl = lo - 0.0002
            signals.append({
                "pair": pair, "strategy": "PinBar", "signal": "BUY", "type": "BUY STOP",
                "entry": round(entry, 5), "sl": round(sl, 5), "tp": round(entry + (entry - sl), 5),
                "time": str(now)
            })
        # Downtrend + Bearish Rejection
        elif ema8[i] < ema20[i] < ema50[i] and bearish_pin:
            entry = lo - 0.0002
            sl = hi + 0.0002
            signals.append({
                "pair": pair, "strategy": "PinBar", "signal": "SELL", "type": "SELL STOP",
                "entry": round(entry, 5), "sl": round(sl, 5), "tp": round(entry - (sl - entry), 5),
                "time": str(now)
            })
    return signals

def generate_fake_breakout_signals():
    # Placeholder for the 4H/5min Fake Breakout logic 
    # Use the same fetch_forex_data(pair, "4h") and fetch_forex_data(pair, "5min")
    return []

# ==========================================
# MAIN EXECUTION
# ==========================================
def generate_signals():
    # Global Killswitch: News Guard
    if is_market_volatile():
        print("🛑 Trade Blocked: High Impact News Detected.")
        return []
    
    all_signals = generate_pinbar_signals() + generate_fake_breakout_signals()
    return all_signals
