# Worker-safe Groww authentication/data wrappers (no Streamlit dependency).
from datetime import datetime, timedelta, date
import os
import pandas as pd
from growwapi import GrowwAPI

def make_groww_client():
    token = os.getenv("GROWW_ACCESS_TOKEN", "").strip()
    if token:
        return GrowwAPI(token)
    api_key = os.getenv("GROWW_API_KEY", "").strip()
    totp_secret = os.getenv("GROWW_TOTP_SECRET", "").strip()
    if not api_key or not totp_secret:
        raise RuntimeError("Set GROWW_ACCESS_TOKEN or GROWW_API_KEY and GROWW_TOTP_SECRET.")
    import pyotp
    token = GrowwAPI.get_access_token(api_key=api_key, totp=pyotp.TOTP(totp_secret).now())
    return GrowwAPI(token)

def get_nifty_candles(groww, lookback_hours=8):
    end = datetime.now()
    start = end - timedelta(hours=lookback_hours)
    response = groww.get_historical_candles(
        exchange=groww.EXCHANGE_NSE, segment=groww.SEGMENT_CASH,
        groww_symbol="NSE-NIFTY",
        start_time=start.strftime("%Y-%m-%d %H:%M:%S"),
        end_time=end.strftime("%Y-%m-%d %H:%M:%S"),
        candle_interval=groww.CANDLE_INTERVAL_MIN_5)
    rows = response.get("candles", [])
    parsed = [r[:6] for r in rows if not isinstance(r, dict) and len(r) >= 6]
    df = pd.DataFrame(parsed, columns=["timestamp", "open", "high", "low", "close", "volume"])
    if df.empty:
        raise RuntimeError("No candles returned by Groww.")
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="s", errors="coerce")
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["timestamp", "open", "high", "low", "close"]).sort_values("timestamp")
    typical = (df.high + df.low + df.close) / 3
    vol = df.volume.fillna(0).clip(lower=0)
    df["vwap"] = (typical * vol).cumsum() / vol.cumsum().replace(0, float("nan"))
    df["ema20"] = df.close.ewm(span=20, adjust=False).mean()
    return df.reset_index(drop=True)

def build_signal(candles):
    from engine import build_signal as _build
    return _build(candles)
