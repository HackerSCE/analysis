import csv
import logging
import threading
import time
import urllib.request
from io import StringIO


logger = logging.getLogger(__name__)

SUPPORTED_EXCHANGES = {"NSE", "BSE", "MCX", "NFO", "CDS", "BFO"}
EXCHANGE_ALIASES = {
    "NFO": "NSE",
    "CDS": "NSE",
    "BFO": "BSE",
}

SYMBOL_MASTER_CACHE_SECONDS = 6 * 60 * 60

MASTER_SOURCES = {
    "NSE_CM": {
        "url": "https://public.fyers.in/sym_details/NSE_CM.csv",
        "logical_exchange": "NSE",
        "group": "spot",
    },
    "BSE_CM": {
        "url": "https://public.fyers.in/sym_details/BSE_CM.csv",
        "logical_exchange": "BSE",
        "group": "spot",
    },
    "NSE_FO": {
        "url": "https://public.fyers.in/sym_details/NSE_FO.csv",
        "logical_exchange": "NFO",
        "group": "derivative",
    },
    "NSE_COM": {
        "url": "https://public.fyers.in/sym_details/NSE_COM.csv",
        "logical_exchange": "NSE",
        "group": "commodity",
    },
    "NSE_CD": {
        "url": "https://public.fyers.in/sym_details/NSE_CD.csv",
        "logical_exchange": "CDS",
        "group": "currency",
    },
    "BSE_FO": {
        "url": "https://public.fyers.in/sym_details/BSE_FO.csv",
        "logical_exchange": "BFO",
        "group": "derivative",
    },
    "MCX_COM": {
        "url": "https://public.fyers.in/sym_details/MCX_COM.csv",
        "logical_exchange": "MCX",
        "group": "commodity",
    },
}

_master_cache = {
    "loaded_at": 0,
    "payload": None,
}
_master_lock = threading.Lock()


def detect_exchange(symbol):
    raw = str(symbol or "").strip().upper()
    if not raw or ":" not in raw:
        return None

    exchange = raw.split(":", 1)[0]
    if exchange in SUPPORTED_EXCHANGES:
        return exchange

    normalized = EXCHANGE_ALIASES.get(exchange, exchange)
    if normalized not in EXCHANGE_ALIASES.values():
        return None

    if normalized == "NSE":
        # NSE symbols may belong to NSE cash, NFO, or CDS segments.
        return "NSE"
    if normalized == "BSE":
        # BSE symbols may belong to BSE cash or BFO segments.
        return "BSE"
    return normalized


def normalize_symbol(symbol):
    if not isinstance(symbol, str):
        return ""
    value = symbol.strip().upper()
    if not value or ":" not in value:
        return value

    exchange, instrument = value.split(":", 1)
    exchange = EXCHANGE_ALIASES.get(exchange, exchange)
    return f"{exchange}:{instrument.strip()}"


def validate_symbol(symbol, lookup=None):
    normalized = normalize_symbol(symbol)
    if not normalized:
        return {
            "valid": False,
            "symbol": symbol,
            "normalized_symbol": normalized,
            "exchange": None,
            "reason": "Empty or invalid symbol input",
        }

    if ":" not in normalized:
        return {
            "valid": False,
            "symbol": symbol,
            "normalized_symbol": normalized,
            "exchange": None,
            "reason": "Missing exchange prefix in symbol",
        }

    exchange = normalized.split(":", 1)[0]
    if exchange not in SUPPORTED_EXCHANGES and exchange not in EXCHANGE_ALIASES.values():
        return {
            "valid": False,
            "symbol": symbol,
            "normalized_symbol": normalized,
            "exchange": exchange,
            "reason": "Unsupported exchange prefix",
        }

    master_lookup = lookup if lookup is not None else get_symbol_master_lookup()
    item = master_lookup.get(normalized)
    if not item:
        return {
            "valid": False,
            "symbol": symbol,
            "normalized_symbol": normalized,
            "exchange": exchange,
            "reason": "Symbol not found in loaded FYERS symbol master",
        }

    return {
        "valid": True,
        "symbol": symbol,
        "normalized_symbol": normalized,
        "exchange": item.get("exchange") or exchange,
        "reason": None,
        "meta": item,
    }


def get_symbol_master_payload(force_refresh=False):
    now = time.time()
    cached = _master_cache.get("payload")
    if (
        not force_refresh
        and cached
        and now - _master_cache.get("loaded_at", 0) < SYMBOL_MASTER_CACHE_SECONDS
    ):
        return cached

    with _master_lock:
        now = time.time()
        cached = _master_cache.get("payload")
        if (
            not force_refresh
            and cached
            and now - _master_cache.get("loaded_at", 0) < SYMBOL_MASTER_CACHE_SECONDS
        ):
            return cached

        payload = _build_symbol_master_payload()
        _master_cache["loaded_at"] = now
        _master_cache["payload"] = payload
        return payload


def get_symbol_master_lookup(force_refresh=False):
    payload = get_symbol_master_payload(force_refresh=force_refresh)
    return payload.get("lookup", {})


def get_exchange_master_counts(force_refresh=False):
    payload = get_symbol_master_payload(force_refresh=force_refresh)
    return payload.get("counts", {})


def startup_master_diagnostics(force_refresh=False):
    payload = get_symbol_master_payload(force_refresh=force_refresh)
    counts = payload.get("counts", {})
    loaded_sources = payload.get("loaded_sources", [])
    missing_sources = payload.get("missing_sources", [])

    for exchange in ("NSE", "BSE", "MCX", "NFO", "CDS", "BFO"):
        logger.info("Loaded %s symbols: %s", exchange, counts.get(exchange, 0))

    if missing_sources:
        for source in missing_sources:
            logger.warning(
                "Symbol master source unavailable: %s (%s) reason=%s",
                source.get("name"),
                source.get("url"),
                source.get("reason"),
            )

    return {
        "counts": counts,
        "loaded_sources": loaded_sources,
        "missing_sources": missing_sources,
        "loaded_at": payload.get("loaded_at"),
    }


def _build_symbol_master_payload():
    lookup = {}
    counts = {exchange: 0 for exchange in SUPPORTED_EXCHANGES}
    loaded_sources = []
    missing_sources = []

    for source_name, source_meta in MASTER_SOURCES.items():
        url = source_meta["url"]
        logical_exchange = source_meta["logical_exchange"]
        group = source_meta["group"]
        try:
            rows = _read_fyers_symbol_master(url)
            loaded_sources.append(source_name)
            for row in rows:
                item = _row_to_lookup_item(row, source_name, logical_exchange, group)
                if not item:
                    continue

                symbol = item["symbol"]
                existing = lookup.get(symbol)
                if not existing:
                    lookup[symbol] = item
                    counts[item["exchange"]] = counts.get(item["exchange"], 0) + 1
                else:
                    # Prefer entries with expiry (derivatives) when duplicate symbol keys appear.
                    if existing.get("expiry_ts") in (None, 0) and item.get("expiry_ts") not in (None, 0):
                        lookup[symbol] = item
        except Exception as exc:
            logger.warning("Unable to load FYERS symbol master %s (%s): %s", source_name, url, exc)
            missing_sources.append({
                "name": source_name,
                "url": url,
                "reason": str(exc),
            })

    payload = {
        "loaded_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "lookup": lookup,
        "counts": counts,
        "loaded_sources": loaded_sources,
        "missing_sources": missing_sources,
    }
    logger.info(
        "Unified symbol master loaded: total_symbols=%s loaded_sources=%s missing_sources=%s",
        len(lookup),
        len(loaded_sources),
        len(missing_sources),
    )
    return payload


def _read_fyers_symbol_master(url):
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=30) as response:
        content = response.read().decode("utf-8", errors="replace")
    rows = list(csv.reader(StringIO(content)))
    logger.info("Loaded %s rows from %s", len(rows), url)
    return rows


def _row_to_lookup_item(row, source_name, logical_exchange, group):
    if len(row) < 10:
        return None

    symbol = (row[9] or "").strip().upper()
    if not symbol or ":" not in symbol:
        return None

    exchange, _ = symbol.split(":", 1)
    if exchange == "NSE" and logical_exchange in {"NFO", "CDS"}:
        mapped_exchange = logical_exchange
    elif exchange == "BSE" and logical_exchange == "BFO":
        mapped_exchange = "BFO"
    else:
        mapped_exchange = exchange

    name = (row[1] if len(row) > 1 else "") or ""
    root_symbol = (row[13] if len(row) > 13 else "") or symbol.split(":", 1)[1]
    instrument_code = (row[2] if len(row) > 2 else "") or ""
    lot_size = _parse_int(row[3] if len(row) > 3 else None)
    expiry_ts = _parse_int(row[8] if len(row) > 8 else None)
    isin = (row[5] if len(row) > 5 else "") or ""
    underlying = (row[17] if len(row) > 17 else "") or ""

    return {
        "symbol": symbol,
        "exchange": mapped_exchange,
        "actual_exchange": exchange,
        "logical_exchange": logical_exchange,
        "source": source_name,
        "group": group,
        "name": str(name).strip(),
        "root_symbol": str(root_symbol).strip().upper(),
        "instrument": _infer_instrument(symbol, source_name, instrument_code),
        "instrument_code": str(instrument_code).strip(),
        "lot_size": lot_size,
        "expiry_ts": expiry_ts,
        "isin": str(isin).strip(),
        "underlying_fytoken": str(underlying).strip(),
    }


def _infer_instrument(symbol, source_name, instrument_code):
    symbol = (symbol or "").upper()
    source_name = (source_name or "").upper()
    code = str(instrument_code or "").strip()

    if symbol.endswith("FUT"):
        if source_name in {"MCX_COM", "NSE_COM"}:
            return "FUTCOM"
        if source_name == "NSE_CD":
            return "FUTCUR"
        return "FUT"
    if symbol.endswith("CE") or symbol.endswith("PE"):
        if source_name in {"MCX_COM", "NSE_COM"}:
            return "OPTCOM"
        if source_name == "NSE_CD":
            return "OPTCUR"
        return "OPT"
    if symbol.endswith("-INDEX"):
        return "INDEX"
    if source_name.endswith("CM"):
        return "EQ"
    if code == "16":
        return "CUR"
    return "UNKNOWN"


def _parse_int(value):
    try:
        if value in (None, ""):
            return None
        return int(float(value))
    except (TypeError, ValueError):
        return None
