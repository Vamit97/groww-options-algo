"""
Persistent worker scaffold for Groww NIFTY options.

Default mode is PAPER. This worker is intentionally conservative:
- live order placement requires LIVE_TRADING=true and a second explicit LIVE_CONFIRM=I_UNDERSTAND value
- one entry per day, maximum trades/day and daily loss limit are enforced locally
- a SQLite state file records signal timestamps and paper trades
- the strategy uses NIFTY 5-minute candles and ATM CE/PE selection

IMPORTANT: Before real-money use, independently validate Groww SDK response formats,
current contract lot size, order status/partial fills, stop execution and restart recovery.
A process crash or network failure can still prevent timely exit; this is not a guarantee of protection.
"""
import os, time, json, sqlite3, logging
from datetime import datetime, date
from engine import load_groww, get_nifty_candles, signal_from_candles, get_option_chain, select_atm_contract
from risk import size_position

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
DB = os.getenv("STATE_DB", "trader_state.sqlite3")
CAPITAL = float(os.getenv("CAPITAL", "50000"))
RISK_PER_TRADE = float(os.getenv("RISK_PER_TRADE", "250"))
DAILY_LOSS_LIMIT = float(os.getenv("DAILY_LOSS_LIMIT", "500"))
MAX_TRADES_PER_DAY = int(os.getenv("MAX_TRADES_PER_DAY", "1"))
LOT_SIZE = int(os.getenv("LOT_SIZE", "65"))  # Verify current contract lot size.
STOP_PCT = float(os.getenv("STOP_PCT", "0.10"))
TARGET_PCT = float(os.getenv("TARGET_PCT", "0.20"))
POLL_SECONDS = int(os.getenv("POLL_SECONDS", "20"))
LIVE = os.getenv("LIVE_TRADING", "false").lower() == "true"
LIVE_CONFIRM = os.getenv("LIVE_CONFIRM", "") == "I_UNDERSTAND"

def db():
    conn = sqlite3.connect(DB)
    conn.execute("""CREATE TABLE IF NOT EXISTS events (
        id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, event TEXT, details TEXT
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS trades (
        id INTEGER PRIMARY KEY AUTOINCREMENT, day TEXT, symbol TEXT, side TEXT,
        qty INTEGER, entry REAL, stop REAL, target REAL, status TEXT,
        last_price REAL, pnl REAL DEFAULT 0, entry_order_id TEXT, exit_order_id TEXT
    )""")
    conn.commit()
    return conn

def log_event(conn, event, details):
    conn.execute("INSERT INTO events(ts,event,details) VALUES(?,?,?)",
                 (datetime.now().isoformat(timespec="seconds"), event, json.dumps(details, default=str)))
    conn.commit()
    logging.info("%s %s", event, details)

def place_order(groww, symbol, qty, transaction_type):
    if not (LIVE and LIVE_CONFIRM):
        return {"paper": True, "symbol": symbol, "qty": qty, "transaction_type": transaction_type}
    return groww.place_order(
        trading_symbol=symbol,
        quantity=int(qty),
        validity=groww.VALIDITY_DAY,
        exchange=groww.EXCHANGE_NSE,
        segment=groww.SEGMENT_FNO,
        product=groww.PRODUCT_MIS,
        order_type=groww.ORDER_TYPE_MARKET,
        transaction_type=(groww.TRANSACTION_TYPE_BUY if transaction_type == "BUY" else groww.TRANSACTION_TYPE_SELL)
    )

def current_expiry(groww):
    expiries = groww.get_expiries(exchange=groww.EXCHANGE_NSE, underlying_symbol="NIFTY").get("expiries", [])
    today = date.today().isoformat()
    future = sorted(x for x in expiries if x >= today)
    if not future:
        raise RuntimeError("No future NIFTY expiry returned by Groww")
    return future[0]

def get_option_price(groww, symbol):
    quote = groww.get_quote(exchange=groww.EXCHANGE_NSE, segment=groww.SEGMENT_FNO, trading_symbol=symbol)
    price = quote.get("last_price") or quote.get("ltp")
    if price is None:
        raise RuntimeError(f"No LTP returned for {symbol}")
    return float(price)

def main():
    conn = db()
    groww = load_groww()
    log_event(conn, "WORKER_STARTED", {"mode": "LIVE" if LIVE and LIVE_CONFIRM else "PAPER"})
    seen_signal_candle = None
    while True:
        try:
            candles = get_nifty_candles(groww)
            signal = signal_from_candles(candles)
            signal_ts = signal.get("timestamp")
            today = date.today().isoformat()

            # Manage open position first.
            row = conn.execute("""SELECT id,symbol,side,qty,entry,stop,target,status FROM trades
                                  WHERE day=? AND status='OPEN' ORDER BY id DESC LIMIT 1""", (today,)).fetchone()
            if row:
                tid, symbol, side, qty, entry, stop, target, status = row
                px = get_option_price(groww, symbol)
                conn.execute("UPDATE trades SET last_price=?, pnl=? WHERE id=?",
                             (px, (px-entry)*qty, tid))
                conn.commit()
                if px <= stop or px >= target:
                    resp = place_order(groww, symbol, qty, "SELL")
                    status = "CLOSED" if not resp.get("paper") else "PAPER_CLOSED"
                    conn.execute("UPDATE trades SET status=?,exit_order_id=? WHERE id=?",
                                 (status, str(resp), tid))
                    conn.commit()
                    log_event(conn, "EXIT", {"symbol": symbol, "price": px, "reason": "STOP" if px <= stop else "TARGET", "response": resp})
                time.sleep(POLL_SECONDS)
                continue

            # Enforce daily local realized P&L and trade count.
            day_pnl = conn.execute("SELECT COALESCE(SUM(pnl),0) FROM trades WHERE day=? AND status IN ('CLOSED','PAPER_CLOSED')", (today,)).fetchone()[0]
            trades_count = conn.execute("SELECT COUNT(*) FROM trades WHERE day=?", (today,)).fetchone()[0]
            if day_pnl <= -DAILY_LOSS_LIMIT or trades_count >= MAX_TRADES_PER_DAY:
                time.sleep(POLL_SECONDS)
                continue

            if signal["action"] not in ("CALL_BIAS", "PUT_BIAS") or signal_ts == seen_signal_candle:
                time.sleep(POLL_SECONDS)
                continue
            seen_signal_candle = signal_ts
            expiry = current_expiry(groww)
            chain = get_option_chain(groww, expiry)
            contract = select_atm_contract(chain, signal["action"])
            if not contract:
                log_event(conn, "NO_CONTRACT", {"signal": signal, "expiry": expiry})
                time.sleep(POLL_SECONDS)
                continue
            entry = float(contract["ltp"])
            stop = round(entry * (1 - STOP_PCT), 2)
            target = round(entry * (1 + TARGET_PCT), 2)
            sizing = size_position(CAPITAL, RISK_PER_TRADE, entry, stop, LOT_SIZE, 0.5)
            if sizing["quantity"] <= 0:
                log_event(conn, "SKIP_SIZE", {"contract": contract, "sizing": sizing})
                time.sleep(POLL_SECONDS)
                continue
            resp = place_order(groww, contract["trading_symbol"], sizing["quantity"], "BUY")
            trade_status = "OPEN" if not resp.get("paper") else "PAPER_OPEN"
            conn.execute("""INSERT INTO trades(day,symbol,side,qty,entry,stop,target,status,last_price,pnl,entry_order_id)
                            VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                         (today, contract["trading_symbol"], contract["side"], sizing["quantity"], entry,
                          stop, target, trade_status, entry, 0, str(resp)))
            conn.commit()
            log_event(conn, "ENTRY", {"signal": signal, "contract": contract, "sizing": sizing, "response": resp})
        except Exception as e:
            log_event(conn, "ERROR", {"type": type(e).__name__, "message": str(e)})
        time.sleep(POLL_SECONDS)

if __name__ == "__main__":
    main()
