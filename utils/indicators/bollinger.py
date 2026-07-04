import numpy as np
import pandas as pd


def calculate_bollinger_bands(close, period=20, std_dev=2):
    close = pd.to_numeric(close, errors="coerce")
    middle = close.rolling(period, min_periods=period).mean()
    deviation = close.rolling(period, min_periods=period).std()
    upper = middle + std_dev * deviation
    lower = middle - std_dev * deviation
    width_pct = ((upper - lower) / middle.replace(0, np.nan)) * 100
    squeeze_threshold = width_pct.rolling(80, min_periods=20).quantile(0.2)
    squeeze = width_pct <= squeeze_threshold
    return upper, middle, lower, width_pct, squeeze
