import requests
import pandas as pd

API_KEY = "d93af08b103e43c99034dd6362a239d3"

def get_data(symbol="EUR/USD", interval="15min", output=50):
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
    df = df.astype(float)
    df = df[::-1]  # oldest → newest
    return df


def ema(series, period):
    return series.ewm(span=period, adjust=False).mean()


def generate_signal(df):
    df["ema8"] = ema(df["close"], 8)
    df["ema20"] = ema(df["close"], 20)
    df["ema50"] = ema(df["close"], 50)

    last = df.iloc[-1]

    trend_up = df["ema8"].iloc[-1] > df["ema20"].iloc[-1] > df["ema50"].iloc[-1]
    trend_down = df["ema8"].iloc[-1] < df["ema20"].iloc[-1] < df["ema50"].iloc[-1]

    body = abs(last["close"] - last["open"])
    lower_wick = min(last["open"], last["close"]) - last["low"]
    upper_wick = last["high"] - max(last["open"], last["close"])

    bullish_pin = lower_wick > 2 * body
    bearish_pin = upper_wick > 2 * body

    if trend_up and bullish_pin:
        return {
            "signal": "BUY",
            "entry": last["high"],
            "sl": last["low"]
        }

    if trend_down and bearish_pin:
        return {
            "signal": "SELL",
            "entry": last["low"],
            "sl": last["high"]
        }

    return None
