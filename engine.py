import requests
import os
from datetime import datetime, timedelta
import pytz

# --- CONFIGURATION ---
# Portfolio: EURUSD, USDJPY, GBPJPY, AUDUSD, EURJPY, GBPUSD
PAIRS = ["EURUSD", "USDJPY", "GBPJPY", "AUDUSD", "EURJPY", "GBPUSD"]
PRIMARY_API_KEY = os.environ.get("PRIMARY_API_KEY")
BACKUP_API_KEY = os.environ.get("BACKUP_API_KEY")
NY_TZ = pytz.timezone("America/New_York")

# ==========================================
# DATA FETCHING WITH BACKUP API LOGIC
# ==========================================
def fetch_data(symbol, interval, outputsize=100):
    """Tries Twelve Data; falls back to Alpha Vantage if Twelve Data fails."""
    # 1. Primary: Twelve Data
    try:
        url = f"https://api.twelvedata.com/time_series?symbol={symbol}&interval={interval}&outputsize={outputsize}&apikey={PRIMARY_API_KEY}"
        res = requests.get(url, timeout=10).json()
        if "values" in res:
            return list(reversed(res["values"]))
    except Exception as e:
        print(f"⚠️ Twelve Data failed for {symbol}: {e}")

    # 2. Backup: Alpha Vantage
    try:
        print(f"🔄 Switching to Alpha Vantage for {symbol}...")
        from_curr, to_curr = symbol[:3], symbol[3:]
        # Map interval names for Alpha Vantage
        av_interval = interval if 'min' in interval else '15min'
        
        url = f"https://www.alphavantage.co/query?function=FX_INTRADAY&from_symbol={from_curr}&to_symbol={to_curr}&interval={av_interval}&apikey={BACKUP_API_KEY}"
        res = requests.get(url, timeout=10).json()
        
        time_key = f"Time Series FX ({av_interval})"
        if time_key in res:
            formatted = []
            for ts, val in res[time_key].items():
                formatted.append({
                    "datetime": ts, "open": val["1. open"], "high": val["2. high"],
                    "low": val["3. low"], "close": val["4. close"]
                })
            return list(reversed(formatted))
    except Exception as e:
        print(f"❌ Backup API also failed for {symbol}: {e}")
    
    return []

def ema(prices, period):
    if not prices: return []
    k = 2 / (period + 1)
    res = [prices[0]]
    for p in prices[1:]:
        res.append(p * k + res[-1] * (1-k))
    return res

# ==========================================
# STRATEGY 1: DAILY PIN BAR (DAILY CHORE)
# ==========================================
def generate_daily_pinbar_signals():
    signals = []
    for pair in PAIRS:
        data = fetch_data(pair, "1day", 60)
        if len(data) < 55: continue

        closes = [float(x["close"]) for x in data]
        highs = [float(x["high"]) for x in data]
        lows = [float(x["low"]) for x in data]
        opens = [float(x["open"]) for x in data]

        e8, e20, e50 = ema(closes, 8), ema(closes, 20), ema(closes, 50)
        op, cl, hi, lo = opens[-1], closes[-1], highs[-1], lows[-1]
        candle_range = hi - lo
        if candle_range == 0: continue

        # Bullish: Open/Close in lower 30% | Bearish: Open/Close in upper 30%[cite: 1]
        is_bullish_pin = max(op, cl) <= lo + (candle_range * 0.3)
        is_bearish_pin = min(op, cl) >= hi - (candle_range * 0.3)

        # SELL SIGNAL Rules[cite: 1]
        if e8[-1] < e20[-1] < e50[-1] and is_bearish_pin and hi >= e8[-1]:
            entry = lo - 0.0002 # 2 pips below low[cite: 1]
            sl = hi + 0.0002    # 2 pips above high[cite: 1]
            tp = entry - (sl - entry) # 1:1 Measured Move[cite: 1]
            signals.append({"pair": pair, "strategy": "DailyPin", "signal": "SELL", "type": "SELL STOP", "entry": round(entry, 5), "sl": round(sl, 5), "tp": round(tp, 5), "status": "ACTIVE"})

        # BUY SIGNAL Rules[cite: 1]
        elif e8[-1] > e20[-1] > e50[-1] and is_bullish_pin and lo <= e8[-1]:
            entry = hi + 0.0002 # 2 pips above high[cite: 1]
            sl = lo - 0.0002    # 2 pips below low[cite: 1]
            tp = entry + (entry - sl) # 1:1 Measured Move[cite: 1]
            signals.append({"pair": pair, "strategy": "DailyPin", "signal": "BUY", "type": "BUY STOP", "entry": round(entry, 5), "sl": round(sl, 5), "tp": round(tp, 5), "status": "ACTIVE"})

    return signals

# ==========================================
# STRATEGY 2: 4H RANGE FAKE BREAKOUT
# ==========================================
def generate_fake_breakout_signals():
    signals = []
    for pair in PAIRS:
        data_4h = fetch_data(pair, "4h", 10)
        if not data_4h: continue
        
        # Mark high/low of first 4H candle of the day[cite: 2]
        first_4h = data_4h[-1] 
        r_high, r_low = float(first_4h['high']), float(first_4h['low'])

        data_5m = fetch_data(pair, "5min", 10)
        if len(data_5m) < 2: continue

        prev_c = float(data_5m[-2]['close'])
        curr_c = float(data_5m[-1]['close'])

        # Break above and return -> Sell[cite: 2]
        if prev_c > r_high and curr_c < r_high:
            entry = curr_c
            sl = r_high + 0.0001
            tp = entry - ((sl - entry) * 2) # 2R Target[cite: 2]
            signals.append({"pair": pair, "strategy": "FakeBreak", "signal": "SELL", "type": "MARKET", "entry": round(entry, 5), "sl": round(sl, 5), "tp": round(tp, 5), "status": "ACTIVE"})

        # Break below and return -> Buy[cite: 2]
        elif prev_c < r_low and curr_c > r_low:
            entry = curr_c
            sl = r_low - 0.0001
            tp = entry + ((entry - sl) * 2) # 2R Target[cite: 2]
            signals.append({"pair": pair, "strategy": "FakeBreak", "signal": "BUY", "type": "MARKET", "entry": round(entry, 5), "sl": round(sl, 5), "tp": round(tp, 5), "status": "ACTIVE"})

    return signals

# ==========================================
# TRACKING & MAIN CALL
# ==========================================
def update_signal_status(active_signals):
    updated = []
    for s in active_signals:
        data = fetch_data(s['pair'], "1min", 5)
        if not data: 
            updated.append(s)
            continue
        curr = float(data[-1]['close'])
        if s['signal'] == "BUY":
            if curr >= s['tp']: s['status'] = "TP HIT"
            elif curr <= s['sl']: s['status'] = "SL HIT"
        else:
            if curr <= s['tp']: s['status'] = "TP HIT"
            elif curr >= s['sl']: s['status'] = "SL HIT"
        updated.append(s)
    return updated

def generate_signals():
    # Combines both strategies into one signal list
    return generate_daily_pinbar_signals() + generate_fake_breakout_signals()
