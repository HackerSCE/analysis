import pandas as pd

from utils.indicators.adx import calculate_atr


def calculate_supertrend(high, low, close, period=10, multiplier=3):
    high = pd.to_numeric(high, errors="coerce").reset_index(drop=True)
    low = pd.to_numeric(low, errors="coerce").reset_index(drop=True)
    close = pd.to_numeric(close, errors="coerce").reset_index(drop=True)
    atr = calculate_atr(high, low, close, period).reset_index(drop=True)

    hl2 = (high + low) / 2
    upper_band = hl2 + multiplier * atr
    lower_band = hl2 - multiplier * atr
    final_upper = upper_band.copy()
    final_lower = lower_band.copy()
    supertrend = pd.Series(index=close.index, dtype="float64")
    direction = pd.Series(index=close.index, dtype="int64")

    for index in range(len(close)):
        if index == 0:
            supertrend.iloc[index] = pd.NA
            direction.iloc[index] = 1
            continue

        if upper_band.iloc[index] < final_upper.iloc[index - 1] or close.iloc[index - 1] > final_upper.iloc[index - 1]:
            final_upper.iloc[index] = upper_band.iloc[index]
        else:
            final_upper.iloc[index] = final_upper.iloc[index - 1]

        if lower_band.iloc[index] > final_lower.iloc[index - 1] or close.iloc[index - 1] < final_lower.iloc[index - 1]:
            final_lower.iloc[index] = lower_band.iloc[index]
        else:
            final_lower.iloc[index] = final_lower.iloc[index - 1]

        previous_supertrend = supertrend.iloc[index - 1]
        if pd.isna(previous_supertrend) or previous_supertrend == final_upper.iloc[index - 1]:
            if close.iloc[index] <= final_upper.iloc[index]:
                supertrend.iloc[index] = final_upper.iloc[index]
                direction.iloc[index] = -1
            else:
                supertrend.iloc[index] = final_lower.iloc[index]
                direction.iloc[index] = 1
        else:
            if close.iloc[index] >= final_lower.iloc[index]:
                supertrend.iloc[index] = final_lower.iloc[index]
                direction.iloc[index] = 1
            else:
                supertrend.iloc[index] = final_upper.iloc[index]
                direction.iloc[index] = -1

    return supertrend, direction
