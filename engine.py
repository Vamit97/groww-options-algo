from datetime import datetime, timedelta
import pandas as pd
from growwapi import GrowwAPI

def load_groww():
    # Streamlit Secrets first, environment variable second.
    import os
    token = ""
    try:
        import streamlit as st
        token = str(st.secrets.get("GROWW_ACCESS_TOKEN", "")).strip()
    except Exception:
        pass
    token = token or os.getenv("GROWW_ACCESS_TOKEN", "").strip()
    if not token:
        raise RuntimeError("Missing GROWW_ACCESS_TOKEN")
    return GrowwAPI(token)

def get_nifty_candles(groww, lookback_hours=8):
    end = datetime.now()
    start = end - timedelta(hours=lookback_hours)
    result = groww.get_historical_candles(
        exchange=groww.EXCHANGE_NSE,
        segment=groww.SEGMENT_CASH,
        groww_symbol="NSE-NIFTY",
        start_time=start.strftime("%Y-%m-%d %H:%M:%S"),
        end_time=end.strftime("%Y-%m-%d %H:%M:%S"),
        candle_interval=groww.CANDLE_INTERVAL_MIN_5
    )
    rows = result.get("candles", [])
    if not rows:
        raise RuntimeError("Groww returned no NIFTY candles")
    df = pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close", "volume", "oi"])
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["timestamp", "open", "high", "low", "close"]).sort_values("timestamp")
    df = df.drop_duplicates("timestamp").reset_index(drop=True)
    typical = (df["high"] + df["low"] + df["close"]) / 3
    vol = df["volume"].fillna(0).clip(lower=0)
    cv = vol.cumsum().replace(0, float("nan"))
    df["vwap"] = (typical * vol).cumsum() / cv
    df["ema20"] = df["close"].ewm(span=20, adjust=False).mean()
    return df

def signal_from_candles(candles):
    if len(candles) < 5:
        return {"action": "WAIT", "reason": "Need at least five candles.", "timestamp": None}
    df = candles.reset_index(drop=True)
    # Opening range uses first 3 candles from the current returned session.
    first_date = df.iloc[0]["timestamp"].date()
    session = df[df["timestamp"].dt.date == first_date].reset_index(drop=True)
    if len(session) < 5:
        return {"action": "WAIT", "reason": "Not enough candles in current session.", "timestamp": str(df.iloc[-1]["timestamp"])}
    opening_high = float(session.loc[:2, "high"].max())
    opening_low = float(session.loc[:2, "low"].min())
    last, prev = session.iloc[-1], session.iloc[-2]
    if (last["close"] > opening_high and last["close"] > last["vwap"]
            and last["close"] > last["ema20"] and prev["close"] <= opening_high):
        return {"action": "CALL_BIAS", "reason": "5m close above opening range, VWAP and EMA20.", "timestamp": str(last["timestamp"])}
    if (last["close"] < opening_low and last["close"] < last["vwap"]
            and last["close"] < last["ema20"] and prev["close"] >= opening_low):
        return {"action": "PUT_BIAS", "reason": "5m close below opening range, VWAP and EMA20.", "timestamp": str(last["timestamp"])}
    return {"action": "WAIT", "reason": "No qualifying breakout on latest candle.", "timestamp": str(last["timestamp"])}

def get_option_chain(groww, expiry_date):
    return groww.get_option_chain(
        exchange=groww.EXCHANGE_NSE,
        underlying="NIFTY",
        expiry_date=expiry_date
    )

def select_atm_contract(chain, action):
    # Groww option-chain response documented as strikes -> strike -> CE/PE -> contract fields.
    underlying = float(chain.get("underlying_ltp") or 0)
    strikes = chain.get("strikes") or {}
    side = "CE" if action == "CALL_BIAS" else "PE"
    candidates = []
    for strike_text, sides in strikes.items():
        try:
            strike = float(strike_text)
            contract = (sides or {}).get(side) or {}
            symbol = contract.get("trading_symbol")
            ltp = float(contract.get("ltp") or 0)
            if symbol and ltp > 0:
                candidates.append((abs(strike - underlying), strike, symbol, ltp, contract))
        except (ValueError, TypeError):
            continue
    if not candidates:
        return None
    _, strike, symbol, ltp, raw = min(candidates, key=lambda x: x[0])
    return {"side": side, "strike": strike, "trading_symbol": symbol, "ltp": ltp, "raw": raw}
