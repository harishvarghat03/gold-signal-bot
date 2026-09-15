import requests
import os
import json
import time
from datetime import datetime, timezone

# --- TELEGRAM ---
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

def send_telegram(message):
    if TELEGRAM_TOKEN and TELEGRAM_CHAT_ID:
        url = "https://api.telegram.org/bot" + TELEGRAM_TOKEN + "/sendMessage"
        try:
            requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}, timeout=10)
        except Exception as e:
            print("Telegram error:", e)

def get_updates():
    """Read recent messages from the Telegram chat."""
    url = "https://api.telegram.org/bot" + TELEGRAM_TOKEN + "/getUpdates"
    try:
        r = requests.get(url, timeout=15)
        data = r.json()
        if data.get("ok"):
            return data.get("result", [])
    except Exception as e:
        print("getUpdates error:", e)
    return []

# --- GITHUB GIST FOR STATE (needs GIST_TOKEN) ---
GIST_ID = os.environ.get("GIST_ID")
GIST_TOKEN = os.environ.get("GIST_TOKEN")

def read_state():
    """Read last signal state from Gist."""
    if not GIST_ID or not GIST_TOKEN:
        return None
    url = "https://api.github.com/gists/" + GIST_ID
    headers = {"Authorization": "Bearer " + GIST_TOKEN}
    try:
        r = requests.get(url, headers=headers, timeout=15)
        if r.status_code == 200:
            files = r.json().get("files", {})
            if "state.json" in files:
                content = files["state.json"]["content"]
                return json.loads(content)
    except Exception as e:
        print("Gist read error:", e)
    return None

def write_state(state):
    """Write state back to Gist."""
    if not GIST_ID or not GIST_TOKEN:
        return
    url = "https://api.github.com/gists/" + GIST_ID
    headers = {"Authorization": "Bearer " + GIST_TOKEN}
    payload = {"files": {"state.json": {"content": json.dumps(state)}}}
    try:
        requests.patch(url, headers=headers, json=payload, timeout=15)
    except Exception as e:
        print("Gist write error:", e)

# --- PARSE SIGNAL FROM TELEGRAM MESSAGE ---
def parse_signal_from_message(text):
    """Extract Entry, TP1, TP2, SL from the signal message format."""
    try:
        # Format:
        # 📊 XAUUSD SHORT NOW 🔴
        # 🔹 Entry : 4287.33 - 4288.33
        # ✅ TP 1: 4280.00
        # ✅ TP 2: 4273.50
        # ❌ SL: 4293.50
        lines = text.split("\n")
        direction = None
        entry = None
        tp1 = None
        tp2 = None
        sl = None

        for line in lines:
            if "LONG NOW" in line:
                direction = "BUY"
            elif "SHORT NOW" in line:
                direction = "SELL"
            elif "Entry" in line and ":" in line:
                nums = line.split(":")[1].strip().split("-")
                entry = float(nums[0].strip())
            elif "TP 1" in line:
                tp1 = float(line.split(":")[1].strip())
            elif "TP 2" in line:
                tp2 = float(line.split(":")[1].strip())
            elif "SL" in line and ":" in line:
                sl = float(line.split(":")[1].strip())

        if direction and entry and tp1 and sl:
            return {"direction": direction, "entry": entry, "tp1": tp1, "tp2": tp2, "sl": sl}
    except Exception as e:
        print("Parse error:", e)
    return None

# --- GET CURRENT XAUUSD PRICE ---
def get_price():
    """Fetch current XAUUSD price from TradingView."""
    try:
        from tvDatafeed import TvDatafeed, Interval
        tv = TvDatafeed()
        d = tv.get_hist(symbol='XAUUSD', exchange='OANDA', interval=Interval.in_1_minute, n_bars=5)
        if d is not None and len(d) > 0:
            return float(d['close'].iloc[-1])
    except Exception as e:
        print("Price fetch error:", e)
    return None

# --- MAIN TRACKER LOGIC ---
def main():
    print("Tracker starting...")

    # 1. Read current state (open signal or nothing)
    state = read_state()
    if state is None:
        state = {"status": "idle"}

    print("Current state:", state)

    # 2. Fetch latest Telegram messages
    updates = get_updates()

    # 3. Find the latest signal message
    latest_signal_msg = None
    latest_signal_time = None
    for u in reversed(updates):
        msg = u.get("message", {})
        text = msg.get("text", "")
        if "XAUUSD" in text and ("LONG NOW" in text or "SHORT NOW" in text):
            latest_signal_msg = text
            latest_signal_time = msg.get("date")
            break

    # 4. If there's a new signal and we're idle, start tracking it
    if latest_signal_msg and state.get("status") == "idle":
        parsed = parse_signal_from_message(latest_signal_msg)
        if parsed:
            parsed["status"] = "open"
            parsed["signal_time"] = latest_signal_time
            state = parsed
            write_state(state)
            print("New signal tracked:", state)

    # 5. If a signal is open, check if TP or SL was hit
    if state.get("status") == "open":
        current_price = get_price()
        if current_price is None:
            print("Could not get price. Skipping.")
            return

        print("Current price:", current_price)
        direction = state["direction"]
        entry = state["entry"]
        tp1 = state["tp1"]
        sl = state["sl"]

        result = None
        if direction == "BUY":
            if current_price >= tp1:
                result = "WIN"
            elif current_price <= sl:
                result = "LOSS"
        elif direction == "SELL":
            if current_price <= tp1:
                result = "WIN"
            elif current_price >= sl:
                result = "LOSS"

        if result == "WIN":
            msg = ("\u2705 *TRADE WON - TP HIT* \u2705\n\n" +
                   "Previous Signal: XAUUSD " + direction + "\n" +
                   "Entry: " + str(entry) + "\n" +
                   "Exit (TP1): " + str(tp1) + "\n" +
                   "Result: +" + str(round(abs(tp1 - entry), 2)) + " points\n" +
                   "Time: " + datetime.now(timezone.utc).strftime("%H:%M UTC"))
            send_telegram(msg)
            state["status"] = "closed_win"
            write_state(state)
            print("TP HIT. Marked closed_win.")

        elif result == "LOSS":
            msg = ("\u274C *TRADE LOST - SL HIT* \u274C\n\n" +
                   "Previous Signal: XAUUSD " + direction + "\n" +
                   "Entry: " + str(entry) + "\n" +
                   "Exit (SL): " + str(sl) + "\n" +
                   "Result: -" + str(round(abs(sl - entry), 2)) + " points\n" +
                   "Time: " + datetime.now(timezone.utc).strftime("%H:%M UTC"))
            send_telegram(msg)
            state["status"] = "closed_loss"
            write_state(state)
            print("SL HIT. Marked closed_loss.")

        else:
            print("Trade still open. No action.")

    # 6. If previous trade is closed, reset to idle so we can track the next one
    if state.get("status") in ["closed_win", "closed_loss"]:
        # Only reset if there's a newer signal than the one we just closed
        if latest_signal_time and latest_signal_time > state.get("signal_time", 0):
            state = {"status": "idle"}
            write_state(state)
            print("Reset to idle for next signal.")

if __name__ == "__main__":
    main()
