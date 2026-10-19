import csv
import logging
import time
import urllib.request
from datetime import datetime
from io import StringIO
from zoneinfo import ZoneInfo

from services.sector_mapping import sectors_for_symbol
from services.symbol_validator import validate_symbol


logger = logging.getLogger(__name__)

IST = ZoneInfo("Asia/Kolkata")
FYERS_NSE_FO_SYMBOL_MASTER_URL = "https://public.fyers.in/sym_details/NSE_FO.csv"
FYERS_NSE_CM_SYMBOL_MASTER_URL = "https://public.fyers.in/sym_details/NSE_CM.csv"
FYERS_NSE_COM_SYMBOL_MASTER_URL = "https://public.fyers.in/sym_details/NSE_COM.csv"
FYERS_MCX_COM_SYMBOL_MASTER_URL = "https://public.fyers.in/sym_details/MCX_COM.csv"
SYMBOL_MASTER_CACHE_SECONDS = 6 * 60 * 60

_catalog_cache = {"loaded_at": 0, "payload": None}
_commodity_catalog_cache = {"loaded_at": 0, "payload": None}


def build_fno_contract_catalog():
    now = time.time()
    cached = _catalog_cache.get("payload")
    if cached and now - _catalog_cache.get("loaded_at", 0) < SYMBOL_MASTER_CACHE_SECONDS:
        logger.info("FYERS symbol catalog cache hit: %s instruments", len(cached.get("items", [])))
        return cached

    logger.info("Loading FYERS symbol masters for NSE CM and NSE FO")
    fo_rows = read_fyers_symbol_master(FYERS_NSE_FO_SYMBOL_MASTER_URL)
    cm_rows = read_fyers_symbol_master(FYERS_NSE_CM_SYMBOL_MASTER_URL)
    spot_by_fytoken, spot_by_symbol = build_spot_symbol_maps(cm_rows)
    futures_by_symbol = build_future_symbol_map(fo_rows)

    items = []
    expired_contracts_skipped = 0
    current_ts = time.time()
    for symbol, contracts in futures_by_symbol.items():
        live_contracts = [contract for contract in contracts if contract["expiry_ts"] >= current_ts]
        expired_contracts_skipped += len(contracts) - len(live_contracts)
        live_contracts = sorted(live_contracts, key=lambda contract: contract["expiry_ts"])
        unique_contracts = dedupe_contracts_by_symbol(live_contracts)
        if len(unique_contracts) < 3:
            continue

        selected_contracts = unique_contracts[:3]
        spot_meta = spot_by_fytoken.get(selected_contracts[0]["underlying_fytoken"]) or spot_by_symbol.get(symbol)
        if not spot_meta:
            logger.warning("No NSE CM spot mapping found for F&O symbol %s", symbol)
            continue

        sectors = sectors_for_symbol(symbol, spot_meta["stock_name"])
        items.append({
            "symbol": symbol,
            "stock_name": spot_meta["stock_name"],
            "spot_symbol": spot_meta["spot_symbol"],
            "sectors": sectors,
            "lot_size": selected_contracts[0]["lot_size"],
            "contracts": {
                "near": selected_contracts[0],
                "next": selected_contracts[1],
                "far": selected_contracts[2],
            },
        })

    payload = {
        "loaded_at": datetime.now(IST).isoformat(),
        "contract_count": sum(len(value) for value in futures_by_symbol.values()),
        "spot_symbol_count": len(spot_by_symbol),
        "expired_contracts_skipped": expired_contracts_skipped,
        "items": sorted(items, key=lambda item: item["symbol"]),
        "valid_symbols": build_valid_symbol_set(items),
        "spot_symbol_map": {
            symbol: meta["spot_symbol"]
            for symbol, meta in spot_by_symbol.items()
        },
    }
    _catalog_cache["loaded_at"] = now
    _catalog_cache["payload"] = payload
    logger.info(
        "FYERS symbol catalog loaded: fno_items=%s spot_symbols=%s expired_futures_skipped=%s",
        len(items),
        len(spot_by_symbol),
        expired_contracts_skipped,
    )
    return payload


def build_commodity_futures_catalog():
    """Build a current commodity-futures catalog from FYERS' NSE and MCX masters.

    Commodity futures do not have a cash-market counterpart in the NSE CM
    master, so each entry intentionally represents the futures contracts for a
    commodity rather than trying to manufacture a spot symbol.
    """
    now = time.time()
    cached = _commodity_catalog_cache.get("payload")
    if cached and now - _commodity_catalog_cache.get("loaded_at", 0) < SYMBOL_MASTER_CACHE_SECONDS:
        logger.info("FYERS commodity catalog cache hit: %s instruments", len(cached.get("items", [])))
        return cached

    logger.info("Loading FYERS symbol masters for NSE and MCX commodities")
    source_rows = []
    for exchange, source_url in (
        ("MCX", FYERS_MCX_COM_SYMBOL_MASTER_URL),
        ("NSE", FYERS_NSE_COM_SYMBOL_MASTER_URL),
    ):
        try:
            source_rows.append((exchange, read_fyers_symbol_master(source_url)))
        except Exception as exc:
            logger.warning("Unable to load FYERS %s commodity master: %s", exchange, exc)
    if not source_rows:
        raise RuntimeError("FYERS commodity symbol masters are currently unavailable.")
    futures_by_instrument = {}
    expired_contracts_skipped = 0
    current_ts = time.time()

    for exchange, rows in source_rows:
        for row in rows:
            contract = parse_commodity_future_contract(row, exchange)
            if not contract:
                continue
            key = (exchange, contract["symbol"])
            futures_by_instrument.setdefault(key, []).append(contract)

    items = []
    for (exchange, symbol), contracts in futures_by_instrument.items():
        live_contracts = [contract for contract in contracts if contract["expiry_ts"] >= current_ts]
        expired_contracts_skipped += len(contracts) - len(live_contracts)
        live_contracts = dedupe_contracts_by_symbol(sorted(live_contracts, key=lambda contract: contract["expiry_ts"]))
        if not live_contracts:
            continue

        items.append({
            "symbol": f"{exchange}:{symbol}",
            "root_symbol": symbol,
            "stock_name": symbol,
            "exchange": exchange,
            "lot_size": live_contracts[0]["lot_size"],
            "contracts": {
                f"contract_{index + 1}": contract
                for index, contract in enumerate(live_contracts)
            },
        })

    payload = {
        "loaded_at": datetime.now(IST).isoformat(),
        "contract_count": sum(len(value) for value in futures_by_instrument.values()),
        "expired_contracts_skipped": expired_contracts_skipped,
        "items": sorted(items, key=lambda item: (item["exchange"], item["root_symbol"])),
    }
    _commodity_catalog_cache["loaded_at"] = now
    _commodity_catalog_cache["payload"] = payload
    logger.info(
        "FYERS commodity catalog loaded: commodity_items=%s expired_futures_skipped=%s",
        len(items),
        expired_contracts_skipped,
    )
    return payload


def read_fyers_symbol_master(url):
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=30) as response:
        content = response.read().decode("utf-8", errors="replace")
    rows = list(csv.reader(StringIO(content)))
    logger.info("Loaded %s rows from %s", len(rows), url)
    return rows


def build_spot_symbol_maps(cm_rows):
    by_fytoken = {}
    by_symbol = {}
    for row in cm_rows:
        if len(row) <= 13:
            continue
        fyers_symbol = row[9].strip()
        if not is_valid_spot_symbol(fyers_symbol):
            continue

        root_symbol = clean_root_symbol(row[13] or fyers_symbol)
        if not root_symbol:
            continue

        meta = {
            "fytoken": row[0].strip(),
            "stock_name": row[1].strip() or root_symbol,
            "spot_symbol": fyers_symbol,
            "short_symbol": root_symbol,
        }
        by_symbol[root_symbol] = meta
        if meta["fytoken"]:
            by_fytoken[meta["fytoken"]] = meta

    return by_fytoken, by_symbol


def build_future_symbol_map(fo_rows):
    futures_by_symbol = {}
    for row in fo_rows:
        contract = parse_fno_future_contract(row)
        if not contract:
            continue
        futures_by_symbol.setdefault(contract["symbol"], []).append(contract)
    return futures_by_symbol


def parse_fno_future_contract(row):
    if len(row) < 18:
        return None
    fyers_symbol = row[9].strip()
    is_stock_future = row[2] == "13" and is_valid_future_symbol(fyers_symbol) and row[16] == "XX"
    if not is_stock_future:
        return None

    expiry_ts = parse_float(row[8])
    if not expiry_ts:
        return None

    return {
        "name": row[1].strip(),
        "symbol": clean_root_symbol(row[13]),
        "fyers_symbol": fyers_symbol,
        "lot_size": int(parse_float(row[3]) or 0),
        "expiry_ts": expiry_ts,
        "expiry": datetime.fromtimestamp(expiry_ts, IST).strftime("%d %b %Y"),
        "underlying_fytoken": row[17].strip(),
    }


def parse_commodity_future_contract(row, expected_exchange):
    if len(row) < 18:
        return None

    fyers_symbol = row[9].strip()
    if not (
        fyers_symbol.startswith(f"{expected_exchange}:")
        and fyers_symbol.endswith("FUT")
        and row[16].strip() == "XX"
    ):
        return None

    expiry_ts = parse_float(row[8])
    root_symbol = clean_root_symbol(row[13])
    if not expiry_ts or not root_symbol:
        return None

    return {
        "name": row[1].strip() or root_symbol,
        "symbol": root_symbol,
        "fyers_symbol": fyers_symbol,
        "lot_size": int(parse_float(row[3]) or 0),
        "expiry_ts": expiry_ts,
        "expiry": datetime.fromtimestamp(expiry_ts, IST).strftime("%d %b %Y"),
        "exchange": expected_exchange,
    }


def dedupe_contracts_by_symbol(contracts):
    seen = set()
    unique_contracts = []
    for contract in contracts:
        if contract["fyers_symbol"] in seen:
            continue
        seen.add(contract["fyers_symbol"])
        unique_contracts.append(contract)
    return unique_contracts


def build_valid_symbol_set(items):
    valid_symbols = set()
    for item in items:
        valid_symbols.add(item["spot_symbol"])
        for contract in item["contracts"].values():
            valid_symbols.add(contract["fyers_symbol"])
    return valid_symbols


def resolve_spot_symbol(root_symbol, catalog):
    cleaned = clean_root_symbol(root_symbol)
    return (catalog.get("spot_symbol_map") or {}).get(cleaned)


def validate_catalog_symbol(symbol, instrument_type_id, catalog=None):
    validation = validate_symbol(symbol)
    if not validation.get("valid"):
        return False

    if catalog and catalog.get("valid_symbols"):
        return symbol in catalog["valid_symbols"]
    return True


def is_valid_spot_symbol(symbol):
    return isinstance(symbol, str) and symbol.startswith("NSE:") and symbol.endswith("-EQ")


def is_valid_future_symbol(symbol):
    return isinstance(symbol, str) and symbol.startswith("NSE:") and symbol.endswith("FUT")


def clean_root_symbol(symbol):
    value = (symbol or "").upper().strip()
    if ":" in value:
        value = value.split(":", 1)[1]
    if value.endswith("-EQ"):
        value = value[:-3]
    if value.endswith("-BE"):
        value = value[:-3]
    return value


def parse_float(value):
    try:
        if value in (None, ""):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None
