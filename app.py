import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, date
from engine import get_groww_client, get_nifty_candles, build_signal, get_nearest_expiry, get_option_chain, pick_atm_option
from risk import size_position

st.set_page_config(
    page_title="Groww Algo",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
:root { --brand: #00a86b; }
.block-container { max-width: 1440px; padding-top: 1.25rem; padding-bottom: 2.5rem; }
[data-testid="stSidebar"] { border-right: 1px solid rgba(120,120,120,.15); }
.hero { padding: 1.2rem 1.4rem; border-radius: 18px; background: linear-gradient(115deg, rgba(0,168,107,.13), rgba(0,168,107,.035)); border: 1px solid rgba(0,168,107,.25); margin-bottom: 1rem; }
.hero-title { font-size: 1.8rem; font-weight: 750; margin: 0; }
.hero-sub { color: #727b78; margin-top: .25rem; font-size: .95rem; }
.pill { display:inline-block; border-radius: 999px; padding: .28rem .65rem; font-size: .78rem; font-weight: 650; background: rgba(0,168,107,.13); color: #008653; }
[data-testid="stMetric"] { border: 1px solid rgba(120,120,120,.20); border-radius: 14px; padding: 14px 16px; background: rgba(120,120,120,.025); }
.small-muted { color: #7b8581; font-size: .82rem; }
div.stButton > button[kind="primary"] { background: #00a86b; border-color: #00a86b; }
</style>
""", unsafe_allow_html=True)

def money(v):
    try:
        return f"₹{float(v):,.2f}"
    except Exception:
        return "—"

with st.sidebar:
    st.markdown("## 📈 Groww Algo")
    st.caption("Simple options trading workspace")
    st.divider()
    st.markdown("### Risk settings")
    capital = st.number_input("Trading capital", min_value=1000, max_value=10000000, value=50000, step=5000, format="%d")
    risk_per_trade = st.number_input("Risk per trade", min_value=50, max_value=100000, value=250, step=50)
    daily_loss_limit = st.number_input("Daily loss limit", min_value=100, max_value=100000, value=500, step=100)
    lot_size = st.number_input("NIFTY lot size", min_value=1, max_value=1000, value=65, step=1,
                               help="Verify the current lot size from official exchange/broker data before trading.")
    capital_fraction = st.slider("Max capital used", 10, 90, 50, 5) / 100
    st.divider()
    st.caption("Broker credentials are read from Streamlit Secrets, never from visible form fields.")
    refresh = st.button("↻ Refresh market data", use_container_width=True)

st.markdown("""
<div class="hero">
  <div class="pill">GROWW API • MARKET DASHBOARD</div>
  <p class="hero-title">Your trading, at a glance.</p>
  <p class="hero-sub">Live market data when connected, clear signals, and risk-first position sizing.</p>
</div>
""", unsafe_allow_html=True)

if "last_refresh" not in st.session_state:
    st.session_state.last_refresh = datetime.now()
if refresh:
    st.cache_data.clear()
    st.session_state.last_refresh = datetime.now()

try:
    groww = get_groww_client()
    connection_ok = True
    connection_msg = "Connected to Groww API"
except Exception as exc:
    groww = None
    connection_ok = False
    connection_msg = str(exc)

c0, c1, c2 = st.columns([1.25, 1, 1])
with c0:
    st.markdown("**Broker connection**")
    if connection_ok:
        st.success("● Connected")
        st.caption("Groww SDK authenticated")
    else:
        st.error("● Not connected")
        st.caption("Check Secrets setup below")
with c1:
    st.metric("Capital", money(capital))
    st.caption(f"Risk per trade: {risk_per_trade/capital:.2%} of capital")
with c2:
    st.metric("Daily loss stop", money(daily_loss_limit))
    st.caption(f"Max allocation: {capital_fraction:.0%}")

if not connection_ok:
    st.error(connection_msg)
    st.markdown("#### Connect your Groww API safely")
    st.markdown("""
Add these values in **Streamlit Cloud → App → Settings → Secrets**. Do not put them in GitHub or send them in chat.

```toml
GROWW_API_KEY = "your Groww API/TOTP token"
GROWW_TOTP_SECRET = "your TOTP secret from Groww"
```

The app generates the short-lived access token from the TOTP secret. If you already use a valid access token instead, set `GROWW_ACCESS_TOKEN` and remove the other two settings.
""")
    st.stop()

try:
    candles = get_nifty_candles(groww)
    signal = build_signal(candles)
    latest = candles.iloc[-1]
    previous = candles.iloc[-2] if len(candles) > 1 else latest
    change = float(latest["close"] - previous["close"])
    change_pct = (change / float(previous["close"]) * 100) if float(previous["close"]) else 0
except Exception as exc:
    st.error(f"Market data could not be loaded: {type(exc).__name__}: {exc}")
    st.info("Check Groww API subscription, credentials, API permissions, and the current SDK response format.")
    st.stop()

st.markdown("### Market overview")
m1, m2, m3, m4 = st.columns(4)
m1.metric("NIFTY 50", f'{latest["close"]:,.2f}', f"{change:+.2f} ({change_pct:+.2f}%)")
m2.metric("VWAP", f'{latest["vwap"]:,.2f}', f'{"Above" if latest["close"] >= latest["vwap"] else "Below"} price')
m3.metric("20 EMA", f'{latest["ema20"]:,.2f}', f'{"Above" if latest["close"] >= latest["ema20"] else "Below"} price')
m4.metric("Latest candle", latest["timestamp"].strftime("%H:%M"), latest["timestamp"].strftime("%d %b %Y"))

st.markdown("### Strategy signal")
s1, s2 = st.columns([1, 2])
with s1:
    if signal["action"] == "CALL_BIAS":
        st.success("🟢 CALL bias")
    elif signal["action"] == "PUT_BIAS":
        st.error("🔴 PUT bias")
    else:
        st.warning("🟡 WAIT")
    st.caption("Signal only — not an order instruction.")
with s2:
    st.write(signal["reason"])
    st.caption("Rules: 5-minute opening range breakout + VWAP + EMA20. This strategy is unproven; validate it before any real-money use.")

tab_market, tab_option, tab_risk, tab_setup = st.tabs(["📊 Chart & candles", "🔎 Option contract", "🛡️ Position sizing", "⚙️ System status"])

with tab_market:
    chart = candles.set_index("timestamp")[["close", "vwap", "ema20"]].tail(100)
    st.line_chart(chart, height=330)
    with st.expander("View latest candles"):
        st.dataframe(candles.tail(20), use_container_width=True, hide_index=True)

with tab_option:
    st.markdown("#### ATM contract preview")
    if signal["action"] not in ("CALL_BIAS", "PUT_BIAS"):
        st.info("No directional setup at the moment. Contract preview is hidden until a signal appears.")
    else:
        try:
            expiry = get_nearest_expiry(groww)
            chain = get_option_chain(groww, expiry)
            contract = pick_atm_option(chain, signal["action"])
            if contract:
                x1, x2, x3 = st.columns(3)
                x1.metric("Expiry", expiry)
                x2.metric("Option side", contract["side"])
                x3.metric("Strike", f'{contract["strike"]:,.0f}')
                st.markdown(f"**Trading symbol:** `{contract['trading_symbol']}`")
                st.metric("Last traded premium", money(contract["ltp"]))
                st.caption("Preview only. The app does not place an order from this screen.")
            else:
                st.warning("Could not identify an ATM contract from Groww's option-chain response.")
        except Exception as exc:
            st.error(f"Option chain unavailable: {type(exc).__name__}: {exc}")

with tab_risk:
    st.markdown("#### Calculate a position before taking a trade")
    x1, x2 = st.columns(2)
    with x1:
        premium = st.number_input("Option buy premium (₹)", min_value=0.05, value=100.0, step=1.0, key="premium")
    with x2:
        stop_premium = st.number_input("Stop-loss premium (₹)", min_value=0.05, value=90.0, step=1.0, key="stop_premium")
    if st.button("Calculate position size", type="primary"):
        try:
            result = size_position(capital, risk_per_trade, premium, stop_premium, int(lot_size), capital_fraction)
            x1, x2, x3 = st.columns(3)
            x1.metric("Lots", str(result["lots"]))
            x2.metric("Quantity", f'{result["quantity"]:,}')
            x3.metric("Premium required", money(result["premium_cost"]))
            st.write(f'Estimated planned loss at stop: **{money(result["planned_loss"])}**')
            if result["lots"] == 0:
                st.warning("No lot fits your selected risk and capital limits. Do not increase risk just to force a trade.")
            st.caption(result["warning"])
        except ValueError as exc:
            st.error(str(exc))

with tab_setup:
    st.markdown("#### Connection details")
    st.write("Groww SDK authentication: **Connected**")
    st.write("Market data: **Loaded successfully**")
    st.write("Order execution from dashboard: **Disabled**")
    st.write("Automated worker: **Separate process required**")
    st.write("Last dashboard refresh:", st.session_state.last_refresh.strftime("%d %b %Y, %H:%M:%S"))
    st.info("For unattended automation, run a separate persistent worker process. Streamlit Cloud is the UI layer, not a reliable 24×7 trading process.")

st.divider()
st.caption("Risk note: options can lose money quickly. Stop orders can slip or fail during outages/gaps. No profit is guaranteed.")
