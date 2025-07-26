# סוכן מסחר רציף עם Kraken API ודמו דרך ChatGPT
# רץ באופן שוטף בענן (Render), בלי לסכן כסף, ומבוסס החלטות GPT

import time
import requests
from datetime import datetime
import krakenex
import os
import threading
from flask import Flask

# התחברות ל-Kraken (להחליף בפרטים אמיתיים או להשאיר ריק לדמו)
api = krakenex.API()
api.key = os.getenv("KRAKEN_API_KEY", "")
api.secret = os.getenv("KRAKEN_API_SECRET", "")

# הגדרות
PAIR = "ETHUSD"
MAX_TRADES_PER_DAY = 30
STOP_LOSS_THRESHOLD = -0.02
FEE = 0.0052
INITIAL_CAPITAL = 5000
TRADE_INTERVAL_MINUTES = 5

# סטטוס הסוכן
capital = INITIAL_CAPITAL
trade_counter = 0
last_reset_day = datetime.utcnow().day

# פונקציית מחירי OHLC ברגע זה

def get_latest_ohlc(pair):
    url = f"https://api.kraken.com/0/public/OHLC?pair={pair}&interval=1"
    try:
        resp = requests.get(url).json()
        result = list(resp['result'].values())[0]
        last = result[-1]  # open, high, low, close, vwap...
        return float(last[1]), float(last[4]), float(last[3])  # open, close, low
    except Exception as e:
        print(f"Error fetching OHLC: {e}", flush=True)
        return None, None, None

# פונקציית החלטה שמתחברת ל-ChatGPT API

def ask_gpt_decision_via_api(open_price, close_price, low_price):
    try:
        response = requests.post("https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {os.getenv('OPENAI')}",
                "Content-Type": "application/json"
            },
            json={
                "model": "gpt-4",
                "messages": [
                    {"role": "system", "content": "אתה סוכן מסחר יומי. אתה עונה רק 'buy', 'sell' או 'hold'."},
                    {"role": "user", "content": f"open={open_price}, close={close_price}, low={low_price}"}
                ]
            })
        decision = response.json()['choices'][0]['message']['content'].strip().lower()
        return decision
    except Exception as e:
        print("❌ GPT API error:", e, flush=True)
        return "hold"

# פקודת קנייה מדומה

def place_order_mock(pair, side, volume, price):
    print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] {side.upper()} {pair} {volume:.4f} units at ${price:.2f}", flush=True)

# פונקציית הריצה המרכזית

def run_bot():
    global capital, trade_counter, last_reset_day
    while True:
        now = datetime.utcnow()
        if now.day != last_reset_day:
            trade_counter = 0
            last_reset_day = now.day
            print("🔁 Reset daily trade counter", flush=True)

        if trade_counter >= MAX_TRADES_PER_DAY:
            print("⏸ הגעת למספר העסקאות היומי. ממתין לחצות...", flush=True)
            time.sleep(300)
            continue

        open_p, close_p, low_p = get_latest_ohlc(PAIR)
        if None in (open_p, close_p, low_p):
            time.sleep(60)
            continue

        decision = ask_gpt_decision_via_api(open_p, close_p, low_p)
        if decision != "buy":
            print("🚫 No trade signal", flush=True)
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

        place_order_mock(PAIR, "buy", volume, open_p)
        print(f"💰 New capital: ${capital:.2f} | Trade #{trade_counter}\n", flush=True)
        time.sleep(TRADE_INTERVAL_MINUTES * 60)

# Flask dummy app to keep Render web service alive
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running"

if __name__ == '__main__':
    threading.Thread(target=run_bot).start()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
