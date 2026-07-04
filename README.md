# FYERS Trading Analytics Platform

This repository contains a Flask-based trading analytics workspace built around FYERS API V3. It now ships with three dashboards:

- POR Strategy Dashboard
- NSE F&O Live Analytics Dashboard
- Advanced F&O Indicator Screener

The app uses FYERS symbol masters for validation and resolution, pandas/numpy for local indicator calculations, and cached, batched fetch flows to stay stable under FYERS rate limits.

## What Changed In This Workspace

- Added the third dashboard at `/indicator-screener`.
- Added navigation between all three pages.
- Added mixed-timeframe indicator conditions in the screener, including supported daily and weekly analysis.
- Added symbol-master validation, batched quotes, cached candles, and bounded concurrency to reduce `Invalid input` and `request limit reached` failures.
- Added a server-side FYERS credentials panel for online deployment, with environment fallback.

## Repository Layout

```text
app.py
strategy.py
services/
  cache_service.py
  indicator_engine.py
  screener_service.py
  sector_mapping.py
  symbol_mapper.py
  symbol_resolver.py
  symbol_search.py
  symbol_validator.py
static/
  app.js
  indicator_screener.js
  nse_fno_analytics.js
  analytics/
    calculations.js
    excelExport.js
templates/
  index.html
  nse_fno_analytics.html
  indicator_screener.html
utils/
  batching.py
  indicators/
    adx.py
    bollinger.py
    rsi.py
    supertrend.py
    vwap.py
```

## Setup

1. Create and activate a virtual environment.
2. Install dependencies:

   ```powershell
   python -m pip install -r requirements.txt
   ```

3. Copy `.env.example` to `.env`.
4. Either set the FYERS credentials in `.env` or use the FYERS Credentials panel after the app starts.
5. Set the FYERS redirect URL to:

   ```text
   http://127.0.0.1:5000/callback
   ```

6. Start the app:

   ```powershell
   python app.py
   ```

7. Open:

   - `http://127.0.0.1:5000`
   - `http://127.0.0.1:5000/nse-fno-analytics`
   - `http://127.0.0.1:5000/indicator-screener`

## Environment

The sample environment files define these values:

- `FLASK_SECRET_KEY` - signs Flask sessions and should be set in production.
- `FYERS_CLIENT_ID`
- `FYERS_SECRET_KEY`
- `FYERS_REDIRECT_URI`

The current workspace also loads `.env` in `app.py` and can persist runtime FYERS app credentials to `instance/fyers_runtime_config.json`.

## FYERS Credentials

FYERS OAuth gives the application an auth code and access token after the user logs in. It does not return your app client secret. For that reason, the app supports two ways to configure the FYERS app credentials:

- environment variables in `.env`
- the FYERS Credentials panel in the UI

The panel saves server-side runtime credentials and keeps the login flow working for online deployments. If you change the FYERS app credentials, the current access token is cleared and you should log in again.

## Pages

### POR Strategy Dashboard

`/`

- Symbol search and direct FYERS symbol entry.
- Date range selection.
- Session start, signal start, and exit time controls.
- POR strategy backtest execution.
- Plotly candlestick chart rendering.
- Trade table and Excel export.
- FYERS Credentials panel shared across the app.

### NSE F&O Live Analytics Dashboard

`/nse-fno-analytics`

- Live or near-real-time NSE F&O futures analytics.
- Spot, near-month, next-month, and far-month prices.
- Premium and discount percentages.
- Search, filter, sort, pagination, and export.
- Summary cards for total stocks, average premium, top premium, top discount, and total contract value.
- FYERS Credentials panel shared across the app.

### Advanced F&O Indicator Screener

`/indicator-screener`

- Instrument universe selection for spot, near month, next month, and far month contracts.
- Sector filters backed by the FYERS F&O catalog.
- Global default timeframe.
- Per-condition timeframe overrides.
- Multi-condition AND / OR logic.
- Presets, saved scans, search, sort, pagination, and export.
- Auto refresh every 60 seconds.
- FYERS Credentials panel shared across the app.

## Indicator Screener Behavior

The screener is designed as a proper scan engine, not a fixed-timeframe form.

Each condition row can carry its own timeframe. If a condition does not specify one, it inherits the scan default timeframe.

Example payload:

```json
{
  "instrumentTypes": ["spot", "near"],
  "sectors": ["Banking"],
  "timeframe": "5",
  "logic": "AND",
  "conditions": [
    {"indicator": "rsi", "operator": "above", "value": 60, "timeframe": "5"},
    {"indicator": "adx", "operator": "above", "value": 25, "timeframe": "1D"},
    {"indicator": "supertrend", "operator": "price_above", "value": null, "timeframe": "1W"}
  ]
}
```

That means one scan can evaluate RSI on 5-minute candles, ADX on daily candles, and Supertrend on weekly candles at the same time.
Weekly scans are built from FYERS daily history and resampled locally, because the FYERS history client supports `1D` but not a direct weekly history resolution.

The row output keeps a timeframe summary, and exports include the default timeframe plus per-condition timeframe text.

### Screener Summary Cards

The top metrics strip shows:

- Total Stocks Scanned
- Matching Results
- Bullish Signals
- Bearish Signals
- Strongest Momentum Stock
- Highest ADX Stock
- Highest Volume Breakout

### Screener Result Table

The results table displays:

- Stock Name
- Sector
- Instrument Type
- Current Price
- RSI
- ADX
- Supertrend Status
- VWAP Status
- Bollinger Status
- Signal Strength
- Timeframe
- Volume
- Last Updated

## Screener Scan Flow

1. Load the FYERS F&O catalog.
2. Resolve symbols from FYERS masters.
3. Filter the universe by instrument type and sector.
4. Build a timeframe plan per symbol and condition.
5. Fetch candle history once per symbol/timeframe.
6. Cache candles for repeated scans.
7. Compute all indicators locally from the same candle set.
8. Evaluate the selected conditions with AND / OR logic.
9. Return matching rows, summary cards, warnings, and health metrics.

## Supported Indicator Groups

The screener engine supports the following local indicator groups:

- Momentum: RSI, MACD, ADX, Stochastic RSI, Momentum
- Trend: Supertrend, EMA, SMA, VWAP, Ichimoku, Parabolic SAR
- Volatility: Bollinger Bands, ATR, Keltner Channel
- Volume: OBV, Volume Breakout, Delivery Volume %

The indicator engine uses pandas/numpy plus local helper modules in `utils/indicators/`.

## Signal Strength

Matched conditions contribute to a scoring model.

- Bullish conditions add positive bias.
- Bearish conditions add negative bias.
- Neutral conditions contribute zero.

The final row label is rendered as text like:

- `3/3 Strong Bullish`
- `2/3 Moderate Bullish`
- `2/3 Moderate Bearish`

The screener also returns `signalBias` and individual indicator status columns for quick scanning.

## Backend Architecture

### `app.py`

Main Flask application entry point.

- Auth flow: `/login`, `/callback`, `/logout`
- Dashboard routes: `/`, `/nse-fno-analytics`, `/indicator-screener`
- Analysis APIs: `/api/analyze`, `/api/nse-fno-analytics`, `/api/indicator-screener/scan`
- Export APIs: `/api/export`, `/api/indicator-screener/export`
- Symbol helpers: `/api/symbol-search`, `/api/debug/symbol-check`
- FYERS historical fetch with symbol resolution and retry handling

### `strategy.py`

POR backtest logic and chart payload creation.

### `services/symbol_validator.py`

Unified FYERS symbol-master validation.

- Loads the FYERS symbol masters.
- Detects and normalizes exchange prefixes.
- Validates symbols by master lookup instead of simple string rules.

### `services/symbol_resolver.py`

Symbol resolution helper.

- Resolves spot, future, and option symbols.
- Chooses the best FYERS symbol candidate from the loaded masters.
- Helps the app turn partial or exchange-less inputs into valid FYERS symbols.

### `services/symbol_mapper.py`

F&O catalog builder.

- Loads FYERS NSE CM and NSE FO masters.
- Builds spot symbol maps and futures contract maps.
- Produces the F&O universe used by the analytics and screener pages.

### `services/symbol_search.py`

Search catalog for symbols and company names across the loaded masters.

### `services/sector_mapping.py`

Sector tagging and display helpers for NSE F&O symbols.

### `services/cache_service.py`

Lightweight in-memory TTL cache and rate limiter used by the screener candle path.

### `services/fyers_credentials.py`

FYERS app credential loader and runtime override store.

- Reads credentials from environment variables.
- Persists manual runtime credentials in `instance/fyers_runtime_config.json`.
- Exposes the current configuration state for the UI and login flow.

### `services/indicator_engine.py`

Indicator calculations and rule evaluation.

- Calculates RSI, MACD, ADX, Stochastic RSI, momentum, Supertrend, EMA, SMA, VWAP, Ichimoku, Parabolic SAR, Bollinger Bands, ATR, Keltner Channel, OBV, and delivery-volume estimates.
- Builds candle snapshots.
- Evaluates indicator rules and label strength.

### `services/screener_service.py`

Scan orchestration for the advanced screener.

- Builds the instrument universe.
- Validates symbols before fetching candles.
- Groups requests into batches.
- Applies a bounded worker pool.
- Pulls candle data once per symbol/timeframe.
- Applies the per-condition timeframe plan.
- Calculates health metrics and warnings.

### `utils/batching.py`

Shared helpers for batching and deduping values.

### `utils/indicators/*`

Low-level indicator implementations used by the engine.

- `adx.py`
- `bollinger.py`
- `rsi.py`
- `supertrend.py`
- `vwap.py`

### `static/*.js`

Browser-side logic for each page.

- `static/app.js` powers the POR strategy dashboard.
- `static/nse_fno_analytics.js` powers the NSE F&O analytics table.
- `static/indicator_screener.js` powers the indicator screener UI, saved scans, presets, and result controls.
- `static/analytics/calculations.js` and `static/analytics/excelExport.js` support the live analytics page.

### `templates/*.html`

Jinja templates for the three dashboards.

- `templates/index.html`
- `templates/nse_fno_analytics.html`
- `templates/indicator_screener.html`

## API Endpoints

- `GET /` - POR dashboard.
- `GET /nse-fno-analytics` - NSE F&O live analytics dashboard.
- `GET /indicator-screener` - advanced screener dashboard.
- `GET /login` - FYERS login redirect.
- `GET /callback` - FYERS auth-code callback.
- `POST /logout` - clear the Flask session.
- `POST /api/analyze` - fetch candles and run the POR strategy.
- `POST /api/export` - export POR trades to Excel.
- `GET /api/nse-fno-analytics` - live futures analytics payload.
- `GET /api/indicator-screener/metadata` - screener metadata, presets, indicators, sectors, timeframes, and mapped symbols.
- `POST /api/indicator-screener/scan` - run the indicator scan.
- `POST /api/indicator-screener/export` - export screener results to CSV or Excel.
- `GET /api/fyers-config` - read the current FYERS app credential state.
- `POST /api/fyers-config` - save runtime FYERS app credentials.
- `DELETE /api/fyers-config` - clear the runtime FYERS app credentials.
- `GET /api/symbol-search?q=...` - symbol search across loaded masters.
- `POST /api/debug/symbol-check` - inspect a symbol against the master lookup.

## Performance And Stability Notes

- The NSE F&O analytics page fetches quotes in 50-symbol batches.
- The screener fetches candle data once per symbol/timeframe and computes all indicators locally.
- The screener uses a TTL candle cache with a 60-second lifetime.
- The screener uses bounded concurrency instead of a wide worker pool.
- The screener spaces history requests and batch groups to reduce rate-limit bursts.
- If one symbol fails, the scan keeps running.
- Logging is used for invalid symbols, cache hits, cache misses, API failures, and rate-limit responses.

## Screener Health Metrics

The screener response includes health details such as:

```json
{
  "symbols_scanned": 190,
  "valid_symbols": 185,
  "invalid_symbols": 5,
  "cache_hits": 120,
  "cache_misses": 40,
  "api_requests": 8,
  "history_api_requests": 8,
  "quote_api_requests": 0,
  "failed_symbols": 0,
  "rate_limit_failures": 0,
  "elapsed_ms": 4123,
  "cache_size": 34
}
```

These values are surfaced in logs and help confirm whether the scan is behaving cleanly under load.

## Export Details

### POR export

- Excel workbook via `/api/export`
- Includes trades and summary sheets

### Screener export

- Excel or CSV via `/api/indicator-screener/export`
- Includes:
  - timestamp
  - selected filters
  - indicator conditions
  - per-condition timeframes
  - row data
  - scan summary

## Troubleshooting

- `Invalid input`: usually means the symbol was not found in the FYERS master lookup. Use the symbol search or debug check endpoint.
- `request limit reached`: the new batching and caching path should reduce this a lot, but it can still appear if the FYERS API is under pressure.
- `FYERS credentials are not configured`: enter the Client ID, Secret Key, and Redirect URI in the FYERS Credentials panel or set them in `.env`.
- No scan results: the filters may be too strict, or the selected universe may not have enough candles for the chosen timeframe mix.
- Login required: authenticate with FYERS before running scans or loading analytics data.

## Notes

- There is no separate frontend build step. The app uses Flask, Jinja templates, and static JavaScript files directly.
- The screener computes indicators from candle history instead of asking FYERS for each indicator separately.
- If you change FYERS credentials, keep `.env` or the FYERS Credentials panel aligned with the FYERS app you registered.
