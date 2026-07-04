import re
import time

from services.symbol_validator import (
    EXCHANGE_ALIASES,
    SUPPORTED_EXCHANGES,
    get_symbol_master_lookup,
    normalize_symbol,
    validate_symbol,
)


def resolve_symbol(exchange, instrument):
    return _resolve(exchange, instrument, kind_hint=None)


def resolve_spot_symbol(exchange, instrument):
    return _resolve(exchange, instrument, kind_hint="spot")


def resolve_future_symbol(exchange, instrument):
    return _resolve(exchange, instrument, kind_hint="future")


def resolve_option_symbol(exchange, instrument):
    return _resolve(exchange, instrument, kind_hint="option")


def _resolve(exchange, instrument, kind_hint=None):
    requested_exchange = _normalize_exchange(exchange)
    raw_instrument = str(instrument or "").strip().upper()
    lookup = get_symbol_master_lookup()

    if not raw_instrument:
        return {
            "success": False,
            "symbol": instrument,
            "exchange": requested_exchange,
            "reason": "Instrument cannot be empty",
        }

    inferred_kind = kind_hint or _infer_kind(raw_instrument)
    exchange_from_symbol = None
    token = raw_instrument

    if ":" in raw_instrument:
        exchange_from_symbol, token = raw_instrument.split(":", 1)
        exchange_from_symbol = _normalize_exchange(exchange_from_symbol)
        requested_exchange = requested_exchange or exchange_from_symbol

        normalized = normalize_symbol(raw_instrument)
        direct = validate_symbol(normalized, lookup=lookup)
        if direct.get("valid"):
            meta = direct.get("meta") or {}
            return {
                "success": True,
                "symbol": direct.get("normalized_symbol"),
                "exchange": meta.get("exchange") or requested_exchange,
                "meta": meta,
                "reason": None,
            }

    if requested_exchange and requested_exchange not in SUPPORTED_EXCHANGES and requested_exchange not in EXCHANGE_ALIASES.values():
        return {
            "success": False,
            "symbol": raw_instrument,
            "exchange": requested_exchange,
            "reason": "Unsupported exchange prefix",
        }

    candidates = _find_candidates(
        lookup_values=list(lookup.values()),
        requested_exchange=requested_exchange,
        token=token,
        kind_hint=inferred_kind,
    )
    if not candidates:
        return {
            "success": False,
            "symbol": raw_instrument,
            "exchange": requested_exchange or exchange_from_symbol,
            "reason": "Exchange supported but contract unavailable",
        }

    best = candidates[0]
    return {
        "success": True,
        "symbol": best.get("symbol"),
        "exchange": best.get("exchange") or requested_exchange,
        "meta": best,
        "reason": None,
    }


def _find_candidates(lookup_values, requested_exchange, token, kind_hint):
    token = (token or "").strip().upper()
    root = _extract_root(token)
    token_without_exchange = token.split(":", 1)[1] if ":" in token else token
    exchange_pool = _exchange_pool(requested_exchange, kind_hint)

    filtered = []
    for item in lookup_values:
        if not item:
            continue
        if exchange_pool and item.get("exchange") not in exchange_pool:
            continue
        if not _kind_matches(item, kind_hint):
            continue

        symbol = str(item.get("symbol") or "").upper()
        item_token = symbol.split(":", 1)[1] if ":" in symbol else symbol
        item_root = _extract_root(item.get("root_symbol") or item_token)

        if token_without_exchange == item_token:
            filtered.append(item)
            continue
        if root and (item_root == root or token_without_exchange.startswith(item_root) or item_root.startswith(root)):
            filtered.append(item)

    return sorted(filtered, key=lambda item: _rank_candidate(item, token_without_exchange, root, kind_hint))


def _rank_candidate(item, token_without_exchange, root, kind_hint):
    symbol = str(item.get("symbol") or "").upper()
    item_token = symbol.split(":", 1)[1] if ":" in symbol else symbol
    item_root = _extract_root(item.get("root_symbol") or item_token)
    score = 0

    if item_token == token_without_exchange:
        score += 100
    if item_root == root:
        score += 50
    if token_without_exchange.startswith(item_root):
        score += 20

    instrument = (item.get("instrument") or "").upper()
    if kind_hint == "spot" and instrument in {"EQ", "INDEX"}:
        score += 15
    elif kind_hint == "future" and instrument in {"FUT", "FUTCOM", "FUTCUR"}:
        score += 15
    elif kind_hint == "option" and instrument in {"OPT", "OPTCOM", "OPTCUR"}:
        score += 15

    if symbol.endswith("-EQ"):
        score += 2
    if symbol.endswith("-A"):
        score += 1

    expiry_ts = item.get("expiry_ts") or 0
    now_ts = int(time.time())
    if kind_hint in {"future", "option"}:
        if expiry_ts and expiry_ts >= now_ts:
            expiry_bucket = expiry_ts
        elif expiry_ts:
            expiry_bucket = expiry_ts + 10**11
        else:
            expiry_bucket = 10**12
    else:
        expiry_bucket = 0

    return (-score, expiry_bucket, symbol)


def _kind_matches(item, kind_hint):
    if not kind_hint:
        return True
    instrument = (item.get("instrument") or "").upper()
    if kind_hint == "spot":
        return instrument in {"EQ", "INDEX"}
    if kind_hint == "future":
        return instrument in {"FUT", "FUTCOM", "FUTCUR"}
    if kind_hint == "option":
        return instrument in {"OPT", "OPTCOM", "OPTCUR"}
    return True


def _exchange_pool(requested_exchange, kind_hint):
    if not requested_exchange:
        return set()

    requested_exchange = _normalize_exchange(requested_exchange)
    if requested_exchange in {"NFO", "CDS", "BFO", "MCX"}:
        return {requested_exchange}

    if requested_exchange == "NSE":
        if kind_hint == "future" or kind_hint == "option":
            return {"NFO"}
        if kind_hint == "spot":
            return {"NSE"}
        return {"NSE", "NFO", "CDS"}

    if requested_exchange == "BSE":
        if kind_hint == "future" or kind_hint == "option":
            return {"BFO"}
        if kind_hint == "spot":
            return {"BSE"}
        return {"BSE", "BFO"}

    return {requested_exchange}


def _normalize_exchange(exchange):
    value = str(exchange or "").strip().upper()
    if not value:
        return None
    return EXCHANGE_ALIASES.get(value, value)


def _infer_kind(token):
    token = str(token or "").upper().strip()
    if token.endswith("FUT"):
        return "future"
    if token.endswith("CE") or token.endswith("PE"):
        return "option"
    if token.endswith("-EQ") or token.endswith("-A") or token.endswith("-BE") or token.endswith("-INDEX"):
        return "spot"
    return None


def _extract_root(token):
    value = str(token or "").upper().strip()
    if ":" in value:
        value = value.split(":", 1)[1]

    for suffix in ("-EQ", "-BE", "-A", "-B", "-T", "-INDEX"):
        if value.endswith(suffix):
            return value[: -len(suffix)]

    match = re.match(r"([A-Z0-9&-]+)", value)
    return match.group(1) if match else value