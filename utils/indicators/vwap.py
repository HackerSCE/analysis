import numpy as np
import pandas as pd


def calculate_vwap(df):
    typical_price = (df["high"] + df["low"] + df["close"]) / 3
    volume = pd.to_numeric(df["volume"], errors="coerce").fillna(0)
    price_volume = typical_price * volume

    if "datetime" in df.columns:
        session_key = pd.to_datetime(df["datetime"], errors="coerce").dt.date
        cumulative_pv = price_volume.groupby(session_key).cumsum()
        cumulative_volume = volume.groupby(session_key).cumsum()
    else:
        cumulative_pv = price_volume.cumsum()
        cumulative_volume = volume.cumsum()

    return cumulative_pv / cumulative_volume.replace(0, np.nan)
