import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from engine import load_groww, get_nifty_candles, signal_from_candles, get_option_chain, select_atm_contract
from risk import size_position

st.set_page_config(page_title="Groww Nifty Options Algo", page_icon="📈", layout="wide")
st.title("Groww Nifty Options Algo")
st.caption("Live-data dashboard + controlled execution worker. Trading options involves substantial risk.")

with st.sidebar:
    st.header("Risk controls")
    capital = st.number_input("Capital (₹)", min_value=1000, value=50000, step=5000)
    risk_trade = st.number_input("Max planned risk/trade (₹)", min_value=50, value=250, step=50)
    daily_stop = st.number_input("Daily loss stop (₹)", min_value=100, value=500, step=100)
    lot_size = st.number_input("NIFTY lot size (verify current exchange value)", min_value=1, value=65, step=1)
    st.caption("Lot size can change; verify before every deployment.")
    expiry = st.text_input("Expiry date (YYYY-MM-DD)", value="")
    st.caption("Leave blank to choose nearest future expiry from Groww's expiry API.")

st.warning("This dashboard does not run an unattended trading loop. Streamlit Cloud is not a reliable always-on trading worker. Deploy worker.py as a separate persistent service/VPS for automated execution.")
st.subheader("Connection")
try:
    groww = load_groww()
    st.success("Groww SDK initialized")
except Exception as e:
    groww = None
    st.error(f"Groww API not configured: {e}")
    st.info("Add GROWW_ACCESS_TOKEN in Streamlit Secrets. Never commit credentials to GitHub.")

if groww:
    col1, col2, col3 = st.columns(3)
    try:
        candles = get_nifty_candles(groww)
        sig = signal_from_candles(candles)
        col1.metric("NIFTY latest close", f'{candles.iloc[-1]["close"]:,.2f}')
        col2.metric("Signal", sig["action"])
        col3.metric("Signal candle", str(sig.get("timestamp", "—")))
        st.write(sig["reason"])
        st.line_chart(candles.set_index("timestamp")[["close", "vwap", "ema20"]].tail(80), height=300)
        with st.expander("Latest candles"):
            st.dataframe(candles.tail(20), use_container_width=True, hide_index=True)
        if sig["action"] in ("CALL_BIAS", "PUT_BIAS"):
            expiries = groww.get_expiries(exchange=groww.EXCHANGE_NSE, underlying_symbol="NIFTY")
            available = sorted(expiries.get("expiries", []))
            today = datetime.now().date().isoformat()
            future = [x for x in available if x >= today]
            chosen_expiry = expiry.strip() or (future[0] if future else "")
            st.write(f"Selected expiry: **{chosen_expiry or 'No future expiry returned'}**")
            if chosen_expiry:
                chain = get_option_chain(groww, chosen_expiry)
                contract = select_atm_contract(chain, sig["action"])
                if contract:
                    st.json(contract)
                    st.caption("Signal and contract preview only. The dashboard does not submit orders.")
                else:
                    st.warning("Could not select an ATM contract from the returned option chain.")
    except Exception as e:
        st.error(f"Groww data request failed: {type(e).__name__}: {e}")

st.subheader("Position sizing")
a, b, c = st.columns(3)
with a:
    premium = st.number_input("Option premium (₹)", min_value=0.05, value=100.0, step=1.0)
with b:
    stop_premium = st.number_input("Stop premium (₹)", min_value=0.05, value=90.0, step=1.0)
with c:
    fraction = st.slider("Capital allocation cap", min_value=0.1, max_value=0.9, value=0.5, step=0.1)
if st.button("Calculate size"):
    try:
        result = size_position(capital, risk_trade, premium, stop_premium, int(lot_size), fraction)
        st.json(result)
    except ValueError as e:
        st.error(str(e))

st.subheader("Automated execution")
st.write("For live execution, configure worker.py separately. The worker defaults to PAPER mode.")
st.markdown("""
1. Set credentials in the deployment's secret manager.
2. Run the worker on a persistent host with restricted access.
3. Test in PAPER mode and verify logs/order state for several sessions.
4. Only then consider enabling live execution after checking current Groww/exchange requirements.
""")
