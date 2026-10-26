from datetime import datetime, timedelta, date
import os
import pandas as pd
import streamlit as st
from growwapi import GrowwAPI

@st.cache_resource(ttl=1800, show_spinner=False)
def get_groww_client():
    """Authenticate using access token OR Groww API key + TOTP secret in Streamlit Secrets."""
    access_token = str(st.secrets.get("GROWW_ACCESS_TOKEN", os.getenv("GROWW_ACCESS_TOKEN", ""))).strip()
    if access_token:
        return GrowwAPI(access_token)

    api_key = str(st.secrets.get("GROWW_API_KEY", os.getenv("GROWW_API_KEY", ""))).strip()
    totp_secret = str(st.secrets.get("GROWW_TOTP_SECRET", os.getenv("GROWW_TOTP_SECRET", ""))).strip()
    if not api_key or not totp_secret:
        raise RuntimeError("Missing secrets. Set GROWW_ACCESS_TOKEN OR both GROWW_API_KEY and GROWW_TOTP_SECRET.")

    import pyotp
    code = pyotp.TOTP(totp_secret).now()
    token = GrowwAPI.get_access_token(api_key=api_key, totp=code)
    if not token:
        raise RuntimeError("Groww did not return an access token. Check API key, TOTP secret, subscription and permissions.")
    return GrowwAPI(token)

@st.cache_data(ttl=30, show_spinner=False)
def _cached_candle_data(_client_marker, start_time, end_time):
    # This function is not called directly; Streamlit cache intentionally avoids caching client objects.
    return None

def get_nifty_candles(groww, lookback_hours=8):
    end = datetime.now()
    start = end - timedelta(hours=lookback_hours)
    response = groww.get_historical_candles(
        exchange=groww.EXCHANGE_NSE,
        segment=groww.SEGMENT_CASH,
        groww_symbol="NSE-NIFTY",
        start_time=start.strftime("%Y-%m-%d %H:%M:%S"),
        end_time=end.strftime("%Y-%m-%d %H:%M:%S"),
        candle_interval=groww.CANDLE_INTERVAL_MIN_5,
    )
    rows = response.get("candles", [])
    if not rows:
        raise RuntimeError("No NIFTY candles returned by Groww.")
    parsed = []
    for row in rows:
        # Official examples return [epoch_seconds, open, high, low, close, volume].
        if isinstance(row, dict):
            ts = row.get("timestamp") or row.get("time")
            parsed.append([ts, row.get("open"), row.get("high"), row.get("low"), row.get("close"), row.get("volume", 0)])
        else:
            if len(row) < 6:
                continue
            parsed.append(row[:6])
    df = pd.DataFrame(parsed, columns=["timestamp", "open", "high", "low", "close", "volume"])
    if df.empty:
        raise RuntimeError("Groww candle response did not contain valid OHLCV rows.")
    # Support epoch timestamps or timestamp strings.
    if pd.api.types.is_numeric_dtype(df["timestamp"]):
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="s", errors="coerce")
    else:
        df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["timestamp", "open", "high", "low", "close"]).sort_values("timestamp")
    df = df.drop_duplicates("timestamp").reset_index(drop=True)
    if df.empty:
        raise RuntimeError("No valid candles after parsing Groww response.")
    typical = (df["high"] + df["low"] + df["close"]) / 3
    vol = df["volume"].fillna(0).clip(lower=0)
    denom = vol.cumsum().replace(0, float("nan"))
    df["vwap"] = (typical * vol).cumsum() / denom
    df["ema20"] = df["close"].ewm(span=20, adjust=False).mean()
    return df

def build_signal(candles):
    if len(candles) < 5:
        return {"action": "WAIT", "reason": "At least five 5-minute candles are required."}
    today = candles["timestamp"].iloc[-1].date()
    session = candles[candles["timestamp"].dt.date == today].reset_index(drop=True)
    if len(session) < 5:
        return {"action": "WAIT", "reason": "Not enough candles in the current session yet."}
    opening_high = float(session.loc[:2, "high"].max())
    opening_low = float(session.loc[:2, "low"].min())
    last, prev = session.iloc[-1], session.iloc[-2]
    if (last["close"] > opening_high and last["close"] > last["vwap"]
            and last["close"] > last["ema20"] and prev["close"] <= opening_high):
        return {"action": "CALL_BIAS", "reason": "Latest close broke above the first 15-minute range and is above VWAP/EMA20."}
    if (last["close"] < opening_low and last["close"] < last["vwap"]
            and last["close"] < last["ema20"] and prev["close"] >= opening_low):
        return {"action": "PUT_BIAS", "reason": "Latest close broke below the first 15-minute range and is below VWAP/EMA20."}
    return {"action": "WAIT", "reason": "No qualifying opening-range breakout on the latest candle."}

def get_nearest_expiry(groww):
    result = groww.get_expiries(exchange=groww.EXCHANGE_NSE, underlying_symbol="NIFTY")
    expiries = sorted(str(x) for x in result.get("expiries", []))
    today = date.today().isoformat()
    future = [x for x in expiries if x >= today]
    if not future:
        raise RuntimeError("Groww returned no future NIFTY expiries.")
    return future[0]

def get_option_chain(groww, expiry):
    return groww.get_option_chain(exchange=groww.EXCHANGE_NSE, underlying="NIFTY", expiry_date=expiry)

def pick_atm_option(chain, action):
    underlying = float(chain.get("underlying_ltp") or chain.get("underlyingLtp") or 0)
    strikes = chain.get("strikes") or {}
    side = "CE" if action == "CALL_BIAS" else "PE"
    candidates = []
    if isinstance(strikes, list):
        iterator = [(str(x.get("strike_price") or x.get("strike")), x) for x in strikes]
    else:
        iterator = strikes.items()
    for strike_key, sides in iterator:
        try:
            strike = float(strike_key)
            option = (sides or {}).get(side) or {}
            symbol = option.get("trading_symbol") or option.get("tradingSymbol") or option.get("groww_symbol")
            ltp = float(option.get("ltp") or option.get("last_price") or 0)
            if symbol and ltp > 0:
                candidates.append((abs(strike - underlying), strike, symbol, ltp, option))
        except (ValueError, TypeError, AttributeError):
            continue
    if not candidates:
        return None
    _, strike, symbol, ltp, raw = min(candidates, key=lambda x: x[0])
    return {"side": side, "strike": strike, "trading_symbol": symbol, "ltp": ltp}
