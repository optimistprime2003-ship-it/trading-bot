import requests
import pandas as pd

# 🔴 PUT YOUR REAL API KEY HERE
API_KEY = "YOUR_TWELVEDATA_API_KEY"

# 🔴 TELEGRAM SETTINGS
TELEGRAM_TOKEN = "YOUR_TELEGRAM_BOT_TOKEN"
CHAT_ID = "YOUR_CHAT_ID"

PAIRS = ["EUR/USD", "GBP/USD", "USD/JPY", "GBP/JPY", "AUD/USD", "EUR/JPY"]


# 📩 TELEGRAM FUNCTION
def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    
    data = {
        "chat_id": CHAT_ID,
        "text": message
    }

    try:
        requests.post(url, data=data)
    except:
        pass


# 📊 GET MARKET DATA
def get_data(symbol, interval, output=100):
    url = "https://api.twelvedata.com/time_series"

    params = {
        "symbol": symbol,
        "interval": interval,
        "outputsize": output,
        "apikey": API_KEY
    }

    response = requests.get(url, params=params).json()

    if "values" not in response:
        return None

    df = pd.DataFrame(response["values"])

    for col in ["open", "high", "low", "close"]:
        df[col] = df[col].astype(float)

    df = df[::-1]
    return df


# 📉 EMA
def ema(series, period):
    return series.ewm(span=period, adjust=False).mean()


# 📈 TREND CHECK
def trend_condition(df):
    return (
        df["ema8"].iloc[-1] > df["ema20"].iloc[-1] > df["ema50"].iloc[-1],
        df["ema8"].iloc[-1] < df["ema20"].iloc[-1] < df["ema50"].iloc[-1]
    )


# 📌 PIN BAR
def is_bullish_pinbar(candle):
    body = abs(candle["close"] - candle["open"])
    lower_wick = min(candle["open"], candle["close"]) - candle["low"]
    return lower_wick >= 2 * body


def is_bearish_pinbar(candle):
    body = abs(candle["close"] - candle["open"])
    upper_wick = candle["high"] - max(candle["open"], candle["close"])
    return upper_wick >= 2 * body


# 💰 TRADE CALCULATION
def calculate_trade(signal_type, candle):
    if signal_type == "BUY":
        entry = candle["high"] + 0.0002
        sl = candle["low"] - 0.0002
        tp = entry + (entry - sl) * 2
    else:
        entry = candle["low"] - 0.0002
        sl = candle["high"] + 0.0002
        tp = entry - (sl - entry) * 2

    return entry, sl, tp


# 🚀 MAIN SIGNAL FUNCTION
def generate_signals():
    results = []

    for pair in PAIRS:

        df_m15 = get_data(pair, "15min")
        df_h1 = get_data(pair, "1h")

        if df_m15 is None or df_h1 is None:
            continue

        # EMA CALCULATION
        for df in [df_m15, df_h1]:
            df["ema8"] = ema(df["close"], 8)
            df["ema20"] = ema(df["close"], 20)
            df["ema50"] = ema(df["close"], 50)

        # TREND
        up_m15, down_m15 = trend_condition(df_m15)
        up_h1, down_h1 = trend_condition(df_h1)

        last = df_m15.iloc[-1]

        # ✅ BUY SIGNAL
        if up_m15 and up_h1 and is_bullish_pinbar(last):
            entry, sl, tp = calculate_trade("BUY", last)

            signal = {
                "pair": pair,
                "signal": "BUY",
                "entry": round(entry, 5),
                "sl": round(sl, 5),
                "tp": round(tp, 5)
            }

            results.append(signal)

            # 📩 TELEGRAM ALERT
            message = (
                f"📈 BUY SIGNAL\n"
                f"Pair: {pair}\n"
                f"Entry: {round(entry,5)}\n"
                f"SL: {round(sl,5)}\n"
                f"TP: {round(tp,5)}"
            )
            send_telegram(message)

        # ❌ SELL SIGNAL
        if down_m15 and down_h1 and is_bearish_pinbar(last):
            entry, sl, tp = calculate_trade("SELL", last)

            signal = {
                "pair": pair,
                "signal": "SELL",
                "entry": round(entry, 5),
                "sl": round(sl, 5),
                "tp": round(tp, 5)
            }

            results.append(signal)

            # 📩 TELEGRAM ALERT
            message = (
                f"📉 SELL SIGNAL\n"
                f"Pair: {pair}\n"
                f"Entry: {round(entry,5)}\n"
                f"SL: {round(sl,5)}\n"
                f"TP: {round(tp,5)}"
            )
            send_telegram(message)

    return results
