import streamlit as st
import pandas as pd
import sqlite3
import os

st.set_page_config(page_title="Algo Monitor", page_icon="📊", layout="wide")
st.title("Groww Algo — Worker Monitor")
st.caption("This dashboard reads the worker's SQLite database. For separate hosts, use a shared database or log store.")

db_path = st.text_input("SQLite database path", value=os.getenv("STATE_DB", "trader_state.sqlite3"))
if st.button("Refresh"):
    st.rerun()
try:
    conn = sqlite3.connect(db_path)
    trades = pd.read_sql_query("SELECT * FROM trades ORDER BY id DESC LIMIT 100", conn)
    events = pd.read_sql_query("SELECT * FROM events ORDER BY id DESC LIMIT 100", conn)
    a, b, c = st.columns(3)
    a.metric("Trades logged", len(trades))
    if not trades.empty:
        b.metric("Open positions", int(trades["status"].isin(["OPEN", "PAPER_OPEN"]).sum()))
        c.metric("Recorded P&L", f'₹{pd.to_numeric(trades["pnl"], errors="coerce").fillna(0).sum():,.2f}')
    st.subheader("Trades")
    st.dataframe(trades, use_container_width=True, hide_index=True)
    st.subheader("Worker events")
    st.dataframe(events, use_container_width=True, hide_index=True)
except Exception as e:
    st.info(f"No worker database found yet: {e}")
