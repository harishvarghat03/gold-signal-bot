import pandas as pd
from tvDatafeed import TvDatafeed, Interval
import requests
import os

# --- TELEGRAM SEND ---
def send_telegram(message):
    token = os.environ.get("TELEGRAM_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if token and chat_id:
        url = "https://api.telegram.org/bot" + token + "/sendMessage"
        try:
            requests.post(url, json={"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}, timeout=10)
            print("Telegram sent.")
        except Exception as e:
            print("Telegram error: " + str(e))
    else:
        print("No Telegram credentials found.")

# --- BOT LOGIC ---
tv = TvDatafeed()
d = tv.get_hist(symbol='XAUUSD', exchange='OANDA', interval=Interval.in_15_minute, n_bars=1000)
d = d[['open','high','low','close','volume']]

h1 = d.resample('1h').agg({'open':'first','high':'max','low':'min','close':'last','volume':'sum'}).dropna()
h4 = d.resample('4h').agg({'open':'first','high':'max','low':'min','close':'last','volume':'sum'}).dropna()
d1 = d.resample('1D').agg({'open':'first','high':'max','low':'min','close':'last','volume':'sum'}).dropna()

def sc(x):
    x = x.copy()
    x['m20'] = x['close'].rolling(20).mean()
    x['m50'] = x['close'].rolling(50).mean()
    x['s'] = 0
    x.loc[x['close'] > x['m20'], 's'] = 1
    x.loc[x['close'] < x['m20'], 's'] = -1
    x.loc[(x['close'] > x['m20']) & (x['m20'] > x['m50']), 's'] = 2
    x.loc[(x['close'] < x['m20']) & (x['m20'] < x['m50']), 's'] = -2
    return x['s'].iloc[-1]

s1 = sc(d1)
s4 = sc(h4)
s1h = sc(h1)
s15 = sc(d)
total = s1 + s4 + s1h + s15

vol_ma = d['volume'].rolling(20).mean().iloc[-1]
last_vol = d['volume'].iloc[-1]
vol_ok = last_vol > vol_ma

vwap = (d['close'] * d['volume']).rolling(96).sum() / d['volume'].rolling(96).sum()
vwap_val = vwap.iloc[-1]

atr = (d['high'] - d['low']).rolling(14).mean().iloc[-1]
p = d['close'].iloc[-1]

sig = "HOLD"
sl = tp1 = tp2 = 0

if total >= 3 and vol_ok and p > vwap_val:
    sig = "BUY"
elif total <= -3 and vol_ok and p < vwap_val:
    sig = "SELL"

if sig == "BUY":
    sl = p - atr*1.5
    tp1 = p + atr*2.0
    tp2 = p + atr*3.0
elif sig == "SELL":
    sl = p + atr*1.5
    tp1 = p - atr*2.0
    tp2 = p - atr*3.0

print("Scores: 1D " + str(s1) + " 4H " + str(s4) + " 1H " + str(s1h) + " 15m " + str(s15))
print("Total: " + str(total))
print("Volume: " + ("GOOD" if vol_ok else "LOW"))
print("VWAP: " + ("ABOVE" if p > vwap_val else "BELOW"))
print("Signal: " + sig)
print("Price: " + str(round(p, 2)))

# --- SEND TELEGRAM ONLY IF BUY OR SELL ---
if sig == "BUY" or sig == "SELL":
    direction = "GREEN" if sig == "BUY" else "RED"
    msg = ("*ITDA Signal: " + sig + "*\n" +
           "Price: " + str(round(p, 2)) + "\n" +
           "SL: " + str(round(sl, 2)) + "\n" +
           "TP1: " + str(round(tp1, 2)) + "\n" +
           "TP2: " + str(round(tp2, 2)))
    send_telegram(msg)
else:
    print("HOLD - no Telegram sent.")
