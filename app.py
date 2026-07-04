import logging
import os
import time
from datetime import date, datetime, timedelta
from io import BytesIO
from zoneinfo import ZoneInfo

import pandas as pd
from dotenv import load_dotenv
from flask import Flask, jsonify, redirect, render_template, request, send_file, session, url_for

from services.fyers_credentials import (
    clear_fyers_config,
    describe_fyers_config,
    get_fyers_config,
    save_fyers_config,
)
from services.screener_service import get_screener_metadata, run_indicator_screener
from services.symbol_search import search_symbols
from services.symbol_resolver import resolve_symbol
from services.symbol_mapper import (
    FYERS_NSE_CM_SYMBOL_MASTER_URL,
    FYERS_NSE_FO_SYMBOL_MASTER_URL,
    build_fno_contract_catalog,
)
from services.symbol_validator import detect_exchange, get_symbol_master_lookup, startup_master_diagnostics, validate_symbol
from strategy import build_chart_payload, run_por_backtest
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

try:
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
    today = date.today()
    default_start = today - timedelta(days=30)
    return render_template(
        "index.html",
        authenticated=bool(session.get("access_token")),
        config_errors=errors,
        **fyers_render_context(),
        default_start=default_start.isoformat(),
        default_end=today.isoformat(),
    )


@app.route("/nse-fno-analytics")
def nse_fno_analytics():
    errors = config_errors()
    return render_template(
        "nse_fno_analytics.html",
        authenticated=bool(session.get("access_token")),
        config_errors=errors,
        **fyers_render_context(),
    )


@app.route("/indicator-screener")
def indicator_screener():
    errors = config_errors()
    return render_template(
        "indicator_screener.html",
        authenticated=bool(session.get("access_token")),
        config_errors=errors,
        **fyers_render_context(),
    )


@app.route("/login")
def login():
    errors = config_errors(include_credentials=True)
    if errors:
        return render_template(
            "index.html",
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
            "index.html",
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
            "index.html",
            authenticated=False,
            config_errors=[str(exc)],
            **fyers_render_context(),
        ), 400

    access_token = response.get("access_token") if isinstance(response, dict) else None
    if not access_token:
        message = response.get("message", "Unable to generate FYERS access token.") if isinstance(response, dict) else str(response)
        return render_template(
            "index.html",
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


@app.route("/api/analyze", methods=["POST"])
def analyze():
    payload = request.get_json(silent=True) or {}
    symbol = (payload.get("symbol") or "").strip().upper()
    if not symbol:
        return jsonify({"error": "Enter a FYERS symbol such as NSE:SBIN-EQ, BSE:RELIANCE-A, or MCX:GOLDPETAL26JUNFUT."}), 400

    if not session.get("access_token"):
        return jsonify({"error": "Login with FYERS before fetching data."}), 401

    try:
        resolution = resolve_symbol(None, symbol)
        if not resolution.get("success"):
            details = {
                "symbol": symbol,
                "exchange": resolution.get("exchange") or detect_exchange(symbol),
                "reason": resolution.get("reason") or "Symbol resolution failed",
            }
            return jsonify({"error": details["reason"], "details": details}), 400

        resolved_symbol = resolution["symbol"]
        options = parse_backtest_options(payload)
        df = fetch_history(resolved_symbol, options["date_from"], options["date_to"])
        if df.empty:
            return jsonify({"error": "FYERS returned no candles for this symbol/date range."}), 404

        trades, metrics = run_por_backtest(
            df,
            session_start=options["session_start"],
            signal_start=options["signal_start"],
            session_exit=options["session_exit"],
        )
        chart = build_chart_payload(df, trades)
        return jsonify({
            "symbol": resolved_symbol,
            "chart": chart,
            "trades": trades,
            "metrics": metrics,
            "options": {
                "date_from": options["date_from"].isoformat(),
                "date_to": options["date_to"].isoformat(),
                "session_start": options["session_start"].strftime("%H:%M"),
                "signal_start": options["signal_start"].strftime("%H:%M"),
                "session_exit": options["session_exit"].strftime("%H:%M"),
            },
        })
    except ValueError as exc:
        details = exc.args[0] if exc.args and isinstance(exc.args[0], dict) else None
        if details:
            message = details.get("reason") or str(exc)
            return jsonify({"error": message, "details": details}), 400
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


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


@app.route("/api/indicator-screener/metadata")
def indicator_screener_metadata():
    warnings = []
    catalog_items = []
    try:
        catalog = get_fno_contract_catalog()
        catalog_items = catalog["items"]
    except Exception as exc:
        warnings.append(f"Unable to load live F&O catalog: {exc}")

    metadata = get_screener_metadata(catalog_items)
    metadata["warnings"] = warnings
    return jsonify(metadata)


@app.route("/api/indicator-screener/scan", methods=["POST"])
def indicator_screener_scan():
    access_token = session.get("access_token")
    if not access_token:
        return jsonify({"error": "Login with FYERS before running the indicator screener."}), 401

    errors = config_errors()
    if errors:
        return jsonify({"error": "; ".join(errors)}), 400

    payload = request.get_json(silent=True) or {}
    try:
        catalog = get_fno_contract_catalog()

        def history_fetcher(symbol, resolution, date_from, date_to):
            return fetch_history_with_token(access_token, symbol, resolution, date_from, date_to)

        result = run_indicator_screener(payload, catalog, history_fetcher)
        return jsonify(result)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/api/export", methods=["POST"])
def export_trades():
    payload = request.get_json(silent=True) or {}
    trades = payload.get("trades") or []
    metrics = payload.get("metrics") or {}
    symbol = (payload.get("symbol") or "trades").replace(":", "_").replace("/", "_")
    options = payload.get("options") or {}

    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        trades_df = pd.DataFrame(trades)
        if trades_df.empty:
            trades_df = pd.DataFrame(columns=[
                "side", "entry_time", "entry_price", "exit_time", "exit_price", "exit_reason", "pnl", "por"
            ])
        trades_df.to_excel(writer, sheet_name="Trades", index=False)

        summary_rows = [
            {"metric": "symbol", "value": payload.get("symbol", "")},
            {"metric": "date_from", "value": options.get("date_from", "")},
            {"metric": "date_to", "value": options.get("date_to", "")},
            {"metric": "session_start", "value": options.get("session_start", "")},
            {"metric": "signal_start", "value": options.get("signal_start", "")},
            {"metric": "session_exit", "value": options.get("session_exit", "")},
            {"metric": "total_pnl", "value": metrics.get("total_pnl", 0)},
            {"metric": "win_rate", "value": metrics.get("win_rate", 0)},
            {"metric": "drawdown", "value": metrics.get("drawdown", 0)},
            {"metric": "trade_count", "value": metrics.get("trade_count", 0)},
        ]
        pd.DataFrame(summary_rows).to_excel(writer, sheet_name="Summary", index=False)

    output.seek(0)
    filename = f"{symbol}_por_trades.xlsx"
    return send_file(
        output,
        as_attachment=True,
        download_name=filename,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@app.route("/api/indicator-screener/export", methods=["POST"])
def export_indicator_screener():
    payload = request.get_json(silent=True) or {}
    rows = payload.get("rows") or []
    scan = payload.get("scan") or {}
    generated_at = payload.get("generated_at") or ""
    export_format = (payload.get("format") or "xlsx").lower()
    exported_at = datetime.now(IST).isoformat()
    export_rows = build_indicator_export_rows(rows, scan, generated_at, exported_at)
    safe_stamp = datetime.now(IST).strftime("%Y%m%d_%H%M%S")

    if export_format == "csv":
        output = BytesIO()
        csv_text = pd.DataFrame(export_rows).to_csv(index=False)
        output.write(csv_text.encode("utf-8-sig"))
        output.seek(0)
        return send_file(
            output,
            as_attachment=True,
            download_name=f"Advanced_FO_Indicator_Screener_{safe_stamp}.csv",
            mimetype="text/csv",
        )

    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        pd.DataFrame(export_rows).to_excel(writer, sheet_name="Screener Results", index=False)
        pd.DataFrame(build_indicator_export_summary(scan, rows, generated_at, exported_at)).to_excel(
            writer,
            sheet_name="Scan Summary",
            index=False,
        )

    output.seek(0)
    return send_file(
        output,
        as_attachment=True,
        download_name=f"Advanced_FO_Indicator_Screener_{safe_stamp}.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


def build_indicator_export_rows(rows, scan, generated_at, exported_at):
    filters = indicator_scan_filter_text(scan)
    conditions = indicator_condition_text(scan.get("conditions") or [])
    return [
        {
            "Exported At": exported_at,
            "Data Timestamp": generated_at,
            "Selected Filters": filters,
            "Indicator Conditions": conditions,
            "Condition Timeframes": ", ".join(row.get("conditionTimeframes") or []) if row.get("conditionTimeframes") else "",
            "Logic": scan.get("logic", "AND"),
            "Stock Name": row.get("stockName"),
            "Symbol": row.get("symbol"),
            "Sector": row.get("sector"),
            "Instrument Type": row.get("instrumentType"),
            "FYERS Symbol": row.get("fyersSymbol"),
            "Current Price": row.get("currentPrice"),
            "RSI": row.get("rsi"),
            "ADX": row.get("adx"),
            "Supertrend Status": row.get("supertrendStatus"),
            "VWAP Status": row.get("vwapStatus"),
            "Bollinger Status": row.get("bollingerStatus"),
            "Signal Strength": row.get("signalStrength"),
            "Signal Bias": row.get("signalBias"),
            "Primary Timeframe": row.get("primaryTimeframe"),
            "Timeframe": row.get("timeframe"),
            "Volume": row.get("volume"),
            "Volume Breakout Ratio": row.get("volumeBreakoutRatio"),
            "Last Updated": row.get("lastUpdated"),
        }
        for row in rows
    ]


def build_indicator_export_summary(scan, rows, generated_at, exported_at):
    return [
        {"Metric": "Exported At", "Value": exported_at},
        {"Metric": "Data Timestamp", "Value": generated_at},
        {"Metric": "Selected Filters", "Value": indicator_scan_filter_text(scan)},
        {"Metric": "Default Timeframe", "Value": scan.get("defaultTimeframeLabel") or scan.get("timeframeLabel") or scan.get("timeframe") or ""},
        {"Metric": "Condition Timeframes", "Value": indicator_condition_timeframes_text(scan.get("conditions") or [])},
        {"Metric": "Logic", "Value": scan.get("logic", "AND")},
        {"Metric": "Indicator Conditions", "Value": indicator_condition_text(scan.get("conditions") or [])},
        {"Metric": "Result Count", "Value": len(rows)},
    ]


def indicator_scan_filter_text(scan):
    return " | ".join([
        f"Instruments: {', '.join(scan.get('instrumentTypes') or [])}",
        f"Sectors: {', '.join(scan.get('sectors') or [])}",
        f"Timeframe: {scan.get('timeframeLabel') or scan.get('timeframe') or ''}",
    ])


def indicator_condition_text(conditions):
    if not conditions:
        return "No explicit indicator conditions"
    parts = []
    for condition in conditions:
        value = condition.get("value")
        value_text = "" if value in (None, "") else f" {value}"
        timeframe_text = condition.get("timeframeLabel") or condition.get("timeframe") or ""
        suffix = f" @ {timeframe_text}" if timeframe_text else ""
        parts.append(f"{condition.get('indicator')} {condition.get('operator')}{value_text}{suffix}")
    return "; ".join(parts)


def indicator_condition_timeframes_text(conditions):
    labels = []
    for condition in conditions:
        label = condition.get("timeframeLabel") or condition.get("timeframe")
        if label and label not in labels:
            labels.append(label)
    return ", ".join(labels)


def get_fno_contract_catalog():
    return build_fno_contract_catalog()


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


def fetch_history(symbol, date_from=None, date_to=None):
    return fetch_history_with_token(session.get("access_token"), symbol, "5", date_from, date_to)


def fetch_history_with_token(token, symbol, resolution="5", date_from=None, date_to=None):
    resolution_result = resolve_symbol(None, symbol)
    if not resolution_result.get("success"):
        raise ValueError({
            "symbol": symbol,
            "exchange": resolution_result.get("exchange") or detect_exchange(symbol),
            "reason": resolution_result.get("reason") or "Symbol not found in loaded FYERS symbol master",
        })
    symbol = resolution_result["symbol"]

    fyers = make_fyers_client(token)
    today = datetime.now().date()
    start = date_from or (today - timedelta(days=30))
    end = date_to or today
    request_payload = {
        "symbol": symbol,
        "resolution": resolution,
        "date_format": "1",
        "range_from": start.strftime("%Y-%m-%d"),
        "range_to": end.strftime("%Y-%m-%d"),
        "cont_flag": "1",
    }

    response = None
    for attempt in range(3):
        response = fyers.history(data=request_payload)
        if isinstance(response, dict) and response.get("s") == "ok":
            break
        message = (response.get("message") or response.get("code")) if isinstance(response, dict) else str(response)
        if "request limit" in str(message).lower() and attempt < 2:
            sleep_for = 1.5 * (attempt + 1)
            logger.warning("FYERS history rate limit for %s %s; retrying in %.1fs", symbol, resolution, sleep_for)
            time.sleep(sleep_for)
            continue
        break

    if not isinstance(response, dict):
        raise RuntimeError(f"Unexpected FYERS response: {response}")
    if response.get("s") != "ok":
        message = response.get("message") or response.get("code") or "FYERS history request failed."
        logger.warning("FYERS history failed for %s %s: %s", symbol, resolution, message)
        raise RuntimeError(message)

    candles = response.get("candles", [])
    df = pd.DataFrame(candles, columns=["timestamp", "open", "high", "low", "close", "volume"])
    if df.empty:
        return df

    df["datetime"] = parse_fyers_timestamps(df["timestamp"])
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df.dropna(subset=["datetime", "open", "high", "low", "close"]).sort_values("datetime").reset_index(drop=True)


def parse_backtest_options(payload):
    today = datetime.now().date()
    default_start = today - timedelta(days=30)
    date_from = parse_date(payload.get("date_from"), default_start)
    date_to = parse_date(payload.get("date_to"), today)
    if date_from > date_to:
        raise ValueError("Start date cannot be after end date.")

    session_start = parse_time_value(payload.get("session_start"), "09:15")
    signal_start = parse_time_value(payload.get("signal_start"), "09:20")
    session_exit = parse_time_value(payload.get("session_exit"), "15:15")
    if not (session_start < signal_start <= session_exit):
        raise ValueError("Times must follow: session start < signal start <= exit time.")

    return {
        "date_from": date_from,
        "date_to": date_to,
        "session_start": session_start,
        "signal_start": signal_start,
        "session_exit": session_exit,
    }


def parse_date(value, default):
    if not value:
        return default
    return datetime.strptime(value, "%Y-%m-%d").date()


def parse_time_value(value, default):
    return datetime.strptime(value or default, "%H:%M").time()


def parse_fyers_timestamps(series):
    numeric = pd.to_numeric(series, errors="coerce")
    if numeric.notna().all():
        return pd.to_datetime(numeric, unit="s", utc=True).dt.tz_convert("Asia/Kolkata")
    parsed = pd.to_datetime(series, errors="coerce")
    if parsed.dt.tz is None:
        return parsed.dt.tz_localize("Asia/Kolkata")
    return parsed.dt.tz_convert("Asia/Kolkata")


if __name__ == "__main__":
    debug = os.getenv("FLASK_DEBUG", "0").lower() in {"1", "true", "yes"}
    app.run(host="127.0.0.1", port=5000, debug=debug)
