import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta

import pandas as pd

from services.cache_service import RateLimiter, TTLCache
from services.indicator_engine import (
    CONDITION_BIAS,
    INDICATOR_GROUPS,
    bias_label,
    calculate_indicator_snapshot,
    derive_score,
    evaluate_condition,
    strength_label,
)
from services.sector_mapping import SECTOR_FILTERS, display_sector, sectors_for_symbol
from services.symbol_mapper import validate_catalog_symbol
from utils.batching import batch_values


logger = logging.getLogger(__name__)


INSTRUMENT_TYPES = [
    {"id": "spot", "label": "Spot Stocks"},
    {"id": "near", "label": "Near Month Futures"},
    {"id": "next", "label": "Next Month Futures"},
    {"id": "far", "label": "Far Month Futures"},
]


TIMEFRAMES = [
    {"id": "1", "label": "1 Minute", "resolution": "1", "lookbackDays": 7},
    {"id": "3", "label": "3 Minute", "resolution": "3", "lookbackDays": 7},
    {"id": "5", "label": "5 Minute", "resolution": "5", "lookbackDays": 14},
    {"id": "15", "label": "15 Minute", "resolution": "15", "lookbackDays": 30},
    {"id": "30", "label": "30 Minute", "resolution": "30", "lookbackDays": 45},
    {"id": "60", "label": "1 Hour", "resolution": "60", "lookbackDays": 90},
    {"id": "240", "label": "4 Hour", "resolution": "240", "lookbackDays": 180},
    {"id": "1D", "label": "1 Day", "resolution": "1D", "lookbackDays": 600},
    {"id": "1W", "label": "1 Week", "resolution": "1D", "aggregation": "W-FRI", "lookbackDays": 600},
]

TIMEFRAME_ALIASES = {
    "D": "1D",
    "DAY": "1D",
    "W": "1W",
    "WEEK": "1W",
}


PRESETS = [
    {
        "id": "intraday_breakout",
        "label": "Intraday Breakout",
        "timeframe": "5",
        "logic": "AND",
        "instrumentTypes": ["spot", "near"],
        "sectors": ["All Sectors"],
        "conditions": [
            {"indicator": "volume_breakout", "operator": "above_average", "value": 1.8},
            {"indicator": "vwap", "operator": "price_above", "value": None},
            {"indicator": "bollinger", "operator": "breakout", "value": None},
        ],
    },
    {
        "id": "swing_bullish",
        "label": "Swing Bullish",
        "timeframe": "1D",
        "logic": "AND",
        "instrumentTypes": ["spot"],
        "sectors": ["All Sectors"],
        "conditions": [
            {"indicator": "rsi", "operator": "above", "value": 55},
            {"indicator": "adx", "operator": "above", "value": 20},
            {"indicator": "supertrend", "operator": "price_above", "value": None},
        ],
    },
    {
        "id": "oversold_reversal",
        "label": "Oversold Reversal",
        "timeframe": "15",
        "logic": "OR",
        "instrumentTypes": ["spot"],
        "sectors": ["All Sectors"],
        "conditions": [
            {"indicator": "rsi", "operator": "below", "value": 30},
            {"indicator": "bollinger", "operator": "near_lower", "value": None},
            {"indicator": "stoch_rsi", "operator": "below", "value": 20},
        ],
    },
    {
        "id": "momentum_buying",
        "label": "Momentum Buying",
        "timeframe": "15",
        "logic": "AND",
        "instrumentTypes": ["spot", "near"],
        "sectors": ["All Sectors"],
        "conditions": [
            {"indicator": "rsi", "operator": "above", "value": 60},
            {"indicator": "macd", "operator": "above_signal", "value": None},
            {"indicator": "vwap", "operator": "price_above", "value": None},
        ],
    },
    {
        "id": "trend_following",
        "label": "Trend Following",
        "timeframe": "60",
        "logic": "AND",
        "instrumentTypes": ["spot"],
        "sectors": ["All Sectors"],
        "conditions": [
            {"indicator": "supertrend", "operator": "price_above", "value": None},
            {"indicator": "adx", "operator": "above", "value": 25},
            {"indicator": "ema", "operator": "price_above", "value": None},
        ],
    },
    {
        "id": "volume_explosion",
        "label": "Volume Explosion",
        "timeframe": "5",
        "logic": "AND",
        "instrumentTypes": ["spot", "near"],
        "sectors": ["All Sectors"],
        "conditions": [
            {"indicator": "volume_breakout", "operator": "above_average", "value": 2.5},
            {"indicator": "obv", "operator": "rising", "value": None},
        ],
    },
]


HISTORY_CACHE_SECONDS = 60
MAX_SCAN_WORKERS = 5
SCAN_BATCH_SIZE = 50
SCAN_BATCH_PAUSE_SECONDS = 0.4
HISTORY_REQUEST_INTERVAL_SECONDS = 0.28
_history_cache = TTLCache(HISTORY_CACHE_SECONDS, name="indicator_candle_cache")
_history_rate_limiter = RateLimiter(HISTORY_REQUEST_INTERVAL_SECONDS, name="fyers_history")


def get_screener_metadata(catalog_items=None):
    symbols = []
    if catalog_items:
        symbols = [
            {
                "symbol": item["symbol"],
                "stockName": item["stock_name"],
                "spotSymbol": item["spot_symbol"],
                "sectors": item.get("sectors") or sectors_for_symbol(item["symbol"], item.get("stock_name", "")),
            }
            for item in catalog_items
        ]

    return {
        "instrumentTypes": INSTRUMENT_TYPES,
        "sectors": SECTOR_FILTERS,
        "timeframes": TIMEFRAMES,
        "indicatorGroups": INDICATOR_GROUPS,
        "presets": PRESETS,
        "symbols": symbols,
        "refreshIntervalSeconds": 60,
    }


def run_indicator_screener(payload, catalog, history_fetcher, quote_fetcher=None):
    default_timeframe = resolve_timeframe(payload.get("timeframe"))
    conditions = normalise_conditions(payload.get("conditions") or [], default_timeframe["id"])
    logic = (payload.get("logic") or "AND").upper()
    if logic not in {"AND", "OR"}:
        logic = "AND"

    catalog_items = catalog.get("items", []) if isinstance(catalog, dict) else catalog
    stats = new_scan_stats()
    instruments = build_instrument_universe(
        catalog_items,
        payload.get("instrumentTypes") or ["spot"],
        payload.get("sectors") or ["All Sectors"],
        catalog if isinstance(catalog, dict) else None,
    )
    stats["symbols_scanned"] = len(instruments)
    instruments, invalid_symbol_warnings = validate_scan_symbols(instruments, catalog if isinstance(catalog, dict) else None)
    stats["valid_symbols"] = len(instruments)
    stats["invalid_symbols"] = len(invalid_symbol_warnings)

    date_to = date.today()
    started_at = time.time()
    warnings = invalid_symbol_warnings[:20]
    rows = []

    if not instruments:
        logger.warning("Indicator screener found no valid symbols for selected scan. stats=%s", stats)
        return {
            "generated_at": datetime.now().astimezone().isoformat(),
            "refresh_interval_seconds": 60,
            "summary": build_summary([], 0, 0),
            "rows": [],
            "warnings": warnings or ["No valid instruments matched the selected universe and sector filters."],
            "scan": build_scan_payload(default_timeframe, conditions, logic, payload),
            "health": stats,
        }

    for batch_index, instrument_batch in enumerate(batch_values(instruments, SCAN_BATCH_SIZE), start=1):
        logger.info(
            "Processing indicator scan batch %s size=%s timeframe=%s logic=%s",
            batch_index,
            len(instrument_batch),
            default_timeframe["label"],
            logic,
        )
        with ThreadPoolExecutor(max_workers=min(MAX_SCAN_WORKERS, len(instrument_batch))) as executor:
            futures = {
                executor.submit(
                    scan_instrument,
                    instrument,
                    default_timeframe,
                    conditions,
                    logic,
                    date_to,
                    history_fetcher,
                    stats,
                ): instrument
                for instrument in instrument_batch
            }

            for future in as_completed(futures):
                instrument = futures[future]
                try:
                    row = future.result()
                    if row:
                        rows.append(row)
                except Exception as exc:
                    stats["failed_symbols"] += 1
                    message = str(exc)
                    if "invalid input" in message.lower():
                        stats["invalid_symbols"] += 1
                    if "request limit" in message.lower():
                        stats["rate_limit_failures"] += 1
                    warning = f"{instrument['rootSymbol']} {instrument['instrumentType']}: {message}"
                    warnings.append(warning)
                    logger.warning("Indicator scan symbol failed: %s", warning)

        if batch_index * SCAN_BATCH_SIZE < len(instruments):
            time.sleep(SCAN_BATCH_PAUSE_SECONDS)

    rows = sorted(rows, key=lambda row: (-abs(row.get("signalScore", 0)), row["stockName"], row["instrumentType"]))
    elapsed_ms = int((time.time() - started_at) * 1000)
    stats["elapsed_ms"] = elapsed_ms
    stats["matching_results"] = len(rows)
    stats["cache_size"] = _history_cache.size()
    logger.info("Indicator screener completed stats=%s", stats)
    return {
        "generated_at": datetime.now().astimezone().isoformat(),
        "refresh_interval_seconds": 60,
        "summary": build_summary(rows, len({instrument["rootSymbol"] for instrument in instruments}), len(instruments)),
        "rows": rows,
        "warnings": summarise_warnings(warnings, stats),
        "scan": build_scan_payload(default_timeframe, conditions, logic, payload),
        "elapsed_ms": elapsed_ms,
        "health": stats,
    }


def resolve_timeframe(value):
    canonical_id = canonical_timeframe_id(value)
    for timeframe in TIMEFRAMES:
        if timeframe["id"] == canonical_id:
            return timeframe
    return TIMEFRAMES[2]


def canonical_timeframe_id(value):
    raw = str(value or "").strip().upper()
    return TIMEFRAME_ALIASES.get(raw, raw)


def normalise_conditions(conditions, default_timeframe_id):
    normalised = []
    for condition in conditions:
        indicator = condition.get("indicator")
        operator = condition.get("operator")
        if not indicator or not operator:
            continue
        timeframe = resolve_timeframe(condition.get("timeframe") or default_timeframe_id)
        value = condition.get("value")
        normalised.append({
            "indicator": indicator,
            "operator": operator,
            "value": value if value not in ("", None) else None,
            "timeframe": timeframe["id"],
            "timeframeLabel": timeframe["label"],
            "timeframeResolution": timeframe["resolution"],
        })
    return normalised


def new_scan_stats():
    return {
        "symbols_scanned": 0,
        "valid_symbols": 0,
        "invalid_symbols": 0,
        "cache_hits": 0,
        "cache_misses": 0,
        "api_requests": 0,
        "quote_api_requests": 0,
        "history_api_requests": 0,
        "failed_symbols": 0,
        "rate_limit_failures": 0,
        "matching_results": 0,
        "elapsed_ms": 0,
        "cache_size": 0,
    }


def build_instrument_universe(catalog_items, instrument_type_ids, selected_sectors, catalog=None):
    selected_types = set(instrument_type_ids or ["spot"])
    selected_sector_set = set(selected_sectors or ["All Sectors"])
    use_all_sectors = "All Sectors" in selected_sector_set or not selected_sector_set
    instruments = []

    for item in catalog_items:
        sectors = item.get("sectors") or sectors_for_symbol(item["symbol"], item.get("stock_name", ""))
        if not use_all_sectors and not selected_sector_set.intersection(sectors):
            continue

        for instrument_type in INSTRUMENT_TYPES:
            type_id = instrument_type["id"]
            if type_id not in selected_types:
                continue

            fyers_symbol = item["spot_symbol"] if type_id == "spot" else item["contracts"][type_id]["fyers_symbol"]
            if type_id == "spot" and catalog and catalog.get("spot_symbol_map"):
                fyers_symbol = catalog["spot_symbol_map"].get(item["symbol"], fyers_symbol)
            expiry = None if type_id == "spot" else item["contracts"][type_id]["expiry"]
            instruments.append({
                "rootSymbol": item["symbol"],
                "stockName": item["stock_name"],
                "fyersSymbol": fyers_symbol,
                "instrumentType": instrument_type["label"],
                "instrumentTypeId": type_id,
                "expiry": expiry,
                "sector": display_sector(sectors),
                "sectorTags": sectors,
            })

    return instruments


def validate_scan_symbols(instruments, catalog=None):
    valid_instruments = []
    warnings = []
    for instrument in instruments:
        symbol = instrument.get("fyersSymbol")
        instrument_type_id = instrument.get("instrumentTypeId")
        if validate_catalog_symbol(symbol, instrument_type_id, catalog):
            valid_instruments.append(instrument)
            continue
        warning = f"{instrument.get('rootSymbol')} {instrument.get('instrumentType')}: invalid FYERS symbol {symbol}"
        warnings.append(warning)
        logger.warning("Invalid screener symbol skipped: %s", warning)
    return valid_instruments, warnings


def scan_instrument(instrument, default_timeframe, conditions, logic, date_to, history_fetcher, stats):
    timeframe_plan = build_timeframe_plan(default_timeframe, conditions)
    snapshots = {}
    for timeframe_id, timeframe in timeframe_plan.items():
        snapshot = build_timeframe_snapshot(
            instrument["fyersSymbol"],
            timeframe,
            date_to,
            history_fetcher,
            stats,
        )
        snapshots[timeframe_id] = snapshot

    evaluation = evaluate_conditions_across_timeframes(snapshots, conditions, logic, default_timeframe["id"])
    if not evaluation["passed"]:
        return None

    primary_timeframe_id = default_timeframe["id"]
    primary_snapshot = snapshots.get(primary_timeframe_id) or next(iter(snapshots.values()), None)
    if not primary_snapshot:
        return None

    latest = primary_snapshot["latest"]
    statuses = primary_snapshot["statuses"]
    timeframe_summary = format_timeframe_summary([snapshots[key]["meta"]["label"] for key in snapshots.keys()])
    return {
        "symbol": instrument["rootSymbol"],
        "stockName": instrument["stockName"],
        "sector": instrument["sector"],
        "sectorTags": instrument["sectorTags"],
        "instrumentType": instrument["instrumentType"],
        "instrumentTypeId": instrument["instrumentTypeId"],
        "fyersSymbol": instrument["fyersSymbol"],
        "expiry": instrument["expiry"],
        "currentPrice": round_float(latest.get("close"), 2),
        "rsi": round_float(latest.get("rsi"), 2),
        "adx": round_float(latest.get("adx"), 2),
        "supertrendStatus": statuses["supertrendStatus"],
        "vwapStatus": statuses["vwapStatus"],
        "bollingerStatus": statuses["bollingerStatus"],
        "signalStrength": evaluation["signalStrength"],
        "signalBias": evaluation["signalBias"],
        "signalScore": evaluation["score"],
        "matchedConditions": evaluation["matchedCount"],
        "totalConditions": evaluation["totalConditions"],
        "timeframe": timeframe_summary,
        "timeframeId": primary_timeframe_id,
        "primaryTimeframe": primary_timeframe_id,
        "conditionTimeframes": [condition["timeframeLabel"] for condition in conditions],
        "volume": int(latest.get("volume") or 0),
        "volumeBreakoutRatio": round_float(latest.get("volume_breakout_ratio"), 2),
        "highestMomentumMetric": round_float(latest.get("momentum"), 2),
        "lastUpdated": serialise_datetime(latest.get("datetime")) or datetime.now().astimezone().isoformat(),
    }


def get_history_dataframe(symbol, resolution, date_from, date_to, history_fetcher, stats=None):
    cache_key = (symbol, resolution, date_from.isoformat(), date_to.isoformat())
    cached = _history_cache.get(cache_key)
    if cached is not None:
        if stats is not None:
            stats["cache_hits"] += 1
        logger.info("Indicator candle cache hit: %s %s", symbol, resolution)
        return cached.copy()

    if stats is not None:
        stats["cache_misses"] += 1
        stats["api_requests"] += 1
        stats["history_api_requests"] += 1
    logger.info("Indicator candle cache miss: %s %s", symbol, resolution)
    _history_rate_limiter.wait()
    df = history_fetcher(symbol, resolution, date_from, date_to)
    _history_cache.set(cache_key, df.copy())
    return df.copy()


def build_timeframe_plan(default_timeframe, conditions):
    timeframe_ids = [default_timeframe["id"]]
    timeframe_ids.extend(condition["timeframe"] for condition in conditions)
    unique_timeframe_ids = []
    seen = set()
    for timeframe_id in timeframe_ids:
        if timeframe_id in seen:
            continue
        seen.add(timeframe_id)
        unique_timeframe_ids.append(timeframe_id)

    plan = {}
    for timeframe_id in unique_timeframe_ids:
        plan[timeframe_id] = resolve_timeframe(timeframe_id)
    return plan


def build_timeframe_snapshot(symbol, timeframe, date_to, history_fetcher, stats):
    date_from = date_to - timedelta(days=timeframe["lookbackDays"])
    df = get_history_dataframe(
        symbol,
        timeframe["resolution"],
        date_from,
        date_to,
        history_fetcher,
        stats,
    )
    if df.empty:
        raise ValueError("FYERS returned no candle history.")

    df = transform_timeframe_dataframe(df, timeframe)
    if df.empty:
        raise ValueError("FYERS returned no candle history.")

    snapshot = calculate_indicator_snapshot(df)
    snapshot["meta"] = timeframe
    return snapshot


def transform_timeframe_dataframe(df, timeframe):
    aggregation = timeframe.get("aggregation")
    if not aggregation:
        return df

    if "datetime" not in df.columns:
        return df

    working = df.copy()
    working = working.dropna(subset=["datetime"]).sort_values("datetime")
    if working.empty:
        return working

    working["datetime"] = pd.to_datetime(working["datetime"], utc=False)
    working = working.set_index("datetime")
    resampled = working.resample(aggregation, label="right", closed="right").agg({
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum",
    })
    return resampled.dropna(subset=["open", "high", "low", "close"]).reset_index()


def evaluate_conditions_across_timeframes(snapshots, conditions, logic, default_timeframe_id):
    active_conditions = [condition for condition in conditions if condition.get("indicator") and condition.get("operator")]
    if not active_conditions:
        primary_snapshot = snapshots.get(default_timeframe_id) or next(iter(snapshots.values()), None)
        if not primary_snapshot:
            return {
                "passed": True,
                "matches": [],
                "matchedCount": 0,
                "totalConditions": 0,
                "score": 0,
                "signalBias": "Neutral",
                "signalStrength": strength_label(0, 3),
            }
        derived_score = derive_score(primary_snapshot)
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
        timeframe_id = condition.get("timeframe") or default_timeframe_id
        snapshot = snapshots.get(timeframe_id) or snapshots.get(default_timeframe_id) or next(iter(snapshots.values()), None)
        if not snapshot:
            evaluations.append({
                "condition": condition,
                "matched": False,
                "bias": 0,
            })
            continue
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


def build_summary(rows, total_stocks_scanned, total_instruments_scanned):
    bullish = [row for row in rows if row.get("signalBias") == "Bullish"]
    bearish = [row for row in rows if row.get("signalBias") == "Bearish"]
    strongest_momentum = max(rows, key=lambda row: abs(row.get("highestMomentumMetric") or 0), default=None)
    highest_adx = max(rows, key=lambda row: row.get("adx") or 0, default=None)
    highest_volume = max(rows, key=lambda row: row.get("volumeBreakoutRatio") or 0, default=None)
    return {
        "totalStocksScanned": total_stocks_scanned,
        "totalInstrumentsScanned": total_instruments_scanned,
        "matchingResults": len(rows),
        "bullishSignals": len(bullish),
        "bearishSignals": len(bearish),
        "strongestMomentumStock": summary_stock(strongest_momentum, "highestMomentumMetric"),
        "highestAdxStock": summary_stock(highest_adx, "adx"),
        "highestVolumeBreakout": summary_stock(highest_volume, "volumeBreakoutRatio"),
    }


def summary_stock(row, value_key):
    if not row:
        return None
    return {
        "symbol": row["symbol"],
        "stockName": row["stockName"],
        "value": row.get(value_key),
    }


def build_scan_payload(timeframe, conditions, logic, payload):
    return {
        "instrumentTypes": payload.get("instrumentTypes") or ["spot"],
        "sectors": payload.get("sectors") or ["All Sectors"],
        "timeframe": timeframe["id"],
        "timeframeLabel": timeframe["label"],
        "defaultTimeframe": timeframe["id"],
        "defaultTimeframeLabel": timeframe["label"],
        "logic": logic,
        "conditions": conditions,
    }


def summarise_warnings(warnings, stats):
    compact_warnings = []
    if stats.get("invalid_symbols"):
        compact_warnings.append(f"Invalid symbols skipped: {stats['invalid_symbols']}")
    if stats.get("rate_limit_failures"):
        compact_warnings.append(f"FYERS rate-limit responses observed: {stats['rate_limit_failures']}")
    if stats.get("failed_symbols"):
        compact_warnings.append(f"Symbols failed without stopping scan: {stats['failed_symbols']}")

    seen = set(compact_warnings)
    for warning in warnings:
        if warning in seen:
            continue
        seen.add(warning)
        compact_warnings.append(warning)
        if len(compact_warnings) >= 40:
            break
    return compact_warnings


def format_timeframe_summary(timeframe_labels):
    labels = [label for label in timeframe_labels if label]
    unique_labels = []
    seen = set()
    for label in labels:
        if label in seen:
            continue
        seen.add(label)
        unique_labels.append(label)
    if not unique_labels:
        return "--"
    if len(unique_labels) == 1:
        return unique_labels[0]
    return " + ".join(unique_labels)


def round_float(value, digits=2):
    if isinstance(value, (int, float)):
        return round(float(value), digits)
    return None


def serialise_datetime(value):
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)
