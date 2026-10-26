# Groww NIFTY Options Algo — repo-ready build

The GitHub repository supplied by the user was empty when checked. This source package is ready to upload into the repository root.

## Included
- `app.py`: Streamlit live-data dashboard (Groww API required)
- `worker.py`: persistent strategy worker; PAPER by default; guarded live order code
- `dashboard.py`: worker database monitor
- `engine.py`: Groww SDK data, 5-minute NIFTY candles, VWAP/EMA opening-range signal, ATM option-chain selection
- `risk.py`: risk-based sizing
- `requirements.txt`: dependencies

## Important limitations
This is a reference implementation, not a certified or production-validated trading system. It has not been tested with the user's Groww account or credentials. Do not turn on live trading without reviewing the code, testing SDK responses, validating lot size and product/order parameters, and testing failure scenarios. Local P&L is not a substitute for broker-confirmed P&L. Stops are monitored by the worker and are not guaranteed broker-side protective orders; if the worker/network goes down, exit logic can fail. For real use, prefer broker-supported protective/Smart Orders where appropriate and verify behavior.

₹5,000 profit per trade is not guaranteed. Strategy is an unproven breakout setup.

## Deploy dashboard
1. Upload these files to GitHub repository root.
2. In Streamlit Community Cloud, create app from repo and set main file to `app.py`.
3. Add `GROWW_ACCESS_TOKEN` using Streamlit Secrets (never commit it).
4. The dashboard fetches current 5-minute candles and displays a signal/ATM contract preview.

## Run worker separately
Do **not** run the worker as a background process inside Streamlit Community Cloud. Deploy it as a persistent worker on a VPS or worker-capable host. Streamlit is the UI; worker is the execution process.

```bash
pip install -r requirements.txt
# configure environment variables using your host's secret manager
python worker.py
```

Worker defaults to paper mode. It logs simulated entries/exits into SQLite. For remote dashboard access, configure a shared persistent database/log store; a local SQLite file on the worker is not automatically available to Streamlit Cloud.

## Live mode safety gate
Live order placement requires both:
- `LIVE_TRADING=true`
- `LIVE_CONFIRM=I_UNDERSTAND`

Do not set these until you have completed paper testing and reviewed the official Groww API docs. This gate is not a guarantee of safety. Verify all broker/exchange/SEBI rules and the active Groww API subscription.

Official Groww docs:
- https://groww.in/trade-api/docs/python-sdk
- https://groww.in/trade-api/docs/python-sdk/live-data
- https://groww.in/trade-api/docs/python-sdk/orders
- https://groww.in/trade-api/docs/python-sdk/backtesting
