import time
import requests
from datetime import datetime
import krakenex
import os
import threading
import random
from flask import Flask
import functools

# הדפסות מיידיות בלוגים
print = functools.partial(print, flush=True)

# התחברות ל-Kraken (דמו אם אין API Key)
api = krakenex.API()
api.key = os.getenv("KRAKEN_API_KEY", "")
api.secret = os.getenv("KRAKEN_API_SECRET", "")

# הגדרות
PAIRS = ["BTCUSD", "ETHUSD", "SOLUSD"]
MAX_TRADES_PER_DAY = 30
STOP_LOSS_THRESHOLD = -0.02
FEE = 0.0052
INITIAL_CAPITAL = 5000
TRADE_INTERVAL_MINUTES = 1  # כל דקה – לדמו

# סטטוס סוכן
capital = INITIAL_CAPITAL
trade_counter = 0
last_reset_day = datetime.utcnow().day

# שליפת מחירים עדכניים
def get_latest_ohlc(pair):
    url = f"https://api.kraken.com/0/public/OHLC?pair={pair}&interval=1"
    try:
        resp = requests.get(url).json()
        result = list(resp['result'].values())[0]
        last = result[-1]
        return float(last[1]), float(last[4]), float(last[3])  # open, close, low
    except Exception as e:
        print(f"Error fetching OHLC for {pair}: {e}")
        return None, None, None

# לוגיקה פנימית להחלטת קנייה/מכירה
def ask_gpt_decision_via_api(open_price, close_price, low_price):
    change_pct = (close_price - open_price) / open_price
    dip_pct = (low_price - open_price) / open_price

    print(f"📊 ניתוח: שינוי {change_pct:.3%}, צנילה {dip_pct:.3%}")

    if 0 < change_pct < 0.01 and dip_pct < -0.015:
        return "buy"
    if change_pct > 0.02 and dip_pct > -0.005:
        return "sell"
    return "hold"

# הדמיית פקודת קנייה
def place_order_mock(pair, side, volume, price):
    print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] {side.upper()} {pair} {volume:.4f} units at ${price:.2f}")

# לולאת הסוכן
def run_bot():
    global capital, trade_counter, last_reset_day
    while True:
        pair = random.choice(PAIRS)

        now = datetime.utcnow()
        if now.day != last_reset_day:
            trade_counter = 0
            last_reset_day = now.day
            print("🔁 Reset daily trade counter")

        if trade_counter >= MAX_TRADES_PER_DAY:
            print("⏸ הגעת למספר העסקאות היומי. ממתין לחצות...")
            time.sleep(60)
            continue

        print(f"\n🔄 בודק את {pair}...")
        open_p, close_p, low_p = get_latest_ohlc(pair)
        if None in (open_p, close_p, low_p):
            time.sleep(30)
            continue

        decision = ask_gpt_decision_via_api(open_p, close_p, low_p)
        if decision != "buy":
            print("🚫 No trade signal")
            time.sleep(TRADE_INTERVAL_MINUTES * 60)
            continue

        investment = capital / MAX_TRADES_PER_DAY
        volume = investment / open_p
        pnl_pct = (close_p - open_p) / open_p - FEE

        if (low_p - open_p) / open_p < STOP_LOSS_THRESHOLD:
            pnl_pct = STOP_LOSS_THRESHOLD - FEE

        profit = investment * pnl_pct
        capital += profit
        trade_counter += 1

        place_order_mock(pair, "buy", volume, open_p)
        print(f"💰 New capital: ${capital:.2f} | Trade #{trade_counter}\n")
        time.sleep(TRADE_INTERVAL_MINUTES * 60)

# Flask + self-ping ל-Render
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running"

def self_ping():
    url = os.getenv("SELF_URL")
    if not url:
        print("⚠️ SELF_URL not set – skipping self-ping")
        return
    while True:
        try:
            print("🔁 Self-ping to stay awake...")
            requests.get(url)
        except Exception as e:
            print("Ping failed:", e)
        time.sleep(14 * 60)

if __name__ == '__main__':
    threading.Thread(target=run_bot).start()
    threading.Thread(target=self_ping, daemon=True).start()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
