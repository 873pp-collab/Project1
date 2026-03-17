import requests
import time
import hashlib
import hmac
import json

# ----------------- CONFIG -----------------
API_KEY = "Mz75LCYjux76NbmRH08a0XUnMRribH"
API_SECRET = "jSwTn8bVs6IT2SyRgVHfI8m4U1ueudSrRGMpVpEhjHnUJ4Ne9KVHWKirZND6"
BASE_URL = "https://cdn-ind.testnet.deltaex.org"
PRODUCT_ID = 84   # BTCUSD Perpetual
ORDER_SIZE = 1    # contracts per trade

# ----------------- POSITION STATE -----------------
# We track position in memory
# None = no position, "LONG" = bought, "SHORT" = sold
current_position = None

# ----------------- SIGNATURE -----------------
def generate_signature(secret, message):
    return hmac.new(
        secret.encode(),
        message.encode(),
        hashlib.sha256
    ).hexdigest()

# ----------------- API REQUEST -----------------
def make_request(method, path, body=None):
    timestamp = str(int(time.time()))
    body_str = json.dumps(body, separators=(',', ':')) if body else ""
    message = method + timestamp + path + body_str
    signature = generate_signature(API_SECRET, message)

    headers = {
        "api-key": API_KEY,
        "timestamp": timestamp,
        "signature": signature,
        "Content-Type": "application/json"
    }

    if method == "POST":
        response = requests.post(BASE_URL + path, headers=headers, data=body_str)
    else:
        response = requests.get(BASE_URL + path, headers=headers)

    return response.json()

# ----------------- PLACE ORDER -----------------
def place_order(side, size=ORDER_SIZE):
    body = {
        "product_id": PRODUCT_ID,
        "order_type": "market_order",
        "side": side,
        "size": size
    }
    print(f"📤 Placing {side.upper()} order — {size} contract(s)")
    result = make_request("POST", "/v2/orders", body)
    
    if result.get("success"):
        fill_price = result["result"].get("average_fill_price", "N/A")
        print(f"✅ Order filled at price: {fill_price}")
    else:
        print(f"❌ Order failed: {result}")
    
    return result

# ----------------- CLOSE POSITION -----------------
def close_position():
    global current_position

    if current_position is None:
        print("ℹ️ No open position to close")
        return

    close_side = "sell" if current_position == "LONG" else "buy"
    print(f"⚠️ Closing {current_position} position with {close_side.upper()}")
    
    result = place_order(close_side, ORDER_SIZE)
    current_position = None
    return result

# ----------------- BUY LOGIC -----------------
def buy():
    global current_position

    if current_position == "LONG":
        print("🟢 Already in LONG position — skipping buy")
        return

    if current_position == "SHORT":
        print("🔄 Reversing SHORT → LONG")
        close_position()

    result = place_order("buy")
    current_position = "LONG"
    print(f"🟢 Position is now: LONG")
    return result

# ----------------- SELL LOGIC -----------------
def sell():
    global current_position

    if current_position == "SHORT":
        print("🔴 Already in SHORT position — skipping sell")
        return

    if current_position == "LONG":
        print("🔄 Reversing LONG → SHORT")
        close_position()

    result = place_order("sell")
    current_position = "SHORT"
    print(f"🔴 Position is now: SHORT")
    return result

# ----------------- SIGNAL HANDLER -----------------
def handle_signal(signal):
    signal = signal.strip().upper()
    print(f"\n📩 Signal received: {signal}")
    print(f"📊 Current position: {current_position}")

    if "BUY" in signal:
        buy()
    elif "SELL" in signal:
        sell()
    else:
        print(f"⚠️ Unknown signal: {signal}")