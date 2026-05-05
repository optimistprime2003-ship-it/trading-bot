import requests
import json
import os
from datetime import datetime, timedelta
import pytz

# --- CONFIGURATION ---
PAIRS = ["EURUSD", "GBPUSD", "USDJPY"]
# These pull directly from the Render Environment Variables we set up
PRIMARY_API_KEY = os.environ.get("PRIMARY_API_KEY")
BACKUP_API_KEY = os.environ.get("BACKUP_API_KEY")
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
        # Mapping 15min/5min to Alpha Vantage format
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
        res = requests.get(url, timeout=5).json()
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
# STRATEGY TOOLS & TRACKING
# ==========================================
def ema(prices, period):
    k = 2 / (period + 1)
    res = []
    for i, p in enumerate(prices):
        if i == 0: res.append(p)
        else: res.append(p * k + res[i-1] * (1-k))
    return res

def update_signal_status(active_signals):
    """
    Checks the current market price for each active trade to see if it hit TP or SL.
    This was the missing function causing the crash.
    """
    updated_list = []
    for signal in active_signals:
        try:
            # Check price on a 1-minute basis for precision
            data = fetch_forex_data(signal['pair'], "1min")
            if not data:
                updated_list.append(signal)
                continue
                
            current_price = float(data[-1]['close'])
            tp = float(signal['tp'])
            sl = float(signal['sl'])
            
            if signal['signal'] == "BUY":
                if current_price >= tp: signal['status'] = "TP HIT"
                elif current_price <= sl: signal['status'] = "SL HIT"
            elif signal['signal'] == "SELL":
                if current_price <= tp: signal['status'] = "TP HIT"
                elif current_price >= sl: signal['status'] = "SL HIT"
                    
        except Exception as e:
            print(f"Error updating {signal['pair']}: {e}")
            
        updated_list.append(signal)
    return updated_list

# ==========================================
# SIGNAL GENERATION
# ==========================================
def generate_pinbar_signals():
    signals = []
    for pair in PAIRS:
        data = fetch_forex_data(pair, "15min")
        if not data or len(data) < 60: continue
        if not has_volume_confirmation(data): continue

        closes = [float(x["close"]) for x in data]
        highs = [float(x["high"]) for x in data]
        lows = [float(x["low"]) for x in data]
        opens = [float(x["open"]) for x in data]

        ema8, ema20, ema50 = ema(closes, 8), ema(closes, 20), ema(closes, 50)
        
        i = -1
        op, cl, hi, lo = opens[i], closes[i], highs[i], lows[i]
        candle_range = hi - lo
        if candle_range == 0: continue

        # Corrected Logic: Bullish = long lower wick, Bearish = long upper wick
        bullish_pin = min(op, cl) > hi - (candle_range * 0.3)
        bearish_pin = max(op, cl) < lo + (candle_range * 0.3)

        if ema8[i] > ema20[i] > ema50[i] and bullish_pin:
            entry = round(hi + 0.0002, 5)
            sl = round(lo - 0.0002, 5)
            signals.append({
                "pair": pair, "strategy": "PinBar", "signal": "BUY", "type": "BUY STOP",
                "entry": entry, "sl": sl, "tp": round(entry + (entry - sl), 5),
                "status": "ACTIVE", "time": str(datetime.utcnow())
            })
        elif ema8[i] < ema20[i] < ema50[i] and bearish_pin:
            entry = round(lo - 0.0002, 5)
            sl = round(hi + 0.0002, 5)
            signals.append({
                "pair": pair, "strategy": "PinBar", "signal": "SELL", "type": "SELL STOP",
                "entry": entry, "sl": sl, "tp": round(entry - (sl - entry), 5),
                "status": "ACTIVE", "time": str(datetime.utcnow())
            })
    return signals

def generate_signals():
    """Main call from main.py"""
    if is_market_volatile():
        print("🛑 Trade Blocked: News Detected.")
        return []
    
    # We will expand Fake Breakout once this is stable
    return generate_pinbar_signals()
