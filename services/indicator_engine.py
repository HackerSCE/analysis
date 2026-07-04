import math

import numpy as np
import pandas as pd

from utils.indicators.adx import calculate_adx, calculate_atr
from utils.indicators.bollinger import calculate_bollinger_bands
from utils.indicators.rsi import calculate_rsi
from utils.indicators.supertrend import calculate_supertrend
from utils.indicators.vwap import calculate_vwap


INDICATOR_GROUPS = [
    {
        "group": "Momentum Indicators",
        "indicators": [
            {
                "id": "rsi",
                "label": "RSI",
                "defaultValue": 60,
                "operators": [
                    {"id": "above", "label": "RSI Above Value", "needsValue": True},
                    {"id": "below", "label": "RSI Below Value", "needsValue": True},
                    {"id": "crosses_above", "label": "RSI Crosses Above", "needsValue": True},
                    {"id": "crosses_below", "label": "RSI Crosses Below", "needsValue": True},
                ],
            },
            {
                "id": "macd",
                "label": "MACD",
                "defaultValue": None,
                "operators": [
                    {"id": "above_signal", "label": "MACD Above Signal", "needsValue": False},
                    {"id": "below_signal", "label": "MACD Below Signal", "needsValue": False},
                    {"id": "bullish_cross", "label": "MACD Bullish Cross", "needsValue": False},
                    {"id": "bearish_cross", "label": "MACD Bearish Cross", "needsValue": False},
                ],
            },
            {
                "id": "adx",
                "label": "ADX",
                "defaultValue": 25,
                "operators": [
                    {"id": "above", "label": "ADX Above Value", "needsValue": True},
                    {"id": "below", "label": "ADX Below Value", "needsValue": True},
                ],
            },
            {
                "id": "stoch_rsi",
                "label": "Stochastic RSI",
                "defaultValue": 80,
                "operators": [
                    {"id": "above", "label": "Stoch RSI Above Value", "needsValue": True},
                    {"id": "below", "label": "Stoch RSI Below Value", "needsValue": True},
                    {"id": "bullish_cross", "label": "Stoch RSI Bullish Cross", "needsValue": False},
                    {"id": "bearish_cross", "label": "Stoch RSI Bearish Cross", "needsValue": False},
                ],
            },
            {
                "id": "momentum",
                "label": "Momentum",
                "defaultValue": 0,
                "operators": [
                    {"id": "above", "label": "Momentum Above Value", "needsValue": True},
                    {"id": "below", "label": "Momentum Below Value", "needsValue": True},
                    {"id": "crosses_above", "label": "Momentum Crosses Above", "needsValue": True},
                    {"id": "crosses_below", "label": "Momentum Crosses Below", "needsValue": True},
                ],
            },
        ],
    },
    {
        "group": "Trend Indicators",
        "indicators": [
            {
                "id": "supertrend",
                "label": "Supertrend",
                "defaultValue": None,
                "operators": [
                    {"id": "price_above", "label": "Price Above Supertrend", "needsValue": False},
                    {"id": "price_below", "label": "Price Below Supertrend", "needsValue": False},
                    {"id": "buy_signal", "label": "Supertrend Buy Signal", "needsValue": False},
                    {"id": "sell_signal", "label": "Supertrend Sell Signal", "needsValue": False},
                ],
            },
            {
                "id": "ema",
                "label": "EMA",
                "defaultValue": None,
                "operators": [
                    {"id": "price_above", "label": "Price Above EMA 20", "needsValue": False},
                    {"id": "price_below", "label": "Price Below EMA 20", "needsValue": False},
                    {"id": "bullish_cross", "label": "EMA 20 Crosses Above EMA 50", "needsValue": False},
                    {"id": "bearish_cross", "label": "EMA 20 Crosses Below EMA 50", "needsValue": False},
                ],
            },
            {
                "id": "sma",
                "label": "SMA",
                "defaultValue": None,
                "operators": [
                    {"id": "price_above", "label": "Price Above SMA 20", "needsValue": False},
                    {"id": "price_below", "label": "Price Below SMA 20", "needsValue": False},
                    {"id": "bullish_cross", "label": "SMA 20 Crosses Above SMA 50", "needsValue": False},
                    {"id": "bearish_cross", "label": "SMA 20 Crosses Below SMA 50", "needsValue": False},
                ],
            },
            {
                "id": "vwap",
                "label": "VWAP",
                "defaultValue": None,
                "operators": [
                    {"id": "price_above", "label": "Price Above VWAP", "needsValue": False},
                    {"id": "price_below", "label": "Price Below VWAP", "needsValue": False},
                    {"id": "crossover", "label": "VWAP Crossover", "needsValue": False},
                    {"id": "crossunder", "label": "VWAP Crossunder", "needsValue": False},
                ],
            },
            {
                "id": "ichimoku",
                "label": "Ichimoku",
                "defaultValue": None,
                "operators": [
                    {"id": "price_above_cloud", "label": "Price Above Cloud", "needsValue": False},
                    {"id": "price_below_cloud", "label": "Price Below Cloud", "needsValue": False},
                    {"id": "conversion_above_base", "label": "Conversion Above Base", "needsValue": False},
                    {"id": "conversion_below_base", "label": "Conversion Below Base", "needsValue": False},
                ],
            },
            {
                "id": "psar",
                "label": "Parabolic SAR",
                "defaultValue": None,
                "operators": [
                    {"id": "price_above", "label": "Price Above SAR", "needsValue": False},
                    {"id": "price_below", "label": "Price Below SAR", "needsValue": False},
                    {"id": "bullish_flip", "label": "SAR Bullish Flip", "needsValue": False},
                    {"id": "bearish_flip", "label": "SAR Bearish Flip", "needsValue": False},
                ],
            },
        ],
    },
    {
        "group": "Volatility Indicators",
        "indicators": [
            {
                "id": "bollinger",
                "label": "Bollinger Bands",
                "defaultValue": None,
                "operators": [
                    {"id": "near_upper", "label": "Price Near Upper Band", "needsValue": False},
                    {"id": "near_lower", "label": "Price Near Lower Band", "needsValue": False},
                    {"id": "breakout", "label": "Band Breakout", "needsValue": False},
                    {"id": "squeeze", "label": "Band Squeeze", "needsValue": False},
                ],
            },
            {
                "id": "atr",
                "label": "ATR",
                "defaultValue": 1,
                "operators": [
                    {"id": "above", "label": "ATR Above Value", "needsValue": True},
                    {"id": "below", "label": "ATR Below Value", "needsValue": True},
                ],
            },
            {
                "id": "keltner",
                "label": "Keltner Channel",
                "defaultValue": None,
                "operators": [
                    {"id": "above_upper", "label": "Price Above Upper Channel", "needsValue": False},
                    {"id": "below_lower", "label": "Price Below Lower Channel", "needsValue": False},
                    {"id": "inside", "label": "Price Inside Channel", "needsValue": False},
                ],
            },
        ],
    },
    {
        "group": "Volume Indicators",
        "indicators": [
            {
                "id": "obv",
                "label": "OBV",
                "defaultValue": None,
                "operators": [
                    {"id": "rising", "label": "OBV Rising", "needsValue": False},
                    {"id": "falling", "label": "OBV Falling", "needsValue": False},
                ],
            },
            {
                "id": "volume_breakout",
                "label": "Volume Breakout",
                "defaultValue": 1.5,
                "operators": [
                    {"id": "above_average", "label": "Volume Above Average", "needsValue": True},
                    {"id": "below_average", "label": "Volume Below Average", "needsValue": True},
                ],
            },
            {
                "id": "delivery_volume",
                "label": "Delivery Volume %",
                "defaultValue": 60,
                "operators": [
                    {"id": "above", "label": "Delivery Volume % Above", "needsValue": True},
                    {"id": "below", "label": "Delivery Volume % Below", "needsValue": True},
                ],
            },
        ],
    },
]


CONDITION_BIAS = {
    ("rsi", "above"): 1,
    ("rsi", "below"): -1,
    ("rsi", "crosses_above"): 1,
    ("rsi", "crosses_below"): -1,
    ("macd", "above_signal"): 1,
    ("macd", "below_signal"): -1,
    ("macd", "bullish_cross"): 1,
    ("macd", "bearish_cross"): -1,
    ("adx", "above"): 1,
    ("adx", "below"): 0,
    ("stoch_rsi", "above"): 1,
    ("stoch_rsi", "below"): -1,
    ("stoch_rsi", "bullish_cross"): 1,
    ("stoch_rsi", "bearish_cross"): -1,
    ("momentum", "above"): 1,
    ("momentum", "below"): -1,
    ("momentum", "crosses_above"): 1,
    ("momentum", "crosses_below"): -1,
    ("supertrend", "price_above"): 1,
    ("supertrend", "price_below"): -1,
    ("supertrend", "buy_signal"): 1,
    ("supertrend", "sell_signal"): -1,
    ("ema", "price_above"): 1,
    ("ema", "price_below"): -1,
    ("ema", "bullish_cross"): 1,
    ("ema", "bearish_cross"): -1,
    ("sma", "price_above"): 1,
    ("sma", "price_below"): -1,
    ("sma", "bullish_cross"): 1,
    ("sma", "bearish_cross"): -1,
    ("vwap", "price_above"): 1,
    ("vwap", "price_below"): -1,
    ("vwap", "crossover"): 1,
    ("vwap", "crossunder"): -1,
    ("ichimoku", "price_above_cloud"): 1,
    ("ichimoku", "price_below_cloud"): -1,
    ("ichimoku", "conversion_above_base"): 1,
    ("ichimoku", "conversion_below_base"): -1,
    ("psar", "price_above"): 1,
    ("psar", "price_below"): -1,
    ("psar", "bullish_flip"): 1,
    ("psar", "bearish_flip"): -1,
    ("bollinger", "near_upper"): 1,
    ("bollinger", "near_lower"): -1,
    ("bollinger", "breakout"): 1,
    ("bollinger", "squeeze"): 0,
    ("atr", "above"): 0,
    ("atr", "below"): 0,
    ("keltner", "above_upper"): 1,
    ("keltner", "below_lower"): -1,
    ("keltner", "inside"): 0,
    ("obv", "rising"): 1,
    ("obv", "falling"): -1,
    ("volume_breakout", "above_average"): 1,
    ("volume_breakout", "below_average"): -1,
    ("delivery_volume", "above"): 1,
    ("delivery_volume", "below"): -1,
}


def calculate_indicator_snapshot(df):
    working = normalise_ohlcv(df)
    if len(working) < 60:
        raise ValueError("At least 60 candles are required for the indicator stack.")

    close = working["close"]
    high = working["high"]
    low = working["low"]
    volume = working["volume"]

    working["rsi"] = calculate_rsi(close)
    working["ema_20"] = close.ewm(span=20, min_periods=20, adjust=False).mean()
    working["ema_50"] = close.ewm(span=50, min_periods=50, adjust=False).mean()
    working["sma_20"] = close.rolling(20, min_periods=20).mean()
    working["sma_50"] = close.rolling(50, min_periods=50).mean()

    ema_12 = close.ewm(span=12, min_periods=12, adjust=False).mean()
    ema_26 = close.ewm(span=26, min_periods=26, adjust=False).mean()
    working["macd"] = ema_12 - ema_26
    working["macd_signal"] = working["macd"].ewm(span=9, min_periods=9, adjust=False).mean()

    working["adx"], working["plus_di"], working["minus_di"] = calculate_adx(high, low, close)
    working["atr"] = calculate_atr(high, low, close)
    working["supertrend"], working["supertrend_direction"] = calculate_supertrend(high, low, close)
    working["vwap"] = calculate_vwap(working)
    (
        working["bb_upper"],
        working["bb_middle"],
        working["bb_lower"],
        working["bb_width_pct"],
        working["bb_squeeze"],
    ) = calculate_bollinger_bands(close)

    working["stoch_rsi_k"], working["stoch_rsi_d"] = calculate_stoch_rsi(working["rsi"])
    working["momentum"] = close - close.shift(10)
    working["ichimoku_conversion"], working["ichimoku_base"], working["ichimoku_span_a"], working["ichimoku_span_b"] = calculate_ichimoku(high, low)
    working["psar"], working["psar_trend"] = calculate_psar(high, low, close)
    working["keltner_middle"] = working["ema_20"]
    working["keltner_upper"] = working["keltner_middle"] + (2 * working["atr"])
    working["keltner_lower"] = working["keltner_middle"] - (2 * working["atr"])
    working["obv"] = calculate_obv(close, volume)
    working["volume_avg_20"] = volume.rolling(20, min_periods=10).mean()
    working["volume_breakout_ratio"] = volume / working["volume_avg_20"].replace(0, np.nan)
    working["delivery_volume_pct"] = estimate_delivery_volume_pct(volume)

    latest = working.iloc[-1]
    previous = working.iloc[-2]
    snapshot = {
        "latest": row_to_values(latest),
        "previous": row_to_values(previous),
    }
    snapshot["statuses"] = build_statuses(snapshot)
    return snapshot


def normalise_ohlcv(df):
    required = ["open", "high", "low", "close", "volume"]
    missing = [column for column in required if column not in df.columns]
    if missing:
        raise ValueError(f"Missing candle columns: {', '.join(missing)}")

    working = df.copy()
    for column in required:
        working[column] = pd.to_numeric(working[column], errors="coerce")
    return working.dropna(subset=["open", "high", "low", "close"]).reset_index(drop=True)


def calculate_stoch_rsi(rsi, period=14, smooth_k=3, smooth_d=3):
    lowest = rsi.rolling(period, min_periods=period).min()
    highest = rsi.rolling(period, min_periods=period).max()
    stoch = 100 * (rsi - lowest) / (highest - lowest).replace(0, np.nan)
    k = stoch.rolling(smooth_k, min_periods=smooth_k).mean()
    d = k.rolling(smooth_d, min_periods=smooth_d).mean()
    return k, d


def calculate_ichimoku(high, low):
    conversion = (high.rolling(9, min_periods=9).max() + low.rolling(9, min_periods=9).min()) / 2
    base = (high.rolling(26, min_periods=26).max() + low.rolling(26, min_periods=26).min()) / 2
    span_a = (conversion + base) / 2
    span_b = (high.rolling(52, min_periods=52).max() + low.rolling(52, min_periods=52).min()) / 2
    return conversion, base, span_a, span_b


def calculate_obv(close, volume):
    direction = np.sign(close.diff()).fillna(0)
    return (direction * volume.fillna(0)).cumsum()


def estimate_delivery_volume_pct(volume):
    rolling_max = volume.rolling(30, min_periods=10).max().replace(0, np.nan)
    return (volume / rolling_max * 100).clip(lower=0, upper=100)


def calculate_psar(high, low, close, step=0.02, max_step=0.2):
    psar = pd.Series(index=close.index, dtype="float64")
    trend = pd.Series(index=close.index, dtype="int64")
    if len(close) == 0:
        return psar, trend

    bull = True
    acceleration = step
    extreme_point = high.iloc[0]
    psar.iloc[0] = low.iloc[0]
    trend.iloc[0] = 1

    for index in range(1, len(close)):
        previous_psar = psar.iloc[index - 1]
        psar.iloc[index] = previous_psar + acceleration * (extreme_point - previous_psar)

        if bull:
            psar.iloc[index] = min(psar.iloc[index], low.iloc[index - 1], low.iloc[max(index - 2, 0)])
            if low.iloc[index] < psar.iloc[index]:
                bull = False
                psar.iloc[index] = extreme_point
                extreme_point = low.iloc[index]
                acceleration = step
            elif high.iloc[index] > extreme_point:
                extreme_point = high.iloc[index]
                acceleration = min(acceleration + step, max_step)
        else:
            psar.iloc[index] = max(psar.iloc[index], high.iloc[index - 1], high.iloc[max(index - 2, 0)])
            if high.iloc[index] > psar.iloc[index]:
                bull = True
                psar.iloc[index] = extreme_point
                extreme_point = high.iloc[index]
                acceleration = step
            elif low.iloc[index] < extreme_point:
                extreme_point = low.iloc[index]
                acceleration = min(acceleration + step, max_step)

        trend.iloc[index] = 1 if bull else -1

    return psar, trend


def row_to_values(row):
    values = {}
    for key, value in row.items():
        if isinstance(value, (np.bool_, bool)):
            values[key] = bool(value)
        elif pd.isna(value):
            values[key] = None
        elif isinstance(value, (np.integer, int)):
            values[key] = int(value)
        elif isinstance(value, (np.floating, float)):
            values[key] = float(value)
        else:
            values[key] = value
    return values


def build_statuses(snapshot):
    latest = snapshot["latest"]
    close = latest.get("close")
    supertrend_direction = latest.get("supertrend_direction") or 0
    vwap = latest.get("vwap")
    bb_upper = latest.get("bb_upper")
    bb_lower = latest.get("bb_lower")
    bb_squeeze = latest.get("bb_squeeze")

    if supertrend_direction > 0:
        supertrend_status = "Bullish"
    elif supertrend_direction < 0:
        supertrend_status = "Bearish"
    else:
        supertrend_status = "Neutral"

    if is_number(close) and is_number(vwap):
        vwap_status = "Above VWAP" if close >= vwap else "Below VWAP"
    else:
        vwap_status = "Neutral"

    if bb_squeeze:
        bollinger_status = "Squeeze"
    elif is_number(close) and is_number(bb_upper) and close >= bb_upper:
        bollinger_status = "Upper Breakout"
    elif is_number(close) and is_number(bb_lower) and close <= bb_lower:
        bollinger_status = "Lower Break"
    elif near_level(close, bb_upper):
        bollinger_status = "Near Upper"
    elif near_level(close, bb_lower):
        bollinger_status = "Near Lower"
    else:
        bollinger_status = "Inside Bands"

    return {
        "supertrendStatus": supertrend_status,
        "vwapStatus": vwap_status,
        "bollingerStatus": bollinger_status,
    }


def evaluate_condition_set(snapshot, conditions, logic="AND"):
    active_conditions = [condition for condition in conditions if condition.get("indicator") and condition.get("operator")]
    if not active_conditions:
        derived_score = derive_score(snapshot)
        return {
            "passed": True,
            "matches": [],
            "matchedCount": 0,
            "totalConditions": 0,
            "score": derived_score,
            "signalBias": bias_label(derived_score),
            "signalStrength": strength_label(derived_score, 3),
        }

    evaluations = []
    for condition in active_conditions:
        matched = evaluate_condition(snapshot, condition)
        bias = CONDITION_BIAS.get((condition.get("indicator"), condition.get("operator")), 0)
        evaluations.append({
            "condition": condition,
            "matched": matched,
            "bias": bias if matched else 0,
        })

    logic = (logic or "AND").upper()
    passed = any(item["matched"] for item in evaluations) if logic == "OR" else all(item["matched"] for item in evaluations)
    score = sum(item["bias"] for item in evaluations)
    matched_count = sum(1 for item in evaluations if item["matched"])
    total = len(evaluations)
    return {
        "passed": passed,
        "matches": evaluations,
        "matchedCount": matched_count,
        "totalConditions": total,
        "score": score,
        "signalBias": bias_label(score),
        "signalStrength": strength_label(score, total),
    }


def evaluate_condition(snapshot, condition):
    indicator = condition.get("indicator")
    operator = condition.get("operator")
    value = parse_condition_value(condition.get("value"))
    latest = snapshot["latest"]
    previous = snapshot["previous"]

    if indicator == "rsi":
        return numeric_condition(latest.get("rsi"), previous.get("rsi"), operator, value)
    if indicator == "adx":
        return numeric_condition(latest.get("adx"), previous.get("adx"), operator, value)
    if indicator == "momentum":
        return numeric_condition(latest.get("momentum"), previous.get("momentum"), operator, value)
    if indicator == "atr":
        return numeric_condition(latest.get("atr"), previous.get("atr"), operator, value)
    if indicator == "delivery_volume":
        return numeric_condition(latest.get("delivery_volume_pct"), previous.get("delivery_volume_pct"), operator, value)
    if indicator == "volume_breakout":
        threshold = value if is_number(value) else 1.5
        if operator == "above_average":
            return compare(latest.get("volume_breakout_ratio"), threshold, ">")
        if operator == "below_average":
            return compare(latest.get("volume_breakout_ratio"), threshold, "<")
    if indicator == "macd":
        return pair_condition(latest, previous, "macd", "macd_signal", operator)
    if indicator == "stoch_rsi":
        if operator in {"above", "below"}:
            return numeric_condition(latest.get("stoch_rsi_k"), previous.get("stoch_rsi_k"), operator, value)
        return pair_condition(latest, previous, "stoch_rsi_k", "stoch_rsi_d", operator)
    if indicator == "supertrend":
        return supertrend_condition(latest, previous, operator)
    if indicator == "ema":
        return moving_average_condition(latest, previous, "ema_20", "ema_50", operator)
    if indicator == "sma":
        return moving_average_condition(latest, previous, "sma_20", "sma_50", operator)
    if indicator == "vwap":
        return price_level_condition(latest, previous, "vwap", operator)
    if indicator == "ichimoku":
        return ichimoku_condition(latest, operator)
    if indicator == "psar":
        return psar_condition(latest, previous, operator)
    if indicator == "bollinger":
        return bollinger_condition(latest, operator)
    if indicator == "keltner":
        return keltner_condition(latest, operator)
    if indicator == "obv":
        return compare_series(latest.get("obv"), previous.get("obv"), operator)
    return False


def numeric_condition(current, previous, operator, value):
    if not is_number(value):
        return False
    if operator == "above":
        return compare(current, value, ">")
    if operator == "below":
        return compare(current, value, "<")
    if operator == "crosses_above":
        return compare(previous, value, "<=") and compare(current, value, ">")
    if operator == "crosses_below":
        return compare(previous, value, ">=") and compare(current, value, "<")
    return False


def pair_condition(latest, previous, primary_key, secondary_key, operator):
    current_primary = latest.get(primary_key)
    current_secondary = latest.get(secondary_key)
    previous_primary = previous.get(primary_key)
    previous_secondary = previous.get(secondary_key)
    if operator == "above_signal":
        return compare(current_primary, current_secondary, ">")
    if operator == "below_signal":
        return compare(current_primary, current_secondary, "<")
    if operator == "bullish_cross":
        return compare(previous_primary, previous_secondary, "<=") and compare(current_primary, current_secondary, ">")
    if operator == "bearish_cross":
        return compare(previous_primary, previous_secondary, ">=") and compare(current_primary, current_secondary, "<")
    return False


def supertrend_condition(latest, previous, operator):
    close = latest.get("close")
    supertrend = latest.get("supertrend")
    direction = latest.get("supertrend_direction")
    previous_direction = previous.get("supertrend_direction")
    if operator == "price_above":
        return compare(close, supertrend, ">")
    if operator == "price_below":
        return compare(close, supertrend, "<")
    if operator == "buy_signal":
        return (previous_direction or 0) <= 0 and (direction or 0) > 0
    if operator == "sell_signal":
        return (previous_direction or 0) >= 0 and (direction or 0) < 0
    return False


def moving_average_condition(latest, previous, fast_key, slow_key, operator):
    if operator == "price_above":
        return compare(latest.get("close"), latest.get(fast_key), ">")
    if operator == "price_below":
        return compare(latest.get("close"), latest.get(fast_key), "<")
    if operator == "bullish_cross":
        return compare(previous.get(fast_key), previous.get(slow_key), "<=") and compare(latest.get(fast_key), latest.get(slow_key), ">")
    if operator == "bearish_cross":
        return compare(previous.get(fast_key), previous.get(slow_key), ">=") and compare(latest.get(fast_key), latest.get(slow_key), "<")
    return False


def price_level_condition(latest, previous, level_key, operator):
    if operator == "price_above":
        return compare(latest.get("close"), latest.get(level_key), ">")
    if operator == "price_below":
        return compare(latest.get("close"), latest.get(level_key), "<")
    if operator == "crossover":
        return compare(previous.get("close"), previous.get(level_key), "<=") and compare(latest.get("close"), latest.get(level_key), ">")
    if operator == "crossunder":
        return compare(previous.get("close"), previous.get(level_key), ">=") and compare(latest.get("close"), latest.get(level_key), "<")
    return False


def ichimoku_condition(latest, operator):
    close = latest.get("close")
    span_a = latest.get("ichimoku_span_a")
    span_b = latest.get("ichimoku_span_b")
    upper_cloud = max_number(span_a, span_b)
    lower_cloud = min_number(span_a, span_b)
    if operator == "price_above_cloud":
        return compare(close, upper_cloud, ">")
    if operator == "price_below_cloud":
        return compare(close, lower_cloud, "<")
    if operator == "conversion_above_base":
        return compare(latest.get("ichimoku_conversion"), latest.get("ichimoku_base"), ">")
    if operator == "conversion_below_base":
        return compare(latest.get("ichimoku_conversion"), latest.get("ichimoku_base"), "<")
    return False


def psar_condition(latest, previous, operator):
    if operator == "price_above":
        return compare(latest.get("close"), latest.get("psar"), ">")
    if operator == "price_below":
        return compare(latest.get("close"), latest.get("psar"), "<")
    if operator == "bullish_flip":
        return (previous.get("psar_trend") or 0) <= 0 and (latest.get("psar_trend") or 0) > 0
    if operator == "bearish_flip":
        return (previous.get("psar_trend") or 0) >= 0 and (latest.get("psar_trend") or 0) < 0
    return False


def bollinger_condition(latest, operator):
    close = latest.get("close")
    if operator == "near_upper":
        return near_level(close, latest.get("bb_upper"))
    if operator == "near_lower":
        return near_level(close, latest.get("bb_lower"))
    if operator == "breakout":
        return compare(close, latest.get("bb_upper"), ">") or compare(close, latest.get("bb_lower"), "<")
    if operator == "squeeze":
        return bool(latest.get("bb_squeeze"))
    return False


def keltner_condition(latest, operator):
    close = latest.get("close")
    if operator == "above_upper":
        return compare(close, latest.get("keltner_upper"), ">")
    if operator == "below_lower":
        return compare(close, latest.get("keltner_lower"), "<")
    if operator == "inside":
        return compare(close, latest.get("keltner_upper"), "<=") and compare(close, latest.get("keltner_lower"), ">=")
    return False


def compare_series(current, previous, operator):
    if operator == "rising":
        return compare(current, previous, ">")
    if operator == "falling":
        return compare(current, previous, "<")
    return False


def compare(left, right, operator):
    if not is_number(left) or not is_number(right):
        return False
    if operator == ">":
        return left > right
    if operator == "<":
        return left < right
    if operator == ">=":
        return left >= right
    if operator == "<=":
        return left <= right
    return False


def near_level(price, level, tolerance=0.01):
    if not is_number(price) or not is_number(level) or price == 0:
        return False
    return abs(price - level) / abs(price) <= tolerance


def parse_condition_value(value):
    try:
        if value in (None, ""):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def is_number(value):
    return isinstance(value, (int, float)) and not math.isnan(value)


def max_number(left, right):
    values = [value for value in (left, right) if is_number(value)]
    return max(values) if values else None


def min_number(left, right):
    values = [value for value in (left, right) if is_number(value)]
    return min(values) if values else None


def derive_score(snapshot):
    statuses = snapshot["statuses"]
    latest = snapshot["latest"]
    score = 0
    score += 1 if statuses["supertrendStatus"] == "Bullish" else -1 if statuses["supertrendStatus"] == "Bearish" else 0
    score += 1 if statuses["vwapStatus"] == "Above VWAP" else -1 if statuses["vwapStatus"] == "Below VWAP" else 0
    if is_number(latest.get("rsi")):
        score += 1 if latest["rsi"] >= 55 else -1 if latest["rsi"] <= 45 else 0
    return score


def bias_label(score):
    if score > 0:
        return "Bullish"
    if score < 0:
        return "Bearish"
    return "Neutral"


def strength_label(score, total):
    denominator = max(total, 3)
    absolute = abs(score)
    if score > 0:
        tone = "Strong Bullish" if absolute >= max(3, math.ceil(denominator * 0.67)) else "Moderate Bullish"
    elif score < 0:
        tone = "Strong Bearish" if absolute >= max(3, math.ceil(denominator * 0.67)) else "Moderate Bearish"
    else:
        tone = "Neutral"
    return f"{absolute}/{denominator} {tone}"
