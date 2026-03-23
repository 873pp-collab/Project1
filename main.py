import requests
import time
import hashlib
import hmac
import json
import os

# ----------------- CONFIG -----------------
API_KEY    = os.environ.get("API_KEY")
API_SECRET = os.environ.get("API_SECRET")
BASE_URL   = "https://cdn-ind.testnet.deltaex.org"
PRODUCT_ID = 84       # BTCUSD Perpetual

# ----------------- POSITION SIZING (100x LEVERAGE) -----------------
#
# !! TESTNET ONLY -- DO NOT USE ON LIVE ACCOUNT !!
#
# Capital          : $195 USD (testnet balance)
# Leverage         : 100x
# BTC price (approx): $71,000
# 1 contract value : $71 (0.001 BTC notional)
# Margin/contract  : $0.71 (at 100x)
#
# ORDER_SIZE = 137 contracts
#   -> Notional value  : $9,727  (137 x $71)
#   -> Margin used     : $97.27  (50% of capital per trade)
#   -> Fee per trade   : $5.16   (0.053% taker)
#   -> Reversal order  : 274 contracts (uses ~100% capital -- safe max)
#   -> Reversal margin : $194.54 (stays within $195 capital)
#   -> Liq buffer      : $97.73  on a normal trade
#
# Why 137 and not more?
#   On a reversal (closing + opening = 2x order), margin doubles.
#   137 x 2 = 274 contracts -> $194.54 margin -> just fits in $195.
#   Going above 137 would make reversal orders exceed capital -> liquidation risk.

ORDER_SIZE = 137      # contracts per trade -- max safe for $195 at 100x

# ----------------- POSITION STATE -----------------
# None = no position, "LONG" = long open, "SHORT" = short open
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
    body_str  = json.dumps(body, separators=(',', ':')) if body else ""
    message   = method + timestamp + path + body_str
    signature = generate_signature(API_SECRET, message)

    headers = {
        "api-key":      API_KEY,
        "timestamp":    timestamp,
        "signature":    signature,
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
        "side":        side,
        "size":        size
    }
    notional = round(size * 71, 2)
    margin   = round(size * 0.71, 2)
    print(f"📤 Placing {side.upper()} | {size} contracts | Notional: ~${notional} | Margin: ~${margin}")

    result = make_request("POST", "/v2/orders", body)

    if result.get("success"):
        fill_price = result["result"].get("average_fill_price", "N/A")
        print(f"✅ Filled at: {fill_price}")
    else:
        print(f"❌ Order failed: {result}")

    return result

# ----------------- BUY LOGIC -----------------
def buy():
    global current_position

    if current_position == "LONG":
        print("🟢 Already LONG — skipping buy")
        return

    if current_position == "SHORT":
        # Single order: 2x size closes SHORT + opens LONG
        print("🔄 Reversing SHORT → LONG (274 contracts, ~$194.54 margin)")
        result = place_order("buy", ORDER_SIZE * 2)
    else:
        print("🟢 Opening LONG (137 contracts, ~$97.27 margin)")
        result = place_order("buy", ORDER_SIZE)

    current_position = "LONG"
    print(f"📊 Position: LONG | {ORDER_SIZE} contracts | Notional: ~${ORDER_SIZE * 71}")
    return result

# ----------------- SELL LOGIC -----------------
def sell():
    global current_position

    if current_position == "SHORT":
        print("🔴 Already SHORT — skipping sell")
        return

    if current_position == "LONG":
        # Single order: 2x size closes LONG + opens SHORT
        print("🔄 Reversing LONG → SHORT (274 contracts, ~$194.54 margin)")
        result = place_order("sell", ORDER_SIZE * 2)
    else:
        print("🔴 Opening SHORT (137 contracts, ~$97.27 margin)")
        result = place_order("sell", ORDER_SIZE)

    current_position = "SHORT"
    print(f"📊 Position: SHORT | {ORDER_SIZE} contracts | Notional: ~${ORDER_SIZE * 71}")
    return result

# ----------------- SIGNAL HANDLER -----------------
def handle_signal(signal):
    signal = signal.strip().upper()
    print(f"\n{'='*50}")
    print(f"📩 Signal   : {signal}")
    print(f"📊 Position : {current_position}")
    print(f"💰 Capital  : $195 | Leverage: 100x | Size: {ORDER_SIZE} contracts")
    print(f"{'='*50}")

    if "BUY" in signal:
        buy()
    elif "SELL" in signal:
        sell()
    else:
        print(f"⚠️ Unknown signal: '{signal}'")
        print("   Valid signals: BUY | SELL")
