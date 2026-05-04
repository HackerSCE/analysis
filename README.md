# FYERS POR Strategy Dashboard

A full-stack Flask app for FYERS API V3 authentication, 5-minute historical data fetches, POR strategy backtesting, Plotly candlestick visualization, and performance metrics.

## Setup

1. Create and activate a virtual environment.
2. Install dependencies:

   ```powershell
   python -m pip install -r requirements.txt
   ```

3. Copy `.env.example` to `.env` and fill in your FYERS app details:

   ```powershell
   Copy-Item .env.example .env
   ```

4. In the FYERS developer console, set the app redirect URL to:

   ```text
   http://127.0.0.1:5000/callback
   ```

5. Start the app:

   ```powershell
   python app.py
   ```

6. Open `http://127.0.0.1:5000`, log in with FYERS, then analyze symbols like `NSE:SBIN-EQ`.

## Backtest Controls

- Choose the symbol, date range, session start, signal start, and session exit from the dashboard.
- Click `Analyze` to fetch FYERS 5-minute candles and run the POR strategy.
- Click `Download Excel` after analysis to export the trade history and summary metrics to an `.xlsx` workbook.

## Notes

- FYERS symbols must use the exchange format expected by FYERS, for example `NSE:SBIN-EQ` or an option contract symbol.
- The strategy uses the 09:15 candle close as POR, waits for a close above or below POR after 09:20, then enters only when a later candle breaks the marked signal candle high or low.
