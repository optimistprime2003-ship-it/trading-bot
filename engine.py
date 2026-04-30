import datetime
import requests

API_KEY = "YOUR_TWELVEDATA_API_KEY"

PAIRS = ["EUR/USD", "GBP/USD"]

def get_price(pair):
    url = f"https://api.twelvedata.com/price?symbol={pair}&apikey={API_KEY}"
    res = requests.get(url).json()
    return float(res["price"])


def generate_signals():
    signals = []

    now = datetime.datetime.utcnow()
    expiry = now + datetime.timedelta(hours=4)

    for pair in PAIRS:
        try:
            price = get_price(pair)

            # 🔥 SIMPLE LOGIC (we will upgrade after)
            if price > 1:  # dummy condition (replace later)
                signals.append({
                    "pair": pair,
                    "signal": "BUY",
                    "type": "MARKET",
                    "entry": price,
                    "sl": price - 0.0020,
                    "tp": price + 0.0040,
                    "time": now.strftime("%Y-%m-%d %H:%M"),
                    "expiry": expiry.strftime("%Y-%m-%d %H:%M"),
                    "status": "ACTIVE"
                })

        except:
            continue

    return signals
