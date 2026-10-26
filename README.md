# Groww Algo — clean Streamlit dashboard

A simplified, Groww-inspired UI for market overview, strategy signal, option-contract preview and position sizing.

## What works in this version
- Streamlit dashboard with clean cards and tabs.
- Groww API authentication via either a current access token or API key + TOTP secret.
- 5-minute NIFTY historical candles, VWAP and EMA20.
- Opening-range breakout signal.
- ATM option-chain preview when the signal is directional.
- Risk-based position-size calculator.
- Optional persistent worker scaffold that logs signals only.

## What is not implemented
- This version does **not** place live orders. `worker.py` logs signals only.
- It does not guarantee profit or validate the strategy's edge.
- It has not been tested with the user's specific Groww credentials/account. Verify SDK response formats and API access in paper mode before relying on it.

## Deploy on Streamlit Community Cloud
1. Upload the repository contents to the root of your GitHub repo.
2. In Streamlit Community Cloud, create an app from the repo; main file path: `app.py`.
3. Under app settings → Secrets, add:
   ```toml
   GROWW_API_KEY = "..."
   GROWW_TOTP_SECRET = "..."
   ```
   Use the API/TOTP token and secret provided by Groww's Trading API page. Do not share them in chat or commit them to GitHub.
4. Reboot the app.

If you have a valid access token instead, use `GROWW_ACCESS_TOKEN` instead of the two TOTP settings. Access tokens may expire, so check current Groww docs.

## Run locally
```bash
pip install -r requirements.txt
streamlit run app.py
```

## Worker scaffold
Set the same auth variables as environment variables on a persistent host and run:
```bash
python worker.py
```
It only logs signals; it does not execute orders. Streamlit Community Cloud should be treated as the UI layer, not an always-on trading engine.

Official docs:
- https://groww.in/trade-api/docs/python-sdk
- https://groww.in/trade-api/docs/python-sdk/live-data
- https://groww.in/trade-api/docs/python-sdk/orders

Options trading is risky. Planned stop-loss is not guaranteed fill price; gaps, slippage, outages and rejected orders can cause larger losses.
