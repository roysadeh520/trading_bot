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

PAIRS = [
    "BTCUSD", "ETHUSD", "SOLUSD", "ADAUSD", "XRPUSD", "DOTUSD", "LINKUSD", "MATICUSD", "AVAXUSD", "DOGEUSD",
    "LTCUSD", "ATOMUSD", "UNIUSD", "AAVEUSD", "NEARUSD", "XLMUSD", "ETCUSD", "EOSUSD", "TRXUSD", "ALGOUSD",
    "FILUSD", "ICPUSD", "FTMUSD"
]
MAX_TRADES_PER_DAY = 100
STOP_LOSS_THRESHOLD = -0.02
FEE = 0.0025  # עדכון: עמלת קנייה של 0.25%
INITIAL_CAPITAL = 5000
TRADE_INTERVAL_MINUTES = 1
OHLC_INTERVAL_MINUTES = 5  # פחות זמן, יותר רגיש
BUY_DROP_THRESHOLD = -0.01  # ירידה של 1%
SELL_GAIN_THRESHOLD = 0.0075  # רווח של 0.75%

capital = INITIAL_CAPITAL
trade_counter = 0
last_reset_day = datetime.utcnow().day
holdings = {}
total_ohlc_history = {pair: [] for pair in PAIRS}


def get_latest_ohlc(pair):
    url = f"https://api.kraken.com/0/public/OHLC?pair={pair}&interval={OHLC_INTERVAL_MINUTES}"
    try:
        resp = requests.get(url).json()
        result = list(resp['result'].values())[0]
        history = result[-6:]  # 6 נרות = 30 דקות
        total_ohlc_history[pair] = [(float(x[1]), float(x[4]), float(x[3])) for x in history]
        last = total_ohlc_history[pair][-1]
        return last[0], last[1], last[2]  # open, close, low
    except Exception as e:
        print(f"Error fetching OHLC for {pair}: {e}")
        return None, None, None


def get_recent_change(pair, periods=6):
    history = total_ohlc_history.get(pair, [])
    if len(history) < periods:
        return 0
    start = history[0][1]
    end = history[-1][1]
    return (end - start) / start


def get_trade_signal(pair, open_price, close_price, low_price):
    trend_pct = get_recent_change(pair, 6)
    change_pct = (close_price - open_price) / open_price
    dip_pct = (low_price - open_price) / open_price
    print(f"📊 ניתוח: שינוי {change_pct:.3%}, צניחה {dip_pct:.3%}, שינוי חצי שעה {trend_pct:.3%}")

    if trend_pct < BUY_DROP_THRESHOLD:
        return "buy"
    if pair in holdings:
        for lot in holdings[pair]:
            buy_price = lot["buy_price"]
            if (close_price - buy_price) / buy_price > SELL_GAIN_THRESHOLD:
                return "sell"
    return "hold"


def place_order_mock(pair, side, volume, price):
    print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] {side.upper()} {pair} {volume:.4f} units at ${price:.2f}")


def calculate_total_value(current_prices):
    total = capital
    for pair, lots in holdings.items():
        if pair in current_prices:
            close_p = current_prices[pair]
            for lot in lots:
                total += lot["amount"] * close_p
    return total


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
        current_prices = {}

        for pair in PAIRS:
            print(f"\n🔄 בודק את {pair}...")
            open_p, close_p, low_p = get_latest_ohlc(pair)
            if None in (open_p, close_p, low_p):
                print(f"⚠️ לא התקבלו נתונים עבור {pair}")
                continue

            current_prices[pair] = close_p
            print(f"💱 מחירי {pair}: Open={open_p:.2f} | Close={close_p:.2f}")
            signal = get_trade_signal(pair, open_p, close_p, low_p)

            if pair in holdings:
                to_remove = []
                for i, lot in enumerate(holdings[pair]):
                    buy_price = lot["buy_price"]
                    amount = lot["amount"]
                    change = (close_p - buy_price) / buy_price
                    if signal == "sell" or change < STOP_LOSS_THRESHOLD:
                        pnl_pct = change - FEE
                        profit = amount * buy_price * pnl_pct
                        capital += amount * close_p
                        trade_counter += 1
                        place_order_mock(pair, "sell", amount, close_p)
                        print(f"💸 רווח ממומש: ${profit:.2f}")
                        print(f"💼 Capital after sell: ${capital:.2f} | Trade #{trade_counter}")
                        to_remove.append(i)
                for idx in sorted(to_remove, reverse=True):
                    del holdings[pair][idx]
                if not holdings[pair]:
                    del holdings[pair]

            if signal == "buy":
                investment = capital / (MAX_TRADES_PER_DAY - trade_counter)
                if capital < 10 or investment > capital:
                    print(f"❌ אין מספיק הון לרכישה של {pair} (נשארו ${capital:.2f})")
                    continue
                volume = investment / open_p
                cost = volume * open_p
                capital -= cost

                if pair not in holdings:
                    holdings[pair] = []
                holdings[pair].append({"amount": volume, "buy_price": open_p})

                trade_counter += 1
                place_order_mock(pair, "buy", volume, open_p)
                print(f"💼 Capital after buy: ${capital:.2f} | Trade #{trade_counter}")
            else:
                print("🚫 No trade signal")

        total_value = calculate_total_value(current_prices)
        percent_change = (total_value - INITIAL_CAPITAL) / INITIAL_CAPITAL * 100
        print(f"📈 שווי נוכחי כולל של התיק: ${total_value:.2f} ({percent_change:+.2f}%)")

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
