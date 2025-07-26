import time
import requests
from datetime import datetime
import krakenex
import os
import threading
from flask import Flask
import functools

print = functools.partial(print, flush=True)

api = krakenex.API()
api.key = os.getenv("KRAKEN_API_KEY", "")
api.secret = os.getenv("KRAKEN_API_SECRET", "")

PAIRS = ["BTCUSD", "ETHUSD", "SOLUSD"]
MAX_TRADES_PER_DAY = 30
STOP_LOSS_THRESHOLD = -0.02
FEE = 0.0025  # עדכון: עמלת קנייה של 0.25%
INITIAL_CAPITAL = 5000
TRADE_INTERVAL_MINUTES = 1
OHLC_INTERVAL_MINUTES = 15

capital = INITIAL_CAPITAL
trade_counter = 0
last_reset_day = datetime.utcnow().day
holdings = {}  # { "ETHUSD": {"amount": x, "buy_price": y} }

def get_latest_ohlc(pair):
    url = f"https://api.kraken.com/0/public/OHLC?pair={pair}&interval={OHLC_INTERVAL_MINUTES}"
    try:
        resp = requests.get(url).json()
        result = list(resp['result'].values())[0]
        last = result[-1]
        return float(last[1]), float(last[4]), float(last[3])  # open, close, low
    except Exception as e:
        print(f"Error fetching OHLC for {pair}: {e}")
        return None, None, None

def get_trade_signal(open_price, close_price, low_price):
    change_pct = (close_price - open_price) / open_price
    dip_pct = (low_price - open_price) / open_price

    print(f"📊 ניתוח: שינוי {change_pct:.3%}, צניחה {dip_pct:.3%}")

    if change_pct > 0.0005 or dip_pct < -0.003:
        return "buy"
    if change_pct > 0.009 and dip_pct > -0.005:
        return "sell"
    return "hold"

def place_order_mock(pair, side, volume, price):
    print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] {side.upper()} {pair} {volume:.4f} units at ${price:.2f}")

def run_bot():
    global capital, trade_counter, last_reset_day, holdings
    while True:
        now = datetime.utcnow()
        if now.day != last_reset_day:
            trade_counter = 0
            last_reset_day = now.day
            print("🔁 Reset daily trade counter")

        if trade_counter >= MAX_TRADES_PER_DAY:
            print("⏸ הגעת למספר העסקאות היומי. ממתין לחצות...")
            time.sleep(60)
            continue

        print(f"📦 תיק נוכחי: {holdings}")
        for pair in PAIRS:
            print(f"\n🔄 בודק את {pair}...")
            open_p, close_p, low_p = get_latest_ohlc(pair)
            if None in (open_p, close_p, low_p):
                print(f"⚠️ לא התקבלו נתונים עבור {pair}")
                continue

            print(f"💱 מחירי {pair}: Open={open_p:.2f} | Close={close_p:.2f}")
            signal = get_trade_signal(open_p, close_p, low_p)

            # SELL
            if signal == "sell" and pair in holdings:
                bought_at = holdings[pair]["buy_price"]
                amount = holdings[pair]["amount"]
                pnl_pct = (close_p - bought_at) / bought_at - FEE
                profit = amount * bought_at * pnl_pct
                capital += amount * close_p
                trade_counter += 1
                place_order_mock(pair, "sell", amount, close_p)
                print(f"💸 רווח ממומש: ${profit:.2f}")
                print(f"💼 Capital: ${capital:.2f} | Trade #{trade_counter}")
                del holdings[pair]
                continue

            # BUY
            if signal == "buy":
                investment = capital / MAX_TRADES_PER_DAY
                volume = investment / open_p
                cost = volume * open_p
                capital -= cost

                if pair in holdings:
                    prev_amt = holdings[pair]["amount"]
                    prev_price = holdings[pair]["buy_price"]
                    total_amt = prev_amt + volume
                    avg_price = (prev_amt * prev_price + cost) / total_amt
                    holdings[pair] = {"amount": total_amt, "buy_price": avg_price}
                else:
                    holdings[pair] = {"amount": volume, "buy_price": open_p}

                trade_counter += 1
                place_order_mock(pair, "buy", volume, open_p)
                print(f"💼 Capital after buy: ${capital:.2f} | Trade #{trade_counter}")
            else:
                print("🚫 No trade signal")
                print(f"💼 Capital: ${capital:.2f}")

        time.sleep(TRADE_INTERVAL_MINUTES * 60)

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
