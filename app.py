import logging
import os
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from flask import Flask, jsonify, redirect, render_template, request, session, url_for

from services.fyers_credentials import (
    clear_fyers_config,
    describe_fyers_config,
    get_fyers_config,
    save_fyers_config,
)
from services.symbol_search import search_symbols
from services.symbol_resolver import resolve_symbol
from services.symbol_mapper import (
    FYERS_NSE_CM_SYMBOL_MASTER_URL,
    FYERS_NSE_FO_SYMBOL_MASTER_URL,
    build_commodity_futures_catalog,
    build_fno_contract_catalog,
    clean_root_symbol,
)
from services.symbol_validator import detect_exchange, get_symbol_master_lookup, startup_master_diagnostics, validate_symbol
from utils.batching import batch_values, unique_preserve_order

try:
    from fyers_apiv3 import fyersModel
except ImportError:  # Keeps the dashboard bootable before dependencies are installed.
    fyersModel = None

# Change this line in app.py (near line 16)
basedir = os.path.abspath(os.path.dirname(__file__))
# This tells Python to look in the exact same folder as app.py
load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))


app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "prajwalp776")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

IST = ZoneInfo("Asia/Kolkata")
QUOTE_CHUNK_SIZE = 50
QUOTE_CHUNK_PAUSE_SECONDS = 1.2
ARBITRAGE_AUTO_REFRESH_SECONDS = 30
EQUITY_CASH_FUTURES_RATES = {
    "equitySttBuyPct": 0.1,
    "equitySttSellPct": 0.1,
    "futuresSttSellPct": 0.05,
    "equityStampBuyPct": 0.015,
    "futuresStampBuyPct": 0.002,
    "equityExchangePct": 0.00307,
    "futuresExchangePct": 0.00183,
    "sebiTurnoverPct": 0.0001,
    "gstPct": 18,
    "futuresBrokeragePct": 0.03,
    "futuresBrokerageCapPerOrder": 20,
    "futuresMarginPct": 20,
}
COMMODITY_FUTURES_RATES = {
    "futuresCttSellPct": 0.01,
    "futuresStampBuyPct": 0.002,
    "mcxExchangePct": 0.0021,
    "nseCommodityExchangePct": 0.0001,
    "sebiAgriTurnoverPct": 0.00001,
    "sebiNonAgriTurnoverPct": 0.0001,
    "gstPct": 18,
    "futuresBrokeragePct": 0.03,
    "futuresBrokerageCapPerOrder": 20,
    "futuresMarginPct": 20,
}

try:
    if os.getenv("FYERS_STARTUP_DIAGNOSTICS", "0").lower() in {"1", "true", "yes"}:
        startup_master_diagnostics()
except Exception as exc:
    logger.warning("Startup symbol-master diagnostics failed: %s", exc)

def fyers_config():
    return get_fyers_config()


def config_errors(include_credentials=False):
    cfg = fyers_config()
    missing = [key for key in ("client_id", "secret_key", "redirect_uri") if not cfg.get(key)]
    errors = []
    if fyersModel is None:
        errors.append("fyers-apiv3 not installed")
    if include_credentials and missing:
        errors.append("FYERS credentials are not configured. Add the Client ID, Secret Key, and Redirect URI in the FYERS Credentials panel.")
    return errors


def fyers_render_context():
    config = describe_fyers_config()
    return {
        "fyers_client_id": config.get("client_id") or "",
        "fyers_redirect_uri": config.get("redirect_uri") or "",
        "fyers_configured": bool(config.get("configured")),
        "fyers_config_source": config.get("source") or "missing",
    }



def make_session_model():
    cfg = fyers_config()
    if not cfg.get("configured"):
        raise RuntimeError("FYERS credentials are not configured. Add the Client ID, Secret Key, and Redirect URI in the FYERS Credentials panel.")
    return fyersModel.SessionModel(
        client_id=cfg["client_id"],
        secret_key=cfg["secret_key"],
        redirect_uri=cfg["redirect_uri"],
        response_type="code",
        grant_type="authorization_code",
    )


def make_fyers_client(token=None):
    token = token or session.get("access_token")
    if not token:
        raise RuntimeError("Not authenticated with FYERS.")
    cfg = fyers_config()
    if not cfg.get("configured"):
        raise RuntimeError("FYERS credentials are not configured. Add the Client ID, Secret Key, and Redirect URI in the FYERS Credentials panel.")
    return fyersModel.FyersModel(
        client_id=cfg["client_id"],
        token=token,
        is_async=False,
        log_path=os.path.join(os.getcwd(), "logs"),
    )


@app.route("/")
def index():
    errors = config_errors()
    return render_template(
        "nse_fno_analytics.html",
        authenticated=bool(session.get("access_token")),
        config_errors=errors,
        **fyers_render_context(),
    )


@app.route("/healthz")
def healthz():
    return jsonify({"ok": True})


@app.route("/nse-fno-analytics")
def nse_fno_analytics():
    return redirect(url_for("index"))


@app.route("/arbitrage-calculator")
def arbitrage_calculator():
    errors = config_errors()
    return render_template(
        "arbitrage_calculator.html",
        authenticated=bool(session.get("access_token")),
        config_errors=errors,
        **fyers_render_context(),
    )


@app.route("/login")
def login():
    errors = config_errors(include_credentials=True)
    if errors:
        return render_template(
            "nse_fno_analytics.html",
            authenticated=False,
            config_errors=errors,
            **fyers_render_context(),
        ), 400

    auth_url = make_session_model().generate_authcode()
    return redirect(auth_url)


@app.route("/callback")
def callback():
    auth_code = request.args.get("auth_code") or request.args.get("code")
    if not auth_code:
        return render_template(
            "nse_fno_analytics.html",
            authenticated=False,
            config_errors=["FYERS did not return an auth_code."],
            **fyers_render_context(),
        ), 400

    try:
        session_model = make_session_model()
        session_model.set_token(auth_code)
        response = session_model.generate_token()
    except Exception as exc:
        return render_template(
            "nse_fno_analytics.html",
            authenticated=False,
            config_errors=[str(exc)],
            **fyers_render_context(),
        ), 400

    access_token = response.get("access_token") if isinstance(response, dict) else None
    if not access_token:
        message = response.get("message", "Unable to generate FYERS access token.") if isinstance(response, dict) else str(response)
        return render_template(
            "nse_fno_analytics.html",
            authenticated=False,
            config_errors=[message],
            **fyers_render_context(),
        ), 400

    session["access_token"] = access_token
    session["token_created_at"] = datetime.utcnow().isoformat()
    return redirect(url_for("index"))


@app.route("/logout", methods=["POST"])
def logout():
    session.pop("access_token", None)
    session.pop("token_created_at", None)
    return jsonify({"ok": True})


@app.route("/api/fyers-config", methods=["GET", "POST", "DELETE"])
def fyers_config_api():
    if request.method == "GET":
        return jsonify(describe_fyers_config())

    if request.method == "DELETE":
        clear_fyers_config()
        session.pop("access_token", None)
        session.pop("token_created_at", None)
        return jsonify(describe_fyers_config())

    payload = request.get_json(silent=True) or {}
    try:
        config = save_fyers_config(
            client_id=payload.get("client_id"),
            secret_key=payload.get("secret_key"),
            redirect_uri=payload.get("redirect_uri"),
        )
        session.pop("access_token", None)
        session.pop("token_created_at", None)
        return jsonify(config)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


@app.route("/api/symbol-search")
def symbol_search():
    query = (request.args.get("q") or "").strip()
    if len(query) < 1:
        return jsonify([])

    try:
        return jsonify(search_symbols(query, limit=15))
    except Exception as exc:
        logger.exception("Symbol search failed for query=%s", query)
        return jsonify({"error": str(exc)}), 500


@app.route("/api/debug/symbol-check", methods=["POST"])
def debug_symbol_check():
    payload = request.get_json(silent=True) or {}
    symbol = (payload.get("symbol") or "").strip().upper()
    if not symbol:
        return jsonify({
            "exists": False,
            "reason": "Missing symbol in request payload",
            "symbol": symbol,
            "exchange": None,
        }), 400

    resolution = resolve_symbol(None, symbol)
    validation = validate_symbol(symbol)
    if validation.get("valid"):
        meta = validation.get("meta") or {}
        return jsonify({
            "exists": True,
            "symbol": validation.get("normalized_symbol"),
            "exchange": meta.get("exchange") or validation.get("exchange"),
            "instrument": meta.get("instrument"),
            "lot_size": meta.get("lot_size"),
            "source": meta.get("source"),
            "resolution": {
                "success": resolution.get("success"),
                "symbol": resolution.get("symbol"),
                "exchange": resolution.get("exchange"),
            },
        })

    return jsonify({
        "exists": False,
        "symbol": symbol,
        "exchange": validation.get("exchange") or detect_exchange(symbol),
        "reason": validation.get("reason") or "Symbol not found in loaded FYERS symbol master",
        "resolution": {
            "success": resolution.get("success"),
            "symbol": resolution.get("symbol"),
            "exchange": resolution.get("exchange"),
            "reason": resolution.get("reason"),
        },
    })


@app.route("/api/nse-fno-analytics")
def nse_fno_analytics_data():
    if not session.get("access_token"):
        return jsonify({"error": "Login with FYERS before loading live F&O analytics."}), 401

    errors = config_errors()
    if errors:
        return jsonify({"error": "; ".join(errors)}), 400

    try:
        catalog = get_fno_contract_catalog()
        rows, warnings = fetch_fno_analytics_rows(catalog["items"])
        generated_at = datetime.now(IST)
        return jsonify({
            "generated_at": generated_at.isoformat(),
            "refresh_interval_seconds": 60,
            "source": {
                "fo_symbol_master": FYERS_NSE_FO_SYMBOL_MASTER_URL,
                "cm_symbol_master": FYERS_NSE_CM_SYMBOL_MASTER_URL,
                "catalog_loaded_at": catalog["loaded_at"],
                "contract_count": catalog["contract_count"],
            },
            "summary": summarize_fno_rows(rows),
            "rows": rows,
            "warnings": warnings,
        })
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/api/arbitrage/metadata")
def arbitrage_metadata():
    try:
        equity_catalog = get_fno_contract_catalog()
        commodity_catalog = get_commodity_futures_catalog()
        return jsonify({
            "generated_at": datetime.now(IST).isoformat(),
            "refresh_interval_seconds": ARBITRAGE_AUTO_REFRESH_SECONDS,
            "equitySymbols": build_arbitrage_symbol_metadata(equity_catalog["items"], "equity"),
            "commoditySymbols": build_arbitrage_symbol_metadata(commodity_catalog["items"], "commodity"),
            "chargeRules": {
                "equity": equity_charge_rules(),
                "commodity": commodity_charge_rules(),
            },
        })
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/api/arbitrage/calculate", methods=["POST"])
def arbitrage_calculate():
    if not session.get("access_token"):
        return jsonify({"error": "Login with FYERS before calculating live arbitrage."}), 401

    errors = config_errors()
    if errors:
        return jsonify({"error": "; ".join(errors)}), 400

    payload = request.get_json(silent=True) or {}
    try:
        market_type = str(payload.get("marketType") or "equity").strip().lower()
        if market_type == "commodity":
            return jsonify(calculate_commodity_arbitrage(payload, get_commodity_futures_catalog()))
        if market_type == "equity":
            return jsonify(calculate_equity_arbitrage(payload, get_fno_contract_catalog()))
        raise ValueError("Select either equity cash-futures or commodity futures.")
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


def get_fno_contract_catalog():
    return build_fno_contract_catalog()


def build_arbitrage_symbol_metadata(catalog_items, market_type):
    return [
        {
            "symbol": item["symbol"],
            "stockName": item["stock_name"],
            "spotSymbol": item.get("spot_symbol"),
            "exchange": item.get("exchange") or "NSE",
            "marketType": market_type,
            "lotSize": item["lot_size"],
            "contracts": [
                {
                    "key": key,
                    "label": "Stock Future" if market_type == "equity" else "Commodity Future",
                    "futureSymbol": contract["fyers_symbol"],
                    "expiry": contract["expiry"],
                    "expiryTs": contract.get("expiry_ts"),
                    "lotSize": contract.get("lot_size"),
                    "exchange": contract.get("exchange") or item.get("exchange") or "NSE",
                }
                for key, contract in item["contracts"].items()
            ],
        }
        for item in catalog_items
    ]


def calculate_equity_arbitrage(payload, catalog):
    buy_item = find_arbitrage_item(catalog, payload.get("buySymbol"))
    if not buy_item:
        raise ValueError("Select a valid F&O stock to buy.")

    sell_item = find_arbitrage_item(catalog, payload.get("sellSymbol") or payload.get("buySymbol"))
    if not sell_item:
        raise ValueError("Select a valid F&O stock future to sell.")

    contract = find_arbitrage_contract(
        sell_item,
        payload.get("futureContract") or payload.get("futureExpiry"),
    )
    if not contract:
        raise ValueError("Select a valid futures expiry for the sell leg.")

    lots = parse_positive_int(payload.get("lots"), "Lots")
    rates = dict(EQUITY_CASH_FUTURES_RATES)
    quotes, quote_warnings = fetch_fyers_quotes([
        buy_item["spot_symbol"],
        contract["fyers_symbol"],
    ])
    spot_price = extract_quote_price(quotes.get(buy_item["spot_symbol"]))
    future_price = extract_quote_price(quotes.get(contract["fyers_symbol"]))
    if spot_price is None:
        raise ValueError(f"FYERS did not return a live spot price for {buy_item['spot_symbol']}.")
    if future_price is None:
        raise ValueError(f"FYERS did not return a live futures price for {contract['fyers_symbol']}.")

    settlement_price = parse_float(payload.get("settlementPrice"))
    if settlement_price is None or settlement_price <= 0:
        settlement_price = spot_price

    warnings = list(quote_warnings or [])
    if buy_item["symbol"] != sell_item["symbol"]:
        warnings.append("Buy stock and sell future are different underlyings; hedge and return estimates may not behave like cash-futures arbitrage.")

    lot_size = int(contract.get("lot_size") or sell_item.get("lot_size") or 0)
    if lot_size <= 0:
        raise ValueError("Could not read lot size for the selected futures contract.")

    quantity = lot_size * lots
    turnover = build_arbitrage_turnover(spot_price, future_price, settlement_price, quantity)
    charges = calculate_equity_cash_futures_charges(turnover, rates)
    gross_profit = round_money(turnover["stockSell"] - turnover["stockBuy"] + turnover["futureSell"] - turnover["futureBuy"])
    net_profit = round_money(gross_profit - charges["total"])
    future_margin = pct_amount(turnover["futureSell"], rates["futuresMarginPct"])
    cash_required = round_money(turnover["stockBuy"] + future_margin + charges["opening"])
    gross_return_pct = percentage_of(gross_profit, cash_required)
    net_return_pct = percentage_of(net_profit, cash_required)
    days_to_expiry = days_until_expiry(contract.get("expiry_ts"))

    return {
        "marketType": "equity",
        "generated_at": datetime.now(IST).isoformat(),
        "warnings": warnings,
        "rates": rates,
        "chargeRules": equity_charge_rules(),
        "inputs": {
            "buySymbol": buy_item["symbol"],
            "sellSymbol": sell_item["symbol"],
            "lots": lots,
            "settlementPrice": settlement_price,
        },
        "instruments": {
            "buyStock": {
                "symbol": buy_item["symbol"],
                "stockName": buy_item["stock_name"],
                "spotSymbol": buy_item["spot_symbol"],
            },
            "sellFuture": {
                "symbol": sell_item["symbol"],
                "stockName": sell_item["stock_name"],
                "futureSymbol": contract["fyers_symbol"],
                "expiry": contract["expiry"],
                "expiryTs": contract.get("expiry_ts"),
            },
        },
        "prices": {
            "spotPrice": spot_price,
            "futurePrice": future_price,
            "settlementPrice": settlement_price,
            "grossSpreadPerShare": round_money(future_price - spot_price),
            "grossSpreadPct": percentage_difference(future_price, spot_price),
            "breakEvenSpreadPerShare": round_money(charges["total"] / quantity),
        },
        "quantity": {
            "lotSize": lot_size,
            "lots": lots,
            "shares": quantity,
            "daysToExpiry": days_to_expiry,
        },
        "turnover": turnover,
        "charges": charges,
        "result": {
            "grossProfit": gross_profit,
            "netProfit": net_profit,
            "cashRequired": cash_required,
            "futureMargin": future_margin,
            "grossReturnPct": gross_return_pct,
            "netReturnPct": net_return_pct,
            "annualizedNetReturnPct": annualized_return(net_return_pct, days_to_expiry),
        },
    }


def calculate_commodity_arbitrage(payload, catalog):
    buy_item = find_arbitrage_item(catalog, payload.get("buySymbol"))
    sell_item = find_arbitrage_item(catalog, payload.get("sellSymbol") or payload.get("buySymbol"))
    if not buy_item or not sell_item:
        raise ValueError("Select valid commodity futures for both the buy and sell legs.")

    # A commodity calendar spread needs the same underlying and exchange. It
    # prevents a misleading difference between unrelated units such as crude oil
    # and gold, or MCX and NSE contracts.
    if buy_item["symbol"] != sell_item["symbol"]:
        raise ValueError("Select buy and sell futures for the same commodity and exchange.")

    buy_contract = find_arbitrage_contract(buy_item, payload.get("buyFutureContract"))
    sell_contract = find_arbitrage_contract(sell_item, payload.get("sellFutureContract"))
    if not buy_contract or not sell_contract:
        raise ValueError("Select valid commodity-futures expiries for both legs.")
    if buy_contract["fyers_symbol"] == sell_contract["fyers_symbol"]:
        raise ValueError("Select two different commodity-futures expiries to calculate a spread.")

    buy_lot_size = int(buy_contract.get("lot_size") or 0)
    sell_lot_size = int(sell_contract.get("lot_size") or 0)
    if buy_lot_size <= 0 or sell_lot_size <= 0:
        raise ValueError("Could not read the lot size for the selected commodity futures.")
    if buy_lot_size != sell_lot_size:
        raise ValueError("The selected commodity futures have different lot sizes and cannot be compared as one spread.")

    lots = parse_positive_int(payload.get("lots"), "Lots")
    commodity_class = str(payload.get("commodityClass") or "non_agri").strip().lower()
    if commodity_class not in {"agri", "non_agri"}:
        raise ValueError("Select whether the commodity is agricultural or non-agricultural.")

    quotes, quote_warnings = fetch_fyers_quotes([
        buy_contract["fyers_symbol"],
        sell_contract["fyers_symbol"],
    ])
    buy_future_price = extract_quote_price(quotes.get(buy_contract["fyers_symbol"]))
    sell_future_price = extract_quote_price(quotes.get(sell_contract["fyers_symbol"]))
    if buy_future_price is None:
        raise ValueError(f"FYERS did not return a live price for {buy_contract['fyers_symbol']}.")
    if sell_future_price is None:
        raise ValueError(f"FYERS did not return a live price for {sell_contract['fyers_symbol']}.")

    quantity = buy_lot_size * lots
    turnover = {
        "futureBuy": round_money(buy_future_price * quantity),
        "futureSell": round_money(sell_future_price * quantity),
        "total": round_money((buy_future_price + sell_future_price) * quantity),
    }
    rates = commodity_futures_rates(buy_item["exchange"], commodity_class)
    charges = calculate_commodity_futures_charges(turnover, rates)
    gross_difference = round_money(turnover["futureSell"] - turnover["futureBuy"])
    net_difference = round_money(gross_difference - charges["total"])
    future_margin = pct_amount(turnover["total"], rates["futuresMarginPct"])
    cash_required = round_money(future_margin + charges["opening"])
    expiry_days = [
        value for value in (
            days_until_expiry(buy_contract.get("expiry_ts")),
            days_until_expiry(sell_contract.get("expiry_ts")),
        ) if value is not None
    ]
    days_to_expiry = min(expiry_days) if expiry_days else None

    return {
        "marketType": "commodity",
        "generated_at": datetime.now(IST).isoformat(),
        "warnings": list(quote_warnings or []) + [
            "The displayed net difference is the current calendar-spread value after entry charges; it is not a guaranteed settlement profit.",
            "Margin is indicative. Actual commodity spread margin is determined by FYERS and the exchange.",
        ],
        "rates": rates,
        "chargeRules": commodity_charge_rules(),
        "inputs": {
            "buySymbol": buy_item["symbol"],
            "sellSymbol": sell_item["symbol"],
            "lots": lots,
            "commodityClass": commodity_class,
        },
        "instruments": {
            "buyFuture": {
                "symbol": buy_item["root_symbol"],
                "stockName": buy_item["stock_name"],
                "futureSymbol": buy_contract["fyers_symbol"],
                "expiry": buy_contract["expiry"],
                "expiryTs": buy_contract.get("expiry_ts"),
                "exchange": buy_item["exchange"],
            },
            "sellFuture": {
                "symbol": sell_item["root_symbol"],
                "stockName": sell_item["stock_name"],
                "futureSymbol": sell_contract["fyers_symbol"],
                "expiry": sell_contract["expiry"],
                "expiryTs": sell_contract.get("expiry_ts"),
                "exchange": sell_item["exchange"],
            },
        },
        "prices": {
            "buyFuturePrice": buy_future_price,
            "sellFuturePrice": sell_future_price,
            "grossSpreadPerShare": round_money(sell_future_price - buy_future_price),
            "grossSpreadPct": percentage_difference(sell_future_price, buy_future_price),
            "breakEvenSpreadPerShare": round_money(charges["total"] / quantity),
        },
        "quantity": {
            "lotSize": buy_lot_size,
            "lots": lots,
            "shares": quantity,
            "daysToExpiry": days_to_expiry,
        },
        "turnover": turnover,
        "charges": charges,
        "result": {
            "grossProfit": gross_difference,
            "netProfit": net_difference,
            "cashRequired": cash_required,
            "futureMargin": future_margin,
            "grossReturnPct": percentage_of(gross_difference, cash_required),
            "netReturnPct": percentage_of(net_difference, cash_required),
            "annualizedNetReturnPct": None,
        },
    }


def find_arbitrage_item(catalog, value):
    cleaned = clean_root_symbol(value)
    value_text = str(value or "").strip().upper()
    if not cleaned and not value_text:
        return None

    for item in catalog.get("items", []):
        symbol = item["symbol"].upper()
        stock_name = item["stock_name"].upper()
        root_symbol = str(item.get("root_symbol") or "").upper()
        spot_symbol = str(item.get("spot_symbol") or "").upper()
        if cleaned in {symbol, root_symbol} or value_text in {symbol, spot_symbol, stock_name, root_symbol}:
            return item
        if value_text and value_text in stock_name:
            return item
        for contract in item["contracts"].values():
            if value_text == contract["fyers_symbol"].upper():
                return item
    return None


def find_arbitrage_contract(item, value):
    contracts = item.get("contracts") or {}
    requested = str(value or "").strip()
    if not requested:
        return contracts.get("near")
    if requested in contracts:
        return contracts[requested]

    requested_upper = requested.upper()
    for contract in contracts.values():
        aliases = {
            contract["fyers_symbol"].upper(),
            str(contract.get("expiry") or "").upper(),
            str(contract.get("expiry_ts") or "").upper(),
        }
        if requested_upper in aliases:
            return contract
    return None


def build_arbitrage_turnover(spot_price, future_price, settlement_price, quantity):
    stock_buy = round_money(spot_price * quantity)
    future_sell = round_money(future_price * quantity)
    stock_sell = round_money(settlement_price * quantity)
    future_buy = round_money(settlement_price * quantity)
    return {
        "stockBuy": stock_buy,
        "futureSell": future_sell,
        "stockSell": stock_sell,
        "futureBuy": future_buy,
        "total": round_money(stock_buy + future_sell + stock_sell + future_buy),
    }


def calculate_equity_cash_futures_charges(turnover, rates):
    equity_buy_brokerage = 0
    equity_sell_brokerage = 0
    future_sell_brokerage = capped_brokerage(turnover["futureSell"], rates)
    future_buy_brokerage = capped_brokerage(turnover["futureBuy"], rates)

    equity_buy_stt = pct_amount(turnover["stockBuy"], rates["equitySttBuyPct"])
    equity_sell_stt = pct_amount(turnover["stockSell"], rates["equitySttSellPct"])
    future_sell_stt = pct_amount(turnover["futureSell"], rates["futuresSttSellPct"])

    equity_buy_stamp = pct_amount(turnover["stockBuy"], rates["equityStampBuyPct"])
    future_buy_stamp = pct_amount(turnover["futureBuy"], rates["futuresStampBuyPct"])

    equity_buy_exchange = pct_amount(turnover["stockBuy"], rates["equityExchangePct"])
    equity_sell_exchange = pct_amount(turnover["stockSell"], rates["equityExchangePct"])
    future_sell_exchange = pct_amount(turnover["futureSell"], rates["futuresExchangePct"])
    future_buy_exchange = pct_amount(turnover["futureBuy"], rates["futuresExchangePct"])

    equity_buy_sebi = pct_amount(turnover["stockBuy"], rates["sebiTurnoverPct"])
    equity_sell_sebi = pct_amount(turnover["stockSell"], rates["sebiTurnoverPct"])
    future_sell_sebi = pct_amount(turnover["futureSell"], rates["sebiTurnoverPct"])
    future_buy_sebi = pct_amount(turnover["futureBuy"], rates["sebiTurnoverPct"])

    opening_gst_base = round_money(
        equity_buy_brokerage
        + future_sell_brokerage
        + equity_buy_exchange
        + future_sell_exchange
        + equity_buy_sebi
        + future_sell_sebi
    )
    closing_gst_base = round_money(
        equity_sell_brokerage
        + future_buy_brokerage
        + equity_sell_exchange
        + future_buy_exchange
        + equity_sell_sebi
        + future_buy_sebi
    )
    opening_gst = pct_amount(opening_gst_base, rates["gstPct"])
    closing_gst = pct_amount(closing_gst_base, rates["gstPct"])

    opening = round_money(
        equity_buy_brokerage
        + future_sell_brokerage
        + equity_buy_stt
        + future_sell_stt
        + equity_buy_stamp
        + equity_buy_exchange
        + future_sell_exchange
        + equity_buy_sebi
        + future_sell_sebi
        + opening_gst
    )
    closing = round_money(
        equity_sell_brokerage
        + future_buy_brokerage
        + equity_sell_stt
        + future_buy_stamp
        + equity_sell_exchange
        + future_buy_exchange
        + equity_sell_sebi
        + future_buy_sebi
        + closing_gst
    )

    brokerage = round_money(equity_buy_brokerage + equity_sell_brokerage + future_sell_brokerage + future_buy_brokerage)
    stt = round_money(equity_buy_stt + equity_sell_stt + future_sell_stt)
    stamp = round_money(equity_buy_stamp + future_buy_stamp)
    exchange = round_money(equity_buy_exchange + equity_sell_exchange + future_sell_exchange + future_buy_exchange)
    sebi = round_money(equity_buy_sebi + equity_sell_sebi + future_sell_sebi + future_buy_sebi)
    gst = round_money(opening_gst + closing_gst)

    return {
        "opening": opening,
        "closing": closing,
        "total": round_money(opening + closing),
        "breakdown": [
            {"label": "Brokerage", "amount": brokerage},
            {"label": "STT", "amount": stt},
            {"label": "Stamp Duty", "amount": stamp},
            {"label": "Exchange Transaction Charges", "amount": exchange},
            {"label": "SEBI Turnover Fees", "amount": sebi},
            {"label": "GST", "amount": gst},
        ],
        "legs": [
            {"label": "Buy Stock Charges", "amount": round_money(equity_buy_brokerage + equity_buy_stt + equity_buy_stamp + equity_buy_exchange + equity_buy_sebi)},
            {"label": "Sell Future Charges", "amount": round_money(future_sell_brokerage + future_sell_stt + future_sell_exchange + future_sell_sebi)},
            {"label": "Sell Stock Charges", "amount": round_money(equity_sell_brokerage + equity_sell_stt + equity_sell_exchange + equity_sell_sebi)},
            {"label": "Buy/Settle Future Charges", "amount": round_money(future_buy_brokerage + future_buy_stamp + future_buy_exchange + future_buy_sebi)},
            {"label": "GST on Charges", "amount": gst},
        ],
    }


def capped_brokerage(turnover, rates):
    return round_money(min(
        pct_amount(turnover, rates["futuresBrokeragePct"]),
        rates["futuresBrokerageCapPerOrder"],
    ))


def commodity_futures_rates(exchange, commodity_class):
    rates = dict(COMMODITY_FUTURES_RATES)
    rates["exchange"] = exchange
    rates["commodityClass"] = commodity_class
    rates["futuresExchangePct"] = (
        rates["mcxExchangePct"] if exchange == "MCX" else rates["nseCommodityExchangePct"]
    )
    rates["sebiTurnoverPct"] = (
        rates["sebiAgriTurnoverPct"] if commodity_class == "agri" else rates["sebiNonAgriTurnoverPct"]
    )
    return rates


def calculate_commodity_futures_charges(turnover, rates):
    future_buy_brokerage = capped_brokerage(turnover["futureBuy"], rates)
    future_sell_brokerage = capped_brokerage(turnover["futureSell"], rates)
    future_sell_ctt = (
        pct_amount(turnover["futureSell"], rates["futuresCttSellPct"])
        if rates["commodityClass"] == "non_agri" else 0
    )
    future_buy_stamp = pct_amount(turnover["futureBuy"], rates["futuresStampBuyPct"])
    future_buy_exchange = pct_amount(turnover["futureBuy"], rates["futuresExchangePct"])
    future_sell_exchange = pct_amount(turnover["futureSell"], rates["futuresExchangePct"])
    future_buy_sebi = pct_amount(turnover["futureBuy"], rates["sebiTurnoverPct"])
    future_sell_sebi = pct_amount(turnover["futureSell"], rates["sebiTurnoverPct"])
    gst_base = round_money(
        future_buy_brokerage
        + future_sell_brokerage
        + future_buy_exchange
        + future_sell_exchange
        + future_buy_sebi
        + future_sell_sebi
    )
    gst = pct_amount(gst_base, rates["gstPct"])
    opening = round_money(
        future_buy_brokerage
        + future_sell_brokerage
        + future_sell_ctt
        + future_buy_stamp
        + future_buy_exchange
        + future_sell_exchange
        + future_buy_sebi
        + future_sell_sebi
        + gst
    )
    brokerage = round_money(future_buy_brokerage + future_sell_brokerage)
    exchange = round_money(future_buy_exchange + future_sell_exchange)
    sebi = round_money(future_buy_sebi + future_sell_sebi)

    return {
        "opening": opening,
        "closing": 0,
        "total": opening,
        "breakdown": [
            {"label": "Brokerage", "amount": brokerage},
            {"label": "CTT (sell side)", "amount": future_sell_ctt},
            {"label": "Stamp Duty (buy side)", "amount": future_buy_stamp},
            {"label": f"{rates['exchange']} Transaction Charges", "amount": exchange},
            {"label": "SEBI Turnover Fees", "amount": sebi},
            {"label": "GST", "amount": gst},
        ],
        "legs": [
            {"label": "Buy Commodity Future Charges", "amount": round_money(future_buy_brokerage + future_buy_stamp + future_buy_exchange + future_buy_sebi)},
            {"label": "Sell Commodity Future Charges", "amount": round_money(future_sell_brokerage + future_sell_ctt + future_sell_exchange + future_sell_sebi)},
            {"label": "GST on Charges", "amount": gst},
        ],
    }


def equity_charge_rules():
    return [
        "Cash equity delivery: zero brokerage; STT 0.10% on buy and sell; NSE transaction charge 0.00307%; stamp duty 0.015% on buy.",
        "NSE stock futures: brokerage 0.03% or Rs. 20 per executed order, whichever is lower; STT 0.05% on sell; transaction charge 0.00183%; stamp duty 0.002% on buy.",
        "SEBI turnover fee is Rs. 10 per crore and GST is 18% of brokerage, exchange transaction charges and SEBI fees.",
    ]


def commodity_charge_rules():
    return [
        "Commodity futures: brokerage 0.03% or Rs. 20 per executed order, whichever is lower; CTT 0.01% on the sell side for non-agri commodities.",
        "Transaction charge: MCX 0.0021% or NSE commodity 0.0001%; stamp duty 0.002% on the buy side.",
        "SEBI turnover fee is Rs. 10 per crore for non-agri or Rs. 1 per crore for agri commodities; GST is 18% of brokerage, exchange transaction charges and SEBI fees.",
    ]


def fetch_fno_analytics_rows(catalog_items):
    requested_symbols = []
    for item in catalog_items:
        requested_symbols.append(item["spot_symbol"])
        requested_symbols.extend(contract["fyers_symbol"] for contract in item["contracts"].values())

    quotes, warnings = fetch_fyers_quotes(requested_symbols)
    rows = []
    for item in catalog_items:
        contracts = item["contracts"]
        spot_price = extract_quote_price(quotes.get(item["spot_symbol"]))
        near_price = extract_quote_price(quotes.get(contracts["near"]["fyers_symbol"]))
        next_price = extract_quote_price(quotes.get(contracts["next"]["fyers_symbol"]))
        far_price = extract_quote_price(quotes.get(contracts["far"]["fyers_symbol"]))

        rows.append({
            "symbol": item["symbol"],
            "stockName": item["stock_name"],
            "spotSymbol": item["spot_symbol"],
            "spotPrice": spot_price,
            "nearFutureSymbol": contracts["near"]["fyers_symbol"],
            "nearFutureExpiry": contracts["near"]["expiry"],
            "nearFuturePrice": near_price,
            "nextFutureSymbol": contracts["next"]["fyers_symbol"],
            "nextFutureExpiry": contracts["next"]["expiry"],
            "nextFuturePrice": next_price,
            "farFutureSymbol": contracts["far"]["fyers_symbol"],
            "farFutureExpiry": contracts["far"]["expiry"],
            "farFuturePrice": far_price,
            "nearDiffPct": percentage_difference(near_price, spot_price),
            "nextDiffPct": percentage_difference(next_price, spot_price),
            "farDiffPct": percentage_difference(far_price, spot_price),
            "lotSize": item["lot_size"],
            "contractValue": contract_value(item["lot_size"], spot_price),
            "quoteStatus": quote_status_for_row(item, contracts, quotes),
        })

    return rows, warnings


def fetch_fyers_quotes(symbols, access_token=None, return_metrics=False, raise_if_empty=True):
    access_token = access_token or session.get("access_token")
    deduped_symbols = unique_preserve_order(symbol for symbol in symbols if symbol)
    lookup = get_symbol_master_lookup()
    valid_symbols = []
    invalid_symbol_details = []
    for symbol in deduped_symbols:
        if not isinstance(symbol, str):
            invalid_symbol_details.append({
                "symbol": str(symbol),
                "exchange": None,
                "reason": "Invalid symbol type",
            })
            continue

        validation = validate_symbol(symbol, lookup=lookup)
        if not validation.get("valid"):
            invalid_symbol_details.append({
                "symbol": symbol,
                "exchange": validation.get("exchange") or detect_exchange(symbol),
                "reason": validation.get("reason") or "Symbol not found in loaded FYERS symbol master",
            })
            continue
        valid_symbols.append(validation.get("normalized_symbol") or symbol)

    deduped_symbols = unique_preserve_order(valid_symbols)
    quotes = {}
    warnings = []
    metrics = {
        "symbols_requested": len(symbols or []),
        "valid_symbols": len(deduped_symbols),
        "invalid_symbols": len(invalid_symbol_details),
        "api_requests": 0,
        "rate_limit_failures": 0,
    }
    if invalid_symbol_details:
        logger.warning(
            "Skipping %s symbols not found in loaded FYERS masters. examples=%s",
            len(invalid_symbol_details),
            invalid_symbol_details[:10],
        )
        warnings.append(f"Skipped {len(invalid_symbol_details)} symbols not found in loaded FYERS symbol masters.")
        for detail in invalid_symbol_details[:5]:
            warnings.append(f"{detail['symbol']}: {detail['reason']}")

    chunks = list(batch_values(deduped_symbols, QUOTE_CHUNK_SIZE))
    logger.info("Fetching FYERS quotes in %s batches for %s symbols", len(chunks), len(deduped_symbols))

    for index, chunk in enumerate(chunks):
        if index:
            time.sleep(QUOTE_CHUNK_PAUSE_SECONDS)
        try:
            metrics["api_requests"] += 1
            response = fetch_quote_chunk(access_token, chunk)
            if not isinstance(response, dict):
                warnings.append(f"Unexpected FYERS quote response for {chunk[0]} batch.")
                logger.warning("Unexpected FYERS quote response for batch starting %s: %s", chunk[0], response)
                continue
            if response.get("s") != "ok":
                message = response.get("message") or response.get("code") or f"FYERS quote batch failed for {chunk[0]}."
                warnings.append(str(message))
                logger.warning("FYERS quote batch failed: batch=%s message=%s", index + 1, message)
                if "request limit" in str(message).lower():
                    metrics["rate_limit_failures"] += 1

            for quote in response.get("d", []) or []:
                symbol = quote.get("n") or quote.get("symbol")
                if not symbol:
                    continue
                quotes[symbol] = quote
                if quote.get("s") not in (None, "ok"):
                    warning = f"{symbol}: {quote.get('errmsg') or quote.get('message') or quote.get('s')}"
                    warnings.append(warning)
                    logger.warning("FYERS quote warning: %s", warning)
        except Exception as exc:
            warning = f"{chunk[0]} batch failed: {exc}"
            warnings.append(warning)
            logger.warning("FYERS quote batch exception: %s", warning)

    if deduped_symbols and not quotes and raise_if_empty:
        raise RuntimeError("FYERS returned no quote data for the F&O universe.")

    if return_metrics:
        return quotes, warnings[:20], metrics
    return quotes, warnings[:20]


def fetch_quote_chunk(access_token, chunk):
    fyers = make_fyers_client(access_token)
    return fyers.quotes(data={"symbols": ",".join(chunk)})


def quote_status_for_row(item, contracts, quotes):
    expected_symbols = [
        item["spot_symbol"],
        contracts["near"]["fyers_symbol"],
        contracts["next"]["fyers_symbol"],
        contracts["far"]["fyers_symbol"],
    ]
    missing = [symbol for symbol in expected_symbols if symbol not in quotes]
    return "Missing: " + ", ".join(missing) if missing else "OK"


def extract_quote_price(quote):
    if not quote:
        return None
    values = quote.get("v") if isinstance(quote, dict) else {}
    for key in ("lp", "ltp", "last_price", "close_price"):
        value = parse_float(values.get(key))
        if value is not None and value > 0:
            return round(value, 2)
    return None


def percentage_difference(future_price, spot_price):
    if future_price is None or spot_price in (None, 0):
        return None
    return round(((future_price - spot_price) / spot_price) * 100, 4)


def contract_value(lot_size, spot_price):
    if not lot_size or spot_price is None:
        return None
    return round(lot_size * spot_price, 2)


def summarize_fno_rows(rows):
    valid_near = [row for row in rows if row["nearDiffPct"] is not None]
    contract_values = [row["contractValue"] for row in rows if row["contractValue"] is not None]
    highest_premium = max(valid_near, key=lambda row: row["nearDiffPct"], default=None)
    highest_discount = min(valid_near, key=lambda row: row["nearDiffPct"], default=None)
    average_near = sum(row["nearDiffPct"] for row in valid_near) / len(valid_near) if valid_near else 0

    return {
        "totalStocks": len(rows),
        "averageNearPremiumPct": round(average_near, 4),
        "highestPremiumStock": summary_stock_payload(highest_premium, "nearDiffPct"),
        "highestDiscountStock": summary_stock_payload(highest_discount, "nearDiffPct"),
        "totalMarketContractValue": round(sum(contract_values), 2),
    }


def summary_stock_payload(row, value_key):
    if not row:
        return None
    return {
        "symbol": row["symbol"],
        "stockName": row["stockName"],
        "value": row[value_key],
    }


def parse_float(value):
    try:
        if value in (None, ""):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_positive_int(value, label):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        raise ValueError(f"{label} must be a whole number.")
    if parsed < 1:
        raise ValueError(f"{label} must be at least 1.")
    return parsed


def pct_amount(base, pct):
    if base is None or pct is None:
        return 0
    return round_money(float(base) * float(pct) / 100)


def percentage_of(value, base):
    if base in (None, 0):
        return None
    return round((float(value) / float(base)) * 100, 4)


def annualized_return(return_pct, days):
    if return_pct is None or not days or days <= 0:
        return None
    growth = 1 + (return_pct / 100)
    if growth <= 0:
        return None
    return round((growth ** (365 / days) - 1) * 100, 4)


def days_until_expiry(expiry_ts):
    expiry_value = parse_float(expiry_ts)
    if expiry_value is None:
        return None
    expiry_date = datetime.fromtimestamp(expiry_value, IST).date()
    return max(0, (expiry_date - datetime.now(IST).date()).days)


def round_money(value):
    return round(float(value or 0), 2)


if __name__ == "__main__":
    debug = os.getenv("FLASK_DEBUG", "0").lower() in {"1", "true", "yes"}
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=debug)
