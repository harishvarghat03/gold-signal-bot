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

# Resample to all timeframes
h1 = d.resample('1h').agg({'open':'first','high':'max','low':'min','close':'last','volume':'sum'}).dropna()
h4 = d.resample('4h').agg({'open':'first','high':'max','low':'min','close':'last','volume':'sum'}).dropna()
d1 = d.resample('1D').agg({'open':'first','high':'max','low':'min','close':'last','volume':'sum'}).dropna()

# 5-minute data for heartbeat trend
d5 = d.resample('5min').agg({'open':'first','high':'max','low':'min','close':'last','volume':'sum'}).dropna()

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

# --- HEARTBEAT TRENDS ---
def trend_text(series, label):
    if len(series) < 5:
        return label + ": FLAT"
    p_now = series['close'].iloc[-1]
    p_ago = series['close'].iloc[-4] if len(series) > 4 else series['close'].iloc[0]
    diff = p_now - p_ago
    if diff > 0.5:
        arrow = "UP \U0001F7E2"
    elif diff < -0.5:
        arrow = "DOWN \U0001F534"
    else:
        arrow = "FLAT \u26AA"
    return label + ": " + arrow + " (" + str(round(diff, 2)) + ")"

def trend_5m_text(series):
    if len(series) < 5:
        return "5 Min: FLAT"
    p_now = series['close'].iloc[-1]
    p_ago = series['close'].iloc[-2] if len(series) > 1 else series['close'].iloc[0]
    diff = p_now - p_ago
    if diff > 0.5:
        arrow = "UP \U0001F7E2"
    elif diff < -0.5:
        arrow = "DOWN \U0001F534"
    else:
        arrow = "FLAT \u26AA"
    return "5 Min: " + arrow + " (" + str(round(diff, 2)) + ")"

# --- FULL SIGNAL CALC ---
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
if total >= 3 and vol_ok and p > vwap_val:
    sig = "BUY"
elif total <= -3 and vol_ok and p < vwap_val:
    sig = "SELL"

print("Scores: 1D " + str(s1) + " 4H " + str(s4) + " 1H " + str(s1h) + " 15m " + str(s15))
print("Total: " + str(total))
print("Volume: " + ("GOOD" if vol_ok else "LOW"))
print("VWAP: " + ("ABOVE" if p > vwap_val else "BELOW"))
print("Signal: " + sig)
print("Price: " + str(round(p, 2)))

# --- SEND TELEGRAM ---
if sig == "BUY" or sig == "SELL":
    # Real signal
    entry_low = round(p, 2)
    entry_high = round(p + 1.0, 2)

    if sig == "BUY":
        header = "XAUUSD LONG NOW \U0001F7E2"
        sl = round(p - atr*1.0, 2)
        tp1 = round(p + atr*1.5, 2)
        tp2 = round(p + atr*2.0, 2)
    else:
        header = "XAUUSD SHORT NOW \U0001F534"
        sl = round(p + atr*1.0, 2)
        tp1 = round(p - atr*1.5, 2)
        tp2 = round(p - atr*2.0, 2)

    msg = ("\U0001F4CA " + header + "\n\n" +
           "\U0001F539 Entry : " + str(entry_low) + " - " + str(entry_high) + "\n" +
           "\u2705 TP 1: " + str(tp1) + "\n" +
           "\u2705 TP 2: " + str(tp2) + "\n\n" +
           "\u274C SL: " + str(sl))
    send_telegram(msg)
    print("Signal sent.")
else:
    # Heartbeat message
    heartbeat = ("\U0001F4CA XAUUSD Heartbeat\n\n" +
                 "\U0001F4B0 Current Price: " + str(round(p, 2)) + "\n\n" +
                 trend_text(d, "15 Min") + "\n" +
                 trend_5m_text(d5) + "\n\n" +
                 "\u23F3 Wait for signal...")
    send_telegram(heartbeat)
    print("Heartbeat sent.")
