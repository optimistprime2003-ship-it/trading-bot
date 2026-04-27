import numpy as np
import pandas as pd

def ema(series, period):
    return series.ewm(span=period, adjust=False).mean()

def is_bullish_pinbar(o, h, l, c):
    body = abs(c - o)
    lower_wick = min(o, c) - l
    return lower_wick >= 2 * body and c > o

def is_bearish_pinbar(o, h, l, c):
    body = abs(c - o)
    upper_wick = h - max(o, c)
    return upper_wick >= 2 * body and c < o
