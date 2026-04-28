import requests
import pandas as pd

API_KEY = "d93af08b103e43c99034dd6362a239d3"

PAIRS = ["EUR/USD", "GBP/USD", "USD/JPY", "GBP/JPY", "AUD/USD", "EUR/JPY"]

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


def ema(series, period):
    return series.ewm(span=period, adjust=False).mean()


def trend_condition(df):
    return (
        df["ema8"].iloc[-1] > df["ema20"].iloc[-1] > df["ema50"].iloc[-1],
        df["ema8"].iloc[-1] < df["ema20"].iloc[-1] < df["ema50"].iloc[-1]
    )


def is_bullish_pinbar(candle):
    body = abs(candle["close"] - candle["open"])
    lower_wick = min(candle["open"], candle["close"]) - candle["low"]
    return lower_wick >= 2 * body


def is_bearish_pinbar(candle):
    body = abs(candle["close"] - candle["open"])
    upper_wick = candle["high"] - max(candle["open"], candle["close"])
    return upper_wick >= 2 * body


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


def generate_signals():
    results = []

    for pair in PAIRS:

        df_m15 = get_data(pair, "15min")
        df_h1 = get_data(pair, "1h")

        if df_m15 is None or df_h1 is None:
            continue

        # EMA calculations
        for df in [df_m15, df_h1]:
            df["ema8"] = ema(df["close"], 8)
            df["ema20"] = ema(df["close"], 20)
            df["ema50"] = ema(df["close"], 50)

        # trend
        up_m15, down_m15 = trend_condition(df_m15)
        up_h1, down_h1 = trend_condition(df_h1)

        last = df_m15.iloc[-1]

        # BUY
        if up_m15 and up_h1 and is_bullish_pinbar(last):
            entry, sl, tp = calculate_trade("BUY", last)

            results.append({
                "pair": pair,
                "signal": "BUY",
                "entry": round(entry, 5),
                "sl": round(sl, 5),
                "tp": round(tp, 5)
            })

        # SELL
        if down_m15 and down_h1 and is_bearish_pinbar(last):
            entry, sl, tp = calculate_trade("SELL", last)

            results.append({
                "pair": pair,
                "signal": "SELL",
                "entry": round(entry, 5),
                "sl": round(sl, 5),
                "tp": round(tp, 5)
            })

    return results 
