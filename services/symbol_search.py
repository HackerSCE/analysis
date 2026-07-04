import logging
import threading
import time

from services.symbol_mapper import (
    FYERS_NSE_CM_SYMBOL_MASTER_URL,
    FYERS_NSE_FO_SYMBOL_MASTER_URL,
    SYMBOL_MASTER_CACHE_SECONDS,
    read_fyers_symbol_master,
)


logger = logging.getLogger(__name__)

FYERS_BSE_CM_SYMBOL_MASTER_URL = "https://public.fyers.in/sym_details/BSE_CM.csv"
FYERS_MCX_COM_SYMBOL_MASTER_URL = "https://public.fyers.in/sym_details/MCX_COM.csv"
FYERS_BSE_FO_SYMBOL_MASTER_URL = "https://public.fyers.in/sym_details/BSE_FO.csv"
FYERS_NSE_CD_SYMBOL_MASTER_URL = "https://public.fyers.in/sym_details/NSE_CD.csv"

_search_cache = {
    "loaded_at": 0,
    "payload": None,
}
_search_lock = threading.Lock()


def search_symbols(query, limit=15):
    normalized = normalize_query(query)
    if not normalized:
        return []

    catalog = get_symbol_search_catalog()
    items = catalog["items"]
    exact_matches = []
    prefix_matches = []
    contains_matches = []

    for item in items:
        if len(exact_matches) + len(prefix_matches) + len(contains_matches) >= 500:
            break

        if not matches_query(item, normalized):
            continue

        name = item.get("name_normalized", "")
        symbol = item.get("symbol_normalized", "")

        if normalized == name or normalized == symbol:
            exact_matches.append(item)
        elif name.startswith(normalized) or symbol.startswith(normalized):
            prefix_matches.append(item)
        else:
            contains_matches.append(item)

    ranked = exact_matches + prefix_matches + contains_matches
    return [format_search_item(item) for item in ranked[: max(1, min(int(limit or 15), 25))]]


def get_symbol_search_catalog(force_refresh=False):
    now = time.time()
    cached = _search_cache.get("payload")
    if (
        not force_refresh
        and cached
        and now - _search_cache.get("loaded_at", 0) < SYMBOL_MASTER_CACHE_SECONDS
    ):
        return cached

    with _search_lock:
        now = time.time()
        cached = _search_cache.get("payload")
        if (
            not force_refresh
            and cached
            and now - _search_cache.get("loaded_at", 0) < SYMBOL_MASTER_CACHE_SECONDS
        ):
            return cached

        payload = build_symbol_search_catalog()
        _search_cache["loaded_at"] = now
        _search_cache["payload"] = payload
        logger.info(
            "Symbol search catalog loaded: %s records (%s)",
            payload.get("record_count", 0),
            payload.get("loaded_at"),
        )
        return payload


def build_symbol_search_catalog():
    items_by_symbol = {}
    _load_cm_rows(FYERS_NSE_CM_SYMBOL_MASTER_URL, "NSE", items_by_symbol)
    _load_cm_rows(FYERS_BSE_CM_SYMBOL_MASTER_URL, "BSE", items_by_symbol)
    _load_fo_rows(FYERS_NSE_FO_SYMBOL_MASTER_URL, items_by_symbol, exchange_label="NFO")
    _load_fo_rows(FYERS_BSE_FO_SYMBOL_MASTER_URL, items_by_symbol, exchange_label="BFO")
    _load_fo_rows(FYERS_NSE_CD_SYMBOL_MASTER_URL, items_by_symbol, exchange_label="CDS")
    _load_mcx_rows(FYERS_MCX_COM_SYMBOL_MASTER_URL, items_by_symbol)

    items = sorted(items_by_symbol.values(), key=_sort_key)
    return {
        "loaded_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "record_count": len(items),
        "items": items,
    }


def _load_cm_rows(url, exchange, items_by_symbol):
    rows = read_fyers_symbol_master(url)
    for row in rows:
        if len(row) < 14:
            continue

        fyers_symbol = (row[9] or "").strip().upper()
        if not fyers_symbol or not fyers_symbol.startswith(f"{exchange}:"):
            continue

        name = (row[1] or "").strip() or (row[13] or "").strip() or fyers_symbol
        type_label = "Index" if fyers_symbol.endswith("-INDEX") else "Stock"

        item = {
            "name": name,
            "name_normalized": normalize_query(name),
            "symbol": fyers_symbol,
            "symbol_normalized": normalize_query(fyers_symbol),
            "type": type_label,
            "exchange": exchange,
            "priority": _type_priority(type_label),
        }
        _upsert_item(items_by_symbol, item)


def _load_fo_rows(url, items_by_symbol, exchange_label="NFO"):
    rows = read_fyers_symbol_master(url)
    for row in rows:
        if len(row) < 14:
            continue

        fyers_symbol = (row[9] or "").strip().upper()
        if not fyers_symbol or not (fyers_symbol.startswith("NSE:") or fyers_symbol.startswith("BSE:")):
            continue

        type_label = infer_fo_type(fyers_symbol)
        if type_label not in {"Future", "Option"}:
            continue

        root_name = (row[13] or "").strip() or (row[1] or "").strip() or fyers_symbol
        item = {
            "name": root_name,
            "name_normalized": normalize_query(root_name),
            "symbol": fyers_symbol,
            "symbol_normalized": normalize_query(fyers_symbol),
            "type": type_label,
            "exchange": exchange_label,
            "priority": _type_priority(type_label),
        }
        _upsert_item(items_by_symbol, item)


def _load_mcx_rows(url, items_by_symbol):
    rows = read_fyers_symbol_master(url)
    for row in rows:
        if len(row) < 10:
            continue

        fyers_symbol = (row[9] or "").strip().upper()
        if not fyers_symbol or not fyers_symbol.startswith("MCX:"):
            continue

        base_name = (row[13] if len(row) > 13 else "") or (row[1] or "")
        name = str(base_name).strip() or fyers_symbol.split(":", 1)[1]
        type_label = "MCX"
        if fyers_symbol.endswith("FUT"):
            type_label = "Future"
        elif fyers_symbol.endswith("CE") or fyers_symbol.endswith("PE"):
            type_label = "Option"

        item = {
            "name": name,
            "name_normalized": normalize_query(name),
            "symbol": fyers_symbol,
            "symbol_normalized": normalize_query(fyers_symbol),
            "type": type_label,
            "exchange": "MCX",
            "priority": _type_priority(type_label),
        }
        _upsert_item(items_by_symbol, item)


def infer_fo_type(symbol):
    if symbol.endswith("FUT"):
        return "Future"
    if symbol.endswith("CE") or symbol.endswith("PE"):
        return "Option"
    return "Other"


def matches_query(item, query):
    return query in item.get("name_normalized", "") or query in item.get("symbol_normalized", "")


def normalize_query(value):
    return str(value or "").upper().strip()


def format_search_item(item):
    return {
        "name": item.get("name"),
        "symbol": item.get("symbol"),
        "type": item.get("type"),
        "exchange": item.get("exchange"),
    }


def _upsert_item(items_by_symbol, item):
    symbol = item["symbol"]
    previous = items_by_symbol.get(symbol)
    if not previous:
        items_by_symbol[symbol] = item
        return

    if item.get("priority", 99) < previous.get("priority", 99):
        items_by_symbol[symbol] = item


def _sort_key(item):
    return (
        item.get("priority", 99),
        item.get("name_normalized", ""),
        item.get("symbol_normalized", ""),
    )


def _type_priority(type_label):
    order = {
        "Stock": 1,
        "Index": 2,
        "Future": 3,
        "Option": 4,
        "MCX": 5,
    }
    return order.get(type_label, 9)