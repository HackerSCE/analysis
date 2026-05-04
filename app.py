import os
from datetime import date, datetime, timedelta
from io import BytesIO

import pandas as pd
from dotenv import load_dotenv
from flask import Flask, jsonify, redirect, render_template, request, send_file, session, url_for

from strategy import build_chart_payload, run_por_backtest

try:
    from fyers_apiv3 import fyersModel
except ImportError:  # Keeps the dashboard bootable before dependencies are installed.
    fyersModel = None

# Change this line in app.py (near line 16)
basedir = os.path.abspath(os.path.dirname(__file__))
# This tells Python to look in the exact same folder as app.py
load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))

print("--- ENVIRONMENT DEBUG ---")
print(f"Current Directory: {os.getcwd()}")
print(f"FYERS_CLIENT_ID: {os.getenv('FYERS_CLIENT_ID')}")
print(f"FYERS_SECRET_KEY: {os.getenv('FYERS_SECRET_KEY')}")
print(f"FYERS_REDIRECT_URI: {os.getenv('FYERS_REDIRECT_URI')}")
print("-------------------------")


app = Flask(__name__)
app.secret_key = "prajwalp776"

def fyers_config():
    return {
        "client_id": "0ZQ4U7I0VQ-100",
        "secret_key": "NXSJE4VDPZ",
        "redirect_uri": "http://127.0.0.1:5000/callback"
    }


def config_errors():
    cfg = fyers_config()
    # This will print to your terminal every time you refresh the page
    print(f"DEBUG Check - ID: {cfg['client_id']}, Secret: {cfg['secret_key']}")
    
    missing = [key for key, value in cfg.items() if not value]
    errors = []
    if missing:
        errors.append(f"Missing values: {', '.join(missing)}")
    if fyersModel is None:
        errors.append("fyers-apiv3 not installed")
    return errors



def make_session_model():
    cfg = fyers_config()
    return fyersModel.SessionModel(
        client_id=cfg["client_id"],
        secret_key=cfg["secret_key"],
        redirect_uri=cfg["redirect_uri"],
        response_type="code",
        grant_type="authorization_code",
    )


def make_fyers_client():
    token = session.get("access_token")
    if not token:
        raise RuntimeError("Not authenticated with FYERS.")
    return fyersModel.FyersModel(
        client_id=fyers_config()["client_id"],
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
        client_id=fyers_config()["client_id"],
        default_start=default_start.isoformat(),
        default_end=today.isoformat(),
    )


@app.route("/login")
def login():
    errors = config_errors()
    if errors:
        return render_template("index.html", authenticated=False, config_errors=errors), 400

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
        ), 400

    session_model = make_session_model()
    session_model.set_token(auth_code)
    response = session_model.generate_token()

    access_token = response.get("access_token") if isinstance(response, dict) else None
    if not access_token:
        message = response.get("message", "Unable to generate FYERS access token.") if isinstance(response, dict) else str(response)
        return render_template("index.html", authenticated=False, config_errors=[message]), 400

    session["access_token"] = access_token
    session["token_created_at"] = datetime.utcnow().isoformat()
    return redirect(url_for("index"))


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"ok": True})


@app.route("/api/analyze", methods=["POST"])
def analyze():
    payload = request.get_json(silent=True) or {}
    symbol = (payload.get("symbol") or "").strip().upper()
    if not symbol:
        return jsonify({"error": "Enter a FYERS symbol such as NSE:SBIN-EQ."}), 400

    if not session.get("access_token"):
        return jsonify({"error": "Login with FYERS before fetching data."}), 401

    try:
        options = parse_backtest_options(payload)
        df = fetch_history(symbol, options["date_from"], options["date_to"])
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
            "symbol": symbol,
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


def fetch_history(symbol, date_from=None, date_to=None):
    fyers = make_fyers_client()
    today = datetime.now().date()
    start = date_from or (today - timedelta(days=30))
    end = date_to or today
    request_payload = {
        "symbol": symbol,
        "resolution": "5",
        "date_format": "1",
        "range_from": start.strftime("%Y-%m-%d"),
        "range_to": end.strftime("%Y-%m-%d"),
        "cont_flag": "1",
    }
    response = fyers.history(data=request_payload)

    if not isinstance(response, dict):
        raise RuntimeError(f"Unexpected FYERS response: {response}")
    if response.get("s") != "ok":
        raise RuntimeError(response.get("message") or response.get("code") or "FYERS history request failed.")

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
