"""
Optional persistent worker scaffold. Defaults to paper mode.
Do not enable LIVE_TRADING until you have independently tested every Groww order/position response.
"""
import os, time, json, sqlite3, logging
from datetime import datetime
from engine_worker import make_groww_client, get_nifty_candles, build_signal
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
LIVE_TRADING = os.getenv("LIVE_TRADING", "false").lower() == "true"
LIVE_CONFIRM = os.getenv("LIVE_CONFIRM", "") == "I_UNDERSTAND"
POLL_SECONDS = int(os.getenv("POLL_SECONDS", "30"))
DB = os.getenv("STATE_DB", "algo_state.sqlite3")

def main():
    conn = sqlite3.connect(DB)
    conn.execute("CREATE TABLE IF NOT EXISTS events(ts TEXT, event TEXT, details TEXT)")
    conn.commit()
    groww = make_groww_client()
    mode = "LIVE" if LIVE_TRADING and LIVE_CONFIRM else "PAPER"
    logging.info("Worker started in %s mode. This scaffold emits signals only; order execution is not wired.", mode)
    while True:
        try:
            candles = get_nifty_candles(groww)
            signal = build_signal(candles)
            details = json.dumps(signal)
            conn.execute("INSERT INTO events VALUES(?,?,?)", (datetime.now().isoformat(), "SIGNAL", details))
            conn.commit()
            logging.info("Signal: %s", details)
        except Exception as exc:
            conn.execute("INSERT INTO events VALUES(?,?,?)", (datetime.now().isoformat(), "ERROR", str(exc)))
            conn.commit()
            logging.exception("Worker error")
        time.sleep(POLL_SECONDS)

if __name__ == "__main__":
    main()
